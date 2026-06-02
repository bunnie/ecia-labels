"""Optional decode-based self-test.

Renders each generated symbol to a raster image and decodes it with
``zxing-cpp``, asserting the decoded payload matches what we encoded. This is
the strongest available check that the labels will actually scan. Both
dependencies are pip-only (no system libraries):

    pip install zxing-cpp pillow

If either import fails, ``available()`` returns False and the CLI skips the
self-test with a note rather than erroring.
"""
from __future__ import annotations

from . import barcodes, datamatrix

try:  # optional deps
    import zxingcpp
    from PIL import Image
    _OK = True
except Exception:  # pragma: no cover
    _OK = False


def available() -> bool:
    return _OK


def _bits_to_image(bits: str, scale: int = 3, height: int = 60, quiet: int = 20):
    width = (len(bits) + 2 * quiet) * scale
    img = Image.new("L", (width, height), 255)
    px = img.load()
    for i, b in enumerate(bits):
        if b == "1":
            x0 = (quiet + i) * scale
            for x in range(x0, x0 + scale):
                for y in range(height):
                    px[x, y] = 0
    return img


def _matrix_to_image(matrix, scale: int = 8, quiet: int = 4):
    n = len(matrix)
    side = (n + 2 * quiet) * scale
    img = Image.new("L", (side, side), 255)
    px = img.load()
    for r, row in enumerate(matrix):
        for c, v in enumerate(row):
            if v:
                x0, y0 = (quiet + c) * scale, (quiet + r) * scale
                for x in range(x0, x0 + scale):
                    for y in range(y0, y0 + scale):
                        px[x, y] = 0
    return img


def verify_code128(value: str) -> tuple[bool, str]:
    bits = barcodes.encode_code128(value)
    results = zxingcpp.read_barcodes(_bits_to_image(bits))
    if not results:
        return False, "no Code 128 symbol decoded"
    got = results[0].text
    if got != value:
        return False, f"decoded {got!r} != encoded {value!r}"
    return True, f"Code 128 OK: {value!r}"


def verify_datamatrix(message: str) -> tuple[bool, str]:
    matrix = datamatrix.encode_matrix(message)
    results = zxingcpp.read_barcodes(_matrix_to_image(matrix))
    if not results:
        return False, "no Data Matrix symbol decoded"
    got = results[0].bytes
    want = message.encode("latin-1")
    if bytes(got) != want:
        return False, "Data Matrix bytes mismatch"
    return True, f"Data Matrix OK: {len(want)} bytes round-tripped"
