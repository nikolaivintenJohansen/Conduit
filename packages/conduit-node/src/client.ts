import { authorize } from './authorize.js';
import { UsageBatcher, type UsageEventDto, type UsageSender } from './batcher.js';
import { Transport } from './transport.js';
import type {
  ConduitConfig,
  AuthorizeOptions,
  AuthorizeResult,
  ChargeInput,
  FetchLike,
  Logger,
  UsageEvent,
  UsageIngestResult,
} from './types.js';

const DEFAULT_BASE_URL = 'https://api.example.com/v1';

const DEFAULT_FLUSH_INTERVAL_MS = 5000;
const DEFAULT_MAX_BATCH_SIZE = 100;
const DEFAULT_MAX_BUFFER_SIZE = 10_000;
const DEFAULT_TIMEOUT_MS = 10_000;
const DEFAULT_RETRIES = 3;

const SILENT_LOGGER: Logger = {};

function env(name: string): string | undefined {
  if (typeof process === 'undefined' || typeof process.env !== 'object') return undefined;
  return process.env[name] as string | undefined;
}

/**
 * Conduit client — the smart meter inside a partner app.
 *
 * - `authorize()` (Phase 6.2): pre-auth + hold on the Redis fast path. Throws
 *   `PaymentRequiredError` on 402 and `UnauthorizedError` on 401.
 * - `charge()` (Phase 6.3): fire-and-forget, in-memory batched usage; flushes to
 *   POST /v1/usage periodically, by size, or on `flush()`/`shutdown()`.
 * - 402 handling (Phase 6.4): catch `PaymentRequiredError` and freeze compute.
 */
export class Conduit {
  private readonly transport: Transport;
  private readonly batcher: UsageBatcher;
  private readonly logger: Logger;

  constructor(config: ConduitConfig) {
    const apiKey = config.apiKey ?? env('CONDUIT_API_KEY');
    if (!apiKey) throw new Error('Conduit: apiKey is required (or set CONDUIT_API_KEY)');

    const baseUrl = (config.baseUrl ?? env('CONDUIT_BASE_URL') ?? DEFAULT_BASE_URL).replace(
      /\/+$/,
      '',
    );
    const fetchImpl: FetchLike = config.fetch ?? fetch;
    const timeoutMs = config.timeoutMs ?? DEFAULT_TIMEOUT_MS;

    this.logger = config.logger ?? SILENT_LOGGER;
    this.transport = new Transport(baseUrl, apiKey, timeoutMs, fetchImpl);

    const sender: UsageSender = async (events: UsageEventDto[]): Promise<UsageIngestResult> => {
      const { data } = await this.transport.post<UsageIngestResult>(
        '/usage',
        { events },
        undefined,
      );
      return data;
    };

    this.batcher = new UsageBatcher(sender, {
      flushIntervalMs: config.flushIntervalMs ?? DEFAULT_FLUSH_INTERVAL_MS,
      maxBatchSize: config.maxBatchSize ?? DEFAULT_MAX_BATCH_SIZE,
      maxBufferSize: config.maxBufferSize ?? DEFAULT_MAX_BUFFER_SIZE,
      retries: config.retries ?? DEFAULT_RETRIES,
      logger: this.logger,
      onDrop: config.onDrop,
      onError: config.onError,
    });
    this.batcher.start();
  }

  /** Phase 6.2 — pre-authorize on the fast path. */
  authorize(options: AuthorizeOptions): Promise<AuthorizeResult> {
    return authorize(this.transport, options);
  }

  /** Phase 6.3 — enqueue usage for batched, fire-and-forget flush. Synchronous, non-blocking. */
  charge(input: ChargeInput): void {
    const event: UsageEvent = {
      requestId: input.requestId,
      model: input.model,
      inputTokens: input.inputTokens ?? 0,
      outputTokens: input.outputTokens ?? 0,
    };
    if (input.provider !== undefined) event.provider = input.provider;
    this.batcher.add(event);
  }

  /** Flush all buffered usage events now. Await in serverless handlers before returning. */
  flush(): Promise<void> {
    return this.batcher.flush();
  }

  /** Stop the timer and await a final flush. Call on graceful process shutdown. */
  shutdown(): Promise<void> {
    return this.batcher.shutdown();
  }

  /** Current number of buffered (un-flushed) usage events. */
  get pendingCount(): number {
    return this.batcher.size;
  }
}
