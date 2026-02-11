"""Conversation logging module for deepagents-cli.

This module provides functionality to log user questions and AI responses
in a human-readable format.

Log storage locations:
- Project logs: {project_root}/.deepagents/logs/{thread_id}.md
- Novel project logs: .novel/logs/{thread_id}.md

Log format: Markdown with timestamps for easy reading and sharing.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from deepagents_cli.config import settings

# Global logger instance
_logger: "ConversationLogger | None" = None


class ConversationLogger:
    """Logger for recording conversation history."""

    def __init__(
        self,
        log_dir: Path | str | None = None,
        thread_id: str | None = None,
        agent_name: str | None = None,
        enable_json: bool = False,
    ):
        """Initialize the conversation logger.

        Args:
            log_dir: Directory to store logs. Defaults to {project_root}/.deepagents/logs/
            thread_id: Session/thread identifier for the log file name
            agent_name: Name of the agent for context
            enable_json: Also save logs in JSON format for programmatic access
        """
        self.thread_id = thread_id or "default"
        self.agent_name = agent_name or "agent"
        self.enable_json = enable_json

        # Set up log directory
        if log_dir:
            self.log_dir = Path(log_dir)
        else:
            self.log_dir = settings.user_deepagents_dir / "logs"

        self.log_dir.mkdir(parents=True, exist_ok=True)

        # Log file paths
        self.md_log_file = self.log_dir / f"{self.thread_id}.md"
        self.json_log_file = self.log_dir / f"{self.thread_id}.jsonl"

        # Initialize log file with header if new
        if not self.md_log_file.exists():
            self._write_header()

    def _write_header(self) -> None:
        """Write markdown header to new log file."""
        header = f"""# Conversation Log

**Thread ID**: {self.thread_id}
**Agent**: {self.agent_name}
**Started**: {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")}

---

"""
        self.md_log_file.write_text(header, encoding="utf-8")

    def _get_timestamp(self) -> str:
        """Get formatted timestamp."""
        return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    def _append_md(self, content: str) -> None:
        """Append content to markdown log file."""
        with open(self.md_log_file, "a", encoding="utf-8") as f:
            f.write(content)

    def _append_json(self, record: dict) -> None:
        """Append record to JSON log file."""
        if self.enable_json:
            with open(self.json_log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def log_user_message(self, message: str) -> None:
        """Log a user message.

        Args:
            message: The user's message content
        """
        timestamp = self._get_timestamp()

        # Markdown format
        md_content = f"""## User [{timestamp}]

{message}

"""
        self._append_md(md_content)

        # JSON format
        self._append_json(
            {
                "type": "user",
                "timestamp": timestamp,
                "content": message,
            }
        )

    def log_assistant_message(self, message: str, model: str | None = None) -> None:
        """Log an assistant (AI) response.

        Args:
            message: The assistant's response content
            model: Optional model name that generated the response
        """
        timestamp = self._get_timestamp()
        model_info = f" (Model: {model})" if model else ""

        # Markdown format
        md_content = f"""## Assistant [{timestamp}]{model_info}

{message}

"""
        self._append_md(md_content)

        # JSON format
        record = {
            "type": "assistant",
            "timestamp": timestamp,
            "content": message,
        }
        if model:
            record["model"] = model
        self._append_json(record)

    def log_tool_call(
        self,
        tool_name: str,
        args: dict | None = None,
        result: str | None = None,
        status: str = "success",
    ) -> None:
        """Log a tool call and its result.

        Args:
            tool_name: Name of the tool called
            args: Arguments passed to the tool
            result: Result of the tool execution
            status: Status of the tool call ("success" or "error")
        """
        timestamp = self._get_timestamp()
        status_icon = "+" if status == "success" else "x"

        # Format args
        args_str = ""
        if args:
            # Truncate long content in args
            truncated_args = {}
            for k, v in args.items():
                if isinstance(v, str) and len(v) > 500:
                    truncated_args[k] = v[:500] + "..."
                else:
                    truncated_args[k] = v
            args_str = f"\n```json\n{json.dumps(truncated_args, ensure_ascii=False, indent=2)}\n```"

        # Format result
        result_str = ""
        if result:
            result_preview = result[:1000] + "..." if len(result) > 1000 else result
            result_str = f"\n**Result:**\n```\n{result_preview}\n```"

        # Markdown format
        md_content = f"""### [{status_icon}] Tool: {tool_name} [{timestamp}]
{args_str}{result_str}

"""
        self._append_md(md_content)

        # JSON format
        self._append_json(
            {
                "type": "tool_call",
                "timestamp": timestamp,
                "tool_name": tool_name,
                "args": args,
                "result": result[:2000] if result else None,
                "status": status,
            }
        )

    def log_system_message(self, message: str) -> None:
        """Log a system message.

        Args:
            message: The system message content
        """
        timestamp = self._get_timestamp()

        # Markdown format
        md_content = f"""### System [{timestamp}]

*{message}*

"""
        self._append_md(md_content)

        # JSON format
        self._append_json(
            {
                "type": "system",
                "timestamp": timestamp,
                "content": message,
            }
        )

    def log_error(self, error: str) -> None:
        """Log an error message.

        Args:
            error: The error message
        """
        timestamp = self._get_timestamp()

        # Markdown format
        md_content = f"""### Error [{timestamp}]

**{error}**

"""
        self._append_md(md_content)

        # JSON format
        self._append_json(
            {
                "type": "error",
                "timestamp": timestamp,
                "content": error,
            }
        )

    def get_log_path(self) -> Path:
        """Get the path to the markdown log file.

        Returns:
            Path to the log file
        """
        return self.md_log_file

    def get_recent_logs(self, n: int = 20) -> str:
        """Get the most recent log entries.

        Args:
            n: Number of recent entries to return

        Returns:
            String containing recent log entries
        """
        if not self.md_log_file.exists():
            return "No logs found."

        content = self.md_log_file.read_text(encoding="utf-8")
        lines = content.split("\n")

        # Find the last n entries by looking for "## " markers
        entry_starts = []
        for i, line in enumerate(lines):
            if line.startswith("## ") or line.startswith("### "):
                entry_starts.append(i)

        if not entry_starts:
            return content

        # Get last n entries
        start_idx = entry_starts[-n] if len(entry_starts) >= n else entry_starts[0]
        return "\n".join(lines[start_idx:])


def init_logger(
    thread_id: str | None = None,
    agent_name: str | None = None,
    log_dir: Path | str | None = None,
    enable_json: bool = False,
) -> ConversationLogger:
    """Initialize or reinitialize the global logger.

    Args:
        thread_id: Session/thread identifier
        agent_name: Name of the agent
        log_dir: Directory to store logs
        enable_json: Also save logs in JSON format

    Returns:
        The initialized ConversationLogger instance
    """
    global _logger
    _logger = ConversationLogger(
        log_dir=log_dir,
        thread_id=thread_id,
        agent_name=agent_name,
        enable_json=enable_json,
    )
    return _logger


def get_logger() -> ConversationLogger | None:
    """Get the global logger instance.

    Returns:
        The global ConversationLogger or None if not initialized
    """
    return _logger


def log_user(message: str) -> None:
    """Log a user message using the global logger.

    Args:
        message: The user's message
    """
    if _logger:
        _logger.log_user_message(message)


def log_assistant(message: str, model: str | None = None) -> None:
    """Log an assistant message using the global logger.

    Args:
        message: The assistant's response
        model: Optional model name
    """
    if _logger:
        _logger.log_assistant_message(message, model)


def log_tool(
    tool_name: str,
    args: dict | None = None,
    result: str | None = None,
    status: str = "success",
) -> None:
    """Log a tool call using the global logger.

    Args:
        tool_name: Name of the tool
        args: Tool arguments
        result: Tool result
        status: Call status
    """
    if _logger:
        _logger.log_tool_call(tool_name, args, result, status)


def log_system(message: str) -> None:
    """Log a system message using the global logger.

    Args:
        message: The system message
    """
    if _logger:
        _logger.log_system_message(message)


def log_error(error: str) -> None:
    """Log an error using the global logger.

    Args:
        error: The error message
    """
    if _logger:
        _logger.log_error(error)


def list_logs(log_dir: Path | str | None = None, limit: int = 20) -> list[dict]:
    """List available log files.

    Args:
        log_dir: Directory to search for logs
        limit: Maximum number of logs to return

    Returns:
        List of log file info dictionaries
    """
    if log_dir:
        search_dir = Path(log_dir)
    else:
        search_dir = settings.user_deepagents_dir / "logs"

    if not search_dir.exists():
        return []

    logs = []
    for log_file in sorted(search_dir.glob("*.md"), key=os.path.getmtime, reverse=True):
        if len(logs) >= limit:
            break

        stat = log_file.stat()
        logs.append(
            {
                "thread_id": log_file.stem,
                "path": str(log_file),
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            }
        )

    return logs


def view_log(
    thread_id: str,
    log_dir: Path | str | None = None,
    recent_only: int | None = None,
) -> str:
    """View the contents of a specific log.

    Args:
        thread_id: The thread ID to view
        log_dir: Directory containing logs
        recent_only: If set, return only the last N entries

    Returns:
        Log content as string
    """
    if log_dir:
        search_dir = Path(log_dir)
    else:
        search_dir = settings.user_deepagents_dir / "logs"

    log_file = search_dir / f"{thread_id}.md"

    if not log_file.exists():
        return f"Log not found: {thread_id}"

    content = log_file.read_text(encoding="utf-8")

    if recent_only:
        lines = content.split("\n")
        entry_starts = []
        for i, line in enumerate(lines):
            if line.startswith("## ") or line.startswith("### "):
                entry_starts.append(i)

        if entry_starts and len(entry_starts) > recent_only:
            start_idx = entry_starts[-recent_only]
            content = "\n".join(lines[start_idx:])

    return content
