import { useState } from "react";
import { adminApi } from "../adminApi";

export default function SettleForm({ fight, onSettled }) {
  const [winner, setWinner] = useState(""); // "a" | "b" | "draw" | "nc"
  const [method, setMethod] = useState("ko_tko");
  const [round, setRound] = useState("");
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  const needsRound = method === "ko_tko" || method === "submission";
  const winnerPicksMethod = winner === "a" || winner === "b";

  async function handleSubmit(e) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const payload = {
        winner_fighter_id: winner === "a" ? fight.fighter_a.id : winner === "b" ? fight.fighter_b.id : null,
        result_method: winnerPicksMethod ? method : winner === "draw" ? "draw" : "no_contest",
        result_round: winnerPicksMethod && needsRound && round ? parseInt(round, 10) : null,
      };
      await adminApi.settleFight(fight.id, payload);
      onSettled();
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="form-card" onSubmit={handleSubmit}>
      <h2 className="form-card__title">Settle Fight</h2>
      <div className="form-row">
        <div className="form-field">
          <label>Winner</label>
          <select required value={winner} onChange={(e) => setWinner(e.target.value)}>
            <option value="">Select…</option>
            <option value="a">{fight.fighter_a.name} (Red)</option>
            <option value="b">{fight.fighter_b.name} (Blue)</option>
            <option value="draw">Draw</option>
            <option value="nc">No Contest</option>
          </select>
        </div>
        {winnerPicksMethod && (
          <div className="form-field">
            <label>Method</label>
            <select value={method} onChange={(e) => setMethod(e.target.value)}>
              <option value="ko_tko">KO/TKO</option>
              <option value="submission">Submission</option>
              <option value="decision">Decision</option>
            </select>
          </div>
        )}
        {winnerPicksMethod && needsRound && (
          <div className="form-field">
            <label>Round</label>
            <input type="number" min="1" placeholder="2" value={round} onChange={(e) => setRound(e.target.value)} />
          </div>
        )}
      </div>
      <button className="btn btn-gold" disabled={submitting || !winner}>
        {submitting ? "Settling…" : "Settle Fight"}
      </button>
      <p style={{ fontSize: 12, color: "var(--color-text-muted)", marginTop: 8 }}>
        This immediately resolves every open market and pays out or forfeits every pending bet. Cannot be undone.
      </p>
      {error && <p className="error-text">{error}</p>}
    </form>
  );
}
