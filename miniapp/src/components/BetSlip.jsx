import { useState } from "react";
import { X } from "lucide-react";
import { hapticError, hapticSuccess } from "../telegram";

const QUICK_STAKES = [20, 50, 100, 200];

export default function BetSlip({ legs, wallet, onClose, onRemoveLeg, onConfirm }) {
  const [stake, setStake] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  const isParlay = legs.length > 1;
  const combinedOdds = legs.reduce((acc, leg) => acc * parseFloat(leg.outcome.odds), 1);
  const stakeNum = parseFloat(stake) || 0;
  const potentialPayout = (stakeNum * combinedOdds).toFixed(2);
  const overBalance = wallet && stakeNum > parseFloat(wallet.balance);

  async function handleConfirm() {
    if (stakeNum <= 0) {
      setError("Enter a stake amount");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await onConfirm(stakeNum.toFixed(2));
      hapticSuccess();
    } catch (e) {
      hapticError();
      setError(e.message || "Couldn't place that bet");
      setSubmitting(false);
    }
  }

  if (legs.length === 0) {
    // The user removed every leg while the slip was open — nothing left to show.
    return (
      <div className="bet-slip-overlay" onClick={onClose}>
        <div className="bet-slip" onClick={(e) => e.stopPropagation()}>
          <p className="empty-note">No selections left.</p>
          <button className="btn-secondary" onClick={onClose}>Close</button>
        </div>
      </div>
    );
  }

  return (
    <div className="bet-slip-overlay" onClick={onClose}>
      <div className="bet-slip" onClick={(e) => e.stopPropagation()}>
        {isParlay && (
          <div className="bet-slip__parlay-badge">
            {legs.length}-Leg Parlay — all selections must win
          </div>
        )}

        <div className="bet-slip__legs">
          {legs.map((leg) => (
            <div className="bet-slip__leg" key={leg.outcome.id}>
              <div className="bet-slip__leg-info">
                <span className="bet-slip__leg-fight">{leg.fightLabel}</span>
                <span className="bet-slip__label">{leg.outcome.label}</span>
              </div>
              <span className="bet-slip__odds">{leg.outcome.odds}</span>
              {isParlay && (
                <button
                  className="bet-slip__leg-remove"
                  onClick={() => onRemoveLeg(leg.outcome.id)}
                  aria-label="Remove selection"
                >
                  <X size={14} />
                </button>
              )}
            </div>
          ))}
        </div>

        {isParlay && (
          <div className="bet-slip__payout" style={{ marginTop: "var(--space-2)" }}>
            <span>Combined odds</span>
            <strong>{combinedOdds.toFixed(2)}</strong>
          </div>
        )}

        <input
          className="bet-slip__stake-input"
          type="number"
          inputMode="decimal"
          placeholder={`Stake (${wallet?.currency || "ETB"})`}
          value={stake}
          onChange={(e) => setStake(e.target.value)}
          autoFocus
        />

        <div className="bet-slip__quick-stakes">
          {QUICK_STAKES.map((amt) => (
            <button key={amt} className="quick-stake-btn" onClick={() => setStake(String(amt))}>
              {amt}
            </button>
          ))}
        </div>

        <div className="bet-slip__payout">
          <span>Potential payout</span>
          <strong>{stakeNum > 0 ? `${potentialPayout} ${wallet?.currency || "ETB"}` : "—"}</strong>
        </div>

        {overBalance && <p className="error-text">That's more than your {wallet.balance} {wallet.currency} balance</p>}
        {error && <p className="error-text">{error}</p>}

        <button className="btn-primary" onClick={handleConfirm} disabled={submitting || stakeNum <= 0 || overBalance}>
          {submitting ? "Placing…" : isParlay ? "Place Parlay" : "Place Bet"}
        </button>
        <button className="btn-secondary" onClick={onClose}>
          Cancel
        </button>
      </div>
    </div>
  );
}
