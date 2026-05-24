// AG-UI Protocol Implementation for IntelliView
// Agent User Interaction Protocol

class AGUIProtocol {
    constructor() {
        this.events = new Map();
        this.messageQueue = [];
        this.websocket = null;
    }

    // 发送消息给 Agent
    send(message) {
        // AG-UI 标准消息格式
        const aguiMessage = {
            type: 'agent-user-interaction',
            timestamp: Date.now(),
            message: message
        };

        // 发送到后端
        this.sendMessageToBackend(aguiMessage);
    }

    // 接收来自 Agent 的消息
    receive(message) {
        // AG-UI 标准消息格式
        const aguiMessage = {
            type: 'user-agent-interaction',
            timestamp: Date.now(),
            message: message
        };

        // 触发事件
        this.dispatchEvent('message', aguiMessage);
    }

    // 事件监听
    on(event, callback) {
        if (!this.events.has(event)) {
            this.events.set(event, []);
        }
        this.events.get(event).push(callback);
    }

    // 触发事件
    dispatchEvent(event, data) {
        if (this.events.has(event)) {
            this.events.get(event).forEach(callback => callback(data));
        }
    }

    // 消息队列处理
    processQueue() {
        while (this.messageQueue.length > 0) {
            const message = this.messageQueue.shift();
            this.receive(message);
        }
    }

    sendMessageToBackend(message) {
        // 通过 WebSocket 发送到后端
        if (this.websocket) {
            this.websocket.send(JSON.stringify(message));
        } else {
            this.messageQueue.push(message);
        }
    }

    connectWebSocket(url) {
        this.websocket = new WebSocket(url);

        this.websocket.onmessage = (event) => {
            const message = JSON.parse(event.data);
            this.receive(message);
        };

        this.websocket.onopen = () => {
            console.log('AG-UI WebSocket connected');
            this.processQueue();
        };

        websocket.onerror = (error) => {
            console.error('AG-UI WebSocket error:', error);
        };

        websocket.onclose = () => {
            console.log('AG-UI WebSocket closed');
        };
    }
}

// 导出 AG-UI Protocol 实例
const agui = new AGUIProtocol();

// 自动连接 WebSocket
agui.connectWebSocket('ws://localhost:8000/agui');
