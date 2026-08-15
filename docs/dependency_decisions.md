# Dependency decisions

`pyproject.toml` carries the machine-readable dependency lists; this document
carries the reason for each entry and is where a proposed dependency is argued
before the version pin changes. A dependency that is not justified here has no
recorded decision behind it.

- Python `>=3.11`: supports `StrEnum`, modern typing, and a maintainable
  standard-library-first implementation.
- `jsonschema>=4.21,<5`: supplies Draft 2020-12,
  reference registries, meta-schema checks, and format validation.
- `pytest>=8,<9` and `pytest-cov>=5,<7`: development/test dependencies only.
- `argparse`, dataclasses, JSON/JSONL, hashing, logging, paths, protocols, and
  `urllib` JSON transport use the Python standard library.

Pydantic, third-party HTTP clients/provider SDKs, databases, queues, web
frameworks, containers, and embedding libraries are intentionally absent. The
implemented DeepSeek/OpenAI/real-API transports are dependency-free and
injectable in tests. A provider SDK should be proposed only if it adds a concrete
capability that the small transport cannot safely support.
