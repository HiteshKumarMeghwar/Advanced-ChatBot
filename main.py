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


from contextlib import AsyncExitStack
from services.mcp_bootstrap import bootstrap_mcp_servers
from langgraph.checkpoint.redis import AsyncRedisSaver
from graphs.meghx_graph import build_graph
from core.database import init_db
from db.database import AsyncSessionLocal
from contextlib import asynccontextmanager
from loguru import logger

from services.limiting import limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi import _rate_limit_exceeded_handler


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
                "redis://localhost:6380/0",
                ttl={"default_ttl": 60*60*24}
            )
            # enter the context-manager once, keep the real saver
            redis_saver = await stack.enter_async_context(redis_cm)
            logger.info("Redis check-pointer active")
        except Exception as exc:
            # print the FULL exception instead of the generic message
            logger.exception("Redis unavailable - running stateless: %s", exc)
            redis_saver = None

        # build the graph **with** the saver (or None)
        async with AsyncSessionLocal() as session:
            raw_graph = await build_graph(session, checkpointer=redis_saver)
            app.state.chatbot = raw_graph.compile(checkpointer=redis_saver)
            logger.info("Chatbot graph READY")

        yield     # <- FastAPI is now serving requests

    # On shutdown
    if hasattr(app.state, "chatbot"):
        app.state.chatbot = None
        logger.info("Chatbot graph released.")


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