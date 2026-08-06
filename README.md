# Fraud MPC System

A service-oriented fraud-detection pipeline for UPI-style payments: a
gateway takes in a payment, three participant banks each compute
features from data they alone hold, and a secure multi-party
computation (MP-SPDZ) combines those private features into a single
risk score — without any party seeing another party's raw data.

## Architecture

```
shared/             Pydantic models, constants, contracts, helpers — everyone imports from here
gateway/             Payment Gateway (port 8000) — entry point, computes its own owned features
participants/        SBI (8001), HDFC (8002), NPCI (8003) — each computes features from its own data
orchestrator/         Fraud Orchestrator (port 8010) — coordinates the above, calls into MPC + decision engine
mpc_integration/      Secure computation layer — real MP-SPDZ integration, or a REVIEW fallback if unconfigured
decision_engine/      Thresholding logic (risk score -> APPROVE / REVIEW / REJECT)
ai_layer/             Behavioral biometrics — placeholder interface for a separate signal source
dashboard/            Minimal JSON dashboard (port 8020), optional
scripts/              Mock data generation
```

Each of SBI, HDFC, and NPCI computes a role-specific set of features
locally and never sends its raw account data anywhere. The gateway
computes transaction/session-layer features it already sees as the
entry point. All of these get combined into a risk score inside an
MP-SPDZ secure computation — see `mpc_integration/README.md` for how
that's wired up, including the specific MP-SPDZ setup and compile
flags that were verified to work.

## Setup

```bash
pip install -r requirements.txt
```

MPC (Module 4) is optional. Without it, the system still runs
end-to-end but every transaction falls back to `risk: null` /
`REVIEW`, which keeps the rest of the pipeline testable without an
MP-SPDZ install. To enable the real secure computation:

```bash
export MPSPDZ_HOME=/path/to/your/MP-SPDZ
python mpc_integration/generate_model_constants.py
```

See `mpc_integration/README.md` for the full setup, including MP-SPDZ
version notes and the two compile-flag details that matter for this
program (fixed-point precision and ring size).

## Run

Start the participant nodes first, then the orchestrator, then the
gateway (each depends on the ones before it being reachable):

```bash
python participants/sbi/main.py
python participants/hdfc/main.py
python participants/npci/main.py
python orchestrator/main.py
python gateway/main.py
```

Optional:

```bash
python dashboard/main.py
```

## Try it

```bash
curl -X POST http://localhost:8000/payment \
  -H "Content-Type: application/json" \
  -d '{"from_account":"SBI001","to_account":"HDFC001","amount":50000,"timestamp":"2026-07-11T10:00:00Z","device_id":"dev123","merchant":"Amazon"}'
```

This runs the full pipeline and returns a decision. If `MPSPDZ_HOME`
isn't set, `risk` will be `null` and the decision will be `REVIEW` —
that's the expected fallback, not an error.

You can inspect what each participant actually computed for a given
transaction (useful for confirming the MPC inputs look right, or for
a demo) via:

```bash
curl http://localhost:8010/session/<session_id>
```

## Mock data

`participants/{sbi,hdfc,npci}/mock_data.json` and
`gateway/{merchant_categories,device_history}.json` are pre-populated:
100 accounts per bank, ~20 flagged suspicious per bank, with a subset
sharing a device fingerprint across BOTH SBI and HDFC — a coordinated
fraud ring that no single bank's own data would catch. NPCI's mock
data is shaped differently from SBI/HDFC's (it's the switch/routing
node, not an account holder) — see `participants/common.py` and
`scripts/generate_mock_data.py` for the details.

Regenerate anytime with:

```bash
python scripts/generate_mock_data.py
```

It's deterministic (seeded), so the same account IDs are always
suspicious and the same ring devices line up across banks.

### Demo requests

A legitimate-looking payment, using an account's own known device:

```bash
curl -X POST http://localhost:8000/payment -H "Content-Type: application/json" -d \
  '{"from_account":"SBI001","to_account":"HDFC001","amount":25000,"timestamp":"2026-07-11T10:00:00Z","device_id":"dev-589933","merchant":"Amazon"}'
```

A fraud-ring payment — both accounts are individually flagged
suspicious by their own bank, and both were seen on the same device:

```bash
curl -X POST http://localhost:8000/payment -H "Content-Type: application/json" -d \
  '{"from_account":"SBI004","to_account":"HDFC004","amount":71524,"timestamp":"2026-07-11T10:05:00Z","device_id":"dev-RING004","merchant":"Unknown Merchant"}'
```

Then check what each bank actually computed for that session:

```bash
curl http://localhost:8010/session/<session_id>
```

For the fraud-ring request, `SBI` and `HDFC` will each independently
report `flagged_suspicious: true` and `device_match: 1` in their own
`features` — computed locally from their own account records, with
neither bank ever seeing the other's data. `NPCI` (not a party to
this transfer, just the routing layer) reports its own signal,
`failed_attempts_24h`, independently. Note that `flagged_suspicious`
and `device_match` are informational only — they aren't part of the
MPC model input set (see `mpc_integration/model_constants.py`), so
they don't affect the risk score; they exist so a session can be
inspected and explained.

## Notes on scope

- **`ai_layer/behavioral_biometrics.py`** is an intentionally empty
  interface for a separate collaborator's work — `compute_behavioral_score()`
  raises `NotImplementedError`. Nail down the real signal set before
  wiring it into the orchestrator.
- **Decision Engine and MPC Integration** are plain importable Python
  modules (`decide(risk)` / `compute_risk(...)`) rather than their own
  FastAPI services, even though they're conceptually separate modules
  in the architecture. Worth confirming that still matches your intent
  before writing anything up as "N live services," since the actual
  process list is gateway + 3 participants + orchestrator (+ optional
  dashboard) — five or six processes, not eight.
