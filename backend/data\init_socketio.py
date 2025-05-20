import pytest
from unittest import mock

# 被测函数中的全局变量
socketio = None

def test_init_socketio_successful_initialization():
    """测试成功初始化socketio实例的情况"""
    # 准备
    mock_socketio = mock.MagicMock()
    
    # 执行
    init_socketio(mock_socketio)
    
    # 断言
    global socketio
    assert socketio == mock_socketio, "socketio实例应该被正确初始化"
    
def test_init_socketio_with_none_parameter():
    """测试传入None参数的情况"""
    # 准备
    global socketio
    original_socketio = socketio
    
    # 执行
    init_socketio(None)
    
    # 断言
    assert socketio is None, "传入None时socketio应该被设置为None"
    
    # 清理
    socketio = original_socketio

def test_init_socketio_overwrite_existing_value():
    """测试覆盖已存在的socketio实例的情况"""
    # 准备
    global socketio
    original_socketio = mock.MagicMock()
    socketio = original_socketio
    new_socketio = mock.MagicMock()
    
    # 执行
    init_socketio(new_socketio)
    
    # 断言
    assert socketio == new_socketio, "应该能够覆盖已存在的socketio实例"
    assert socketio != original_socketio, "新的socketio实例应该替换旧的实例"
    
    # 清理
    socketio = original_socketio

def test_init_socketio_with_non_mock_object():
    """测试传入非mock对象的情况"""
    # 准备
    class FakeSocketIO:
        pass
    
    fake_socketio = FakeSocketIO()
    
    # 执行
    init_socketio(fake_socketio)
    
    # 断言
    global socketio
    assert isinstance(socketio, FakeSocketIO), "应该能够接受任何类型的对象作为参数"
    assert socketio == fake_socketio, "传入的对象应该被正确设置"