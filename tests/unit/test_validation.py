from __future__ import annotations

import copy
import json
from pathlib import Path

from tool_call_tr.registry import ToolRegistry
from tool_call_tr.validation import RuleBasedValidator


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def codes(report) -> set[str]:
    return {issue.code for issue in report.issues}


def validator() -> RuleBasedValidator:
    return RuleBasedValidator(registry=ToolRegistry.load(ROOT / "registry" / "registry.jsonl"))


def test_valid_dataset_benchmark_and_blueprints_pass_all_layers() -> None:
    validate = validator()
    for name in ("valid_single_tool.json", "valid_no_tool.json", "valid_missing_parameter.json"):
        assert validate.validate_record("dataset", load(FIXTURES / "dataset" / name)).valid
    assert validate.validate_record("benchmark", load(FIXTURES / "benchmark" / "valid_tool_call.json")).valid
    for path in (FIXTURES / "blueprints" / "valid").glob("*.json"):
        assert validate.validate_record("blueprint", load(path)).valid, path.name


def test_tool_argument_required_type_additional_and_enum_errors() -> None:
    validate = validator()
    base = load(FIXTURES / "dataset" / "valid_single_tool.json")
    arguments = base["messages"][1]["tool_calls"][0]["function"]["arguments"]
    del arguments["right"]
    arguments["left"] = "on iki"
    arguments["unsupported"] = True
    report = validate.validate_record("dataset", base)
    assert {"ARG_REQUIRED", "ARG_TYPE", "ARG_UNSUPPORTED"} <= codes(report)

    weather = load(FIXTURES / "blueprints" / "valid" / "multi_turn.json")
    weather["expected_tool_calls"][0]["function"]["arguments"]["unit"] = "kelvin"
    assert "ARG_ENUM" in codes(validate.validate_record("blueprint", weather))


def test_unknown_function_and_call_result_consistency_errors() -> None:
    validate = validator()
    record = load(FIXTURES / "dataset" / "valid_single_tool.json")
    record["messages"][1]["tool_calls"][0]["function"]["name"] = "utility_unknown"
    assert "FUNCTION_NOT_IN_REGISTRY" in codes(validate.validate_record("dataset", record))

    record = load(FIXTURES / "dataset" / "valid_single_tool.json")
    record["messages"][2]["tool_call_id"] = "call_999"
    result_codes = codes(validate.validate_record("dataset", record))
    assert {"UNMATCHED_TOOL_RESULT", "MISSING_TOOL_RESULT"} <= result_codes

    record = load(FIXTURES / "dataset" / "valid_single_tool.json")
    record["messages"][2]["name"] = "utility_multiply"
    assert "TOOL_RESULT_NAME_MISMATCH" in codes(validate.validate_record("dataset", record))


def _multi_tool_record(sequential: bool = False) -> dict:
    record = load(FIXTURES / "dataset" / "valid_single_tool.json")
    multiply = copy.deepcopy(record["tools"][0])
    multiply["function"]["name"] = "utility_multiply"
    multiply["function"]["description"] = "İki sayıyı deterministik olarak çarpar."
    record["tools"].append(multiply)
    call_2 = {
        "id": "call_002", "type": "function",
        "function": {"name": "utility_multiply", "arguments": {"left": 12, "right": 8}}
    }
    result_2 = {"role": "tool", "tool_call_id": "call_002", "name": "utility_multiply", "content": "{\"result\":96}"}
    record["metadata"]["main_category"] = "multi_tool"
    record["metadata"]["secondary_tags"] = ["sequential_tool" if sequential else "parallel_tool"]
    if sequential:
        record["messages"] = [record["messages"][0], record["messages"][1], record["messages"][2], {"role": "assistant", "content": None, "tool_calls": [call_2]}, result_2, record["messages"][3]]
    else:
        record["messages"][1]["tool_calls"].append(call_2)
        record["messages"].insert(3, result_2)
    return record


def test_parallel_and_sequential_structure_rules() -> None:
    validate = validator()
    assert validate.validate_record("dataset", _multi_tool_record()).valid
    assert validate.validate_record("dataset", _multi_tool_record(sequential=True)).valid
    invalid = _multi_tool_record(sequential=True)
    invalid["messages"][2], invalid["messages"][3] = invalid["messages"][3], invalid["messages"][2]
    assert "SEQUENTIAL_ORDER_INVALID" in codes(validate.validate_record("dataset", invalid))

    invalid_parallel = _multi_tool_record(sequential=True)
    invalid_parallel["metadata"]["secondary_tags"] = ["parallel_tool"]
    assert "PARALLEL_STRUCTURE_INVALID" in codes(validate.validate_record("dataset", invalid_parallel))

    duplicate = _multi_tool_record()
    duplicate["messages"][1]["tool_calls"][1]["id"] = "call_001"
    assert "DUPLICATE_TOOL_CALL_ID" in codes(validate.validate_record("dataset", duplicate))


def test_category_final_method_execution_and_review_rules() -> None:
    validate = validator()
    record = load(FIXTURES / "dataset" / "valid_single_tool.json")
    del record["metadata"]["final_response_method"]
    assert "FINAL_RESPONSE_METHOD_REQUIRED" in codes(validate.validate_record("dataset", record))

    record = load(FIXTURES / "dataset" / "valid_no_tool.json")
    record["metadata"]["main_category"] = "multi_turn"
    assert "CATEGORY_PRIORITY_MISMATCH" in codes(validate.validate_record("dataset", record))

    record = load(FIXTURES / "dataset" / "valid_single_tool.json")
    record["metadata"]["validation"]["language"] = "not_run"
    assert "REVIEW_ACCEPTED_BEFORE_VALIDATION" in codes(validate.validate_record("dataset", record))


def test_internal_operation_markers_are_blocked_in_natural_text_and_blueprints() -> None:
    validate = validator()
    record = load(FIXTURES / "dataset" / "valid_single_tool.json")
    record["metadata"]["review"]["status"] = "needs_revision"
    record["messages"][-1]["content"] = "Bu sonuç sentetik fixture üzerinden hazırlandı."
    assert "NATURAL_TEXT_INTERNAL_MARKER" in codes(validate.validate_record("dataset", record))

    blueprint = load(FIXTURES / "blueprints" / "valid" / "no_tool.json")
    blueprint["user_goal"] = "Sentetik bir fixture hakkında bilgi istemek"
    assert "BLUEPRINT_INTERNAL_MARKER" in codes(validate.validate_record("blueprint", blueprint))

    blueprint["metadata"]["secondary_tags"].append("internal_marker_topic")
    assert "BLUEPRINT_INTERNAL_MARKER" not in codes(validate.validate_record("blueprint", blueprint))


def test_benchmark_decision_and_expected_arguments() -> None:
    validate = validator()
    record = load(FIXTURES / "benchmark" / "valid_tool_call.json")
    record["expected"] = {"decision": "direct_answer", "missing_parameters": [], "tool_calls": [], "response": "Doğrudan yanıt."}
    record["metadata"]["execution"] = {"type": "not_applicable", "status": "not_called"}
    assert "BENCHMARK_DECISION_INCONSISTENT" in codes(validate.validate_record("benchmark", record))


def test_parameter_format_values_are_checked() -> None:
    base_registry = ToolRegistry.load(ROOT / "registry" / "registry.jsonl")
    calendar = {
        "tool_registry_version": "0.1.0", "tool_id": "calendar.lookup.v1", "tool_version": "1.0.0", "domain": "calendar",
        "function": {"name": "calendar_lookup", "description": "Tarihi doğrular.", "parameters": {"type": "object", "properties": {"date": {"type": "string", "format": "date"}}, "required": ["date"], "additionalProperties": False}},
        "output_schema": {"type": "object", "properties": {"date": {"type": "string"}}, "required": ["date"], "additionalProperties": False},
        "execution": {"default_type": "mock", "supported_types": ["mock"], "fixture_ids": [], "resettable": False},
        "access": {"source": "test", "url": None, "authentication": "not_applicable", "credential_env_vars": [], "license": None, "license_url": None, "terms_checked_on": None},
        "risks": {"safety": "low", "freshness": "static", "personal_data": False, "side_effects": False, "notes": None}, "lifecycle": "demo"
    }
    custom = ToolRegistry([*base_registry.records, calendar])
    record = load(FIXTURES / "dataset" / "valid_single_tool.json")
    record["metadata"]["domain"] = "calendar"
    record["tools"] = [{"type": "function", "function": calendar["function"]}]
    record["messages"][1]["tool_calls"][0]["function"] = {"name": "calendar_lookup", "arguments": {"date": "06/08/2026"}}
    record["messages"][2]["name"] = "calendar_lookup"
    record["messages"][2]["content"] = '{"date":"2026-08-06"}'
    assert "ARG_FORMAT" in codes(RuleBasedValidator(registry=custom).validate_record("dataset", record))


def test_jsonl_parsing_reports_line_and_cli_ready_shape(tmp_path: Path) -> None:
    path = tmp_path / "records.jsonl"
    valid = (FIXTURES / "dataset" / "valid_no_tool.json").read_text(encoding="utf-8").replace("\n", "")
    path.write_text(valid + "\n{broken\n", encoding="utf-8")
    report = validator().validate_path("dataset", path)
    assert "JSONL_RECORD_PARSE_ERROR" in codes(report)
    issue = next(issue for issue in report.issues if issue.code == "JSONL_RECORD_PARSE_ERROR")
    assert issue.line == 2
    assert report.to_dict()["valid"] is False

    json_path = tmp_path / "broken.json"
    json_path.write_text("{broken", encoding="utf-8")
    assert "JSON_PARSE_ERROR" in codes(validator().validate_path("dataset", json_path))
