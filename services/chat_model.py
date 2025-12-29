from langchain_huggingface import HuggingFaceEndpoint, ChatHuggingFace
from langchain_groq import ChatGroq
from core.config import GROQ_API_KEY
from dotenv import load_dotenv
load_dotenv()

# =================== Chat MODEL ===================

class ChatModelCreator:
    def __init__(
        self, 
        model_name: str, 
        model_task: str,
        temperature: float = 0,
        max_new_tokens: int = 1024,
        streaming: bool = True,
        # condition: str = "groq"
    ):

        # use the endpoint you already configured
        self.model_gen = HuggingFaceEndpoint(
            repo_id=model_name,
            task=model_task,
            temperature=temperature,
            max_new_tokens=max_new_tokens,
            streaming=streaming,              # 🔥 THIS IS CRITICAL FOR STREAMING
            return_full_text=False,      # ✅ avoids duplicated output
        )
        self.generator_llm = ChatHuggingFace(
            llm=self.model_gen,
            streaming=streaming,
        )

        self.groq_generator_llm = ChatGroq(
            model=model_name,
            temperature=temperature,
            max_tokens=max_new_tokens,        # ← Groq uses max_tokens
            streaming=streaming,
            groq_api_key=GROQ_API_KEY,  # Set this in .env
        )