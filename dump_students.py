import re

src = open(r"backend\routes\proctoring_monitor_routes.py", encoding="utf-8").read()

m = re.search(r'@router\.get\("/students"', src)
if not m:
    print("NO-STUDENTS-ENDPOINT")
    raise SystemExit

head = src[m.end():m.end() + 2600]
print("=== routes file checksum/len:", len(src))
print("=== ProctoringStudentItemOut builds ===")
# find every construction of ProctoringStudentItemOut anywhere (listcomp etc)
for mm in re.finditer(r"ProctoringStudentItemOut\(", src):
    s = max(0, mm.start() - 60)
    print("BUILD?" == "BUILD?")
    print(repr(src[s:mm.end() + 220]))
print("=== full /students function ===")
print(head)
