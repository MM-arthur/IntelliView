#!/usr/bin/env python3
"""
AG-UI Protocol Test Script

测试 AG-UI 协议的集成是否成功
"""

import asyncio
import websockets
import json
import time


async def test_agui_websocket():
    """测试 AG-UI WebSocket 连接"""

    uri = "ws://localhost:8000/agui"
    print(f"Connecting to AG-UI WebSocket: {uri}")

    try:
        async with websockets.connect(uri) as websocket:
            print("✓ Connected to AG-UI WebSocket")

            # 发送测试消息
            test_message = {
                "type": "agent-user-interaction",
                "timestamp": int(time.time() * 1000),
                "message": "Hello, AG-UI!"
            }

            print(f"Sending message: {json.dumps(test_message, indent=2)}")
            await websocket.send(json.dumps(test_message))

            # 接收响应
            response = await websocket.recv()
            response_data = json.loads(response)

            print(f"Received response: {json.dumps(response_data, indent=2)}")

            # 检查响应
            if response_data.get("type") == "user-agent-interaction":
                print("✓ AG-UI Protocol working correctly!")
                return True
            else:
                print("✗ Unexpected response type")
                return False

    except websockets.exceptions.WebSocketException as e:
        print(f"✗ WebSocket error: {e}")
        return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False


async def test_agui_health():
    """测试 AG-UI 健康检查端点"""

    import httpx

    url = "http://localhost:8000/agui/health"
    print(f"Checking AG-UI health: {url}")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            data = response.json()

            print(f"✓ Health check passed")
            print(f"  Status: {data.get('status')}")
            print(f"  Connected Clients: {data.get('connected_clients')}")
            print(f"  Protocol: {data.get('protocol')}")

            return True

    except Exception as e:
        print(f"✗ Health check failed: {e}")
        return False


async def main():
    """主测试函数"""

    print("=" * 60)
    print("AG-UI Protocol Test")
    print("=" * 60)
    print()

    # 测试健康检查
    print("1. Testing AG-UI Health Check...")
    health_ok = await test_agui_health()
    print()

    # 测试 WebSocket 连接
    print("2. Testing AG-UI WebSocket Connection...")
    websocket_ok = await test_agui_websocket()
    print()

    # 总结
    print("=" * 60)
    if health_ok and websocket_ok:
        print("✓ All AG-UI tests passed!")
    else:
        print("✗ Some tests failed")
        print("\nNote: Make sure the IntelliView server is running on port 8000")
        print("      Start it with: python src/main.py")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
