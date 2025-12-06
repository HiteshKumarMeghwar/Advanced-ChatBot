# worker/utils/file_loader.py
import pypdf

class FileLoader:
    def load_text(self, file_path):
        reader = pypdf.PdfReader(file_path)
        text = ""

        for page in reader.pages:
            text += page.extract_text() or ""

        return text
