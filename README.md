# ECIA EIGP 114 label generator

Generates **product** and **logistic** labels that conform to the ECIA
EIGP 114 specification (the format in your customer's routing guide). Each run
takes a small JSON file of field values and writes a self-contained
`.html` file you can open in a browser to print or screenshot.

Both 1D and 2D symbologies are produced:

* **1D:** Code 128, one barcode per field, encoding `<DataIdentifier><value>`
  (e.g. `Q50`), with the human-readable `(DI) Field Name: value` text.
* **2D:** Data Matrix **ECC-200** carrying every field in one **ISO/IEC 15434
  Format 06** message:
  `[)>` `RS` `06` `GS` `<DI><val>` `GS` … `<DI><val>` `RS` `EOT`.

Every generated symbol has been verified to scan (see *Self-test* below).

## Install

```bash
pip install .                 # installs the `ecia-label` command
pip install .[verify]         # also installs the --self-test decoder deps
```

For local development, install editable (`pip install -e .`) or skip installing
entirely and run the module from the source tree with `python -m ecia_labels`
(only `pip install -r requirements.txt` is needed for that).

## Usage

Once installed, use the `ecia-label` command. During local development the
equivalent is `python -m ecia_labels` run from the source tree.

```bash
# product label  -> labels/product.html
ecia-label samples/product.json

# logistic label -> labels/logistic.html (+ labels/logistic.csv)
ecia-label samples/logistic.json

# with a layout override and a decode self-test
ecia-label samples/logistic.json \
    --layout samples/layout_logistic_custom.json --self-test

# logistic shipment: multiple PO line items, split into cartons,
# each label numbered (13Q) across the whole shipment
ecia-label samples/logistic_shipment.json --package-count

# same thing without installing, from the source tree:
python -m ecia_labels samples/logistic_shipment.json --package-count
```

Output goes to `./labels/` by default (created if missing); pass `-o DIR` to
change it. Each run writes one file named after the input JSON, e.g.
`samples/product.json` -> `labels/product.html`. The HTML is fully
self-contained (barcodes are inline SVG), so there are no separate asset files.

Open the generated `.html` in a browser, then print (the page carries a print
stylesheet sized in inches) or screenshot.

## Data JSON

`label_type` is `"product"` or `"logistic"`. `fields` holds the values.

Product (required + customer part number):

```json
{
  "label_type": "product",
  "fields": {
    "customer_part_number": "596-777A1-ND",
    "supplier_part_number": "XAF4444",
    "quantity": "1",
    "date_code": "1452",
    "lot_code": "ABC123456789",
    "country_of_origin": "US"
  }
}
```

Logistic uses shipment-level fields plus an `items` array of PO line items.
`ship_from`/`ship_to` are text only (no barcode) and accept a list of address
lines. Each item has its own `quantity` (the line total) and an optional
`master_carton_quantity` that splits the line into cartons:

```json
{
  "label_type": "logistic",
  "fields": {
    "ship_from": ["Premier Supplier", "1234 Niagara St.", "Buffalo, NY 44556"],
    "ship_to":   ["Standard Company", "110 Commerce Drive", "Cityville, IL 60601"],
    "customer_po": "029-HG135",
    "items": [
      { "customer_po_line": "1", "supplier_part_number": "BAOCHIP-DABAO-V3",
        "quantity": "3500", "date_code": "2626", "lot_code": "BAO-0033",
        "country_of_origin": "CN", "master_carton_quantity": 500 },
      { "customer_po_line": "2", "supplier_part_number": "BAOCHIP-ANOTHER",
        "quantity": "15", "date_code": "2627", "lot_code": "BAO-0042",
        "country_of_origin": "CN", "master_carton_quantity": 10 }
    ]
  }
}
```

A single-carton item can omit `master_carton_quantity` (one label for the whole
`quantity`) and may supply its own `package_id`. The older flat logistic format
(per-line fields directly under `fields`, no `items`, optional top-level
`print_run`) is still accepted and treated as a single line item.

### Fields and Data Identifiers

| field key              | DI    | max | label    | notes                              |
|------------------------|-------|-----|----------|------------------------------------|
| customer_part_number   | P     | 40  | product¹ |                                    |
| supplier_part_number   | 1P    | 40  | both     | logistic: per item                 |
| quantity               | Q     | 9   | both     | logistic: per item = line total    |
| date_code              | 10D   | 7   | both     | `9D`/`10D`; YYWW; override `*_di`  |
| lot_code               | 1T    | 20  | both     | logistic: per item                 |
| country_of_origin      | 4L    | 2   | both     | ISO 3166 alpha-2                   |
| customer_po            | K     | 25  | logistic | shipment-level                     |
| customer_po_line       | 4K    | 5   | logistic | per item                           |
| package_id             | 4S    | 25  | logistic | generated per carton²; `5S` via DI |
| package_count          | 13Q   | 11  | logistic | only with `--package-count`        |
| ship_from / ship_to    | —     | —   | logistic | shipment-level, text, list of lines|

¹ Customer part number is optional in EIGP 114; it is required here on the
product label per your customer's rule. Override a multi-DI field's identifier
by adding e.g. `"date_code_di": "9D"` or `"package_id_di": "5S"` (product:
under `fields`; logistic: inside the item).

² For a split line `package_id` is generated per carton (any supplied value is
ignored). A single-carton item with no `master_carton_quantity` uses a supplied
`package_id` if present, else generates one.

Validation aborts on a missing/empty required field, a value over its max
length, a value with characters Code 128 cannot encode, or a non-integer
`quantity`/`master_carton_quantity`. It warns (but continues) on a non-2-letter
country code or a date code that is not a 4-digit YYWW.

## Logistic shipments: cartons, package IDs, package counts

Each item is split into labels by its `master_carton_quantity`: `total // master`
full cartons plus a remainder carton when `total % master` is non-zero. With the
example above, line 1 (3500 / 500) yields seven 500-unit labels and line 2
(15 / 10) yields two labels of 10 and 5 — and the whole run goes into one HTML
file, one label per print page.

**Package IDs.** Every label gets a unique 12-character ID (uppercase letters
and digits) in its `(4S) Package ID` field. The generator is seeded per item
from the base seed plus the PO line, the supplier part number and an optional
`po_split`, so:

* re-running the same file reproduces the same IDs (idempotent);
* different line items never share an ID sequence;
* bumping `po_split` on a line re-rolls only that line's IDs — use this when you
  split one line/lot across multiple physical shipments.

The base seed is `customer_po` by default (so it is stable for a PO), or
`--seed VALUE` to override, or random if neither is available. `po_split` may be
set per item (preferred) or shipment-wide (applies to items without their own).
Uniqueness is also enforced globally across the whole run.

**Package count (`--package-count`).** Adds the `(13Q) Package Count` field,
numbered across the whole shipment — with the example above the 13 labels are
`1/13`, `2/13`, … `13/13` in line-item order. This reflects what the receiver
checks: total packages in the shipment, each with a unique number.

### Tracking CSV

Every logistic run also writes a `.csv` matching the label file name (e.g.
`logistic_shipment.csv`), one row per label, for pasting into your tracking
spreadsheet (the `Package Count` column appears only with `--package-count`):

| Package ID   | PO Number | PO Line | Supplier PN      | Quantity | Package Count |
|--------------|-----------|---------|------------------|----------|---------------|
| V8CJW2WVDBWF | 029-HG135 | 1       | BAOCHIP-DABAO-V3 | 500      | 1/13          |
| ...          | ...       | ...     | ...              | ...      | ...           |
| 2OQWEO66GRDI | 029-HG135 | 3       | BAOCHIP-ANOTHER  | 5        | 13/13         |

## Optional layout override (`--layout`)

The built-in layouts reproduce the EIGP 114 example labels, so you usually
need only the data JSON. To re-order fields, group them into columns, move
break lines, reposition the Data Matrix, or change sizes, pass a layout JSON.
Provided keys override the built-in defaults; omitted keys keep them.

```json
{
  "width_in": 4.5,
  "caption_width_in": 1.5,
  "hrt_style": "inline",
  "xdim_in": 0.013,
  "module_in": 0.02,
  "rows": [
    {"type": "address", "left": "ship_from", "right": "ship_to"},
    {"type": "break"},
    {"type": "columns", "fields": ["customer_po", "customer_po_line"]},
    {"type": "field", "name": "supplier_part_number"},
    {"type": "datamatrix", "align": "center"}
  ]
}
```

Row types: `field`, `columns` (N side-by-side), `address` (From/To header),
`break` (horizontal rule), `datamatrix` (`align`: left/center/right).
`caption_width_in` sets the width of the left caption column on `stacked` (product) rows; shrink it to give the barcodes more room (default 1.7in). The longest field names stay on one line down to about 1.65in and wrap to two lines below that (still legible); to go narrower and keep them single-line, also lower the `.cap` font-size in layout.py. `hrt_style` is `stacked` (caption left, value above bars — the product look)
or `inline` (`(DI) Name: value` on one line, bars beneath — the logistic look).
The Data Matrix encodes the barcoded fields in the order they appear in `rows`.

## Spec compliance notes (EIGP 114)

* Data Matrix is ECC-200; X-dimension default 20 mil (min 14.6); 2-module
  quiet zone (min 1). Code 128 X-dimension default 13 mil (min 9.5); height
  0.375"; quiet zone ≥ max(10×X, 0.25"). Adjust `xdim_in` / `module_in` in a
  layout file if your printer needs it.
* The 1D barcode encodes the Data Identifier with no space before the value.
* Sizes are set in inches with a print stylesheet, so "Print → Save as PDF" at
  100% scale preserves the X-dimensions. Verify a printed sample on a scanner
  and against your customer's print-quality grade before going live.

## Self-test

`--self-test` rasterises every generated symbol and decodes it with
`zxing-cpp`, asserting the Data Matrix round-trips byte-for-byte (separators
included) and each Code 128 decodes to its `DI+value`. Requires the decoder
deps (`pip install .[verify]`, or `pip install zxing-cpp pillow`); without them
the flag is skipped with a note.

## Layout

```
pyproject.toml           packaging / `ecia-label` entry point
ecia_labels/
  __main__.py            enables `python -m ecia_labels`
  cli.py                 command-line interface
  spec.py                field registry, separators, default layouts
  validate.py            JSON parsing + validation
  barcodes.py            Code 128 -> SVG
  datamatrix.py          Format 06 message + ECC-200 -> SVG
  production.py          print-run breakdown, package IDs, tracking CSV
  layout.py              HTML layout engine
  verify.py              optional decode self-test
samples/                 example data + layout-override JSON
```

## AI Usage Disclaimer

Vibe-coded with Claude Opus 4.8-high using the following prompt:

```
I just got sent this guide from a customer of the shipping label format they require for my product. I need a python script that can generate an ECIA product label and ECIA logistics label, as described in this document (appendix A.1, A.3 outline the field descriptions, we are only using the "required" ones, with the exception for the product label we are adding the customer part number).

These fields should be specified as a JSON file that goes into the script, and the output should be a product label and a logistics label that conforms to their specification. The labels could be described as a simple HTML page, in which case the output is a directory containing the label and its image assets, with an index.html that I can open using a local browser to then screenshot and/or print to generate the label.

An example of a compliant product label is on page 16 of 44 (PDF page 34), "ECIA Format -Product1", and a logistics label is two pages later on page 18 of 44 (PDF page 36).

For the python script you can assume I'm running on linux, use argparse, pathlib where possible, and that I am relatively fluent in command line tools and editing python. The hard part for me is encoding the CODE39 barcodes, and then aggregating it into a Data Matrix ECC 200 code that scans according to their specification, and finally placing these fields. I would imagine that the script you write would have a modules for:

* parsing and validating the json
* generating the various barcode elements as bitmaps
* compositing the data for the datamatrix ecc code & generating its bitmap
* a layout engine for placing all the data into html format

The layout engine may require some customization. I think we can also require a second JSON file that specifies the following:

* ordering of the fields on the two labels
* some ability to handle two-column fields. For example, on the logistics label example, the From is on the top half, the To is on the right half. And the date code/COO fields are laid out two in a line, but the rest are in linear format
* some ability to specify a horizontal break line
* and a field to specify where the datamatrix code goes

I'm not an expert in HTML or web layout, so maybe these are easy things to do and if it is pretty easy to just lay these out without the second JSON file you can skip that direction and go straight to the HTML output.

Have a think about this first, and let me know if you think the strategy is in the right direction, if you have better ideas on how to do this, or if maybe there isn't already an off the shelf free tool that can do this for me and I don't have to write one myself.
```

And the Mouser product guide PDF as guidance. Some further tweaks were made to change the coding to CODE128 and fix some SVG overflow issues, but largely, Opus one-shotted this.