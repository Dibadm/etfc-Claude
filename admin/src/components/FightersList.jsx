import { useEffect, useState } from "react";
import { adminApi } from "../adminApi";

function FighterRow({ fighter, onSaved }) {
  const [editing, setEditing] = useState(false);
  const [imageUrl, setImageUrl] = useState(fighter.image_url || "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  async function save() {
    setSaving(true);
    setError(null);
    try {
      await adminApi.updateFighter(fighter.id, { image_url: imageUrl || null });
      setEditing(false);
      onSaved();
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <tr>
      <td style={{ width: 48 }}>
        {fighter.image_url ? (
          <img
            src={fighter.image_url}
            alt={fighter.name}
            width={36}
            height={36}
            style={{ borderRadius: "50%", objectFit: "cover", display: "block" }}
            onError={(e) => { e.target.style.visibility = "hidden"; }}
          />
        ) : (
          <div
            style={{
              width: 36, height: 36, borderRadius: "50%", background: "var(--color-surface-raised)",
              border: "1px solid var(--color-border)", display: "flex", alignItems: "center",
              justifyContent: "center", fontSize: 12, color: "var(--color-text-muted)",
            }}
          >
            —
          </div>
        )}
      </td>
      <td>{fighter.name}</td>
      <td>{fighter.nickname || "—"}</td>
      <td>
        {editing ? (
          <input
            style={{ width: "100%" }}
            placeholder="https://…"
            value={imageUrl}
            onChange={(e) => setImageUrl(e.target.value)}
            autoFocus
          />
        ) : (
          <span style={{ color: fighter.image_url ? "var(--color-text)" : "var(--color-text-muted)", fontSize: 13 }}>
            {fighter.image_url || "No photo set"}
          </span>
        )}
      </td>
      <td>
        {editing ? (
          <>
            <button className="btn btn-sm" onClick={save} disabled={saving}>Save</button>{" "}
            <button className="btn btn-sm" onClick={() => { setEditing(false); setImageUrl(fighter.image_url || ""); }}>
              Cancel
            </button>
          </>
        ) : (
          <button className="btn btn-sm" onClick={() => setEditing(true)}>
            {fighter.image_url ? "Edit photo" : "Add photo"}
          </button>
        )}
        {error && <div className="error-text">{error}</div>}
      </td>
    </tr>
  );
}

export default function FightersList() {
  const [fighters, setFighters] = useState(null);

  function refresh() {
    adminApi.listFighters().then(setFighters);
  }

  useEffect(refresh, []);

  return (
    <div>
      <h1 className="page-title">Fighters</h1>
      <p style={{ color: "var(--color-text-muted)", marginTop: -12, marginBottom: 20, fontSize: 14 }}>
        Paste a hosted image URL for each fighter — it'll show up on their fight cards in the Mini App.
        Fighters without a photo get an initials badge instead, so nothing looks broken in the meantime.
      </p>
      {fighters === null && <p className="empty-note">Loading…</p>}
      {fighters?.length === 0 && <p className="empty-note">No fighters yet — add one from the fight creation form.</p>}
      {fighters?.length > 0 && (
        <table>
          <thead>
            <tr>
              <th></th>
              <th>Name</th>
              <th>Nickname</th>
              <th>Photo URL</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {fighters.map((f) => (
              <FighterRow key={f.id} fighter={f} onSaved={refresh} />
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
