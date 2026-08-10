import { useEffect, useState } from "react";
import { adminApi } from "../adminApi";

export default function Withdrawals() {
  const [withdrawals, setWithdrawals] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filter, setFilter] = useState("pending");

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const data = await adminApi.listWithdrawals(filter === "all" ? undefined : filter);
      setWithdrawals(data);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(load, [filter]);

  async function handleApprove(id) {
    await adminApi.approveWithdrawal(id);
    load();
  }

  async function handleReject(id) {
    await adminApi.rejectWithdrawal(id);
    load();
  }

  if (loading) return <div className="spinner" />;
  if (error) return <p className="error-text">{error}</p>;

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "var(--space-4)" }}>
        <h1 style={{ fontSize: 20, fontWeight: 600 }}>Withdrawals</h1>
        <select
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          style={{ padding: "6px 12px", borderRadius: "var(--radius-md)", border: "1px solid var(--color-border)", background: "var(--color-surface)", color: "var(--color-text)" }}
        >
          <option value="pending">Pending</option>
          <option value="approved">Approved</option>
          <option value="rejected">Rejected</option>
          <option value="paid">Paid</option>
          <option value="all">All</option>
        </select>
      </div>

      {withdrawals.length === 0 ? (
        <p style={{ color: "var(--color-text-muted)" }}>No withdrawals found.</p>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
          {withdrawals.map((w) => (
            <div
              key={w.id}
              style={{
                background: "var(--color-surface-raised)",
                border: "1px solid var(--color-border)",
                borderRadius: "var(--radius-md)",
                padding: "var(--space-3)",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "var(--space-2)" }}>
                <div>
                  <strong>{w.amount} ETB</strong> — User {w.user_id.slice(0, 8)}
                </div>
                <span
                  style={{
                    fontSize: 11,
                    fontWeight: 600,
                    textTransform: "uppercase",
                    padding: "2px 8px",
                    borderRadius: "var(--radius-sm)",
                    background:
                      w.status === "pending"
                        ? "var(--color-warning)"
                        : w.status === "approved" || w.status === "paid"
                          ? "var(--color-success)"
                          : "var(--color-danger)",
                    color: "#fff",
                  }}
                >
                  {w.status}
                </span>
              </div>
              <div style={{ fontSize: 12, color: "var(--color-text-muted)", marginBottom: "var(--space-1)" }}>
                Telebirr: {w.telebirr_phone}
              </div>
              <div style={{ fontSize: 11, color: "var(--color-text-faint)", marginBottom: w.status === "pending" ? "var(--space-2)" : 0 }}>
                {new Date(w.created_at).toLocaleString()}
              </div>
              {w.status === "pending" && (
                <div style={{ display: "flex", gap: "var(--space-2)", marginTop: "var(--space-2)" }}>
                  <button
                    className="btn-primary"
                    onClick={() => handleApprove(w.id)}
                    style={{ fontSize: 13, padding: "6px 12px" }}
                  >
                    Approve
                  </button>
                  <button
                    className="btn-secondary"
                    onClick={() => handleReject(w.id)}
                    style={{ fontSize: 13, padding: "6px 12px" }}
                  >
                    Reject
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
