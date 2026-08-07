# Contribution workflow

1. Choose the lifecycle first. Preserve dataset inputs under
   `data/dataset/raw/` and independent benchmark inputs under
   `data/benchmark/raw/`; record source, split, license, and upstream ID.
2. Propose or select a versioned registry tool. A `demo` tool is not approved.
3. Author and validate a scenario blueprint before generating a candidate.
4. Generate or convert one candidate into the shared record shape, then place it
   in either `data/dataset/staging/` or `data/benchmark/staging/`. Never copy a
   record between the two lifecycles and never create category-specific formats.
5. Run schema and layered validation. Failed records go to `needs_revision` or
   `rejected`, never `accepted`.
6. Execute only through the recorded environment. Any real-to-mock change must be
   explicit in transformation history; never use live changing benchmark gold.
7. Run duplicate/provenance checks and semantic/Turkish quality review.
8. Assign a language or technical reviewer. Contributors cannot finally approve
   their own records; multi-tool/sequential/marked records need both perspectives.
9. Export through `dataset export` or `benchmark export`; do not copy files
   manually into a release.
10. Compare accepted benchmark candidates against the accepted dataset with
    `benchmark contamination-check`, then freeze gold with a checksum manifest.
11. Store model predictions under `runs/`, never back into benchmark gold.

Machine identifiers, function names, parameter keys, enum values, call IDs, and
structured result fields stay unchanged and English where specified. Natural
user/assistant text and tool/parameter descriptions should be natural Turkish.
