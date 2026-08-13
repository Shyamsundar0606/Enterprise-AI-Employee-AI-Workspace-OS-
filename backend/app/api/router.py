from fastapi import APIRouter

from app.api.routes.auth import router as auth_router
from app.api.routes.chat import router as chat_router
from app.api.routes.health import router as health_router
from app.api.routes.llm import router as llm_router
from app.api.routes.memory import router as memory_router
from app.api.v1.agents import router as agents_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["health"])
api_router.include_router(auth_router)
api_router.include_router(chat_router)
api_router.include_router(llm_router)
api_router.include_router(memory_router)
api_router.include_router(agents_router)
