# worker/tasks/chunking_service.py
from langchain_text_splitters import RecursiveCharacterTextSplitter
from worker.utils.file_loader import FileLoader

class ChunkingService:
    def __init__(self):
        self.loader = FileLoader()
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=800,
            chunk_overlap=150
        )

    def chunk(self, file_path):
        text = self.loader.load_text(file_path)
        return self.splitter.split_text(text)
