import FighterAvatar from "./FighterAvatar";

function formatDate(iso) {
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" }) +
    " · " + d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

function FightCard({ fight, onSelect }) {
  const isMain = fight.is_main_event;
  const avatarSize = isMain ? 64 : 44;

  return (
    <button
      key={fight.id}
      className={`fight-card ${isMain ? "fight-card--main-event" : ""}`}
      onClick={() => onSelect(fight)}
    >
      {isMain && <div className="main-event-ribbon">★ Main Event</div>}
      <div className="fight-card__meta">
        <span>{fight.event_name}</span>
        <span>{formatDate(fight.scheduled_at)}</span>
      </div>
      <div className="fight-card__matchup">
        <div className="corner corner--red">
          <FighterAvatar fighter={fight.fighter_a} corner="red" size={avatarSize} />
          <span className="corner__tag">Red</span>
          <div className="corner__name">{fight.fighter_a.name}</div>
        </div>
        <div className="fight-card__vs">VS</div>
        <div className="corner corner--blue">
          <FighterAvatar fighter={fight.fighter_b} corner="blue" size={avatarSize} />
          <span className="corner__tag">Blue</span>
          <div className="corner__name">{fight.fighter_b.name}</div>
        </div>
      </div>
      {fight.moneyline_odds_a && fight.moneyline_odds_b && (
        <div className="fight-card__odds-row">
          <div className="odds-pill odds-pill--red">{fight.moneyline_odds_a}</div>
          <div className="odds-pill odds-pill--blue">{fight.moneyline_odds_b}</div>
        </div>
      )}
    </button>
  );
}

export default function FightList({ fights, onSelect }) {
  if (fights === null) {
    return <div className="spinner" />;
  }

  if (fights.length === 0) {
    return (
      <div className="empty-state">
        <div className="empty-state__title">No fights scheduled</div>
        Check back soon — new cards get posted as they're announced.
      </div>
    );
  }

  return (
    <div>
      {fights.map((fight) => (
        <FightCard key={fight.id} fight={fight} onSelect={onSelect} />
      ))}
    </div>
  );
}
