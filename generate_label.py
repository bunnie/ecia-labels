#!/usr/bin/env python3
"""Generate ECIA EIGP 114 product or logistic labels as printable HTML.

Usage:
    python generate_label.py DATA.json [-o OUTDIR] [--layout LAYOUT.json]
                             [--seed N] [--self-test]

DATA.json sets label_type ("product" | "logistic") and the field values.
Output goes to OUTDIR (default: ./labels, created if missing). Each run writes
one file named after the input JSON, e.g. logistic_print_run.json ->
labels/logistic_print_run.html. Logistic runs also write a matching .csv.

Logistic labels may include a "print_run" block:

    "print_run": { "total_quantity": 3600, "master_carton_quantity": 500 }

which derives one label per carton (full cartons of the master quantity plus a
remainder), each with a unique generated 12-character package ID. All labels go
into the one HTML file (one print page each), and the matching .csv tracking
sheet (package id, PO number, supplier PN, quantity) is written alongside.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

from ecia_labels import layout as layout_mod
from ecia_labels import production, spec, validate, verify

# Soft guard: warn (don't block) above this many labels in one run.
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
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("data", type=Path, help="path to the label data JSON")
    p.add_argument("-o", "--output", type=Path, default=Path("labels"),
                   help="output directory (created if missing; default: labels)")
    p.add_argument("--layout", type=Path, default=None,
                   help="optional layout-override JSON")
    p.add_argument("--seed", default=None,
                   help="explicit seed for package IDs; overrides the default "
                        "(seed from customer_po, else random)")
    p.add_argument("--self-test", action="store_true",
                   help="decode every generated symbol to confirm it scans "
                        "(needs: pip install zxing-cpp pillow)")
    args = p.parse_args(argv)

    try:
        data = validate.load(args.data)
        label_type, fields, print_run, warnings = validate.validate(data)
    except validate.ValidationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    for w in warnings:
        print(f"warning: {w}", file=sys.stderr)

    # Package-ID RNG seed: an explicit --seed wins; otherwise seed from
    # customer_po so a given PO reproduces the same IDs; otherwise random.
    if args.seed is not None:
        seed = args.seed
        seed_source = "--seed"
    elif fields.get("customer_po"):
        seed = fields["customer_po"]
        seed_source = "customer_po"
    else:
        seed = None
        seed_source = "random"
    rng = random.Random(seed)

    # Expand a print run into one field set per label.
    if print_run is not None:
        labels_fields = production.expand_print_run(
            fields, print_run["total_quantity"],
            print_run["master_carton_quantity"], rng)
    else:
        labels_fields = [fields]

    if len(labels_fields) > LARGE_RUN_WARN:
        print(f"warning: this run produces {len(labels_fields)} labels in one "
              f"HTML file; consider splitting it", file=sys.stderr)

    try:
        layout = _load_layout(label_type, args.layout) if args.layout else None
        html, messages = layout_mod.render_document(
            label_type, labels_fields, data["fields"], layout)
    except (ValueError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    outdir = args.output
    outdir.mkdir(parents=True, exist_ok=True)
    stem = args.data.stem
    html_path = outdir / f"{stem}.html"
    html_path.write_text(html, encoding="utf-8")
    print(f"wrote {html_path} ({len(labels_fields)} label(s))")

    # Tracking CSV for logistic labels, named to match the label file.
    if label_type == "logistic":
        csv_text = production.tracking_csv(labels_fields)
        csv_path = outdir / f"{stem}.csv"
        csv_path.write_text(csv_text, encoding="utf-8")
        print(f"wrote {csv_path}")

    if print_run is not None:
        qtys = [f["quantity"] for f in labels_fields]
        print(f"print run: {print_run['total_quantity']} units / "
              f"{print_run['master_carton_quantity']} per carton "
              f"-> {len(qtys)} labels [{', '.join(qtys)}]")
        print(f"package IDs seeded from: {seed_source}")

    # Show the first label's payload (all share structure; only Q + 4S differ).
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
                    if spec.FIELDS[key]["kind"] != "barcode":
                        continue
                    di = spec.resolved_di(key, data["fields"])
                    res, detail = verify.verify_code128(di + lf[key])
                    if not res:
                        print(f" FAIL label {i} {key}: {detail}"); ok = False
            if not ok:
                print("self-test: FAILURES detected", file=sys.stderr)
                return 1
            symbols = sum(1 + sum(spec.FIELDS[k]["kind"] == "barcode" for k in lf)
                          for lf in labels_fields)
            print(f"self-test: all {symbols} symbols across "
                  f"{len(labels_fields)} label(s) scanned correctly")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())