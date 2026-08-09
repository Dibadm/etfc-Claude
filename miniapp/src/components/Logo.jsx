import { useState } from "react";

/** Looks for a real logo at /logo.png (drop a file into miniapp/public/logo.png
 * to have it appear automatically — no code changes needed). Falls back to a
 * built-in glove monogram if no file is there yet, so the header never looks
 * broken or empty in the meantime. */
export default function Logo({ size = 36 }) {
  const [hasCustomLogo, setHasCustomLogo] = useState(true);

  if (hasCustomLogo) {
    return (
      <img
        src="/logo.png"
        alt="ETFC"
        width={size}
        height={size}
        style={{ borderRadius: "8px", objectFit: "cover", flexShrink: 0 }}
        onError={() => setHasCustomLogo(false)}
      />
    );
  }

  return (
    <div
      style={{
        width: size,
        height: size,
        borderRadius: "8px",
        background: "linear-gradient(160deg, var(--color-gold-bright), var(--color-gold))",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        flexShrink: 0,
      }}
    >
      <svg width={size * 0.6} height={size * 0.6} viewBox="0 0 24 24" fill="none">
        <path
          d="M7 12.5c0-2.5 1.5-4.5 3.5-5.5M17 12.5c0-2.5-1.5-4.5-3.5-5.5"
          stroke="#16130f"
          strokeWidth="1.8"
          strokeLinecap="round"
        />
        <path
          d="M6 11c-1.5 0-2.5 1.2-2.5 2.5S4.5 16 6 16h1M18 11c1.5 0 2.5 1.2 2.5 2.5S19.5 16 18 16h-1"
          stroke="#16130f"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <rect x="7" y="10" width="10" height="8" rx="3" fill="#16130f" />
      </svg>
    </div>
  );
}
