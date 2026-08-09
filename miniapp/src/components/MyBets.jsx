const STATUS_LABEL = {
  pending: "Pending",
  won: "Won",
  lost: "Lost",
  void: "Void",
};

function ParlayRow({ parlay }) {
  return (
    <div className="bet-row bet-row--parlay">
      <div className="bet-row__details" style={{ flex: 1 }}>
        <span className="bet-row__stake">
          {parlay.stake} @ {parseFloat(parlay.combined_odds).toFixed(2)} · {parlay.legs.length}-Leg Parlay
        </span>
        <span className="bet-row__meta">Potential: {parlay.potential_payout}</span>
        <div className="parlay-legs-list">
          {parlay.legs.map((leg) => (
            <div className="parlay-legs-list__item" key={leg.id}>
              <span>{leg.odds_at_placement}</span>
              <span className={`status-badge status-badge--${leg.status} status-badge--sm`}>
                {STATUS_LABEL[leg.status] || leg.status}
              </span>
            </div>
          ))}
        </div>
      </div>
      <span className={`status-badge status-badge--${parlay.status}`}>
        {STATUS_LABEL[parlay.status] || parlay.status}
      </span>
    </div>
  );
}

export default function MyBets({ bets, parlays }) {
  if (bets === null || parlays === null) return <div className="spinner" />;

  if (bets.length === 0 && parlays.length === 0) {
    return (
      <div className="empty-state">
        <div className="empty-state__title">No bets yet</div>
        Once you back a fighter, it'll show up here.
      </div>
    );
  }

  return (
    <div>
      {parlays.length > 0 && (
        <>
          <div className="section-title" style={{ marginTop: 0 }}>Parlays</div>
          {parlays.map((parlay) => (
            <ParlayRow key={parlay.id} parlay={parlay} />
          ))}
        </>
      )}

      {bets.length > 0 && (
        <>
          <div className="section-title" style={{ marginTop: parlays.length > 0 ? undefined : 0 }}>
            Single Bets
          </div>
          {bets.map((bet) => (
            <div className="bet-row" key={bet.id}>
              <div className="bet-row__details">
                <span className="bet-row__stake">{bet.stake} @ {bet.odds_at_placement}</span>
                <span className="bet-row__meta">Potential: {bet.potential_payout}</span>
              </div>
              <span className={`status-badge status-badge--${bet.status}`}>
                {STATUS_LABEL[bet.status] || bet.status}
              </span>
            </div>
          ))}
        </>
      )}
    </div>
  );
}
