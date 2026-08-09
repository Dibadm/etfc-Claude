function initials(name) {
  const parts = name.trim().split(/\s+/);
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

/** Shows the fighter's photo if one's set; falls back to a corner-colored
 * initials badge otherwise. Never breaks layout if image_url is missing,
 * broken, or slow — the fallback renders immediately and a loaded image
 * just replaces it. */
export default function FighterAvatar({ fighter, corner, size = 48 }) {
  const dims = { width: size, height: size, borderRadius: "50%" };

  if (fighter.image_url) {
    return (
      <div style={{ position: "relative", width: size, height: size, flexShrink: 0 }}>
        <img
          src={fighter.image_url}
          alt={fighter.name}
          style={{ ...dims, objectFit: "cover", border: `2px solid var(--color-${corner}-corner)`, display: "block" }}
          onError={(e) => {
            // Swap to the initials fallback in place if the URL 404s or the
            // photo fails to load — no broken-image icon ever shown.
            e.target.style.display = "none";
            e.target.nextSibling.style.display = "flex";
          }}
        />
        <div style={{ position: "absolute", inset: 0, display: "none" }}>
          <InitialsFallback fighter={fighter} corner={corner} size={size} />
        </div>
      </div>
    );
  }

  return <InitialsFallback fighter={fighter} corner={corner} size={size} />;
}

export function InitialsFallback({ fighter, corner, size = 48, style = {} }) {
  return (
    <div
      style={{
        width: size,
        height: size,
        borderRadius: "50%",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: `var(--color-${corner}-corner-dim)`,
        border: `2px solid var(--color-${corner}-corner)`,
        color: "var(--color-text)",
        fontFamily: "var(--font-display)",
        fontWeight: 600,
        fontSize: size * 0.36,
        flexShrink: 0,
        ...style,
      }}
    >
      {initials(fighter.name)}
    </div>
  );
}
