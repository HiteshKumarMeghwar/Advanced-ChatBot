from langchain_huggingface import HuggingFaceEndpoint, ChatHuggingFace
from dotenv import load_dotenv
load_dotenv()

# =================== Chat MODEL ===================

class ChatModelCreator:
    def __init__(
        self, 
        model_name: str, 
        model_task: str,
        temperature: float = 0.7,
        max_new_tokens: int = 1024,
    ):

        # use the endpoint you already configured
        self.model_gen = HuggingFaceEndpoint(
            repo_id=model_name,
            task=model_task,
            temperature=temperature,
            max_new_tokens=max_new_tokens,
            streaming=True,              # 🔥 THIS IS CRITICAL FOR STREAMING
            return_full_text=False,      # ✅ avoids duplicated output
        )
        self.generator_llm = ChatHuggingFace(
            llm=self.model_gen,
            streaming=True,
        )