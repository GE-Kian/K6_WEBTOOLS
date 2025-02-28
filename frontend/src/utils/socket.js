import { io } from 'socket.io-client';

const SOCKET_URL = 'http://localhost:5001';

class Socket {
    constructor() {
        this.socket = null;
        this.events = new Map();
        this.connect();
    }

    connect() {
        if (this.socket) {
            this.socket.close();
        }

        this.socket = io(SOCKET_URL, {
            transports: ['websocket', 'polling'],
            reconnection: true,
            reconnectionDelay: 1000,
            reconnectionDelayMax: 5000,
            timeout: 20000
        });

        this.socket.on('connect', () => {
            console.log('连接成功');
            this.emit('client_ready');
        });

        this.socket.on('disconnect', () => {
            console.log('连接断开');
        });

        this.socket.on('connect_error', (error) => {
            console.error('连接错误:', error);
        });

        return this;
    }

    on(event, callback) {
        if (!this.events.has(event)) {
            this.events.set(event, new Set());
        }
        this.events.get(event).add(callback);
        this.socket.on(event, callback);
        return this;
    }

    off(event, callback) {
        if (this.events.has(event)) {
            this.events.get(event).delete(callback);
        }
        this.socket.off(event, callback);
        return this;
    }

    emit(event, data) {
        if (this.socket && this.socket.connected) {
            this.socket.emit(event, data);
        }
        return this;
    }

    disconnect() {
        if (this.socket) {
            this.socket.disconnect();
            this.socket = null;
        }
        this.events.clear();
    }
}

// 创建单例
const socket = new Socket();

// 导出实例和方法
export const { on, off, emit } = socket;
export default socket; 