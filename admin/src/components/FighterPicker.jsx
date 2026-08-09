import { useState } from "react";

/** A <select> of existing fighters, with a "+ New fighter" option that
 * reveals a text field to create one inline — avoids forcing the admin
 * to a separate "manage fighters" screen for the common case of adding
 * a fighter while building a fight card. */
export default function FighterPicker({ label, fighters, value, onChange, onCreateNew, disabled }) {
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [newPhotoUrl, setNewPhotoUrl] = useState("");

  if (creating) {
    return (
      <div className="form-field">
        <label>{label}</label>
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <input
            placeholder="New fighter name"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            autoFocus
          />
          <input
            placeholder="Photo URL (optional)"
            value={newPhotoUrl}
            onChange={(e) => setNewPhotoUrl(e.target.value)}
          />
          <div style={{ display: "flex", gap: 6 }}>
            <button
              type="button"
              className="btn btn-sm"
              disabled={!newName.trim()}
              onClick={async () => {
                const fighter = await onCreateNew(newName.trim(), newPhotoUrl.trim() || null);
                onChange(fighter.id);
                setCreating(false);
                setNewName("");
                setNewPhotoUrl("");
              }}
            >
              Add
            </button>
            <button type="button" className="btn btn-sm" onClick={() => setCreating(false)}>
              Cancel
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="form-field">
      <label>{label}</label>
      <select
        value={value}
        disabled={disabled}
        onChange={(e) => {
          if (e.target.value === "__new__") {
            setCreating(true);
          } else {
            onChange(e.target.value);
          }
        }}
      >
        <option value="">Select fighter…</option>
        {fighters.map((f) => (
          <option key={f.id} value={f.id}>
            {f.name}
          </option>
        ))}
        <option value="__new__">+ New fighter</option>
      </select>
    </div>
  );
}
