"""Layout engine: turn validated fields into a printable HTML label.

The body is described by a *layout* (a width + ordered rows). Built-in layouts
in ``spec.DEFAULT_LAYOUTS`` reproduce the EIGP 114 example labels; an optional
layout JSON can override row order, column grouping, break placement, the
Data Matrix position, the X-dimensions and the label width.

The 2D Data Matrix encodes every barcoded field, in the order the fields first
appear in the layout (columns flattened left to right) -- matching the
top-to-bottom element order shown in the spec examples.
"""
from __future__ import annotations

from html import escape

from . import barcodes, datamatrix, spec


# --------------------------------------------------------------------------- #
# field helpers
# --------------------------------------------------------------------------- #
def _field_parts(key, fields, raw):
    """Return (di, value, barcode_payload) for a barcoded field."""
    di = spec.resolved_di(key, raw)
    value = fields[key]
    return di, value, di + value


def _barcoded_order(layout):
    """Field keys in DM/encoding order, as they appear in the layout."""
    order = []
    for row in layout["rows"]:
        if row["type"] == "field":
            order.append(row["name"])
        elif row["type"] == "columns":
            order.extend(row["fields"])
    return order


# --------------------------------------------------------------------------- #
# row renderers
# --------------------------------------------------------------------------- #
def _hrt_label(di, name):
    return f'<span class="di">({escape(di)})</span> {escape(name)}'


def _render_field(key, fields, raw, hrt_style, xdim_in):
    di, value, payload = _field_parts(key, fields, raw)
    name = spec.FIELDS[key]["name"]
    bars = barcodes.code128_svg(payload, xdim_in=xdim_in)
    if hrt_style == "stacked":
        # field label on the left, value above the bars (product look)
        return (
            '<div class="row stacked">'
            f'<div class="cap">{_hrt_label(di, name)}:</div>'
            '<div class="bc">'
            f'<div class="val">{escape(value)}</div>{bars}'
            '</div></div>'
        )
    # inline: "(DI) Name: value" on one line, bars beneath (logistic look)
    return (
        '<div class="row inline">'
        f'<div class="line">{_hrt_label(di, name)}: '
        f'<span class="val">{escape(value)}</span></div>'
        f'<div class="bc">{bars}</div>'
        '</div>'
    )


def _render_columns(keys, fields, raw, xdim_in):
    cells = []
    for key in keys:
        di, value, payload = _field_parts(key, fields, raw)
        name = spec.FIELDS[key]["name"]
        bars = barcodes.code128_svg(payload, xdim_in=xdim_in)
        cells.append(
            '<div class="col-cell">'
            f'<div class="line">{_hrt_label(di, name)}: '
            f'<span class="val">{escape(value)}</span></div>'
            f'<div class="bc">{bars}</div></div>'
        )
    return f'<div class="columns">{"".join(cells)}</div>'


def _render_address(left_key, right_key, fields):
    def block(tag, key):
        lines = fields.get(key, [])
        body = "<br>".join(escape(s) for s in lines)
        return f'<div class="addr-cell"><div class="tag">{tag}</div>{body}</div>'
    return (
        '<div class="address">'
        + block("FROM", left_key)
        + block("TO", right_key)
        + '</div>'
    )


def _render_datamatrix(align, message, module_in):
    svg = datamatrix.datamatrix_svg(message, module_in=module_in)
    return f'<div class="dm dm-{align}">{svg}</div>'


# --------------------------------------------------------------------------- #
# page assembly
# --------------------------------------------------------------------------- #
_CSS = """
:root {{ --ink:#000; }}
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; padding: 0; background: #f3f3f3; }}
body {{ font-family: Helvetica, Arial, "Liberation Sans", sans-serif;
        color: var(--ink); -webkit-font-smoothing: antialiased; }}
.sheet {{ padding: 0.4in; }}
.label {{
    width: {width}in; background: #fff; color: var(--ink);
    border: 1.5pt solid var(--ink); padding: 0.12in 0.14in;
    font-size: 9.5pt; line-height: 1.15;
}}
.row {{ padding: 0.035in 0; }}
.di {{ font-weight: 700; }}
.val {{ font-weight: 600; }}
.bc {{ margin-top: 0.02in; min-width: 0; }}
/* never let a barcode spill past the label border; it scales to fit width */
.bc svg {{ display: block; max-width: 100%; height: auto; }}

/* stacked (product) rows: caption left, value-over-bars right */
.row.stacked {{ display: flex; align-items: center; gap: 0.1in; }}
.row.stacked .cap {{ flex: 0 0 {cap_width}in; }}
.row.stacked .bc {{ flex: 1 1 auto; min-width: 0; margin-top: 0; text-align: center; }}
.row.stacked .bc .val {{ font-size: 8.5pt; margin-bottom: 0.01in; text-align: center; }}
.row.stacked .bc svg {{ margin: 0 auto; }}

/* inline (logistic) rows */
.row.inline .line {{ white-space: nowrap; }}

/* two-up columns */
.columns {{ display: flex; gap: 0.18in; padding: 0.035in 0; }}
.columns .col-cell {{ flex: 1 1 0; min-width: 0; }}

/* From / To header */
.address {{ display: flex; }}
.address .addr-cell {{ flex: 1 1 0; padding: 0.02in 0.12in; }}
.address .addr-cell:last-child {{ border-left: 1pt solid var(--ink); }}
.address .tag {{ font-size: 6.5pt; letter-spacing: 0.04em; }}

/* break line */
.brk {{ border: none; border-top: 1pt solid var(--ink); margin: 0.06in 0; }}

/* data matrix block */
.dm {{ display: flex; padding-top: 0.06in; }}
.dm-left {{ justify-content: flex-start; }}
.dm-center {{ justify-content: center; }}
.dm-right {{ justify-content: flex-end; }}
.dm svg {{ display: block; }}

@media print {{
    @page {{ margin: 0.25in; }}
    html, body {{ background: #fff; }}
    .sheet {{ padding: 0; }}
    .label {{ page-break-inside: avoid; }}
}}
"""


def render_html(label_type, fields, raw, layout=None):
    """Return (html_document, format06_message)."""
    layout = layout or spec.DEFAULT_LAYOUTS[label_type]
    width = layout.get("width_in", 4.5)
    cap_width = layout.get("caption_width_in", 1.5)
    hrt_style = layout.get("hrt_style",
                           spec.DEFAULT_LAYOUTS[label_type]["hrt_style"])
    xdim_in = layout.get("xdim_in", barcodes.DEFAULT_XDIM_IN)
    module_in = layout.get("module_in", datamatrix.DEFAULT_MODULE_IN)

    # Build the Format 06 message from barcoded fields in layout order.
    elements = []
    for key in _barcoded_order(layout):
        if key in fields:
            di, value, _ = _field_parts(key, fields, raw)
            elements.append((di, value))
    message = datamatrix.build_format06(elements)

    body_parts = []
    for row in layout["rows"]:
        rtype = row["type"]
        if rtype == "field":
            if row["name"] in fields:
                body_parts.append(
                    _render_field(row["name"], fields, raw, hrt_style, xdim_in))
        elif rtype == "columns":
            keys = [k for k in row["fields"] if k in fields]
            if keys:
                body_parts.append(_render_columns(keys, fields, raw, xdim_in))
        elif rtype == "address":
            body_parts.append(
                _render_address(row["left"], row["right"], fields))
        elif rtype == "break":
            body_parts.append('<hr class="brk">')
        elif rtype == "datamatrix":
            body_parts.append(
                _render_datamatrix(row.get("align", "center"), message, module_in))
        else:
            raise ValueError(f"unknown layout row type: {rtype!r}")

    css = _CSS.format(width=width, cap_width=cap_width)
    title = f"ECIA {label_type.capitalize()} Label"
    html = (
        "<!DOCTYPE html>\n"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{escape(title)}</title><style>{css}</style></head>"
        f'<body><div class="sheet"><div class="label {label_type}">'
        f'{"".join(body_parts)}'
        "</div></div></body></html>"
    )
    return html, message