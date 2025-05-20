import pytest
from unittest import mock
from datetime import datetime

# 测试socketio未初始化的情况
@mock.patch('module.socketio', None)
@mock.patch('builtins.print')
def test_socketio_not_initialized(mock_print):
    broadcast_test_status('test1', 'running')
    mock_print.assert_called_once_with("错误: socketio未初始化，无法广播测试状态 (test_id=test1, status=running)")

# 测试正常状态广播（无message）
@mock.patch('module.socketio')
@mock.patch('module.datetime')
@mock.patch('builtins.print')
def test_broadcast_normal_status(mock_print, mock_datetime, mock_socketio):
    fixed_time = datetime(2023, 1, 1, 12, 0, 0)
    mock_datetime.now.return_value = fixed_time
    broadcast_test_status('test2', 'running')
    
    expected_data = {
        'test_id': 'test2',
        'status': 'running',
        'timestamp': fixed_time.isoformat()
    }
    mock_socketio.emit.assert_called_once_with('test_status', expected_data)
    mock_print.assert_called_once_with("广播测试状态: test_id=test2, status=running, message=None")

# 测试带message参数的广播
@mock.patch('module.socketio')
@mock.patch('module.datetime')
@mock.patch('builtins.print')
def test_broadcast_with_message(mock_print, mock_datetime, mock_socketio):
    fixed_time = datetime(2023, 1, 1, 12, 0, 0)
    mock_datetime.now.return_value = fixed_time
    message = "进行中"
    broadcast_test_status('test3', 'running', message)
    
    expected_data = {
        'test_id': 'test3',
        'status': 'running',
        'timestamp': fixed_time.isoformat(),
        'message': message
    }
    mock_socketio.emit.assert_called_once_with('test_status', expected_data)
    mock_print.assert_called_once_with(f"广播测试状态: test_id=test3, status=running, message={message}")

# 测试最终状态发送100%进度更新
@pytest.mark.parametrize('status', ['completed', 'stopped', 'failed'])
@mock.patch('module.socketio')
@mock.patch('module.datetime')
@mock.patch('builtins.print')
def test_final_status_sends_100_percent_progress(mock_print, mock_datetime, mock_socketio, status):
    fixed_time = datetime(2023, 1, 1, 12, 0, 0)
    mock_datetime.now.return_value = fixed_time
    broadcast_test_status('test4', status)
    
    test_status_call = mock.call('test_status', {
        'test_id': 'test4',
        'status': status,
        'timestamp': fixed_time.isoformat()
    })
    test_metrics_call = mock.call('test_metrics', {
        'test_id': 'test4',
        'progress': 100,
        'status': status,
        'timestamp': fixed_time.isoformat()
    })
    
    mock_socketio.emit.assert_has_calls([test_status_call, test_metrics_call])
    assert mock_socketio.emit.call_count == 2, "应该发送两次事件"
    mock_print.assert_any_call(f"测试 test4 已{status}，发送100%进度更新")

# 测试异常处理
@mock.patch('module.socketio')
@mock.patch('module.datetime')
@mock.patch('builtins.print')
def test_broadcast_exception_handling(mock_print, mock_datetime, mock_socketio):
    mock_socketio.emit.side_effect = Exception("emit错误")
    fixed_time = datetime(2023, 1, 1, 12, 0, 0)
    mock_datetime.now.return_value = fixed_time
    
    broadcast_test_status('test5', 'running')
    
    mock_socketio.emit.assert_called_once_with('test_status', mock.ANY)
    mock_print.assert_any_call("广播测试状态时出错: emit错误")