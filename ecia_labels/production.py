"""Print-run helpers for logistic labels.

A logistic shipment carries one or more PO line items. Each item has a total
quantity and an optional master-carton quantity; if the master quantity is
given the item is split into full cartons plus a remainder carton, otherwise
the item is a single carton holding the whole quantity. Every resulting label
gets a unique package ID, and (optionally) a per-item Package Count "n/total".

Package-ID determinism: IDs are generated from a per-item seed combining the
base seed (customer_po or an explicit override), the PO line, the supplier part
number and an optional po_split counter. So a given line reproduces the same
IDs on re-run, different lines never share a sequence, and bumping po_split
re-rolls a line that was re-split across shipments. Uniqueness is also enforced
globally across the whole run.
"""
from __future__ import annotations

import csv
import io
import random
import string

PACKAGE_ID_ALPHABET = string.ascii_uppercase + string.digits  # A-Z 0-9
PACKAGE_ID_LENGTH = 12


def carton_breakdown(total_quantity: int, master_carton_quantity: int) -> list[int]:
    """Per-carton unit counts: full master cartons plus a remainder carton."""
    if total_quantity <= 0:
        raise ValueError("quantity must be a positive integer")
    if master_carton_quantity <= 0:
        raise ValueError("master_carton_quantity must be a positive integer")
    full, remainder = divmod(total_quantity, master_carton_quantity)
    quantities = [master_carton_quantity] * full
    if remainder:
        quantities.append(remainder)
    return quantities


def generate_package_id(rng: random.Random) -> str:
    return "".join(rng.choice(PACKAGE_ID_ALPHABET) for _ in range(PACKAGE_ID_LENGTH))


def unique_package_ids(count: int, rng: random.Random,
                       used: set | None = None) -> list[str]:
    """Return ``count`` package IDs not already in ``used`` (updates ``used``)."""
    used = used if used is not None else set()
    out: list[str] = []
    while len(out) < count:
        pid = generate_package_id(rng)
        if pid in used:
            continue
        used.add(pid)
        out.append(pid)
    return out


def seed_for_item(base_seed, customer_po_line, supplier_part_number, po_split):
    """Combine the base seed with per-item identifiers.

    Returns None (-> system randomness) when there is no base seed.
    """
    if base_seed is None:
        return None
    return "|".join([
        str(base_seed),
        str(customer_po_line or ""),
        str(supplier_part_number or ""),
        "" if po_split is None else str(po_split),
    ])


def expand_shipment(shipment: dict, items: list[dict], base_seed,
                    package_count: bool = False) -> list[dict]:
    """Expand a shipment + its items into one field dict per label.

    With ``package_count`` the (13Q) value is numbered across the whole shipment
    (1/total .. total/total), since the receiver tracks total packages per
    shipment rather than per line item.
    """
    used: set[str] = set()
    labels: list[dict] = []

    # First pass: per-item carton quantities, so we know the shipment total.
    item_cartons: list[list[int]] = []
    for item in items:
        total = int(item["quantity"])
        master = item.get("master_carton_quantity")
        item_cartons.append(
            carton_breakdown(total, int(master)) if master else [total])
    grand_total = sum(len(c) for c in item_cartons)

    seq = 0
    for item, cartons in zip(items, item_cartons):
        po_split = item.get("po_split", shipment.get("po_split"))
        seed = seed_for_item(base_seed, item.get("customer_po_line"),
                             item.get("supplier_part_number"), po_split)
        rng = random.Random(seed)

        master = item.get("master_carton_quantity")
        if master:
            pids = unique_package_ids(len(cartons), rng, used)
        else:
            supplied = item.get("package_id")
            if supplied:
                pids = [supplied]
                used.add(supplied)
            else:
                pids = unique_package_ids(1, rng, used)

        for qty, pid in zip(cartons, pids):
            seq += 1
            lf: dict = {}
            for k in ("ship_from", "ship_to", "customer_po"):
                if k in shipment:
                    lf[k] = shipment[k]
            for k in shipment:                       # carry shipment DI overrides
                if k.endswith("_di"):
                    lf[k] = shipment[k]
            for k, v in item.items():                # item label fields + DI overrides
                if k in ("master_carton_quantity", "po_split", "quantity",
                         "package_id"):
                    continue
                lf[k] = v
            lf["quantity"] = str(qty)
            lf["package_id"] = pid
            if package_count:
                lf["package_count"] = f"{seq}/{grand_total}"
            labels.append(lf)

    return labels


def tracking_csv(labels: list[dict], include_package_count: bool = False) -> str:
    """Build the tracking CSV, one row per label."""
    header = ["Package ID", "PO Number", "PO Line", "Supplier PN", "Quantity"]
    if include_package_count:
        header.append("Package Count")
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(header)
    for f in labels:
        row = [
            f.get("package_id", ""),
            f.get("customer_po", ""),
            f.get("customer_po_line", ""),
            f.get("supplier_part_number", ""),
            f.get("quantity", ""),
        ]
        if include_package_count:
            row.append(f.get("package_count", ""))
        writer.writerow(row)
    return buf.getvalue()
