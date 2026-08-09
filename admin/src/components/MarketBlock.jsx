import { useState } from "react";
import { adminApi } from "../adminApi";

const MARKET_TITLES = {
  moneyline: "Moneyline",
  method_of_victory: "Method of Victory",
  round_prop: "Round Props",
};

function OutcomeRow({ outcome, onOddsSaved }) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(outcome.odds);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  async function save() {
    setSaving(true);
    setError(null);
    try {
      await adminApi.updateOdds(outcome.id, value);
      setEditing(false);
      onOddsSaved();
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <tr>
      <td>{outcome.label}</td>
      <td className="mono">
        {editing ? (
          <input className="odds-cell-input" value={value} onChange={(e) => setValue(e.target.value)} autoFocus />
        ) : (
          outcome.odds
        )}
      </td>
      <td>
        {editing ? (
          <>
            <button className="btn btn-sm" onClick={save} disabled={saving}>
              Save
            </button>{" "}
            <button className="btn btn-sm" onClick={() => { setEditing(false); setValue(outcome.odds); }}>
              Cancel
            </button>
          </>
        ) : (
          <button className="btn btn-sm" onClick={() => setEditing(true)}>
            Edit odds
          </button>
        )}
        {error && <div className="error-text">{error}</div>}
      </td>
    </tr>
  );
}

export default function MarketBlock({ market, onRefresh }) {
  const [busy, setBusy] = useState(false);

  async function toggleSuspend() {
    setBusy(true);
    try {
      if (market.status === "open") {
        await adminApi.suspendMarket(market.id);
      } else if (market.status === "suspended") {
        await adminApi.reopenMarket(market.id);
      }
      onRefresh();
    } finally {
      setBusy(false);
    }
  }

  const canToggle = market.status === "open" || market.status === "suspended";

  return (
    <div className="market-block">
      <div className="market-block__header">
        <span className="market-block__title">{MARKET_TITLES[market.market_type] || market.market_type}</span>
        <span>
          <span className={`pill pill--${market.status}`} style={{ marginRight: 8 }}>
            {market.status}
          </span>
          {canToggle && (
            <button className="btn btn-sm" onClick={toggleSuspend} disabled={busy}>
              {market.status === "open" ? "Suspend" : "Reopen"}
            </button>
          )}
        </span>
      </div>
      <table>
        <thead>
          <tr>
            <th>Outcome</th>
            <th>Odds</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {market.outcomes.map((o) => (
            <OutcomeRow key={o.id} outcome={o} onOddsSaved={onRefresh} />
          ))}
        </tbody>
      </table>
    </div>
  );
}
