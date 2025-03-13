from datetime import datetime

# 初始化时设置为None，在app.py中初始化
socketio = None

def init_socketio(app_socketio):
    """初始化socketio实例"""
    global socketio
    socketio = app_socketio

def broadcast_metrics(metrics_data):
    """广播测试指标数据
    
    Args:
        metrics_data: 包含测试ID和指标数据的字典
    """
    if not socketio:
        print("错误: socketio未初始化，无法广播指标数据")
        return
    
    # 添加时间戳
    if 'timestamp' not in metrics_data:
        metrics_data['timestamp'] = datetime.now().isoformat()
    
    try:
        # 确保数据格式正确
        if 'test_id' not in metrics_data:
            print("错误: metrics_data中缺少test_id")
            return
        
        # 确保metrics字段存在且格式正确
        if 'metrics' not in metrics_data:
            metrics_data['metrics'] = {}
        
        # 确保所有必要的指标都存在
        metrics = metrics_data['metrics']
        metrics.setdefault('vus', 0)
        metrics.setdefault('rps', 0)
        metrics.setdefault('response_time', 0)
        metrics.setdefault('error_rate', 0)
        metrics.setdefault('total_requests', 0)
        metrics.setdefault('failed_requests', 0)
        
        # 确保进度字段存在
        if 'progress' not in metrics_data:
            metrics_data['progress'] = 0
        
        # 确保状态字段存在
        if 'status' not in metrics_data:
            metrics_data['status'] = 'running'
            
        # 打印广播数据（调试用）
        print(f"广播指标数据: test_id={metrics_data['test_id']}, metrics={metrics_data.get('metrics', {})}, 进度={metrics_data.get('progress', 0)}%")
        
        # 直接发送metrics_data
        socketio.emit('test_metrics', metrics_data)
    except Exception as e:
        print(f"广播指标数据时出错: {str(e)}")

def broadcast_test_status(test_id, status, message=None):
    """广播测试状态更新"""
    if not socketio:
        print(f"错误: socketio未初始化，无法广播测试状态 (test_id={test_id}, status={status})")
        return
        
    try:
        data = {
            'test_id': test_id,
            'status': status,
            'timestamp': datetime.now().isoformat()
        }
        if message:
            data['message'] = message
            
        # 打印广播数据（调试用）
        print(f"广播测试状态: test_id={test_id}, status={status}, message={message}")
        
        # 发送状态更新
        socketio.emit('test_status', data)
        
        # 如果测试完成或失败，确保前端知道进度为100%
        if status in ['completed', 'stopped', 'failed']:
            metrics_data = {
                'test_id': test_id,
                'progress': 100,
                'status': status,
                'timestamp': datetime.now().isoformat()
            }
            socketio.emit('test_metrics', metrics_data)
            print(f"测试 {test_id} 已{status}，发送100%进度更新")
    except Exception as e:
        print(f"广播测试状态时出错: {str(e)}")