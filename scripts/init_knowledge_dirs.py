import os

dirs = [
    "src/brain/knowledge",
    "src/brain/knowledge/extractors",
    "src/brain/knowledge/chunkers",
    "src/brain/knowledge/classifiers",
    "src/brain/knowledge/embeddings",
    "src/brain/knowledge/indexing",
    "src/brain/knowledge/queue"
]

for d in dirs:
    os.makedirs(d, exist_ok=True)
    init_f = os.path.join(d, "__init__.py")
    if not os.path.exists(init_f):
        with open(init_f, "w", encoding="utf-8") as f:
            f.write('"""Package init."""\n')

print("All knowledge directories initialized!")
