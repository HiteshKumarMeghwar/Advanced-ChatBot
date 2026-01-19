from dotenv import load_dotenv
load_dotenv()
import asyncio
import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from api.routes.auth import router as auth_router
from api.routes.threads import router as threads_router
from api.routes.messages import router as messages_router
from api.routes.documents import router as documents_router
from api.routes.vector import router as vector_router
from api.routes.tools import router as tools_router
from api.routes.chat import router as chat_router
from api.routes.user_profile import router as user_router
from api.routes.notification_status import router as notification_status_router
from api.routes.user_tool_status import router as user_tool_status
from api.routes.user_theme_change import router as user_theme_change
from api.routes.user_tools_view import router as user_tools_view
from api.routes.expense_categories import router as expense_categories_router
from api.routes.mcp import router as mcp_router
from api.routes.voice import router as voice_router
from api.routes.vision import router as image_router
from api.routes.user_memory_settings import router as user_memory_settings
from api.routes.feedback import router as feedback_router
from api.routes.acounts_integration import router as acounts_integration_router
from api.routes.expense import router as expense_router


from contextlib import AsyncExitStack
from core.config import ASYNC_REDIS_CHECKPOINTER_URL, CHAT_MODEL_HF_LLAMA_8B, CHAT_MODEL_LARGEST_GPTOSS_20B, CHAT_MODEL_LARGEST_LLAMA_70B, CHAT_MODEL_SMALLEST_8B, CHAT_MODEL_TEXT, DEFAULT_CHECKPOINTER_TTL, VISSION_CHAT_MODEL_METALLAMA_17B
from services.chat_model import ChatModelCreator
from services.mcp_bootstrap import bootstrap_mcp_servers
from services.memory_maintenance import start_background_maintenance
from langgraph.checkpoint.redis import AsyncRedisSaver
from graphs.meghx_graph import build_graph
from tools.gather_tools import gather_tools
from core.database import init_db
from db.database import AsyncSessionLocal
from contextlib import asynccontextmanager
from fastapi.staticfiles import StaticFiles
from prometheus_client import make_asgi_app
from loguru import logger

from services.limiting import limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi import _rate_limit_exceeded_handler
from tools.tool_registry import ToolRegistry


logger.add("logs.json", serialize=True)


# -------------------------------
# INIT DB (async engine + tables)
# -------------------------------
# ⚠️ must be awaited INSIDE lifespan — not at module level
# init_async_db() is async now!
# -------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):

    # Bootstrap MCP servers (ONE TIME, safe)
    bootstrap_mcp_servers()

    # Initialize tables (Alembic recommended but this works)
    await init_db()

    async with AsyncExitStack() as stack:   # guarantees __aexit__ is called
        try:
            redis_cm = AsyncRedisSaver.from_conn_string(
                ASYNC_REDIS_CHECKPOINTER_URL,
                ttl={"default_ttl": DEFAULT_CHECKPOINTER_TTL}
            )
            # enter the context-manager once, keep the real saver
            redis_saver = await stack.enter_async_context(redis_cm)
            logger.info("Redis check-pointer active")
        except Exception as exc:
            # print the FULL exception instead of the generic message
            logger.exception("Redis unavailable - running stateless: %s", exc)
            redis_saver = None

        try:
            # build the graph **with** the saver (or None)
            async with AsyncSessionLocal() as session:
                raw_graph = await build_graph(session, checkpointer=redis_saver)
                app.state.chatbot = raw_graph.compile(checkpointer=redis_saver)
                logger.info("Chatbot graph READY")
        except Exception as exc:
            logger.exception("Chatbot graph compiling issue -: %s", exc)

        try:
            await start_background_maintenance(app)
            logger.info("Background - Memory Maintenance Start.")
        except Exception as exc:
            logger.exception("Background Memory Maintenance issue -: %s", exc)

        try:
            app.state.llms = {
                # ---------------- CHAT (FAST, STREAMING) ----------------
                "chat_base": ChatModelCreator(
                    model_name=CHAT_MODEL_LARGEST_GPTOSS_20B,
                    model_task=CHAT_MODEL_TEXT,
                    temperature=0.6,          # 👈 conversational
                    max_new_tokens=1024,
                    streaming=True,           # 👈 REQUIRED for UX
                ).groq_generator_llm,

                # ---------------- SYSTEM / EXTRACTION (STRONG, STABLE) ----------------
                "system": ChatModelCreator(
                    model_name=CHAT_MODEL_LARGEST_LLAMA_70B,
                    model_task=CHAT_MODEL_TEXT,
                    temperature=0.0,          # 👈 deterministic
                    max_new_tokens=512,
                    streaming=False,          # 👈 DO NOT STREAM extraction
                ).groq_generator_llm,

                # ---------------- CHAT (POST PROCESSING, STREAMING) ----------------
                "chat_post": ChatModelCreator(
                    model_name=CHAT_MODEL_HF_LLAMA_8B,
                    model_task=CHAT_MODEL_TEXT,
                    temperature=0.6,          # 👈 conversational
                    max_new_tokens=1024,
                    streaming=True,           # 👈 REQUIRED for UX
                ).generator_llm,

                # ---------------- VISSION (TEXT+IMAGE, STREAMING) ----------------
                "vision": ChatModelCreator(
                    model_name=VISSION_CHAT_MODEL_METALLAMA_17B,
                    model_task=CHAT_MODEL_TEXT,
                    temperature=0.3,        
                    max_new_tokens=1024,
                    streaming=True,         
                ).groq_generator_llm,
            }

            logger.info("LLMs Started successfully (chat=7B, vission=17b, system=70B).")

        except Exception as exc:
            logger.exception("LLM Initialization issue -: %s", exc)

        try:
            app.state.tool_registry = ToolRegistry()
            all_tools = await gather_tools()
            await app.state.tool_registry.refresh(all_tools)
            logger.info("Tool registry initialized (version=%s)",
                getattr(app.state.tool_registry, "version", "unknown"))
        except Exception as exc:
            logger.exception("Tools Initiating issue -: %s", exc)


        yield     # <- FastAPI is now serving requests


    # On shutdown
    if hasattr(app.state, "chatbot"):
        app.state.chatbot = None
        logger.info("Chatbot graph released.")
    
    if redis_saver:
        redis_saver = None
        logger.info("Redis check-pointer inactive.")

    if hasattr(app.state, "llms"):
        app.state.llms = None
        logger.info("LLMs released.")

    if hasattr(app.state, "llms"):
        app.state.tool_registry = None
        logger.info("Tool registry released.")
    
    if hasattr(app.state, "memory_maintenance_task"):
        app.state.memory_maintenance_shutdown = True
        app.state.memory_maintenance_task.cancel()
        logger.info("Background - Memory Maintenance shutdown.")
        try:
            await app.state.memory_maintenance_task
        except asyncio.CancelledError:
            pass


# FastAPI app
app = FastAPI(
    title="Advanced Chatbot With Multi Functionality API (Async)",
    lifespan=lifespan,
)


# ---------- SlowAPI -------------
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ---------- CORS ----------
# 1. Replace with the real origin(s) of your front-end
origins = [
    "http://localhost:3000",        # Next.js dev server
    # "https://meghbot.ddns.net",     # production server
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,          # ✅ explicit list (safer than ["*"])
    allow_credentials=True,         # if you send cookies / auth headers
    allow_methods=["*"],
    allow_headers=["*"],            # or list the ones you need
)

@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request, exc):
    return JSONResponse(
        status_code=429,
        content={"detail": "Too many requests — slow down"}
    )


# ROUTES -----------------------
@app.get("/health")
async def health():
    return {"status": "ok"}


app.mount(
    "/media_ocr/images",
    StaticFiles(directory="images_ocr"),
    name="images",
)

app.mount("/metrics", make_asgi_app())

app.include_router(auth_router)
app.include_router(threads_router)
app.include_router(messages_router)
app.include_router(documents_router)
app.include_router(vector_router)
app.include_router(tools_router)
app.include_router(chat_router)
app.include_router(user_router)
app.include_router(notification_status_router)
app.include_router(user_tool_status)
app.include_router(user_theme_change)
app.include_router(user_tools_view)
app.include_router(expense_categories_router)
app.include_router(mcp_router)
app.include_router(voice_router)
app.include_router(image_router)
app.include_router(user_memory_settings)
app.include_router(feedback_router)
app.include_router(acounts_integration_router)
app.include_router(expense_router)



@app.get("/")
async def root():
    return {"status": "running", "engine": "Async RAG backend initialized"}


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="debug"
    )