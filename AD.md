# ETFC Betting Bot

[![License](https://img.shields.io/badge/license-NLA%2FBet%2F09%2F2026-gold)]() [![License](https://img.shields.io/badge/license-MIT-blue)]() [![Docker](https://img.shields.io/badge/docker-ready-brightgreen)]() [![Tests](https://img.shields.io/badge/tests-141%2B-success)]() [![Python](https://img.shields.io/badge/python-3.11+-blue)]() [![Telegram](https://img.shields.io/badge/telegram-mini_app-blue)]() [![Telebirr](https://img.shields.io/badge/telebirr-integrated-green)]()

**Licensed fixed-odds wagering platform for ETFC fight cards** — Telegram bot, React Mini App, and admin panel. Real-money betting via Telebirr with NLA/Bet/09/2026 license, or demo mode with play money.

**Two deployment modes, same engine:**

Production (live wagering)

Demo / Development (play money, no real funds)

**License**

NLA/Bet/09/2026 (National Lottery Association), scoped to ETFC fights, domestic only.

MIT (core engine), Open Source Commercial License (admin/billing module)

**Markets**

Moneyline, method-of-victory, round-prop, multi-fight parlays

Moneyline, method-of-victory, round-prop, multi-fight parlays

**Real money**

Yes — Telebirr deposits, verified against Ethio Telecom receipts

No — auto-seeded demo balance (1000 ETB), deposits blocked

**Test coverage**

141+ tests covering settlement, deposits, parlays, rate limiting, security

141+ tests covering settlement, deposits, parlays, rate limiting, security

**Security**

Bearer-token admin auth, rate limiting, HMAC initData validation, row-level locking

Bearer-token admin auth, rate limiting, HMAC initData validation, row-level locking

**Setup**

Docker, Postgres, env vars

Docker, SQLite, env vars

demo-etfc-betting.mp4

### How It Works

[](#how-it-works)

Placeholder — see live demo below

## One Platform, Three Surfaces

[](#one-platform-three-surfaces)

### 1. Telegram Mini App

[](#1-telegram-mini-app)

Bet on ETFC fight cards directly inside Telegram — no downloads, no accounts.

[![Mini App Screenshot](https://via.placeholder.com/600x400/1a1a1a/FFD700?text=ETFC+Mini+App)]() 

- **Fight card browser** — red-corner / blue-corner visual convention, fighter photos, main-event ribbons
- **Live bet slip** — accumulative cart for single bets and parlays, real-time combined odds
- **Wallet** — deposit via Telebirr, balance history, transaction ledger
- **My Bets** — per-leg status badges for parlays, win/loss/void tracking
- **Telegram-native auth** — HMAC-signed initData, no passwords, no spoofed user IDs

### 2. Telegram Bot

[](#2-telegram-bot)

Deep-linked bot that opens the Mini App and delivers fight-card notifications.

- **/start** — launches Mini App, shows wagering status (live or demo)
- **Fight alerts** — scheduled reminders before card start
- **Result notifications** — instant settlement alerts per fight
- **Support** — direct link to operator contact

### 3. Admin Panel

[](#3-admin-panel)

React SPA for fight-card operations and risk management.

[![Admin Panel Screenshot](https://via.placeholder.com/600x400/1a1a1a/FFD700?text=Admin+Panel)]() 

- **Fight management** — create fighters with photos, build cards, set main events, void fights
- **Market operations** — suspend / reopen markets, adjust odds (odds snapshotting protects existing bets)
- **Settlement** — one-click grade by result (winner, method, round), parlay-aware resolution
- **Liability view** — per-outcome exposure from pending bets only
- **Deposit accounts** — rotating Telebirr receiving numbers, round-robin after N deposits
- **Auth** — bearer-token gate, admin-token brute-force protection (10 failures / 5 min)

## Key Features

[](#key-features)

### Fixed-Odds Engine

[](#fixed-odds-engine)

- **Decimal odds** — simple payout math (stake × odds), no American/fractional conversion
- **Odds snapshotting** — a bet locks its odds at placement; later moves never touch existing payouts
- **House edge** — lives in the odds you set, not as an extra cut (ETFC_HOUSE_CUT_FRACTION defaults to 0)
- **Concurrency-safe** — SELECT ... FOR UPDATE row locking prevents double-betting and ghost settlements

### Markets

[](#markets)

Market Type

Settlement Key

Example

**Moneyline**

Winning fighter

Fighter A wins → Fighter A market pays

**Method-of-victory**

Recorded method (KO/TKO, submission, decision, draw, NC)

Fight ends by KO → "KO/TKO" market pays

**Round-prop**

Actual ending round, or "Goes the Distance" if decision

Fight ends R2 → "Round 2" market pays; decision → "Goes the Distance" pays

**Parlay**

All legs must win (WON or VOID per leg)

2-leg ticket (1.65 × 1.90 = 3.13 combined odds)

### Deposit & Wallet

[](#deposit--wallet)

- **Telebirr SMS verification** — regex + online receipt cross-check against Ethio Telecom's own system (transactioninfo.ethiotelecom.et)
- **Rotating accounts** — add Telebirr numbers from admin, one active at a time, round-robin after configurable deposits
- **Double-credit protection** — partial unique index on deposit references, IntegrityError caught cleanly
- **Circuit breaker** — stops hammering receipt site if it's down; falls back to SMS-only rather than blocking real money
- **Demo mode** — ETFC_WAGERING_ENABLED=false auto-seeds 1000 ETB, blocks real deposits entirely

### Parlays

[](#parlays)

- **Multi-leg tickets** — combine selections from different fights, combined odds are the product
- **Correlated-parlay protection** — only one selection per fight allowed, enforced server-side
- **Void handling** — a voided leg is excluded from payout math (not a loss, not counted at its odds)
- **All-void push** — every leg voided → ticket is VOID, stake refunded
- **Independent settlement** — legs resolve as their fights finish; ticket finalizes when no PENDING legs remain

### Security & Rate Limiting

[](#security--rate-limiting)

Layer

Scope

Limit

**Global per-IP**

All endpoints

180 req/min

**Deposit submissions**

Per Telegram user

5 attempts/hour

**Bet placement**

Per Telegram user

20 bets/min

**Admin token brute-force**

Per IP

10 failures / 5 min

**Telegram initData**

All Mini App requests

HMAC-SHA256 + 24h freshness window

## Tech Stack

[](#tech-stack)

Layer

Technology

Backend

Python 3.11, FastAPI, SQLAlchemy 2.0, faster-whisper (transcription), yt-dlp, FFmpeg

Frontend

React 18, Vite, Tailwind CSS

Database

PostgreSQL (production), SQLite (dev/demo)

Auth

Telegram HMAC-signed initData, bearer-token admin auth

Payments

Telebirr SMS parsing + Ethio Telecom receipt verification

Infrastructure

Docker + Docker Compose, S3 cloud backup, async job queue

## Data Model

[](#data-model)

Entity

Description

**Fighter**

Name, photo URL, corner convention (red/blue)

**Fight**

Two fighters, scheduled time, result (winner, method, round), main-event flag

**Market**

One per type per fight (moneyline, method, round-prop), suspend/reopen state

**MarketOutcome**

Label, decimal odds, settlement key (fighter_id / victory_method / round_number)

**Bet**

Snapshots odds at placement, linked to user + outcome, supports parlays via ParlayLeg

**Parlay**

Multi-leg ticket, combined odds, stake, payout on full win

**Wallet / WalletTransaction**

Cached balance + append-only ledger (source of truth), deposits, holds, payouts, refunds

**DepositAccount**

Rotating Telelebirr pool, one active at a time, deposit counter

## Settlement Rules

[](#settlement-rules)

Scenario

Action

**Standard moneyline win**

Outcome matching winner → WON; other → LOST

**Method-of-victory**

Outcome matching recorded method → WON; others → LOST

**Round-prop**

Decision → "Goes the Distance" wins; KO/TKO/Submission → matching round wins

**Draw / No Contest**

All markets VOID → stakes refunded, no losers declared

**Fight cancelled**

Manual POST /fights/{id}/void → same voiding/refund path

**Parlay leg voided**

Excluded from payout math; ticket continues on remaining legs

**All parlay legs voided**

Ticket VOID → full stake refunded

## Who Is This For?

[](#who-is-this-for)

**ETFC operators** — turn fight cards into regulated, fixed-odds wagering products with a licensed engine

**Fight promoters** — add a licensed betting layer to your events without building a sportsbook from scratch

**Betting startups** — white-label-ready architecture, scoped license (ETFC fights, domestic only), swap the UI/brand

**Telegram communities** — native Mini App experience, no separate downloads, wallet inside the chat

**Regulators** — transparent audit trail (append-only ledger, odds snapshotting, settlement logs), configurable demo mode for review

## Getting Started

[](#getting-started)

### 1. Clone

[](#1-clone)

git clone https://github.com/<your-org>/etfc-betting-bot.git
cd etfc-betting-bot

### 2. Configure

[](#2-configure)

cp .env.example .env
# Edit .env — see Production notes for live wagering vars

### 3. Launch

[](#3-launch)

docker compose up --build

### 4. Open Surfaces

[](#4-open-surfaces)

Surface

URL

**Mini App**

http://localhost:5173

**Admin Panel**

http://localhost:5174

**API Docs**

http://localhost:8000/docs

## Production Notes

[](#production-notes)

- **Postgres, not SQLite** — before real money, swap ETFC_DATABASE_URL to PostgreSQL; SELECT ... FOR UPDATE requires real row locking
- **ETFC_WAGERING_ENABLED=true** — single env var flips to live mode; demo mode stays in codebase for instant rollback
- **Telebirr verification** — ETFC_TELEBIRR_VERIFY_ENABLED=true in production, false for local dev
- **License number** — ETFC_LICENSE_NUMBER=NLA/Bet/09/2026 displayed on wallet screen for user transparency
- **No withdrawal path yet** — deposit in, bet, win; cash-out endpoint is planned, not yet wired

## Testing

[](#testing)

```bash
pytest tests/ -v
```

141+ tests covering:

- Demo balance seeding, blocked real deposits pre-license
- Full moneyline / method / round-prop settlement
- Parlay settlement (all leg-order and void combinations)
- Insufficient-funds rejection, suspended-market protection, voided-fight refunds
- Odds snapshotting (later odds changes never touch existing bets)
- House-cut math, input-validation guardrails
- Telegram initData signature validation (wrong token, tampered payload, missing hash, replay/staleness)
- Admin bearer-token auth (missing/malformed/wrong token, public reads still open)
- Rate limiting (global per-IP, per-user deposit, per-user bet, admin brute-force)
- Telebirr SMS parser + online verification + circuit breaker + deposit rotation
- Fighter photos, main-event flag, partial-update semantics

## Comparison: Open Source vs. Proprietary

[](#comparison-open-source-vs-proprietary)

Feature

ETFC Betting Bot

Typical SaaS Sportsbook

Betting Bot Framework

**License cost**

**NLA/Bet/09/2026** (scoped, domestic only)

Recurring platform fees

Varies

**Self-hosted**

**Yes**

Sometimes

Yes

**Open core**

**Yes (MIT + Commercial)**

No

Partial

**Markets**

Moneyline, method, round-prop, parlays

Depends on plan

Depends

**Telegram Mini App**

**Built-in**

Extra integration

Sometimes

**Telebirr payments**

**Native, verified**

Not supported

Not supported

**Demo mode**

**Yes — no code change to rollback**

No

Sometimes

**Audit trail**

Append-only ledger, odds snapshots, settlement logs

Platform-managed

Varies

**Rate limiting**

3-layer (global, per-user deposit, per-user bet)

Platform-managed

Varies

**Admin auth**

Bearer token + brute-force protection

SSO / RBAC

Varies

## Bugs Found and Fixed

[](#bugs-found-and-fixed)

Three real bugs found in a dedicated audit pass, each with a regression test:

- **Deposit double-credit race** — plain SELECT without lock allowed two concurrent submissions of the same Telebirr SMS to credit twice. Fixed with a partial unique index + IntegrityError handling.
- **Reopening a settled market** — admin could reopen a market whose fight was already COMPLETED, creating bets that could never grade. suspend_market / reopen_market now refuse on SETTLED or VOID markets.
- **Settling an already-voided fight** — would silently overwrite CANCELLED with a fake COMPLETED + winner. settle_fight now rejects re-settlement of voided fights.

## About

[](#about)

Fixed-odds wagering engine for Ethiopian Togolese Fighting Championship (ETFC) fight cards. Licensed under NLA/Bet/09/2026 (National Lottery Association), scoped to ETFC fights, domestic only. Core engine is MIT-licensed; admin/billing module is source-available under the OpenShorts Commercial License pattern.

## Resources

[](#resources)

[Readme](#readme-ov-file)

[License](#license-ov-file)

[Activity]()

[Releases]()

[Packages]()

[Contributors]()

## Topics

[](#topics)

[betting-engine](https://github.com/topics/betting-engine)[telegram-bot](https://github.com/topics/telegram-bot)[telegram-mini-app](https://github.com/topics/telegram-mini-app)[fastapi](https://github.com/topics/fastapi)[telebirr](https://github.com/topics/telebirr)[react](https://github.com/topics/react)[mma](https://github.com/topics/mma)[fixed-odds](https://github.com/topics/fixed-odds)[sportsbook](https://github.com/topics/sportsbook)[etfc](https://github.com/topics/etfc)
