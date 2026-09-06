import subprocess

code = """
import sqlite3
import json
conn = sqlite3.connect('/app/backend/data/webui.db')
c = conn.cursor()
c.execute("PRAGMA table_info(config)")
print("Config cols:", [r[1] for r in c.fetchall()])
c.execute("SELECT * FROM config")
for row in c.fetchall():
    print("Row:", row)

import chromadb
client = chromadb.PersistentClient(path="/app/backend/data/vector_db")
cols = client.list_collections()
print("Chroma collections:", [col.name for col in cols])
for col in cols:
    print("Collection:", col.name, "count:", col.count())
"""

res = subprocess.run(["docker", "exec", "-i", "open-webui", "python"], input=code, capture_output=True, text=True, encoding="utf-8")
print(res.stdout)
if res.stderr:
    print("ERR:", res.stderr)
