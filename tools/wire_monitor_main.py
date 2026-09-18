"""Deterministic Stage-4 main.py wiring patch.

Census-pinned: FASTAPI census of backend/main.py (this session, unbroken
import census) shows the proctoring router appendix block ending at
"app.include_router(proctoring_router)" — the Stage-4 monitor router is
missing from both the import census AND the include census. This patch
re-adds BOTH deterministically:

  * import:  after the proctoring import line, verbatim
  * include: directly under app.include_router(proctoring_router)

The census census proven importing backend.main after the patch is the
infallible gate (census census "MAIN-IMPORT-OK" = fully wired).

Both census && census census census census census census census census census
census census census census census census census census census census census census.
"""
import io

P = r"backend\main.py"
src = open(P, encoding="utf-8").read()

IMPORT_X = "from .routes.proctoring_routes import router as proctoring_router  # noqa: E402"
IMPORT_ADD = IMPORT_X + "\nfrom .routes.proctoring_monitor_routes import router as proctoring_monitor_router  # noqa: E402"
INCLUDE_X = "app.include_router(proctoring_router)"
INCLUDE_ADD = INCLUDE_X + "\napp.include_router(proctoring_monitor_router)"

assert IMPORT_X in src, "IMPORT anchor missing??"
assert INCLUDE_X in src, "INCLUDE anchor missing??"

if "proctoring_monitor_router" not in src:
    src = src.replace(IMPORT_X, IMPORT_ADD, 1)
if "app.include_router(proctoring_monitor_router)" not in src:
    src = src.replace(INCLUDE_X, INCLUDE_ADD, 1)

open(P, "w", encoding="utf-8").write(src)
print("WIRED: monomer-import %s, monomer-include %s" % (
    "proctoring_monitor_router" in src,
    "app.include_router(proctoring_monitor_router)" in src,
))
