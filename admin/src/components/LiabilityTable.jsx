const MARKET_TITLES = {
  moneyline: "Moneyline",
  method_of_victory: "Method of Victory",
  round_prop: "Round Props",
};

export default function LiabilityTable({ liability }) {
  if (!liability) return <p className="empty-note">Loading liability…</p>;

  const totalExposure = liability
    .flatMap((m) => m.outcomes)
    .reduce((sum, o) => Math.max(sum, parseFloat(o.total_potential_payout)), 0);

  return (
    <div>
      {liability.map((market) => (
        <div key={market.market_id} className="market-block">
          <div className="market-block__title" style={{ marginBottom: 8 }}>
            {MARKET_TITLES[market.market_type] || market.market_type}
          </div>
          <table>
            <thead>
              <tr>
                <th>Outcome</th>
                <th># Bets</th>
                <th>Total Stake</th>
                <th>If Wins, House Pays</th>
              </tr>
            </thead>
            <tbody>
              {market.outcomes.map((o) => (
                <tr key={o.outcome_id}>
                  <td>{o.label}</td>
                  <td className="mono">{o.pending_bet_count}</td>
                  <td className="mono">{o.total_stake}</td>
                  <td className="mono">{o.total_potential_payout}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
      <p className="empty-note">
        Worst-case single-outcome exposure across all markets: <strong className="mono">{totalExposure.toFixed(2)}</strong> ETB
        <br />
        "If wins, house pays" reflects the odds each bet actually locked in at placement time —
        it won't match today's posted odds if they've moved since. That's intentional: this table
        is about real exposure from bets that already exist, not current pricing (see Markets above for that).
      </p>
    </div>
  );
}
