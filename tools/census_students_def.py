import re

src = open(r"backend\routes\proctoring_monitor_routes.py", encoding="utf-8").read()

# locate router decorators that mention 'students'
paths = [n for n in ("/students", "/sessions", "/overview", "/summary", "/review") if f'"{n}"' in src]
print("PATHS-FOUND:", paths)

m = re.search(r'@router\.(get|post)\("/students"[^)]*\)', src)
if not m:
    m = re.search(r'@router\.[a-z]+\("([^"]*students[^"]*)"\)', src)
print("STUDENTS-DECORATOR:", m.group(0) if m else None)

i = src.find("def monitor_students")
if i < 0:
    print("NO monitor_students def")
else:
    body = src[i : i + 1900]
    print(body)
