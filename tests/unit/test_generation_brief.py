from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from tool_call_tr.generation.brief import GenerationBriefError, build_generation_brief
from tool_call_tr.text_quality import find_internal_operation_markers


ROOT = Path(__file__).resolve().parents[2]
VALID_BLUEPRINTS = ROOT / "tests" / "fixtures" / "blueprints" / "valid"


def load_blueprint(name: str) -> dict[str, Any]:
    path = ROOT / "tests" / "fixtures" / "blueprints" / "valid" / name
    return json.loads(path.read_text(encoding="utf-8"))


def test_valid_generation_briefs_exclude_internal_context() -> None:
    blueprints = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(VALID_BLUEPRINTS.glob("*.json"))
    ]
    assert blueprints
    for blueprint in blueprints:
        brief = build_generation_brief(blueprint)
        serialized = json.dumps(brief, ensure_ascii=False, sort_keys=True)
        assert not find_internal_operation_markers(serialized), blueprint["id"]
        assert "metadata" not in brief
        assert "intended_execution_type" not in serialized
        assert "fixture_id" not in serialized
        assert "provenance" not in serialized
        assert "data_version" not in serialized


def test_generation_brief_filters_internal_result_fields_and_values() -> None:
    blueprint = load_blueprint("single_tool.json")
    blueprint["expected_tool_result"] = {
        "value": 12,
        "source": "synthetic_pilot_fixture",
        "data_version": "synthetic-v1",
        "nested": {
            "label": "Kullanıcıya uygun sonuç",
            "internal_label": "Sentetik kayıt",
        },
    }
    brief = build_generation_brief(blueprint)
    assert brief["grounding_facts"] == {
        "value": 12,
        "nested": {"label": "Kullanıcıya uygun sonuç"},
    }


def test_generation_brief_blocks_natural_instruction_leak_before_provider() -> None:
    blueprint = load_blueprint("no_tool.json")
    blueprint["expected_final_behavior"] = "Kaydın sentetik olduğunu söylemek."
    with pytest.raises(GenerationBriefError, match="internal operation markers"):
        build_generation_brief(blueprint)


def test_generation_brief_allows_an_explicit_data_creation_topic() -> None:
    blueprint = copy.deepcopy(load_blueprint("no_tool.json"))
    blueprint["metadata"]["secondary_tags"].append("internal_marker_topic")
    blueprint["user_goal"] = "Sentetik veri kavramını öğrenmek"
    blueprint["expected_final_behavior"] = "Sentetik veriyi doğal Türkçe ile açıklamak."
    brief = build_generation_brief(blueprint)
    assert brief["user_goal"] == "Sentetik veri kavramını öğrenmek"


@pytest.mark.parametrize(
    "text",
    [
        "sentetiktir",
        "synthetic_pilot_fixture",
        "fixture'dan",
        "fikstürü",
        "simülasyonda",
    ],
)
def test_internal_marker_detection_covers_suffixes_and_machine_labels(text: str) -> None:
    assert find_internal_operation_markers(text)
