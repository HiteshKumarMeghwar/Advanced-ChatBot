# worker/tasks/embedding_service.py
from langchain_huggingface import HuggingFaceEmbeddings

class EmbeddingService:
    def __init__(self):
        self.model = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")

    def embed(self, chunks):
        return self.model.embed_documents(chunks)
