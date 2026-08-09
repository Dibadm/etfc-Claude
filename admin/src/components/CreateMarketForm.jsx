import { useState } from "react";
import { adminApi } from "../adminApi";

export default function CreateMarketForm({ marketType, fightId, fighterAName, fighterBName, onCreated }) {
  const [values, setValues] = useState({});
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      if (marketType === "moneyline") {
        await adminApi.createMoneyline({
          fight_id: fightId,
          odds_fighter_a: values.odds_fighter_a,
          odds_fighter_b: values.odds_fighter_b,
        });
      } else if (marketType === "method_of_victory") {
        await adminApi.createMethodOfVictory({
          fight_id: fightId,
          odds_ko_tko: values.odds_ko_tko,
          odds_submission: values.odds_submission,
          odds_decision: values.odds_decision,
        });
      } else if (marketType === "round_prop") {
        const totalRounds = parseInt(values.total_rounds || "3", 10);
        const oddsByRound = {};
        for (let i = 1; i <= totalRounds; i++) {
          oddsByRound[i] = values[`round_${i}`];
        }
        await adminApi.createRoundProp({
          fight_id: fightId,
          total_rounds: totalRounds,
          odds_by_round: oddsByRound,
          odds_goes_the_distance: values.odds_goes_the_distance,
        });
      }
      onCreated();
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  const set = (key) => (e) => setValues({ ...values, [key]: e.target.value });

  if (marketType === "moneyline") {
    return (
      <form className="form-card" onSubmit={handleSubmit}>
        <h2 className="form-card__title">Add Moneyline Market</h2>
        <div className="form-row">
          <div className="form-field">
            <label>{fighterAName} odds</label>
            <input required placeholder="1.80" onChange={set("odds_fighter_a")} />
          </div>
          <div className="form-field">
            <label>{fighterBName} odds</label>
            <input required placeholder="2.00" onChange={set("odds_fighter_b")} />
          </div>
        </div>
        <button className="btn btn-gold" disabled={submitting}>Add Market</button>
        {error && <p className="error-text">{error}</p>}
      </form>
    );
  }

  if (marketType === "method_of_victory") {
    return (
      <form className="form-card" onSubmit={handleSubmit}>
        <h2 className="form-card__title">Add Method of Victory Market</h2>
        <div className="form-row">
          <div className="form-field">
            <label>KO/TKO odds</label>
            <input required placeholder="2.10" onChange={set("odds_ko_tko")} />
          </div>
          <div className="form-field">
            <label>Submission odds</label>
            <input required placeholder="3.50" onChange={set("odds_submission")} />
          </div>
          <div className="form-field">
            <label>Decision odds</label>
            <input required placeholder="2.40" onChange={set("odds_decision")} />
          </div>
        </div>
        <button className="btn btn-gold" disabled={submitting}>Add Market</button>
        {error && <p className="error-text">{error}</p>}
      </form>
    );
  }

  // round_prop
  const totalRounds = parseInt(values.total_rounds || "3", 10);
  return (
    <form className="form-card" onSubmit={handleSubmit}>
      <h2 className="form-card__title">Add Round Props Market</h2>
      <div className="form-row">
        <div className="form-field">
          <label>Scheduled rounds</label>
          <select value={values.total_rounds || "3"} onChange={set("total_rounds")}>
            <option value="3">3 (non-title)</option>
            <option value="5">5 (title fight)</option>
          </select>
        </div>
      </div>
      <div className="form-row">
        {Array.from({ length: totalRounds }, (_, i) => i + 1).map((round) => (
          <div className="form-field" key={round}>
            <label>Round {round} odds</label>
            <input required placeholder="4.50" onChange={set(`round_${round}`)} />
          </div>
        ))}
      </div>
      <div className="form-row">
        <div className="form-field">
          <label>Goes the distance odds</label>
          <input required placeholder="2.20" onChange={set("odds_goes_the_distance")} />
        </div>
      </div>
      <button className="btn btn-gold" disabled={submitting}>Add Market</button>
      {error && <p className="error-text">{error}</p>}
    </form>
  );
}
