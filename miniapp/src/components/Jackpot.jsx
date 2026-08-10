import { useEffect, useState } from "react";
import { api } from "../api";
import { hapticError, hapticSuccess } from "../telegram";

export default function Jackpot() {
  const [rounds, setRounds] = useState([]);
  const [selectedRound, setSelectedRound] = useState(null);
  const [picks, setPicks] = useState({});
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  const [myEntries, setMyEntries] = useState([]);

  useEffect(() => {
    api.jackpotRounds().then(setRounds).catch((e) => setError(e.message)).finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (selectedRound) {
      api.myJackpotEntries().then(setMyEntries).catch(() => {});
    }
  }, [selectedRound]);

  function togglePick(fightId, fighterSide) {
    setPicks((prev) => {
      const next = { ...prev };
      if (next[fightId] === fighterSide) {
        delete next[fightId];
      } else {
        next[fightId] = fighterSide;
      }
      return next;
    });
  }

  async function handleSubmit(e) {
    e.preventDefault();
    if (!selectedRound) return;
    setSubmitting(true);
    setError(null);
    setSuccess(null);
    try {
      const entry = await api.submitJackpotEntry(selectedRound.id, picks);
      setSuccess(`Jackpot entry submitted! Good luck.`);
      setPicks({});
      hapticSuccess();
    } catch (e) {
      hapticError();
      setError(e.message);
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) return <div className="spinner" />;

  if (selectedRound) {
    const alreadyEntered = myEntries.some((e) => e.round_id === selectedRound.id);
    const allPicked = (selectedRound.fight_ids?.length || selectedRound.fight_ids.length) === Object.keys(picks).length;
    const now = new Date();
    const isLocked = now >= new Date(selectedRound.deadline);
    const roundStatus = selectedRound.status;

    return (
      <div>
        <button
          onClick={() => { setSelectedRound(null); setPicks({}); }}
          style={{
            background: "none",
            border: "none",
            color: "var(--color-text-muted)",
            cursor: "pointer",
            marginBottom: "var(--space-3)",
            fontSize: 14,
          }}
        >
          ← Back to jackpot rounds
        </button>

        <div className="form-card" style={{ margin: 0 }}>
          <div className="form-card__title">{selectedRound.name}</div>
          <div style={{ fontSize: 13, color: "var(--color-text-muted)", marginBottom: "var(--space-3)" }}>
            Entry fee: {selectedRound.entry_fee} ETB · Prize pool: {selectedRound.prize_pool.toLocaleString()} ETB ·
            Pick {selectedRound.min_correct_to_win}+ of {selectedRound.fight_ids.length} to win
          </div>

          {roundStatus === "settled" && (
            <div style={{ marginBottom: "var(--space-3)", padding: "var(--space-3)", background: "var(--color-surface-raised)", borderRadius: "var(--radius-md)" }}>
              <strong>Settled</strong>
              {myEntries
                .filter((e) => e.round_id === selectedRound.id)
                .map((e) => (
                  <div key={e.id} style={{ marginTop: "var(--space-2)" }}>
                    You got {e.correct_count}/{selectedRound.fight_ids.length} correct · {e.won ? `Won ${e.payout?.toLocaleString()} ETB` : "Better luck next time"}
                  </div>
                ))}
            </div>
          )}

          {alreadyEntered && roundStatus !== "settled" && (
            <div style={{ marginBottom: "var(--space-3)", padding: "var(--space-3)", background: "var(--color-surface-raised)", borderRadius: "var(--radius-md)" }}>
              You already entered this round. Check back after all fights are settled to see if you won.
            </div>
          )}

          {!alreadyEntered && roundStatus === "open" && !isLocked && (
            <form onSubmit={handleSubmit}>
              <div style={{ marginBottom: "var(--space-3)" }}>
                {(selectedRound.fights || []).map((fight, idx) => {
                  const fa = fight.fighter_a || {};
                  const fb = fight.fighter_b || {};
                  const faName = fa.nickname || fa.name || "Fighter A";
                  const fbName = fb.nickname || fb.name || "Fighter B";
                  const event = fight.event_name || "";
                  const picked = picks[fight.id];

                  return (
                    <div
                      key={fight.id}
                      style={{
                        display: "flex",
                        flexDirection: "column",
                        gap: "var(--space-2)",
                        padding: "var(--space-3) 0",
                        borderBottom: "1px solid var(--color-border)",
                      }}
                    >
                      <div style={{ fontSize: 12, color: "var(--color-text-faint)", fontWeight: 600 }}>
                        {event} · Fight {idx + 1}
                      </div>
                      <div style={{ display: "flex", gap: "var(--space-2)" }}>
                        <button
                          type="button"
                          onClick={() => togglePick(fight.id, "A")}
                          style={{
                            flex: 1,
                            padding: "10px",
                            borderRadius: "var(--radius-md)",
                            border: picked === "A" ? "2px solid var(--color-primary)" : "1px solid var(--color-border)",
                            background: picked === "A" ? "var(--color-primary)" : "var(--color-surface)",
                            color: picked === "A" ? "#fff" : "var(--color-text)",
                            cursor: "pointer",
                            fontSize: 13,
                            fontWeight: 600,
                            textAlign: "center",
                          }}
                        >
                          {faName}
                        </button>
                        <button
                          type="button"
                          onClick={() => togglePick(fight.id, "B")}
                          style={{
                            flex: 1,
                            padding: "10px",
                            borderRadius: "var(--radius-md)",
                            border: picked === "B" ? "2px solid var(--color-primary)" : "1px solid var(--color-border)",
                            background: picked === "B" ? "var(--color-primary)" : "var(--color-surface)",
                            color: picked === "B" ? "#fff" : "var(--color-text)",
                            cursor: "pointer",
                            fontSize: 13,
                            fontWeight: 600,
                            textAlign: "center",
                          }}
                        >
                          {fbName}
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
              <button
                className="btn-primary"
                type="submit"
                disabled={submitting || !allPicked}
                style={{ width: "100%" }}
              >
                {submitting ? "Submitting…" : `Pay ${selectedRound.entry_fee} ETB & Submit Entry`}
              </button>
            </form>
          )}

          {isLocked && roundStatus === "open" && (
            <p style={{ color: "var(--color-text-muted)" }}>Entries are locked. The round is in progress.</p>
          )}
        </div>
      </div>
    );
  }

  return (
    <div>
      <h1 style={{ fontSize: 20, fontWeight: 600, marginBottom: "var(--space-4)" }}>Jackpot Pool</h1>
      {rounds.length === 0 ? (
        <p style={{ color: "var(--color-text-muted)" }}>No jackpot rounds available right now.</p>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
          {rounds.map((r) => (
            <div
              key={r.id}
              onClick={() => setSelectedRound(r)}
              style={{
                background: "var(--color-surface-raised)",
                border: "1px solid var(--color-border)",
                borderRadius: "var(--radius-md)",
                padding: "var(--space-3)",
                cursor: "pointer",
              }}
            >
              <div style={{ fontWeight: 600, marginBottom: "var(--space-1)" }}>{r.name}</div>
              <div style={{ fontSize: 13, color: "var(--color-text-muted)" }}>
                {r.fight_ids.length} fights · {r.entry_fee} ETB entry · {r.prize_pool.toLocaleString()} ETB prize
              </div>
              <div style={{ fontSize: 12, color: "var(--color-text-faint)", marginTop: "var(--space-1)" }}>
                Deadline: {new Date(r.deadline).toLocaleString()} · Status: {r.status}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
