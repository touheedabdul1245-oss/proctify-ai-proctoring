import ast
import importlib
import inspect
import json
import pathlib
import sys

ROOT = pathlib.Path(r"D:\dev\proctify_stage3")
MODULES = [
    "backend.proctoring.constants",
    "backend.proctoring.events",
    "backend.proctoring.observation",
    "backend.proctoring.temporal",
    "backend.proctoring.incidents",
    "backend.proctoring.risk",
    "backend.proctoring.evidence",
]

out = {}
for modname in MODULES:
    try:
        mod = importlib.import_module(modname)
    except Exception as exc:
        out[modname] = {"load": "FAIL", "error": repr(exc)}
        continue
    entry = {"load": "OK", "public": []}
    for name in dir(mod):
        if name.startswith("_"):
            continue
        obj = getattr(mod, name)
        kind = "fn"
        if inspect.isclass(obj):
            kind = "cls"
        elif not inspect.isfunction(obj):
            kind = type(obj).__name__
        entry["public"].append(name)
    entry["public"].sort()
    out[modname] = entry

for modname, entry in out.items():
    print("==", modname, entry.get("load"))
    if entry.get("load") == "FAIL":
        print("   ", entry.get("error"))
        continue
    for n in entry["public"]:
        print("   ", n)

print("--- events imports-from-constants ---")
path = ROOT / "backend" / "proctoring" / "events.py"
tree = ast.parse(path.read_text(encoding="utf-8"))
for node in tree.body:
    if isinstance(node, ast.ImportFrom) and node.module and "constants" in node.module:
        print("   ", [a.name for a in node.names])
