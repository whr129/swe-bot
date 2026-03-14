"""BaseAgent - reusable ReAct loop with playbook-driven prompts and RAG memory."""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Coroutine, Optional

from openai import AsyncOpenAI

from services.memory import MemoryManager

logger = logging.getLogger("leetbot.agent")

PLAYBOOK_DIR = Path(__file__).parent / "playbooks"


@dataclass
class AgentResult:
    """Result from a ReAct agent run."""

    answer: str
    agent_name: str = ""
    tool_calls_made: list[dict] = field(default_factory=list)
    iterations: int = 0
    raw_data: dict = field(default_factory=dict)


ToolHandler = Callable[..., Coroutine[Any, Any, Any]]


def _load_playbook(name: str) -> str:
    """Load _base.md + agent-specific playbook and return the combined prompt."""
    base_path = PLAYBOOK_DIR / "_base.md"
    agent_path = PLAYBOOK_DIR / f"{name}.md"

    parts: list[str] = []
    if base_path.exists():
        parts.append(base_path.read_text(encoding="utf-8").strip())
    if agent_path.exists():
        parts.append(agent_path.read_text(encoding="utf-8").strip())

    return "\n\n".join(parts) if parts else "You are a helpful assistant."


class BaseAgent:
    """Domain-specific ReAct agent with playbook-driven prompts and RAG memory.

    Subclasses set ``name`` and ``tool_definitions``, and implement
    ``execute_tool`` to dispatch tool calls to their service layer.
    The system prompt is loaded from ``agents/playbooks/{name}.md``.
    """

    name: str = "base"
    tool_definitions: list[dict] = []

    MEMORY_TOOL_DEFINITIONS: list[dict] = [
        {
            "type": "function",
            "function": {
                "name": "recall_memory",
                "description": "Retrieve semantically relevant past conversations and saved facts for this user.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "user_id": {
                            "type": "integer",
                            "description": "The Discord user ID",
                        },
                    },
                    "required": ["user_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "save_preference",
                "description": "Save a user preference for future reference (e.g. watchlist, username, preferred topics).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "user_id": {
                            "type": "integer",
                            "description": "The Discord user ID",
                        },
                        "key": {
                            "type": "string",
                            "description": "Preference key, e.g. 'watchlist', 'username'",
                        },
                        "value": {
                            "description": "Preference value (string, number, list, etc.)",
                        },
                    },
                    "required": ["user_id", "key", "value"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "save_fact",
                "description": "Save an important fact or insight to long-term memory for future reference.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "user_id": {
                            "type": "integer",
                            "description": "The Discord user ID",
                        },
                        "fact": {
                            "type": "string",
                            "description": "The fact or insight to remember",
                        },
                        "importance": {
                            "type": "string",
                            "enum": ["low", "normal", "high"],
                            "description": "How important this fact is (default: normal)",
                        },
                    },
                    "required": ["user_id", "fact"],
                },
            },
        },
    ]

    def __init__(
        self,
        client: Optional[AsyncOpenAI],
        memory: MemoryManager,
        model: str = "gpt-4o-mini",
        max_iterations: int = 8,
    ):
        self.client = client
        self.memory = memory
        self.model = model
        self.max_iterations = max_iterations
        self.system_prompt = _load_playbook(self.name)

    def is_available(self) -> bool:
        return self.client is not None

    def get_all_tool_definitions(self) -> list[dict]:
        return self.tool_definitions + self.MEMORY_TOOL_DEFINITIONS

    async def execute_tool(self, name: str, args: dict) -> Any:
        """Override in subclass to dispatch domain-specific tools."""
        raise NotImplementedError

    async def _dispatch_tool(self, name: str, args: dict, user_message: str) -> str:
        try:
            if name == "recall_memory":
                ctx = self.memory.recall(
                    args["user_id"], query=user_message, agent_name=self.name,
                )
                result = {
                    "recent_conversations": ctx.recent_conversations,
                    "relevant_facts": ctx.relevant_facts,
                    "preferences": ctx.preferences,
                    "shared_context": ctx.shared_context,
                }
            elif name == "save_preference":
                self.memory.save_preference(args["user_id"], args["key"], args["value"])
                result = {"status": "saved", "key": args["key"]}
            elif name == "save_fact":
                self.memory.save_fact(
                    args["user_id"],
                    args["fact"],
                    agent_name=self.name,
                    importance=args.get("importance", "normal"),
                )
                result = {"status": "saved", "fact": args["fact"]}
            else:
                result = await self.execute_tool(name, args)
            return json.dumps(result, default=str, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": f"{type(e).__name__}: {e}"})

    async def run(
        self,
        user_message: str,
        discord_id: Optional[int] = None,
        context: Optional[str] = None,
        peer_context: Optional[dict[str, "AgentResult"]] = None,
    ) -> AgentResult:
        if not self.client:
            return AgentResult(
                answer="AI is not configured. Set OPENAI_API_KEY in your .env file.",
                agent_name=self.name,
            )

        system_content = self.system_prompt
        if discord_id is not None:
            mem = self.memory.recall(discord_id, query=user_message, agent_name=self.name)
            memory_block = mem.to_prompt_block(discord_id)
            if memory_block:
                system_content += memory_block

        if peer_context:
            peer_block = "\n\n[Results from other agents]:\n"
            for agent_name, result in peer_context.items():
                peer_block += f"- {agent_name}: {result.answer[:500]}\n"
            system_content += peer_block

        messages: list[dict] = [{"role": "system", "content": system_content}]
        user_content = f"{context}\n\n{user_message}" if context else user_message
        messages.append({"role": "user", "content": user_content})

        tools = self.get_all_tool_definitions()
        tool_calls_log: list[dict] = []

        for iteration in range(1, self.max_iterations + 1):
            try:
                resp = await self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=tools,
                    max_tokens=1500,
                )
            except Exception as e:
                logger.error("[%s] LLM call failed on iteration %d: %s", self.name, iteration, e)
                return AgentResult(
                    answer=f"AI error: {e}",
                    agent_name=self.name,
                    tool_calls_made=tool_calls_log,
                    iterations=iteration,
                )

            choice = resp.choices[0]

            if choice.finish_reason == "stop" or not choice.message.tool_calls:
                answer = choice.message.content or "I couldn't generate a response."
                if discord_id is not None:
                    self.memory.add_conversation(
                        discord_id, user_message, answer, agent_name=self.name,
                    )
                return AgentResult(
                    answer=answer,
                    agent_name=self.name,
                    tool_calls_made=tool_calls_log,
                    iterations=iteration,
                )

            messages.append(choice.message)

            for tool_call in choice.message.tool_calls:
                fn_name = tool_call.function.name
                try:
                    fn_args = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    fn_args = {}

                logger.info("[%s] Tool call [%d]: %s(%s)", self.name, iteration, fn_name, fn_args)
                result = await self._dispatch_tool(fn_name, fn_args, user_message)

                tool_calls_log.append({
                    "tool": fn_name,
                    "args": fn_args,
                    "iteration": iteration,
                })
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                })

        return AgentResult(
            answer="I ran out of steps trying to answer. Please try a simpler question.",
            agent_name=self.name,
            tool_calls_made=tool_calls_log,
            iterations=self.max_iterations,
        )
