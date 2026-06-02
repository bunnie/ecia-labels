# ECIA EIGP 114 label generator

Generates **product** and **logistic** labels that conform to the ECIA
EIGP 114 specification (the format required by Mouser, for example). Each run
takes a small JSON file of field values and writes a self-contained
`index.html` you can open in a browser to print or screenshot.

Both 1D and 2D symbologies are produced:

* **1D:** Code 128, one barcode per field, encoding `<DataIdentifier><value>`
  (e.g. `Q50`), with the human-readable `(DI) Field Name: value` text.
* **2D:** Data Matrix **ECC-200** carrying every field in one **ISO/IEC 15434
  Format 06** message:
  `[)>` `RS` `06` `GS` `<DI><val>` `GS` … `<DI><val>` `RS` `EOT`.

Every generated symbol has been verified to scan (see *Self-test* below).

## Install

```bash
pip install -r requirements.txt
# optional, only for --self-test:
pip install zxing-cpp pillow
```

## Usage

```bash
# product label
python generate_label.py samples/product.json -o out/product

# logistic label
python generate_label.py samples/logistic.json -o out/logistic

# with a layout override and a decode self-test
python generate_label.py samples/logistic.json -o out/logistic \
    --layout samples/layout_logistic_custom.json --self-test
```

Open `out/<label>/index.html` in a browser, then print (the page carries a
print stylesheet sized in inches) or screenshot. The HTML is fully
self-contained — barcodes are inline SVG, so there are **no separate image
asset files** to keep alongside it.

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

Logistic (required, incl. PO Line). `ship_from`/`ship_to` are text only (no
barcode) and accept a list of address lines:

```json
{
  "label_type": "logistic",
  "fields": {
    "ship_from": ["Premier Supplier", "1234 Niagara St.", "Buffalo, NY 44556"],
    "ship_to":   ["Standard Company", "110 Commerce Drive", "Cityville, IL 60601"],
    "customer_po": "1234567891234",
    "customer_po_line": "2",
    "supplier_part_number": "DEF3R3H2055",
    "quantity": "50",
    "package_id": "81664789011239840",
    "date_code": "1452",
    "country_of_origin": "US",
    "lot_code": "ABC123456789"
  }
}
```

### Fields and Data Identifiers

| field key              | DI    | max | label    | notes                              |
|------------------------|-------|-----|----------|------------------------------------|
| customer_part_number   | P     | 40  | both¹    |                                    |
| supplier_part_number   | 1P    | 40  | both     |                                    |
| quantity               | Q     | 9   | both     |                                    |
| date_code              | 10D   | 7   | both     | `9D`/`10D`; YYWW; override `*_di`  |
| lot_code               | 1T    | 20  | both     |                                    |
| country_of_origin      | 4L    | 2   | both     | ISO 3166 alpha-2                   |
| customer_po            | K     | 25  | logistic |                                    |
| customer_po_line       | 4K    | 5   | logistic |                                    |
| package_id             | 4S    | 25  | logistic | `4S` like / `5S` mixed; override   |
| ship_from / ship_to    | —     | —   | logistic | text only, list of lines           |

¹ Customer part number is optional in EIGP 114; it is required here on the
product label per your customer's rule. Override a multi-DI field's identifier
by adding e.g. `"date_code_di": "9D"` or `"package_id_di": "5S"` to `fields`.

Validation aborts on a missing/empty required field, a value over its max
length, or a value with characters Code 128 cannot encode. It warns (but
continues) on a non-2-letter country code, a non-numeric quantity, or a date
code that is not a 4-digit YYWW.

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
included) and each Code 128 decodes to its `DI+value`. Requires
`pip install zxing-cpp pillow`; without them the flag is skipped with a note.

## Layout

```
generate_label.py        CLI
ecia_labels/
  spec.py                field registry, separators, default layouts
  validate.py            JSON parsing + validation
  barcodes.py            Code 128 -> SVG
  datamatrix.py          Format 06 message + ECC-200 -> SVG
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