"""
LangChain AI Stack - FastAPI Entry Point

职责：
- FastAPI app 创建 + CORS
- 路由注册（REST + WebSocket）
- 健康检查

所有业务逻辑已拆分到 src/core/ 和 src/routes/
"""

import sys
import logging
from pathlib import Path

# 添加项目根目录到 sys.path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ── FastAPI app ─────────────────────────────────────────────────────────────

app = FastAPI(
    title="LangChain AI Stack",
    description="AI 面试助手 - 单例 Agent + 分层会话 + 流式事件驱动",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8080", "null", "http://localhost:5000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routes ──────────────────────────────────────────────────────────────────

from src.routes.rest import router as api_router
from src.routes.agui import router as agui_router

app.include_router(api_router)

app.include_router(agui_router, tags=["AG-UI"])

# 注意：原有的 /ws/chat 端点已被 AG-UI 协议替换
# 请使用 /agui 端点


# ── Init agent on startup ─────────────────────────────────────────────────────

@app.on_event("startup")
async def startup_event():
    from src.routes.rest import init_config_file
    from src.core.session_manager import get_agent_singleton
    init_config_file()
    agent = get_agent_singleton()
    logger.info(f"[Startup] Agent initialized, model: {agent.agent}")


@app.get("/")
async def root():
    return {"message": "LangChain AI Stack is running", "docs": "/docs"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)