# Security boundaries

DocSync processes supplied strings and never executes source, applies edits,
reads filesystem paths, or writes repository files. Output can include source
defaults, annotations, documentation lines and path labels. These may contain
secrets or personal information; sanitize before sharing or logging reports.

AST extraction is static and incomplete. It cannot prove the runtime interface,
resolve modules/imports, evaluate decorators, or establish repository coverage.
Names colliding across files require human disambiguation. Missing from supplied
input is not proof of deletion. Syntax/conditional/decorator uncertainty blocks
automatic replacement proposals.

The Markdown scanner recognizes a limited inline form. Review context and syntax
before using any proposal. Report hashes and source/line preconditions are content
bindings, not signatures. An external application must independently verify
current file contents, target paths, access authority and review state.

File/model size and item limits cover normal APIs, not malicious in-process Python
code, memory exhaustion during parsing, or every Python grammar edge case. Exposed
services need request limits and process isolation. No third-party runtime
dependencies exist; no build-tool vulnerability scan is claimed.
Report defects privately using sanitized minimal source examples.
