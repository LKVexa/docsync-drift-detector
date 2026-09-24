"""Read-only Python/Markdown drift analysis; all proposals require review."""
from __future__ import annotations
import ast
import copy
import hashlib
import json
import re

VERSION = "0.1.2a1"
MAX_FILE_BYTES = 1024 * 1024
MAX_TOTAL_BYTES = 16 * 1024 * 1024
MAX_FILES = 1000
MAX_ITEMS = 10000
_NAME = r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*"
_DOC_SIG = re.compile(r"^(?P<name>"+_NAME+r")\((?P<args>.*)\)(?:\s*->\s*(?P<returns>.+))?$")
_CODE_SPAN = re.compile(r"(?<![\x60\\])\x60([^\x60\n]+)\x60(?!\x60)")

def _digest(text):
    if type(text) is not str:
        raise ValueError("digest input must be text")
    try:
        return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()
    except UnicodeError:
        raise ValueError("text must be valid UTF-8") from None

def _model_digest(value):
    try:
        text = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError, RecursionError):
        raise ValueError("artifact must be finite JSON") from None
    if len(text.encode("utf-8")) > MAX_TOTAL_BYTES:
        raise ValueError("artifact size limit exceeded")
    return _digest(text)

def _source(text, path):
    if type(path) is not str or not path or len(path) > 1024 or any(ord(c) < 32 for c in path):
        raise ValueError("source path must be a bounded label")
    if type(text) is not str:
        raise ValueError("source contents must be text")
    try:
        if len(text.encode("utf-8")) > MAX_FILE_BYTES:
            raise ValueError("source file exceeds size limit")
    except UnicodeError:
        raise ValueError("source text must be valid UTF-8") from None
    return _digest(text)

def _signature(fn, name):
    signature = name + "(" + ast.unparse(fn.args) + ")"
    if fn.returns:
        signature += " -> " + ast.unparse(fn.returns)
    return signature

def extract_code_interface(py_source, path):
    digest = _source(py_source, path)
    try:
        tree = ast.parse(py_source)
    except (SyntaxError, ValueError, RecursionError):
        return {"symbols": {}, "errors": [f"{path}: Python source cannot be parsed"],
                "ambiguous_symbols": []}
    symbols, ambiguous, errors = {}, set(), []
    def record(name, node, kind):
        if any(not isinstance(decorator, ast.Name) or decorator.id not in ("staticmethod", "classmethod")
               for decorator in node.decorator_list):
            errors.append(f"{path}: decorated public definitions require manual review")
        if name in symbols or name in ambiguous:
            symbols.pop(name, None)
            ambiguous.add(name)
            return
        try:
            signature = name if kind=="class" else _signature(node, name)
        except (RecursionError, ValueError):
            errors.append(f"{path}: signature normalization failed")
            ambiguous.add(name)
            return
        symbols[name] = {"kind": kind,
            "signature": signature,
            "async": isinstance(node, ast.AsyncFunctionDef),
            "provenance": {"path": path, "line": node.lineno, "source_digest": digest}}
    for node in tree.body:
        if isinstance(node, (ast.If, ast.Try, ast.For, ast.While, ast.With)) and any(
                isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                and not child.name.startswith("_") for child in ast.walk(node)):
            errors.append(f"{path}: conditional public definitions require manual review")
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
            record(node.name, node, "function")
        elif isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
            record(node.name, node, "class")
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and not child.name.startswith("_"):
                    record(node.name+"."+child.name, child, "method")
    rebound = set()
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            rebound.update(child.id for target in targets for child in ast.walk(target) if isinstance(child, ast.Name))
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            rebound.update(alias.asname or alias.name.split(".")[0] for alias in node.names)
    ambiguous.update(rebound & set(symbols))
    for name in list(symbols):
        if name in ambiguous or any(name.startswith(parent+".") for parent in ambiguous):
            ambiguous.add(name)
            symbols.pop(name)
    if len(symbols) + len(ambiguous) > MAX_ITEMS:
        raise ValueError("symbol limit exceeded")
    return {"symbols": symbols, "errors": errors, "ambiguous_symbols": sorted(ambiguous)}

def extract_doc_references(md_text, path):
    digest = _source(md_text, path)
    refs, fence = [], None
    in_comment = False
    for line_number, line in enumerate(md_text.splitlines(), 1):
        fence_match = re.match(r"^\s{0,3}(\x60{3,}|~{3,})", line)
        if fence_match:
            delimiter = fence_match.group(1)
            if fence is None:
                fence = delimiter
            elif delimiter[0] == fence[0] and len(delimiter) >= len(fence):
                fence = None
            continue
        if fence:
            continue
        # Ignore comments conservatively, including lines with mixed comment/prose.
        if "<!--" in line:
            in_comment = True
        if in_comment:
            if "-->" in line:
                in_comment = False
            continue
        for match in _CODE_SPAN.finditer(line):
            content = match.group(1)
            signature = _DOC_SIG.fullmatch(content)
            if signature:
                try:
                    stub = "def _("+signature["args"]+")"
                    if signature["returns"]:
                        stub += " -> "+signature["returns"]
                    fn = ast.parse(stub+":\n    pass\n").body[0]
                    normalized = _signature(fn, signature["name"])
                except (SyntaxError, ValueError, RecursionError):
                    continue
                name, form = signature["name"], "signature"
            elif re.fullmatch(_NAME, content):
                name, normalized, form = content, content, "identifier"
            else:
                continue
            refs.append({"name": name, "form": form, "documented_signature": normalized,
                "raw": match.group(0), "span": [match.start(), match.end()],
                "provenance": {"path": path, "line": line_number, "line_text": line,
                               "source_digest": digest, "line_digest": _digest(line)}})
            if len(refs) > MAX_ITEMS:
                raise ValueError("reference limit exceeded")
    return refs

def _sealed_finding(value):
    value = copy.deepcopy(value)
    value["finding_digest"] = _model_digest(value)
    return value

def detect_drift(code_iface, doc_refs):
    _model_digest(code_iface)
    _model_digest(doc_refs)
    if type(code_iface) is not dict or type(code_iface.get("symbols")) is not dict or type(doc_refs) is not list:
        raise ValueError("interface and references have invalid shapes")
    if len(code_iface["symbols"]) > MAX_ITEMS or len(doc_refs) > MAX_ITEMS:
        raise ValueError("analysis item limit exceeded")
    symbols = code_iface["symbols"]
    for name, symbol in symbols.items():
        if type(name) is not str or not re.fullmatch(_NAME, name) or type(symbol) is not dict or symbol.get("kind") not in ("function", "class", "method") or type(symbol.get("signature")) is not str:
            raise ValueError("invalid code symbol")
        provenance = symbol.get("provenance")
        if type(provenance) is not dict or type(provenance.get("path")) is not str or type(provenance.get("line")) is not int or provenance["line"] < 1:
            raise ValueError("invalid code provenance")
    for field in ("ambiguous_symbols", "errors"):
        if type(code_iface.get(field, [])) is not list or any(type(item) is not str for item in code_iface.get(field, [])):
            raise ValueError("invalid interface diagnostics")
    ambiguous = set(code_iface.get("ambiguous_symbols", []))
    errors = code_iface.get("errors", [])
    findings, documented = [], set()
    for ref in doc_refs:
        if type(ref) is not dict or type(ref.get("name")) is not str:
            raise ValueError("invalid documentation reference")
        if type(ref.get("documented_signature")) is not str or type(ref.get("raw")) is not str or type(ref.get("provenance")) is not dict or type(ref.get("span")) is not list or len(ref["span"]) != 2:
            raise ValueError("documentation reference lacks source evidence")
        name, symbol = ref["name"], symbols.get(ref["name"])
        if ref.get("form") == "identifier" and (symbol is None or symbol["kind"] != "class"):
            continue
        documented.add(name)
        common = {"symbol": name, "doc": ref}
        if errors or name in ambiguous:
            findings.append(_sealed_finding(dict(common, kind="unresolved-symbol", severity="high",
                explanation="code inventory is incomplete or symbol identity is ambiguous; manual review required")))
        elif symbol is None:
            findings.append(_sealed_finding(dict(common, kind="documented-symbol-missing", severity="high",
                explanation=f"no supplied code definition resolves {name}; verify repository scope before removal")))
        elif symbol["kind"] in ("function", "method") and ref["documented_signature"] != symbol["signature"]:
            findings.append(_sealed_finding(dict(common, kind="signature-mismatch", code=symbol, severity="medium",
                explanation=f"docs say {ref['documented_signature']} but code defines {symbol['signature']}")))
    if not errors:
        for name, symbol in symbols.items():
            if name not in documented and symbol["kind"] in ("function", "class"):
                findings.append(_sealed_finding({"kind": "undocumented-symbol", "symbol": name,
                    "code": symbol, "severity": "low", "explanation": f"public {symbol['kind']} {name} has no documentation reference"}))
    order = {"high": 0, "medium": 1, "low": 2}
    return sorted(findings, key=lambda item: (order[item["severity"]], item["symbol"],
        item.get("doc", {}).get("provenance", {}).get("path", ""),
        item.get("doc", {}).get("span", [0])[0]))

def propose_patches(findings):
    _model_digest(findings)
    if type(findings) is not list or len(findings) > MAX_ITEMS:
        raise ValueError("findings must be a bounded list")
    patches, replacements = [], {}
    for original in findings:
        if type(original) is not dict:
            raise ValueError("finding must be an object")
        finding = copy.deepcopy(original)
        digest = finding.pop("finding_digest", None)
        if digest != _model_digest(finding):
            raise ValueError("finding digest missing or mismatched")
        kind = finding["kind"]
        if kind == "unresolved-symbol":
            continue
        if kind in ("signature-mismatch", "documented-symbol-missing"):
            doc = finding["doc"]
            provenance = doc["provenance"]
            line = provenance["line_text"]
            start, end = doc["span"]
            if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(line) or line[start:end] != doc["raw"]:
                raise ValueError("documentation span does not match source line")
            if _digest(line) != provenance["line_digest"]:
                raise ValueError("documentation line digest mismatch")
            if kind == "signature-mismatch":
                if "\x60" in finding["code"]["signature"] or "\n" in finding["code"]["signature"]:
                    patches.append({"action": "flag-manual-review", "file": provenance["path"],
                        "line": provenance["line"], "old": line, "new": None,
                        "grounded_in": [finding["code"]["provenance"]],
                        "rationale": "signature cannot safely fit a single inline code span"})
                    continue
                key = (provenance["path"], provenance["line"])
                group = replacements.setdefault(key, {"provenance": provenance, "edits": {}, "grounding": [], "reasons": []})
                if group["provenance"] != provenance:
                    raise ValueError("conflicting source snapshots on the same line")
                replacement = "\x60"+finding["code"]["signature"]+"\x60"
                if (start, end) in group["edits"] and group["edits"][(start, end)] != replacement:
                    raise ValueError("conflicting replacements")
                group["edits"][(start, end)] = replacement
                if finding["code"]["provenance"] not in group["grounding"]:
                    group["grounding"].append(finding["code"]["provenance"])
                group["reasons"].append(finding["explanation"])
            else:
                patches.append({"action": "flag-for-removal", "file": provenance["path"], "line": provenance["line"],
                    "old": line, "new": None, "expected_doc_digest": provenance["source_digest"],
                    "expected_line_digest": provenance["line_digest"],
                    "rationale": finding["explanation"]+" — removal needs human confirmation; no content is deleted"})
        elif kind == "undocumented-symbol":
            patches.append({"action": "suggest-addition", "file": None, "line": None, "old": None,
                "new": (None if "\x60" in finding["code"]["signature"] else "\x60"+finding["code"]["signature"]+"\x60 — (documentation needed; content is a human authoring task)"),
                "grounded_in": [finding["code"]["provenance"]], "rationale": finding["explanation"]})
        else:
            raise ValueError("unsupported finding kind")
    for (path, number), group in sorted(replacements.items()):
        provenance = group["provenance"]
        edits = sorted(group["edits"].items())
        if any(left[0][1] > right[0][0] for left, right in zip(edits, edits[1:])):
            raise ValueError("overlapping replacements")
        new_line = provenance["line_text"]
        for (start, end), replacement in reversed(edits):
            new_line = new_line[:start]+replacement+new_line[end:]
        patches.append({"action": "replace-line", "file": path, "line": number,
            "old": provenance["line_text"], "new": new_line,
            "expected_doc_digest": provenance["source_digest"], "expected_line_digest": provenance["line_digest"],
            "grounded_in": sorted(group["grounding"], key=lambda item: (item["path"], item["line"])),
            "rationale": "; ".join(sorted(set(group["reasons"])))})
    for patch in patches:
        patch["draft"] = True
        patch["closure_state"] = "TRACE"
        patch["patch_digest"] = _model_digest(patch)
    return sorted(patches, key=lambda item: (item["file"] or "", item["line"] or 0, item["action"], item["patch_digest"]))

def sync_report(py_files, md_files):
    if type(py_files) is not dict or type(md_files) is not dict or len(py_files)+len(md_files) > MAX_FILES:
        raise ValueError("file inputs must be bounded path-to-text mappings")
    total = 0
    for files in (py_files, md_files):
        for path, text in files.items():
            _source(text, path)
            total += len(text.encode("utf-8"))
    if total > MAX_TOTAL_BYTES:
        raise ValueError("combined source size limit exceeded")
    symbols, errors, ambiguous = {}, [], set()
    for path, source in sorted(py_files.items()):
        interface = extract_code_interface(source, path)
        errors.extend(interface["errors"])
        ambiguous.update(interface["ambiguous_symbols"])
        for name, symbol in interface["symbols"].items():
            if name in symbols or name in ambiguous:
                ambiguous.add(name)
            else:
                symbols[name] = symbol
    for name in ambiguous:
        symbols.pop(name, None)
    refs = []
    for path, text in sorted(md_files.items()):
        refs.extend(extract_doc_references(text, path))
    findings = detect_drift({"symbols": symbols, "errors": errors, "ambiguous_symbols": sorted(ambiguous)}, refs)
    report = {"schema": "docsync/report/v1", "docsync_version": VERSION,
        "code_symbols": len(symbols), "doc_references": len(refs), "parse_errors": errors,
        "ambiguous_symbols": sorted(ambiguous), "analysis_complete": not errors and not ambiguous,
        "findings": findings, "proposed_patches": propose_patches(findings),
        "draft_only": True, "write_access": False,
        "closure_note": "findings are at TRACE; Accept/Prove/Close require human review and applied evidence"}
    report["report_digest"] = _model_digest(report)
    return report
