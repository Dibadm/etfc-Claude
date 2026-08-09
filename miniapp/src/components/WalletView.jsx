import { useEffect, useState } from "react";
import { api, ApiError } from "../api";
import { hapticError, hapticSuccess } from "../telegram";

function DepositFlow({ onDeposited }) {
  const [account, setAccount] = useState(null);
  const [accountError, setAccountError] = useState(null);
  const [smsText, setSmsText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [successAmount, setSuccessAmount] = useState(null);

  function loadAccount() {
    setAccountError(null);
    api.depositAccount().then(setAccount).catch((e) => setAccountError(e.message));
  }

  useEffect(loadAccount, []);

  async function handleSubmit(e) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    setSuccessAmount(null);
    try {
      const before = await api.me();
      const after = await api.submitDeposit(smsText);
      const credited = (parseFloat(after.wallet.balance) - parseFloat(before.wallet.balance)).toFixed(2);
      setSuccessAmount(credited);
      setSmsText("");
      hapticSuccess();
      onDeposited();
    } catch (e) {
      hapticError();
      setError(e instanceof ApiError ? e.message : "Something went wrong — try again");
    } finally {
      setSubmitting(false);
    }
  }

  if (accountError) {
    return (
      <div className="empty-state" style={{ padding: "var(--space-4)" }}>
        <div className="empty-state__title">Deposits temporarily unavailable</div>
        {accountError}
      </div>
    );
  }

  return (
    <div className="form-card" style={{ margin: 0 }}>
      <div className="form-card__title">Deposit via Telebirr</div>

      {account ? (
        <div
          style={{
            background: "var(--color-surface-raised)",
            border: "1px solid var(--color-border)",
            borderRadius: "var(--radius-md)",
            padding: "var(--space-3)",
            marginBottom: "var(--space-3)",
          }}
        >
          <div style={{ fontSize: 12, color: "var(--color-text-muted)", marginBottom: 4 }}>
            Send any amount via Telebirr to
          </div>
          <div className="mono" style={{ fontSize: 18, fontWeight: 600 }}>
            {account.phone}
          </div>
          <div style={{ fontSize: 13, color: "var(--color-text-muted)" }}>{account.recipient_name}</div>
        </div>
      ) : (
        <div className="spinner" />
      )}

      <form onSubmit={handleSubmit}>
        <textarea
          required
          placeholder="Paste the full Telebirr confirmation SMS you received here…"
          value={smsText}
          onChange={(e) => setSmsText(e.target.value)}
          rows={5}
          style={{
            width: "100%",
            background: "var(--color-surface-raised)",
            border: "1px solid var(--color-border)",
            borderRadius: "var(--radius-md)",
            padding: "var(--space-3)",
            color: "var(--color-text)",
            fontSize: 14,
            marginBottom: "var(--space-3)",
            resize: "vertical",
          }}
        />
        <button className="btn-primary" disabled={submitting || !smsText.trim() || !account}>
          {submitting ? "Verifying…" : "Submit Deposit"}
        </button>
      </form>

      {successAmount && (
        <p className="success-text" style={{ color: "var(--color-success)", marginTop: "var(--space-2)" }}>
          {successAmount} credited to your balance.
        </p>
      )}
      {error && <p className="error-text">{error}</p>}
    </div>
  );
}

export default function WalletView({ me, status, onRefreshMe }) {
  if (!me) return <div className="spinner" />;

  return (
    <div>
      <div className="balance-card">
        <div className="balance-card__label">Your Balance</div>
        <div className="balance-card__amount">
          {me.wallet.balance}
          <span className="balance-card__currency">{me.wallet.currency}</span>
        </div>
      </div>

      {status?.wagering_enabled ? (
        <DepositFlow onDeposited={onRefreshMe} />
      ) : (
        <div className="empty-state" style={{ padding: "var(--space-4)" }}>
          <div className="empty-state__title">Demo balance</div>
          Real-money deposits open once ETFC/Lottery Service licensing is approved.
          This play-money balance works exactly like the real thing so you can try
          everything now.
        </div>
      )}

      {status?.license_number && (
        <p style={{ textAlign: "center", fontSize: 11, color: "var(--color-text-faint)", marginTop: "var(--space-5)" }}>
          Licensed by the National Lottery Association — {status.license_number}
        </p>
      )}
    </div>
  );
}
