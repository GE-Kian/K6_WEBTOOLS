import pytest
from unittest import mock
from datetime import datetime
import sys

# 测试模块的导入可能需要调整路径
sys.modules['socketio'] = mock.Mock()  # 模拟全局socketio对象

from your_module import broadcast_metrics  # 替换为实际模块路径

@pytest.fixture
def mock_socketio(mocker):
    mocker.patch('your_module.socketio', new_callable=mock.Mock)
    return sys.modules['your_module'].socketio

@pytest.fixture
def valid_metrics_data():
    return {
        'test_id': 'test_123',
        'metrics': {
            'vus': 10,
            'rps': 100,
            'response_time': 0.5,
            'error_rate': 0.1,
            'total_requests': 1000,
            'failed_requests': 100
        },
        'progress': 50,
        'status': 'running'
    }

def test_broadcast_without_socketio_initialization(mock_socketio, capsys):
    """测试socketio未初始化时的处理"""
    mock_socketio.return_value = None
    broadcast_metrics({'test_id': 'test_123'})
    captured = capsys.readouterr()
    assert "错误: socketio未初始化，无法广播指标数据" in captured.out

def test_successful_metrics_broadcast(mock_socketio, valid_metrics_data, mocker):
    """测试正常指标广播流程"""
    mock_datetime = mocker.patch('your_module.datetime')
    mock_datetime.now.return_value.isoformat.return_value = '2023-01-01T00:00:00'
    
    broadcast_metrics(valid_metrics_data)
    
    mock_socketio.emit.assert_called_once_with('test_metrics', {
        'test_id': 'test_123',
        'metrics': valid_metrics_data['metrics'],
        'progress': 50,
        'status': 'running',
        'timestamp': '2023-01-01T00:00:00'
    })

def test_missing_test_id_handling(mock_socketio, capsys):
    """测试缺少test_id的错误处理"""
    broadcast_metrics({'metrics': {}})
    captured = capsys.readouterr()
    assert "错误: metrics_data中缺少test_id" in captured.out
    mock_socketio.emit.assert_not_called()

def test_metrics_field_initialization(mock_socketio, mocker):
    """测试自动补全metrics字段的默认值"""
    test_data = {'test_id': 'test_123'}
    mocker.patch('your_module.datetime').now.return_value.isoformat.return_value = 'fixed_time'
    
    broadcast_metrics(test_data)
    
    expected_metrics = {
        'vus': 0,
        'rps': 0,
        'response_time': 0,
        'error_rate': 0,
        'total_requests': 0,
        'failed_requests': 0
    }
    assert mock_socketio.emit.call_args[0][1]['metrics'] == expected_metrics
    assert mock_socketio.emit.call_args[0][1]['progress'] == 0
    assert mock_socketio.emit.call_args[0][1]['status'] == 'running'

def test_exception_handling(mock_socketio, valid_metrics_data, mocker):
    """测试异常捕获和处理"""
    mock_socketio.emit.side_effect = Exception("Network error")
    broadcast_metrics(valid_metrics_data)
    captured = capsys.readouterr()
    assert "广播指标数据时出错: Network error" in captured.out

def test_timestamp_generation(mock_socketio, mocker):
    """测试自动生成时间戳功能"""
    fixed_time = datetime(2023, 1, 1, 12, 0, 0)
    mock_datetime = mocker.patch('your_module.datetime')
    mock_datetime.now.return_value = fixed_time
    
    test_data = {'test_id': 'test_123'}
    broadcast_metrics(test_data)
    
    assert mock_socketio.emit.call_args[0][1]['timestamp'] == fixed_time.isoformat()

def test_partial_metrics_handling(mock_socketio):
    """测试部分指标字段的补全"""
    test_data = {
        'test_id': 'test_123',
        'metrics': {'vus': 5, 'rps': 50}
    }
    
    broadcast_metrics(test_data)
    
    metrics = mock_socketio.emit.call_args[0][1]['metrics']
    assert metrics['vus'] == 5
    assert metrics['rps'] == 50
    assert metrics['response_time'] == 0  # 默认值
    assert metrics['total_requests'] == 0  # 默认值

def test_progress_status_defaults(mock_socketio):
    """测试进度和状态的默认值设置"""
    test_data = {'test_id': 'test_123'}
    broadcast_metrics(test_data)
    
    emitted_data = mock_socketio.emit.call_args[0][1]
    assert emitted_data['progress'] == 0
    assert emitted_data['status'] == 'running'