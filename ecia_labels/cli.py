#!/usr/bin/env python3
"""Generate ECIA EIGP 114 product or logistic labels as printable HTML.

Usage (installed):     ecia-label DATA.json [options]
Usage (local dev):     python -m ecia_labels DATA.json [options]

    options: [-o OUTDIR] [--layout LAYOUT.json]
             [--package-count] [--seed VALUE] [--self-test]

Output goes to OUTDIR (default: ./labels, created if missing). Each run writes
one file named after the input JSON, e.g. shipment.json -> labels/shipment.html.
Logistic runs also write a matching .csv tracking sheet.

Logistic data uses shipment-level fields (ship_from, ship_to, customer_po,
optional po_split) plus an "items" array of PO line items. Each item has a
quantity (the line total) and an optional master_carton_quantity that splits
the line into cartons (full cartons plus a remainder). Every carton becomes a
label with a unique package ID; with --package-count each label also carries a
(13Q) Package Count "n/total" within its line item.

Package IDs are seeded per item from the base seed (customer_po, or --seed) plus
the PO line, supplier part number and optional po_split, so a line reproduces
its IDs on re-run, different lines never collide, and bumping po_split re-rolls
a line that is re-split across shipments.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import layout as layout_mod
from . import production, spec, validate, verify

LARGE_RUN_WARN = 250


def _readable_message(msg: str) -> str:
    return (msg.replace(spec.RS, "<RS>").replace(spec.GS, "<GS>")
               .replace(spec.EOT, "<EOT>"))


def _load_layout(label_type: str, path) -> dict:
    merged = json.loads(json.dumps(spec.DEFAULT_LAYOUTS[label_type]))  # deep copy
    override = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(override, dict):
        raise ValueError(f"{path}: layout must be a JSON object")
    merged.update(override)
    return merged


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="ecia-label",
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("data", type=Path, help="path to the label data JSON")
    p.add_argument("-o", "--output", type=Path, default=Path("labels"),
                   help="output directory (created if missing; default: labels)")
    p.add_argument("--layout", type=Path, default=None,
                   help="optional layout-override JSON")
    p.add_argument("--package-count", action="store_true",
                   help="add the (13Q) Package Count field, numbered per line "
                        "item (e.g. 1/7 .. 7/7)")
    p.add_argument("--seed", default=None,
                   help="explicit base seed for package IDs; overrides the "
                        "default (customer_po, else random)")
    p.add_argument("--self-test", action="store_true",
                   help="decode every generated symbol to confirm it scans "
                        "(needs: pip install zxing-cpp pillow)")
    args = p.parse_args(argv)

    try:
        data = validate.load(args.data)
        label_type, payload, warnings = validate.validate(data)
    except validate.ValidationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    for w in warnings:
        print(f"warning: {w}", file=sys.stderr)

    # Build the per-label field dicts.
    seed_source = None
    if label_type == "product":
        labels_fields = [payload["fields"]]
    else:
        shipment, items = payload["shipment"], payload["items"]
        if args.seed is not None:
            base_seed, seed_source = args.seed, "--seed"
        elif shipment.get("customer_po"):
            base_seed, seed_source = shipment["customer_po"], "customer_po"
        else:
            base_seed, seed_source = None, "random"
        try:
            labels_fields = production.expand_shipment(
                shipment, items, base_seed, args.package_count)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

    if len(labels_fields) > LARGE_RUN_WARN:
        print(f"warning: this run produces {len(labels_fields)} labels in one "
              f"HTML file; consider splitting it", file=sys.stderr)

    try:
        layout = _load_layout(label_type, args.layout) if args.layout else None
        html, messages = layout_mod.render_document(
            label_type, labels_fields, layout)
    except (ValueError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    outdir = args.output
    outdir.mkdir(parents=True, exist_ok=True)
    stem = args.data.stem
    html_path = outdir / f"{stem}.html"
    html_path.write_text(html, encoding="utf-8")
    print(f"wrote {html_path} ({len(labels_fields)} label(s))")

    if label_type == "logistic":
        csv_text = production.tracking_csv(
            labels_fields, include_package_count=args.package_count)
        csv_path = outdir / f"{stem}.csv"
        csv_path.write_text(csv_text, encoding="utf-8")
        print(f"wrote {csv_path}")

        for item in payload["items"]:
            total = int(item["quantity"])
            master = item.get("master_carton_quantity")
            cartons = (production.carton_breakdown(total, int(master))
                       if master else [total])
            print(f"  line {item.get('customer_po_line')} "
                  f"{item.get('supplier_part_number')}: "
                  f"{len(cartons)} label(s) {cartons}")
        print(f"package IDs seeded from: {seed_source}")

    print(f"2D Format 06 payload (label 1): {_readable_message(messages[0])}")

    if args.self_test:
        if not verify.available():
            print("self-test skipped: install with 'pip install zxing-cpp pillow'",
                  file=sys.stderr)
        else:
            ok = True
            for i, (msg, lf) in enumerate(zip(messages, labels_fields), 1):
                res, detail = verify.verify_datamatrix(msg)
                if not res:
                    print(f" FAIL label {i}: {detail}"); ok = False
                for key in lf:
                    if key.endswith("_di") or key not in spec.FIELDS:
                        continue
                    if spec.FIELDS[key]["kind"] != "barcode":
                        continue
                    di = spec.resolved_di(key, lf)
                    res, detail = verify.verify_code128(di + lf[key])
                    if not res:
                        print(f" FAIL label {i} {key}: {detail}"); ok = False
            if not ok:
                print("self-test: FAILURES detected", file=sys.stderr)
                return 1
            print(f"self-test: all symbols across {len(labels_fields)} "
                  f"label(s) scanned correctly")

    return 0

