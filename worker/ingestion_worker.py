# worker/ingestion_worker.py
from worker.base_worker import BaseWorker
from worker.tasks.document_ingestion import DocumentIngestionService

class IngestionWorker(BaseWorker):
    def run(self, document_id: int):
        self.log(f"Processing document {document_id}")

        processor = DocumentIngestionService(document_id)
        processor.process()

        self.log(f"Completed document {document_id}")


# RQ ENTRYPOINT
def ingest_document(document_id: int):
    worker = IngestionWorker()
    worker.run(document_id)
