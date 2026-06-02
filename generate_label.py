#!/usr/bin/env python3
"""Generate an ECIA EIGP 114 product or logistic label as a printable HTML page.

Usage:
    python generate_label.py DATA.json -o OUTDIR [--layout LAYOUT.json] [--self-test]

DATA.json sets label_type ("product" | "logistic") and the field values.
The output directory gets a self-contained index.html (barcodes are inline
SVG, so there are no separate asset files to keep together). Open it in a
browser, then print or screenshot the label.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ecia_labels import layout as layout_mod
from ecia_labels import spec, validate, verify


def _readable_message(msg: str) -> str:
    """Show control characters as their mnemonic for human-readable output."""
    return (msg.replace(spec.RS, "<RS>").replace(spec.GS, "<GS>")
               .replace(spec.EOT, "<EOT>"))


def _load_layout(label_type: str, path) -> dict:
    """Start from the built-in layout, override with the user's layout JSON."""
    merged = json.loads(json.dumps(spec.DEFAULT_LAYOUTS[label_type]))  # deep copy
    override = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(override, dict):
        raise ValueError(f"{path}: layout must be a JSON object")
    merged.update(override)
    return merged


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("data", type=Path, help="path to the label data JSON")
    p.add_argument("-o", "--output", type=Path, required=True,
                   help="output directory for index.html")
    p.add_argument("--layout", type=Path, default=None,
                   help="optional layout-override JSON")
    p.add_argument("--self-test", action="store_true",
                   help="decode every generated symbol to confirm it scans "
                        "(needs: pip install zxing-cpp pillow)")
    args = p.parse_args(argv)

    try:
        data = validate.load(args.data)
        label_type, fields, warnings = validate.validate(data)
    except validate.ValidationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    for w in warnings:
        print(f"warning: {w}", file=sys.stderr)

    try:
        layout = _load_layout(label_type, args.layout) if args.layout else None
        html, message = layout_mod.render_html(label_type, fields, data, layout)
    except (ValueError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    outdir = args.output
    outdir.mkdir(parents=True, exist_ok=True)
    index = outdir / "index.html"
    index.write_text(html, encoding="utf-8")

    print(f"wrote {index}")
    print(f"2D Format 06 payload: {_readable_message(message)}")

    if args.self_test:
        if not verify.available():
            print("self-test skipped: install with 'pip install zxing-cpp pillow'",
                  file=sys.stderr)
        else:
            ok = True
            res, detail = verify.verify_datamatrix(message)
            print(("  ok  " if res else " FAIL ") + detail); ok &= res
            for key in fields:
                if spec.FIELDS[key]["kind"] != "barcode":
                    continue
                di = spec.resolved_di(key, data)
                res, detail = verify.verify_code128(di + fields[key])
                print(("  ok  " if res else " FAIL ") + detail); ok &= res
            if not ok:
                print("self-test: FAILURES detected", file=sys.stderr)
                return 1
            print("self-test: all symbols scanned correctly")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
