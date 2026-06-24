"""Loading and validation of the GSY DEX "intelligent" ontology schemas.

The JSON Schemas under ``schemas/intelligent`` are the agreed data contract
between AMMBA and the GSY DEX off-chain storage. They are the single source of
truth for the shape of the objects that cross the service boundary — orders in,
trades and clearing results out — so the clearing node validates against them at
the I/O boundary rather than trusting hand-written dicts.

Validation uses a small, dependency-free checker that covers the subset of JSON
Schema (draft 2020-12) these files actually use: ``type`` (including nullable
unions), ``required``, ``properties``, ``additionalProperties: false``,
``enum``, ``format`` (``uuid`` / ``date-time``), ``pattern``, ``minimum`` /
``exclusiveMinimum``, ``items`` and ``$ref``. Pulling in the full ``jsonschema``
package was avoided on purpose to keep the dependency set (and the lockfile)
small — see the root ``CLAUDE.md`` note on dependency hygiene.
"""

import json
import re
from datetime import datetime
from functools import lru_cache
from pathlib import Path

SCHEMA_DIR = Path(__file__).parent.parent / "schemas" / "intelligent"

ORDER_SCHEMA = "int.order.schema.v1.json"
TRADE_SCHEMA = "int.trade.schema.v1.json"
CLEARING_RESULT_SCHEMA = "int.clearing-result.schema.v1.json"

_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-" r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


class SchemaValidationError(ValueError):
    """Raised when an instance does not conform to its ontology schema."""


@lru_cache(maxsize=1)
def _registry() -> dict:
    """Load every vendored schema, keyed by both filename and ``$id``."""
    reg: dict = {}
    for path in SCHEMA_DIR.glob("*.json"):
        with open(path) as f:
            schema = json.load(f)
        reg[path.name] = schema
        schema_id = schema.get("$id")
        if schema_id:
            reg[schema_id] = schema
    return reg


def load_schema(name: str) -> dict:
    reg = _registry()
    if name not in reg:
        raise KeyError(f"Schema not found: {name}")
    return reg[name]


def _resolve_ref(ref: str) -> dict:
    reg = _registry()
    # Relative refs look like "./int.order.schema.v1.json"; match on basename.
    basename = ref.split("/")[-1]
    if basename in reg:
        return reg[basename]
    if ref in reg:
        return reg[ref]
    raise KeyError(f"Cannot resolve $ref: {ref}")


def _is_datetime(value: str) -> bool:
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except (ValueError, AttributeError):
        return False


def _type_ok(value, type_name: str) -> bool:
    if type_name == "object":
        return isinstance(value, dict)
    if type_name == "array":
        return isinstance(value, list)
    if type_name == "string":
        return isinstance(value, str)
    if type_name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if type_name == "number":
        return isinstance(value, int | float) and not isinstance(value, bool)
    if type_name == "boolean":
        return isinstance(value, bool)
    if type_name == "null":
        return value is None
    return True


def _check(value, schema: dict, path: str, errors: list[str]) -> None:
    if "$ref" in schema:
        schema = _resolve_ref(schema["$ref"])

    declared_type = schema.get("type")
    if declared_type is not None:
        types = declared_type if isinstance(declared_type, list) else [declared_type]
        if not any(_type_ok(value, t) for t in types):
            errors.append(f"{path}: expected type {types}, got {type(value).__name__}")
            return  # Type is wrong; deeper checks would be noise.

    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: {value!r} not in enum {schema['enum']}")

    fmt = schema.get("format")
    if fmt and isinstance(value, str):
        if fmt == "uuid" and not _UUID_RE.match(value):
            errors.append(f"{path}: not a valid uuid: {value!r}")
        elif fmt == "date-time" and not _is_datetime(value):
            errors.append(f"{path}: not a valid ISO 8601 date-time: {value!r}")

    pattern = schema.get("pattern")
    if pattern and isinstance(value, str) and not re.search(pattern, value):
        errors.append(f"{path}: {value!r} does not match pattern {pattern}")

    if isinstance(value, int | float) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path}: {value} < minimum {schema['minimum']}")
        if "exclusiveMinimum" in schema and value <= schema["exclusiveMinimum"]:
            errors.append(f"{path}: {value} <= exclusiveMinimum {schema['exclusiveMinimum']}")

    if isinstance(value, dict) and (schema.get("type") == "object" or "properties" in schema):
        props = schema.get("properties", {})
        for required in schema.get("required", []):
            if required not in value:
                errors.append(f"{path}: missing required property '{required}'")
        if schema.get("additionalProperties") is False:
            for key in value:
                if key not in props:
                    errors.append(f"{path}: additional property '{key}' not allowed")
        for key, child in value.items():
            if key in props:
                _check(child, props[key], f"{path}.{key}", errors)

    if isinstance(value, list) and "items" in schema:
        for i, item in enumerate(value):
            _check(item, schema["items"], f"{path}[{i}]", errors)


def validate(instance, schema_name: str) -> None:
    """Validate ``instance`` against the named schema, raising on failure."""
    errors: list[str] = []
    _check(instance, load_schema(schema_name), "$", errors)
    if errors:
        raise SchemaValidationError(f"{schema_name} validation failed:\n  " + "\n  ".join(errors))


def validate_order(order: dict) -> None:
    validate(order, ORDER_SCHEMA)


def validate_trade(trade: dict) -> None:
    validate(trade, TRADE_SCHEMA)


def validate_clearing_result(result: dict) -> None:
    validate(result, CLEARING_RESULT_SCHEMA)
