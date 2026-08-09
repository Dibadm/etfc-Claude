import { useState } from "react";
import { LogOut } from "lucide-react";
import Login from "./components/Login";
import FightsList from "./components/FightsList";
import FightAdmin from "./components/FightAdmin";
import FightersList from "./components/FightersList";
import DepositAccounts from "./components/DepositAccounts";
import { getToken, clearToken } from "./adminApi";

export default function App() {
  const [authed, setAuthed] = useState(() => Boolean(getToken()));
  const [page, setPage] = useState("fights"); // "fights" | "fighters" | "deposits"
  const [selectedFight, setSelectedFight] = useState(null);

  if (!authed) {
    return <Login onSuccess={() => setAuthed(true)} />;
  }

  function handleLogout() {
    clearToken();
    setAuthed(false);
    setSelectedFight(null);
  }

  function goToFights() {
    setPage("fights");
    setSelectedFight(null);
  }

  return (
    <div className="admin-shell">
      <aside className="admin-sidebar">
        <div className="admin-sidebar__title">ETFC Admin</div>
        <button className={`nav-item ${page === "fights" ? "nav-item--active" : ""}`} onClick={goToFights}>
          Fights
        </button>
        <button
          className={`nav-item ${page === "fighters" ? "nav-item--active" : ""}`}
          onClick={() => setPage("fighters")}
        >
          Fighters
        </button>
        <button
          className={`nav-item ${page === "deposits" ? "nav-item--active" : ""}`}
          onClick={() => setPage("deposits")}
        >
          Deposit Accounts
        </button>
        <button className="nav-item" onClick={handleLogout} style={{ marginTop: 24, display: "flex", alignItems: "center", gap: 6 }}>
          <LogOut size={14} /> Log out
        </button>
      </aside>
      <main className="admin-main">
        {page === "fighters" && <FightersList />}
        {page === "deposits" && <DepositAccounts />}
        {page === "fights" && selectedFight && (
          <FightAdmin fight={selectedFight} onBack={() => setSelectedFight(null)} />
        )}
        {page === "fights" && !selectedFight && <FightsList onSelectFight={setSelectedFight} />}
      </main>
    </div>
  );
}
