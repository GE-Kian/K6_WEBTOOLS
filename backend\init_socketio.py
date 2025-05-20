import pytest
from unittest.mock import MagicMock
import sys

@pytest.fixture
def mock_module():
    # Mock the module containing the global socketio variable
    test_module = type(sys)('test_module')
    test_module.socketio = None
    sys.modules['test_module'] = test_module
    return test_module

def test_should_initialize_global_socketio_instance(mock_module):
    """Test initialization of global socketio instance with valid input"""
    from test_module import init_socketio
    mock_socketio = MagicMock()
    
    init_socketio(mock_socketio)
    assert mock_module.socketio is mock_socketio, \
        "Global socketio instance should be set to provided instance"

def test_should_override_existing_global_instance(mock_module):
    """Test that existing global socketio instance gets overwritten"""
    from test_module import init_socketio
    initial_mock = MagicMock()
    new_mock = MagicMock()
    mock_module.socketio = initial_mock
    
    init_socketio(new_mock)
    assert mock_module.socketio is new_mock, \
        "Existing global socketio instance should be overwritten"

def test_should_handle_none_value(mock_module):
    """Test initialization with None value"""
    from test_module import init_socketio
    mock_module.socketio = MagicMock()
    
    init_socketio(None)
    assert mock_module.socketio is None, \
        "Global socketio instance should accept None value"