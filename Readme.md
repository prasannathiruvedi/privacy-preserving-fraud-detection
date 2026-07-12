# AI_MODEL — UPI Fraud Detection Service

Modular ML service using **Logistic Regression** + **MP-SPDZ MPC**.

---

## Project Structure

```
AI_MODEL/
├── config.py                        ← ALL config, rules, allowed values
├── requirements.txt
├── README.md
│
├── data/
│   ├── __init__.py
│   └── generator.py                 ← Synthetic UPI data (training only)
│
├── features/
│   ├── __init__.py
│   └── engineer.py                  ← Feature engineering (model-agnostic)
│
├── model/
│   ├── __init__.py
│   ├── train.py                     ← Train LR + save artifacts (run once)
│   └── predictor.py                 ← Load artifacts + inference only
│
├── api/
│   ├── __init__.py
│   ├── service.py                   ← Orchestration layer
│   └── main.py                      ← FastAPI endpoints + validation
│
├── utils/
│   ├── __init__.py
│   └── explanation.py               ← Human-readable explanations
│
├── mpc/
│   ├── prepare_mpc_data.py          ← Export UPI data for MP-SPDZ
│   ├── Player-Data/                 ← MP-SPDZ reads input from here
│   └── Programs/Source/
│       └── upi_fraud_logistic.mpc   ← MP-SPDZ MPC program (SGDLogistic)
│
└── artifacts/                       ← Auto-created after training
    ├── lr_model.joblib
    ├── scaler.joblib
    ├── label_encoders.joblib
    └── threshold.joblib
```

---

## Step-by-Step Run Guide

### Part A — Standard LR API

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Train model (run ONCE — saves artifacts)
cd AI_MODEL
python model/train.py

# 3. Start FastAPI server
python api/main.py

# 4. API is live at:
#    http://localhost:8000/docs      ← Swagger UI
#    POST http://localhost:8000/predict
#    POST http://localhost:8000/batch
#    GET  http://localhost:8000/health
```

### Part B — MP-SPDZ MPC Integration

Based exactly on:
https://mp-spdz.readthedocs.io/en/latest/machine-learning.html

```bash
# 1. Install MP-SPDZ (Linux/macOS)
wget https://github.com/data61/MP-SPDZ/releases/latest/download/mp-spdz-*.tar.xz
tar xf mp-spdz-*.tar.xz
cd mp-spdz-*/

# 2. Prepare UPI data for MPC input
cd /path/to/AI_MODEL
python mpc/prepare_mpc_data.py
# Creates: mpc/Player-Data/Input-P0-0
# Creates: mpc/Player-Data/Input-Binary-P0-0

# 3. Copy MPC program into MP-SPDZ
cp mpc/Programs/Source/upi_fraud_logistic.mpc /path/to/mp-spdz/Programs/Source/

# 4. Copy Player-Data into MP-SPDZ
cp mpc/Player-Data/* /path/to/mp-spdz/Player-Data/

# 5. Run MPC training (standard)
cd /path/to/mp-spdz
Scripts/compile-run.py -E ring upi_fraud_logistic

# 6. Run with approximate sigmoid (faster)
Scripts/compile-emulate.py upi_fraud_logistic approx

# 7. Run with accuracy testing after each epoch
Scripts/compile-emulate.py upi_fraud_logistic testing
```

---

## API Usage

### Single Transaction — POST /predict

```bash
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{
    "amount": 99000,
    "sender_upi_app": "GPay",
    "receiver_upi_app": "Paytm",
    "sender_bank": "SBI",
    "receiver_bank": "Kotak",
    "merchant_category": "Transfer",
    "sender_state": "Delhi",
    "receiver_state": "Maharashtra",
    "ip_country": "Foreign",
    "sender_account_age_days": 3,
    "receiver_account_age_days": 2,
    "sender_txn_count_7d": 0,
    "receiver_txn_count_7d": 0,
    "sender_avg_amount_30d": 200,
    "is_new_device": 1,
    "is_new_beneficiary": 1,
    "failed_attempts_24h": 8,
    "device_change_30d": 5
  }'
```

### Response

```json
{
  "status": "success",
  "result": {
    "fraud_score": 100.0,
    "risk_level": "CRITICAL",
    "action": "BLOCK",
    "emoji": "🚫",
    "top_risk_factors": ["is_new_receiver_acc", "amount_vs_avg_ratio", ...],
    "feature_risks": {
      "Amount Risk": 100,
      "Account Age Risk": 99,
      "Device Risk": 100,
      "Velocity Risk": 0,
      "Geography Risk": 100,
      "Attempt Risk": 100
    },
    "explanation": "Fraud score 100.0/100 — CRITICAL risk. Key signals: ...",
    "timestamp": "2024-01-01 12:00:00"
  }
}
```

---

## Architecture Flow

```
Training (offline, run once):
  data/generator.py
       ↓
  features/engineer.py
       ↓
  model/train.py  ──────────────────────→  artifacts/
                  ──→ mpc/Player-Data/   (for MP-SPDZ)

Runtime (API, always running):
  POST /predict
       ↓
  Input Validation (Pydantic — rejects missing fields)
       ↓
  api/service.py  (FraudService)
       ↓
  features/engineer.py  (FeatureEngineer)
       ↓
  model/predictor.py  (FraudPredictor → LR Model)
       ↓
  utils/explanation.py  (ExplanationEngine)
       ↓
  JSON Response

MPC (secure training with MP-SPDZ):
  mpc/prepare_mpc_data.py
       ↓
  Player-Data/Input-P0-0
       ↓
  upi_fraud_logistic.mpc
       ↓
  ml.SGDLogistic(20, 2, program)  ← exactly per MP-SPDZ docs
       ↓
  log.fit(X_train, y_train)
       ↓
  log.predict_proba(X_test).reveal()
```

---

## MP-SPDZ Integration Notes

The MPC program uses exactly the API from the official docs:

| Docs | This project |
|---|---|
| `ml.SGDLogistic(20, 2, program)` | ✅ Used as-is |
| `log.fit(X_train, y_train)` | ✅ Used as-is |
| `log.fit_with_testing(...)` | ✅ With `testing` arg |
| `log.predict(X_test)` | ✅ Used as-is |
| `log.predict_proba(X_test)` | ✅ Used as-is |
| `sfix.input_tensor_via(0, X)` | ✅ Used as-is |
| `sint.input_tensor_via(0, y)` | ✅ Used as-is |
| `var.write_to_file()` | ✅ Model saved |

## Input Validation

All 18 fields are required. Missing any field returns HTTP 422:

```json
{
  "detail": [
    {
      "loc": ["body", "receiver_bank"],
      "msg": "field required",
      "type": "missing"
    }
  ]
}
```