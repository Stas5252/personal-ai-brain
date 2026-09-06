import subprocess

code = """
import sqlite3
conn = sqlite3.connect('/app/backend/data/webui.db')
c = conn.cursor()
c.execute("SELECT name FROM sqlite_master WHERE type='table'")
print("Tables:", [r[0] for r in c.fetchall()])
for t in ["document", "memory", "file", "knowledge"]:
    try:
        c.execute(f"PRAGMA table_info({t})")
        cols = [r[1] for r in c.fetchall()]
        print(f"{t} cols:", cols)
    except Exception as e:
        print(t, e)
"""

res = subprocess.run(["docker", "exec", "-i", "open-webui", "python"], input=code, capture_output=True, text=True, encoding="utf-8")
print(res.stdout)
if res.stderr:
    print("ERR:", res.stderr)
