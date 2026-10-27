"""Tests verifying on-demand tool execution by agents."""

import json
from pathlib import Path
from unittest.mock import Mock

from langchain_core.messages import AIMessage

from reviewer.services.tool_executor import execute_agent
from reviewer.services.tools import (
    existing_test_inspection,
    get_active_workspace,
    inspect_source,
    reset_active_workspace,
    run_bandit,
    run_ruff,
    set_active_workspace,
)


def test_active_workspace_context(tmp_path: Path) -> None:
    test_dir = tmp_path / "my_project"
    test_dir.mkdir()

    assert get_active_workspace() != test_dir
    set_active_workspace(test_dir)
    assert get_active_workspace() == test_dir
    set_active_workspace(None)
    assert get_active_workspace() != test_dir


def test_active_workspace_token_reset(tmp_path: Path) -> None:
    dir1 = tmp_path / "workspace_one"
    dir2 = tmp_path / "workspace_two"
    dir1.mkdir()
    dir2.mkdir()

    token1 = set_active_workspace(dir1)
    assert get_active_workspace() == dir1

    token2 = set_active_workspace(dir2)
    assert get_active_workspace() == dir2

    reset_active_workspace(token2)
    assert get_active_workspace() == dir1

    reset_active_workspace(token1)
    assert get_active_workspace() != dir1


def test_active_workspace_separate_contexts_isolated(tmp_path: Path) -> None:
    """Verify that concurrent threads/contexts do not overwrite each other's workspace."""
    import concurrent.futures
    import time

    dir_a = tmp_path / "project_a"
    dir_b = tmp_path / "project_b"
    dir_a.mkdir()
    dir_b.mkdir()

    def run_worker_a() -> list[Path]:
        results: list[Path] = []
        token = set_active_workspace(dir_a)
        try:
            results.append(get_active_workspace())
            time.sleep(0.05)
            results.append(get_active_workspace())
        finally:
            reset_active_workspace(token)
        results.append(get_active_workspace())
        return results

    def run_worker_b() -> list[Path]:
        results: list[Path] = []
        time.sleep(0.02)  # Start slightly after worker A
        token = set_active_workspace(dir_b)
        try:
            results.append(get_active_workspace())
            time.sleep(0.05)
            results.append(get_active_workspace())
        finally:
            reset_active_workspace(token)
        results.append(get_active_workspace())
        return results

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        future_a = executor.submit(run_worker_a)
        future_b = executor.submit(run_worker_b)

        results_a = future_a.result()
        results_b = future_b.result()

    # Context A must have seen dir_a during its run, and reverted afterwards
    assert results_a[0] == dir_a
    assert results_a[1] == dir_a
    assert results_a[2] != dir_a

    # Context B must have seen dir_b during its run, completely isolated from Context A
    assert results_b[0] == dir_b
    assert results_b[1] == dir_b
    assert results_b[2] != dir_b



def test_execute_agent_tool_calling_loop() -> None:
    """Verify tool_executor handles tool calls from LLM and feeds results back."""
    mock_llm = Mock()

    # Turn 1: LLM decides to call inspect_source tool
    tool_call_msg = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "inspect_source",
                "args": {"file_path": "test.py", "source_code": "import sys\nx = 1"},
                "id": "call_123",
            }
        ],
    )
    # Turn 2: LLM receives tool response and produces final analysis answer
    final_msg = AIMessage(
        content=json.dumps({"findings": []}),
    )

    mock_llm.invoke.side_effect = [tool_call_msg, final_msg]

    messages = [{"role": "system", "content": "You are an agent."}]
    allowed_tools = {
        "inspect_source": inspect_source,
        "run_ruff": run_ruff,
        "run_bandit": run_bandit,
        "existing_test_inspection": existing_test_inspection,
    }

    result = execute_agent(
        llm=mock_llm,
        messages=messages,
        allowed_tools=allowed_tools,
        max_rounds=3,
    )

    assert result == final_msg
    assert mock_llm.invoke.call_count == 2
    # Verify the tool result was added as a ToolMessage with tool_call_id
    tool_messages = [m for m in messages if getattr(m, "tool_call_id", None) == "call_123"]
    assert len(tool_messages) == 1
    tool_data = json.loads(tool_messages[0].content)
    assert tool_data["file_path"] == "test.py"
    assert tool_data["import_count"] == 1
