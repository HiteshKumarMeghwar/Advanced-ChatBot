# embeddings.py
from typing import List
from langchain_huggingface import HuggingFaceEndpointEmbeddings
from dotenv import load_dotenv
load_dotenv()


class EmbeddingsCreator:

    def __init__(self, model_name: str):
        # use the endpoint you already configured
        self.model = HuggingFaceEndpointEmbeddings(model=model_name)

    def create_embedding(self, text: str) -> List[float]:
        # lang-chain returns List[float] already
        return self.model.embed_query(text)
