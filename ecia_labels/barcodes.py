"""Code 128 1D barcodes, rendered as self-contained SVG.

The actual symbology encoding (start code, code-set switching, modulo-103
check digit, stop code) is delegated to the well-tested ``python-barcode``
library via ``Code128(...).build()``, which returns the raw module bit string
("1" = bar module, "0" = space module). We render that bit string ourselves so
we control the X-dimension, bar height and quiet zone, and emit clean inline
SVG with no library-drawn human-readable text (ECIA places its own).

EIGP 114 Appendix C constraints honoured by the defaults:
  * X-dimension >= 9.5 mil            -> DEFAULT_XDIM_IN = 0.013"
  * bar height ~0.375"                -> DEFAULT_HEIGHT_IN = 0.375"
  * quiet zone >= max(10*X, 0.25")    -> computed per symbol
"""
from __future__ import annotations

from barcode import Code128

DEFAULT_XDIM_IN = 0.013      # 13 mil (min allowed is 9.5 mil)
DEFAULT_HEIGHT_IN = 0.375    # target linear barcode height


def encode_code128(value: str) -> str:
    """Return the raw module bit string for a Code 128 symbol of ``value``."""
    built = Code128(value).build()
    if not built:
        raise ValueError(f"could not encode Code 128 for {value!r}")
    return built[0]


def _quiet_zone_modules(xdim_in: float) -> int:
    quiet_in = max(10 * xdim_in, 0.25)
    return int(round(quiet_in / xdim_in))


def code128_svg(value: str, xdim_in: float = DEFAULT_XDIM_IN,
                height_in: float = DEFAULT_HEIGHT_IN) -> str:
    """Render ``value`` (already DI+data) as an inline Code 128 SVG string.

    Coordinates are in module units (1 unit = 1 X-dimension); physical size is
    fixed via the svg width/height attributes so printed output meets the
    X-dimension spec regardless of screen zoom.
    """
    bits = encode_code128(value)
    qz = _quiet_zone_modules(xdim_in)
    n = len(bits)
    total_w = qz + n + qz
    height_modules = max(1, int(round(height_in / xdim_in)))

    # Merge consecutive bar modules into single rects.
    rects = []
    i = 0
    while i < n:
        if bits[i] == "1":
            j = i
            while j < n and bits[j] == "1":
                j += 1
            rects.append(f'<rect x="{qz + i}" y="0" width="{j - i}" '
                         f'height="{height_modules}"/>')
            i = j
        else:
            i += 1

    width_in = total_w * xdim_in
    return (
        f'<svg class="bc-code128" xmlns="http://www.w3.org/2000/svg" '
        f'width="{width_in:.4f}in" height="{height_in:.4f}in" '
        f'viewBox="0 0 {total_w} {height_modules}" '
        f'preserveAspectRatio="xMinYMid meet" shape-rendering="crispEdges">'
        f'<rect x="0" y="0" width="{total_w}" height="{height_modules}" '
        f'fill="#fff"/>'
        f'<g fill="#000">{"".join(rects)}</g>'
        f'</svg>'
    )
