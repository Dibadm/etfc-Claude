import { useEffect, useState } from "react";
import { adminApi } from "../adminApi";
import FighterPicker from "./FighterPicker";

function formatDate(iso) {
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" }) +
    " " + d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

export default function FightsList({ onSelectFight }) {
  const [fights, setFights] = useState(null);
  const [fighters, setFighters] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ event_name: "", weight_class: "", fighter_a_id: "", fighter_b_id: "", scheduled_at: "", is_main_event: false });
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  function refresh() {
    adminApi.listFights().then(setFights).catch((e) => setError(e.message));
    adminApi.listFighters().then(setFighters).catch(() => {});
  }

  useEffect(refresh, []);

  async function handleCreateFighter(name, imageUrl) {
    const fighter = await adminApi.createFighter({ name, image_url: imageUrl });
    setFighters((prev) => [...prev, fighter]);
    return fighter;
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await adminApi.createFight({
        event_name: form.event_name,
        weight_class: form.weight_class || null,
        fighter_a_id: form.fighter_a_id,
        fighter_b_id: form.fighter_b_id,
        scheduled_at: new Date(form.scheduled_at).toISOString(),
        is_main_event: form.is_main_event,
      });
      setForm({ event_name: form.event_name, weight_class: "", fighter_a_id: "", fighter_b_id: "", scheduled_at: "", is_main_event: false });
      setShowForm(false);
      refresh();
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
        <h1 className="page-title" style={{ margin: 0 }}>Fights</h1>
        <button className="btn btn-gold" onClick={() => setShowForm((v) => !v)}>
          {showForm ? "Cancel" : "+ New Fight"}
        </button>
      </div>

      {showForm && (
        <form className="form-card" onSubmit={handleSubmit}>
          <h2 className="form-card__title">Create Fight</h2>
          <div className="form-row">
            <div className="form-field">
              <label>Event name</label>
              <input
                required
                placeholder="ETFC 11"
                value={form.event_name}
                onChange={(e) => setForm({ ...form, event_name: e.target.value })}
              />
            </div>
            <div className="form-field">
              <label>Weight class</label>
              <input
                placeholder="Lightweight"
                value={form.weight_class}
                onChange={(e) => setForm({ ...form, weight_class: e.target.value })}
              />
            </div>
          </div>
          <div className="form-row">
            <FighterPicker
              label="Red corner (Fighter A)"
              fighters={fighters}
              value={form.fighter_a_id}
              onChange={(id) => setForm({ ...form, fighter_a_id: id })}
              onCreateNew={handleCreateFighter}
            />
            <FighterPicker
              label="Blue corner (Fighter B)"
              fighters={fighters}
              value={form.fighter_b_id}
              onChange={(id) => setForm({ ...form, fighter_b_id: id })}
              onCreateNew={handleCreateFighter}
            />
          </div>
          <div className="form-row">
            <div className="form-field">
              <label>Scheduled at</label>
              <input
                required
                type="datetime-local"
                value={form.scheduled_at}
                onChange={(e) => setForm({ ...form, scheduled_at: e.target.value })}
              />
            </div>
            <div className="form-field" style={{ justifyContent: "flex-end" }}>
              <label style={{ display: "flex", alignItems: "center", gap: 6, cursor: "pointer" }}>
                <input
                  type="checkbox"
                  checked={form.is_main_event}
                  onChange={(e) => setForm({ ...form, is_main_event: e.target.checked })}
                  style={{ width: "auto" }}
                />
                ★ This is the main event
              </label>
            </div>
          </div>
          <button
            className="btn btn-gold"
            type="submit"
            disabled={submitting || !form.fighter_a_id || !form.fighter_b_id || form.fighter_a_id === form.fighter_b_id}
          >
            {submitting ? "Creating…" : "Create Fight"}
          </button>
          {form.fighter_a_id && form.fighter_a_id === form.fighter_b_id && (
            <p className="error-text">Fighter A and B must be different</p>
          )}
          {error && <p className="error-text">{error}</p>}
        </form>
      )}

      {fights === null && <p className="empty-note">Loading…</p>}
      {fights?.length === 0 && <p className="empty-note">No fights yet — create one above.</p>}
      {fights?.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>Event</th>
              <th>Matchup</th>
              <th>Weight</th>
              <th>Date</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {fights.map((f) => (
              <tr key={f.id} className="fight-row" onClick={() => onSelectFight(f)}>
                <td>{f.event_name}{f.is_main_event && <span title="Main event" style={{ color: "var(--color-gold-bright)", marginLeft: 6 }}>★</span>}</td>
                <td>
                  <span className="tag-red">{f.fighter_a.name}</span> vs{" "}
                  <span className="tag-blue">{f.fighter_b.name}</span>
                </td>
                <td>{f.weight_class || "—"}</td>
                <td className="mono">{formatDate(f.scheduled_at)}</td>
                <td>
                  <span className={`pill pill--${f.status}`}>{f.status}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
