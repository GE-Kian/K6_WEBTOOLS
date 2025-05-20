import pytest
from unittest import mock
from datetime import datetime
from your_module import broadcast_test_status

@pytest.fixture
def mock_socketio():
    return mock.MagicMock()

@pytest.fixture
def mock_datetime_now(monkeypatch):
    mock_now = datetime(2023, 1, 1, 12, 0, 0)
    datetime_mock = mock.MagicMock(wraps=datetime)
    datetime_mock.now.return_value = mock_now
    monkeypatch.setattr('your_module.datetime', datetime_mock)
    return mock_now

def test_broadcast_test_status_with_message(mock_socketio, mock_datetime_now):
    """测试广播带有消息的测试状态"""
    test_id = "test123"
    status = "running"
    message = "Test is running"
    
    with mock.patch('your_module.socketio', mock_socketio):
        broadcast_test_status(test_id, status, message)
        
        expected_data = {
            'test_id': test_id,
            'status': status,
            'timestamp': mock_datetime_now.isoformat(),
            'message': message
        }
        
        mock_socketio.emit.assert_called_once_with('test_status', expected_data)
        mock_socketio.emit.reset_mock()

def test_broadcast_test_status_without_message(mock_socketio, mock_datetime_now):
    """测试广播不带消息的测试状态"""
    test_id = "test456"
    status = "started"
    
    with mock.patch('your_module.socketio', mock_socketio):
        broadcast_test_status(test_id, status)
        
        expected_data = {
            'test_id': test_id,
            'status': status,
            'timestamp': mock_datetime_now.isoformat()
        }
        
        mock_socketio.emit.assert_called_once_with('test_status', expected_data)
        mock_socketio.emit.reset_mock()

def test_broadcast_completed_status_sends_metrics(mock_socketio, mock_datetime_now):
    """测试广播完成状态时发送指标数据"""
    test_id = "test789"
    status = "completed"
    
    with mock.patch('your_module.socketio', mock_socketio):
        broadcast_test_status(test_id, status)
        
        # 检查test_status广播
        expected_status_data = {
            'test_id': test_id,
            'status': status,
            'timestamp': mock_datetime_now.isoformat()
        }
        mock_socketio.emit.assert_any_call('test_status', expected_status_data)
        
        # 检查test_metrics广播
        expected_metrics_data = {
            'test_id': test_id,
            'progress': 100,
            'status': status,
            'timestamp': mock_datetime_now.isoformat()
        }
        mock_socketio.emit.assert_any_call('test_metrics', expected_metrics_data)
        assert mock_socketio.emit.call_count == 2

def test_broadcast_failed_status_sends_metrics(mock_socketio, mock_datetime_now):
    """测试广播失败状态时发送指标数据"""
    test_id = "test999"
    status = "failed"
    
    with mock.patch('your_module.socketio', mock_socketio):
        broadcast_test_status(test_id, status)
        
        # 检查test_status广播
        expected_status_data = {
            'test_id': test_id,
            'status': status,
            'timestamp': mock_datetime_now.isoformat()
        }
        mock_socketio.emit.assert_any_call('test_status', expected_status_data)
        
        # 检查test_metrics广播
        expected_metrics_data = {
            'test_id': test_id,
            'progress': 100,
            'status': status,
            'timestamp': mock_datetime_now.isoformat()
        }
        mock_socketio.emit.assert_any_call('test_metrics', expected_metrics_data)
        assert mock_socketio.emit.call_count == 2

def test_broadcast_with_socketio_not_initialized(capsys):
    """测试当socketio未初始化时的行为"""
    test_id = "test000"
    status = "running"
    
    with mock.patch('your_module.socketio', None):
        broadcast_test_status(test_id, status)
        
        captured = capsys.readouterr()
        assert f"错误: socketio未初始化，无法广播测试状态 (test_id={test_id}, status={status})" in captured.out

def test_broadcast_with_emit_exception(mock_socketio, mock_datetime_now, capsys):
    """测试广播时发生异常的情况"""
    test_id = "test111"
    status = "running"
    error_message = "Connection failed"
    
    mock_socketio.emit.side_effect = Exception(error_message)
    
    with mock.patch('your_module.socketio', mock_socketio):
        broadcast_test_status(test_id, status)
        
        captured = capsys.readouterr()
        assert f"广播测试状态时出错: {error_message}" in captured.out