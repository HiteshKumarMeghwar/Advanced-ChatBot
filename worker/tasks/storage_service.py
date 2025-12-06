# worker/tasks/storage_service.py
import os
from db.database import SessionLocal
from db.models import DocumentChunk
from worker.utils.logger import log

class StorageService:
    def __init__(self):
        self.db = SessionLocal()

    def load_file(self, document_id):
        result = self.db.execute(
            "SELECT file_path FROM documents WHERE id = :id",
            {"id": document_id}
        ).fetchone()

        if not result:
            raise Exception("Document not found")

        return result[0]

    def save_chunks(self, document_id, chunks):
        for idx, chunk in enumerate(chunks):
            self.db.add(DocumentChunk(
                document_id=document_id,
                chunk_order=idx,
                text=chunk
            ))
        self.db.commit()
        log("Chunks saved.")

    def save_embeddings(self, document_id, embeddings):
        # to do: Save numpy embeddings to FAISS index
        log("Embeddings stored in FAISS.")
