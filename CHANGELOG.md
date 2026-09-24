# 0.1.2a1 — 2026-09-23

- Preserve full parameter syntax and parse nested documented signatures.
- Flag collisions, rebinding and incomplete extraction instead of guessing removals.
- Combine exact-span edits per line and bind proposals to source/line digests.
- Detach grounding, bound input and defer unsafe inline signatures to human review.
- Add 37 regressions, packaging, Apache 2.0 LICENSE/NOTICE, README and CI.
- Compatibility: regenerate artifacts; grounded_in is now a list.

# Changelog — DocSync (JY-S010-P001)

## 0.1.1-partial — 2026-09-14 (audit A011)

Baseline fingerprint: build-0001 product.zip
sha256 b36da9a50479b4cb7ed3cd8d531923162a5e20fb7657be826966e6f6cb4271d4
(6793 bytes), baseline version 0.1.0-partial (docsync/core.py VERSION).

Repairs only; no new public API; patch bump per policy.

### A011-F1 — async methods in classes not extracted (severity: high)
- Observed (reproduced on baseline): `extract_code_interface` captured
  top-level `async def` functions but skipped `async def` methods inside
  classes (only `ast.FunctionDef` matched in class bodies). A correct doc
  reference to an async method (e.g. `` `C.arun(self, x)` ``) was reported
  as high-severity `documented-symbol-missing`, and the method could never
  be reported as undocumented.
- Expected: async methods are public interface like sync methods.
- Fix: class-body scan now matches `(ast.FunctionDef, ast.AsyncFunctionDef)`.

### A011-F2 — returned findings alias caller-owned mutable dicts (severity: medium)
- Observed (reproduced on baseline): `detect_drift` embedded the exact
  `sym` and `ref` dict objects from its inputs into returned findings;
  mutating `findings[i]["code"]["signature"]` corrupted the caller's
  `code_iface`, and multiple findings on one symbol shared one dict.
- Expected: returned findings are isolated snapshots.
- Fix: `detect_drift` deep-copies the doc ref and code symbol into each
  finding.

### Compatibility
- No public signatures changed; report schema unchanged
  (`docsync/report/v1`). Behavioral deltas: async class methods now
  appear in interfaces/reports; findings no longer share identity with
  inputs (code that relied on aliasing mutation would change behavior —
  none known).

### Rollback
- Restore baseline build-0001 product.zip
  (sha256 b36da9a50479b4cb7ed3cd8d531923162a5e20fb7657be826966e6f6cb4271d4).
