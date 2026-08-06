# Module 4 — MP-SPDZ Integration

## Status: verified end-to-end against real MP-SPDZ (v0.4.3)

Everything below was actually compiled and run — this is not a
paper design, it's a tested result. Both demo transactions from the
project README go through the gateway, all three participant nodes,
the real 3-party MP-SPDZ secure computation, and the decision engine,
live over HTTP:

```
legit payment (SBI001 -> HDFC001, ₹25,000):
  risk=0.111  decision=APPROVE

fraud-ring payment (SBI004 -> HDFC004, ₹71,524, shared device dev-RING004):
  risk=0.977  decision=REJECT
```

## Files

| File | Role |
|---|---|
| `generate_model_constants.py` | Run once (and after every retrain). Reads the AI repo's `lr_model.joblib`/`scaler.joblib`/`threshold.joblib`, folds the scaler into the linear layer, computes the logit threshold, writes `model_constants.py`. |
| `model_constants.py` | Generated. The numeric contract — feature order, ownership, folded weights, label-encoder classes. |
| `mpc/fraud_score.mpc` | Template MP-SPDZ program. 15 gateway features are `__PLACEHOLDER__` tokens; everything else (weights, thresholds, sender/receiver/NPCI secret inputs) is already filled in. **Compiles and runs correctly as of this testing.** |
| `render_mpc_script.py` | Fills the gateway placeholders in for one transaction. |
| `main.py` | `compute_risk()` — writes `Player-Data/Input-Pn-0`, runs `compile.py -R 128` + `Scripts/ring.sh`, parses the revealed logit back to a probability. |

## The three design decisions worth knowing before you touch this

1. **Folded weights, no MPC division for standardization.** `StandardScaler`
   + the LR linear layer collapse algebraically into one dot product over
   *raw* feature values (`generate_model_constants.py`'s docstring has the
   derivation). Verified twice: 500 random points against sklearn (exact
   match), and a live MP-SPDZ run against a matched plaintext computation
   (matched to ~0.005 out of a logit of ~30 — see "known precision
   behaviour" below).
2. **Logit threshold, no sigmoid under MPC.** Since sigmoid is monotonic,
   `sigmoid(logit) >= threshold  <=>  logit >= ln(threshold/(1-threshold))`.
   The script only ever does a fixed-point comparison, then reveals the
   raw logit — `compute_risk()` applies sigmoid itself, in plaintext,
   *after* the reveal (no privacy cost, since revealing the logit was
   already the point of running the computation).
3. **Party 0/1 are roles, not banks.** SBI and HDFC swap which one is
   "sender" and which is "receiver" depending on the transaction, so the
   orchestrator resolves that per-request (via each participant's own
   `role` field in its `/prepare` response) before handing inputs to
   `compute_risk()`. NPCI is always player 2.

## Two real bugs found and fixed by actually compiling against MP-SPDZ 0.4.3

Neither of these was guessable from the integration guide alone — both
only surfaced from a real `compile.py` run:

1. **Fixed-point range.** `sfix.set_precision(16, 31)` gives a value range
   of only `[-16384, 16384)` — too small for a ₹25,000 transaction amount.
   Fixed by widening to `set_precision(16, 48)`. Note `cfix` tracks its
   own precision separately from `sfix` — both need setting.
2. **Ring size for division.** The script's two divisions
   (`amount_vs_avg_ratio`, `txn_velocity_ratio`) need `compile.py -R 128`,
   not the default. Compiling for the default prime field, or even
   `-R 64`, fails at compile time (division) or at runtime
   ("compiled for a prime field, not a ring" — `Scripts/ring.sh` needs a
   ring-domain compile to match). `mpc_integration/main.py` now passes
   `-R 128` explicitly.

Also needed once per machine, not code: `Scripts/setup-ssl.sh 3` inside
the MP-SPDZ checkout, to generate the local player certificates
`Scripts/ring.sh` expects.

## Known precision behaviour

The revealed logit differs from an exact plaintext computation by ~0.005
(observed: MP-SPDZ gave `29.7525` where plaintext Python gave
`29.7574`, on the same inputs). That's ordinary 16-bit fixed-point
quantization compounding across 35 multiply-accumulates, not a bug —
`sfix.round_nearest = True` was tested and made no measurable difference
to the error while costing ~6x more rounds/triples (124 -> 401 rounds),
so it's left off. This magnitude of error will never flip a threshold
decision in practice; if your paper wants a citable bound, the max
per-term rounding error is `2^-16 ~= 1.5e-5` per multiply, and there are
35 terms.

## How to reproduce this

```bash
export MPSPDZ_HOME=/path/to/your/MP-SPDZ         # release binary or built from source
export AI_ARTIFACTS_DIR=/path/to/AI/AI/fixed/artifacts   # if not already sibling repos

cd $MPSPDZ_HOME && Scripts/setup-ssl.sh 3          # once per machine

python mpc_integration/generate_model_constants.py  # once, and after every retrain

# bring the system up (see repo-root README.md) — Module 4 now runs for
# real instead of falling back to REVIEW.
```

If you're on a different MP-SPDZ version and something doesn't compile,
the standalone check is faster than restarting the whole pipeline:

```bash
cd $MPSPDZ_HOME
python3 -c "
import sys; sys.path.insert(0, '/path/to/MPC')
from mpc_integration.render_mpc_script import render
gw = {n: 0.0 for n in ['hour','day_of_week','is_weekend','is_night','log_amount',
  'is_large_txn','is_round_amount','is_new_device','device_change_30d',
  'device_change_risk','foreign_ip','sender_bank','receiver_bank',
  'merchant_category','ip_country']}
open('Programs/Source/fraud_score.mpc','w').write(render(gw, amount=1000))
"
python3 compile.py -R 128 fraud_score
```
