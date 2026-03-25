import os
from better_code_review_graph.embeddings import init_backend
backend = init_backend()
print(f"Backend name: {backend.name}")
print(f"API key explicitly used: {'YES' if os.environ.get('COHERE_API_KEY') else 'NO'}")
