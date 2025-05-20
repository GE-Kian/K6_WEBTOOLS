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
        'test_id': 'test123',
        'metrics': {
            'vus': 10,
            'rps': 100,
            'response_time': 50,
            'error_rate': 0.1,
            'total_requests': 1000,
            'failed_requests': 100
        },
        'progress': 50,
        'status': 'running'
    }

def test_broadcast_metrics_with_valid_data(mock_socketio, valid_metrics_data):
    """测试使用完整有效数据时函数正常工作"""
    broadcast_metrics(valid_metrics_data)
    
    # 检查是否添加了时间戳
    assert 'timestamp' in valid_metrics_data
    # 检查socketio.emit是否被调用
    mock_socketio.emit.assert_called_once_with('test_metrics', valid_metrics_data)

def test_broadcast_metrics_with_missing_test_id(mock_socketio, capsys):
    """测试缺少test_id时的处理"""
    data = {'metrics': {}}
    broadcast_metrics(data)
    
    # 检查错误消息是否正确打印
    captured = capsys.readouterr()
    assert "错误: metrics_data中缺少test_id" in captured.out
    # 检查socketio.emit未被调用
    mock_socketio.emit.assert_not_called()

def test_broadcast_metrics_with_missing_metrics(mock_socketio):
    """测试缺少metrics字段时的处理"""
    data = {'test_id': 'test123'}
    broadcast_metrics(data)
    
    # 检查是否添加了默认metrics
    assert 'metrics' in data
    assert data['metrics'] == {
        'vus': 0,
        'rps': 0,
        'response_time': 0,
        'error_rate': 0,
        'total_requests': 0,
        'failed_requests': 0
    }
    # 检查socketio.emit被调用
    mock_socketio.emit.assert_called_once()

def test_broadcast_metrics_with_partial_metrics(mock_socketio):
    """测试metrics部分缺失时的处理"""
    data = {
        'test_id': 'test123',
        'metrics': {'vus': 5, 'rps': 50}
    }
    broadcast_metrics(data)
    
    # 检查是否添加了缺失的默认metrics
    assert data['metrics'] == {
        'vus': 5,
        'rps': 50,
        'response_time': 0,
        'error_rate': 0,
        'total_requests': 0,
        'failed_requests': 0
    }
    # 检查socketio.emit被调用
    mock_socketio.emit.assert_called_once()

def test_broadcast_metrics_with_missing_progress(mock_socketio):
    """测试缺少progress字段时的处理"""
    data = {'test_id': 'test123', 'metrics': {}}
    broadcast_metrics(data)
    
    # 检查是否添加了默认progress
    assert 'progress' in data
    assert data['progress'] == 0
    # 检查socketio.emit被调用
    mock_socketio.emit.assert_called_once()

def test_broadcast_metrics_with_missing_status(mock_socketio):
    """测试缺少status字段时的处理"""
    data = {'test_id': 'test123', 'metrics': {}}
    broadcast_metrics(data)
    
    # 检查是否添加了默认status
    assert 'status' in data
    assert data['status'] == 'running'
    # 检查socketio.emit被调用
    mock_socketio.emit.assert_called_once()

def test_broadcast_metrics_with_socketio_not_initialized(capsys):
    """测试socketio未初始化时的处理"""
    with mock.patch('your_module.socketio', None):
        data = {'test_id': 'test123', 'metrics': {}}
        broadcast_metrics(data)
        
        # 检查错误消息是否正确打印
        captured = capsys.readouterr()
        assert "错误: socketio未初始化，无法广播指标数据" in captured.out

def test_broadcast_metrics_with_exception(mock_socketio, capsys):
    """测试函数内部发生异常时的处理"""
    mock_socketio.emit.side_effect = Exception("Test error")
    data = {'test_id': 'test123', 'metrics': {}}
    broadcast_metrics(data)
    
    # 检查错误消息是否正确打印
    captured = capsys.readouterr()
    assert "广播指标数据时出错: Test error" in captured.out