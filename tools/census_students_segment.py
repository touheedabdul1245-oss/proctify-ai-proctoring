import sys
sys.path.insert(0, ".")

src = open(r"backend\routes\proctoring_monitor_routes.py", encoding="utf-8").read()

print("FULL ROUTER %d bytes" % len(src))
print("STUDENTS-SEGMENT ====================")
i = src.find('"/students"')
if i < 0:
    i = src.find("students")
low = max(0, src.rfind("\ndef ", 0, i))
print(src[low : i + 2600])
