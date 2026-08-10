"""Deterministic repository and pull-request contribution review."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path, PurePosixPath
import re
from typing import Iterable, Literal

from jsonschema.exceptions import SchemaError, ValidationError

from tool_call_tr.registry import RegistryValidationError, ToolRegistry
from tool_call_tr.schemas import SchemaStore
from tool_call_tr.validation import RuleBasedValidator
from tool_call_tr.validation.diagnostics import ValidationIssue
from tool_call_tr.validation.parsing import parse_path


FindingSeverity = Literal["error", "warning", "info"]
COMMENT_MARKER = "<!-- magibu-contribution-bot -->"
_REQUIRED_PR_SECTIONS = (
    "Katkı türü",
    "Değişiklik",
    "Kaynak ve lisans",
    "Otomatik kontroller",
    "İnsan incelemesi",
)
_TEXT_SUFFIXES = {".json", ".jsonl", ".md", ".py", ".yml", ".yaml", ".toml", ".txt"}
_MAX_FINDINGS_PER_SECTION = 50
_SECRET_PATTERNS = (
    ("SECRET_PRIVATE_KEY", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("SECRET_OPENAI_STYLE", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("SECRET_GITHUB_TOKEN", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("SECRET_BEARER_TOKEN", re.compile(r"\bBearer\s+[A-Za-z0-9._~-]{24,}\b", re.IGNORECASE)),
)


@dataclass(frozen=True, slots=True)
class ContributionFinding:
    code: str
    severity: FindingSeverity
    message: str
    suggestion: str
    file: str | None = None
    line: int | None = None

    @property
    def location(self) -> str:
        if not self.file:
            return "PR açıklaması"
        return f"{self.file}:{self.line}" if self.line else self.file


@dataclass(slots=True)
class ContributionReport:
    findings: list[ContributionFinding]
    checks: list[str]

    @property
    def errors(self) -> list[ContributionFinding]:
        return [finding for finding in self.findings if finding.severity == "error"]

    @property
    def warnings(self) -> list[ContributionFinding]:
        return [finding for finding in self.findings if finding.severity == "warning"]

    @property
    def has_errors(self) -> bool:
        return bool(self.errors)

    def markdown(self) -> str:
        status = (
            f"❌ {len(self.errors)} düzeltme gerekli"
            if self.errors
            else f"✅ Deterministik kontroller geçti"
        )
        if self.warnings:
            status += f"; ⚠️ {len(self.warnings)} uyarı"
        lines = [COMMENT_MARKER, "## Magibu katkı kontrolü", "", f"**Sonuç:** {status}"]
        for severity, title in (("error", "Düzeltilmesi gerekenler"), ("warning", "Uyarılar")):
            selected = [finding for finding in self.findings if finding.severity == severity]
            if not selected:
                continue
            lines.extend(["", f"### {title}", ""])
            for index, finding in enumerate(selected[:_MAX_FINDINGS_PER_SECTION], 1):
                lines.extend(
                    [
                        f"{index}. `{finding.location}` — **{finding.code}**",
                        f"   {finding.message}",
                        f"   **Düzeltme:** {finding.suggestion}",
                        "",
                    ]
                )
            hidden = len(selected) - _MAX_FINDINGS_PER_SECTION
            if hidden > 0:
                lines.append(f"> {hidden} ek bulgu yorum boyutunu sınırlamak için gösterilmedi; workflow annotation’larını inceleyin.")
        if self.checks:
            lines.extend(["", "### Geçen kontroller", ""])
            lines.extend(f"- ✅ {check}" for check in self.checks)
        lines.extend(
            [
                "",
                "> Bu kontrol şema, bağlantı ve güvenlik kurallarını denetler; doğal Türkçe, kaynak uygunluğu ve nihai kabul insan incelemesindedir.",
            ]
        )
        return "\n".join(lines).rstrip() + "\n"


def review_contribution(
    project_root: Path,
    *,
    changed_paths: Iterable[str] = (),
    pr_body: str | None = None,
) -> ContributionReport:
    """Review an already materialized repository tree without executing contributed code."""

    root = project_root.resolve()
    changed = sorted({_normalize_relative_path(path) for path in changed_paths})
    findings: list[ContributionFinding] = []
    checks: list[str] = []
    if pr_body is not None:
        findings.extend(_review_pr_body(pr_body))
        if not any(finding.code.startswith("PR_") for finding in findings):
            checks.append("PR şablonu")

    findings.extend(_scan_changed_files(root, changed))
    try:
        schema_store = SchemaStore(root / "schemas")
        for required_kind in ("registry", "blueprint", "dataset"):
            schema_store.load(required_kind)
    except (OSError, UnicodeError, ValueError, SchemaError) as exc:
        findings.append(
            ContributionFinding(
                "SCHEMA_STORE_INVALID",
                "error",
                f"Şema deposu yüklenemedi: {exc}",
                "`schemas/` altındaki JSON dosyalarını, `$id` değerlerini ve JSON Schema sözleşmelerini düzeltin.",
                "schemas",
            )
        )
        return ContributionReport(_deduplicate_findings(findings), checks)
    registries, registry_findings = _load_registries(root, schema_store)
    findings.extend(registry_findings)
    if not registry_findings:
        checks.append("Tool registry sözleşmeleri")

    findings.extend(_validate_declared_fixtures(root, registries))
    if not any(finding.code.startswith("FIXTURE_") for finding in findings):
        checks.append("Fixture bağlantıları ve sonuç şemaları")

    blueprint_findings = _validate_blueprints(root, schema_store, registries)
    findings.extend(blueprint_findings)
    if not blueprint_findings:
        checks.append("Scenario blueprint sözleşmeleri")

    dataset_findings = _validate_changed_dataset(root, changed, schema_store, registries)
    findings.extend(dataset_findings)
    if any(_is_dataset_path(path) for path in changed) and not dataset_findings:
        checks.append("Değişen dataset kayıtları")

    findings.extend(_review_change_completeness(root, changed))
    findings = _deduplicate_findings(findings)
    return ContributionReport(findings, checks)


def _review_pr_body(body: str) -> list[ContributionFinding]:
    sections = _markdown_sections(body)
    findings: list[ContributionFinding] = []
    for required in _REQUIRED_PR_SECTIONS:
        if required.casefold() not in sections:
            findings.append(
                ContributionFinding(
                    "PR_SECTION_MISSING",
                    "error",
                    f"`{required}` bölümü bulunamadı.",
                    "Güncel pull request şablonundaki bölümü ekleyip kısa ve somut biçimde doldurun.",
                )
            )
    contribution_type = sections.get("katkı türü", "")
    if contribution_type and not re.search(r"^- \[[xX]\] ", contribution_type, re.MULTILINE):
        findings.append(
            ContributionFinding(
                "PR_CONTRIBUTION_TYPE_MISSING",
                "error",
                "Hiçbir katkı türü seçilmemiş.",
                "`Katkı türü` bölümünde değişikliği en iyi tanımlayan en az bir kutuyu işaretleyin.",
            )
        )
    for section_name in ("değişiklik", "kaynak ve lisans"):
        if section_name in sections and not _meaningful_section_text(sections[section_name]):
            findings.append(
                ContributionFinding(
                    "PR_SECTION_EMPTY",
                    "error",
                    f"`{section_name.title()}` bölümü açıklama içermiyor.",
                    "Somut bilgi yazın; uygulanmıyorsa nedenini `Uygulanamaz` olarak belirtin.",
                )
            )
    return findings


def _markdown_sections(body: str) -> dict[str, str]:
    matches = list(re.finditer(r"^##\s+(.+?)\s*$", body or "", re.MULTILINE))
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        sections[match.group(1).strip().casefold()] = body[match.end():end].strip()
    return sections


def _meaningful_section_text(value: str) -> bool:
    without_comments = re.sub(r"<!--.*?-->", "", value, flags=re.DOTALL)
    without_checkboxes = re.sub(r"^- \[[ xX]\].*$", "", without_comments, flags=re.MULTILINE)
    return bool(without_checkboxes.strip())


def _scan_changed_files(root: Path, changed: list[str]) -> list[ContributionFinding]:
    findings: list[ContributionFinding] = []
    for relative in changed:
        path = root / Path(relative)
        if not path.is_file() or path.suffix.casefold() not in _TEXT_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            findings.append(
                ContributionFinding(
                    "CONTRIBUTION_FILE_UNREADABLE",
                    "error",
                    "Dosya UTF-8 metin olarak okunamadı.",
                    "Dosyayı UTF-8 olarak kaydedin ve ikili içeriği katkı veri klasörlerine koymayın.",
                    relative,
                )
            )
            continue
        for code, pattern in _SECRET_PATTERNS:
            match = pattern.search(text)
            if match:
                findings.append(
                    ContributionFinding(
                        code,
                        "error",
                        "Dosyada yüksek güvenli bir secret deseni bulundu.",
                        "Değeri derhal kaldırın, gerekiyorsa anahtarı iptal edin ve yalnız environment variable adını bırakın.",
                        relative,
                        text.count("\n", 0, match.start()) + 1,
                    )
                )
    return findings


def _load_registries(
    root: Path,
    schema_store: SchemaStore,
) -> tuple[dict[str, ToolRegistry], list[ContributionFinding]]:
    paths = {
        "canonical": root / "registry" / "registry.jsonl",
        "proposal": root / "registry" / "proposals" / "pilot_candidates.jsonl",
    }
    registries: dict[str, ToolRegistry] = {}
    findings: list[ContributionFinding] = []
    for label, path in paths.items():
        if not path.exists():
            findings.append(
                ContributionFinding(
                    "REGISTRY_FILE_MISSING",
                    "error",
                    f"{label} registry dosyası bulunamadı.",
                    "Registry dosyasını geri yükleyin; yaşam döngüsü dosyalarını sessizce kaldırmayın.",
                    _relative(root, path),
                )
            )
            continue
        try:
            registries[label] = ToolRegistry.load(path, schema_store=schema_store)
        except RegistryValidationError as exc:
            for issue in exc.issues:
                findings.append(
                    ContributionFinding(
                        issue.code,
                        "error",
                        f"{issue.message} ({issue.path})",
                        _diagnostic_suggestion(issue.code),
                        _relative(root, path),
                        issue.line,
                    )
                )
        except (OSError, UnicodeError, ValueError, SchemaError) as exc:
            findings.append(
                ContributionFinding(
                    "REGISTRY_LOAD_FAILED",
                    "error",
                    str(exc),
                    "JSONL biçimini, UTF-8 kodlamasını ve bağlı şema dosyalarını kontrol edin.",
                    _relative(root, path),
                )
            )
    return registries, findings


def _validate_declared_fixtures(
    root: Path,
    registries: dict[str, ToolRegistry],
) -> list[ContributionFinding]:
    findings: list[ContributionFinding] = []
    for registry in registries.values():
        declared: set[str] = set()
        for tool in registry.records:
            for fixture_id in tool["execution"]["fixture_ids"]:
                declared.add(fixture_id)
                try:
                    registry.load_fixture(fixture_id)
                except FileNotFoundError:
                    findings.append(
                        ContributionFinding(
                            "FIXTURE_FILE_MISSING",
                            "error",
                            f"`{fixture_id}` registry içinde tanımlı ancak fixture dosyası bulunamadı.",
                            "Registry kaydını kaldırın veya aynı ID ile şema uyumlu fixture dosyasını ekleyin.",
                            _relative(root, registry.fixtures_dir / f"{fixture_id}.json"),
                        )
                    )
                except (KeyError, TypeError, ValueError, json.JSONDecodeError, ValidationError) as exc:
                    findings.append(
                        ContributionFinding(
                            "FIXTURE_INVALID",
                            "error",
                            f"`{fixture_id}` fixture doğrulanamadı: {exc}",
                            "Function name, arguments ve result alanlarını registry input/output şemalarıyla eşitleyin.",
                            _relative(root, registry.fixtures_dir / f"{fixture_id}.json"),
                        )
                    )
        if registry.fixtures_dir and registry.fixtures_dir.exists():
            for path in registry.fixtures_dir.glob("*.json"):
                try:
                    value = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                    findings.append(
                        ContributionFinding(
                            "FIXTURE_FILE_INVALID",
                            "error",
                            f"Fixture dosyası geçerli UTF-8 JSON değil: {exc}",
                            "Dosyayı tek bir JSON object ve UTF-8 kodlamasıyla kaydedin.",
                            _relative(root, path),
                        )
                    )
                    continue
                fixture_id = value.get("fixture_id") if isinstance(value, dict) else None
                if not isinstance(fixture_id, str):
                    findings.append(
                        ContributionFinding(
                            "FIXTURE_ID_MISSING",
                            "error",
                            "Fixture dosyasında geçerli bir `fixture_id` yok.",
                            "Registry kaydındaki ID ile eşleşen bir `fixture_id` alanı ekleyin.",
                            _relative(root, path),
                        )
                    )
                elif fixture_id not in declared:
                    findings.append(
                        ContributionFinding(
                            "FIXTURE_UNDECLARED",
                            "error",
                            f"`{fixture_id}` hiçbir tool kaydının `fixture_ids` alanında tanımlı değil.",
                            "Fixture ID’yi doğru tool kaydına ekleyin veya kullanılmayan dosyayı kaldırın.",
                            _relative(root, path),
                        )
                    )
    return findings


def _validate_blueprints(
    root: Path,
    schema_store: SchemaStore,
    registries: dict[str, ToolRegistry],
) -> list[ContributionFinding]:
    registry = registries.get("proposal") or registries.get("canonical")
    if registry is None:
        return []
    validator = RuleBasedValidator(schema_store=schema_store, registry=registry)
    findings: list[ContributionFinding] = []
    seen_ids: dict[str, tuple[str, int | None]] = {}
    blueprint_root = root / "blueprints"
    paths = sorted([*blueprint_root.rglob("*.json"), *blueprint_root.rglob("*.jsonl")]) if blueprint_root.exists() else []
    for path in paths:
        relative = _relative(root, path)
        try:
            records, parse_issues = parse_path(path)
        except UnicodeError as exc:
            findings.append(
                ContributionFinding(
                    "BLUEPRINT_FILE_UNREADABLE",
                    "error",
                    f"Blueprint UTF-8 olarak okunamadı: {exc}",
                    "Dosyayı UTF-8 JSON veya JSONL olarak kaydedin.",
                    relative,
                )
            )
            continue
        findings.extend(_validation_findings(relative, parse_issues))
        for line, record in records:
            report = validator.validate_record("blueprint", record, line=line)
            findings.extend(_validation_findings(relative, report.issues))
            blueprint_id = record.get("id") if isinstance(record, dict) else None
            if not isinstance(blueprint_id, str):
                continue
            if blueprint_id in seen_ids:
                first_file, first_line = seen_ids[blueprint_id]
                findings.append(
                    ContributionFinding(
                        "BLUEPRINT_ID_DUPLICATE_ACROSS_FILES",
                        "error",
                        f"`{blueprint_id}` daha önce `{first_file}:{first_line or 1}` içinde tanımlanmış.",
                        "Yeni ve kararlı bir blueprint ID kullanın; mevcut ID’yi başka dosyada tekrar etmeyin.",
                        relative,
                        line,
                    )
                )
            else:
                seen_ids[blueprint_id] = (relative, line)
    return findings


def _validate_changed_dataset(
    root: Path,
    changed: list[str],
    schema_store: SchemaStore,
    registries: dict[str, ToolRegistry],
) -> list[ContributionFinding]:
    registry = registries.get("proposal") or registries.get("canonical")
    if registry is None:
        return []
    validator = RuleBasedValidator(schema_store=schema_store, registry=registry)
    findings: list[ContributionFinding] = []
    for relative in changed:
        if not _is_dataset_path(relative) or Path(relative).suffix.casefold() not in {".json", ".jsonl"}:
            continue
        path = root / Path(relative)
        if not path.exists():
            continue
        try:
            report = validator.validate_path("dataset", path)
        except (OSError, UnicodeError, ValueError) as exc:
            findings.append(
                ContributionFinding(
                    "DATASET_FILE_UNREADABLE",
                    "error",
                    f"Dataset dosyası doğrulanamadı: {exc}",
                    "Dosyayı UTF-8 JSON/JSONL olarak kaydedip dataset sözleşmesine göre düzeltin.",
                    relative,
                )
            )
        else:
            findings.extend(_validation_findings(relative, report.issues))
    return findings


def _review_change_completeness(root: Path, changed: list[str]) -> list[ContributionFinding]:
    findings: list[ContributionFinding] = []
    if any(path.startswith("schemas/") for path in changed):
        findings.append(
            ContributionFinding(
                "SCHEMA_CHANGE_MANUAL_REVIEW",
                "warning",
                "Şema sözleşmesi değişmiş; güvenli PR kontrolü katkı dalındaki şemayı çalıştırmaz.",
                "Şema uyumluluğunu normal CI sonucu ve insan incelemesiyle doğrulayın; migration etkisini PR açıklamasına yazın.",
            )
        )
    execution_changed = any(path.startswith("src/tool_call_tr/execution/") for path in changed)
    tests_changed = any(path.startswith("tests/") for path in changed)
    if execution_changed and not tests_changed:
        findings.append(
            ContributionFinding(
                "EXECUTION_TEST_MISSING",
                "warning",
                "Execution implementasyonu değişmiş ancak test dosyasında değişiklik görünmüyor.",
                "Başarılı yolun yanında en az bir hata, reset veya timeout davranışını sınayan test ekleyin.",
            )
        )
    registry_changed = any(path.startswith("registry/") and path.endswith(".jsonl") for path in changed)
    if registry_changed and not tests_changed:
        findings.append(
            ContributionFinding(
                "REGISTRY_TEST_NOT_CHANGED",
                "warning",
                "Registry değişmiş ancak bu sözleşmeyi kapsayan test değişikliği görünmüyor.",
                "Yeni tool davranışını veya önemli sözleşme sınırını doğrulayan hedefli test ekleyin.",
            )
        )
    dataset_changed = any(_is_dataset_path(path) for path in changed)
    quality_report_present = any(path.startswith("review/dataset/") and path.endswith(".json") for path in changed)
    if dataset_changed and not quality_report_present:
        findings.append(
            ContributionFinding(
                "QUALITY_REPORT_NOT_CHANGED",
                "warning",
                "Dataset kaydı değişmiş ancak aynı PR’da kalite raporu değişikliği görünmüyor.",
                "İlgili `dataset quality` raporunu ekleyin veya bu değişikliğin neden rapor gerektirmediğini PR’da açıklayın.",
            )
        )
    return findings


def _validation_findings(file: str, issues: Iterable[ValidationIssue]) -> list[ContributionFinding]:
    return [
        ContributionFinding(
            issue.code,
            "warning" if issue.severity.value == "warning" else "error",
            f"{issue.message} ({issue.path})",
            _diagnostic_suggestion(issue.code),
            file,
            issue.line,
        )
        for issue in issues
    ]


def _diagnostic_suggestion(code: str) -> str:
    if code.startswith("SCHEMA_") or code.startswith("REGISTRY_SCHEMA"):
        return "İlgili JSON yolunu şema sözleşmesine göre düzeltin; zorunlu alan, tür, enum ve ek alan kısıtlarını kontrol edin."
    if code.startswith("ARG_"):
        return "Tool argümanlarını registry input schema’sındaki isim, tür, enum ve zorunlu alanlarla eşitleyin."
    if code.startswith("RESULT_") or "RESULT" in code:
        return "Tool sonucunu registry output schema’sıyla ve beklenen fixture sonucuyla eşitleyin."
    if "INTERNAL_MARKER" in code:
        return "İç operasyon terimini doğal kullanıcı/asistan metninden çıkarın; gerekli provenance bilgisini yalnız metadata’da tutun."
    if "FUNCTION" in code or "TOOL" in code:
        return "Function adını ve exposed tool listesini seçilen registry kaydıyla birebir eşitleyin."
    if "DUPLICATE" in code:
        return "Kararlı ve benzersiz bir ID kullanın veya yinelenen kaydı kaldırın."
    return "Hata mesajındaki dosya ve JSON yolunu mevcut registry/blueprint sözleşmesine göre düzeltip doğrulamayı yeniden çalıştırın."


def _normalize_relative_path(value: str) -> str:
    path = PurePosixPath(value.replace("\\", "/"))
    if not value or path.is_absolute() or ".." in path.parts or (path.parts and ":" in path.parts[0]):
        raise ValueError(f"unsafe contribution path: {value}")
    return path.as_posix()


def _relative(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _is_dataset_path(path: str) -> bool:
    return path.startswith("data/dataset/needs_revision/") or path.startswith("data/dataset/accepted/")


def _deduplicate_findings(findings: list[ContributionFinding]) -> list[ContributionFinding]:
    seen: set[tuple[object, ...]] = set()
    result: list[ContributionFinding] = []
    for finding in findings:
        key = (finding.code, finding.severity, finding.message, finding.file, finding.line)
        if key not in seen:
            seen.add(key)
            result.append(finding)
    return sorted(result, key=lambda item: (item.severity != "error", item.file or "", item.line or 0, item.code))
