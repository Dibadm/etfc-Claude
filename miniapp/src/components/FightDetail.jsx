import { useEffect, useState } from "react";
import { ArrowLeft } from "lucide-react";
import { api } from "../api";
import FighterAvatar from "./FighterAvatar";

const MARKET_TITLES = {
  moneyline: "Moneyline — Who Wins",
  method_of_victory: "Method of Victory",
  round_prop: "Round Props",
};

export default function FightDetail({ fight, onBack, onSelectOutcome, selectedOutcomeIds }) {
  const [markets, setMarkets] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    api
      .fightMarkets(fight.id)
      .then((data) => !cancelled && setMarkets(data))
      .catch((e) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
    };
  }, [fight.id]);

  return (
    <div>
      <button
        onClick={onBack}
        style={{
          background: "none",
          border: "none",
          color: "var(--color-text-muted)",
          display: "flex",
          alignItems: "center",
          gap: 4,
          padding: 0,
          marginBottom: "var(--space-4)",
          fontSize: 14,
        }}
      >
        <ArrowLeft size={16} /> Back to fights
      </button>

      {fight.is_main_event && (
        <div className="main-event-ribbon" style={{ position: "static", display: "inline-block", marginBottom: "var(--space-3)" }}>
          ★ Main Event
        </div>
      )}
      <div className="fight-card__matchup" style={{ marginBottom: "var(--space-2)" }}>
        <div className="corner corner--red">
          <FighterAvatar fighter={fight.fighter_a} corner="red" size={64} />
          <span className="corner__tag">Red</span>
          <div className="corner__name">{fight.fighter_a.name}</div>
        </div>
        <div className="fight-card__vs">VS</div>
        <div className="corner corner--blue">
          <FighterAvatar fighter={fight.fighter_b} corner="blue" size={64} />
          <span className="corner__tag">Blue</span>
          <div className="corner__name">{fight.fighter_b.name}</div>
        </div>
      </div>
      <div className="fight-card__meta" style={{ marginBottom: 0 }}>
        <span>{fight.event_name}</span>
        {fight.weight_class && <span>{fight.weight_class}</span>}
      </div>

      {error && <p className="error-text">{error}</p>}
      {markets === null && !error && <div className="spinner" />}

      {markets?.length === 0 && (
        <div className="empty-state">
          <div className="empty-state__title">Odds not posted yet</div>
          Markets for this fight haven't opened. Check back closer to fight night.
        </div>
      )}

      {markets?.map((market) => (
        <div key={market.id}>
          <div className="section-title">{MARKET_TITLES[market.market_type] || market.market_type}</div>
          <div className="market-card">
            {market.outcomes.map((outcome) => {
              const selected = selectedOutcomeIds?.has(outcome.id);
              return (
                <div className="outcome-row" key={outcome.id}>
                  <span className="outcome-row__label">{outcome.label}</span>
                  <button
                    className={`outcome-row__odds-btn ${selected ? "outcome-row__odds-btn--selected" : ""}`}
                    disabled={market.status !== "open"}
                    onClick={() => onSelectOutcome(outcome, market)}
                  >
                    {outcome.odds}
                  </button>
                </div>
              );
            })}
          </div>
          {market.status !== "open" && (
            <p style={{ color: "var(--color-text-muted)", fontSize: 12, marginTop: -8 }}>
              {market.status === "suspended" ? "Betting suspended on this market" : "This market has settled"}
            </p>
          )}
        </div>
      ))}
    </div>
  );
}
