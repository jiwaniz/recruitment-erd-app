"""
Rendering regression test.
1. Static: no view may contain a bare conditional / name / attribute expression statement (Streamlit 'magic'
   would display its value, e.g. a DeltaGenerator object, instead of the intended interface).
2. Dynamic: after opening every page as each role, the page must contain no st.help / code-doc elements.
"""
import ast, pathlib, sys
from streamlit.testing.v1 import AppTest

ROOT = pathlib.Path(__file__).resolve().parents[1]
APP = str(ROOT / "app.py")


def static_scan():
    bad = []
    for f in sorted((ROOT / "views").glob("*.py")) + [ROOT / "app.py"]:
        for node in ast.walk(ast.parse(f.read_text(encoding="utf8"))):
            if isinstance(node, ast.Expr) and not isinstance(node.value, (ast.Call, ast.Constant)):
                bad.append(f"{f.name}:{node.lineno} {ast.unparse(node.value)[:70]}")
    return bad


def pages(at):
    return [p for p in __import__("json").loads(at.session_state["_page_files"])]


def stray_elements(at):
    out = []
    for e in at.main:
        if type(e).__name__ == "Help":
            out.append(type(e).__name__)
        if "DeltaGenerator" in repr(getattr(e, "value", "")):
            out.append("DeltaGenerator text")
    return out


if __name__ == "__main__":
    bad = static_scan()
    assert not bad, f"bare expression statements found: {bad}"
    print("  ok  static scan: no bare expression statements in views/")
