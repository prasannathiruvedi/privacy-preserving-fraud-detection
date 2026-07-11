"""
Generates mock participant datasets for SBI, HDFC, and NPCI.

Follows the same shape as the Module 2 generator: 100 accounts per
institution, ~80 legitimate / ~20 suspicious, with a subset of the
suspicious accounts sharing correlated fraud signals ACROSS all three
banks (same device fingerprint, same recently-changed pattern) — since
the whole point of the MPC layer is to catch fraud rings that no single
institution's data would flag on its own.

Run from the project root:
    python scripts/generate_mock_data.py
"""
import json
import os
import random

random.seed(42)

BANKS = ["SBI", "HDFC", "NPCI"]
ACCOUNTS_PER_BANK = 100
SUSPICIOUS_COUNT = 20
# Of the suspicious accounts, this many are a coordinated ring that shows
# up as suspicious at the same index across ALL banks with a shared device.
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
        avg_amount = round(rng.uniform(500, 5000), 2)          # normally low-value account
        last_txn_amount = round(rng.uniform(30000, 95000), 2)   # sudden large transaction
        account_age_days = rng.randint(1, 45)                    # freshly opened
        beneficiary_count = rng.randint(5, 15)                   # many new beneficiaries added fast
        txn_count_30d = rng.randint(15, 40)                      # unusually high velocity
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
    }


def generate_bank_dataset(bank: str, ring_devices: dict) -> list:
    suspicious_indices = set(random.sample(range(1, ACCOUNTS_PER_BANK + 1), SUSPICIOUS_COUNT))
    ring_indices = set(list(suspicious_indices)[:CROSS_BANK_RING_COUNT])

    records = []
    for idx in range(1, ACCOUNTS_PER_BANK + 1):
        is_suspicious = idx in suspicious_indices
        shared_device = ring_devices.get(idx) if idx in ring_indices else None
        records.append(make_account(bank, idx, is_suspicious, shared_device))
    return records


def main():
    # Pre-assign shared device fingerprints for the cross-bank fraud ring,
    # so the SAME device_id shows up as "suspicious" at matching indices
    # across SBI, HDFC, and NPCI — that cross-institution correlation is
    # exactly what a single bank's local data can't see on its own.
    ring_candidate_indices = random.sample(range(1, ACCOUNTS_PER_BANK + 1), CROSS_BANK_RING_COUNT)
    ring_devices = {idx: f"dev-RING{idx:03d}" for idx in ring_candidate_indices}

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    summary = {}
    for bank in BANKS:
        # reset seed per bank draw of suspicious_indices so each bank has its
        # own distribution, but reuse ring_devices/ring_candidate_indices so
        # the ring accounts line up at the same indices across banks
        random.seed(hash(bank) % (2**31))
        remaining_pool = [i for i in range(1, ACCOUNTS_PER_BANK + 1) if i not in ring_candidate_indices]
        extra_suspicious = random.sample(remaining_pool, SUSPICIOUS_COUNT - CROSS_BANK_RING_COUNT)
        # ring indices are always suspicious and always included in the count
        suspicious_indices = set(extra_suspicious) | set(ring_candidate_indices)

        records = []
        for idx in range(1, ACCOUNTS_PER_BANK + 1):
            is_suspicious = idx in suspicious_indices
            shared_device = ring_devices.get(idx) if idx in ring_candidate_indices else None
            records.append(make_account(bank, idx, is_suspicious, shared_device))

        out_path = os.path.join(base_dir, "participants", bank.lower(), "mock_data.json")
        with open(out_path, "w") as f:
            json.dump(records, f, indent=2)

        summary[bank] = {
            "total": len(records),
            "suspicious": sum(1 for r in records if r["suspicious"]),
            "ring_accounts": sorted(f"{bank}{i:03d}" for i in ring_candidate_indices),
        }

    print("Generated mock data:")
    for bank, s in summary.items():
        print(f"  {bank}: {s['total']} accounts, {s['suspicious']} suspicious "
              f"({s['ring_accounts']} share cross-bank ring devices)")


if __name__ == "__main__":
    main()
