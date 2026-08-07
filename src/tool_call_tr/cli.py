"""Command-line entry point with isolated dataset and benchmark lifecycles."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
from typing import Any

from jsonschema.exceptions import ValidationError as JsonSchemaValidationError

from tool_call_tr import __version__
from tool_call_tr.access import (
    AccessDenied,
    AccessPolicy,
    AccessPolicyError,
    append_audit_event,
    verify_audit_log,
)
from tool_call_tr.config import Settings, redact_secret
from tool_call_tr.batch import (
    BatchError,
    collect_existing_ids,
    create_job_manifest,
    load_manifest,
    run_job,
    write_manifest,
)
from tool_call_tr.contamination import compare_corpora
from tool_call_tr.deduplication import DeterministicTokenSimilarity, compare_records
from tool_call_tr.dataset_workflow import (
    DatasetWorkflowError,
    dataset_record_paths,
    default_job_id,
    default_job_paths,
    inspect_blueprints,
    next_dataset_number,
    prepare_generated_candidate,
)
from tool_call_tr.evaluation import BenchmarkEvaluator, BenchmarkRunError, run_benchmark
from tool_call_tr.freeze import FreezeError, freeze_benchmark, verify_benchmark_freeze
from tool_call_tr.generation.providers import (
    DeepSeekIntegration,
    MockSemanticJudge,
    ProviderError,
    ProviderNotConfigured,
    RetryPolicy,
    run_with_retry,
)
from tool_call_tr.ids import IdError, generate_call_id, generate_record_id
from tool_call_tr.logging import configure_logging
from tool_call_tr.localization import LocalizationError, localize_items
from tool_call_tr.execution import (
    ExecutionEngine,
    ExecutionRequest,
    ExecutionRouter,
    ExecutionRoutingError,
    ExecutionStatus,
    ExecutionType,
    HttpJsonAdapter,
    LocalExecutableAdapter,
    MockAdapter,
)
from tool_call_tr.records import RecordIOError, load_records, write_records
from tool_call_tr.registry import ToolRegistry
from tool_call_tr.reporting import benchmark_run_report, corpus_report
from tool_call_tr.review import ReviewError, apply_review, export_accepted
from tool_call_tr.sources import SourceIngestionError, get_source_adapter, import_source
from tool_call_tr.semantic import CachedEmbeddingSimilarity, OpenAIEmbeddingProvider
from tool_call_tr.validation import RuleBasedValidator
from tool_call_tr.validation.parsing import parse_path


SOURCE_TYPES = ("translated", "original_turkish", "turkey_native")
OUTPUT_FORMATS = ("text", "json")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="magibu-toolcall",
        description="Operate isolated Turkish tool-calling dataset and benchmark lifecycles.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--log-level", choices=("DEBUG", "INFO", "WARNING", "ERROR"), default=None)
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")

    config = subparsers.add_parser("config", help="Show non-secret effective configuration.")
    config.set_defaults(handler=_cmd_config)

    dataset = subparsers.add_parser("dataset", help="Manage training-dataset records only.")
    dataset_commands = dataset.add_subparsers(dest="dataset_command", metavar="COMMAND", required=True)
    _add_record_commands(dataset_commands, "dataset", include_corpus_report=True)
    _add_dataset_source_commands(dataset_commands)
    _add_batch_commands(dataset_commands, "dataset")
    _add_dataset_generation_command(dataset_commands)

    benchmark = subparsers.add_parser("benchmark", help="Manage isolated benchmark gold and runs only.")
    benchmark_commands = benchmark.add_subparsers(dest="benchmark_command", metavar="COMMAND", required=True)
    _add_record_commands(benchmark_commands, "benchmark", include_corpus_report=False)
    _add_benchmark_commands(benchmark_commands)
    _add_batch_commands(benchmark_commands, "benchmark")
    _add_generation_command(benchmark_commands, "benchmark")

    _add_support_commands(subparsers)
    _add_access_commands(subparsers)
    return parser


def _add_record_commands(subparsers: argparse._SubParsersAction, kind: str, *, include_corpus_report: bool) -> None:
    generate = subparsers.add_parser("generate-id", help=f"Generate a deterministic {kind} record ID.")
    generate.add_argument("number", type=int)
    generate.add_argument("--source-type", choices=SOURCE_TYPES, required=True)
    generate.set_defaults(handler=_cmd_record_id, record_kind=kind)

    validate = subparsers.add_parser("validate", help=f"Validate {kind} JSON/JSONL records.")
    validate.add_argument("path", type=Path)
    validate.add_argument("--output", choices=OUTPUT_FORMATS, default="text")
    validate.set_defaults(handler=_cmd_validate, record_kind=kind)

    duplicates = subparsers.add_parser("check-duplicates", help=f"Check duplicates within {kind} records.")
    _add_duplicate_arguments(duplicates)
    duplicates.set_defaults(handler=_cmd_duplicates)

    review = subparsers.add_parser("review", help=f"Apply one explicit human-review event to a {kind} record.")
    review.add_argument("input_path", type=Path)
    review.add_argument("output_path", type=Path)
    review.add_argument("--record-id", required=True)
    review.add_argument("--reviewer-id", required=True)
    review.add_argument("--role", choices=("language", "technical"), required=True)
    review.add_argument("--status", choices=("accepted", "needs_revision", "rejected"), required=True)
    review.add_argument("--notes")
    review.add_argument("--timestamp")
    review.add_argument("--policy", type=Path, required=True)
    review.add_argument("--audit-log", type=Path, required=True)
    review.add_argument("--overwrite", action="store_true")
    review.set_defaults(handler=_cmd_review, record_kind=kind)

    export = subparsers.add_parser("export", help=f"Validate and export accepted {kind} records only.")
    export.add_argument("input_path", type=Path)
    export.add_argument("output_path", type=Path)
    export.add_argument("--overwrite", action="store_true")
    export.add_argument("--actor-id", required=True)
    export.add_argument("--policy", type=Path, required=True)
    export.add_argument("--audit-log", type=Path, required=True)
    export.set_defaults(handler=_cmd_export, record_kind=kind)

    if include_corpus_report:
        report = subparsers.add_parser("report", help="Report deterministic dataset distributions and readiness.")
        report.add_argument("path", type=Path)
        report.add_argument("--targets", type=Path)
        report.add_argument("--output", choices=OUTPUT_FORMATS, default="text")
        report.set_defaults(handler=_cmd_corpus_report, record_kind=kind)


def _add_benchmark_commands(subparsers: argparse._SubParsersAction) -> None:
    contamination = subparsers.add_parser(
        "contamination-check",
        help="Compare benchmark gold candidates against training-dataset records.",
    )
    contamination.add_argument("--benchmark", type=Path, required=True)
    contamination.add_argument("--dataset", type=Path, required=True)
    _add_semantic_arguments(contamination)
    contamination.add_argument("--output", choices=OUTPUT_FORMATS, default="text")
    contamination.set_defaults(handler=_cmd_contamination)

    freeze = subparsers.add_parser("freeze", help="Validate and freeze accepted benchmark gold with a checksum manifest.")
    freeze.add_argument("input_path", type=Path)
    freeze.add_argument("output_path", type=Path)
    freeze.add_argument("--dataset", type=Path, required=True, help="Accepted dataset snapshot used for the mandatory contamination gate.")
    freeze.add_argument("--manifest", type=Path)
    freeze.add_argument("--freeze-id", required=True)
    freeze.add_argument("--frozen-at")
    _add_semantic_arguments(freeze)
    freeze.add_argument("--overwrite", action="store_true")
    freeze.add_argument("--output", choices=OUTPUT_FORMATS, default="text")
    freeze.add_argument("--actor-id", required=True)
    freeze.add_argument("--policy", type=Path, required=True)
    freeze.add_argument("--audit-log", type=Path, required=True)
    freeze.set_defaults(handler=_cmd_freeze)

    verify = subparsers.add_parser("verify-freeze", help="Verify frozen benchmark gold against its checksum manifest.")
    verify.add_argument("gold_path", type=Path)
    verify.add_argument("manifest_path", type=Path)
    verify.add_argument("--output", choices=OUTPUT_FORMATS, default="text")
    verify.set_defaults(handler=_cmd_verify_freeze)

    run = subparsers.add_parser("run", help="Evaluate isolated predictions without modifying benchmark gold.")
    run.add_argument("gold_path", type=Path)
    run.add_argument("predictions_path", type=Path)
    run.add_argument("--model-name", required=True)
    run.add_argument("--model-version")
    run.add_argument("--run-id", required=True)
    run.add_argument("--runs-dir", type=Path, default=Path("runs"))
    run.add_argument("--semantic-judge-test-double", action="store_true")
    run.add_argument("--overwrite", action="store_true")
    run.add_argument("--output", choices=OUTPUT_FORMATS, default="json")
    run.add_argument("--actor-id", required=True)
    run.add_argument("--policy", type=Path, required=True)
    run.add_argument("--audit-log", type=Path, required=True)
    run.set_defaults(handler=_cmd_benchmark_run)

    report = subparsers.add_parser("report", help="Aggregate an existing benchmark run log.")
    report.add_argument("run_log", type=Path)
    report.add_argument("--output", choices=OUTPUT_FORMATS, default="json")
    report.set_defaults(handler=_cmd_benchmark_report)


def _add_dataset_source_commands(subparsers: argparse._SubParsersAction) -> None:
    source = subparsers.add_parser("source", help="Import and localize upstream source records.")
    commands = source.add_subparsers(dest="source_command", metavar="COMMAND", required=True)

    ingest = commands.add_parser("import", help="Import real xLAM or When2Call JSON/JSONL shapes into work items.")
    ingest.add_argument("input_path", type=Path)
    ingest.add_argument("output_path", type=Path)
    ingest.add_argument("--source", choices=("xlam", "when2call"), required=True)
    ingest.add_argument("--split", required=True)
    ingest.add_argument("--source-terms-accepted", action="store_true")
    ingest.add_argument("--overwrite", action="store_true")
    ingest.add_argument("--actor-id", required=True)
    ingest.add_argument("--policy", type=Path, required=True)
    ingest.add_argument("--audit-log", type=Path, required=True)
    ingest.set_defaults(handler=_cmd_source_import)

    ingest_job = commands.add_parser("import-job", help="Run a planned resumable xLAM or When2Call import job.")
    ingest_job.add_argument("manifest_path", type=Path)
    ingest_job.add_argument("--source", choices=("xlam", "when2call"), required=True)
    ingest_job.add_argument("--split", required=True)
    ingest_job.add_argument("--source-terms-accepted", action="store_true")
    ingest_job.add_argument("--actor-id", required=True)
    ingest_job.add_argument("--policy", type=Path, required=True)
    ingest_job.add_argument("--audit-log", type=Path, required=True)
    ingest_job.set_defaults(handler=_cmd_source_import_job)

    validate = commands.add_parser("validate", help="Validate imported/localized source work items.")
    validate.add_argument("path", type=Path)
    validate.add_argument("--output", choices=OUTPUT_FORMATS, default="text")
    validate.set_defaults(handler=_cmd_validate, record_kind="source")

    localize = commands.add_parser("localize", help="Apply reviewed Turkish localization patches without changing machine fields.")
    localize.add_argument("input_path", type=Path)
    localize.add_argument("patches_path", type=Path)
    localize.add_argument("output_path", type=Path)
    localize.add_argument("--timestamp")
    localize.add_argument("--overwrite", action="store_true")
    localize.add_argument("--actor-id", required=True)
    localize.add_argument("--policy", type=Path, required=True)
    localize.add_argument("--audit-log", type=Path, required=True)
    localize.set_defaults(handler=_cmd_source_localize)

    generate = commands.add_parser("generate-localizations", help="Run a resumable DeepSeek localization job.")
    generate.add_argument("manifest_path", type=Path)
    generate.add_argument("--provider", choices=("deepseek",), default="deepseek")
    generate.add_argument("--execute-live", action="store_true")
    generate.add_argument("--actor-id", required=True)
    generate.add_argument("--policy", type=Path, required=True)
    generate.add_argument("--audit-log", type=Path, required=True)
    generate.set_defaults(handler=_cmd_generate_localizations)


def _add_batch_commands(subparsers: argparse._SubParsersAction, lifecycle: str) -> None:
    batch = subparsers.add_parser("batch", help=f"Plan and inspect resumable {lifecycle} jobs.")
    commands = batch.add_subparsers(dest="batch_command", metavar="COMMAND", required=True)
    plan = commands.add_parser("plan", help="Create a checksum-bound shard plan with collision preflight.")
    plan.add_argument("input_path", type=Path)
    plan.add_argument("manifest_path", type=Path)
    plan.add_argument("--job-id", required=True)
    operations = (
        ("source_import", "source_localization", "scenario_generation")
        if lifecycle == "dataset"
        else ("benchmark_generation",)
    )
    plan.add_argument(
        "--operation",
        choices=operations,
        required=True,
    )
    plan.add_argument("--output", type=Path, required=True)
    plan.add_argument("--checkpoint", type=Path, required=True)
    plan.add_argument("--errors", type=Path, required=True)
    plan.add_argument("--shard-size", type=int, default=50)
    plan.add_argument("--targets", type=Path)
    plan.add_argument("--source-type", choices=SOURCE_TYPES)
    plan.add_argument("--start-number", type=int)
    plan.add_argument("--existing", type=Path, action="append", default=[])
    plan.add_argument("--timestamp")
    plan.add_argument("--actor-id", required=True)
    plan.add_argument("--policy", type=Path, required=True)
    plan.add_argument("--audit-log", type=Path, required=True)
    plan.set_defaults(handler=_cmd_batch_plan, record_kind=lifecycle)

    status = commands.add_parser("status", help="Verify input checksum and show current job state.")
    status.add_argument("manifest_path", type=Path)
    status.add_argument("--output", choices=OUTPUT_FORMATS, default="json")
    status.set_defaults(handler=_cmd_batch_status, record_kind=lifecycle)

    report = commands.add_parser("report", help="Compare completed generated records with the manifest distribution targets.")
    report.add_argument("manifest_path", type=Path)
    report.add_argument("--output", choices=OUTPUT_FORMATS, default="json")
    report.set_defaults(handler=_cmd_batch_corpus_report, record_kind=lifecycle)

    if lifecycle == "dataset":
        run = commands.add_parser("run", help="Resume an already planned dataset generation manifest.")
        run.add_argument("manifest_path", type=Path)
        run.add_argument("--provider", choices=("deepseek",), default="deepseek")
        run.add_argument("--execute-live", action="store_true")
        run.add_argument("--actor-id", required=True)
        run.add_argument("--policy", type=Path, required=True)
        run.add_argument("--audit-log", type=Path, required=True)
        run.set_defaults(handler=_cmd_generate_candidates, record_kind="dataset")


def _add_dataset_generation_command(subparsers: argparse._SubParsersAction) -> None:
    generate = subparsers.add_parser(
        "generate",
        help="Validate blueprints, plan a resumable job, and generate review-required dataset drafts.",
    )
    generate.add_argument("blueprints_path", type=Path)
    generate.add_argument("--output", type=Path)
    generate.add_argument("--job-id")
    generate.add_argument("--runs-dir", type=Path)
    generate.add_argument("--targets", type=Path)
    generate.add_argument("--source-type", choices=("original_turkish", "turkey_native"))
    generate.add_argument("--start-number", type=int)
    generate.add_argument("--existing", type=Path, action="append", default=[])
    generate.add_argument("--shard-size", type=int, default=50)
    generate.add_argument("--timestamp")
    generate.add_argument("--provider", choices=("deepseek",), default="deepseek")
    generate.add_argument("--execute-live", action="store_true")
    generate.add_argument("--actor-id", required=True)
    generate.add_argument("--policy", type=Path, required=True)
    generate.add_argument("--audit-log", type=Path, required=True)
    generate.set_defaults(handler=_cmd_generate_dataset, record_kind="dataset")


def _add_generation_command(subparsers: argparse._SubParsersAction, lifecycle: str) -> None:
    generate = subparsers.add_parser("generate", help=f"Run a resumable live {lifecycle} candidate-generation job.")
    generate.add_argument("manifest_path", type=Path)
    generate.add_argument("--provider", choices=("deepseek",), default="deepseek")
    generate.add_argument("--execute-live", action="store_true")
    generate.add_argument("--actor-id", required=True)
    generate.add_argument("--policy", type=Path, required=True)
    generate.add_argument("--audit-log", type=Path, required=True)
    generate.set_defaults(handler=_cmd_generate_candidates, record_kind=lifecycle)


def _add_duplicate_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("path", type=Path)
    _add_semantic_arguments(parser)
    parser.add_argument("--output", choices=OUTPUT_FORMATS, default="text")


def _add_semantic_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--semantic-provider",
        choices=("none", "token-test-double", "openai"),
        default="none",
        help="Select no semantic scan, the deterministic test double, or production OpenAI embeddings.",
    )
    parser.add_argument("--semantic-threshold", type=float, default=0.9)
    parser.add_argument("--semantic-cache", type=Path)


def _add_support_commands(subparsers: argparse._SubParsersAction) -> None:
    registry = subparsers.add_parser("registry", help="Manage canonical Tool Registry infrastructure.")
    registry_commands = registry.add_subparsers(dest="registry_command", metavar="COMMAND", required=True)
    registry_validate = registry_commands.add_parser("validate", help="Validate a registry JSONL file.")
    registry_validate.add_argument("path", type=Path)
    registry_validate.add_argument("--output", choices=OUTPUT_FORMATS, default="text")
    registry_validate.set_defaults(handler=_cmd_validate, record_kind="registry")

    blueprint = subparsers.add_parser("blueprint", help="Manage scenario-blueprint infrastructure.")
    blueprint_commands = blueprint.add_subparsers(dest="blueprint_command", metavar="COMMAND", required=True)
    blueprint_validate = blueprint_commands.add_parser("validate", help="Validate a scenario blueprint.")
    blueprint_validate.add_argument("path", type=Path)
    blueprint_validate.add_argument("--output", choices=OUTPUT_FORMATS, default="text")
    blueprint_validate.set_defaults(handler=_cmd_validate, record_kind="blueprint")

    tool = subparsers.add_parser("tool", help="Run deterministic tool fixtures and generate call IDs.")
    tool_commands = tool.add_subparsers(dest="tool_command", metavar="COMMAND", required=True)
    execute = tool_commands.add_parser("run-fixture", help="Run a declared deterministic registry fixture.")
    execute.add_argument("fixture_id")
    execute.add_argument("--mode", choices=("mock", "local_executable"), default="mock")
    execute.set_defaults(handler=_cmd_run_fixture)
    api = tool_commands.add_parser("run-api", help="Run an approved read-only HTTPS JSON tool with explicit live confirmation.")
    api.add_argument("function_name")
    api.add_argument("--arguments", required=True, help="JSON object containing function arguments.")
    api.add_argument("--call-id", default="call_001")
    api.add_argument("--timeout-ms", type=int)
    api.add_argument("--confirm-live", action="store_true")
    api.add_argument("--actor-id", required=True)
    api.add_argument("--policy", type=Path, required=True)
    api.add_argument("--audit-log", type=Path, required=True)
    api.set_defaults(handler=_cmd_run_api)
    call_id = tool_commands.add_parser("generate-call-id", help="Generate a deterministic tool-call ID.")
    call_id.add_argument("number", type=int)
    call_id.set_defaults(handler=_cmd_call_id)


def _add_access_commands(subparsers: argparse._SubParsersAction) -> None:
    access = subparsers.add_parser("access", help="Validate principals, permissions, and audit logs.")
    commands = access.add_subparsers(dest="access_command", metavar="COMMAND", required=True)
    validate = commands.add_parser("validate", help="Validate an access-policy file.")
    validate.add_argument("path", type=Path)
    validate.set_defaults(handler=_cmd_access_validate)
    check = commands.add_parser("check", help="Check one principal permission without changing state.")
    check.add_argument("path", type=Path)
    check.add_argument("--actor-id", required=True)
    check.add_argument("--lifecycle", choices=("dataset", "benchmark", "platform"), required=True)
    check.add_argument("--permission", required=True)
    check.add_argument("--reviewer-role", choices=("language", "technical"))
    check.set_defaults(handler=_cmd_access_check)
    audit = commands.add_parser("verify-audit", help="Verify an append-only audit log hash chain.")
    audit.add_argument("path", type=Path)
    audit.add_argument("--output", choices=OUTPUT_FORMATS, default="text")
    audit.set_defaults(handler=_cmd_audit_verify)


def _cmd_config(args: argparse.Namespace) -> int:
    settings = Settings.from_env()
    print(f"project_root={settings.project_root}")
    print(f"log_level={args.log_level or settings.log_level}")
    print(f"deepseek_api_key={redact_secret(settings.deepseek_api_key)}")
    print(f"deepseek_model={settings.deepseek_model}")
    print(f"deepseek_base_url={settings.deepseek_base_url}")
    print(f"openai_api_key={redact_secret(settings.openai_api_key)}")
    print(f"openai_embedding_model={settings.openai_embedding_model}")
    print(f"openai_base_url={settings.openai_base_url}")
    print(f"semantic_cache_dir={settings.semantic_cache_dir}")
    print(f"request_timeout_seconds={settings.request_timeout_seconds}")
    print(f"max_retries={settings.max_retries}")
    return 0


def _cmd_access_validate(args: argparse.Namespace) -> int:
    try:
        policy = AccessPolicy.load(args.path)
    except AccessPolicyError as exc:
        print(f"ERROR ACCESS_POLICY_INVALID: {exc}")
        return 1
    print(f"OK: access policy is valid; principals={len(policy.principals)}")
    return 0


def _cmd_access_check(args: argparse.Namespace) -> int:
    try:
        AccessPolicy.load(args.path).authorize(
            args.actor_id,
            lifecycle=args.lifecycle,
            permission=args.permission,
            reviewer_role=args.reviewer_role,
        )
    except (AccessPolicyError, AccessDenied) as exc:
        print(f"ERROR ACCESS_DENIED: {exc}")
        return 1
    print(f"OK: {args.actor_id} may {args.permission} in {args.lifecycle}")
    return 0


def _cmd_audit_verify(args: argparse.Namespace) -> int:
    try:
        result = verify_audit_log(args.path)
    except AccessPolicyError as exc:
        print(f"ERROR AUDIT_INVALID: {exc}")
        return 1
    _print_payload(result, args.output)
    return 0 if result["valid"] else 1


def _cmd_record_id(args: argparse.Namespace) -> int:
    return _generate_id(args.record_kind, args.number, args.source_type)


def _cmd_call_id(args: argparse.Namespace) -> int:
    return _generate_id("call", args.number, None)


def _generate_id(kind: str, number: int, source_type: str | None) -> int:
    try:
        value = generate_call_id(number) if kind == "call" else generate_record_id(kind, source_type or "", number)
    except IdError as exc:
        print(f"ERROR ID_INVALID: {exc}")
        return 1
    print(value)
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    return _validate_schema(args.record_kind, args.path, args.output)


def _validate_schema(kind: str, path: Path, output: str) -> int:
    report = RuleBasedValidator().validate_path(kind, path)
    if output == "json":
        print(json.dumps(report.to_dict(), ensure_ascii=False, sort_keys=True))
    else:
        print(report.human())
    return 0 if report.valid else 1


def _cmd_run_fixture(args: argparse.Namespace) -> int:
    registry = ToolRegistry.load()
    fixture = registry.load_fixture(args.fixture_id)
    execution_type = ExecutionType(args.mode)
    adapter = MockAdapter.from_registry(registry, [args.fixture_id]) if execution_type == ExecutionType.MOCK else LocalExecutableAdapter()
    engine = ExecutionEngine(registry, ExecutionRouter([adapter]))
    result = engine.execute(ExecutionRequest("call_001", fixture["function_name"], fixture["arguments"], execution_type))
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == ExecutionStatus.PASSED else 1


def _cmd_run_api(args: argparse.Namespace) -> int:
    if not args.confirm_live:
        print("ERROR LIVE_EXECUTION_BLOCKED: --confirm-live is required")
        return 1
    try:
        _authorize_cli_action(
            args,
            actor_id=args.actor_id,
            lifecycle="platform",
            permission="real_api",
            resource_id=args.function_name,
        )
        arguments = json.loads(args.arguments)
        if not isinstance(arguments, dict):
            raise ValueError("arguments must be a JSON object")
        registry = ToolRegistry.load()
        tool = registry.by_function_name(args.function_name)
        if tool["lifecycle"] != "approved":
            raise ValueError("live execution requires an approved registry tool")
        engine = ExecutionEngine(registry, ExecutionRouter([HttpJsonAdapter(registry)]))
        result = engine.execute(ExecutionRequest(
            args.call_id,
            args.function_name,
            arguments,
            ExecutionType.REAL_API,
            timeout_ms=args.timeout_ms,
        ))
    except (
        AccessPolicyError, AccessDenied, JsonSchemaValidationError, ExecutionRoutingError,
        json.JSONDecodeError, KeyError, ValueError,
    ) as exc:
        print(f"ERROR LIVE_EXECUTION_BLOCKED: {exc}")
        return 1
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    _audit_cli_allowed(args, args.actor_id, "platform", "real_api", args.function_name)
    return 0 if result.status == ExecutionStatus.PASSED else 1


def _cmd_source_import(args: argparse.Namespace) -> int:
    try:
        _authorize_cli_action(
            args, actor_id=args.actor_id, lifecycle="dataset", permission="source_import",
            resource_id=str(args.output_path),
        )
        records = import_source(
            args.input_path,
            source=args.source,
            split=args.split,
            source_terms_accepted=args.source_terms_accepted,
        )
        validation = _validate_loaded_records("source", records)
        if validation:
            print(validation)
            return 1
        count = write_records(args.output_path, records, overwrite=args.overwrite)
    except (AccessPolicyError, AccessDenied, OSError, RecordIOError, SourceIngestionError) as exc:
        print(f"ERROR SOURCE_IMPORT_BLOCKED: {exc}")
        return 1
    _audit_cli_allowed(args, args.actor_id, "dataset", "source_import", str(args.output_path))
    print(f"OK: imported {count} {args.source} source work item(s) to {args.output_path}")
    return 0


def _cmd_source_import_job(args: argparse.Namespace) -> int:
    try:
        manifest = load_manifest(args.manifest_path)
        if manifest["lifecycle"] != "dataset" or manifest["operation"] != "source_import":
            raise BatchError("expected a dataset source_import manifest")
        _authorize_cli_action(
            args, actor_id=args.actor_id, lifecycle="dataset", permission="source_import",
            resource_id=manifest["job_id"],
        )
        adapter = get_source_adapter(args.source, source_terms_accepted=args.source_terms_accepted)
        validator = RuleBasedValidator()
        source_file = Path(manifest["input_path"]).name

        def process(row: dict[str, Any], index: int, record_id: str | None) -> dict[str, Any]:
            item = adapter.convert(row, row_number=index + 1, source_file=source_file, split=args.split)
            report = validator.validate_record("source", item)
            if not report.valid:
                raise BatchError(report.human())
            return item

        completed = run_job(args.manifest_path, process)
    except (AccessPolicyError, AccessDenied, BatchError, SourceIngestionError) as exc:
        print(f"ERROR SOURCE_IMPORT_BLOCKED: {exc}")
        return 1
    _audit_cli_allowed(args, args.actor_id, "dataset", "source_import", completed["job_id"])
    _print_payload({"job_id": completed["job_id"], "status": completed["status"], "counts": completed["counts"]}, "json")
    return 0 if completed["counts"]["failed"] == 0 else 1


def _cmd_source_localize(args: argparse.Namespace) -> int:
    try:
        _authorize_cli_action(
            args, actor_id=args.actor_id, lifecycle="dataset", permission="localize",
            resource_id=str(args.output_path),
        )
        records = load_records(args.input_path)
        patches = load_records(args.patches_path)
        mismatched_actors = [
            patch.get("source_example_id", "<unknown>")
            for patch in patches
            if patch.get("actor_id") != args.actor_id
        ]
        if mismatched_actors:
            raise LocalizationError("patch actor_id must match the authorized actor: " + ", ".join(mismatched_actors))
        validation = _validate_loaded_records("source", records)
        if validation:
            print(validation)
            return 1
        localized = localize_items(records, patches, timestamp=args.timestamp)
        validation = _validate_loaded_records("source", localized)
        if validation:
            print(validation)
            return 1
        count = write_records(args.output_path, localized, overwrite=args.overwrite)
    except (AccessPolicyError, AccessDenied, OSError, RecordIOError, LocalizationError) as exc:
        print(f"ERROR LOCALIZATION_BLOCKED: {exc}")
        return 1
    _audit_cli_allowed(args, args.actor_id, "dataset", "localize", str(args.output_path))
    print(f"OK: localized {count} source work item(s) to {args.output_path}; human review still required")
    return 0


def _cmd_batch_plan(args: argparse.Namespace) -> int:
    permission = {
        "source_import": "source_import",
        "source_localization": "localize",
        "scenario_generation": "generate",
        "benchmark_generation": "generate",
    }[args.operation]
    try:
        _authorize_cli_action(
            args, actor_id=args.actor_id, lifecycle=args.record_kind, permission=permission,
            resource_id=args.job_id,
        )
        if args.operation in {"scenario_generation", "benchmark_generation"} and (
            args.source_type is None or args.start_number is None
        ):
            raise BatchError("generation jobs require --source-type and --start-number")
        targets: dict[str, dict[str, int]] | None = None
        if args.targets:
            targets = json.loads(args.targets.read_text(encoding="utf-8"))
            if not isinstance(targets, dict):
                raise BatchError("target distributions must be a JSON object")
        existing = collect_existing_ids(args.existing)
        manifest = create_job_manifest(
            job_id=args.job_id,
            lifecycle=args.record_kind,
            operation=args.operation,
            input_path=args.input_path,
            output_path=args.output,
            checkpoint_path=args.checkpoint,
            error_path=args.errors,
            shard_size=args.shard_size,
            targets=targets,
            source_type=args.source_type,
            start_number=args.start_number,
            existing_ids=existing,
            timestamp=args.timestamp,
        )
        write_manifest(args.manifest_path, manifest)
    except (AccessPolicyError, AccessDenied, OSError, json.JSONDecodeError, BatchError) as exc:
        print(f"ERROR BATCH_PLAN_BLOCKED: {exc}")
        return 1
    _audit_cli_allowed(args, args.actor_id, args.record_kind, permission, args.job_id)
    print(f"OK: planned {manifest['total_items']} item(s) in {len(manifest['shards'])} shard(s) at {args.manifest_path}")
    return 0


def _cmd_batch_status(args: argparse.Namespace) -> int:
    try:
        manifest = load_manifest(args.manifest_path)
        if manifest["lifecycle"] != args.record_kind:
            raise BatchError(f"job belongs to {manifest['lifecycle']}, not {args.record_kind}")
    except BatchError as exc:
        print(f"ERROR BATCH_INVALID: {exc}")
        return 1
    payload = {
        "job_id": manifest["job_id"],
        "lifecycle": manifest["lifecycle"],
        "operation": manifest["operation"],
        "status": manifest["status"],
        "total_items": manifest["total_items"],
        "counts": manifest["counts"],
        "shards": manifest["shards"],
        "target_distributions": manifest["target_distributions"],
        "input_verified": True,
    }
    _print_payload(payload, args.output)
    return 0


def _cmd_generate_candidates(args: argparse.Namespace) -> int:
    if not args.execute_live:
        print("ERROR GENERATION_BLOCKED: --execute-live is required")
        return 1
    try:
        manifest = load_manifest(args.manifest_path)
        expected_operation = "scenario_generation" if args.record_kind == "dataset" else "benchmark_generation"
        if manifest["lifecycle"] != args.record_kind or manifest["operation"] != expected_operation:
            raise BatchError(f"expected a {args.record_kind} {expected_operation} manifest")
        if manifest["id_plan"] is None:
            raise BatchError("candidate generation requires a manifest ID plan")
        _authorize_cli_action(
            args, actor_id=args.actor_id, lifecycle=args.record_kind, permission="generate",
            resource_id=manifest["job_id"],
        )
        settings = Settings.from_env()
        provider = DeepSeekIntegration.from_settings(settings)
        provider.require_configured()
        completed = _execute_candidate_generation(
            args,
            manifest_path=args.manifest_path,
            settings=settings,
            provider=provider,
        )
    except (AccessPolicyError, AccessDenied, BatchError, ProviderNotConfigured, DatasetWorkflowError) as exc:
        print(f"ERROR GENERATION_BLOCKED: {exc}")
        return 1
    _audit_cli_allowed(args, args.actor_id, args.record_kind, "generate", completed["job_id"])
    _print_payload({"job_id": completed["job_id"], "status": completed["status"], "counts": completed["counts"]}, "json")
    return 0 if completed["counts"]["failed"] == 0 else 1


def _cmd_generate_dataset(args: argparse.Namespace) -> int:
    if not args.execute_live:
        print("ERROR GENERATION_BLOCKED: --execute-live is required")
        return 1
    try:
        settings = Settings.from_env()
        validator = RuleBasedValidator()
        plan = inspect_blueprints(args.blueprints_path, validator=validator)
        source_type = args.source_type or plan.source_type
        if source_type != plan.source_type:
            raise DatasetWorkflowError(
                f"--source-type {source_type} does not match blueprint source_type {plan.source_type}"
            )
        targets = plan.target_distributions
        if args.targets:
            targets = json.loads(args.targets.read_text(encoding="utf-8"))
            if not isinstance(targets, dict):
                raise DatasetWorkflowError("target distributions must be a JSON object")

        provider = DeepSeekIntegration.from_settings(settings)
        provider.require_configured()
        job_id = args.job_id or default_job_id(args.blueprints_path)
        paths = default_job_paths(
            project_root=settings.project_root,
            runs_dir=(args.runs_dir or settings.runs_dir),
            job_id=job_id,
            output_path=args.output,
        )
        existing_paths = dataset_record_paths(settings.project_root)
        existing_paths.extend(args.existing)
        existing_ids = collect_existing_ids(sorted(set(existing_paths)))
        start_number = (
            args.start_number
            if args.start_number is not None
            else next_dataset_number(existing_ids, source_type)
        )

        _authorize_cli_action(
            args,
            actor_id=args.actor_id,
            lifecycle="dataset",
            permission="generate",
            resource_id=job_id,
        )
        manifest = create_job_manifest(
            job_id=job_id,
            lifecycle="dataset",
            operation="scenario_generation",
            input_path=args.blueprints_path,
            output_path=paths.output,
            checkpoint_path=paths.checkpoint,
            error_path=paths.errors,
            shard_size=args.shard_size,
            targets=targets,
            source_type=source_type,
            start_number=start_number,
            existing_ids=existing_ids,
            timestamp=args.timestamp,
        )
        write_manifest(paths.manifest, manifest)
        completed = _execute_candidate_generation(
            args,
            manifest_path=paths.manifest,
            settings=settings,
            provider=provider,
        )
    except (
        AccessPolicyError,
        AccessDenied,
        BatchError,
        DatasetWorkflowError,
        IdError,
        JsonSchemaValidationError,
        ProviderNotConfigured,
        OSError,
        json.JSONDecodeError,
    ) as exc:
        print(f"ERROR GENERATION_BLOCKED: {exc}")
        return 1

    _audit_cli_allowed(args, args.actor_id, "dataset", "generate", completed["job_id"])
    _print_payload(
        {
            "job_id": completed["job_id"],
            "status": completed["status"],
            "counts": completed["counts"],
            "manifest": str(paths.manifest),
            "output": str(paths.output),
            "errors": str(paths.errors),
            "pending_quality_gates": ["execution_when_applicable", "semantic", "language", "duplicate"],
        },
        "json",
    )
    return 0 if completed["counts"]["failed"] == 0 else 1


def _execute_candidate_generation(
    args: argparse.Namespace,
    *,
    manifest_path: Path,
    settings: Settings,
    provider: DeepSeekIntegration,
) -> dict[str, Any]:
    manifest = load_manifest(manifest_path)
    validator = RuleBasedValidator()
    generated_at = getattr(args, "timestamp", None) or datetime.now(timezone.utc).isoformat()

    def process(blueprint: dict[str, Any], index: int, record_id: str | None) -> dict[str, Any]:
        if record_id is None:
            raise BatchError("generation item has no assigned record ID")
        blueprint_report = validator.validate_record("blueprint", blueprint)
        if not blueprint_report.valid:
            raise BatchError(blueprint_report.human())
        response = _provider_retry(
            lambda: provider.generate_candidate(
                lifecycle=args.record_kind,
                blueprint=blueprint,
                record_id=record_id,
            ),
            settings,
        )
        value = response.value
        if args.record_kind == "dataset":
            value = prepare_generated_candidate(
                value,
                blueprint=blueprint,
                record_id=record_id,
                identity=response.identity,
                actor_id=args.actor_id,
                generated_at=generated_at,
            )
        else:
            if not isinstance(value, dict) or value.get("id") != record_id:
                raise BatchError(f"provider returned an unexpected record ID for item {index}")
            review = value.get("metadata", {}).get("review", {})
            if review.get("status") != "needs_revision" or review.get("reviewer_ids"):
                raise BatchError("generated candidates must remain unreviewed needs_revision records")
        report = validator.validate_record(args.record_kind, value)
        if not report.valid:
            raise BatchError(report.human())
        return value

    return run_job(manifest_path, process)


def _cmd_generate_localizations(args: argparse.Namespace) -> int:
    if not args.execute_live:
        print("ERROR LOCALIZATION_BLOCKED: --execute-live is required")
        return 1
    try:
        manifest = load_manifest(args.manifest_path)
        if manifest["lifecycle"] != "dataset" or manifest["operation"] != "source_localization":
            raise BatchError("expected a dataset source_localization manifest")
        _authorize_cli_action(
            args, actor_id=args.actor_id, lifecycle="dataset", permission="localize",
            resource_id=manifest["job_id"],
        )
        settings = Settings.from_env()
        provider = DeepSeekIntegration.from_settings(settings)
        provider.require_configured()
        validator = RuleBasedValidator()

        def process(item: dict[str, Any], index: int, record_id: str | None) -> dict[str, Any]:
            report = validator.validate_record("source", item)
            if not report.valid:
                raise BatchError(report.human())
            response = _provider_retry(
                lambda: provider.generate_localization_patch(item, actor_id=args.actor_id),
                settings,
            )
            patch = response.value
            if patch.get("source_example_id") != item["source"]["example_id"]:
                raise BatchError(f"provider returned an unexpected source ID for item {index}")
            patch["actor_id"] = args.actor_id
            patch["provider"] = "deepseek"
            patch["provider_version"] = provider.model
            localized = localize_items([item], [patch])[0]
            report = validator.validate_record("source", localized)
            if not report.valid:
                raise BatchError(report.human())
            return localized

        completed = run_job(args.manifest_path, process)
    except (AccessPolicyError, AccessDenied, BatchError, ProviderNotConfigured) as exc:
        print(f"ERROR LOCALIZATION_BLOCKED: {exc}")
        return 1
    _audit_cli_allowed(args, args.actor_id, "dataset", "localize", completed["job_id"])
    _print_payload({"job_id": completed["job_id"], "status": completed["status"], "counts": completed["counts"]}, "json")
    return 0 if completed["counts"]["failed"] == 0 else 1


def _cmd_duplicates(args: argparse.Namespace) -> int:
    parsed, parse_issues = parse_path(args.path)
    if parse_issues:
        return _print_parse_issues(parse_issues, args.output)
    records = [record for _, record in parsed]
    try:
        semantic = _semantic_similarity(args)
        reports = [
            compare_records(
                records[left], records[right], semantic=semantic,
                semantic_threshold=args.semantic_threshold,
            )
            for left in range(len(records))
            for right in range(left + 1, len(records))
        ]
    except (ProviderError, ProviderNotConfigured, ValueError) as exc:
        print(f"ERROR SEMANTIC_SCAN_BLOCKED: {exc}")
        return 1
    if args.output == "json":
        print(json.dumps([report.to_dict() for report in reports], ensure_ascii=False, sort_keys=True))
    else:
        for report in reports:
            print(f"{report.left_id} {report.right_id}: {report.decision}")
        if not reports:
            print("OK: fewer than two records; no pairs to compare")
    return 1 if any(report.decision in {"duplicate", "possible_duplicate"} for report in reports) else 0


def _cmd_review(args: argparse.Namespace) -> int:
    try:
        permission = "accept" if args.status == "accepted" else "review"
        _authorize_cli_action(
            args,
            actor_id=args.reviewer_id,
            lifecycle=args.record_kind,
            permission=permission,
            reviewer_role=args.role,
            resource_id=args.record_id,
        )
        records = load_records(args.input_path)
        matches = [index for index, record in enumerate(records) if record.get("id") == args.record_id]
        if len(matches) != 1:
            raise ReviewError(f"record ID must match exactly one input record: {args.record_id}")
        index = matches[0]
        reviewed = apply_review(
            records[index],
            reviewer_id=args.reviewer_id,
            reviewer_role=args.role,
            new_status=args.status,
            notes=args.notes,
            timestamp=args.timestamp,
        )
        report = RuleBasedValidator().validate_record(args.record_kind, reviewed)
        if not report.valid:
            print(report.human())
            return 1
        records[index] = reviewed
        write_records(args.output_path, records, overwrite=args.overwrite)
    except (AccessPolicyError, AccessDenied, RecordIOError, ReviewError) as exc:
        print(f"ERROR REVIEW_BLOCKED: {exc}")
        return 1
    _audit_cli_allowed(args, args.reviewer_id, args.record_kind, permission, args.record_id)
    print(f"OK: reviewed {args.record_id} -> {args.status}; wrote {args.output_path}")
    return 0


def _cmd_export(args: argparse.Namespace) -> int:
    try:
        _authorize_cli_action(
            args, actor_id=args.actor_id, lifecycle=args.record_kind, permission="export",
            resource_id=str(args.output_path),
        )
    except (AccessPolicyError, AccessDenied) as exc:
        print(f"ERROR EXPORT_BLOCKED: {exc}")
        return 1
    result = _export(args.record_kind, args.input_path, args.output_path, args.overwrite)
    if result == 0:
        _audit_cli_allowed(args, args.actor_id, args.record_kind, "export", str(args.output_path))
    return result


def _export(kind: str, input_path: Path, output_path: Path, overwrite: bool) -> int:
    parsed, parse_issues = parse_path(input_path)
    if parse_issues:
        return _print_parse_issues(parse_issues, "text")
    try:
        count = export_accepted(
            [record for _, record in parsed],
            output_path,
            validator=RuleBasedValidator(),
            kind=kind,
            overwrite=overwrite,
        )
    except ReviewError as exc:
        print(f"ERROR EXPORT_BLOCKED: {exc}")
        return 1
    print(f"OK: exported {count} accepted {kind} record(s) to {output_path}")
    return 0


def _cmd_corpus_report(args: argparse.Namespace) -> int:
    try:
        records = load_records(args.path)
    except RecordIOError as exc:
        print(f"ERROR REPORT_BLOCKED: {exc}")
        return 1
    validation = _validate_loaded_records(args.record_kind, records)
    if validation:
        print(validation)
        return 1
    try:
        targets = json.loads(args.targets.read_text(encoding="utf-8")) if args.targets else None
        report = corpus_report(records, kind=args.record_kind, targets=targets)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"ERROR REPORT_BLOCKED: {exc}")
        return 1
    _print_payload(report, args.output)
    return 0


def _cmd_batch_corpus_report(args: argparse.Namespace) -> int:
    try:
        manifest = load_manifest(args.manifest_path)
        if manifest["lifecycle"] != args.record_kind:
            raise BatchError(f"job belongs to {manifest['lifecycle']}, not {args.record_kind}")
        if manifest["status"] not in {"completed", "completed_with_errors"}:
            raise BatchError("batch report requires a completed job")
        records = load_records(Path(manifest["output_path"]))
        validation = _validate_loaded_records(args.record_kind, records)
        if validation:
            print(validation)
            return 1
        report = corpus_report(
            records,
            kind=args.record_kind,
            targets=manifest["target_distributions"],
        )
    except (BatchError, RecordIOError, ValueError) as exc:
        print(f"ERROR REPORT_BLOCKED: {exc}")
        return 1
    _print_payload(report, args.output)
    return 0 if report.get("distribution_targets_met", True) else 1


def _cmd_contamination(args: argparse.Namespace) -> int:
    try:
        benchmark = load_records(args.benchmark)
        dataset = load_records(args.dataset)
    except RecordIOError as exc:
        print(f"ERROR CONTAMINATION_BLOCKED: {exc}")
        return 1
    for kind, records in (("benchmark", benchmark), ("dataset", dataset)):
        validation = _validate_loaded_records(kind, records)
        if validation:
            print(validation)
            return 1
    try:
        semantic = _semantic_similarity(args)
        report = compare_corpora(
            benchmark,
            dataset,
            semantic=semantic,
            semantic_threshold=args.semantic_threshold,
        )
    except (ProviderError, ProviderNotConfigured, ValueError) as exc:
        print(f"ERROR SEMANTIC_SCAN_BLOCKED: {exc}")
        return 1
    if args.output == "json":
        print(json.dumps(report.to_dict(), ensure_ascii=False, sort_keys=True))
    else:
        print(
            f"{report.status.upper()}: checked {report.pairs_checked} pair(s); "
            f"blocking={report.blocking_count}, needs_review={report.review_required_count}"
        )
        for finding in report.findings:
            print(f"{finding.benchmark_id} {finding.dataset_id}: {finding.decision}")
    return 0 if report.passed else 1


def _cmd_freeze(args: argparse.Namespace) -> int:
    manifest_path = args.manifest or Path(str(args.output_path) + ".manifest.json")
    try:
        _authorize_cli_action(
            args, actor_id=args.actor_id, lifecycle="benchmark", permission="freeze",
            resource_id=args.freeze_id,
        )
        records = load_records(args.input_path)
        dataset = load_records(args.dataset)
        dataset_validation = _validate_loaded_records("dataset", dataset)
        if dataset_validation:
            print(dataset_validation)
            return 1
        semantic = _semantic_similarity(args)
        contamination = compare_corpora(
            records,
            dataset,
            semantic=semantic,
            semantic_threshold=args.semantic_threshold,
        )
        manifest = freeze_benchmark(
            records,
            args.output_path,
            manifest_path=manifest_path,
            freeze_id=args.freeze_id,
            validator=RuleBasedValidator(),
            contamination_report=contamination,
            dataset_sha256=hashlib.sha256(args.dataset.read_bytes()).hexdigest(),
            frozen_at=args.frozen_at,
            overwrite=args.overwrite,
        )
    except (AccessPolicyError, AccessDenied, ProviderError, ProviderNotConfigured, OSError, RecordIOError, FreezeError, ValueError) as exc:
        print(f"ERROR FREEZE_BLOCKED: {exc}")
        return 1
    payload = {**manifest, "gold_path": str(args.output_path), "manifest_path": str(manifest_path)}
    _print_payload(payload, args.output)
    _audit_cli_allowed(args, args.actor_id, "benchmark", "freeze", args.freeze_id)
    return 0


def _cmd_verify_freeze(args: argparse.Namespace) -> int:
    try:
        result = verify_benchmark_freeze(args.gold_path, args.manifest_path)
    except FreezeError as exc:
        print(f"ERROR FREEZE_INVALID: {exc}")
        return 1
    _print_payload(result, args.output)
    return 0 if result["valid"] else 1


def _cmd_benchmark_run(args: argparse.Namespace) -> int:
    try:
        _authorize_cli_action(
            args, actor_id=args.actor_id, lifecycle="benchmark", permission="benchmark_run",
            resource_id=args.run_id,
        )
        gold = load_records(args.gold_path)
        predictions = load_records(args.predictions_path)
    except (AccessPolicyError, AccessDenied, RecordIOError) as exc:
        print(f"ERROR RUN_BLOCKED: {exc}")
        return 1
    validation = _validate_loaded_records("benchmark", gold)
    if validation:
        print(validation)
        return 1
    not_accepted = [record["id"] for record in gold if record["metadata"]["review"]["status"] != "accepted"]
    if not_accepted:
        print("ERROR RUN_BLOCKED: benchmark gold is not accepted: " + ", ".join(not_accepted))
        return 1
    semantic = MockSemanticJudge(1.0) if args.semantic_judge_test_double else None
    try:
        path, metrics = run_benchmark(
            gold,
            predictions,
            evaluator=BenchmarkEvaluator(ToolRegistry.load(), semantic),
            runs_dir=args.runs_dir,
            model_name=args.model_name,
            model_version=args.model_version,
            run_id=args.run_id,
            overwrite=args.overwrite,
        )
    except (BenchmarkRunError, ValueError) as exc:
        print(f"ERROR RUN_BLOCKED: {exc}")
        return 1
    _print_payload({"run_log": str(path), "metrics": metrics}, args.output)
    _audit_cli_allowed(args, args.actor_id, "benchmark", "benchmark_run", args.run_id)
    return 0


def _cmd_benchmark_report(args: argparse.Namespace) -> int:
    try:
        entries = load_records(args.run_log)
        report = benchmark_run_report(entries)
    except (RecordIOError, KeyError, TypeError) as exc:
        print(f"ERROR REPORT_BLOCKED: {exc}")
        return 1
    _print_payload(report, args.output)
    return 0


def _validate_loaded_records(kind: str, records: list[dict[str, Any]]) -> str | None:
    validator = RuleBasedValidator()
    failures = []
    for record in records:
        report = validator.validate_record(kind, record)
        if not report.valid:
            failures.append(report.human())
    return "\n".join(failures) if failures else None


def _print_parse_issues(issues, output: str) -> int:
    if output == "json":
        print(json.dumps([issue.to_dict() for issue in issues], ensure_ascii=False))
    else:
        print("\n".join(f"ERROR {issue.code}: {issue.message}" for issue in issues))
    return 1


def _print_payload(payload: dict[str, Any], output: str) -> None:
    if output == "json":
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return
    for key, value in payload.items():
        rendered = json.dumps(value, ensure_ascii=False, sort_keys=True) if isinstance(value, (dict, list)) else value
        print(f"{key}={rendered}")


def _authorize_cli_action(
    args: argparse.Namespace,
    *,
    actor_id: str,
    lifecycle: str,
    permission: str,
    resource_id: str,
    reviewer_role: str | None = None,
) -> None:
    try:
        AccessPolicy.load(args.policy).authorize(
            actor_id,
            lifecycle=lifecycle,
            permission=permission,
            reviewer_role=reviewer_role,
        )
    except (AccessPolicyError, AccessDenied):
        try:
            append_audit_event(
                args.audit_log,
                actor_id=actor_id,
                lifecycle=lifecycle,
                action=permission,
                resource_id=resource_id,
                decision="denied",
            )
        except AccessPolicyError:
            pass
        raise


def _audit_cli_allowed(
    args: argparse.Namespace,
    actor_id: str,
    lifecycle: str,
    permission: str,
    resource_id: str,
) -> None:
    append_audit_event(
        args.audit_log,
        actor_id=actor_id,
        lifecycle=lifecycle,
        action=permission,
        resource_id=resource_id,
        decision="allowed",
    )


def _semantic_similarity(args: argparse.Namespace):
    if not 0.0 <= args.semantic_threshold <= 1.0:
        raise ValueError("semantic threshold must be between 0 and 1")
    if args.semantic_provider == "none":
        return None
    if args.semantic_provider == "token-test-double":
        return DeterministicTokenSimilarity()
    settings = Settings.from_env()
    cache_dir = args.semantic_cache or settings.semantic_cache_dir
    return CachedEmbeddingSimilarity(OpenAIEmbeddingProvider.from_settings(settings), cache_dir)


def _provider_retry(operation, settings: Settings):
    value, _ = run_with_retry(
        operation,
        RetryPolicy(max_attempts=settings.max_retries + 1, base_seconds=settings.retry_base_seconds),
        retryable=lambda exc: isinstance(exc, ProviderError),
        sleep=time.sleep,
    )
    return value


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    settings = Settings.from_env()
    configure_logging(args.log_level or settings.log_level)
    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 0
    return handler(args)
