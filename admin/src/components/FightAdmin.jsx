import { useEffect, useState } from "react";
import { ArrowLeft } from "lucide-react";
import { adminApi } from "../adminApi";
import MarketBlock from "./MarketBlock";
import CreateMarketForm from "./CreateMarketForm";
import SettleForm from "./SettleForm";
import LiabilityTable from "./LiabilityTable";

const ALL_MARKET_TYPES = ["moneyline", "method_of_victory", "round_prop"];

export default function FightAdmin({ fight, onBack }) {
  const [markets, setMarkets] = useState(null);
  const [liability, setLiability] = useState(null);
  const [voidError, setVoidError] = useState(null);
  const [voiding, setVoiding] = useState(false);
  const [isMainEvent, setIsMainEvent] = useState(fight.is_main_event);
  const [togglingMainEvent, setTogglingMainEvent] = useState(false);

  function refresh() {
    adminApi.fightMarkets(fight.id).then(setMarkets);
    adminApi.liability(fight.id).then(setLiability);
  }

  useEffect(refresh, [fight.id]);

  async function toggleMainEvent() {
    setTogglingMainEvent(true);
    try {
      const updated = await adminApi.setMainEvent(fight.id, !isMainEvent);
      setIsMainEvent(updated.is_main_event);
    } finally {
      setTogglingMainEvent(false);
    }
  }

  async function handleVoid() {
    if (!confirm("Void this fight? All pending bets on it will be refunded. This cannot be undone.")) return;
    setVoiding(true);
    setVoidError(null);
    try {
      await adminApi.voidFight(fight.id);
      refresh();
    } catch (e) {
      setVoidError(e.message);
    } finally {
      setVoiding(false);
    }
  }

  const existingTypes = new Set((markets || []).map((m) => m.market_type));
  const missingTypes = ALL_MARKET_TYPES.filter((t) => !existingTypes.has(t));
  const isSettleable = fight.status === "scheduled";

  return (
    <div>
      <button className="back-link" onClick={onBack}>
        <ArrowLeft size={14} /> Back to fights
      </button>

      <h1 className="page-title" style={{ marginBottom: 4 }}>
        <span className="tag-red">{fight.fighter_a.name}</span> vs <span className="tag-blue">{fight.fighter_b.name}</span>
      </h1>
      <p style={{ color: "var(--color-text-muted)", marginTop: 0, marginBottom: 12 }}>
        {fight.event_name} {fight.weight_class && `· ${fight.weight_class}`} ·{" "}
        <span className={`pill pill--${fight.status}`}>{fight.status}</span>
        {isMainEvent && <span style={{ color: "var(--color-gold-bright)", marginLeft: 8 }}>★ Main Event</span>}
      </p>
      <button className="btn btn-sm" onClick={toggleMainEvent} disabled={togglingMainEvent} style={{ marginBottom: 24 }}>
        {togglingMainEvent ? "Updating…" : isMainEvent ? "★ Unmark as main event" : "☆ Mark as main event"}
      </button>

      <h2 className="form-card__title" style={{ marginTop: 0 }}>Markets</h2>
      {markets === null && <p className="empty-note">Loading…</p>}
      {markets?.map((m) => (
        <MarketBlock key={m.id} market={m} onRefresh={refresh} />
      ))}
      {missingTypes.map((type) => (
        <CreateMarketForm
          key={type}
          marketType={type}
          fightId={fight.id}
          fighterAName={fight.fighter_a.name}
          fighterBName={fight.fighter_b.name}
          onCreated={refresh}
        />
      ))}

      <h2 className="form-card__title">Liability</h2>
      <div className="form-card">
        <LiabilityTable liability={liability} />
      </div>

      {isSettleable && (
        <>
          <SettleForm fight={fight} onSettled={onBack} />
          <button className="btn btn-danger" onClick={handleVoid} disabled={voiding}>
            {voiding ? "Voiding…" : "Void Fight (refund everyone)"}
          </button>
          {voidError && <p className="error-text">{voidError}</p>}
        </>
      )}
      {!isSettleable && (
        <p className="empty-note">
          This fight is {fight.status} — settlement/void actions only apply while a fight is scheduled.
        </p>
      )}
    </div>
  );
}
