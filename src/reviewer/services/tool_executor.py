import json
import logging
from typing import Any

from langchain_core.messages import AIMessage, ToolMessage

logger = logging.getLogger(__name__)

MAX_ROUNDS = 5
MAX_TOOL_ITEMS = 15
MAX_STRING_LENGTH = 1200
MAX_DICT_KEYS = 30


def _limit_tool_result(value: Any) -> Any:
    """Reduce tool output size before adding it to the LLM conversation."""
    if isinstance(value, dict):
        limited = {}
        items = list(value.items())

        for key, item in items[:MAX_DICT_KEYS]:
            limited[str(key)] = _limit_tool_result(item)

        if len(items) > MAX_DICT_KEYS:
            limited["_omitted_keys"] = len(items) - MAX_DICT_KEYS

        return limited

    if isinstance(value, list):
        limited_items = [
            _limit_tool_result(item)
            for item in value[:MAX_TOOL_ITEMS]
        ]

        if len(value) > MAX_TOOL_ITEMS:
            limited_items.append(
                f"... {len(value) - MAX_TOOL_ITEMS} additional items omitted"
            )

        return limited_items

    if isinstance(value, str) and len(value) > MAX_STRING_LENGTH:
        return value[:MAX_STRING_LENGTH] + "... [text truncated]"

    return value


def _serialize_tool_result(result: Any) -> str:
    """Serialize a bounded tool result for a LangChain ToolMessage."""
    limited_result = _limit_tool_result(result)

    try:
        return json.dumps(
            limited_result,
            ensure_ascii=False,
            default=str,
        )
    except (TypeError, ValueError):
        logger.exception("Could not serialize tool output")
        return json.dumps(
            {"error": "Tool output could not be serialized"}
        )


def execute_agent(
    llm: Any,
    messages: list[Any],
    allowed_tools: list[Any] | dict[str, Any],
    max_rounds: int = MAX_ROUNDS,
) -> AIMessage:
    """Run an agent's LLM and tool-calling loop with bounded tool outputs."""
    if isinstance(allowed_tools, dict):
        tools_by_name = allowed_tools
    else:
        tools_by_name = {
            tool.name: tool
            for tool in allowed_tools
        }

    for round_number in range(max_rounds):
        response: AIMessage = llm.invoke(messages)
        messages.append(response)

        tool_calls = response.tool_calls

        if not tool_calls:
            return response

        logger.debug(
            "Executing %s tool calls in round %s",
            len(tool_calls),
            round_number + 1,
        )

        for tool_call in tool_calls:
            tool_name = tool_call["name"]
            tool_call_id = tool_call["id"]
            tool = tools_by_name.get(tool_name)

            if tool is None:
                logger.warning(
                    "Agent requested an unknown tool: %s",
                    tool_name,
                )
                result = {"error": f"Unknown tool: {tool_name}"}
            else:
                try:
                    result = tool.invoke(tool_call.get("args", {}))
                except Exception:
                    logger.exception(
                        "Tool execution failed: %s",
                        tool_name,
                    )
                    result = {
                        "error": f"Tool {tool_name} failed during execution"
                    }

            messages.append(
                ToolMessage(
                    content=_serialize_tool_result(result),
                    name=tool_name,
                    tool_call_id=tool_call_id,
                )
            )

    # Give the model one final opportunity to answer after the tool rounds.
    final_response: AIMessage = llm.invoke(messages)
    messages.append(final_response)

    if final_response.tool_calls:
        logger.warning(
            "Agent requested more tools after reaching the round limit"
        )

    return final_response
