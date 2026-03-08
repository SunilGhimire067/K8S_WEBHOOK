import asyncio
import json
import logging
import queue as thread_queue
from pathlib import Path
from typing import AsyncGenerator

import yaml

from .llm_client import get_model, get_openai_client
from .tool_executor import execute_tool
from .tool_registry import TOOL_DEFINITIONS

logger = logging.getLogger("chat-handler")

_BACKEND_DIR = Path(__file__).resolve().parent


def _load_system_prompt() -> str:
    return (_BACKEND_DIR / "system_prompt.md").read_text()


def _load_skills() -> dict:
    return yaml.safe_load((_BACKEND_DIR / "skills.yaml").read_text())


SYSTEM_PROMPT = _load_system_prompt()
SKILLS = _load_skills()

MAX_TOOL_ROUNDS = 10


def reload_config():
    """Reload system prompt and skills from disk (call after editing files)."""
    global SYSTEM_PROMPT, SKILLS
    SYSTEM_PROMPT = _load_system_prompt()
    SKILLS = _load_skills()
    logger.info("Reloaded system_prompt.md and skills.yaml")


def _expand_skill(messages: list[dict]) -> list[dict]:
    """If the last user message matches a skill, replace it with the full prompt."""
    if not messages:
        return messages
    last = messages[-1]
    if last.get("role") != "user":
        return messages
    content = last["content"]
    for skill in SKILLS.values():
        trigger = f"[{skill['label']}]"
        if content.startswith(trigger):
            expanded = messages.copy()
            expanded[-1] = {**last, "content": skill["prompt"]}
            return expanded
    return messages


async def handle_chat(messages: list[dict]) -> dict:
    """Non-streaming fallback — returns all messages at once."""
    new_messages: list[dict] = []
    async for event in handle_chat_stream(messages):
        if event["type"] == "message":
            new_messages.append(event["data"])
    return {"new_messages": new_messages}


async def _stream_llm(client, model, messages, tools) -> AsyncGenerator[dict, None]:
    """Stream an LLM call, yielding token/tool_call delta events.

    Uses a thread-safe queue so the synchronous OpenAI stream iterator runs in
    a background thread while the async generator drains events without blocking
    the event loop.
    """
    q: thread_queue.Queue = thread_queue.Queue()

    def _run_sync():
        """Runs in a background thread — iterates the sync stream and pushes chunks."""
        try:
            stream = client.chat.completions.create(
                model=model,
                messages=messages,
                tools=tools,
                tool_choice="auto",
                stream=True,
            )
            for chunk in stream:
                q.put(chunk)
        except Exception as exc:
            q.put(exc)
        finally:
            q.put(None)  # sentinel = done

    # Start the sync stream reader in a background thread
    loop = asyncio.get_event_loop()
    fut = loop.run_in_executor(None, _run_sync)

    content_buf = ""
    tool_calls_buf: dict[int, dict] = {}
    token_count = 0

    while True:
        # Drain from the thread-safe queue; use to_thread for the blocking get
        item = await asyncio.to_thread(q.get)

        if item is None:
            break  # stream finished
        if isinstance(item, Exception):
            raise item

        chunk = item
        delta = chunk.choices[0].delta if chunk.choices else None
        if delta is None:
            continue

        # Content token
        if delta.content:
            content_buf += delta.content
            token_count += 1
            yield {"type": "token", "content": delta.content}

        # Tool call deltas
        if delta.tool_calls:
            for tc_delta in delta.tool_calls:
                idx = tc_delta.index
                if idx not in tool_calls_buf:
                    tool_calls_buf[idx] = {"id": "", "name": "", "arguments": ""}
                entry = tool_calls_buf[idx]
                if tc_delta.id:
                    entry["id"] = tc_delta.id
                if tc_delta.function:
                    if tc_delta.function.name:
                        entry["name"] += tc_delta.function.name
                    if tc_delta.function.arguments:
                        entry["arguments"] += tc_delta.function.arguments

    # Wait for the background thread to finish
    await fut

    logger.info("Streamed %d content tokens", token_count)

    # Build final tool_calls list (sorted by index)
    final_tool_calls = None
    if tool_calls_buf:
        final_tool_calls = [
            {
                "id": tool_calls_buf[i]["id"],
                "type": "function",
                "function": {
                    "name": tool_calls_buf[i]["name"],
                    "arguments": tool_calls_buf[i]["arguments"],
                },
            }
            for i in sorted(tool_calls_buf)
        ]

    # Yield the complete assistant message for history
    msg_dict: dict = {"role": "assistant", "content": content_buf}
    if final_tool_calls:
        msg_dict["tool_calls"] = final_tool_calls
    yield {"type": "message", "data": msg_dict}


async def handle_chat_stream(messages: list[dict]) -> AsyncGenerator[dict, None]:
    """Streaming chat handler — yields SSE events: progress, token, tool_start, message, done."""
    client = get_openai_client()
    model = get_model()

    messages = _expand_skill(messages)
    full_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + messages

    for round_num in range(MAX_TOOL_ROUNDS):
        yield {"type": "progress", "level": "info", "message": "Thinking..."}

        try:
            assistant_msg = None
            async for event in _stream_llm(client, model, full_messages, TOOL_DEFINITIONS):
                if event["type"] == "message":
                    assistant_msg = event["data"]
                else:
                    yield event  # token events
        except Exception as e:
            logger.error("LLM API call failed: %s", e)
            error_msg = f"Failed to connect to LLM server ({model}): {e}"
            yield {"type": "message", "data": {"role": "assistant", "content": error_msg}}
            return

        if assistant_msg is None:
            yield {"type": "message", "data": {"role": "assistant", "content": "No response from LLM."}}
            return

        # Yield the full assistant message (for history tracking on the frontend)
        yield {"type": "message", "data": assistant_msg}
        full_messages.append(assistant_msg)

        if "tool_calls" not in assistant_msg:
            break

        for tool_call in assistant_msg["tool_calls"]:
            fn_name = tool_call["function"]["name"]
            try:
                fn_args = json.loads(tool_call["function"]["arguments"])
            except json.JSONDecodeError:
                fn_args = {}

            yield {"type": "tool_start", "tool": fn_name, "args": fn_args}

            # Create a queue so the tool can push progress events to us
            progress_queue: asyncio.Queue = asyncio.Queue()

            # Run tool and drain progress events concurrently
            async def _run_tool(_name=fn_name, _args=fn_args):
                return await execute_tool(_name, _args, queue=progress_queue)

            task = asyncio.create_task(_run_tool())

            # Drain progress events while the tool runs
            while not task.done():
                try:
                    event = await asyncio.wait_for(progress_queue.get(), timeout=0.1)
                    yield event
                except asyncio.TimeoutError:
                    continue

            result = await task

            # Drain any remaining events
            while not progress_queue.empty():
                yield await progress_queue.get()

            tool_msg = {
                "role": "tool",
                "tool_call_id": tool_call["id"],
                "content": result,
            }
            yield {"type": "message", "data": tool_msg}
            full_messages.append(tool_msg)

    yield {"type": "done"}
