"""Parse and validate the label data JSON.

Product labels use a flat ``fields`` map. Logistic labels use shipment-level
fields (ship_from, ship_to, customer_po, optional po_split) plus an ``items``
array of PO line items; each item carries its own quantity (the line total),
date/lot/COO/part/line and an optional master_carton_quantity that splits the
line into cartons.

Backward compatible: a logistic ``fields`` map without ``items`` is treated as
a single line item built from the flat per-line keys (and an optional top-level
``print_run`` block, kept for older files).

Returns (label_type, payload, warnings):
  * product  -> payload = {"fields": {...}}
  * logistic -> payload = {"shipment": {...}, "items": [ {...}, ... ]}
"""
from __future__ import annotations

import json
from pathlib import Path

from . import spec


class ValidationError(ValueError):
    pass


def _is_code128_safe(value: str) -> bool:
    return all(0x20 <= ord(ch) <= 0x7E for ch in value)


def load(path) -> dict:
    text = Path(path).read_text(encoding="utf-8")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValidationError(f"{path}: invalid JSON - {exc}") from exc
    if not isinstance(data, dict):
        raise ValidationError(f"{path}: top level must be a JSON object")
    return data


def _clean_barcode_value(key: str, value) -> str:
    meta = spec.FIELDS[key]
    value = "" if value is None else str(value)
    if meta["max_len"] is not None and len(value) > meta["max_len"]:
        raise ValidationError(
            f"{key}: value {value!r} exceeds max length {meta['max_len']}")
    if not _is_code128_safe(value):
        raise ValidationError(
            f"{key}: value {value!r} contains characters Code 128 cannot encode "
            f"(only printable ASCII 0x20-0x7E is allowed)")
    return value


def _clean_text_value(value) -> list:
    lines = value if isinstance(value, list) else [value]
    return [str(s) for s in lines if str(s).strip() != ""]


def _soft_checks(fields: dict, warnings: list, prefix: str = ""):
    coo = fields.get("country_of_origin")
    if coo and not (len(coo) == 2 and coo.isalpha()):
        warnings.append(
            f"{prefix}country_of_origin={coo!r} is not a 2-letter ISO 3166 "
            f"alpha-2 code")
    qty = fields.get("quantity")
    if qty and not str(qty).isdigit():
        warnings.append(f"{prefix}quantity={qty!r} is not all digits")
    dc = fields.get("date_code")
    if dc and not (len(str(dc)) == 4 and str(dc).isdigit()):
        warnings.append(
            f"{prefix}date_code={dc!r} is not in the recommended YYWW shape")


def _resolve_dis(fields: dict):
    for key in fields:
        if (not key.endswith("_di") and key in spec.FIELDS
                and spec.FIELDS[key]["kind"] == "barcode"):
            spec.resolved_di(key, fields)


# --------------------------------------------------------------------------- #
# product
# --------------------------------------------------------------------------- #
def _validate_product(data: dict, raw_fields: dict, warnings: list) -> dict:
    if data.get("print_run") is not None:
        raise ValidationError("print_run is only valid for logistic labels")
    if "items" in raw_fields:
        raise ValidationError("items[] is only valid for logistic labels")

    required = spec.LABELS["product"]["required"]
    for key in required:
        if key not in raw_fields:
            raise ValidationError(f"required field missing: {key}")

    fields: dict = {}
    for key, value in raw_fields.items():
        if key.endswith("_di") and key[:-3] in spec.FIELDS:
            fields[key] = str(value)
            continue
        if key not in spec.FIELDS:
            warnings.append(f"unknown field ignored: {key}")
            continue
        if spec.FIELDS[key]["kind"] == "text":
            warnings.append(f"{key} is not a product field; ignored")
            continue
        v = _clean_barcode_value(key, value)
        if v == "":
            if key in required:
                raise ValidationError(f"required field empty: {key}")
            continue
        fields[key] = v

    _resolve_dis(fields)
    _soft_checks(fields, warnings)
    return fields


# --------------------------------------------------------------------------- #
# logistic
# --------------------------------------------------------------------------- #
def _validate_item(item, warnings: list, index: int) -> dict:
    if not isinstance(item, dict):
        raise ValidationError(f"items[{index}] must be a JSON object")

    for key in spec.LOGISTIC_ITEM_REQUIRED:
        if key not in item:
            raise ValidationError(f"items[{index}]: required field missing: {key}")

    cleaned: dict = {}

    if item.get("master_carton_quantity") is not None:
        try:
            master = int(item["master_carton_quantity"])
        except (TypeError, ValueError):
            raise ValidationError(
                f"items[{index}]: master_carton_quantity must be an integer")
        if master <= 0:
            raise ValidationError(
                f"items[{index}]: master_carton_quantity must be positive")
        cleaned["master_carton_quantity"] = master
    if "po_split" in item:
        cleaned["po_split"] = str(item["po_split"])

    for key, value in item.items():
        if key in ("master_carton_quantity", "po_split"):
            continue
        if key.endswith("_di") and key[:-3] in spec.FIELDS:
            cleaned[key] = str(value)
            continue
        if key == "quantity":
            try:
                q = int(value)
            except (TypeError, ValueError):
                raise ValidationError(f"items[{index}]: quantity must be an integer")
            if q <= 0:
                raise ValidationError(f"items[{index}]: quantity must be positive")
            if len(str(q)) > spec.FIELDS["quantity"]["max_len"]:
                raise ValidationError(
                    f"items[{index}]: quantity {q} exceeds "
                    f"{spec.FIELDS['quantity']['max_len']} digits")
            cleaned["quantity"] = str(q)
            continue
        if key not in spec.FIELDS:
            warnings.append(f"items[{index}]: unknown field ignored: {key}")
            continue
        if spec.FIELDS[key]["kind"] == "text":
            warnings.append(f"items[{index}]: {key} is not an item field; ignored")
            continue
        v = _clean_barcode_value(key, value)
        if v == "":
            if key in spec.LOGISTIC_ITEM_REQUIRED:
                raise ValidationError(f"items[{index}]: required field empty: {key}")
            continue
        cleaned[key] = v

    if "master_carton_quantity" in cleaned and "package_id" in cleaned:
        warnings.append(
            f"items[{index}]: package_id is ignored when master_carton_quantity "
            f"splits the line (IDs are generated per carton)")

    _resolve_dis(cleaned)
    _soft_checks(cleaned, warnings, prefix=f"items[{index}]: ")
    return cleaned


def _validate_logistic(data: dict, raw_fields: dict, warnings: list):
    for key in spec.LOGISTIC_SHIPMENT_REQUIRED:
        if key not in raw_fields:
            raise ValidationError(f"required field missing: {key}")

    shipment: dict = {}
    for key in ("ship_from", "ship_to"):
        lines = _clean_text_value(raw_fields[key])
        if not lines:
            raise ValidationError(f"required field empty: {key}")
        shipment[key] = lines
    cpo = _clean_barcode_value("customer_po", raw_fields["customer_po"])
    if cpo == "":
        raise ValidationError("required field empty: customer_po")
    shipment["customer_po"] = cpo
    if "po_split" in raw_fields:
        shipment["po_split"] = str(raw_fields["po_split"])
    if "customer_po_di" in raw_fields:
        shipment["customer_po_di"] = str(raw_fields["customer_po_di"])

    new_format = "items" in raw_fields
    if new_format:
        items_raw = raw_fields["items"]
        if not isinstance(items_raw, list) or not items_raw:
            raise ValidationError("'items' must be a non-empty array")
        if data.get("print_run") is not None:
            warnings.append("print_run is ignored when items[] is used")
        known_top = (set(spec.LOGISTIC_SHIPMENT_REQUIRED)
                     | {"po_split", "items", "customer_po_di"})
        for key in raw_fields:
            if key in known_top:
                continue
            warnings.append(
                f"top-level field {key!r} ignored; item fields go inside items[]")
        items = [_validate_item(it, warnings, i)
                 for i, it in enumerate(items_raw, 1)]
    else:
        item: dict = {}
        for key, value in raw_fields.items():
            if key in ("ship_from", "ship_to", "customer_po", "po_split",
                       "customer_po_di", "items"):
                continue
            if key.endswith("_di") and key[:-3] in spec.FIELDS:
                item[key] = str(value)
                continue
            if key in spec.FIELDS or key == "master_carton_quantity":
                item[key] = value
            else:
                warnings.append(f"unknown field ignored: {key}")
        pr = data.get("print_run")
        if pr is not None:
            if not isinstance(pr, dict):
                raise ValidationError("print_run must be a JSON object")
            try:
                item["quantity"] = int(pr["total_quantity"])
                item["master_carton_quantity"] = int(pr["master_carton_quantity"])
            except KeyError as exc:
                raise ValidationError(f"print_run missing {exc.args[0]!r}") from exc
            except (TypeError, ValueError) as exc:
                raise ValidationError(
                    "print_run quantities must be integers") from exc
        if "quantity" not in item:
            raise ValidationError("required field missing: quantity")
        items = [_validate_item(item, warnings, 1)]

    return shipment, items


# --------------------------------------------------------------------------- #
# entry point
# --------------------------------------------------------------------------- #
def validate(data: dict):
    warnings: list = []

    label_type = data.get("label_type")
    if label_type not in spec.LABELS:
        raise ValidationError(
            f"label_type must be one of {sorted(spec.LABELS)}, got {label_type!r}")

    raw_fields = data.get("fields")
    if not isinstance(raw_fields, dict):
        raise ValidationError("'fields' must be a JSON object")

    if label_type == "product":
        fields = _validate_product(data, raw_fields, warnings)
        return label_type, {"fields": fields}, warnings

    shipment, items = _validate_logistic(data, raw_fields, warnings)
    return label_type, {"shipment": shipment, "items": items}, warnings