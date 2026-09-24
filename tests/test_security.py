import copy
import unittest
from unittest.mock import patch
from docsync.core import (extract_code_interface, extract_doc_references, detect_drift,
                          propose_patches, sync_report, _model_digest)

def quoted(value):
    return chr(96)+value+chr(96)

class SecurityRegressions(unittest.TestCase):
    def report(self, code="def f(a):\n    pass\n", docs=None):
        return sync_report({"a.py": code}, {"a.md": quoted("f(b)") if docs is None else docs})

    def test_defaults_preserved(self):
        iface = extract_code_interface("def f(x=3): pass", "a.py")
        self.assertEqual(iface["symbols"]["f"]["signature"], "f(x=3)")

    def test_parameter_kinds_preserved(self):
        signature = extract_code_interface("def f(a, /, b, *, c, **kw): pass", "a.py")["symbols"]["f"]["signature"]
        self.assertEqual(signature, "f(a, /, b, *, c, **kw)")

    def test_annotations_and_return_preserved(self):
        signature = extract_code_interface("def f(x: int) -> str: pass", "a.py")["symbols"]["f"]["signature"]
        self.assertEqual(signature, "f(x: int) -> str")

    def test_nested_defaults_and_annotations_parse(self):
        docs = quoted("f(x: tuple[int, int]=(1, 2), y=dict(a=3)) -> list[int]")
        refs = extract_doc_references(docs, "a.md")
        self.assertEqual(len(refs), 1)
        self.assertIn("dict(a=3)", refs[0]["documented_signature"])

    def test_equivalent_normalized_signatures_match(self):
        report = self.report("def f(x=(1,2)): pass", quoted("f(x = (1, 2))"))
        self.assertEqual(report["findings"], [])

    def test_changed_default_is_detected(self):
        report = self.report("def f(x=2): pass", quoted("f(x=1)"))
        self.assertEqual(report["findings"][0]["kind"], "signature-mismatch")

    def test_star_marker_difference_is_detected(self):
        report = self.report("def f(*, x): pass", quoted("f(x)"))
        self.assertEqual(report["findings"][0]["kind"], "signature-mismatch")

    def test_class_identifier_reference_counts(self):
        report = self.report("class C: pass", quoted("C"))
        self.assertEqual(report["findings"], [])

    def test_unknown_bare_identifiers_are_ignored(self):
        report = self.report("", "The "+quoted("value")+" is optional.")
        self.assertEqual(report["findings"], [])

    def test_fenced_examples_not_treated_as_references(self):
        text = chr(96)*3+"python\n"+quoted("f(x)")+"\n"+chr(96)*3+"\n"+quoted("f(y)")
        self.assertEqual([r["documented_signature"] for r in extract_doc_references(text, "a.md")], ["f(y)"])

    def test_tilde_fences_ignored(self):
        self.assertEqual(extract_doc_references("~~~\n"+quoted("f(x)")+"\n~~~", "a.md"), [])

    def test_multiline_comments_ignored(self):
        self.assertEqual(extract_doc_references("<!--\n"+quoted("f(x)")+"\n-->", "a.md"), [])

    def test_escaped_and_double_backticks_not_single_spans(self):
        text = "\\"+quoted("f(x)")+" and "+chr(96)*2+"f(y)"+chr(96)*2
        self.assertEqual(extract_doc_references(text, "a.md"), [])

    def test_duplicate_symbols_across_files_are_ambiguous(self):
        report = sync_report({"a.py": "def f(a): pass", "b.py": "def f(b): pass"}, {"a.md": quoted("f(c)")})
        self.assertEqual(report["ambiguous_symbols"], ["f"])
        self.assertEqual(report["findings"][0]["kind"], "unresolved-symbol")
        self.assertEqual(report["proposed_patches"], [])

    def test_duplicate_same_file_symbol_is_ambiguous(self):
        report = self.report("def f(a): pass\ndef f(b): pass")
        self.assertEqual(report["ambiguous_symbols"], ["f"])
        self.assertEqual(report["proposed_patches"], [])

    def test_duplicate_class_invalidates_methods(self):
        iface = extract_code_interface("class C:\n def a(self): pass\nclass C:\n def b(self): pass", "a.py")
        self.assertEqual(iface["symbols"], {})
        self.assertEqual(iface["ambiguous_symbols"], ["C", "C.a", "C.b"])

    def test_rebound_function_is_ambiguous(self):
        iface = extract_code_interface("def f(a): pass\nf = other", "a.py")
        self.assertEqual(iface["symbols"], {})
        self.assertIn("f", iface["ambiguous_symbols"])

    def test_conditional_definition_abstains(self):
        for code in ("if enabled:\n def f(a): pass", "@decorator\ndef f(a): pass"):
            report = self.report(code, quoted("f(b)"))
            self.assertTrue(report["parse_errors"])
            self.assertEqual(report["proposed_patches"], [])

    def test_syntax_error_never_suggests_removal(self):
        report = self.report("def broken(:", quoted("f(b)"))
        self.assertFalse(report["analysis_complete"])
        self.assertEqual(report["findings"][0]["kind"], "unresolved-symbol")
        self.assertEqual(report["proposed_patches"], [])

    def test_partial_parse_never_suggests_replacements(self):
        report = sync_report({"a.py": "def f(a): pass", "b.py": "def broken(:"}, {"a.md": quoted("f(b)")})
        self.assertEqual(report["proposed_patches"], [])

    def test_same_line_edits_are_combined(self):
        report = self.report("def f(a): pass\ndef g(b): pass", "Use "+quoted("f(old)")+" and "+quoted("g(old)")+".")
        replacements = [p for p in report["proposed_patches"] if p["action"] == "replace-line"]
        self.assertEqual(len(replacements), 1)
        self.assertEqual(replacements[0]["new"], "Use "+quoted("f(a)")+" and "+quoted("g(b)")+".")

    def test_repeated_reference_spans_are_replaced_once_each(self):
        report = self.report(docs=quoted("f(b)")+" and "+quoted("f(b)"))
        self.assertEqual(report["proposed_patches"][0]["new"], quoted("f(a)")+" and "+quoted("f(a)"))

    def test_trailing_spaces_preserved(self):
        report = self.report(docs=quoted("f(b)")+"  ")
        self.assertTrue(report["proposed_patches"][0]["new"].endswith("  "))

    def test_source_and_line_preconditions_present(self):
        patch = self.report()["proposed_patches"][0]
        self.assertTrue(patch["expected_doc_digest"].startswith("sha256:"))
        self.assertTrue(patch["expected_line_digest"].startswith("sha256:"))

    def test_patch_digest_binds_location(self):
        first = self.report()["proposed_patches"][0]
        second = sync_report({"a.py": "def f(a):\n    pass\n"}, {"other.md": quoted("f(b)")})["proposed_patches"][0]
        self.assertNotEqual(first["patch_digest"], second["patch_digest"])

    def test_tampered_finding_rejected(self):
        findings = self.report()["findings"]
        findings[0]["code"]["signature"] = "f(forged)"
        with self.assertRaises(ValueError):
            propose_patches(findings)

    def test_forged_line_precondition_rejected_even_if_resealed(self):
        findings = self.report()["findings"]
        findings[0]["doc"]["provenance"]["line_text"] = "different"
        findings[0].pop("finding_digest")
        findings[0]["finding_digest"] = _model_digest(findings[0])
        with self.assertRaises(ValueError):
            propose_patches(findings)

    def test_same_line_conflicting_snapshot_rejected(self):
        a = self.report()["findings"][0]
        b = copy.deepcopy(a)
        b["doc"]["provenance"]["source_digest"] = "sha256:"+"0"*64
        b.pop("finding_digest")
        b["finding_digest"] = _model_digest(b)
        with self.assertRaises(ValueError):
            propose_patches([a, b])

    def test_patch_grounding_is_detached(self):
        findings = self.report()["findings"]
        patches = propose_patches(findings)
        findings[0]["code"]["provenance"]["path"] = "changed"
        self.assertEqual(patches[0]["grounded_in"][0]["path"], "a.py")

    def test_backtick_default_requires_manual_review(self):
        report = self.report("def f(x='"+chr(96)+"'): pass", quoted("f(x)"))
        self.assertEqual(report["proposed_patches"][0]["action"], "flag-manual-review")
        self.assertIsNone(report["proposed_patches"][0]["new"])

    def test_input_types_rejected(self):
        for code in (None, [], {"a.py": 7}):
            with self.subTest(code=code), self.assertRaises(ValueError):
                sync_report(code, {})

    def test_file_size_limit(self):
        with patch("docsync.core.MAX_FILE_BYTES", 10), self.assertRaises(ValueError):
            self.report()

    def test_file_count_limit(self):
        with patch("docsync.core.MAX_FILES", 1), self.assertRaises(ValueError):
            self.report()

    def test_total_size_limit(self):
        with patch("docsync.core.MAX_TOTAL_BYTES", 20), self.assertRaises(ValueError):
            self.report()

    def test_malformed_interface_contract(self):
        with self.assertRaises(ValueError):
            detect_drift({"symbols": {"f": []}}, [])

    def test_malformed_reference_contract(self):
        with self.assertRaises(ValueError):
            detect_drift(extract_code_interface("def f(a): pass", "a.py"), [{"name": "f"}])

    def test_report_digest_covers_complete_report(self):
        report = self.report()
        digest = report.pop("report_digest")
        self.assertEqual(_model_digest(report), digest)
