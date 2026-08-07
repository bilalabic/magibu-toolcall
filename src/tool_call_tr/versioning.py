"""Semantic-version parsing and project-specific development gates."""

from __future__ import annotations

from dataclasses import dataclass
import re


SEMVER_RE = re.compile(
    r"^(?P<major>0|[1-9][0-9]*)\."
    r"(?P<minor>0|[1-9][0-9]*)\."
    r"(?P<patch>0|[1-9][0-9]*)"
    r"(?:-(?P<prerelease>(?:0|[1-9][0-9]*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*)(?:\.(?:0|[1-9][0-9]*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*))*))?"
    r"(?:\+(?P<build>[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)
TOOL_ID_RE = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*\.v(?P<major>[1-9][0-9]*)$")


class VersionError(ValueError):
    pass


@dataclass(frozen=True, order=True, slots=True)
class SemanticVersion:
    major: int
    minor: int
    patch: int
    prerelease: str | None = None
    build: str | None = None

    @classmethod
    def parse(cls, value: str) -> "SemanticVersion":
        match = SEMVER_RE.fullmatch(value)
        if not match:
            raise VersionError(f"invalid semantic version: {value}")
        return cls(
            int(match.group("major")),
            int(match.group("minor")),
            int(match.group("patch")),
            match.group("prerelease"),
            match.group("build"),
        )

    @property
    def is_development(self) -> bool:
        return self.major == 0


def require_development_version(value: str) -> SemanticVersion:
    version = SemanticVersion.parse(value)
    if not version.is_development:
        raise VersionError("pilot schema and registry versions must remain in 0.x")
    return version


def validate_tool_id_major(tool_id: str, tool_version: str) -> bool:
    match = TOOL_ID_RE.fullmatch(tool_id)
    if not match:
        return False
    return int(match.group("major")) == SemanticVersion.parse(tool_version).major


VERSION_CHANGE_POLICY = {
    "schema_required_field_changed": "schema_version",
    "schema_field_type_changed": "schema_version",
    "messages_incompatible": "schema_version",
    "tool_call_incompatible": "schema_version",
    "tool_added": "tool_registry_version",
    "tool_removed": "tool_registry_version",
    "tool_input_changed": "tool_registry_version",
    "tool_output_changed": "tool_registry_version",
    "tool_required_parameters_changed": "tool_registry_version",
    "tool_execution_environment_changed": "tool_registry_version",
    "tool_schema_incompatible": "tool_id_major",
    "description_only": "patch_only",
}


def version_target_for(change: str) -> str:
    try:
        return VERSION_CHANGE_POLICY[change]
    except KeyError as exc:
        raise VersionError(f"unknown version change: {change}") from exc

