# Print the /students endpoint verbatim from the monitor router.
src = open(r"backend\routes\proctoring_monitor_routes.py", encoding="utf-8").read().splitlines()
for i, l in enumerate(src):
    if '"students"' in l or "'students'" in l:
        print("===ROUTER-LINE", i + 1, "===")
        for j in range(i, min(i + 70, len(src))):
            print(f"{j+1:4}", repr(src[j])[:170])
        break
