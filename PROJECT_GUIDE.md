# Fraud MPC System — Full Project Guide

A complete reference for what this project is, how every piece fits together, and a
single linear path to get it running end to end — including the real secure
multi-party computation (MPC) module, not just the fallback mode.

---

## 1. What this project is

This is a **service-oriented fraud-detection pipeline for UPI-style payments**.

The core idea: a payment passes through a gateway and three participant banks
(SBI, HDFC, NPCI). Each of those parties can see *some* of the signals that
matter for fraud detection, but none of them can see all of it, and none of
them are willing (or allowed) to hand their raw account data to anyone else.
**Secure multi-party computation (MPC)**, via [MP-SPDZ](https://github.com/data61/MP-SPDZ),
lets all three parties jointly compute a single fraud-risk score over their
combined private inputs — without any party ever seeing another party's raw
data. Only the final score (and the APPROVE / REVIEW / REJECT decision built
from it) comes out the other side.

This is what makes the system interesting from a fraud standpoint: a
coordinated fraud ring can spread its footprint across two different banks
(e.g. an account at SBI and an account at HDFC sharing the same device
fingerprint) specifically so that **no single bank's own data would catch
it**. Only by combining signals across institutions — without breaking data
privacy — does the pattern become visible. That cross-institution correlation
is the entire reason this is worth doing under MPC instead of just training
one bank's model on one bank's data.

### The underlying model

A trained logistic-regression fraud classifier (35 features) is the brains of
the operation. Its weights are not sent around at runtime — they're baked in
ahead of time as public constants that every party already knows, and the
*only* things kept secret at runtime are the raw account-level feature values
each bank feeds in. The MPC circuit computes `logit = bias + Σ(weight_i × feature_i)`
over a mix of public and secret values, and only the final logit is revealed.

### High-level flow

```
                        ┌─────────────┐
   payment request ───► │   Gateway    │  (port 8000)
                        │ (owns 15     │
                        │  features)   │
                        └──────┬──────┘
                               │ broadcasts transaction
                 ┌─────────────┼─────────────┐
                 ▼             ▼             ▼
             ┌───────┐    ┌───────┐    ┌───────┐
             │  SBI  │    │ HDFC  │    │ NPCI  │   participant nodes
             │ :8001 │    │ :8002 │    │ :8003 │   (each computes its
             └───┬───┘    └───┬───┘    └───┬───┘    own local features)
                 │            │            │
                 └─────┬──────┴──────┬─────┘
                        ▼             ▼
                 ┌─────────────────────────┐
                 │      Orchestrator        │ (port 8010)
                 │  pulls gateway + each    │
                 │  participant's features  │
                 └────────────┬────────────┘
                               │
                               ▼
                 ┌─────────────────────────┐
                 │   MPC Integration Layer  │  ── real MP-SPDZ 3-party
                 │  (mpc_integration/)      │     secure computation, OR
                 └────────────┬────────────┘     risk=None fallback
                               │
                               ▼
                 ┌─────────────────────────┐
                 │      Decision Engine     │  → APPROVE / REVIEW / REJECT
                 └─────────────────────────┘
```

---

## 2. Repository layout

```
shared/            Pydantic models, constants, API contract reference — everyone imports from here
gateway/           Payment Gateway (port 8000) — entry point; computes its own 15 owned features
participants/      SBI (8001), HDFC (8002), NPCI (8003) — each computes features from its own data
orchestrator/      Fraud Orchestrator (port 8010) — coordinates everything, calls MPC + decision engine
mpc_integration/   Secure computation layer — real MP-SPDZ integration, falls back to REVIEW if unconfigured
decision_engine/   Thresholding logic (risk score → APPROVE / REVIEW / REJECT)
ai_layer/          Behavioral biometrics — placeholder interface for a separate collaborator's signal
dashboard/         Minimal JSON dashboard (port 8020), optional
scripts/           Mock data generation
mpc_review/        A duplicate copy of the whole project tree, kept in sync — safe to ignore; treat the
                   top-level folders above as the single source of truth
```

All comments and docstrings have been stripped from every `.py` and `.mpc`
file in this delivery — the code is unchanged in behavior, just uncommented.

---

## 3. Component reference

### 3.1 `shared/` — the common contract

- `constants.py` — enums (`SessionStatus`, `Decision`, `ParticipantName`), port
  assignments (gateway `8000`, SBI `8001`, HDFC `8002`, NPCI `8003`,
  orchestrator `8010`, dashboard `8020`), and the two decision thresholds
  (`RISK_THRESHOLD_REJECT = 0.85`, `RISK_THRESHOLD_REVIEW = 0.5`).
- `models.py` — every Pydantic request/response model used across services
  (`PaymentRequest`, `TransactionMessage`, `PrepareResponse`,
  `EvaluateResponse`, `SessionRecord`, etc.).
- `api_contracts.py` — a single-file index mapping every HTTP endpoint to its
  request/response model, so the full API surface can be read in one place.
- `utils.py` — ID generators (`generate_txn_id`, `generate_session_id`) and a
  timestamped `log()` helper used by every service.

### 3.2 `gateway/` — the entry point (port 8000)

Receives the incoming `POST /payment` request and is the **owner of 15 of the
35 model features** — everything derivable purely from the payment request
itself plus lookups it already has (timestamp, amount, device history,
merchant category, IP heuristic). These are *public* features under MPC: the
gateway, SBI, HDFC, and NPCI all already see who's paying whom, when, and how
much, in real UPI — there's no privacy reason to secret-share them.

Key pieces:
- `compute_gateway_features()` — builds all 15 gateway-owned columns plus the
  raw `amount` (needed for one derived feature, `amount_vs_avg_ratio`).
- `device_history.json` — per-account known devices and a running
  `device_changes_30d` counter (a real system would use a proper rolling
  30-day window; this demo uses a monotonically increasing counter).
- `merchant_categories.json` — a merchant name → category lookup.
- `GET /features?txn_id=...` — lets the orchestrator (and `ai_layer`) pull
  back what the gateway computed, mirroring the participants' own
  `/status`-style pull pattern.

After computing its features, the gateway broadcasts the transaction to all
three participants (`POST /transaction`), waits for every ack, then calls the
orchestrator's `POST /evaluate` and returns whatever decision comes back.

### 3.3 `participants/` — SBI, HDFC, NPCI

`participants/common.py` holds a shared FastAPI app factory
(`create_participant_app`) used by all three institutions, plus the two
feature-computation strategies:

- **`make_bank_feature_fn`** — used by SBI and HDFC (retail, account-holding
  banks). For a given transaction it looks at whichever of its own accounts
  is involved and reports either **sender-side** or **receiver-side**
  features (whichever role applies), pulled from `mock_data.json`. Two extra
  fields — `flagged_suspicious` and `device_match` — are computed too but are
  **not** model inputs; they exist purely so `GET /session/<id>` can show a
  human that two banks each independently flagged the same fraud ring,
  without either one ever seeing the other's account data.
- **`make_npci_feature_fn`** — NPCI isn't an account-holding bank; it's the
  UPI switch/routing layer, so its `mock_data.json` is shaped completely
  differently: `{account_id: failed_attempts_24h}`. It reports
  `failed_attempts_24h` and a derived `failed_attempt_risk` flag for the
  *sender* account on every transaction, regardless of which bank owns that
  account.

Every participant exposes the same three endpoints:
- `POST /transaction` — receive and stash a pending transaction.
- `POST /prepare` — actually compute this institution's features for a given
  `txn_id`/`session_id` and return them (`role` + `features`).
- `GET /status?txn_id=...` — check whether a transaction has been prepared.

Because SBI and HDFC can each be sender **or** receiver depending on the
transaction, each one reports its own resolved `role` in its `/prepare`
response — the orchestrator never has to guess bank-to-role mapping itself.

### 3.4 `orchestrator/` — coordination (port 8010)

`POST /evaluate` is the heart of the pipeline:
1. Creates a `SessionRecord`, calls every participant's `/prepare` in
   parallel.
2. Pulls the gateway's already-computed features via `GET /features`.
3. Reshapes everything into the `{sender, receiver, npci, gateway}` shape
   `mpc_integration.main.compute_risk()` expects (`_build_mpc_inputs`).
4. Calls `compute_risk()`. If MP-SPDZ isn't configured (`MPSPDZ_HOME` unset)
   or the computation fails for any reason, it logs why and falls back to
   `risk=None` rather than crashing the request.
5. Runs `decision_engine.decide(risk)` and stores the result on the session.

`GET /session/{id}` and `GET /sessions` expose the full session record —
including each participant's raw *reported* features — for debugging and
demoing (this is how you inspect "what did SBI/HDFC actually compute for this
transaction").

### 3.5 `mpc_integration/` — Module 4, the secure computation layer

This is the most involved part of the system. It has been **verified
end-to-end against a real MP-SPDZ v0.4.3 install** — not just designed on
paper. Both demo transactions below have actually been run through the full
pipeline, live, over HTTP:

```
legit payment (SBI001 -> HDFC001, ₹25,000):
  risk=0.111  decision=APPROVE

fraud-ring payment (SBI004 -> HDFC004, ₹71,524, shared device dev-RING004):
  risk=0.977  decision=REJECT
```

| File | Role |
|---|---|
| `generate_model_constants.py` | Run once (and after every retrain of the model). Reads the trained model's `lr_model.joblib` / `scaler.joblib` / `threshold.joblib` / `label_encoders.joblib`, folds the `StandardScaler` into the linear layer, computes the logit-space decision threshold, and writes `model_constants.py`. |
| `model_constants.py` | **Auto-generated — do not hand-edit.** The numeric contract: feature order, feature ownership, folded weights/bias, logit threshold, and the exact label-encoder classes for every categorical column. |
| `mpc/fraud_score.mpc` | The actual MP-SPDZ secure-computation program, templated per transaction. Compiles and runs correctly against MP-SPDZ 0.4.3. |
| `render_mpc_script.py` | Fills the gateway's 15 public feature placeholders into the `.mpc` template for one specific transaction. |
| `main.py` | `compute_risk()` — writes each party's secret inputs to `Player-Data/Input-Pn-0`, compiles with `compile.py -R 128`, runs `Scripts/ring.sh`, and parses the revealed logit back into a probability. |

#### Three design decisions worth understanding

1. **Folded weights — no MPC division for standardization.** `StandardScaler`
   (`z = (x - mean) / scale`) and the logistic-regression linear layer
   (`logit = intercept + Σ coef·z`) collapse algebraically into a single dot
   product over *raw* feature values: `folded_weight_i = coef_i / scale_i`,
   `folded_bias = intercept - Σ(coef_i·mean_i/scale_i)`. This has been
   verified twice — against 500 random points vs. scikit-learn (exact match),
   and against a live MP-SPDZ run vs. a matched plaintext computation
   (matched to within ~0.005 out of a logit of ~30 — ordinary fixed-point
   quantization, not a bug; see below).
2. **Logit-threshold comparison — no sigmoid under MPC.** Since sigmoid is
   monotonic, `sigmoid(logit) ≥ threshold ⇔ logit ≥ ln(threshold/(1−threshold))`.
   The MPC circuit only ever performs a single fixed-point comparison and
   reveals the raw logit; `sigmoid()` is applied afterward, in plaintext, in
   `compute_risk()` — with no privacy cost, since revealing the logit was
   already the point of the computation.
3. **Party slots are transaction roles, not fixed banks.** SBI and HDFC swap
   which one is "sender" (player 0) and which is "receiver" (player 1)
   depending on the transaction — the orchestrator resolves this per-request
   from each participant's own `role` field. NPCI is always player 2.

#### Two real bugs that only a real MP-SPDZ compile caught

Neither of these was guessable from documentation alone:

1. **Fixed-point range.** `sfix.set_precision(16, 31)` only covers
   `[-16384, 16384)` — too small for a ₹25,000 transaction amount. Fixed by
   widening to `set_precision(16, 48)`. Note `cfix` tracks its own precision
   separately from `sfix` — both need setting.
2. **Ring size for division.** The script's two divisions
   (`amount_vs_avg_ratio`, `txn_velocity_ratio`) require compiling with
   `compile.py -R 128` — the default prime-field compile fails outright, and
   even `-R 64` fails at runtime ("compiled for a prime field, not a ring").
   `mpc_integration/main.py` passes `-R 128` explicitly.

Also required once per machine (not a code change):
`Scripts/setup-ssl.sh 3` inside your MP-SPDZ checkout, to generate the local
player certificates `Scripts/ring.sh` expects.

#### Known precision behaviour

The revealed logit differs from an exact plaintext computation by about
0.005 (MP-SPDZ gave `29.7525` where plaintext Python gave `29.7574` on the
same inputs) — ordinary 16-bit fixed-point rounding compounding across 35
multiply-accumulates. This is never large enough to flip a threshold decision
in practice. (Max per-term rounding error ≈ `2^-16 ≈ 1.5e-5`, across 35
terms.) Turning on `sfix.round_nearest = True` made no measurable difference
to this error while costing ~6× more MPC rounds (124 → 401), so it's left
off.

### 3.6 `decision_engine/` — thresholding

`decide(risk)` is a single pure function: `risk=None` → `REVIEW` (Module 4
not available or failed); `risk ≥ 0.85` → `REJECT`; `risk ≥ 0.5` → `REVIEW`;
otherwise → `APPROVE`. Tune the two thresholds in `shared/constants.py` once
real risk scores are flowing.

### 3.7 `ai_layer/` — intentionally unfinished

`behavioral_biometrics.py` is a placeholder for a separate collaborator's
work: `compute_behavioral_score()` raises `NotImplementedError`. Don't wire
this into the orchestrator until the real signal set and output format are
agreed on.

### 3.8 `dashboard/` — optional (port 8020)

A minimal `GET /sessions` JSON passthrough to the orchestrator. No real
frontend yet.

### 3.9 `scripts/generate_mock_data.py`

Generates deterministic (seeded) mock datasets: 100 accounts each for SBI and
HDFC (~20 flagged suspicious per bank), with 8 of those suspicious accounts
deliberately sharing a device fingerprint **across both banks** — a
coordinated fraud ring that no single bank's own data would catch on its own.
NPCI's dataset is derived from the same run: suspicious accounts (including
the ring) get an elevated `failed_attempts_24h`. Re-run any time with:

```bash
python scripts/generate_mock_data.py
```

### 3.10 A structural note on "modules" vs. services

Only five (or six, with the optional dashboard) processes actually run:
gateway, SBI, HDFC, NPCI, orchestrator (+ dashboard). `decision_engine` and
`mpc_integration` are plain importable Python modules (`decide()`,
`compute_risk()`), not their own FastAPI services — worth keeping in mind if
you're writing this up as "N live microservices."

---

## 4. Linear setup guide

This is a single ordered path from a clean checkout to a fully working
system **including the real MP-SPDZ secure computation**. Steps 1–7 get the
system running in fallback mode (`risk: null` / `REVIEW` on every
transaction); steps 8–13 layer the real MPC module on top.

### Step 1 — Prerequisites

- Python 3.9+ available as `python3` / `python`.
- `pip`.
- (For Module 4 only) a Unix-like environment (Linux or macOS) to build or
  run MP-SPDZ — MP-SPDZ does not support Windows natively.

### Step 2 — Install Python dependencies

From the project root:

```bash
pip install -r requirements.txt
```

This installs `fastapi`, `uvicorn`, `httpx`, and `pydantic` — everything the
services themselves need. (`generate_model_constants.py` additionally needs
`joblib` and `numpy` — only required if you're regenerating
`model_constants.py` from a retrained model; the checked-in
`model_constants.py` already works out of the box.)

### Step 3 — Generate mock data (if you want a fresh dataset)

The repo ships with pre-generated mock data already in place
(`participants/{sbi,hdfc,npci}/mock_data.json`,
`gateway/{merchant_categories,device_history}.json`), so this step is
optional. To regenerate:

```bash
python scripts/generate_mock_data.py
```

This is deterministic — the same account IDs are always suspicious and the
same fraud-ring devices line up across banks every time you run it.

### Step 4 — Start the participant nodes

Each must be reachable before the orchestrator and gateway come up. Open
three terminals (or run them backgrounded):

```bash
python participants/sbi/main.py     # port 8001
python participants/hdfc/main.py    # port 8002
python participants/npci/main.py    # port 8003
```

### Step 5 — Start the orchestrator

```bash
python orchestrator/main.py         # port 8010
```

### Step 6 — Start the gateway

```bash
python gateway/main.py              # port 8000
```

### Step 7 — (Optional) start the dashboard

```bash
python dashboard/main.py            # port 8020
```

At this point you have a fully working pipeline that runs end-to-end but
always returns `risk: null` and `decision: REVIEW`, since Module 4 isn't
configured yet. Verify it:

```bash
curl -X POST http://localhost:8000/payment \
  -H "Content-Type: application/json" \
  -d '{"from_account":"SBI001","to_account":"HDFC001","amount":50000,"timestamp":"2026-07-11T10:00:00Z","device_id":"dev123","merchant":"Amazon"}'
```

You can inspect exactly what each participant computed for that transaction:

```bash
curl http://localhost:8010/session/<session_id>
```

---

### Step 8 — Get MP-SPDZ onto your machine

Either download a release binary or build from source:
[https://github.com/data61/MP-SPDZ](https://github.com/data61/MP-SPDZ). This
integration was verified against **MP-SPDZ v0.4.3** — use that version if you
want to reproduce the exact numbers quoted above; other versions may need
minor adjustments (see the "if something doesn't compile" note in Step 13).

### Step 9 — One-time per-machine MP-SPDZ setup

Inside your MP-SPDZ checkout, generate the local player certificates that
`Scripts/ring.sh` needs:

```bash
cd $MPSPDZ_HOME
Scripts/setup-ssl.sh 3
```

### Step 10 — Point the project at your MP-SPDZ checkout

```bash
export MPSPDZ_HOME=/path/to/your/MP-SPDZ
```

Do this in every terminal where you'll run `orchestrator/main.py` (the
orchestrator is the process that actually shells out to MP-SPDZ via
`mpc_integration/main.py`).

### Step 11 — (Re-)generate the model constants (only if retraining)

The checked-in `mpc_integration/model_constants.py` is already generated and
ready to use — **skip this step unless you've retrained the underlying
model**. If you have:

```bash
export AI_ARTIFACTS_DIR=/path/to/your/model/artifacts   # containing lr_model.joblib, scaler.joblib, threshold.joblib, label_encoders.joblib
python mpc_integration/generate_model_constants.py
```

This re-derives the folded weights/bias, the logit threshold, and the
label-encoder classes, and overwrites `model_constants.py`. It runs a
built-in sanity check (500 random points compared against scikit-learn's own
predictions) and will refuse to write the file if the folded math doesn't
reproduce the trained model's decisions exactly.

### Step 12 — Restart the full pipeline with MPC enabled

With `MPSPDZ_HOME` exported in the same shell, restart the services from
Steps 4–6 (order still matters: participants → orchestrator → gateway).
Module 4 now runs for real instead of falling back to `REVIEW` on every
transaction.

### Step 13 — Verify the real secure computation

Run the two reference transactions and confirm you get real, non-null risk
scores:

**A legitimate-looking payment**, using an account's own known device:

```bash
curl -X POST http://localhost:8000/payment -H "Content-Type: application/json" -d \
  '{"from_account":"SBI001","to_account":"HDFC001","amount":25000,"timestamp":"2026-07-11T10:00:00Z","device_id":"dev-589933","merchant":"Amazon"}'
```

Expect approximately `risk≈0.111`, `decision=APPROVE`.

**A fraud-ring payment** — both accounts are individually flagged suspicious
by their own bank, and both were seen on the same device:

```bash
curl -X POST http://localhost:8000/payment -H "Content-Type: application/json" -d \
  '{"from_account":"SBI004","to_account":"HDFC004","amount":71524,"timestamp":"2026-07-11T10:05:00Z","device_id":"dev-RING004","merchant":"Unknown Merchant"}'
```

Expect approximately `risk≈0.977`, `decision=REJECT`.

Then inspect what each bank actually computed for either session:

```bash
curl http://localhost:8010/session/<session_id>
```

For the fraud-ring request, `SBI` and `HDFC` will each independently report
`flagged_suspicious: true` and `device_match: 1` in their own `features`
block — computed purely from their own account records, with neither bank
ever seeing the other's data. `NPCI` (not a party to this transfer, just the
routing layer) reports its own `failed_attempts_24h` signal independently.
Note that `flagged_suspicious` and `device_match` are informational only —
they are not part of the MPC model's input set, so they never affect the
actual risk score.

**If something doesn't compile** on a different MP-SPDZ version, this
standalone check is much faster than restarting the whole pipeline:

```bash
cd $MPSPDZ_HOME
python3 -c "
import sys; sys.path.insert(0, '/path/to/this/project')
from mpc_integration.render_mpc_script import render
gw = {n: 0.0 for n in ['hour','day_of_week','is_weekend','is_night','log_amount',
  'is_large_txn','is_round_amount','is_new_device','device_change_30d',
  'device_change_risk','foreign_ip','sender_bank','receiver_bank',
  'merchant_category','ip_country']}
open('Programs/Source/fraud_score.mpc','w').write(render(gw, amount=1000))
"
python3 compile.py -R 128 fraud_score
```

---

## 5. Quick troubleshooting checklist

| Symptom | Likely cause |
|---|---|
| Every transaction returns `risk: null` / `REVIEW` | `MPSPDZ_HOME` isn't set (or set in a different shell than the orchestrator is running in), or doesn't point to a valid MP-SPDZ checkout |
| Gateway returns `502` immediately | One of SBI/HDFC/NPCI isn't up yet, or isn't reachable on its expected port |
| Orchestrator raises "no participant reported role(s)" | A participant's `mock_data.json` doesn't contain the account in this transaction, so it can't resolve sender/receiver/npci role |
| MP-SPDZ compile fails on division / ring errors | Missing `-R 128` compile flag, or `Scripts/setup-ssl.sh 3` was never run for this machine |
| `sfix` overflow / wildly wrong logit | Precision set too low — must be `sfix.set_precision(16, 48)` and `cfix.set_precision(16, 48)`, both set |

---

## 6. Scope notes carried over from the original design

- **`ai_layer/behavioral_biometrics.py`** is an intentionally empty interface
  for a separate collaborator's work. Don't wire it into the orchestrator
  until the real signal set is finalized.
- **`decision_engine` and `mpc_integration`** are plain importable Python
  modules, not standalone services — the actual running process count is
  gateway + 3 participants + orchestrator (+ optional dashboard): five or six
  processes, not eight.
