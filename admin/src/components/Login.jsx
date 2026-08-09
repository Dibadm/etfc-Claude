import { useState } from "react";
import { adminApi, setToken } from "../adminApi";

export default function Login({ onSuccess }) {
  const [token, setTokenInput] = useState("");
  const [error, setError] = useState(null);
  const [checking, setChecking] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setChecking(true);
    setError(null);
    setToken(token.trim());
    try {
      await adminApi.checkToken();
      onSuccess();
    } catch (err) {
      setError(err.status === 401 ? "Invalid token" : err.message);
      setChecking(false);
    }
  }

  return (
    <div className="login-screen">
      <form className="login-card" onSubmit={handleSubmit}>
        <h1 className="login-card__title">ETFC Admin</h1>
        <p className="login-card__subtitle">Enter the admin token to continue</p>
        <div className="form-field" style={{ marginBottom: 16 }}>
          <input
            type="password"
            placeholder="Admin token"
            value={token}
            onChange={(e) => setTokenInput(e.target.value)}
            autoFocus
          />
        </div>
        <button className="btn btn-gold" type="submit" disabled={!token || checking} style={{ width: "100%" }}>
          {checking ? "Checking…" : "Continue"}
        </button>
        {error && <p className="error-text">{error}</p>}
      </form>
    </div>
  );
}
