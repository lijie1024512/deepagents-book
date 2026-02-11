"""Unit tests for conversation logger module."""

import json
import tempfile
from pathlib import Path

import pytest

from deepagents_cli.conversation_logger import (
    ConversationLogger,
    get_logger,
    init_logger,
    list_logs,
    log_assistant,
    log_error,
    log_system,
    log_tool,
    log_user,
    view_log,
)


@pytest.fixture
def temp_log_dir():
    """Create a temporary directory for logs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


class TestConversationLogger:
    """Tests for ConversationLogger class."""

    def test_init_creates_log_dir(self, temp_log_dir):
        """Test that initialization creates the log directory."""
        log_dir = temp_log_dir / "nested" / "logs"
        logger = ConversationLogger(log_dir=log_dir, thread_id="test123")

        assert log_dir.exists()
        assert logger.log_dir == log_dir

    def test_init_creates_header(self, temp_log_dir):
        """Test that initialization creates a markdown header."""
        logger = ConversationLogger(
            log_dir=temp_log_dir, thread_id="test-thread", agent_name="test-agent"
        )

        content = logger.md_log_file.read_text()
        assert "# Conversation Log" in content
        assert "test-thread" in content
        assert "test-agent" in content

    def test_log_user_message(self, temp_log_dir):
        """Test logging user messages."""
        logger = ConversationLogger(log_dir=temp_log_dir, thread_id="test")
        logger.log_user_message("Hello, how are you?")

        content = logger.md_log_file.read_text()
        assert "## User" in content
        assert "Hello, how are you?" in content

    def test_log_assistant_message(self, temp_log_dir):
        """Test logging assistant messages."""
        logger = ConversationLogger(log_dir=temp_log_dir, thread_id="test")
        logger.log_assistant_message("I'm doing great!", model="claude-3")

        content = logger.md_log_file.read_text()
        assert "## Assistant" in content
        assert "I'm doing great!" in content
        assert "claude-3" in content

    def test_log_tool_call(self, temp_log_dir):
        """Test logging tool calls."""
        logger = ConversationLogger(log_dir=temp_log_dir, thread_id="test")
        logger.log_tool_call(
            tool_name="read_file",
            args={"path": "/test.txt"},
            result="File content here",
            status="success",
        )

        content = logger.md_log_file.read_text()
        assert "Tool: read_file" in content
        assert '"/test.txt"' in content
        assert "File content here" in content
        assert "[+]" in content  # success icon

    def test_log_tool_call_error(self, temp_log_dir):
        """Test logging failed tool calls."""
        logger = ConversationLogger(log_dir=temp_log_dir, thread_id="test")
        logger.log_tool_call(
            tool_name="write_file",
            args={"path": "/test.txt"},
            result="Permission denied",
            status="error",
        )

        content = logger.md_log_file.read_text()
        assert "[x]" in content  # error icon

    def test_log_system_message(self, temp_log_dir):
        """Test logging system messages."""
        logger = ConversationLogger(log_dir=temp_log_dir, thread_id="test")
        logger.log_system_message("Session started")

        content = logger.md_log_file.read_text()
        assert "### System" in content
        assert "Session started" in content

    def test_log_error(self, temp_log_dir):
        """Test logging errors."""
        logger = ConversationLogger(log_dir=temp_log_dir, thread_id="test")
        logger.log_error("Something went wrong")

        content = logger.md_log_file.read_text()
        assert "### Error" in content
        assert "Something went wrong" in content

    def test_json_logging(self, temp_log_dir):
        """Test JSON logging when enabled."""
        logger = ConversationLogger(log_dir=temp_log_dir, thread_id="test", enable_json=True)
        logger.log_user_message("Test message")

        # Check JSON file exists and has content
        assert logger.json_log_file.exists()
        with open(logger.json_log_file) as f:
            line = f.readline()
            record = json.loads(line)
            assert record["type"] == "user"
            assert record["content"] == "Test message"

    def test_get_log_path(self, temp_log_dir):
        """Test getting log file path."""
        logger = ConversationLogger(log_dir=temp_log_dir, thread_id="my-thread")
        path = logger.get_log_path()

        assert path == temp_log_dir / "my-thread.md"

    def test_get_recent_logs(self, temp_log_dir):
        """Test getting recent log entries."""
        logger = ConversationLogger(log_dir=temp_log_dir, thread_id="test")
        logger.log_user_message("First message")
        logger.log_assistant_message("First response")
        logger.log_user_message("Second message")
        logger.log_assistant_message("Second response")

        recent = logger.get_recent_logs(n=2)
        assert "Second message" in recent
        assert "Second response" in recent


class TestGlobalLoggerFunctions:
    """Tests for global logger convenience functions."""

    def test_init_logger_sets_global(self, temp_log_dir):
        """Test that init_logger sets the global logger."""
        init_logger(thread_id="global-test", log_dir=temp_log_dir)
        logger = get_logger()

        assert logger is not None
        assert logger.thread_id == "global-test"

    def test_log_user_global(self, temp_log_dir):
        """Test global log_user function."""
        init_logger(thread_id="global-test", log_dir=temp_log_dir)
        log_user("Hello world")

        logger = get_logger()
        content = logger.md_log_file.read_text()
        assert "Hello world" in content

    def test_log_assistant_global(self, temp_log_dir):
        """Test global log_assistant function."""
        init_logger(thread_id="global-test", log_dir=temp_log_dir)
        log_assistant("Hi there!", model="test-model")

        logger = get_logger()
        content = logger.md_log_file.read_text()
        assert "Hi there!" in content

    def test_log_tool_global(self, temp_log_dir):
        """Test global log_tool function."""
        init_logger(thread_id="global-test", log_dir=temp_log_dir)
        log_tool("shell", args={"command": "ls"}, result="file1 file2")

        logger = get_logger()
        content = logger.md_log_file.read_text()
        assert "shell" in content

    def test_log_system_global(self, temp_log_dir):
        """Test global log_system function."""
        init_logger(thread_id="global-test", log_dir=temp_log_dir)
        log_system("System ready")

        logger = get_logger()
        content = logger.md_log_file.read_text()
        assert "System ready" in content

    def test_log_error_global(self, temp_log_dir):
        """Test global log_error function."""
        init_logger(thread_id="global-test", log_dir=temp_log_dir)
        log_error("Test error")

        logger = get_logger()
        content = logger.md_log_file.read_text()
        assert "Test error" in content


class TestLogManagementFunctions:
    """Tests for log listing and viewing functions."""

    def test_list_logs_empty(self, temp_log_dir):
        """Test listing logs when directory is empty."""
        logs = list_logs(log_dir=temp_log_dir)
        assert logs == []

    def test_list_logs(self, temp_log_dir):
        """Test listing available logs."""
        # Create some log files
        ConversationLogger(log_dir=temp_log_dir, thread_id="thread1")
        ConversationLogger(log_dir=temp_log_dir, thread_id="thread2")

        logs = list_logs(log_dir=temp_log_dir)
        thread_ids = [log["thread_id"] for log in logs]

        assert "thread1" in thread_ids
        assert "thread2" in thread_ids

    def test_list_logs_limit(self, temp_log_dir):
        """Test limiting number of logs returned."""
        for i in range(5):
            ConversationLogger(log_dir=temp_log_dir, thread_id=f"thread{i}")

        logs = list_logs(log_dir=temp_log_dir, limit=3)
        assert len(logs) == 3

    def test_view_log(self, temp_log_dir):
        """Test viewing a specific log."""
        logger = ConversationLogger(log_dir=temp_log_dir, thread_id="viewtest")
        logger.log_user_message("Test content")

        content = view_log("viewtest", log_dir=temp_log_dir)
        assert "Test content" in content

    def test_view_log_not_found(self, temp_log_dir):
        """Test viewing a non-existent log."""
        content = view_log("nonexistent", log_dir=temp_log_dir)
        assert "not found" in content.lower()

    def test_view_log_recent_only(self, temp_log_dir):
        """Test viewing only recent entries."""
        logger = ConversationLogger(log_dir=temp_log_dir, thread_id="recent-test")
        for i in range(10):
            logger.log_user_message(f"Message {i}")

        content = view_log("recent-test", log_dir=temp_log_dir, recent_only=3)
        # Should have recent messages but not early ones
        assert "Message 9" in content
        assert "Message 8" in content
        assert "Message 7" in content
