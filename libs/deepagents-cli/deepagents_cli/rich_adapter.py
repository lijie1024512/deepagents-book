"""Pure terminal UI adapter using Rich for output (no TUI framework).

This adapter provides a simple terminal experience that works well on all platforms,
including Windows terminals where Textual's mouse events are not properly forwarded.
Users can scroll using the terminal's native scrollbar.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from langchain.agents.middleware.human_in_the_loop import (
    ActionRequest,
    HITLRequest,
    HITLResponse,
)
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.types import Command, Interrupt
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.styles import Style
from pydantic import TypeAdapter, ValidationError
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.syntax import Syntax
from rich.text import Text

from deepagents_cli.file_ops import FileOpTracker
from deepagents_cli.image_utils import create_multimodal_content
from deepagents_cli.input import ImageTracker, parse_file_mentions
from deepagents_cli.ui import format_tool_display, format_tool_message_content

if TYPE_CHECKING:
    pass

_HITL_REQUEST_ADAPTER = TypeAdapter(HITLRequest)

# Console for output
console = Console()

# Prompt style
PROMPT_STYLE = Style.from_dict({
    "prompt": "bold green",
})


def _is_summarization_chunk(metadata: dict | None) -> bool:
    """Check if a message chunk is from summarization middleware."""
    if metadata is None:
        return False
    return metadata.get("lc_source") == "summarization"


def print_welcome(version: str = "0.0.13a2") -> None:
    """Print welcome banner."""
    banner = """
[bold green]╔═══════════════════════════════════════════════════════════╗
║                                                           ║
║     █████╗  ██████╗ ███████╗███╗   ██╗████████╗███████╗  ║
║    ██╔══██╗██╔════╝ ██╔════╝████╗  ██║╚══██╔══╝██╔════╝  ║
║    ███████║██║  ███╗█████╗  ██╔██╗ ██║   ██║   ███████╗  ║
║    ██╔══██║██║   ██║██╔══╝  ██║╚██╗██║   ██║   ╚════██║  ║
║    ██║  ██║╚██████╔╝███████╗██║ ╚████║   ██║   ███████║  ║
║    ╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═══╝   ╚═╝   ╚══════╝  ║
║                                                           ║
╚═══════════════════════════════════════════════════════════╝[/bold green]
"""
    console.print(banner)
    console.print(f"[dim]v{version}[/dim]")
    console.print()
    console.print("[green]Ready to code![/green] What would you like to build?")
    console.print("[dim]Enter send • Ctrl+J newline • @ files • / commands[/dim]")
    console.print()


def print_user_message(message: str) -> None:
    """Print user message."""
    console.print(f"[bold blue]> {message}[/bold blue]")
    console.print()


def print_assistant_text(text: str) -> None:
    """Print assistant text as markdown."""
    md = Markdown(text)
    console.print(md)
    console.print()


def print_tool_call(tool_name: str, args: dict) -> None:
    """Print tool call notification."""
    display = format_tool_display(tool_name, args)
    console.print(f"[dim]⚙ {display}[/dim]")


def print_tool_result(tool_name: str, status: str, output: str | None = None) -> None:
    """Print tool result."""
    if status == "success":
        icon = "[green]✓[/green]"
    else:
        icon = "[red]✗[/red]"
    
    console.print(f"{icon} [dim]{tool_name}[/dim]")
    
    if output and len(output) > 200:
        # Truncate long output
        console.print(f"[dim]{output[:200]}...[/dim]")
    elif output:
        console.print(f"[dim]{output}[/dim]")


def print_diff(diff: str, file_path: str) -> None:
    """Print file diff."""
    console.print(f"[bold cyan]📝 {file_path}[/bold cyan]")
    
    for line in diff.split("\n"):
        if line.startswith("+") and not line.startswith("+++"):
            console.print(f"[green]{line}[/green]")
        elif line.startswith("-") and not line.startswith("---"):
            console.print(f"[red]{line}[/red]")
        elif line.startswith("@@"):
            console.print(f"[cyan]{line}[/cyan]")
        else:
            console.print(f"[dim]{line}[/dim]")
    console.print()


def print_error(message: str) -> None:
    """Print error message."""
    console.print(f"[bold red]Error: {message}[/bold red]")


def print_system(message: str) -> None:
    """Print system message."""
    console.print(f"[yellow]{message}[/yellow]")


def prompt_approval(action_request: ActionRequest, auto_approve: bool) -> dict[str, str]:
    """Prompt user for tool approval.
    
    Returns:
        Decision dict: {"type": "approve"}, {"type": "reject"}, or {"type": "auto_approve_all"}
    """
    if auto_approve:
        return {"type": "approve"}
    
    tool_name = action_request.get("name", "unknown")
    tool_args = action_request.get("args", {})
    
    console.print()
    console.print(Panel(
        f"[bold yellow]>>> {tool_name} Requires Approval <<<[/bold yellow]\n\n"
        f"[dim]{format_tool_display(tool_name, tool_args)}[/dim]",
        border_style="yellow",
    ))
    console.print()
    console.print("[bold]Options:[/bold]")
    console.print("  [green]y[/green] - Approve")
    console.print("  [red]n[/red] - Reject")
    console.print("  [cyan]a[/cyan] - Auto-approve all this session")
    console.print()
    
    while True:
        try:
            choice = input("Your choice [y/n/a]: ").strip().lower()
            if choice in ("y", "yes", "1"):
                return {"type": "approve"}
            elif choice in ("n", "no", "2"):
                return {"type": "reject"}
            elif choice in ("a", "auto", "3"):
                return {"type": "auto_approve_all"}
            else:
                console.print("[dim]Please enter y, n, or a[/dim]")
        except (EOFError, KeyboardInterrupt):
            return {"type": "reject"}


async def run_rich_cli(
    agent: Any,
    assistant_id: str | None,
    backend: Any = None,
    auto_approve: bool = False,
    cwd: str | None = None,
    thread_id: str | None = None,
    initial_prompt: str | None = None,
) -> None:
    """Run the pure terminal CLI interface using Rich.
    
    Args:
        agent: The LangGraph agent to execute
        assistant_id: Agent identifier for memory storage
        backend: Backend for file operations
        auto_approve: Whether to auto-approve tool calls
        cwd: Current working directory
        thread_id: Thread ID for session persistence
        initial_prompt: Optional prompt to auto-submit
    """
    from pathlib import Path
    
    # Print welcome
    print_welcome()
    
    # Set up prompt session with history
    history_file = Path.home() / ".deepagents" / "history.txt"
    history_file.parent.mkdir(parents=True, exist_ok=True)
    
    session: PromptSession = PromptSession(
        history=FileHistory(str(history_file)),
        style=PROMPT_STYLE,
    )
    
    session_auto_approve = auto_approve
    
    # Handle initial prompt
    if initial_prompt and initial_prompt.strip():
        print_user_message(initial_prompt)
        await _execute_task_rich(
            user_input=initial_prompt,
            agent=agent,
            assistant_id=assistant_id,
            thread_id=thread_id,
            backend=backend,
            auto_approve_ref=[session_auto_approve],
        )
    
    # Main chat loop
    while True:
        try:
            # Get user input
            user_input = await session.prompt_async(
                [("class:prompt", "> ")],
                multiline=False,
            )
            
            if not user_input.strip():
                continue
            
            # Handle commands
            cmd = user_input.strip().lower()
            
            if cmd in ("/quit", "/exit", "/q"):
                console.print("[yellow]Goodbye![/yellow]")
                break
            elif cmd == "/clear":
                console.clear()
                print_welcome()
                continue
            elif cmd == "/help":
                console.print("[bold]Commands:[/bold]")
                console.print("  /quit, /exit, /q - Exit")
                console.print("  /clear - Clear screen")
                console.print("  /help - Show this help")
                console.print("  @ - File mention (autocomplete)")
                console.print("  ! - Run shell command")
                continue
            elif user_input.startswith("!"):
                # Shell command
                import subprocess
                cmd_str = user_input[1:].strip()
                console.print()  # Add spacing after prompt
                try:
                    result = subprocess.run(
                        cmd_str,
                        shell=True,
                        capture_output=True,
                        text=True,
                        cwd=cwd,
                        timeout=60,
                    )
                    if result.stdout:
                        console.print(Syntax(result.stdout, "text", theme="monokai"))
                    if result.stderr:
                        console.print(f"[red]{result.stderr}[/red]")
                    if result.returncode != 0:
                        console.print(f"[dim]Exit code: {result.returncode}[/dim]")
                except subprocess.TimeoutExpired:
                    print_error("Command timed out (60s)")
                except Exception as e:
                    print_error(str(e))
                continue
            
            # Normal message - send to agent
            # Note: Don't print user message again - prompt_toolkit already displayed it
            console.print()  # Just add a blank line for spacing
            
            await _execute_task_rich(
                user_input=user_input,
                agent=agent,
                assistant_id=assistant_id,
                thread_id=thread_id,
                backend=backend,
                auto_approve_ref=[session_auto_approve],
            )
            
        except (EOFError, KeyboardInterrupt):
            console.print("\n[yellow]Goodbye![/yellow]")
            break
        except Exception as e:
            print_error(str(e))


async def _execute_task_rich(
    user_input: str,
    agent: Any,
    assistant_id: str | None,
    thread_id: str | None,
    backend: Any = None,
    auto_approve_ref: list[bool] | None = None,
    image_tracker: ImageTracker | None = None,
) -> None:
    """Execute a task with output to Rich console.
    
    Args:
        user_input: The user's input message
        agent: The LangGraph agent
        assistant_id: Agent identifier
        thread_id: Thread ID for session
        backend: Backend for file operations
        auto_approve_ref: Mutable reference to auto-approve flag [bool]
        image_tracker: Optional image tracker
    """
    if auto_approve_ref is None:
        auto_approve_ref = [False]
    
    # Parse file mentions
    prompt_text, mentioned_files = parse_file_mentions(user_input)
    
    max_embed_bytes = 256 * 1024
    
    if mentioned_files:
        context_parts = [prompt_text, "\n\n## Referenced Files\n"]
        for file_path in mentioned_files:
            try:
                file_size = file_path.stat().st_size
                if file_size > max_embed_bytes:
                    size_kb = file_size // 1024
                    context_parts.append(
                        f"\n### {file_path.name}\n"
                        f"Path: `{file_path}`\n"
                        f"Size: {size_kb}KB (too large to embed)"
                    )
                else:
                    content = file_path.read_text()
                    context_parts.append(
                        f"\n### {file_path.name}\nPath: `{file_path}`\n```\n{content}\n```"
                    )
            except Exception as e:
                context_parts.append(f"\n### {file_path.name}\n[Error: {e}]")
        final_input = "\n".join(context_parts)
    else:
        final_input = prompt_text
    
    # Include images
    images_to_send = []
    if image_tracker:
        images_to_send = image_tracker.get_images()
    if images_to_send:
        message_content = create_multimodal_content(final_input, images_to_send)
    else:
        message_content = final_input
    
    config = {
        "configurable": {"thread_id": thread_id},
        "metadata": {
            "assistant_id": assistant_id,
            "agent_name": assistant_id,
            "updated_at": datetime.now(UTC).isoformat(),
        }
        if assistant_id
        else {},
    }
    
    file_op_tracker = FileOpTracker(assistant_id=assistant_id, backend=backend)
    displayed_tool_ids: set[str] = set()
    tool_call_buffers: dict[str | int, dict] = {}
    pending_text_by_namespace: dict[tuple, str] = {}
    
    if image_tracker:
        image_tracker.clear()
    
    stream_input: dict | Command = {"messages": [{"role": "user", "content": message_content}]}
    
    # Show thinking indicator
    with Progress(
        SpinnerColumn(),
        TextColumn("[dim]Thinking...[/dim]"),
        transient=True,
    ) as progress:
        progress.add_task("thinking", total=None)
        
        try:
            while True:
                interrupt_occurred = False
                hitl_response: dict[str, HITLResponse] = {}
                pending_interrupts: dict[str, HITLRequest] = {}
                
                # Stop progress when we start getting content
                first_content = True
                
                async for chunk in agent.astream(
                    stream_input,
                    stream_mode=["messages", "updates"],
                    subgraphs=True,
                    config=config,
                    durability="exit",
                ):
                    if not isinstance(chunk, tuple) or len(chunk) != 3:
                        continue
                    
                    namespace, current_stream_mode, data = chunk
                    ns_key = tuple(namespace) if namespace else ()
                    is_main_agent = ns_key == ()
                    
                    # Handle updates
                    if current_stream_mode == "updates":
                        if not isinstance(data, dict):
                            continue
                        
                        if "__interrupt__" in data:
                            interrupts: list[Interrupt] = data["__interrupt__"]
                            if interrupts:
                                for interrupt_obj in interrupts:
                                    try:
                                        validated = _HITL_REQUEST_ADAPTER.validate_python(
                                            interrupt_obj.value
                                        )
                                        pending_interrupts[interrupt_obj.id] = validated
                                        interrupt_occurred = True
                                    except ValidationError:
                                        raise
                    
                    # Handle messages
                    elif current_stream_mode == "messages":
                        if not is_main_agent:
                            continue
                        
                        if not isinstance(data, tuple) or len(data) != 2:
                            continue
                        
                        message, _metadata = data
                        
                        if _is_summarization_chunk(_metadata):
                            continue
                        
                        if isinstance(message, HumanMessage):
                            pending_text = pending_text_by_namespace.get(ns_key, "")
                            if pending_text:
                                if first_content:
                                    progress.stop()
                                    first_content = False
                                print_assistant_text(pending_text)
                                pending_text_by_namespace[ns_key] = ""
                            continue
                        
                        if isinstance(message, ToolMessage):
                            tool_name = getattr(message, "name", "")
                            tool_status = getattr(message, "status", "success")
                            tool_content = format_tool_message_content(message.content)
                            record = file_op_tracker.complete_with_message(message)
                            
                            print_tool_result(tool_name, tool_status, str(tool_content) if tool_content else None)
                            
                            if record and record.diff:
                                print_diff(record.diff, record.display_path)
                            continue
                        
                        if not hasattr(message, "content_blocks"):
                            continue
                        
                        for block in message.content_blocks:
                            block_type = block.get("type")
                            
                            if block_type == "text":
                                text = block.get("text", "")
                                if text:
                                    if first_content:
                                        progress.stop()
                                        first_content = False
                                    
                                    pending_text = pending_text_by_namespace.get(ns_key, "")
                                    pending_text += text
                                    pending_text_by_namespace[ns_key] = pending_text
                                    
                                    # Stream output character by character for smooth effect
                                    console.print(text, end="")
                            
                            elif block_type in ("tool_call_chunk", "tool_call"):
                                chunk_name = block.get("name")
                                chunk_args = block.get("args")
                                chunk_id = block.get("id")
                                chunk_index = block.get("index")
                                
                                buffer_key: str | int
                                if chunk_index is not None:
                                    buffer_key = chunk_index
                                elif chunk_id is not None:
                                    buffer_key = chunk_id
                                else:
                                    buffer_key = f"unknown-{len(tool_call_buffers)}"
                                
                                buffer = tool_call_buffers.setdefault(
                                    buffer_key,
                                    {"name": None, "id": None, "args": None, "args_parts": []},
                                )
                                
                                if chunk_name:
                                    buffer["name"] = chunk_name
                                if chunk_id:
                                    buffer["id"] = chunk_id
                                
                                if isinstance(chunk_args, dict):
                                    buffer["args"] = chunk_args
                                elif isinstance(chunk_args, str) and chunk_args:
                                    parts = buffer.setdefault("args_parts", [])
                                    if not parts or chunk_args != parts[-1]:
                                        parts.append(chunk_args)
                                    buffer["args"] = "".join(parts)
                                elif chunk_args is not None:
                                    buffer["args"] = chunk_args
                                
                                buffer_name = buffer.get("name")
                                buffer_id = buffer.get("id")
                                if buffer_name is None:
                                    continue
                                
                                parsed_args = buffer.get("args")
                                if isinstance(parsed_args, str):
                                    if not parsed_args:
                                        continue
                                    try:
                                        parsed_args = json.loads(parsed_args)
                                    except json.JSONDecodeError:
                                        continue
                                elif parsed_args is None:
                                    continue
                                
                                if not isinstance(parsed_args, dict):
                                    parsed_args = {"value": parsed_args}
                                
                                # Flush pending text
                                pending_text = pending_text_by_namespace.get(ns_key, "")
                                if pending_text:
                                    console.print()  # End streaming line
                                    pending_text_by_namespace[ns_key] = ""
                                
                                if buffer_id and buffer_id not in displayed_tool_ids:
                                    displayed_tool_ids.add(buffer_id)
                                    file_op_tracker.start_operation(buffer_name, parsed_args, buffer_id)
                                    
                                    if first_content:
                                        progress.stop()
                                        first_content = False
                                    
                                    print_tool_call(buffer_name, parsed_args)
                                
                                tool_call_buffers.pop(buffer_key, None)
                        
                        if getattr(message, "chunk_position", None) == "last":
                            pending_text = pending_text_by_namespace.get(ns_key, "")
                            if pending_text:
                                console.print()  # End streaming line
                                pending_text_by_namespace[ns_key] = ""
                
                # Flush remaining text
                for ns_key, pending_text in list(pending_text_by_namespace.items()):
                    if pending_text:
                        console.print()
                pending_text_by_namespace.clear()
                
                # Handle HITL
                if interrupt_occurred:
                    any_rejected = False
                    
                    for interrupt_id, hitl_request in pending_interrupts.items():
                        if auto_approve_ref[0]:
                            decisions = [{"type": "approve"} for _ in hitl_request["action_requests"]]
                            hitl_response[interrupt_id] = {"decisions": decisions}
                        else:
                            decisions = []
                            
                            for action_request in hitl_request["action_requests"]:
                                decision = prompt_approval(action_request, auto_approve_ref[0])
                                
                                if decision.get("type") == "auto_approve_all":
                                    auto_approve_ref[0] = True
                                    decisions.append({"type": "approve"})
                                    for _ in hitl_request["action_requests"][len(decisions):]:
                                        decisions.append({"type": "approve"})
                                    break
                                
                                decisions.append(decision)
                                
                                if decision.get("type") == "reject":
                                    any_rejected = True
                                    break
                            
                            hitl_response[interrupt_id] = {"decisions": decisions}
                            
                            if any_rejected:
                                break
                
                if interrupt_occurred and hitl_response:
                    if any_rejected:
                        print_system("Command rejected. Tell the agent what you'd like instead.")
                        return
                    
                    stream_input = Command(resume=hitl_response)
                else:
                    break
        
        except asyncio.CancelledError:
            print_system("Interrupted by user")
            return
        except KeyboardInterrupt:
            print_system("Interrupted by user")
            return
    
    console.print()  # Final newline

