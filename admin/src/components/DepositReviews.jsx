import { useEffect, useState } from "react";
import { adminApi } from "../adminApi";

export default function DepositReviews() {
  const [reviews, setReviews] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filter, setFilter] = useState("pending");

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const data = await adminApi.listDepositReviews(filter === "all" ? undefined : filter);
      setReviews(data);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(load, [filter]);

  async function handleApprove(id) {
    await adminApi.approveDepositReview(id);
    load();
  }

  async function handleReject(id) {
    const reason = prompt("Rejection reason (optional):");
    await adminApi.rejectDepositReview(id, reason || undefined);
    load();
  }

  if (loading) return <div className="spinner" />;
  if (error) return <p className="error-text">{error}</p>;

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "var(--space-4)" }}>
        <h1 style={{ fontSize: 20, fontWeight: 600 }}>Deposit Reviews</h1>
        <select
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          style={{ padding: "6px 12px", borderRadius: "var(--radius-md)", border: "1px solid var(--color-border)", background: "var(--color-surface)", color: "var(--color-text)" }}
        >
          <option value="pending">Pending</option>
          <option value="approved">Approved</option>
          <option value="rejected">Rejected</option>
          <option value="all">All</option>
        </select>
      </div>

      {reviews.length === 0 ? (
        <p style={{ color: "var(--color-text-muted)" }}>No deposit reviews found.</p>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
          {reviews.map((r) => (
            <div
              key={r.id}
              style={{
                background: "var(--color-surface-raised)",
                border: "1px solid var(--color-border)",
                borderRadius: "var(--radius-md)",
                padding: "var(--space-3)",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "var(--space-2)" }}>
                <div>
                  <strong>{r.amount} ETB</strong> — User {r.user_id.slice(0, 8)}
                </div>
                <span
                  style={{
                    fontSize: 11,
                    fontWeight: 600,
                    textTransform: "uppercase",
                    padding: "2px 8px",
                    borderRadius: "var(--radius-sm)",
                    background: r.status === "pending" ? "var(--color-warning)" : r.status === "approved" ? "var(--color-success)" : "var(--color-danger)",
                    color: "#fff",
                  }}
                >
                  {r.status}
                </span>
              </div>
              <div style={{ fontSize: 12, color: "var(--color-text-muted)", marginBottom: "var(--space-1)" }}>
                Reference: {r.reference}
              </div>
              <div style={{ fontSize: 12, color: "var(--color-text-muted)", marginBottom: "var(--space-1)" }}>
                Error: {r.verification_error}
              </div>
              <div style={{ fontSize: 12, color: "var(--color-text-muted)", marginBottom: "var(--space-2)" }}>
                SMS: {r.sms_text.slice(0, 200)}...
              </div>
              <div style={{ fontSize: 11, color: "var(--color-text-faint)", marginBottom: "var(--space-2)" }}>
                {new Date(r.created_at).toLocaleString()}
              </div>
              {r.status === "pending" && (
                <div style={{ display: "flex", gap: "var(--space-2)" }}>
                  <button
                    className="btn-primary"
                    onClick={() => handleApprove(r.id)}
                    style={{ fontSize: 13, padding: "6px 12px" }}
                  >
                    Approve & Credit
                  </button>
                  <button
                    className="btn-secondary"
                    onClick={() => handleReject(r.id)}
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
