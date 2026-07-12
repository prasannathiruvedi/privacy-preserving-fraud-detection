# ============================================================
# mpc/prepare_mpc_data.py
# Prepares UPI transaction data for MP-SPDZ input.
#
# MP-SPDZ reads data from:
#   Player-Data/Input-P0-0       (text format)
#   Player-Data/Input-Binary-P0-0 (binary format)
#
# Run BEFORE compiling the .mpc program:
#   cd AI_MODEL
#   python mpc/prepare_mpc_data.py
# ============================================================

import sys
import os
import struct
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from data.generator import UPIDataGenerator
from features.engineer import FeatureEngineer
from sklearn.model_selection import train_test_split

PLAYER_DATA_DIR = Path(__file__).parent / "Player-Data"
PLAYER_DATA_DIR.mkdir(exist_ok=True)


def prepare():
    print("[prepare_mpc_data] Generating UPI dataset...")
    gen = UPIDataGenerator(n=10000, fraud_ratio=0.05)
    df  = gen.generate()

    print("[prepare_mpc_data] Engineering features...")
    fe = FeatureEngineer()
    X, feature_cols = fe.transform(df, fit=True)
    y = df["is_fraud"].values

    # Normalize to [0,1] — required for MPC fixed-point arithmetic
    X_min = X.min(axis=0)
    X_max = X.max(axis=0)
    X_range = X_max - X_min
    X_range[X_range == 0] = 1
    X_normalized = (X - X_min) / X_range

    X_train, X_test, y_train, y_test = train_test_split(
        X_normalized, y, test_size=0.2, stratify=y, random_state=42
    )

    print(f"[prepare_mpc_data] Train={len(X_train)} | Test={len(X_test)} | Features={X_train.shape[1]}")

    # ── Write text format (whitespace-separated) ──────────────
    # MP-SPDZ reads from Player-Data/Input-P0-0
    txt_path = PLAYER_DATA_DIR / "Input-P0-0"
    with open(txt_path, "w") as f:
        # Write labels first, then samples (as per MP-SPDZ convention)
        for label in y_train:
            f.write(f"{int(label)}\n")
        for row in X_train:
            f.write(" ".join(f"{v:.8f}" for v in row) + "\n")
        for label in y_test:
            f.write(f"{int(label)}\n")
        for row in X_test:
            f.write(" ".join(f"{v:.8f}" for v in row) + "\n")

    print(f"[prepare_mpc_data] ✅ Text data  → {txt_path}")

    # ── Write binary format (single-precision float) ──────────
    # MP-SPDZ reads from Player-Data/Input-Binary-P0-0
    bin_path = PLAYER_DATA_DIR / "Input-Binary-P0-0"
    with open(bin_path, "wb") as f:
        # Write as float32 (single-precision) little-endian
        for label in y_train:
            f.write(struct.pack("<f", float(label)))
        for row in X_train:
            for v in row:
                f.write(struct.pack("<f", float(v)))
        for label in y_test:
            f.write(struct.pack("<f", float(label)))
        for row in X_test:
            for v in row:
                f.write(struct.pack("<f", float(v)))

    print(f"[prepare_mpc_data] ✅ Binary data → {bin_path}")

    # ── Save metadata for MPC program ─────────────────────────
    meta_path = PLAYER_DATA_DIR / "mpc_metadata.txt"
    with open(meta_path, "w") as f:
        f.write(f"n_train={len(X_train)}\n")
        f.write(f"n_test={len(X_test)}\n")
        f.write(f"n_features={X_train.shape[1]}\n")
        f.write(f"feature_cols={','.join(feature_cols)}\n")

    print(f"[prepare_mpc_data] ✅ Metadata    → {meta_path}")
    print(f"[prepare_mpc_data] Done. Now run the MPC program:")
    print(f"   Scripts/compile-run.py -E ring upi_fraud_logistic")


if __name__ == "__main__":
    prepare()