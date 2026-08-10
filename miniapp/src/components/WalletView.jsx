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
  const [underReview, setUnderReview] = useState(false);
  const [copied, setCopied] = useState(false);

  function loadAccount() {
    setAccountError(null);
    api.depositAccount().then(setAccount).catch((e) => setAccountError(e.message));
  }

  useEffect(loadAccount, []);

  async function handleCopyPhone() {
    if (!account?.phone) return;
    try {
      await navigator.clipboard.writeText(account.phone);
      setCopied(true);
      hapticSuccess();
      setTimeout(() => setCopied(false), 1500);
    } catch {
      setError("Couldn't copy — please copy the number manually");
    }
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    setSuccessAmount(null);
    setUnderReview(false);
    try {
      const idempotencyKey = crypto.randomUUID();
      const before = await api.me();
      const after = await api.submitDeposit(smsText, undefined, idempotencyKey);
      if (after.status === "under_review") {
        setUnderReview(true);
        hapticError();
      } else {
        const credited = (parseFloat(after.wallet.balance) - parseFloat(before.wallet.balance)).toFixed(2);
        setSuccessAmount(credited);
        setSmsText("");
        hapticSuccess();
        onDeposited();
      }
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
          onClick={handleCopyPhone}
          style={{
            background: "var(--color-surface-raised)",
            border: "1px solid var(--color-border)",
            borderRadius: "var(--radius-md)",
            padding: "var(--space-3)",
            marginBottom: "var(--space-3)",
            cursor: "pointer",
            userSelect: "none",
          }}
        >
          <div style={{ fontSize: 12, color: "var(--color-text-muted)", marginBottom: 4 }}>
            Send any amount via Telebirr to
          </div>
          <div className="mono" style={{ fontSize: 18, fontWeight: 600 }}>
            {account.phone}
            <span style={{ marginLeft: 8, fontSize: 12, color: copied ? "var(--color-success)" : "var(--color-text-muted)" }}>
              {copied ? "Copied" : "Tap to copy"}
            </span>
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
      {underReview && (
        <p className="success-text" style={{ color: "var(--color-warning)", marginTop: "var(--space-2)" }}>
          Your deposit is under review. We'll credit it within a few hours.
        </p>
      )}
      {error && <p className="error-text">{error}</p>}
    </div>
  );
}

function WithdrawFlow({ onWithdrawn }) {
  const [amount, setAmount] = useState("");
  const [telebirr, setTelebirr] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    setSuccess(false);
    try {
      await api.requestWithdrawal(amount, telebirr);
      hapticSuccess();
      setSuccess(true);
      setAmount("");
      setTelebirr("");
      onWithdrawn();
    } catch (e) {
      hapticError();
      setError(e instanceof ApiError ? e.message : "Something went wrong — try again");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="form-card" style={{ margin: 0 }}>
      <div className="form-card__title">Withdraw via Telebirr</div>
      <p style={{ fontSize: 13, color: "var(--color-text-muted)", marginTop: -8, marginBottom: 12 }}>
        Funds are sent to the Telebirr number you provide. Processing takes up to 24 hours.
      </p>
      <form onSubmit={handleSubmit}>
        <input
          required
          type="number"
          inputMode="decimal"
          placeholder="Amount"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          style={{
            width: "100%",
            background: "var(--color-surface-raised)",
            border: "1px solid var(--color-border)",
            borderRadius: "var(--radius-md)",
            padding: "var(--space-3)",
            color: "var(--color-text)",
            fontSize: 14,
            marginBottom: "var(--space-3)",
          }}
        />
        <input
          required
          placeholder="Telebirr phone number (2519XXXXXXXX)"
          value={telebirr}
          onChange={(e) => setTelebirr(e.target.value)}
          style={{
            width: "100%",
            background: "var(--color-surface-raised)",
            border: "1px solid var(--color-border)",
            borderRadius: "var(--radius-md)",
            padding: "var(--space-3)",
            color: "var(--color-text)",
            fontSize: 14,
            marginBottom: "var(--space-3)",
          }}
        />
        <button className="btn-primary" disabled={submitting || !amount || !telebirr}>
          {submitting ? "Submitting…" : "Request Withdrawal"}
        </button>
      </form>
      {success && (
        <p className="success-text" style={{ color: "var(--color-success)", marginTop: "var(--space-2)" }}>
          Withdrawal requested. It will be processed shortly.
        </p>
      )}
      {error && <p className="error-text">{error}</p>}
    </div>
  );
}

export default function WalletView({ me, status, onRefreshMe }) {
  const [showWithdraw, setShowWithdraw] = useState(false);
  const [showDeposit, setShowDeposit] = useState(false);
  const [history, setHistory] = useState(null);

  useEffect(() => {
    if (status?.wagering_enabled) {
      api.myWithdrawals().then(setHistory).catch(() => {});
    }
  }, [status?.wagering_enabled]);

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

      <div style={{ marginBottom: "var(--space-4)" }}>
        {!showDeposit ? (
          <button className="btn-primary" style={{ width: "100%", marginBottom: "var(--space-3)" }} onClick={() => setShowDeposit(true)}>
            Deposit
          </button>
        ) : (
          <DepositFlow onDeposited={onRefreshMe} />
        )}
        {status?.wagering_enabled ? (
          !showWithdraw ? (
            <button className="btn-primary" style={{ width: "100%" }} onClick={() => setShowWithdraw(true)}>
              Withdraw
            </button>
          ) : (
            <WithdrawFlow onWithdrawn={onRefreshMe} />
          )
        ) : (
          <div className="empty-state" style={{ padding: "var(--space-4)", marginBottom: "var(--space-4)" }}>
            <div className="empty-state__title">Demo balance</div>
            Real-money deposits and withdrawals open once ETFC/Lottery Service licensing is approved.
            This play-money balance works exactly like the real thing so you can try everything now.
          </div>
        )}
      </div>

      {history && history.length > 0 && (
        <div style={{ marginBottom: "var(--space-4)" }}>
          <div className="section-title">Recent Withdrawals</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {history.map((w) => (
              <div key={w.id} style={{ display: "flex", justifyContent: "space-between", padding: "var(--space-2) var(--space-3)", background: "var(--color-surface-raised)", borderRadius: "var(--radius-md)" }}>
                <span className="mono">{w.amount} ETB</span>
                <span className={`pill pill--${w.status === "pending" ? "scheduled" : w.status}`}>{w.status}</span>
              </div>
            ))}
          </div>
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
