# AG-UI Protocol API Routes
# Agent User Interaction Protocol Implementation
# 替换原有的 /ws/chat 端点

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Dict, Any
import json
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


class AGUIConnectionManager:
    """管理 AG-UI WebSocket 连接"""

    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, client_id: str):
        """接受 WebSocket 连接"""
        await websocket.accept()
        self.active_connections[client_id] = websocket

    def disconnect(self, client_id: str):
        """断开 WebSocket 连接"""
        if client_id in self.active_connections:
            del self.active_connections[client_id]

    async def send_to_client(self, client_id: str, message: Dict[str, Any]):
        """发送消息给指定客户端"""
        if client_id in self.active_connections:
            await self.active_connections[client_id].send_json(message)


# 全局连接管理器
manager = AGUIConnectionManager()


# 导入原有的聊天逻辑
def _get_timestamp(websocket) -> int:
    """Extract timestamp from websocket headers."""
    if websocket.extra_headers:
        return int(websocket.extra_headers.get("timestamp", 0))
    return 0


def _make_response_msg(result: dict, websocket, is_complete: bool = False, **kwargs) -> dict:
    """Build AG-UI response message from result dict."""
    ts = _get_timestamp(websocket)
    return {
        "type": "user-agent-interaction",
        "timestamp": int((result.get("timestamp") or 0) * 1000) or ts,
        "message": result.get("response", ""),
        "intent_mode": result.get("intent_mode", "normal"),
        "mock_interview_mode": result.get("mock_interview_mode", False),
        "current_round": result.get("current_round", 0),
        "is_complete": is_complete,
        **kwargs,
    }


async def handle_chat_message(session_id: str, query: str, websocket: WebSocket):
    """处理聊天消息 - 调用原有的 websocket_chat 逻辑"""
    from src.core.session_manager import get_session_manager, get_agent_singleton, build_langgraph_config

    sm = get_session_manager()
    sm.get_session(session_id)  # 确保 session 存在

    history = sm.get_history(session_id)
    agent_input = {"input_text": query, "history": history}
    config = build_langgraph_config(session_id)

    try:
        agent = get_agent_singleton().agent
        result = agent.invoke(agent_input, config)

        new_history = result.get("history", history)
        sm.update_history(session_id, new_history)

        # AG-UI 格式响应
        response_text = result.get("response", "")
        await websocket.send_json(_make_response_msg(result, websocket))

        # 发送完成信号
        await websocket.send_json(_make_response_msg(result, websocket, is_complete=True))

    except Exception as e:
        import traceback
        traceback.print_exc()
        logger.error(f"[AG-UI] 执行失败: {e}")
        await websocket.send_json({
            "type": "error",
            "message": str(e)
        })


async def handle_reset_message(session_id: str, websocket: WebSocket):
    """处理重置会话消息"""
    from src.core.session_manager import get_session_manager

    sm = get_session_manager()
    sm.update_history(session_id, [])
    await websocket.send_json({
        "type": "reset_complete"
    })


@router.websocket("/agui")
async def agui_websocket(websocket: WebSocket):
    """
    AG-UI WebSocket 端点
    处理 Agent 与用户之间的交互协议
    替换原有的 /ws/chat/{session_id} 端点
    """
    client_id = f"client_{id(websocket)}"
    await manager.connect(websocket, client_id)

    # 从连接中提取 session_id（前端需要在连接时提供）
    session_id = getattr(websocket, 'path_params', {}).get('session_id', 'default')
    
    # 从查询参数获取 session_id
    try:
        # 尝试从 URL 路径获取
        path = websocket.url.path
        if '/agui/' in path:
            session_id = path.split('/agui/')[-1]
        else:
            session_id = 'default'
    except:
        session_id = 'default'

    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)

            # AG-UI 格式：用户发送消息给 Agent
            if message.get('type') == 'agent-user-interaction':
                query = message.get('message', '')
                if query:
                    await handle_chat_message(session_id, query, websocket)
                else:
                    # 空消息，可能是心跳或初始化
                    await websocket.send_json({
                        "type": "pong",
                        "timestamp": int(message.get('timestamp', 0))
                    })

            # 未知消息类型
            else:
                logger.warning(f"AG-UI: Unknown message type: {message.get('type')}")

    except WebSocketDisconnect:
        manager.disconnect(client_id)
        logger.info(f"AG-UI: Client {client_id} disconnected")

    except json.JSONDecodeError as e:
        logger.error(f"AG-UI: JSON decode error: {e}")
        await websocket.close()

    except Exception as e:
        logger.error(f"AG-UI: Error: {e}")
        await websocket.close()


@router.get("/agui/health")
async def agui_health_check():
    """AG-UI 健康检查端点"""
    return {
        "status": "ok",
        "connected_clients": len(manager.active_connections),
        "protocol": "AG-UI (Agent User Interaction Protocol)"
    }