import { describe, expect, it, vi } from 'vitest';
import { UsageBatcher, type UsageEventDto, type UsageSender } from '../src/batcher.js';
import { ServerError } from '../src/errors.js';
import type { UsageEvent } from '../src/types.js';

function ev(id: string): UsageEvent {
  return { requestId: id, model: 'gpt-4o', inputTokens: 10, outputTokens: 5 };
}

function makeSender(): {
  sender: UsageSender;
  calls: UsageEventDto[][];
  resolveNext: () => void;
  setReject: (err: unknown) => void;
  setOk: () => void;
  pending: { resolve: (() => void) | null };
} {
  const calls: UsageEventDto[][] = [];
  const pending: { resolve: (() => void) | null; reject: ((e: unknown) => void) | null } = {
    resolve: null,
    reject: null,
  };
  const sender: UsageSender = (events) =>
    new Promise((resolve, reject) => {
      calls.push(events);
      pending.resolve = () => resolve({ accepted: events.length, duplicated: 0, stream: 'uaw:usage:events', requestIds: events.map((e) => e.request_id) });
      pending.reject = reject;
    });
  return {
    sender,
    calls,
    resolveNext: () => pending.resolve?.(),
    setReject: (err) => pending.reject?.(err),
    setOk: () => pending.resolve?.(),
    pending: { resolve: null },
  };
}

describe('UsageBatcher (Phase 6.3)', () => {
  it('flushes on explicit flush()', async () => {
    const s = makeSender();
    const b = new UsageBatcher(s.sender, {
      flushIntervalMs: 0,
      maxBatchSize: 1000,
      maxBufferSize: 10_000,
      retries: 0,
      sleep: () => Promise.resolve(),
    });
    b.add(ev('r1'));
    b.add(ev('r2'));
    expect(b.size).toBe(2);
    const p = b.flush();
    s.resolveNext();
    await p;
    expect(s.calls.length).toBe(1);
    expect(s.calls[0]!.map((e) => e.request_id)).toEqual(['r1', 'r2']);
    expect(b.size).toBe(0);
  });

  it('dedupes by requestId (last write wins)', async () => {
    const s = makeSender();
    const b = new UsageBatcher(s.sender, {
      flushIntervalMs: 0,
      maxBatchSize: 1000,
      maxBufferSize: 10_000,
      retries: 0,
      sleep: () => Promise.resolve(),
    });
    b.add(ev('r1'));
    b.add({ ...ev('r1'), inputTokens: 999 });
    expect(b.size).toBe(1);
    const p = b.flush();
    s.resolveNext();
    await p;
    expect(s.calls[0]![0]!.input_tokens).toBe(999);
  });

  it('auto-flushes when maxBatchSize is reached', async () => {
    const s = makeSender();
    const b = new UsageBatcher(s.sender, {
      flushIntervalMs: 0,
      maxBatchSize: 2,
      maxBufferSize: 10_000,
      retries: 0,
      sleep: () => Promise.resolve(),
    });
    b.add(ev('r1'));
    b.add(ev('r2')); // triggers flush
    s.resolveNext();
    await vi.waitFor(() => expect(s.calls.length).toBe(1));
  });

  it('flushes on the interval timer', async () => {
    const s = makeSender();
    let tickFn: (() => void) | null = null;
    const fakeSetInterval = (fn: () => void) => {
      tickFn = fn;
      return {} as ReturnType<typeof setInterval>;
    };
    const b = new UsageBatcher(s.sender, {
      flushIntervalMs: 1000,
      maxBatchSize: 1000,
      maxBufferSize: 10_000,
      retries: 0,
      sleep: () => Promise.resolve(),
      setInterval: fakeSetInterval as unknown as typeof setInterval,
      clearInterval: () => undefined,
    });
    b.start();
    b.add(ev('r1'));
    expect(s.calls.length).toBe(0);
    tickFn!();
    s.resolveNext();
    await vi.waitFor(() => expect(s.calls.length).toBe(1));
  });

  it('retry with backoff then drop + onDrop/onError after max retries', async () => {
    const sleeps: number[] = [];
    const dropped: { reason: string; ids: string[] }[] = [];
    const errors: { code: string }[] = [];
    const calls: number[] = [];
    const alwaysRejectSender: UsageSender = async (events) => {
      calls.push(events.length);
      throw new ServerError('boom', { code: 'provider_error', status: 502 });
    };
    const b = new UsageBatcher(alwaysRejectSender, {
      flushIntervalMs: 0,
      maxBatchSize: 1000,
      maxBufferSize: 10_000,
      retries: 2,
      sleep: (ms) => {
        sleeps.push(ms);
        return Promise.resolve();
      },
      onDrop: (events, reason) => dropped.push({ reason, ids: events.map((e) => e.requestId) }),
      onError: (err) => errors.push({ code: err.code }),
    });
    b.add(ev('r1'));
    await b.flush();
    expect(calls.length).toBe(3); // initial + 2 retries
    expect(sleeps.length).toBe(2); // backoff before retries 1 and 2
    expect(dropped).toEqual([{ reason: 'max_retries', ids: ['r1'] }]);
    expect(errors).toEqual([{ code: 'provider_error' }]);
  });

  it('does not retry non-retriable 402 errors', async () => {
    const s = makeSender();
    const { PaymentRequiredError } = await import('../src/errors.js');
    const dropped: string[] = [];
    const b = new UsageBatcher(s.sender, {
      flushIntervalMs: 0,
      maxBatchSize: 1000,
      maxBufferSize: 10_000,
      retries: 3,
      sleep: () => Promise.resolve(),
      onDrop: (events) => dropped.push(...events.map((e) => e.requestId)),
    });
    b.add(ev('r1'));
    const p = b.flush();
    s.setReject(new PaymentRequiredError('no funds', { code: 'insufficient_balance' }));
    await p;
    expect(dropped).toEqual(['r1']);
    expect(s.calls.length).toBe(1); // not retried
  });

  it('applies backpressure via maxBufferSize (drops oldest)', async () => {
    const s = makeSender();
    const dropped: string[] = [];
    const b = new UsageBatcher(s.sender, {
      flushIntervalMs: 0,
      maxBatchSize: 1000,
      maxBufferSize: 2,
      retries: 0,
      sleep: () => Promise.resolve(),
      onDrop: (events) => dropped.push(...events.map((e) => e.requestId)),
    });
    b.add(ev('r1'));
    b.add(ev('r2'));
    b.add(ev('r3')); // exceeds cap, drops r1
    expect(b.size).toBe(2);
    expect(dropped).toEqual(['r1']);
    const p = b.flush();
    s.resolveNext();
    await p;
    expect(s.calls[0]!.map((e) => e.request_id)).toEqual(['r2', 'r3']);
  });

  it('shutdown() flushes pending and stops accepting events', async () => {
    const s = makeSender();
    const b = new UsageBatcher(s.sender, {
      flushIntervalMs: 0,
      maxBatchSize: 1000,
      maxBufferSize: 10_000,
      retries: 0,
      sleep: () => Promise.resolve(),
    });
    b.add(ev('r1'));
    const p = b.shutdown();
    s.resolveNext();
    await p;
    expect(s.calls.length).toBe(1);
    expect(b.size).toBe(0);
    b.add(ev('r2'));
    expect(b.size).toBe(0); // stopped
  });

  it('charge-equivalent: add() is synchronous and does not block', () => {
    const s = makeSender();
    const b = new UsageBatcher(s.sender, {
      flushIntervalMs: 0,
      maxBatchSize: 1_000_000,
      maxBufferSize: 10_000,
      retries: 0,
      sleep: () => Promise.resolve(),
    });
    const start = Date.now();
    for (let i = 0; i < 1000; i++) b.add(ev(`r${i}`));
    const elapsed = Date.now() - start;
    expect(b.size).toBe(1000);
    expect(elapsed).toBeLessThan(100); // synchronous, non-blocking
  });

  it('re-entrant flush() shares a single in-flight call', async () => {
    const s = makeSender();
    const b = new UsageBatcher(s.sender, {
      flushIntervalMs: 0,
      maxBatchSize: 1000,
      maxBufferSize: 10_000,
      retries: 0,
      sleep: () => Promise.resolve(),
    });
    b.add(ev('r1'));
    const p1 = b.flush();
    const p2 = b.flush();
    expect(p1).toBe(p2);
    s.resolveNext();
    await p1;
    expect(s.calls.length).toBe(1);
  });
});
