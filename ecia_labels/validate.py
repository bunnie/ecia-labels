"""Parse and validate the label data JSON.

Hard errors (raise ValidationError, abort):
  * unknown label_type
  * a required field missing or empty
  * a value longer than the field's max length
  * a value containing characters Code 128 cannot encode (non-printable /
    non-ASCII)
  * print_run on a non-logistic label, or with non-positive quantities

Soft warnings (collected, printed, but do not abort):
  * country_of_origin not two ASCII letters
  * quantity not all digits
  * date code not in the YYWW shape (4 digits) the spec recommends
  * quantity / package_id supplied alongside a print_run (they are derived)

Returns (label_type, fields, print_run, warnings). ``print_run`` is None for a
single label, or {"total_quantity": int, "master_carton_quantity": int}.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import spec


class ValidationError(ValueError):
    pass


def _is_code128_safe(value: str) -> bool:
    # Code 128 (sets A/B/C) can carry full ASCII; we restrict to the printable
    # range 0x20-0x7E so the human-readable text and barcode always agree.
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


def _parse_print_run(data: dict, label_type: str):
    pr = data.get("print_run")
    if pr is None:
        return None
    if label_type != "logistic":
        raise ValidationError("print_run is only valid for logistic labels")
    if not isinstance(pr, dict):
        raise ValidationError("print_run must be a JSON object")
    try:
        total = int(pr["total_quantity"])
        master = int(pr["master_carton_quantity"])
    except KeyError as exc:
        raise ValidationError(f"print_run missing {exc.args[0]!r}") from exc
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            "print_run total_quantity and master_carton_quantity must be "
            "integers") from exc
    if total <= 0 or master <= 0:
        raise ValidationError("print_run quantities must be positive")
    return {"total_quantity": total, "master_carton_quantity": master}


def validate(data: dict):
    """Validate a parsed data dict.

    Returns (label_type, fields, print_run, warnings).
    """
    warnings: list[str] = []

    label_type = data.get("label_type")
    if label_type not in spec.LABELS:
        raise ValidationError(
            f"label_type must be one of {sorted(spec.LABELS)}, got {label_type!r}"
        )

    raw_fields = data.get("fields")
    if not isinstance(raw_fields, dict):
        raise ValidationError("'fields' must be a JSON object")

    print_run = _parse_print_run(data, label_type)

    required = list(spec.LABELS[label_type]["required"])
    if print_run is not None:
        # quantity and package_id are derived per label, not supplied.
        for derived in ("quantity", "package_id"):
            if derived in required:
                required.remove(derived)
            if derived in raw_fields:
                warnings.append(
                    f"{derived} is ignored when print_run is set (it is derived "
                    f"per label)")

    # Required-field presence.
    for key in required:
        if key not in raw_fields:
            raise ValidationError(f"required field missing: {key}")

    fields: dict = {}
    for key, value in raw_fields.items():
        # "<field>_di" keys are DI overrides handled by spec.resolved_di.
        if key.endswith("_di") and key[:-3] in spec.FIELDS:
            continue
        if key not in spec.FIELDS:
            warnings.append(f"unknown field ignored: {key}")
            continue
        meta = spec.FIELDS[key]

        if meta["kind"] == "text":
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

    return label_type, fields, print_run, warnings