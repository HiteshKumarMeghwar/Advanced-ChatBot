from core.config import CHAT_MODEL, CHAT_MODEL_TEXT
from tools.gather_tools import gather_tools
from services.chat_model import ChatModelCreator

async def binded_tools_with_llm():
    generator_llm = ChatModelCreator(model_name=CHAT_MODEL, model_task=CHAT_MODEL_TEXT).generator_llm
    tools = await gather_tools()
    return generator_llm.bind_tools(tools)

async def without_tool_llm():
    return ChatModelCreator(model_name=CHAT_MODEL, model_task=CHAT_MODEL_TEXT).generator_llm

async def groq_with_tools_llm():
    groq_generator_llm = ChatModelCreator(model_name=CHAT_MODEL, model_task=CHAT_MODEL_TEXT).groq_generator_llm
    tools = await gather_tools()
    return groq_generator_llm.bind_tools(tools)

async def groq_without_tool_llm():
    return ChatModelCreator(model_name=CHAT_MODEL, model_task=CHAT_MODEL_TEXT).groq_generator_llm