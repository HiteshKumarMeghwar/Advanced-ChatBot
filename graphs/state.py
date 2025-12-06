from typing import TypedDict, List, Optional, Annotated
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage

class ChatState(TypedDict):
    thread_id: str
    user_query: str
    tool_call: Optional[str]
    messages: Annotated[list[BaseMessage], add_messages]
    assistant_reply: Optional[str]

    # JWT for internal calls
    jwt: str

    # Data returned by RAG tool
    tool_response: Optional[dict]

    # Optional extracted convenience fields
    context: Optional[List[str]]
    metadata: Optional[List[dict]]
    source_file: Optional[str]
