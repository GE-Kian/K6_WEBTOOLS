import pytest
from unittest import mock
from datetime import datetime
from your_module import broadcast_test_status  # 替换为实际模块名

@pytest.fixture
def mock_socketio():
    return mock.MagicMock()

@pytest.fixture
def mock_datetime_now(monkeypatch):
    mock_now = datetime(2023, 1, 1, 12, 0, 0)
    with mock.patch('your_module.datetime') as mock_datetime:
        mock_datetime.now.return_value = mock_now
        yield mock_now

def test_broadcast_test_status_with_socketio_initialized(mock_socketio, mock_datetime_now):
    """测试socketio已初始化时的正常广播"""
    test_id = "test123"
    status = "running"
    message = "Test is running"
    
    # 替换全局socketio为mock对象
    with mock.patch('your_module.socketio', mock_socketio):
        broadcast_test_status(test_id, status, message)
    
    # 验证emit调用
    expected_data = {
        'test_id': test_id,
        'status': status,
        'timestamp': mock_datetime_now.isoformat(),
        'message': message
    }
    mock_socketio.emit.assert_any_call('test_status', expected_data)
    assert not mock_socketio.emit.call_args_list[1:], "不应该发送额外的metrics更新"

def test_broadcast_test_status_without_message(mock_socketio, mock_datetime_now):
    """测试没有message参数时的广播"""
    test_id = "test123"
    status = "running"
    
    with mock.patch('your_module.socketio', mock_socketio):
        broadcast_test_status(test_id, status)
    
    expected_data = {
        'test_id': test_id,
        'status': status,
        'timestamp': mock_datetime_now.isoformat()
    }
    mock_socketio.emit.assert_called_once_with('test_status', expected_data)

def test_broadcast_test_status_with_final_status(mock_socketio, mock_datetime_now, capsys):
    """测试完成状态(completed/stopped/failed)时发送进度更新"""
    test_id = "test123"
    
    for status in ['completed', 'stopped', 'failed']:
        mock_socketio.reset_mock()
        with mock.patch('your_module.socketio', mock_socketio):
            broadcast_test_status(test_id, status)
        
        # 验证test_status广播
        expected_status_data = {
            'test_id': test_id,
            'status': status,
            'timestamp': mock_datetime_now.isoformat()
        }
        mock_socketio.emit.assert_any_call('test_status', expected_status_data)
        
        # 验证test_metrics广播
        expected_metrics_data = {
            'test_id': test_id,
            'progress': 100,
            'status': status,
            'timestamp': mock_datetime_now.isoformat()
        }
        mock_socketio.emit.assert_any_call('test_metrics', expected_metrics_data)
        
        # 验证打印输出
        captured = capsys.readouterr()
        assert f"测试 {test_id} 已{status}，发送100%进度更新" in captured.out

def test_broadcast_test_status_with_socketio_not_initialized(capsys):
    """测试socketio未初始化时的处理"""
    test_id = "test123"
    status = "running"
    
    with mock.patch('your_module.socketio', None):
        broadcast_test_status(test_id, status)
    
    captured = capsys.readouterr()
    assert f"错误: socketio未初始化，无法广播测试状态 (test_id={test_id}, status={status})" in captured.out

def test_broadcast_test_status_with_emit_exception(mock_socketio, mock_datetime_now, capsys):
    """测试emit抛出异常时的错误处理"""
    test_id = "test123"
    status = "running"
    error_message = "Connection failed"
    
    mock_socketio.emit.side_effect = Exception(error_message)
    
    with mock.patch('your_module.socketio', mock_socketio):
        broadcast_test_status(test_id, status)
    
    captured = capsys.readouterr()
    assert f"广播测试状态时出错: {error_message}" in captured.out