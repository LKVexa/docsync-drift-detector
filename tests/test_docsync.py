import unittest

from docsync.core import (detect_drift, extract_code_interface,
                          extract_doc_references, propose_patches, sync_report)

CODE = '''\
def connect(host, port, timeout=5):
    pass

def fetch(url):
    pass

class Client:
    def close(self):
        pass

def _private():
    pass
'''

DOCS = """\
# API

Use `connect(host, port)` to open a session.
Then call `fetch(url)` for data.
Legacy users may call `disconnect()` (removed in 2.0).
"""


class Extraction(unittest.TestCase):
    def test_code_symbols_with_provenance(self):
        iface = extract_code_interface(CODE, "lib.py")
        self.assertEqual(iface["symbols"]["connect"]["signature"],
                         "connect(host, port, timeout=5)")
        self.assertEqual(iface["symbols"]["Client.close"]["signature"],
                         "Client.close(self)")
        self.assertNotIn("_private", iface["symbols"])
        self.assertEqual(iface["symbols"]["fetch"]["provenance"]["line"], 4)

    def test_syntax_error_reported_not_guessed(self):
        iface = extract_code_interface("def broken(:", "bad.py")
        self.assertEqual(iface["symbols"], {})
        self.assertTrue(iface["errors"])

    def test_doc_refs(self):
        refs = extract_doc_references(DOCS, "api.md")
        names = [r["name"] for r in refs]
        self.assertEqual(names, ["connect", "fetch", "disconnect"])
        self.assertEqual(refs[0]["documented_signature"], "connect(host, port)")
        self.assertEqual(refs[0]["provenance"]["line"], 3)


class Drift(unittest.TestCase):
    def setUp(self):
        self.findings = detect_drift(extract_code_interface(CODE, "lib.py"),
                                     extract_doc_references(DOCS, "api.md"))
        self.by_kind = {}
        for f in self.findings:
            self.by_kind.setdefault(f["kind"], []).append(f)

    def test_all_three_drift_kinds(self):
        self.assertEqual([f["symbol"] for f in self.by_kind["signature-mismatch"]],
                         ["connect"])
        self.assertEqual([f["symbol"] for f in self.by_kind["documented-symbol-missing"]],
                         ["disconnect"])
        self.assertIn("Client",
                      [f["symbol"] for f in self.by_kind["undocumented-symbol"]])

    def test_fetch_matches_no_finding(self):
        self.assertNotIn("fetch", [f["symbol"] for f in self.findings])

    def test_severity_ordering(self):
        sevs = [f["severity"] for f in self.findings]
        order = {"high": 0, "medium": 1, "low": 2}
        self.assertEqual(sevs, sorted(sevs, key=order.get))


class Patches(unittest.TestCase):
    def setUp(self):
        self.report = sync_report({"lib.py": CODE}, {"api.md": DOCS})
        self.patches = {p["action"]: p for p in self.report["proposed_patches"]
                        if p["action"] != "suggest-addition"}
        self.additions = [p for p in self.report["proposed_patches"]
                          if p["action"] == "suggest-addition"]

    def test_minimal_replacement_grounded_in_code(self):
        p = self.patches["replace-line"]
        self.assertIn("`connect(host, port)`", p["old"])
        self.assertIn("`connect(host, port, timeout=5)`", p["new"])
        self.assertEqual(p["new"].replace("`connect(host, port, timeout=5)`",
                                          "`connect(host, port)`"), p["old"])
        self.assertEqual(p["grounded_in"][0]["path"], "lib.py")
        self.assertEqual(p["grounded_in"][0]["line"], 1)
        self.assertTrue(p["grounded_in"][0]["source_digest"].startswith("sha256:"))

    def test_removal_needs_human_confirmation(self):
        p = self.patches["flag-for-removal"]
        self.assertIsNone(p["new"])
        self.assertIn("human", p["rationale"])

    def test_addition_defers_prose_to_humans(self):
        self.assertTrue(any("human authoring task" in p["new"]
                            for p in self.additions))

    def test_draft_only_and_closure_semantics(self):
        self.assertTrue(self.report["draft_only"])
        self.assertFalse(self.report["write_access"])
        for p in self.report["proposed_patches"]:
            self.assertTrue(p["draft"])
            self.assertEqual(p["closure_state"], "TRACE")
        import docsync.core as m
        for name in dir(m):
            for bad in ("write_file", "apply", "save_doc", "commit"):
                self.assertNotIn(bad, name.lower())

    def test_deterministic(self):
        again = sync_report({"lib.py": CODE}, {"api.md": DOCS})
        self.assertEqual(self.report, again)


if __name__ == "__main__":
    unittest.main()


class TestUpgrade011(unittest.TestCase):
    """Regression tests for JY-S010-P001 0.1.1-partial fixes (A011)."""

    def test_async_method_extracted(self):
        # A011-F1 positive: async methods in classes are public interface
        code = "class C:\n    async def arun(self, x):\n        return x\n"
        iface = extract_code_interface(code, "m.py")
        self.assertIn("C.arun", iface["symbols"])
        self.assertEqual(iface["symbols"]["C.arun"]["signature"],
                         "C.arun(self, x)")

    def test_async_method_no_false_missing_finding(self):
        # A011-F1 negative: a correct doc ref must not be flagged missing
        code = "class C:\n    async def arun(self, x):\n        return x\n"
        iface = extract_code_interface(code, "m.py")
        refs = extract_doc_references("`C.arun(self, x)`", "d.md")
        kinds = [f["kind"] for f in detect_drift(iface, refs)
                 if f["symbol"] == "C.arun"]
        self.assertNotIn("documented-symbol-missing", kinds)

    def test_private_async_method_still_excluded(self):
        code = "class C:\n    async def _hidden(self):\n        pass\n"
        iface = extract_code_interface(code, "m.py")
        self.assertNotIn("C._hidden", iface["symbols"])

    def test_findings_isolated_from_inputs(self):
        # A011-F2: mutating a returned finding must not corrupt inputs
        iface = extract_code_interface("def f(a):\n    pass\n", "m.py")
        refs = extract_doc_references("`f(b)`", "d.md")
        findings = detect_drift(iface, refs)
        findings[0]["code"]["signature"] = "TAMPERED"
        findings[0]["doc"]["name"] = "TAMPERED"
        self.assertEqual(iface["symbols"]["f"]["signature"], "f(a)")
        self.assertEqual(refs[0]["name"], "f")

    def test_findings_isolated_from_each_other(self):
        # A011-F2: two findings on the same symbol share no mutable state
        iface = extract_code_interface("def f(a):\n    pass\n", "m.py")
        refs = extract_doc_references("`f(b)` and `f(c)`", "d.md")
        findings = [f for f in detect_drift(iface, refs)
                    if f["kind"] == "signature-mismatch"]
        self.assertEqual(len(findings), 2)
        findings[0]["code"]["signature"] = "TAMPERED"
        self.assertEqual(findings[1]["code"]["signature"], "f(a)")
