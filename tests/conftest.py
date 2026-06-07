import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    os.unlink(path)


@pytest.fixture
def sample_session():
    return {
        "id": "session-abc-123",
        "project": "test-project",
        "status": "active",
        "created_at": "2026-06-07T10:00:00Z",
        "updated_at": "2026-06-07T10:00:00Z",
    }


@pytest.fixture
def sample_tool_before():
    return {
        "type": "tool.execute.before",
        "data": {
            "tool": "Read",
            "args": {"file_path": "/test/file.py"},
            "user": "test-user",
        },
        "session_id": "session-abc-123",
        "timestamp": "2026-06-07T10:01:00Z",
    }


@pytest.fixture
def sample_tool_after():
    return {
        "type": "tool.execute.after",
        "data": {
            "tool": "Read",
            "duration": 150.5,
            "success": True,
            "output": {"lines": 100},
        },
        "session_id": "session-abc-123",
        "timestamp": "2026-06-07T10:01:01Z",
    }


@pytest.fixture
def sample_compacted_event():
    return {
        "type": "session.compacted",
        "data": {
            "context_size_before": 50000,
            "context_size_after": 20000,
        },
        "session_id": "session-abc-123",
        "timestamp": "2026-06-07T10:05:00Z",
    }


@pytest.fixture
def sample_message_event():
    return {
        "type": "message.user.updated",
        "data": {
            "role": "user",
            "content_size": 2048,
            "token_count": 512,
        },
        "session_id": "session-abc-123",
        "timestamp": "2026-06-07T10:02:00Z",
    }
