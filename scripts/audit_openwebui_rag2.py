import subprocess

code = """
import sqlite3
conn = sqlite3.connect('/app/backend/data/webui.db')
c = conn.cursor()
c.execute("SELECT * FROM config WHERE key LIKE '%rag%' OR key LIKE '%embed%' OR key LIKE '%vector%' OR key LIKE '%chunk%'")
for r in c.fetchall():
    print(r[0], "-->", r[1])
"""

res = subprocess.run(["docker", "exec", "-i", "open-webui", "python"], input=code, capture_output=True, text=True, encoding="utf-8")
print(res.stdout)
if res.stderr:
    print("ERR:", res.stderr)
