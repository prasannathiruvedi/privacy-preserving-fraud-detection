# UPI Fraud Detection Service

Modular, production-ready ML service using Logistic Regression.

## Project Structure

```
upi_fraud_service/
├── config.py              ← All configuration, rules, allowed values
├── requirements.txt
│
├── data/
│   └── generator.py       ← Synthetic data (training only)
│
├── features/
│   └── engineer.py        ← Feature engineering (model-agnostic)
│
├── model/
│   ├── train.py           ← Run once to train + save artifacts
│   └── predictor.py       ← Load artifacts + run inference
│
├── api/
│   ├── service.py         ← Fraud service layer (orchestration)
│   └── main.py            ← FastAPI endpoints + input validation
│
├── utils/
│   └── explanation.py     ← Human-readable explanations
│
└── artifacts/             ← Auto-created after training
    ├── lr_model.joblib
    ├── scaler.joblib
    ├── label_encoders.joblib
    └── threshold.joblib
```

## How to Run

### Step 1 — Install dependencies
```bash
pip install -r requirements.txt
```

### Step 2 — Train model (run ONCE)
```bash
python model/train.py
```
This generates `artifacts/` folder with saved model, scaler, encoders, threshold.

### Step 3 — Start FastAPI server
```bash
python api/main.py
# or
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

### Step 4 — Call the API

**Single prediction:**
```bash
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{
    "amount": 75000,
    "sender_upi_app": "GPay",
    "receiver_upi_app": "Paytm",
    "sender_bank": "SBI",
    "receiver_bank": "BOB",
    "merchant_category": "Transfer",
    "sender_state": "Delhi",
    "receiver_state": "UP",
    "ip_country": "Foreign",
    "sender_account_age_days": 5,
    "receiver_account_age_days": 2,
    "sender_txn_count_7d": 0,
    "receiver_txn_count_7d": 0,
    "sender_avg_amount_30d": 300,
    "is_new_device": 1,
    "is_new_beneficiary": 1,
    "failed_attempts_24h": 7,
    "device_change_30d": 3
  }'
```

**Health check:**
```bash
curl http://localhost:8000/health
```

**API Docs (auto-generated):**
```
http://localhost:8000/docs
```

## Architecture Flow

```
Training (offline):
  generator.py → engineer.py → train.py → artifacts/

Runtime (API):
  POST /predict
      ↓
  Input Validation (Pydantic)
      ↓
  FraudService (service.py)
      ↓
  FeatureEngineer (engineer.py)
      ↓
  FraudPredictor (predictor.py)
      ↓
  Logistic Regression Model
      ↓
  ExplanationEngine (explanation.py)
      ↓
  JSON Response
```

## Input Validation

All 18 fields are required. Missing fields return HTTP 422 with a descriptive error.
No silent default injection.

| Field | Type | Allowed Values |
|---|---|---|
| amount | float > 0 | Any positive number |
| sender_upi_app | string | GPay, PhonePe, Paytm, BHIM, Amazon Pay, WhatsApp Pay |
| receiver_upi_app | string | same |
| sender_bank | string | SBI, HDFC, ICICI, Axis, Kotak, PNB, Canara, BOB |
| receiver_bank | string | same |
| merchant_category | string | Grocery, Food, Travel, Shopping, Bill, Transfer, Entertainment, Medical |
| sender_state | string | Maharashtra, Delhi, Karnataka, Tamil Nadu, West Bengal, Telangana, Gujarat, Rajasthan, UP, MP |
| receiver_state | string | same |
| ip_country | string | India, Foreign |
| sender_account_age_days | float ≥ 0 | days |
| receiver_account_age_days | float ≥ 0 | days |
| sender_txn_count_7d | float ≥ 0 | count |
| receiver_txn_count_7d | float ≥ 0 | count |
| sender_avg_amount_30d | float ≥ 0 | ₹ |
| is_new_device | 0 or 1 | 0=No, 1=Yes |
| is_new_beneficiary | 0 or 1 | 0=No, 1=Yes |
| failed_attempts_24h | float ≥ 0 | count |
| device_change_30d | float ≥ 0 | count |