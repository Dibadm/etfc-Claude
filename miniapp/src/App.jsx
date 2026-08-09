import { useEffect, useState, useCallback } from "react";
import { Swords, Wallet as WalletIcon, ListChecks } from "lucide-react";
import { api } from "./api";
import FightList from "./components/FightList";
import FightDetail from "./components/FightDetail";
import BetSlip from "./components/BetSlip";
import SlipBar from "./components/SlipBar";
import WalletView from "./components/WalletView";
import MyBets from "./components/MyBets";
import Logo from "./components/Logo";

const TABS = [
  { id: "fights", label: "Fights", icon: Swords },
  { id: "wallet", label: "Wallet", icon: WalletIcon },
  { id: "bets", label: "My Bets", icon: ListChecks },
];

export default function App() {
  const [activeTab, setActiveTab] = useState("fights");
  const [selectedFight, setSelectedFight] = useState(null);

  // The bet slip is a "cart": legs accumulate here as the user taps
  // outcomes, possibly across different fights, until they review and
  // submit. One selection = a single bet; two or more = a parlay — see
  // BetSlip.jsx for which API call that becomes.
  const [slipLegs, setSlipLegs] = useState([]); // [{ outcome, market, fightId, fightLabel }]
  const [slipOpen, setSlipOpen] = useState(false);

  const [status, setStatus] = useState(null);
  const [me, setMe] = useState(null);
  const [fights, setFights] = useState(null);
  const [myBets, setMyBets] = useState(null);
  const [myParlays, setMyParlays] = useState(null);
  const [toast, setToast] = useState(null);
  const [loadError, setLoadError] = useState(null);

  const refreshMe = useCallback(() => {
    api.me().then(setMe).catch((e) => setLoadError(e.message));
  }, []);

  const refreshBets = useCallback(() => {
    api.myBets().then(setMyBets).catch((e) => setLoadError(e.message));
    api.myParlays().then(setMyParlays).catch((e) => setLoadError(e.message));
  }, []);

  useEffect(() => {
    api.status().then(setStatus).catch(() => {});
    api.listFights("scheduled").then(setFights).catch((e) => setLoadError(e.message));
    refreshMe();
  }, [refreshMe]);

  useEffect(() => {
    if (activeTab === "bets") refreshBets();
  }, [activeTab, refreshBets]);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 2500);
    return () => clearTimeout(t);
  }, [toast]);

  function toggleSlipLeg(outcome, market, fight) {
    setSlipLegs((prev) => {
      const alreadyThisOutcome = prev.some((leg) => leg.outcome.id === outcome.id);
      if (alreadyThisOutcome) {
        return prev.filter((leg) => leg.outcome.id !== outcome.id);
      }
      // Only one selection per fight is allowed (see parlay_service.py's
      // correlated-legs rule) — picking a new outcome from a fight that
      // already has a selection swaps it rather than erroring later.
      const withoutSameFight = prev.filter((leg) => leg.fightId !== fight.id);
      return [
        ...withoutSameFight,
        { outcome, market, fightId: fight.id, fightLabel: `${fight.fighter_a.name} vs ${fight.fighter_b.name}` },
      ];
    });
  }

  function removeSlipLeg(outcomeId) {
    setSlipLegs((prev) => prev.filter((leg) => leg.outcome.id !== outcomeId));
  }

  async function handleConfirmSlip(stake) {
    if (slipLegs.length === 1) {
      const bet = await api.placeBet(slipLegs[0].outcome.id, stake);
      setToast(`Bet placed — ${bet.stake} on ${slipLegs[0].outcome.label}`);
    } else {
      const parlay = await api.placeParlay(slipLegs.map((l) => l.outcome.id), stake);
      setToast(`${slipLegs.length}-leg parlay placed — ${parlay.stake} to win ${parlay.potential_payout}`);
    }
    setSlipLegs([]);
    setSlipOpen(false);
    refreshMe();
    if (activeTab === "bets") refreshBets();
  }

  const selectedOutcomeIds = new Set(slipLegs.map((l) => l.outcome.id));

  return (
    <div className="app-shell">
      <header className="app-header">
        <div style={{ display: "flex", alignItems: "center", gap: "var(--space-3)" }}>
          <Logo />
          <div>
            <h1 className="app-header__title" style={{ marginBottom: 0 }}>ETFC Betting</h1>
            {status && (
              <span className={`mode-banner mode-banner--${status.wagering_enabled ? "live" : "demo"}`}>
                {status.wagering_enabled ? "● LIVE" : "● DEMO"}
              </span>
            )}
          </div>
        </div>
      </header>

      <main className="app-content">
        {loadError && <p className="error-text">{loadError}</p>}

        {activeTab === "fights" && !selectedFight && (
          <FightList fights={fights} onSelect={setSelectedFight} />
        )}
        {activeTab === "fights" && selectedFight && (
          <FightDetail
            fight={selectedFight}
            onBack={() => setSelectedFight(null)}
            onSelectOutcome={(outcome, market) => toggleSlipLeg(outcome, market, selectedFight)}
            selectedOutcomeIds={selectedOutcomeIds}
          />
        )}
        {activeTab === "wallet" && <WalletView me={me} status={status} onRefreshMe={refreshMe} />}
        {activeTab === "bets" && <MyBets bets={myBets} parlays={myParlays} />}
      </main>

      {slipLegs.length > 0 && !slipOpen && (
        <SlipBar count={slipLegs.length} onOpen={() => setSlipOpen(true)} />
      )}

      <nav className="tab-bar">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            className={`tab-bar__item ${activeTab === id ? "tab-bar__item--active" : ""}`}
            onClick={() => setActiveTab(id)}
          >
            <Icon size={20} />
            {label}
          </button>
        ))}
      </nav>

      {slipOpen && (
        <BetSlip
          legs={slipLegs}
          wallet={me?.wallet}
          onClose={() => setSlipOpen(false)}
          onRemoveLeg={removeSlipLeg}
          onConfirm={handleConfirmSlip}
        />
      )}

      {toast && <div className="toast">{toast}</div>}
    </div>
  );
}
