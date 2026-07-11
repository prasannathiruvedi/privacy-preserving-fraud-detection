# Fraud MPC System — Service Scaffold

Service-oriented layout matching the architecture doc: gateway, participant
nodes, orchestrator, decision engine, and a stub for MPC + the AI layer.

## Layout

```
shared/             # Pydantic models, constants, contracts, helpers — everyone imports from here
gateway/             # Module 1 — Payment Gateway (port 8000)
participants/        # Module 2 — SBI (8001), HDFC (8002), NPCI (8003)
orchestrator/         # Module 3 — Fraud Orchestrator (port 8010)
mpc_integration/      # Module 4 — EMPTY STUB, raises NotImplementedError
decision_engine/      # Module 5 — thresholding logic, real
ai_layer/             # AI / behavioral biometrics — EMPTY STUB for collaborator
dashboard/            # Module 6 — minimal JSON dashboard (port 8020), optional
```

## Setup

```bash
pip install -r requirements.txt
```

## Run (5 terminals, in this order)

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

Right now this will run end to end and return a decision — but with
`risk: null` and decision `REVIEW`, because Module 4 (MPC) is a stub. That's
intentional: it lets you exercise the whole gateway -> participants ->
orchestrator -> decision path before MP-SPDZ is wired in.

## What's stubbed on purpose

- **`mpc_integration/main.py`** — `compute_risk()` raises `NotImplementedError`.
  The orchestrator catches this and falls back to `risk=None` / `REVIEW`, so
  nothing downstream breaks while you build the real MP-SPDZ layer.
- **`ai_layer/behavioral_biometrics.py`** — `compute_behavioral_score()` raises
  `NotImplementedError`. Interface is a placeholder — nail down the real
  signal set with your collaborator before wiring it into the orchestrator.

## Mock data

`participants/{sbi,hdfc,npci}/mock_data.json` are now populated: 100 accounts
per bank, 20 flagged suspicious, 8 of which share a device fingerprint across
ALL THREE banks (`dev-RING004`, `dev-RING015`, etc.) — a coordinated fraud
ring that no single institution's local data would catch on its own. That's
the whole point of the MPC layer, so it's worth demoing explicitly.

Regenerate anytime with:
```bash
python scripts/generate_mock_data.py
```
It's deterministic (seeded), so the same account IDs are always suspicious.

### Demo requests

Legit-looking payment:
```bash
curl -X POST http://localhost:8000/payment -H "Content-Type: application/json" -d \
  '{"from_account":"SBI001","to_account":"HDFC001","amount":25000,"timestamp":"2026-07-11T10:00:00Z","device_id":"dev-589933","merchant":"Amazon"}'
```

Fraud-ring payment (both sides flagged suspicious, matching device):
```bash
curl -X POST http://localhost:8000/payment -H "Content-Type: application/json" -d \
  '{"from_account":"SBI004","to_account":"HDFC004","amount":71524,"timestamp":"2026-07-11T10:05:00Z","device_id":"dev-RING004","merchant":"Unknown Merchant"}'
```

Then check what each bank actually computed for that session:
```bash
curl http://localhost:8010/session/<session_id>
```
You'll see `SBI` and `HDFC` both return `flagged_suspicious: true` with a
`device_match`, while `NPCI` (routing node, not a party to this transfer)
comes back unmatched — that's expected, not a bug.

## Note on Modules 4/5

The architecture doc treats MPC Integration (4) and Decision Engine (5) as
separate services from Orchestrator. This scaffold keeps Decision Engine as
a plain importable module (`decide(risk)`) rather than its own FastAPI
service, per the doc's own suggestion ("Could simply be an internal Python
module"). MPC Integration is imported the same way, not run as a separate
service — worth confirming that still matches your intent to keep 4/5 out
of the live execution path as separate microservices, since the report
should describe what's actually running.
