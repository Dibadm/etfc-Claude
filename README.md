# ETFC Betting — Phase 1 (engine) + Phase 2 (Telegram bot + Mini App) + Phase 3 (admin panel) + Live

Fixed-odds wagering engine for ETFC fight cards: moneyline, method-of-victory,
and round-prop markets, plus a Telegram bot, React Mini App, and an admin
panel on top of it. Licensed under **NLA/Bet/09/2026** (National Lottery
Association), scoped to ETFC fights, domestic only.

## The licensing switch

`ETFC_WAGERING_ENABLED` is the single control for whether real money can
move:

- **Off:** deposits/withdrawals of real funds are rejected. Every new
  user is auto-seeded with a demo balance
  (`ETFC_DEMO_SEED_BALANCE`, default 1000 ETB) so the entire product —
  markets, odds, bet placement, settlement, payouts — can be demoed
  end-to-end with play money. This is what got shown to ETFC and the
  National Lottery Association to secure the license.
- **On:** real Telebirr deposits/withdrawals are allowed (see "Going
  live" below); new users stop being demo accounts and start at a real
  0.00 balance.

Flipping it is a config change, not a code change — the betting logic
is identical in both modes, and neither mode is deleted code the other
replaces; both stay live in the codebase so the switch can go either
way. The code default is still `false` (see `app/config.py`) — a fresh
deploy shouldn't accidentally go live on real money just because an env
var was missed. Set it to `true` explicitly in your production `.env`
once you're ready.

## Running it

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Visit `http://localhost:8000/docs` for interactive API docs.

## Running tests

```bash
pytest tests/ -v
```

16 tests cover: demo balance seeding, blocked real deposits pre-license,
full moneyline win/loss settlement, method-of-victory + round-prop
settling together off one fight result, insufficient-funds rejection,
betting against a suspended market, voided-fight refunds, double-settlement
protection, odds snapshotting (a later odds change never touches
an already-placed bet), house-cut math, and a set of input-validation
guardrails (bad outcome/user ids, duplicate/self fighter matchups,
odds ≤ 1.00) added after a manual audit — see "Hardening pass" below.

36 tests total as of Phase 2 — the additional 20 cover Telegram initData
signature validation (wrong token, tampered payload, missing hash,
replay/staleness, malformed user field) and the `/miniapp/*` integration
surface (a user can only ever bet as themselves, bad/missing auth is
rejected cleanly, market display ordering, moneyline preview odds on the
fight list).

50 tests total as of Phase 3 — the additional 14 cover admin bearer-token
auth (missing/malformed/wrong token all rejected, public read endpoints
still need no token), the dedicated `/admin/ping` auth-check endpoint
(added after the login screen couldn't tell a bad token apart from a
404 on a real resource — see "Phase 3" below), suspend/reopen market,
odds updates (including that a later odds change never affects an
already-placed bet's payout, re-verified from the admin-endpoint side),
and the liability view (correctly sums only PENDING bets, excludes
settled ones).

61 tests total after the frontend upgrade — the additional 11 cover
fighter photos (create/patch with `image_url`, partial-update semantics,
404 on a bad fighter id) and the main-event flag (defaults false, settable
at creation or toggled after, and correctly appears in the fight list
alongside fighter photos).

100 tests total after wiring up real Telebirr deposits — see "Going live"
below for what the additional 39 cover.

121 tests total after adding rate limiting — see "Rate limiting" below
for what the additional 21 cover.

141 tests total after the bug-hunt pass and adding parlays — see "Bugs
found and fixed" and "Multi-fight tickets" below for what the additional
20 cover.

## Data model

- **Fighter / Fight** — a fight has two fighters, a scheduled time, and
  (once settled) a result: winner, method (KO/TKO, submission, decision,
  draw, no contest), and round.
- **Market / MarketOutcome** — a fight can have one market per type
  (moneyline, method-of-victory, round-prop). Each outcome carries its
  own decimal odds (stake × odds = potential payout) plus a
  settlement-matching key (`fighter_id`, `victory_method`, or
  `round_number`) so settlement doesn't have to parse label text.
- **Bet** — snapshots the odds at placement time, so later odds moves
  never retroactively change an existing bet's payout.
- **Wallet / WalletTransaction** — `wallet.balance` is a cached total;
  `WalletTransaction` is the append-only ledger that's the actual source
  of truth (tests assert the two always agree).
- **DepositAccount** — a rotating pool of Telebirr receiving numbers;
  exactly one is `is_active` at a time. See "Going live" below.

## Settlement rules

- **Moneyline:** the outcome matching the winning fighter wins; the other loses.
- **Method-of-victory:** the outcome matching the recorded method wins.
- **Round-prop:** if the fight went to decision, "Goes the Distance" wins;
  otherwise the outcome matching the actual ending round wins.
- **Draw / No Contest:** every market on that fight is voided instead of
  settled — all pending bets get their stake refunded, nobody is declared
  a loser on a result that wasn't really a result.
- **Fight cancelled:** same voiding/refund path, triggered manually via
  `POST /fights/{id}/void`.

## Hardening pass

Before delivery, every endpoint was manually probed with bad/edge-case
input rather than trusting the happy-path tests alone. Five real gaps
were found and fixed:

- A bad `outcome_id` or `user_id` on `POST /bets` crashed with an
  unhandled 500 instead of a 404 (`OutcomeNotFoundError` /
  `UserNotFoundError` now raised and caught cleanly).
- SQLite was silently ignoring the `ForeignKey()` constraints in
  `models.py` — a fight could be created pointing at a nonexistent
  fighter and nothing complained. `PRAGMA foreign_keys=ON` is now set
  per-connection so dev/test behavior matches Postgres.
- A fight could be created with the same fighter as both sides — now
  rejected with a 400.
- Market creation accepted odds ≤ 1.00 (nonsensical — the bettor
  couldn't win money) or negative odds. All three market-creation
  schemas now reject odds below 1.01.

## Phase 2 — Telegram bot + Mini App

**Setup:**

```bash
# .env (project root)
ETFC_TELEGRAM_BOT_TOKEN=<from @BotFather>
ETFC_MINI_APP_URL=https://<wherever you deploy miniapp/>
ETFC_CORS_ALLOW_ORIGINS=https://<same mini app domain>,http://localhost:5173

# run the API
uvicorn app.main:app --reload

# run the bot (separate process, same .env)
python bot.py

# run the Mini App frontend
cd miniapp && npm install
echo "VITE_API_BASE_URL=http://localhost:8000" > .env   # or your deployed API URL
npm run dev
```

**Telegram auth (`app/telegram_auth.py`).** The Mini App frontend sends
Telegram's signed `initData` (from `window.Telegram.WebApp.initData`) as an
`X-Telegram-Init-Data` header on every request to `/miniapp/*`. The backend
verifies the HMAC signature against the bot token, rejects anything stale
(replay protection) or tampered, and only then trusts the `user.id` inside
it. This is what makes it safe to drop `user_id` from the request body
entirely on this surface — there's nothing left for a client to spoof.
The original Phase 1 endpoints (`/users`, `/bets` with a raw `user_id`,
etc.) are untouched and still work, for internal testing/tooling.

**What's still open (not a gap I patched around — a real Phase 3 item):**
the fight/market/settlement endpoints (`POST /fights`, `POST /markets/*`,
`POST /fights/{id}/settle`, `/void`) have **no auth at all** right now.
Fine while only you're calling them directly; not fine once this is
live and those URLs are guessable. Phase 3 (admin panel) needs to close
this before launch — a simple bearer-token gate would do it.

**CORS.** The Mini App and the API are different origins, so
`ETFC_CORS_ALLOW_ORIGINS` must include the Mini App's real deployed
domain in production (defaults to localhost origins for dev). Found this
one by actually running the frontend against the API rather than trusting
the code — every fetch failed silently as a CORS error until this was
added.

**Design.** Dark, MMA-specific palette (see `miniapp/src/index.css` — the
red-corner/blue-corner convention is the actual structural device, not
decoration, used consistently from the fight list through to individual
markets). Oswald for fighter names/titles, Inter for body text, IBM Plex
Mono for odds figures so they align like a scoreboard. Verified by
running the built app end-to-end (auth → fight list → bet slip → wallet
→ bet history) in a real browser and screenshotting each screen, not just
reading the code.

## Phase 3 — Admin panel

**Setup:**

```bash
# add to .env, alongside the Phase 2 vars
ETFC_ADMIN_TOKEN=<pick a long random string>

cd admin && npm install
echo "VITE_API_BASE_URL=http://localhost:8000" > .env
npm run dev
```

Open the admin URL, paste the token in, done — it's stored in
`sessionStorage` for that browser tab only (not `localStorage` — cleared
when the tab closes, deliberately, since this token isn't meant to be a
long-lived credential sitting in a browser).

**What closed the gap flagged at the end of Phase 2.** Every mutating
endpoint (`POST /fighters`, `POST /fights`, `POST /markets/*`, settle,
void) plus the new admin-only ones (suspend/reopen market, update odds,
liability view) now require `Authorization: Bearer <ETFC_ADMIN_TOKEN>`
(`app/admin_auth.py`). Fails closed: if the token isn't configured at
all, these endpoints refuse to work rather than silently staying open.
Read-only endpoints the Mini App needs (`GET /fights`, `/fights/{id}/markets`,
`/status`) are untouched — still public, no token needed.

**What's new beyond closing that gap:**
- **Suspend/reopen a market** — for pulling odds off the board right
  before a fight without having to settle it.
- **Adjust an outcome's odds** — rejects the same odds-floor (≤1.00) as
  market creation. Re-verified that this never touches bets already
  placed at the old odds — that's the whole point of odds snapshotting,
  and it held up all the way through the admin UI, not just the service
  layer.
- **Liability view** — per-outcome exposure (bet count, total stake,
  worst-case payout) from *pending* bets only. One real gotcha found
  while screenshotting this: if you change an outcome's odds after bets
  already exist on it, the liability table's payout figures reflect what
  those bets actually locked in, not today's price — showing "current
  odds" next to that number was actively misleading, so that column was
  removed. The table is about real exposure from bets that exist, not
  a pricing display.
- A fight-creation form with an inline "+ New fighter" quick-add, so
  building a card doesn't require a separate fighter-management screen
  first.

**Found by actually running it, not just reading the code:** the first
version of the login screen used a real resource endpoint
(`/admin/fights/<fake-id>/liability`) to check whether the entered token
was valid. A *correct* token still got a 404 (fight doesn't exist),
which the login screen couldn't distinguish from a 401 (bad token) — so
login could never succeed with any token, correct or not. Fixed by
adding `GET /admin/ping`, an endpoint whose only job is "is this token
valid, yes or no," with nothing to look up and therefore nothing to
404 on.

**Still open, on purpose:** one shared token, not per-admin accounts —
fine for a single operator, not fine if this ever becomes a team
managing fight cards. Upgrade to real admin accounts before handing the
token to more than one person.

## Frontend upgrade — fighter photos, main event styling, logo

**Fighter photos.** `Fighter.image_url` (optional) — set it at creation or
later from the admin panel's new **Fighters** page. The Mini App shows the
photo if one's set; if it's missing, empty, or the URL 404s, it falls back
to a corner-colored initials badge instead — never a broken-image icon.
`FighterAvatar` (`miniapp/src/components/FighterAvatar.jsx`) is the shared
component behind both the fight list and fight detail screens.

**Main event styling.** `Fight.is_main_event` (bool, defaults false) — set
it in the create-fight form or toggle it later from the fight detail admin
page. A main-event fight gets a gold border/glow, a "★ Main Event" ribbon,
and larger avatars/type in the Mini App. No exclusivity is enforced — the
system won't stop you from marking two fights as main event on the same
card; that's on the admin to manage.

**Logo.** Drop a file at `miniapp/public/logo.png` (square, ideally
128px+, transparent background) and it appears next to "ETFC BETTING" in
the header automatically — no code change needed. Until then, a built-in
gold monogram badge fills that spot so the header never looks broken or
empty. Verified both states actually render correctly (fallback badge,
then swapped for a real file) rather than just trusting the `onError`
logic — see `miniapp/src/components/Logo.jsx`.

## Going live — real Telebirr deposits

Licensed under NLA/Bet/09/2026 (National Lottery Association), scoped to
ETFC fights, domestic only. This section covers what changes when
`ETFC_WAGERING_ENABLED` flips to `true`.

**Nothing to "de-demo" separately.** Every place that said "demo" — the
header banner, the wallet screen, the bot's `/start` message — reads
`status.wagering_enabled` (or `settings.wagering_enabled` server-side)
and switches to live language automatically. There's no hardcoded demo
copy to hunt down and delete; the demo-mode fallback stays in the
codebase (not stripped out) so it's still there if wagering ever needs
to pause again — see `app/config.py`'s docstring for the reasoning
that's been true since Phase 1.

**Telebirr verification is ported from Habesha Bet, not reimplemented
from a guess.** `app/services/telebirr_sms_parser.py` and
`app/services/telebirr_verify.py` are the same regex patterns and the
same online-receipt cross-check as `github.com/Dibadm/mosses-`
(`backend/sms_parser.py` / `backend/telebirr_verify.py`), pulled from
that repo directly. One deliberate change: amounts are `Decimal` here,
not `float`, to match how the rest of this codebase already handles
money.

The verification isn't just "trust the pasted SMS text" — a user could
edit that by hand. The real check is the transaction reference number
inside the SMS getting looked up against **Ethio Telecom's own online
receipt system** (`transactioninfo.ethiotelecom.et`), so the source of
truth is Ethio Telecom's own record, not anything the user submitted.
If that site is genuinely unreachable, deposits fall back to the
SMS-regex checks rather than blocking real money on a flaky third-party
site — but a receipt that's actively wrong (not found, mismatched
amount) is a real rejection, not a fallback. A circuit breaker (ported
as-is) stops hammering the receipt site if it's failing repeatedly.

**Rotating deposit accounts** work the same way as Habesha Bet: add
Telebirr numbers from the admin panel's new **Deposit Accounts** page,
exactly one is active at a time, and deposits rotate to the next account
round-robin after `ETFC_ROTATE_AFTER_DEPOSITS` (default 20) successful
deposits on the active one.

**Env vars to set before flipping the switch:**
```
ETFC_WAGERING_ENABLED=true
ETFC_LICENSE_NUMBER=NLA/Bet/09/2026
ETFC_DATABASE_URL=postgresql://...       # not sqlite — see below
ETFC_TELEBIRR_VERIFY_ENABLED=true        # false only for local dev
```
The license number is purely informational — it's displayed on the
wallet screen for user-facing transparency, nothing in the code enforces
it or checks it against anything.

Full test coverage for this: 39 new tests across
`tests/test_telebirr_sms_parser.py` (parser correctness against the real
SMS format), `tests/test_telebirr_verify.py` (online verification with
the HTTP layer mocked — no real network calls in tests — including the
circuit breaker actually tripping and resetting), and
`tests/test_deposit_flow.py` (the full orchestration: wrong-account
rejection, duplicate-reference rejection, account rotation, and the
online-verification success/mismatch/site-down-fallback/not-found
branches). Verified beyond the test suite too — screenshotted the actual
deposit flow end to end in a real browser against a running API: pasted
a real-format SMS, watched the balance go from 0.00 to 500.00, confirmed
the admin panel's deposit-accounts table reflected the same transaction.

## Bugs found and fixed in a dedicated audit pass

Three real ones, each with a regression test:

- **Deposit double-credit race.** `reference_already_used()` was a plain
  SELECT with no lock behind it — two concurrent submissions of the same
  Telebirr SMS could both pass that check before either committed,
  crediting the same real transaction twice. Fixed at the database
  level: a partial unique index on `WalletTransaction(reference) WHERE
  type='deposit'` (not a global unique constraint — `reference` legitimately
  repeats for other transaction types, e.g. every demo-credit row shares
  the literal string `"signup_demo_seed"`, and a bet's hold/payout/refund
  rows all share that bet's id across three different types). The
  application-level check stays as a friendly first error; the index is
  the actual guard, with `deposit_service.py` catching the resulting
  `IntegrityError` and turning it into the same clean rejection instead
  of a raw 500.
- **Reopening a settled/voided market.** Nothing stopped an admin from
  reopening a market whose fight was already `COMPLETED` — new bets
  could get placed against it that could never be graded, debiting stake
  with no way to ever resolve it. `odds_service.suspend_market`/
  `reopen_market` now refuse on a `SETTLED` or `VOID` market.
- **Settling an already-voided fight.** Would silently overwrite
  `CANCELLED` with a fake `COMPLETED` + winner — no money at risk (markets
  are already refunded and closed), but it corrupted the fight's history.
  `settlement_service.settle_fight` now rejects this the same way it
  already rejected re-settling a completed fight.

## Multi-fight tickets (parlays)

Didn't exist before this — every bet was locked to one outcome on one
fight. `Parlay` / `ParlayLeg` (`app/models.py`) and
`app/services/parlay_service.py` add real multi-leg tickets: combine
selections from **different** fights into one wager, combined odds are
the product of each leg's odds, and every leg has to win for the ticket
to pay out.

**Correlated-parlay protection.** A ticket can only include one selection
per fight — two markets from the same fight (e.g. "Fighter A wins" and
"Fighter A wins by KO/TKO") aren't independent risk, and combining them
would misprice the payout in the bettor's favor. This is enforced at
placement (`CorrelatedLegsError`), not just a frontend nicety — though the
Mini App also enforces it proactively: picking a second outcome from a
fight that already has a selection swaps it rather than letting the user
hit a 400 at submit time.

**Settlement is the genuinely hard part.** A parlay can't be graded until
*every* leg's fight has been settled, which normally happens across
several separate `settle_fight` calls over an event, in whatever order
the fights actually finish. `settlement_service.py` resolves each leg as
its fight settles, and only finalizes the parent ticket once no leg is
left `PENDING`:
- Any leg **lost** → the whole ticket is `LOST` (settlement order doesn't
  matter — a ticket loses even if the losing leg happens to settle first).
- A leg's fight gets **voided** → that leg is `VOID`, excluded from the
  payout math entirely (not counted as a loss, and not counted at its
  original odds either) rather than sinking the ticket.
- **Every** leg ends up voided → the ticket is `VOID` and the stake is
  refunded — that's a push, not a "win" with nothing to multiply.
- Otherwise, once every leg is `WON` or `VOID` → payout is recomputed
  from the **won legs' odds only**, not the odds locked at placement time
  (which assumed every leg would win).

18 tests in `tests/test_parlay.py` cover all of the above, plus: combined-
odds/payout math, stake debiting, too-few/too-many/duplicate legs,
betting against a suspended market, insufficient funds, and — importantly
— that a parlay resolving alongside a *regular single bet on the same
outcome* doesn't disturb that bet's settlement at all.

**Mini App:** the old "tap an outcome → instant single-bet slip" flow
became a persistent bet-slip cart (`App.jsx`'s `slipLegs` state) —
selections accumulate across different fights (highlighted gold on the
outcome buttons as you go), a floating slip bar shows the running count,
and the slip itself becomes a parlay ticket automatically once it holds
2+ legs (`BetSlip.jsx` decides `placeBet` vs `placeParlay` based on leg
count, with per-leg remove buttons and live combined odds). Verified in
a real browser end to end: selected two legs across different fights,
watched combined odds compute correctly (1.65 × 1.90 = 3.13) and the
payout preview update live, placed the ticket, and confirmed it showed
correctly under a new "Parlays" section in My Bets with per-leg status
badges.

**Known gap, not addressed here:** the admin liability view
(`/admin/fights/{id}/liability`) only accounts for single-bet exposure —
it doesn't yet factor in pending parlay legs touching a fight. Worth
adding before parlay volume gets meaningful; skipped this pass to keep
scope to what's actually been tested.

## Rate limiting

Three layers, all in-memory/process-local (same tradeoff as the Telebirr
circuit breaker — fine for a single `uvicorn` worker, move to Redis if
this ever runs multi-process behind a load balancer):

- **Global per-IP:** 180 requests/minute across every endpoint, via
  middleware (`app/main.py`). A broad safety net, not tuned per-endpoint.
- **Deposit submissions:** 5 attempts/hour per user (not per IP — keyed
  by the resolved Telegram user id, since many real users can share an
  IP behind carrier-grade NAT, which is common on Ethiopian mobile
  networks). This is the tightest limit on purpose — every submission
  calls out to Ethio Telecom's real receipt system (see "Going live"
  above), so spamming this endpoint doesn't just cost us, it hammers a
  third party's server through ours.
- **Bet placement:** 20 bets/minute per user — generous for a real
  bettor working through a fight card, tight enough to block scripted
  spam.
- **Admin token brute-forcing:** 10 wrong-token attempts per 5 minutes
  per IP (`app/admin_auth.py`). Only *failures* count — a legitimate
  admin who fat-fingers the token twice and then gets it right is never
  throttled by their own typos.

All three return `429` with a `Retry-After` header. `app/services/rate_limiter.py`
is the shared sliding-window implementation behind all of them.

12 tests for the limiter itself (independent keys, window sliding,
peek-without-recording, the failure-only-counts pattern), plus
integration tests confirming each limit actually fires at the right
endpoint and is scoped correctly (per-user limits don't leak across
users; the global limit doesn't leak across IPs) — including one that
hammers `/admin/ping` with a wrong token over real HTTP against a
running server, not just through the test client, to confirm the
10-failures-then-429 behavior holds outside of TestClient's request
plumbing too.

## Production notes before going live

- **Postgres, not SQLite, before real money is involved.** Bet placement
  and settlement use `SELECT ... FOR UPDATE` row locking to keep
  concurrent bets/settlement safe — SQLite doesn't enforce real row
  locks. SQLite is fine for this phase's dev/tests; swap
  `ETFC_DATABASE_URL` for production.
- **Odds format is decimal** (e.g. 2.50), not American/fractional —
  simplest payout math (`stake × odds`) for a from-scratch engine.
- **The house edge lives in the odds you set**, not as an extra cut —
  `ETFC_HOUSE_CUT_FRACTION` defaults to 0 and stacking it on top of
  already-vigged odds is discouraged (see `odds_service.py` docstring).
- **No withdrawal path yet** — `wallet_service.withdraw_real_funds()`
  exists at the service layer but isn't wired to any API endpoint or UI.
  Users can deposit; there's currently no way for them to cash out.
