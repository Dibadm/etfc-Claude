import { getInitData } from "./telegram";

// Set at build time (see .env.example) to point at the deployed API.
const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

async function request(path, { method = "GET", body, auth = true } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (auth) {
    headers["X-Telegram-Init-Data"] = getInitData();
  }
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const data = await res.json();
      detail = data.detail || detail;
    } catch {
      // response wasn't JSON — keep statusText
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return null;
  return res.json();
}

export const api = {
  me: () => request("/miniapp/me"),
  listFights: (status) => request(`/fights${status ? `?status=${status}` : ""}`, { auth: false }),
  fightMarkets: (fightId) => request(`/fights/${fightId}/markets`, { auth: false }),
  placeBet: (outcomeId, stake) =>
    request("/miniapp/bets", { method: "POST", body: { outcome_id: outcomeId, stake } }),
  myBets: () => request("/miniapp/bets"),
  placeParlay: (outcomeIds, stake) =>
    request("/miniapp/parlays", { method: "POST", body: { outcome_ids: outcomeIds, stake } }),
  myParlays: () => request("/miniapp/parlays"),
  status: () => request("/status", { auth: false }),
  depositAccount: () => request("/miniapp/deposit-account"),
  submitDeposit: (smsText, expectedAmount, idempotencyKey) =>
    request("/miniapp/deposit", {
      method: "POST",
      body: { sms_text: smsText, expected_amount: expectedAmount, idempotency_key: idempotencyKey },
    }),
};

export { ApiError };
