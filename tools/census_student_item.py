import sys

sys.stdout.reconfigure(encoding="utf-8")

src = open(r"backend\routes\proctoring_monitor_routes.py", encoding="utf-8").read()

print("===LEN===", len(src))

# find def building student items — search for 'ProctoringStudentItemOut' line context
i = src.find("ProctoringStudentItemOut")
# print every token-window around it (400 chars)
print("===OCCURRENCES===")
start = 0
k = 0
while True:
    j = src.find("ProctoringStudentItemOut", start)
    if j < 0:
        break
    k += 1
    s = max(0, j - 260)
    print("### OCC", k, "@", j)
    print(src[s : j + 320])
    start = j + len("ProctoringStudentItemOut")
