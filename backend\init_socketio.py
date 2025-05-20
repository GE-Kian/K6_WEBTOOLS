import pytest
from unittest import mock

# 被测函数中的全局变量
socketio = None

def test_init_socketio_successful_initialization():
    """测试成功初始化socketio实例"""
    # Arrange
    mock_socketio = mock.MagicMock()
    
    # Act
    init_socketio(mock_socketio)
    
    # Assert
    assert socketio == mock_socketio, "socketio实例应该被正确初始化"

def test_init_socketio_with_none_input():
    """测试传入None值初始化socketio实例"""
    # Arrange
    global socketio
    original_socketio = socketio
    
    # Act
    init_socketio(None)
    
    # Assert
    assert socketio is None, "socketio实例应该允许被设置为None"
    
    # Cleanup
    socketio = original_socketio

def test_init_socketio_multiple_calls():
    """测试多次调用初始化函数"""
    # Arrange
    mock_socketio1 = mock.MagicMock()
    mock_socketio2 = mock.MagicMock()
    
    # Act & Assert
    init_socketio(mock_socketio1)
    assert socketio == mock_socketio1, "第一次初始化应该成功"
    
    init_socketio(mock_socketio2)
    assert socketio == mock_socketio2, "第二次初始化应该覆盖第一次的值"

def test_init_socketio_with_non_mock_object():
    """测试使用非mock对象初始化"""
    # Arrange
    class DummySocketIO:
        pass
    
    dummy = DummySocketIO()
    
    # Act
    init_socketio(dummy)
    
    # Assert
    assert socketio == dummy, "socketio实例应该接受任何对象类型"