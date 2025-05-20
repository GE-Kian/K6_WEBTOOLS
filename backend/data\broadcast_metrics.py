import pytest
from unittest import mock
from datetime import datetime
from your_module import broadcast_metrics

@pytest.fixture
def mock_socketio():
    with mock.patch('your_module.socketio') as mock_socket:
        yield mock_socket

@pytest.fixture
def valid_metrics_data():
    return {
        'test_id': 'test_123',
        'metrics': {
            'vus': 10,
            'rps': 100,
            'response_time': 50,
            'error_rate': 0.1,
            'total_requests': 1000,
            'failed_requests': 10
        },
        'progress': 50,
        'status': 'running'
    }

def test_broadcast_metrics_with_valid_data(mock_socketio, valid_metrics_data):
    """测试使用完整有效数据时函数正常工作"""
    broadcast_metrics(valid_metrics_data)
    
    # 检查是否添加了时间戳
    assert 'timestamp' in valid_metrics_data
    assert isinstance(valid_metrics_data['timestamp'], str)
    
    # 检查socketio.emit是否被正确调用
    mock_socketio.emit.assert_called_once_with('test_metrics', valid_metrics_data)

def test_broadcast_metrics_with_missing_test_id(mock_socketio, capsys):
    """测试缺少test_id时的错误处理"""
    data = {'metrics': {}}
    broadcast_metrics(data)
    
    # 检查错误消息
    captured = capsys.readouterr()
    assert "错误: metrics_data中缺少test_id" in captured.out
    
    # 检查socketio.emit未被调用
    mock_socketio.emit.assert_not_called()

def test_broadcast_metrics_with_missing_metrics(mock_socketio):
    """测试缺少metrics字段时的默认值设置"""
    data = {'test_id': 'test_123'}
    broadcast_metrics(data)
    
    # 检查是否添加了默认metrics
    assert 'metrics' in data
    metrics = data['metrics']
    assert metrics['vus'] == 0
    assert metrics['rps'] == 0
    assert metrics['response_time'] == 0
    assert metrics['error_rate'] == 0
    assert metrics['total_requests'] == 0
    assert metrics['failed_requests'] == 0
    
    # 检查socketio.emit被调用
    mock_socketio.emit.assert_called_once()

def test_broadcast_metrics_with_missing_progress_and_status(mock_socketio):
    """测试缺少progress和status字段时的默认值设置"""
    data = {'test_id': 'test_123', 'metrics': {}}
    broadcast_metrics(data)
    
    # 检查是否添加了默认progress和status
    assert data['progress'] == 0
    assert data['status'] == 'running'
    
    # 检查socketio.emit被调用
    mock_socketio.emit.assert_called_once()

def test_broadcast_metrics_with_socketio_not_initialized(capsys):
    """测试socketio未初始化时的错误处理"""
    with mock.patch('your_module.socketio', None):
        data = {'test_id': 'test_123'}
        broadcast_metrics(data)
    
    # 检查错误消息
    captured = capsys.readouterr()
    assert "错误: socketio未初始化，无法广播指标数据" in captured.out

def test_broadcast_metrics_with_exception_handling(mock_socketio, capsys):
    """测试异常情况下的错误处理"""
    mock_socketio.emit.side_effect = Exception("Test error")
    data = {'test_id': 'test_123'}
    
    broadcast_metrics(data)
    
    # 检查错误消息
    captured = capsys.readouterr()
    assert "广播指标数据时出错: Test error" in captured.out

def test_broadcast_metrics_timestamp_generation(mock_socketio):
    """测试时间戳是否正确生成"""
    test_time = datetime(2023, 1, 1, 12, 0, 0)
    with mock.patch('your_module.datetime') as mock_datetime:
        mock_datetime.now.return_value = test_time
        data = {'test_id': 'test_123'}
        broadcast_metrics(data)
    
    # 检查时间戳格式和值
    assert data['timestamp'] == test_time.isoformat()
    mock_socketio.emit.assert_called_once()