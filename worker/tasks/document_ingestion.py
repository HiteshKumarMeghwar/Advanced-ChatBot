# worker/tasks/document_ingestion.py
from worker.tasks.chunking_service import ChunkingService
from worker.tasks.embedding_service import EmbeddingService
from worker.tasks.storage_service import StorageService

class DocumentIngestionService:
    def __init__(self, document_id: int):
        self.document_id = document_id

        self.chunker = ChunkingService()
        self.embedder = EmbeddingService()
        self.storage = StorageService()

    def process(self):
        # Load file from database storage
        file_path = self.storage.load_file(self.document_id)

        # Convert to text & chunk
        chunks = self.chunker.chunk(file_path)

        # Embed chunks
        embeddings = self.embedder.embed(chunks)

        # Store embeddings to FAISS + MySQL
        self.storage.save_chunks(self.document_id, chunks)
        self.storage.save_embeddings(self.document_id, embeddings)
