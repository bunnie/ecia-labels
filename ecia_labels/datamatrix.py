"""Data Matrix ECC-200 (ISO/IEC 15434 Format 06) message + SVG.

Two responsibilities:

1. ``build_format06`` assembles the data stream exactly as EIGP 114 B.3
   specifies::

       [)>  RS  06  GS  <DI><val>  GS  <DI><val>  GS ... <DI><val>  RS  EOT

   with RS = 0x1E, GS = 0x1D, EOT = 0x04 and the compliance indicator "[)>".

2. ``datamatrix_svg`` encodes that string as an ECC-200 symbol (via the
   pure-Python ``pystrich`` encoder, which yields the module matrix) and
   renders it as inline SVG with a quiet zone.

EIGP 114 Appendix B constraints honoured by the defaults:
  * ECC-200 mandatory                 -> pystrich produces ECC-200
  * X-dimension >= 14.6 mil           -> DEFAULT_MODULE_IN = 0.020"
  * quiet zone >= 1 X-dimension       -> DEFAULT_QUIET_MODULES = 2 (>= min)
"""
from __future__ import annotations

from pystrich.datamatrix import DataMatrixEncoder

from . import spec

DEFAULT_MODULE_IN = 0.020      # 20 mil (min allowed is 14.6 mil)
# pystrich's renderer already adds a 2-module quiet zone (ECIA minimum is 1),
# so no extra quiet zone is added by default.
DEFAULT_QUIET_MODULES = 0


def build_format06(elements: list[tuple[str, str]]) -> str:
    """Build the Format 06 message string from (data_identifier, value) pairs."""
    header = spec.COMPLIANCE_INDICATOR + spec.RS + spec.FORMAT_INDICATOR + spec.GS
    stream = spec.GS.join(di + value for di, value in elements)
    trailer = spec.RS + spec.EOT
    return header + stream + trailer


def encode_matrix(message: str):
    """Return the full ECC-200 symbol grid (rows of 0/1) for ``message``.

    ``DataMatrixEncoder.matrix`` is only the bare data region; the renderer is
    what adds the finder pattern (solid L + clock track) and quiet zone that a
    scanner needs, so we take the renderer's final matrix.
    """
    # latin-1 keeps every byte (incl. the 0x1D/0x1E/0x04 separators) intact.
    enc = DataMatrixEncoder(message.encode("latin-1").decode("latin-1"))
    return enc.init_renderer().matrix


def datamatrix_svg(message: str, module_in: float = DEFAULT_MODULE_IN,
                   quiet_modules: int = DEFAULT_QUIET_MODULES) -> str:
    """Render ``message`` as an inline Data Matrix ECC-200 SVG string."""
    matrix = encode_matrix(message)
    n = len(matrix)
    total = n + 2 * quiet_modules

    rects = []
    for r, row in enumerate(matrix):
        c = 0
        while c < n:
            if row[c]:
                start = c
                while c < n and row[c]:
                    c += 1
                rects.append(
                    f'<rect x="{quiet_modules + start}" '
                    f'y="{quiet_modules + r}" width="{c - start}" height="1"/>'
                )
            else:
                c += 1

    side_in = total * module_in
    return (
        f'<svg class="bc-datamatrix" xmlns="http://www.w3.org/2000/svg" '
        f'width="{side_in:.4f}in" height="{side_in:.4f}in" '
        f'viewBox="0 0 {total} {total}" shape-rendering="crispEdges">'
        f'<rect x="0" y="0" width="{total}" height="{total}" fill="#fff"/>'
        f'<g fill="#000">{"".join(rects)}</g>'
        f'</svg>'
    )
