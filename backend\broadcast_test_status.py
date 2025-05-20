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
    mock_datetime = mock.MagicMock()
    mock_datetime.now.return_value = mock_now
    monkeypatch.setattr('your_module.datetime', mock_datetime)
    return mock_now

def test_broadcast_test_status_with_socketio_initialized(mock_socketio, mock_datetime_now):
    """测试socketio已初始化时的正常广播"""
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
    
    mock_socketio.emit.assert_any_call('test_status', expected_data)
    assert not mock_socketio.emit.called_with('test_metrics', mock.ANY)

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
    
    mock_socketio.emit.assert_called_with('test_status', expected_data)

def test_broadcast_test_status_with_final_status(mock_socketio, mock_datetime_now):
    """测试最终状态(completed/stopped/failed)时的广播"""
    test_id = "test123"
    for status in ['completed', 'stopped', 'failed']:
        mock_socketio.reset_mock()
        
        with mock.patch('your_module.socketio', mock_socketio):
            broadcast_test_status(test_id, status)
        
        expected_status_data = {
            'test_id': test_id,
            'status': status,
            'timestamp': mock_datetime_now.isoformat()
        }
        expected_metrics_data = {
            'test_id': test_id,
            'progress': 100,
            'status': status,
            'timestamp': mock_datetime_now.isoformat()
        }
        
        mock_socketio.emit.assert_any_call('test_status', expected_status_data)
        mock_socketio.emit.assert_any_call('test_metrics', expected_metrics_data)

def test_broadcast_test_status_with_socketio_not_initialized(capsys):
    """测试socketio未初始化时的处理"""
    test_id = "test123"
    status = "running"
    
    with mock.patch('your_module.socketio', None):
        broadcast_test_status(test_id, status)
    
    captured = capsys.readouterr()
    assert f"错误: socketio未初始化，无法广播测试状态 (test_id={test_id}, status={status})" in captured.out

def test_broadcast_test_status_with_emit_exception(mock_socketio, mock_datetime_now, capsys):
    """测试广播时发生异常的处理"""
    test_id = "test123"
    status = "running"
    error_message = "Connection error"
    mock_socketio.emit.side_effect = Exception(error_message)
    
    with mock.patch('your_module.socketio', mock_socketio):
        broadcast_test_status(test_id, status)
    
    captured = capsys.readouterr()
    assert f"广播测试状态时出错: {error_message}" in captured.out