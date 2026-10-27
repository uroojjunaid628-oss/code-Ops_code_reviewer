import json
from collections.abc import Callable
from typing import Any

from langchain_core.messages import AIMessage, ToolMessage

# Mapping of tool name to callable
ToolRegistry = dict[str, Callable[..., Any]]


def execute_agent(
    llm,  # LangChain LLM with bound tools
    messages: list[Any],
    allowed_tools: ToolRegistry,
    max_rounds: int = 5,
) -> Any:
    """Run a bounded tool‑calling loop.

    Parameters
    ----------
    llm: the LangChain LLM (already bound to the desired tools).
    messages: initial message list (SystemMessage + HumanMessage).
    allowed_tools: dict mapping allowed tool names to callables.
    max_rounds: maximum number of tool‑call iterations.

    Returns
    -------
    The final AIMessage returned by the model after no more tool calls.
    """
    for _ in range(max_rounds):
        # Invoke the model
        response: AIMessage = llm.invoke(messages)  # type: ignore[arg-type]

        # If the model returned tool calls, execute them
        if getattr(response, "tool_calls", None):
            messages.append(response)
            for tool_call in response.tool_calls:
                name = tool_call.get("name")
                args = tool_call.get("args", {})
                if name not in allowed_tools:
                    raise ValueError(f"Tool '{name}' is not permitted for this agent")
                # Execute the tool safely
                tool_obj = allowed_tools[name]
                if hasattr(tool_obj, "invoke"):
                    result = tool_obj.invoke(args)
                elif callable(tool_obj):
                    result = tool_obj(**args)
                else:
                    raise TypeError(f"Tool '{name}' cannot be invoked")
                tool_call_id = tool_call.get("id") or f"call_{name}"
                # Append a ToolMessage so the model sees the result
                messages.append(
                    ToolMessage(
                        content=json.dumps(result),
                        name=name,
                        tool_call_id=tool_call_id,
                    )
                )
            # Continue loop – the next model turn will have the tool results in context
            continue
        # No tool calls – we are done
        return response
    # If we exceed max rounds, raise
    raise RuntimeError("Exceeded maximum tool-calling rounds without reaching a final answer")
