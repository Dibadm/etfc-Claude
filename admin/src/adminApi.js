const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";
const TOKEN_KEY = "etfc_admin_token";

export function getToken() {
  return sessionStorage.getItem(TOKEN_KEY) || "";
}

export function setToken(token) {
  sessionStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  sessionStorage.removeItem(TOKEN_KEY);
}

class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

async function request(path, { method = "GET", body } = {}) {
  const headers = { "Content-Type": "application/json" };
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const data = await res.json();
      detail = data.detail || detail;
    } catch {
      // not JSON
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return null;
  return res.json();
}

export const adminApi = {
  // Dedicated auth-check endpoint — see app/main.py's admin_ping. Deliberately
  // NOT hitting a real resource endpoint with a fake id: that returns 404,
  // which the login screen would have no way to distinguish from a bad token.
  checkToken: () => request("/admin/ping"),

  listFights: (status) => request(`/fights${status ? `?status=${status}` : ""}`),
  createFight: (payload) => request("/fights", { method: "POST", body: payload }),
  settleFight: (fightId, payload) => request(`/fights/${fightId}/settle`, { method: "POST", body: payload }),
  voidFight: (fightId) => request(`/fights/${fightId}/void`, { method: "POST" }),
  setMainEvent: (fightId, isMainEvent) =>
    request(`/admin/fights/${fightId}/set-main-event?is_main_event=${isMainEvent}`, { method: "POST" }),

  createFighter: (payload) => request("/fighters", { method: "POST", body: payload }),
  listFighters: () => request("/fighters"),
  updateFighter: (fighterId, payload) => request(`/fighters/${fighterId}`, { method: "PATCH", body: payload }),

  fightMarkets: (fightId) => request(`/fights/${fightId}/markets`),
  createMoneyline: (payload) => request("/markets/moneyline", { method: "POST", body: payload }),
  createMethodOfVictory: (payload) => request("/markets/method-of-victory", { method: "POST", body: payload }),
  createRoundProp: (payload) => request("/markets/round-prop", { method: "POST", body: payload }),

  suspendMarket: (marketId) => request(`/admin/markets/${marketId}/suspend`, { method: "POST" }),
  reopenMarket: (marketId) => request(`/admin/markets/${marketId}/reopen`, { method: "POST" }),
  updateOdds: (outcomeId, newOdds) =>
    request(`/admin/outcomes/${outcomeId}/odds`, { method: "POST", body: { new_odds: newOdds } }),

  liability: (fightId) => request(`/admin/fights/${fightId}/liability`),

  listDepositAccounts: () => request("/admin/deposit-accounts"),
  addDepositAccount: (payload) => request("/admin/deposit-accounts", { method: "POST", body: payload }),
  removeDepositAccount: (accountId) => request(`/admin/deposit-accounts/${accountId}`, { method: "DELETE" }),
  activateDepositAccount: (accountId) =>
    request(`/admin/deposit-accounts/${accountId}/activate`, { method: "POST" }),

  listDepositReviews: (status) => request(`/admin/deposit-reviews${status ? `?status=${status}` : ""}`),
  approveDepositReview: (reviewId) =>
    request(`/admin/deposit-reviews/${reviewId}/approve`, { method: "POST" }),
  rejectDepositReview: (reviewId, reason) =>
    request(`/admin/deposit-reviews/${reviewId}/reject`, { method: "POST", body: { reason } }),

  jackpotRounds: () => request("/jackpot/rounds"),
  createJackpotRound: (payload) => request("/admin/jackpot/rounds", { method: "POST", body: payload }),
  settleJackpotRound: (roundId) => request(`/admin/jackpot/rounds/${roundId}/settle`, { method: "POST" }),
  jackpotEntries: (roundId) => request(`/admin/jackpot/rounds/${roundId}/entries`),

  status: () => request("/status"),
};

export { ApiError };
