# Audit and hardening — 0.1.2a1

Date: 2026-09-23. Source: JY-S010-P001 / 0.1.1-partial / run-0001 / product.
Reviewed all extraction, drift and patch-proposal code. Original source is separate.

## Repaired findings

- Signature extraction discarded defaults, annotations and argument-kind markers.
  AST normalization now preserves these interface details and return annotations.
- Markdown argument splitting broke nested expressions and defaults. Declaration
  parsing now handles nested syntax; fenced/comment/escaped examples are excluded.
- Same-named symbols overwrote earlier source facts. Duplicate definitions, simple
  rebinding and cross-file collisions become explicit ambiguity.
- Syntax failures could falsely imply removed symbols. Incomplete extraction now
  produces unresolved findings without removal/replacement proposals. Conditional
  definitions and unsupported decorators also require manual review.
- Class-only inline references were not recognized. Bare identifiers now count
  only when resolving an extracted class, avoiding general inline-code false alarms.
- Per-finding string replacement created conflicting patches on one line and
  replaced repeated occurrences without span grounding. Exact span edits are now
  combined per line, preserving trailing spaces and rejecting conflicts/overlaps.
- Findings/proposals lost source content binding, patch hashes omitted locations,
  and patch grounding retained mutable aliases. Full structured digests, file/line
  preconditions and detached grounding now preserve the review context.
- Backticks in source defaults could create malformed Markdown proposals. Those
  cases defer to manual review rather than emitting an unsafe inline replacement.
- Source/model sizes, file counts and analysis items are now bounded.

## Verification and release

16 inherited tests passed before changes. Signature/grounding assertions were
updated for the intentional richer format. 53 source and installed-wheel tests
pass, including 37 regressions. Historical check evidence remains separate.
CI covers Linux Python 3.10/3.12/3.14 and Windows Python 3.12.

Version 0.1.1-partial -> 0.1.2a1. Regenerate all findings/reports; grounded_in is
now a list and low-level patch proposals require finding digests. Added packaging,
pinned-action CI, README, security docs and Apache 2.0 LICENSE/NOTICE naming
RUSSELL PHILIP SMITHSON.

No third-party runtime dependencies need upgrading or scanning. No build-tool
vulnerability scan is claimed. Static extraction, partial Markdown support and
external patch review remain limitations; production promotion is untouched.
