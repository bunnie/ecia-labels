"""ECIA EIGP 114 field registry and message constants.

This is the single source of truth for:
  * the control characters used by the ISO/IEC 15434 Format 06 envelope,
  * each label field's Data Identifier (DI), human name and max length,
  * which fields are required on each label type,
  * the built-in (spec-faithful) layouts for the product and logistic labels.

Reference: EIGP 114.2018 Appendices A.1 (product), A.3 (logistic),
B.3 (2D message format) and C (linear barcode).
"""

# --- ISO/IEC 15434 Format 06 control characters (Appendix B.3.2) -------------
COMPLIANCE_INDICATOR = "[)>"   # 0x5B 0x29 0x3E
RS = "\x1e"                    # Record Separator   (ASCII 30 / 0x1E)
GS = "\x1d"                    # Group Separator    (ASCII 29 / 0x1D)
EOT = "\x04"                   # End of Transmission (ASCII 04 / 0x04)
FORMAT_INDICATOR = "06"

# --- Field registry ----------------------------------------------------------
# kind: "barcode" -> rendered as DI+value 1D barcode AND placed in the 2D code.
#       "text"    -> printed as plain text only (no barcode, not in 2D code).
#
# di:   the Data Identifier prepended to the value inside the barcode/2D code.
#       For fields with more than one permitted DI (date code 9D/10D,
#       package id 4S/5S) the spec-default is used; override per-field in the
#       data JSON with "<field>_di" if you need the alternate.
FIELDS = {
    "customer_part_number": dict(di="P",   name="Customer PN",          max_len=40, kind="barcode"),
    "supplier_part_number": dict(di="1P",  name="Supplier PN",          max_len=40, kind="barcode"),
    "quantity":             dict(di="Q",   name="Quantity",             max_len=9,  kind="barcode"),
    "date_code":            dict(di="10D", name="Date Code",            max_len=7,  kind="barcode"),
    "lot_code":             dict(di="1T",  name="Lot Code",             max_len=20, kind="barcode"),
    "country_of_origin":    dict(di="4L",  name="COO",                  max_len=2,  kind="barcode"),
    "customer_po":          dict(di="K",   name="PO Number",            max_len=25, kind="barcode"),
    "customer_po_line":     dict(di="4K",  name="PO Line",              max_len=5,  kind="barcode"),
    "package_id":           dict(di="4S",  name="Package ID",           max_len=25, kind="barcode"),
    "ship_from":            dict(di=None,  name="Ship From",            max_len=None, kind="text"),
    "ship_to":              dict(di=None,  name="Ship To",              max_len=None, kind="text"),
}

# Permitted alternate DIs (validated when *_di override is supplied).
ALTERNATE_DIS = {
    "date_code":  {"9D", "10D"},
    "package_id": {"4S", "5S"},
}

# --- Required fields per label type (Appendix A.1 / A.3) ----------------------
# Product label: ECIA-required + Customer Part Number (added per customer rule).
# Logistic label: ECIA-required incl. Customer PO Line (4K).
LABELS = {
    "product": dict(
        required=[
            "customer_part_number", "supplier_part_number", "quantity",
            "date_code", "lot_code", "country_of_origin",
        ],
    ),
    "logistic": dict(
        required=[
            "ship_from", "ship_to", "customer_po", "customer_po_line",
            "supplier_part_number", "quantity", "package_id",
            "date_code", "country_of_origin", "lot_code",
        ],
    ),
}

# --- Built-in layouts (mirror the EIGP 114 example labels) -------------------
# A layout is a width plus an ordered list of rows. Row types:
#   {"type": "field",   "name": <field>}            single barcoded field
#   {"type": "columns", "fields": [<field>, ...]}   N fields side by side
#   {"type": "address", "left": <field>, "right": <field>}  From/To header
#   {"type": "break"}                               horizontal rule
#   {"type": "datamatrix", "align": "left|center|right"}
# hrt_style: "stacked" -> field label on the left, value above the bars
#                         (the product-label look)
#            "inline"  -> "(DI) Name: value" on one line, bars beneath
#                         (the logistic-label look)
DEFAULT_LAYOUTS = {
    "product": dict(
        width_in=4.0,
        hrt_style="stacked",
        rows=[
            {"type": "field", "name": "customer_part_number"},
            {"type": "field", "name": "supplier_part_number"},
            {"type": "field", "name": "quantity"},
            {"type": "field", "name": "date_code"},
            {"type": "field", "name": "lot_code"},
            {"type": "field", "name": "country_of_origin"},
            {"type": "break"},
            {"type": "datamatrix", "align": "right"},
        ],
    ),
    "logistic": dict(
        width_in=4.0,
        hrt_style="inline",
        rows=[
            {"type": "address", "left": "ship_from", "right": "ship_to"},
            {"type": "break"},
            {"type": "field", "name": "customer_po"},
            {"type": "field", "name": "customer_po_line"},
            {"type": "field", "name": "supplier_part_number"},
            {"type": "field", "name": "quantity"},
            {"type": "field", "name": "package_id"},
            {"type": "break"},
            {"type": "columns", "fields": ["date_code", "country_of_origin"]},
            {"type": "field", "name": "lot_code"},
            {"type": "break"},
            {"type": "datamatrix", "align": "center"},
        ],
    ),
}


def resolved_di(field_key, data):
    """Return the DI for a field, honouring an optional '<field>_di' override."""
    base = FIELDS[field_key]["di"]
    override = data.get(field_key + "_di")
    if override:
        allowed = ALTERNATE_DIS.get(field_key)
        if allowed and override not in allowed:
            raise ValueError(
                f"{field_key}_di={override!r} is not one of {sorted(allowed)}"
            )
        return override
    return base
