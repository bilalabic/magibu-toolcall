"""JSON Schema loading and validation. Schema files are authoritative."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError
from referencing import Registry, Resource

from tool_call_tr.config import Settings


SCHEMA_FILES = {
    "dataset": "dataset.schema.json",
    "benchmark": "benchmark.schema.json",
    "registry": "tool_registry.schema.json",
    "blueprint": "scenario_blueprint.schema.json",
    "source": "source_record.schema.json",
    "job": "job_manifest.schema.json",
    "access": "access_policy.schema.json",
}


class SchemaStore:
    def __init__(self, schemas_dir: Path | None = None) -> None:
        self.schemas_dir = schemas_dir or Settings.from_env().schemas_dir
        self._schemas: dict[str, dict[str, Any]] = {}
        resources: list[tuple[str, Resource[Any]]] = []
        for path in sorted(self.schemas_dir.glob("*.schema.json")):
            schema = json.loads(path.read_text(encoding="utf-8"))
            Draft202012Validator.check_schema(schema)
            schema_id = schema.get("$id")
            if not schema_id:
                raise ValueError(f"schema has no $id: {path}")
            self._schemas[path.name] = schema
            resources.append((schema_id, Resource.from_contents(schema)))
        self._registry = Registry().with_resources(resources)

    def load(self, kind: str) -> dict[str, Any]:
        try:
            filename = SCHEMA_FILES[kind]
            return self._schemas[filename]
        except KeyError as exc:
            raise ValueError(f"unknown or unavailable schema kind: {kind}") from exc

    def validator(self, kind: str) -> Draft202012Validator:
        return Draft202012Validator(
            self.load(kind),
            registry=self._registry,
            format_checker=FormatChecker(),
        )

    def errors(self, kind: str, record: Any) -> list[ValidationError]:
        return sorted(
            self.validator(kind).iter_errors(record),
            key=lambda error: (list(error.absolute_path), error.message),
        )

    def validate(self, kind: str, record: Any) -> None:
        self.validator(kind).validate(record)


def json_path(error: ValidationError) -> str:
    parts = [str(part) if isinstance(part, int) else str(part) for part in error.absolute_path]
    return "$" + "".join(f"[{p}]" if p.isdigit() else f".{p}" for p in parts)
