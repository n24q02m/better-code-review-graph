import os
os.environ["COHERE_API_KEY"] = "test"
from better_code_review_graph.embeddings import init_backend
backend = init_backend()
try:
    backend.embed_single("test")
except Exception as e:
    print(f"Exception: {e}")
