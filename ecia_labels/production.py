"""Print-run helpers for logistic labels.

Given a total quantity and a master-carton quantity, work out how many labels
to print and how many units each carton holds, mint a unique package ID per
label, and build the tracking CSV.

Example: total 3600, master 500 -> [500, 500, 500, 500, 500, 500, 500, 100]
(eight labels: seven full cartons plus a 100-unit remainder).
"""
from __future__ import annotations

import csv
import io
import random
import string

# Package ID: uppercase letters + digits, fixed length.
PACKAGE_ID_ALPHABET = string.ascii_uppercase + string.digits
PACKAGE_ID_LENGTH = 12


def carton_breakdown(total_quantity: int, master_carton_quantity: int) -> list[int]:
    """Return the per-label unit counts for a print run."""
    if total_quantity <= 0:
        raise ValueError("total_quantity must be a positive integer")
    if master_carton_quantity <= 0:
        raise ValueError("master_carton_quantity must be a positive integer")
    full, remainder = divmod(total_quantity, master_carton_quantity)
    quantities = [master_carton_quantity] * full
    if remainder:
        quantities.append(remainder)
    return quantities


def generate_package_id(rng: random.Random) -> str:
    return "".join(rng.choice(PACKAGE_ID_ALPHABET) for _ in range(PACKAGE_ID_LENGTH))


def unique_package_ids(count: int, rng: random.Random) -> list[str]:
    """Return ``count`` distinct package IDs."""
    seen: set[str] = set()
    out: list[str] = []
    while len(out) < count:
        pid = generate_package_id(rng)
        if pid not in seen:
            seen.add(pid)
            out.append(pid)
    return out


def expand_print_run(fields: dict, total_quantity: int,
                     master_carton_quantity: int, rng: random.Random) -> list[dict]:
    """Expand one logistic field set into one field set per label.

    Each returned dict is a copy of ``fields`` with ``quantity`` and a freshly
    generated, unique ``package_id`` filled in.
    """
    quantities = carton_breakdown(total_quantity, master_carton_quantity)
    pids = unique_package_ids(len(quantities), rng)
    labels = []
    for qty, pid in zip(quantities, pids):
        per = dict(fields)
        per["quantity"] = str(qty)
        per["package_id"] = pid
        labels.append(per)
    return labels


def tracking_csv(labels: list[dict]) -> str:
    """Build the tracking CSV: package ID, PO number, supplier PN, quantity."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Package ID", "PO Number", "Supplier PN", "Quantity"])
    for f in labels:
        writer.writerow([
            f.get("package_id", ""),
            f.get("customer_po", ""),
            f.get("supplier_part_number", ""),
            f.get("quantity", ""),
        ])
    return buf.getvalue()