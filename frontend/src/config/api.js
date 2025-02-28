// API 基础配置
export const API_BASE_URL = 'http://localhost:5001';
export const WS_BASE_URL = 'ws://localhost:5001';

// API 端点
export const API_ENDPOINTS = {
    // 脚本相关
    SCRIPTS: '/api/scripts',
    
    // 测试相关
    START_TEST: '/api/tests/start',
    STOP_TEST: '/api/tests/stop',
    TEST_STATUS: '/api/tests/status',
    TEST_HISTORY: '/api/tests/history',
    TEST_REPORT: '/api/tests/report',
    
    // WebSocket
    WS_METRICS: '/socket.io'  // 使用 socket.io 路径
};

// 完整的 API URL
export const getApiUrl = (endpoint) => `${API_BASE_URL}${endpoint}`;
export const getWsUrl = (endpoint) => `${WS_BASE_URL}${endpoint}`; 