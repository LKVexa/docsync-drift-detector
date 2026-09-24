# DocSync Drift Detector

**0.1.2a1 — experimental partial candidate, JY-S010-P001**

Compares supplied Python source and Markdown API references, explains interface
drift, and proposes source-grounded documentation edits for human review. It reads
no files itself, executes no source and has no write or patch-application API.

## Install and use

Python 3.10 or newer; no third-party runtime dependencies.

~~~sh
python -m pip install .
python -m unittest discover -s tests -t .
~~~

~~~python
from docsync.core import sync_report

report = sync_report(
    {"api.py": "def connect(host, timeout=5): pass"},
    {"api.md": "Use "+chr(96)+"connect(host)"+chr(96)+" to open a connection."},
)
~~~

Inspect parse_errors, ambiguous_symbols and analysis_complete before reviewing
findings. Every patch remains draft: true at closure state TRACE. Accept, Prove
and Close require external human review and evidence.

## Extraction and uncertainty

Python AST extraction covers top-level public functions/classes and immediate
public methods, including async declarations. Signatures retain defaults,
annotations, positional-only and keyword-only markers, variadics and return
annotations. No code, default expression, import or decorator is executed.

Markdown supports single-backtick inline signatures and bare class references.
Signature arguments are parsed as Python declaration syntax, so nested defaults
and annotations work. Fenced code, HTML comment lines, escaped delimiters and
double-backtick spans are ignored. This is a bounded scanner, not a full Markdown
implementation; unsupported forms need human review.

Duplicate definitions, cross-file name collisions and simple rebinding are
ambiguous. Syntax failures, conditional public definitions and unsupported
decorators prevent confident drift proposals. Incomplete code extraction produces
unresolved findings without replacement or removal proposals. Staticmethod and
classmethod declarations are recognized as declared syntax, not runtime validation.

Names remain unqualified by module. If two files declare the same public name,
the report abstains for that name; it does not choose the last file. A missing
symbol means absent from supplied code, not proven deleted from the repository.
Verify that input coverage is complete before considering removal.

## Reviewable proposals

Multiple mismatches on one Markdown line become one replacement using exact
character spans. Untouched text and trailing spaces are preserved. Conflicting
snapshots, overlapping spans and inconsistent findings are rejected.

Each replacement includes source grounding, expected_doc_digest and
expected_line_digest. An external tool must compare those preconditions with
current contents before applying a reviewed proposal. DocSync never applies it.
Signatures that cannot fit a single inline span become manual-review flags.
Additions defer prose to a human; removals are flags only.

Finding, patch and report digests cover complete structured content, including
locations and provenance. They detect accidental changes, not authenticity or
authorization. Do not execute arbitrary text included in reports.

## Input limits and compatibility

Inputs are bounded path-to-text mappings: at most 1,000 files, 1 MiB UTF-8 per file,
16 MiB combined, and 10,000 symbols/references/findings at relevant stages. File
paths are labels up to 1,024 characters. Invalid types/limits raise ValueError.
Malformed Python is reported as an extraction diagnostic. No filesystem access
is performed using supplied paths.

Version 0.1.1-partial -> 0.1.2a1 changes signature normalization and patch grouping.
Regenerate findings/reports. Low-level propose_patches now requires sealed findings
from detect_drift. grounded_in is a list, and patch/report digests are stronger
content bindings. Schema identifiers remain v1 with additive metadata.

53 tests include 16 inherited checks and 37 regressions. Source and installed-wheel
results are in [CHECK_RUNS](docs/CHECK_RUNS.json), with [AUDIT](docs/AUDIT.md) and
[SECURITY](SECURITY.md). CI covers Linux Python 3.10/3.12/3.14 and Windows Python 3.12.

Runtime-generated interfaces, module/import resolution, nested public classes,
multiple languages, CLI/config drift and the original 356-entry roadmap remain
outside this candidate. No production promotion or BLOCKER closure is claimed.

## License

Copyright 2026 **RUSSELL PHILIP SMITHSON**.
[Apache License 2.0](LICENSE), with [NOTICE](NOTICE).
No third-party code is vendored.
