import pytest
from unittest import mock

# 被测模块中的全局变量
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
    """测试传入None值时socketio实例被设置为None"""
    # Arrange
    global socketio
    socketio = mock.MagicMock()  # 先设置一个非None值
    
    # Act
    init_socketio(None)
    
    # Assert
    assert socketio is None, "传入None时socketio实例应该被设置为None"

def test_init_socketio_multiple_calls():
    """测试多次调用init_socketio时全局变量被正确更新"""
    # Arrange
    mock_socketio1 = mock.MagicMock()
    mock_socketio2 = mock.MagicMock()
    
    # Act & Assert
    init_socketio(mock_socketio1)
    assert socketio == mock_socketio1, "第一次调用后应该设置第一个实例"
    
    init_socketio(mock_socketio2)
    assert socketio == mock_socketio2, "第二次调用后应该更新为第二个实例"

def test_init_socketio_with_non_socketio_object():
    """测试传入非socketio对象时也能正常工作"""
    # Arrange
    non_socketio_obj = "not a socketio instance"
    
    # Act
    init_socketio(non_socketio_obj)
    
    # Assert
    assert socketio == non_socketio_obj, "应该能接受任何类型的对象赋值"