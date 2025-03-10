from datetime import datetime

# 初始化时设置为None，在app.py中初始化
socketio = None

def init_socketio(socket_instance):
    """初始化socketio实例"""
    global socketio
    socketio = socket_instance

def broadcast_metrics(test_id, metrics_data):
    """广播测试指标数据"""
    if socketio:
        socketio.emit('test_metrics', {
            'test_id': test_id,
            'data': metrics_data,
            'timestamp': datetime.now().isoformat()
        })

def broadcast_test_status(test_id, status, message=None):
    """广播测试状态更新"""
    if socketio:
        socketio.emit('test_status', {
            'test_id': test_id,
            'status': status,
            'message': message,
            'timestamp': datetime.now().isoformat()
        }) 