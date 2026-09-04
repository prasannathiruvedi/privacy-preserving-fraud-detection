import json
import os
import random

random.seed(42)

RETAIL_BANKS = ["SBI", "HDFC"]
ACCOUNTS_PER_BANK = 100
SUSPICIOUS_COUNT = 20
CROSS_BANK_RING_COUNT = 8

FIRST_NAMES = ["Aarav", "Vihaan", "Diya", "Ananya", "Kabir", "Ishaan", "Meera",
               "Rohan", "Priya", "Aditya", "Sara", "Arjun", "Neha", "Vikram", "Tara"]
CITIES = ["Mumbai", "Delhi", "Bengaluru", "Chennai", "Hyderabad", "Pune", "Kolkata", "Ahmedabad"]

def make_device_id(rng: random.Random) -> str:
    return f"dev-{rng.randint(100000, 999999)}"

def make_account(bank: str, idx: int, suspicious: bool, shared_device: str = None) -> dict:
    account_id = f"{bank}{idx:03d}"
    rng = random.Random(f"{bank}-{idx}")

    if suspicious:
        avg_amount = round(rng.uniform(500, 5000), 2)
        last_txn_amount = round(rng.uniform(30000, 95000), 2)
        account_age_days = rng.randint(1, 45)
        beneficiary_count = rng.randint(5, 15)
        txn_count_30d = rng.randint(15, 40)
        device_id = shared_device or make_device_id(rng)
    else:
        avg_amount = round(rng.uniform(2000, 60000), 2)
        last_txn_amount = round(avg_amount * rng.uniform(0.7, 1.3), 2)
        account_age_days = rng.randint(180, 3650)
        beneficiary_count = rng.randint(1, 6)
        txn_count_30d = rng.randint(1, 12)
        device_id = make_device_id(rng)

    return {
        "account_id": account_id,
        "holder_name": rng.choice(FIRST_NAMES),
        "city": rng.choice(CITIES),
        "account_age_days": account_age_days,
        "avg_amount": avg_amount,
        "last_txn_amount": last_txn_amount,
        "txn_count_30d": txn_count_30d,
        "beneficiary_count": beneficiary_count,
        "device_id": device_id,
        "suspicious": suspicious,
        "state": rng.choice([
            "Delhi", "Gujarat", "Karnataka", "MP", "Maharashtra",
            "Rajasthan", "Tamil Nadu", "Telangana", "UP", "West Bengal",
        ]),
        "txn_count_7d": max(1, round(txn_count_30d / 4)),
        "known_beneficiaries": [],
    }

def generate_retail_bank(bank: str, ring_candidate_indices: list, ring_devices: dict) -> list:
    random.seed(hash(bank) % (2**31))
    remaining_pool = [i for i in range(1, ACCOUNTS_PER_BANK + 1) if i not in ring_candidate_indices]
    extra_suspicious = random.sample(remaining_pool, SUSPICIOUS_COUNT - CROSS_BANK_RING_COUNT)
    suspicious_indices = set(extra_suspicious) | set(ring_candidate_indices)

    records = []
    for idx in range(1, ACCOUNTS_PER_BANK + 1):
        is_suspicious = idx in suspicious_indices
        shared_device = ring_devices.get(idx) if idx in ring_candidate_indices else None
        records.append(make_account(bank, idx, is_suspicious, shared_device))
    return records

def generate_npci_dataset(all_bank_records: dict, rng: random.Random) -> dict:
    failed_attempts_by_account: dict = {}
    for bank, records in all_bank_records.items():
        for record in records:
            if record["suspicious"]:
                failed_attempts_by_account[record["account_id"]] = rng.randint(3, 6)
    return failed_attempts_by_account

def main():
    ring_candidate_indices = random.sample(range(1, ACCOUNTS_PER_BANK + 1), CROSS_BANK_RING_COUNT)
    ring_devices = {idx: f"dev-RING{idx:03d}" for idx in ring_candidate_indices}

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    all_bank_records = {}
    summary = {}
    for bank in RETAIL_BANKS:
        records = generate_retail_bank(bank, ring_candidate_indices, ring_devices)
        all_bank_records[bank] = records

        out_path = os.path.join(base_dir, "participants", bank.lower(), "mock_data.json")
        with open(out_path, "w") as f:
            json.dump(records, f, indent=2)

        summary[bank] = {
            "total": len(records),
            "suspicious": sum(1 for r in records if r["suspicious"]),
            "ring_accounts": sorted(f"{bank}{i:03d}" for i in ring_candidate_indices),
        }

    npci_rng = random.Random("NPCI-failed-attempts")
    npci_data = generate_npci_dataset(all_bank_records, npci_rng)
    npci_out_path = os.path.join(base_dir, "participants", "npci", "mock_data.json")
    with open(npci_out_path, "w") as f:
        json.dump(npci_data, f, indent=2)

    print("Generated mock data:")
    for bank, s in summary.items():
        print(f"  {bank}: {s['total']} accounts, {s['suspicious']} suspicious "
              f"({s['ring_accounts']} share cross-bank ring devices)")
    print(f"  NPCI: {len(npci_data)} accounts with elevated failed_attempts_24h "
          f"(across {', '.join(RETAIL_BANKS)}, keyed by account id — not its own account set)")

if __name__ == "__main__":
    main()
