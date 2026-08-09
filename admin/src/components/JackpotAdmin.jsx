import { useEffect, useState } from "react";
import { adminApi } from "../adminApi";

export default function JackpotAdmin() {
  const [rounds, setRounds] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    name: "",
    fight_ids: "",
    entry_fee: "30",
    prize_pool: "1000000",
    min_correct_to_win: "10",
    deadline: "",
  });
  const [submitting, setSubmitting] = useState(false);
  const [selectedRound, setSelectedRound] = useState(null);
  const [entries, setEntries] = useState([]);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const data = await adminApi.jackpotRounds();
      setRounds(data);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(load, []);

  async function handleCreate(e) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const fightIds = form.fight_ids.split(",").map((s) => s.trim()).filter(Boolean);
      if (fightIds.length !== 11) {
        throw new Error("You must provide exactly 11 fight IDs, comma-separated.");
      }
      await adminApi.createJackpotRound({
        name: form.name,
        fight_ids: fightIds,
        entry_fee: parseFloat(form.entry_fee),
        prize_pool: parseFloat(form.prize_pool),
        min_correct_to_win: parseInt(form.min_correct_to_win, 10),
        deadline: new Date(form.deadline).toISOString(),
      });
      setShowForm(false);
      setForm({ name: "", fight_ids: "", entry_fee: "30", prize_pool: "1000000", min_correct_to_win: "10", deadline: "" });
      load();
    } catch (e) {
      setError(e.message);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleSettle(roundId) {
    if (!confirm("Settle this round? This will score all entries and credit winners.")) return;
    try {
      await adminApi.settleJackpotRound(roundId);
      load();
      if (selectedRound?.id === roundId) {
        setSelectedRound(null);
        setEntries([]);
      }
    } catch (e) {
      alert(e.message);
    }
  }

  async function viewEntries(roundId) {
    try {
      const data = await adminApi.jackpotEntries(roundId);
      setEntries(data);
      const r = rounds.find((x) => x.id === roundId);
      setSelectedRound(r);
    } catch (e) {
      alert(e.message);
    }
  }

  if (loading) return <div className="spinner" />;
  if (error) return <p className="error-text">{error}</p>;

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "var(--space-4)" }}>
        <h1 style={{ fontSize: 20, fontWeight: 600 }}>Jackpot Rounds</h1>
        <button className="btn-primary" onClick={() => setShowForm(!showForm)} style={{ fontSize: 13, padding: "6px 12px" }}>
          {showForm ? "Cancel" : "New Round"}
        </button>
      </div>

      {showForm && (
        <form onSubmit={handleCreate} style={{ marginBottom: "var(--space-4)", padding: "var(--space-3)", background: "var(--color-surface-raised)", borderRadius: "var(--radius-md)" }}>
          <div style={{ marginBottom: "var(--space-2)" }}>
            <label style={{ fontSize: 13, fontWeight: 600 }}>Name</label>
            <input
              required
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              style={{ width: "100%", marginTop: 4, padding: "8px", borderRadius: "var(--radius-md)", border: "1px solid var(--color-border)", background: "var(--color-surface)", color: "var(--color-text)" }}
              placeholder="ETFC Aug 27"
            />
          </div>
          <div style={{ marginBottom: "var(--space-2)" }}>
            <label style={{ fontSize: 13, fontWeight: 600 }}>Fight IDs (comma-separated, exactly 11)</label>
            <input
              required
              value={form.fight_ids}
              onChange={(e) => setForm({ ...form, fight_ids: e.target.value })}
              style={{ width: "100%", marginTop: 4, padding: "8px", borderRadius: "var(--radius-md)", border: "1px solid var(--color-border)", background: "var(--color-surface)", color: "var(--color-text)" }}
              placeholder="id1, id2, ..."
            />
          </div>
          <div style={{ display: "flex", gap: "var(--space-3)", marginBottom: "var(--space-2)" }}>
            <div style={{ flex: 1 }}>
              <label style={{ fontSize: 13, fontWeight: 600 }}>Entry Fee (ETB)</label>
              <input
                type="number"
                required
                value={form.entry_fee}
                onChange={(e) => setForm({ ...form, entry_fee: e.target.value })}
                style={{ width: "100%", marginTop: 4, padding: "8px", borderRadius: "var(--radius-md)", border: "1px solid var(--color-border)", background: "var(--color-surface)", color: "var(--color-text)" }}
              />
            </div>
            <div style={{ flex: 1 }}>
              <label style={{ fontSize: 13, fontWeight: 600 }}>Prize Pool (ETB)</label>
              <input
                type="number"
                required
                value={form.prize_pool}
                onChange={(e) => setForm({ ...form, prize_pool: e.target.value })}
                style={{ width: "100%", marginTop: 4, padding: "8px", borderRadius: "var(--radius-md)", border: "1px solid var(--color-border)", background: "var(--color-surface)", color: "var(--color-text)" }}
              />
            </div>
          </div>
          <div style={{ display: "flex", gap: "var(--space-3)", marginBottom: "var(--space-2)" }}>
            <div style={{ flex: 1 }}>
              <label style={{ fontSize: 13, fontWeight: 600 }}>Min Correct to Win</label>
              <input
                type="number"
                required
                min={1}
                max={11}
                value={form.min_correct_to_win}
                onChange={(e) => setForm({ ...form, min_correct_to_win: e.target.value })}
                style={{ width: "100%", marginTop: 4, padding: "8px", borderRadius: "var(--radius-md)", border: "1px solid var(--color-border)", background: "var(--color-surface)", color: "var(--color-text)" }}
              />
            </div>
            <div style={{ flex: 1 }}>
              <label style={{ fontSize: 13, fontWeight: 600 }}>Deadline (UTC)</label>
              <input
                type="datetime-local"
                required
                value={form.deadline}
                onChange={(e) => setForm({ ...form, deadline: e.target.value })}
                style={{ width: "100%", marginTop: 4, padding: "8px", borderRadius: "var(--radius-md)", border: "1px solid var(--color-border)", background: "var(--color-surface)", color: "var(--color-text)" }}
              />
            </div>
          </div>
          <button className="btn-primary" type="submit" disabled={submitting} style={{ fontSize: 13, padding: "8px 12px" }}>
            {submitting ? "Creating…" : "Create Round"}
          </button>
        </form>
      )}

      {selectedRound && (
        <div style={{ marginBottom: "var(--space-4)", padding: "var(--space-3)", background: "var(--color-surface-raised)", borderRadius: "var(--radius-md)" }}>
          <div style={{ fontWeight: 600, marginBottom: "var(--space-2)" }}>Entries for {selectedRound.name}</div>
          {entries.length === 0 ? (
            <p style={{ color: "var(--color-text-muted)", fontSize: 13 }}>No entries yet.</p>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)" }}>
              {entries.map((e) => (
                <div key={e.id} style={{ fontSize: 13, padding: "6px 0", borderBottom: "1px solid var(--color-border)" }}>
                  User {e.user_id.slice(0, 8)} — {e.correct_count}/11 correct — {e.won ? `Won ${e.payout?.toLocaleString()} ETB` : "Not a winner"}
                </div>
              ))}
            </div>
          )}
          <button
            className="btn-secondary"
            onClick={() => { setSelectedRound(null); setEntries([]); }}
            style={{ marginTop: "var(--space-2)", fontSize: 13, padding: "6px 12px" }}
          >
            Close
          </button>
        </div>
      )}

      <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
        {rounds.map((r) => (
          <div
            key={r.id}
            style={{
              background: "var(--color-surface-raised)",
              border: "1px solid var(--color-border)",
              borderRadius: "var(--radius-md)",
              padding: "var(--space-3)",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "var(--space-1)" }}>
              <strong>{r.name}</strong>
              <span style={{ fontSize: 11, fontWeight: 600, textTransform: "uppercase", padding: "2px 8px", borderRadius: "var(--radius-sm)", background: "var(--color-primary)", color: "#fff" }}>
                {r.status}
              </span>
            </div>
            <div style={{ fontSize: 13, color: "var(--color-text-muted)" }}>
              {r.fight_ids.length} fights · {r.entry_fee} ETB entry · {r.prize_pool.toLocaleString()} ETB prize
            </div>
            <div style={{ fontSize: 12, color: "var(--color-text-faint)", marginTop: "var(--space-1)" }}>
              Deadline: {new Date(r.deadline).toLocaleString()}
            </div>
            <div style={{ display: "flex", gap: "var(--space-2)", marginTop: "var(--space-2)" }}>
              <button className="btn-secondary" onClick={() => viewEntries(r.id)} style={{ fontSize: 13, padding: "6px 12px" }}>
                View Entries
              </button>
              {r.status !== "settled" && r.status !== "cancelled" && (
                <button className="btn-primary" onClick={() => handleSettle(r.id)} style={{ fontSize: 13, padding: "6px 12px" }}>
                  Settle Round
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
