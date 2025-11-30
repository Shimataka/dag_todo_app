import json
from typing import Any, Literal

import yaml  # type: ignore[import-untyped]
from pyresults import Err, Ok, Result


def serialize(
    metadata: str,
    parser: Literal["json", "yaml"] | None = None,
) -> Result[dict[str, Any], str]:
    by_json = serialize_by_json(metadata)
    by_yaml = serialize_by_yaml(metadata)
    match parser:
        case "json":
            return by_json
        case "yaml":
            return by_yaml
        case None:
            if by_json.is_ok():
                return by_json
            if by_yaml.is_ok():
                return by_yaml
            return Err(f"Invalid metadata: {metadata!s}")


def deserialize(
    metadata: dict[str, Any],
    parser: Literal["json", "yaml"] | None = None,
) -> Result[str, str]:
    by_json = deserialize_by_json(metadata)
    by_yaml = deserialize_by_yaml(metadata)
    match parser:
        case "json":
            return by_json
        case "yaml":
            return by_yaml
        case None:
            if by_json.is_ok():
                return by_json
            if by_yaml.is_ok():
                return by_yaml
            return Err(f"Invalid metadata: {metadata!s}")


def serialize_by_json(metadata: str) -> Result[dict[str, Any], str]:
    try:
        return Ok(json.loads(metadata))
    except json.JSONDecodeError as e:
        return Err(f"Invalid JSON: {e!s}")
    except Exception as e:  # noqa: BLE001
        return Err(f"Unknown error: {e!s}")


def deserialize_by_json(metadata: dict[str, Any]) -> Result[str, str]:
    try:
        return Ok(json.dumps(metadata))
    except json.JSONDecodeError as e:
        return Err(f"Invalid JSON: {e!s}")
    except Exception as e:  # noqa: BLE001
        return Err(f"Unknown error: {e!s}")


def serialize_by_yaml(metadata: str) -> Result[dict[str, Any], str]:
    try:
        return Ok(yaml.safe_load(metadata))
    except Exception as e:  # noqa: BLE001
        return Err(f"Unknown error: {e!s}")


def deserialize_by_yaml(metadata: dict[str, Any]) -> Result[str, str]:
    try:
        return Ok(yaml.safe_dump(metadata))
    except yaml.YAMLError as e:
        return Err(f"Invalid YAML: {e!s}")
    except Exception as e:  # noqa: BLE001
        return Err(f"Unknown error: {e!s}")
