"""Parse and validate the label data JSON.

Hard errors (raise ValueError, abort):
  * unknown label_type
  * a required field missing or empty
  * a value longer than the field's max length
  * a value containing characters Code 128 cannot encode (non-printable /
    non-ASCII)

Soft warnings (collected, printed, but do not abort):
  * country_of_origin not two ASCII letters
  * quantity not all digits
  * date code not in the YYWW shape (4 digits) the spec recommends
"""
from __future__ import annotations

import json
from pathlib import Path

from . import spec


class ValidationError(ValueError):
    pass


def _is_code128_safe(value: str) -> bool:
    # Code 128 (sets A/B/C) can carry full ASCII; we restrict to the printable
    # range 0x20-0x7E so the human-readable text and barcode always agree and
    # nothing exotic sneaks in.
    return all(0x20 <= ord(ch) <= 0x7E for ch in value)


def load(path) -> dict:
    """Load and parse the data JSON, returning the raw dict."""
    text = Path(path).read_text(encoding="utf-8")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValidationError(f"{path}: invalid JSON - {exc}") from exc
    if not isinstance(data, dict):
        raise ValidationError(f"{path}: top level must be a JSON object")
    return data


def validate(data: dict):
    """Validate a parsed data dict. Returns (label_type, fields, warnings)."""
    warnings: list[str] = []

    label_type = data.get("label_type")
    if label_type not in spec.LABELS:
        raise ValidationError(
            f"label_type must be one of {sorted(spec.LABELS)}, got {label_type!r}"
        )

    raw_fields = data.get("fields")
    if not isinstance(raw_fields, dict):
        raise ValidationError("'fields' must be a JSON object")

    required = spec.LABELS[label_type]["required"]

    # Required-field presence.
    for key in required:
        if key not in raw_fields:
            raise ValidationError(f"required field missing: {key}")

    fields: dict[str, object] = {}
    for key, value in raw_fields.items():
        if key not in spec.FIELDS:
            warnings.append(f"unknown field ignored: {key}")
            continue
        meta = spec.FIELDS[key]

        if meta["kind"] == "text":
            # Address blocks: accept a string or a list of lines.
            lines = value if isinstance(value, list) else [value]
            lines = [str(s) for s in lines if str(s).strip() != ""]
            if not lines and key in required:
                raise ValidationError(f"required field empty: {key}")
            fields[key] = lines
            continue

        value = "" if value is None else str(value)
        if value == "":
            if key in required:
                raise ValidationError(f"required field empty: {key}")
            continue

        if meta["max_len"] is not None and len(value) > meta["max_len"]:
            raise ValidationError(
                f"{key}: value {value!r} exceeds max length {meta['max_len']}"
            )
        if not _is_code128_safe(value):
            raise ValidationError(
                f"{key}: value {value!r} contains characters Code 128 cannot "
                f"encode (only printable ASCII 0x20-0x7E is allowed)"
            )
        fields[key] = value

    # Resolve any DI overrides early so errors surface here.
    for key in fields:
        if spec.FIELDS[key]["kind"] == "barcode":
            spec.resolved_di(key, raw_fields)

    # Soft format checks.
    coo = fields.get("country_of_origin")
    if coo and not (len(coo) == 2 and coo.isalpha()):
        warnings.append(
            f"country_of_origin={coo!r} is not a 2-letter ISO 3166 alpha-2 code"
        )
    qty = fields.get("quantity")
    if qty and not qty.isdigit():
        warnings.append(f"quantity={qty!r} is not all digits")
    dc = fields.get("date_code")
    if dc and not (len(dc) == 4 and dc.isdigit()):
        warnings.append(
            f"date_code={dc!r} is not in the recommended YYWW (4-digit) shape"
        )

    return label_type, fields, warnings
