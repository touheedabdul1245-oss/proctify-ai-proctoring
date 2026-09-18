"""Generate backend/schemas_stage4.py directly from the monitor router AST.

The router is the single source of truth for the wire contract: every
`Proctoring*Out(...)`/schema construction inside proctoring_monitor_routes.py
tells us the exact field names AND their runtime value types. Deriving the
pydantic classes from that AST guarantees the schemas can never drift from
what the router emits (the failure mode that just cost us two bad writes).

Strategy (fully mechanical, no hand-typed field lists):

  1. Parse backend/routes/proctoring_monitor_routes.py.
  2. Find every Call whose .func.id is a schema name we must export
     (router's `from ..schemas_stage4 import (...)` set).
  3. For each construction, collect keyword arg name -> the AST expression.
  4. Infer a pydantic-expressible type from that expression:
        - ast.Call to int(...)                -> int
        - ast.Call to float(...) or the .upper() on str -> float/str
        - ast.Call to str(...) / .replace(..) -> str
        - ast.Call to bool(...)               -> bool
        - ListComp / sorted(...)              -> List[<inner model or Any>]
        - ast.Name/Attribute/None/Num/Str/Constant -> try literal inference
        - conditional (IfExp) / dict comp     -> Any (kept permissive)
    5. Nested model fields (e.g. List[ProctoringMonitorIncidentCard]) are
       resolved to the SAME names the router imports, so no cross-file drift.
    6. Emit BaseModel classes (pydantic v2, from_attributes off — these are
       wire contracts) with the inferred annotations into schemas_stage4.py.

The output file is then import-smoked by the caller immediately after.
"""
import ast
import re
from typing import List

ROUTER = r"backend/routes/proctoring_monitor_routes.py"
OUT = r"backend/schemas_stage4.py"

# names that must end up exported from OUT (verbatim router import set)
IMPORTS_SCOPE = None  # resolved below from the router's import block


def _import_scope(src: str) -> List[str]:
    m = re.search(
        r"from \.\.schemas_stage4 import \((.*?)\)\n", src, re.S
    )
    if not m:
        raise SystemExit("router import block not found")
    return [x.strip() for x in m.group(1).split(",") if x.strip()]


def _infer(node, model_names) -> str:
    """Map an AST value expression to a pydantic annotation string."""
    if isinstance(node, ast.IfExp):
        # ~ each branch; if both look like a list -> List[Any]
        a, b = _infer(node.body, model_names), _infer(node.orelse, model_names)
        if a.startswith("List[") and b.startswith("List["):
            return "List[Any]"
        return "Any"
    if isinstance(node, ast.Call):
        fn = node.func
        name = fn.id if isinstance(fn, ast.Name) else ""
        if name == "int":
            return "int"
        if name == "float":
            return "float"
        if name == "str":
            return "str"
        if name == "bool":
            return "bool"
        if name in ("sorted", "list"):
            if node.args:
                inner = _infer(node.args[0], model_names)
                if inner.startswith("List["):
                    return inner
            return "List[Any]"
        if name in ("_split",):  # returns Optional[List[str]]
            return "Optional[List[str]]"
        if isinstance(fn, ast.Attribute) and fn.attr in (
            "isoformat",
            "replace",
            "lower",
            "upper",
            "strip",
        ):
            base = _infer(fn.value, model_names)
            if base in ("str", "Any"):
                return "str"
            if fn.attr in ("isoformat",):
                return "str"
        if name in ("_to_float",):
            return "float"
        # fallback: maybe not a known helper
        return "Any"
    if isinstance(node, (ast.ListComp, ast.GeneratorExp)):
        # inner model named like Proctoring* -> that model; else Any
        if node.elt and isinstance(node.elt, ast.Name):
            if node.elt.id in model_names:
                return f"List[{node.elt.id}]"
            return "List[Any]"
        if node.elt and isinstance(node.elt, ast.Call):
            return f"List[Any]"
        return "List[Any]"
    if isinstance(node, (ast.List, ast.Tuple)):
        return "List[Any]"
    if isinstance(node, ast.Dict):
        return "Dict[str, Any]"
    if isinstance(node, ast.Constant):
        if node.value is None:
            return "Optional[Any]"
        if isinstance(node.value, bool):
            return "bool"
        if isinstance(node.value, (int, float)):
            return (
                "float" if isinstance(node.value, float) else "int"
            )
        if isinstance(node.value, str):
            return "str"
        return "Any"
    if isinstance(node, ast.Name):
        if node.id in model_names:
            return node.id
        if node.id in ("True", "False"):
            return "bool"
        if node.id in ("None",):
            return "Optional[Any]"
        # variable holding a model / list / date; be permissive
        return "Any"
    if isinstance(node, ast.Attribute) and node.attr in (
        "id",
        "level",
        "status",
        "session_token",
    ):
        return "Any"
    return "Any"


def _field_types(call, model_names) -> List[tuple]:
    """Return list of (field_name, annotation) for one construction."""
    out = []
    for kw in call.keywords or []:
        if kw.arg is None:
            continue
        ann = _infer(kw.value, model_names)
        out.append((kw.arg, ann))
    return out


def main() -> None:
    src = open(ROUTER, encoding="utf-8").read()
    model_names = _import_scope(src)
    tree = ast.parse(src)

    constructions = []  # (class_name, [(field, type), ...])
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Name):
            continue
        if node.func.id not in model_names:
            continue
        fields = _field_types(node, model_names)
        constructions.append((node.func.id, fields))

    # group by class name, keeping the field order of the first occurrence
    merged = {}
    order = []
    for name, fields in constructions:
        if name not in merged:
            merged[name] = {}
            order.append(name)
        for f, t in fields:
            merged[name][f] = t

    lines = [
        '"""Stage-4 teacher monitoring wire contracts.',
        "",
        "GENERATED from backend/routes/proctoring_monitor_routes.py so the ",
        "response surface can never drift from what the monitor router emits.",
        "Regenerate with:  python tools/gen_schemas_stage4.py",
        '"""',
        "from datetime import datetime",
        "from typing import Any, Dict, List, Optional",
        "",
        "from pydantic import BaseModel, ConfigDict",
        "",
    ]
    for name in order:
        lines.append(f"class {name}(BaseModel):")
        lines.append('    model_config = ConfigDict(extra="allow")')
        fields = merged[name]
        if not fields:
            lines.append("    pass")
        else:
            for f, t in fields.items():
                lines.append(f"    {f}: {t}")
        lines.append("")
        lines.append("")

    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))

    print("WROTE", OUT)
    print("classes:", order)
    for name in order:
        print("  ", name, "->", sorted(merged[name].keys()))


if __name__ == "__main__":
    main()
