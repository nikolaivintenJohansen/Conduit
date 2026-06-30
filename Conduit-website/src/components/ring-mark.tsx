interface RingMarkProps {
  className?: string;
  size?: number;
  withWordmark?: boolean;
}

export function RingMark({ className, size = 32, withWordmark = false }: RingMarkProps) {
  if (withWordmark) {
    return (
      <span className={className} style={{ display: "inline-flex", alignItems: "center", gap: 10 }}>
        <RingMark size={size} />
        <span
          style={{
            fontFamily: "Inter, sans-serif",
            fontWeight: 700,
            fontSize: size * 0.62,
            letterSpacing: "-0.02em",
            color: "var(--ink)",
            lineHeight: 1,
          }}
        >
          Conduit
        </span>
      </span>
    );
  }
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 64 64"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-label="Conduit"
      role="img"
    >
      <defs>
        <mask id="ring-mask-left">
          <rect width="64" height="64" fill="white" />
          {/* hide section where right ring is on top */}
          <path d="M32 18 a14 14 0 0 1 0 28 Z" fill="black" />
        </mask>
      </defs>
      {/* right ring (secondary, drawn first so left can weave over it) */}
      <circle cx="42" cy="32" r="14" stroke="#0084FF" strokeWidth="6" fill="none" />
      {/* left ring (primary) over the right */}
      <circle cx="22" cy="32" r="14" stroke="#0061D5" strokeWidth="6" fill="none" />
      {/* small over-under accent: re-draw a tiny arc of the right ring on top to weave */}
      <path
        d="M42 18 a14 14 0 0 1 12.124 21 "
        stroke="#0084FF"
        strokeWidth="6"
        fill="none"
        strokeLinecap="butt"
      />
    </svg>
  );
}
