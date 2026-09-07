import os
from pathlib import Path

course_dir = Path(r"C:\Users\пп\Desktop\вика курсы")
stats = {}
total_files = 0
total_size = 0

for f in course_dir.rglob("*"):
    if f.is_file():
        ext = f.suffix.lower()
        size = f.stat().st_size
        total_files += 1
        total_size += size
        if ext not in stats:
            stats[ext] = {"count": 0, "size": 0}
        stats[ext]["count"] += 1
        stats[ext]["size"] += size

print("=" * 45)
print(f"{'EXTENSION':12} | {'COUNT':8} | {'SIZE (MB)':12}")
print("=" * 45)
for ext, data in sorted(stats.items(), key=lambda x: -x[1]["size"]):
    print(f"{ext:12} | {data['count']:8d} | {data['size'] / (1024 * 1024):12.2f}")
print("=" * 45)
print(f"Total files: {total_files}, Total size: {total_size / (1024 * 1024 * 1024):.2f} GB")
