import { useEffect, useState } from "react";
import { adminApi } from "../adminApi";

export default function DepositAccounts() {
  const [accounts, setAccounts] = useState(null);
  const [status, setStatus] = useState(null);
  const [form, setForm] = useState({ phone: "", recipient_name: "" });
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  function refresh() {
    adminApi.listDepositAccounts().then(setAccounts).catch((e) => setError(e.message));
    adminApi.status().then(setStatus).catch(() => {});
  }

  useEffect(refresh, []);

  async function handleAdd(e) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await adminApi.addDepositAccount(form);
      setForm({ phone: "", recipient_name: "" });
      refresh();
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleActivate(id) {
    await adminApi.activateDepositAccount(id);
    refresh();
  }

  async function handleRemove(id) {
    if (!confirm("Remove this deposit account? If it's the active one, the next account in the list takes over.")) return;
    await adminApi.removeDepositAccount(id);
    refresh();
  }

  return (
    <div>
      <h1 className="page-title">Deposit Accounts</h1>
      <p style={{ color: "var(--color-text-muted)", marginTop: -12, marginBottom: 20, fontSize: 14 }}>
        Telebirr numbers users send deposits to. Exactly one is active at a time — that's the number shown
        in the Mini App's wallet screen. Deposits rotate to the next account automatically after{" "}
        {status ? "the configured threshold" : "…"} successful deposits on the active one.
      </p>

      {!status?.wagering_enabled && (
        <div className="empty-state" style={{ marginBottom: 20 }}>
          Wagering is currently in demo mode — real deposits are disabled regardless of the accounts
          configured here. Set <code>ETFC_WAGERING_ENABLED=true</code> to go live.
        </div>
      )}

      <form className="form-card" onSubmit={handleAdd}>
        <h2 className="form-card__title">Add Deposit Account</h2>
        <div className="form-row">
          <div className="form-field">
            <label>Telebirr phone number</label>
            <input
              required
              placeholder="2519XXXXXXXX"
              value={form.phone}
              onChange={(e) => setForm({ ...form, phone: e.target.value })}
            />
          </div>
          <div className="form-field">
            <label>Recipient name (as it appears on Telebirr)</label>
            <input
              required
              placeholder="Full name"
              value={form.recipient_name}
              onChange={(e) => setForm({ ...form, recipient_name: e.target.value })}
            />
          </div>
        </div>
        <button className="btn btn-gold" disabled={submitting}>
          {submitting ? "Adding…" : "Add Account"}
        </button>
        {error && <p className="error-text">{error}</p>}
      </form>

      {accounts === null && <p className="empty-note">Loading…</p>}
      {accounts?.length === 0 && <p className="empty-note">No deposit accounts yet — add one above.</p>}
      {accounts?.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>Phone</th>
              <th>Recipient</th>
              <th>Deposits since rotation</th>
              <th>Status</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {accounts.map((a) => (
              <tr key={a.id}>
                <td className="mono">{a.phone}</td>
                <td>{a.recipient_name}</td>
                <td className="mono">{a.deposit_count}</td>
                <td>
                  <span className={`pill ${a.is_active ? "pill--open" : "pill--completed"}`}>
                    {a.is_active ? "Active" : "Idle"}
                  </span>
                </td>
                <td>
                  {!a.is_active && (
                    <button className="btn btn-sm" onClick={() => handleActivate(a.id)}>
                      Activate
                    </button>
                  )}{" "}
                  <button className="btn btn-sm btn-danger" onClick={() => handleRemove(a.id)}>
                    Remove
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
