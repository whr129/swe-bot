"""Orchestrator - plans, executes, and synthesizes multi-agent tasks."""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from openai import AsyncOpenAI

from agents.base import AgentResult, BaseAgent, _load_playbook
from services.memory import MemoryManager

logger = logging.getLogger("leetbot.orchestrator")


@dataclass
class SubTask:
    agent_name: str
    instruction: str
    depends_on: list[str] = field(default_factory=list)


@dataclass
class TaskPlan:
    agents: list[str]
    subtasks: list[SubTask]
    parallel: bool = True
    needs_synthesis: bool = False


PLAN_SCHEMA = {
    "type": "function",
    "function": {
        "name": "create_task_plan",
        "description": "Create a plan for which agents to use and how.",
        "parameters": {
            "type": "object",
            "properties": {
                "agents": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of agent names to invoke",
                },
                "parallel": {
                    "type": "boolean",
                    "description": "True if subtasks can run concurrently, false if they must be sequential",
                },
                "subtasks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "agent_name": {"type": "string"},
                            "instruction": {"type": "string", "description": "What this agent should do"},
                            "depends_on": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Agent names whose results this subtask needs",
                            },
                        },
                        "required": ["agent_name", "instruction"],
                    },
                },
                "needs_synthesis": {
                    "type": "boolean",
                    "description": "Whether multiple agent results need to be merged into one answer",
                },
            },
            "required": ["agents", "subtasks"],
        },
    },
}


class Orchestrator:
    """Multi-agent orchestrator: plan -> execute -> synthesize."""

    def __init__(
        self,
        agents: dict[str, BaseAgent],
        client: Optional[AsyncOpenAI],
        memory: MemoryManager,
        model: str = "gpt-4o-mini",
    ):
        self.agents = agents
        self.client = client
        self.memory = memory
        self.model = model
        self.system_prompt = _load_playbook("orchestrator")

        agent_caps = []
        for name, agent in agents.items():
            tools = [t["function"]["name"] for t in agent.tool_definitions]
            agent_caps.append(f"- **{name}**: tools = {tools}")
        self._agent_capabilities = "\n".join(agent_caps)

    def is_available(self) -> bool:
        return self.client is not None and any(a.is_available() for a in self.agents.values())

    async def _plan(
        self,
        query: str,
        discord_id: Optional[int] = None,
    ) -> TaskPlan:
        """Use the LLM to create a task plan."""
        if not self.client:
            return TaskPlan(
                agents=["leetcode"],
                subtasks=[SubTask(agent_name="leetcode", instruction=query)],
            )

        system = (
            f"{self.system_prompt}\n\n"
            f"## Agent Capabilities\n{self._agent_capabilities}\n\n"
            "Analyze the user's query and call the create_task_plan function. "
            "Choose the minimum set of agents needed. Most queries need only ONE agent."
        )

        if discord_id is not None:
            mem = self.memory.recall(discord_id, query=query)
            block = mem.to_prompt_block(discord_id)
            if block:
                system += block

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": query},
        ]

        try:
            resp = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=[PLAN_SCHEMA],
                tool_choice={"type": "function", "function": {"name": "create_task_plan"}},
                max_tokens=500,
                temperature=0,
            )
        except Exception as e:
            logger.error("Planning LLM call failed: %s", e)
            return self._fallback_plan(query)

        choice = resp.choices[0]
        if choice.message.tool_calls:
            try:
                args = json.loads(choice.message.tool_calls[0].function.arguments)
                return self._parse_plan(args, query)
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                logger.warning("Failed to parse plan: %s", e)

        return self._fallback_plan(query)

    def _parse_plan(self, args: dict, original_query: str) -> TaskPlan:
        agents = [a for a in args.get("agents", []) if a in self.agents]
        if not agents:
            return self._fallback_plan(original_query)

        subtasks = []
        for st in args.get("subtasks", []):
            name = st.get("agent_name", "")
            if name not in self.agents:
                continue
            subtasks.append(SubTask(
                agent_name=name,
                instruction=st.get("instruction", original_query),
                depends_on=[d for d in st.get("depends_on", []) if d in self.agents],
            ))

        if not subtasks:
            subtasks = [SubTask(agent_name=agents[0], instruction=original_query)]

        parallel = args.get("parallel", len(subtasks) > 1)
        needs_synthesis = args.get("needs_synthesis", len(subtasks) > 1)

        return TaskPlan(
            agents=agents,
            subtasks=subtasks,
            parallel=parallel,
            needs_synthesis=needs_synthesis,
        )

    def _fallback_plan(self, query: str) -> TaskPlan:
        """Keyword-based fallback when the LLM planner fails."""
        lower = query.lower()
        agent_name = "leetcode"

        stock_kw = {"stock", "price", "quote", "ticker", "market", "share", "portfolio"}
        news_kw = {"news", "headline", "briefing", "latest", "breaking"}
        alert_kw = {"alert", "remind", "reminder", "notify", "deadline"}

        words = set(lower.split())
        if words & alert_kw:
            agent_name = "alerts"
        elif words & stock_kw or "$" in query:
            agent_name = "stock"
        elif words & news_kw:
            agent_name = "news"

        return TaskPlan(
            agents=[agent_name],
            subtasks=[SubTask(agent_name=agent_name, instruction=query)],
        )

    async def _execute(
        self,
        plan: TaskPlan,
        original_query: str,
        discord_id: Optional[int] = None,
    ) -> dict[str, AgentResult]:
        """Execute the task plan and return per-agent results."""
        results: dict[str, AgentResult] = {}

        if plan.parallel and not any(st.depends_on for st in plan.subtasks):
            coros = []
            for st in plan.subtasks:
                agent = self.agents[st.agent_name]
                coros.append(
                    agent.run(
                        user_message=st.instruction,
                        discord_id=discord_id,
                    )
                )
            agent_results = await asyncio.gather(*coros, return_exceptions=True)
            for st, result in zip(plan.subtasks, agent_results):
                if isinstance(result, Exception):
                    logger.error("Agent %s failed: %s", st.agent_name, result)
                    results[st.agent_name] = AgentResult(
                        answer=f"Error: {result}",
                        agent_name=st.agent_name,
                    )
                else:
                    results[st.agent_name] = result
        else:
            for st in plan.subtasks:
                peer_ctx = {
                    dep: results[dep]
                    for dep in st.depends_on
                    if dep in results
                } or None

                agent = self.agents[st.agent_name]
                try:
                    result = await agent.run(
                        user_message=st.instruction,
                        discord_id=discord_id,
                        peer_context=peer_ctx,
                    )
                except Exception as e:
                    logger.error("Agent %s failed: %s", st.agent_name, e)
                    result = AgentResult(answer=f"Error: {e}", agent_name=st.agent_name)
                results[st.agent_name] = result

        return results

    async def _synthesize(
        self,
        query: str,
        results: dict[str, AgentResult],
    ) -> str:
        """Merge multiple agent results into a single coherent answer."""
        if not self.client:
            return "\n\n".join(r.answer for r in results.values())

        agent_outputs = []
        for name, result in results.items():
            agent_outputs.append(f"[{name} agent]:\n{result.answer}")

        system = (
            "You are a synthesis assistant. Combine the following agent outputs into a "
            "single coherent response for the user. Keep it concise (under 1800 chars), "
            "use Markdown formatting, and don't repeat information."
        )

        messages = [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": (
                    f"Original query: {query}\n\n"
                    + "\n\n".join(agent_outputs)
                    + "\n\nSynthesize these into one response."
                ),
            },
        ]

        try:
            resp = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=1500,
            )
            return resp.choices[0].message.content or ""
        except Exception as e:
            logger.error("Synthesis LLM call failed: %s", e)
            return "\n\n".join(r.answer for r in results.values())

    async def run(
        self,
        query: str,
        discord_id: Optional[int] = None,
    ) -> AgentResult:
        """Full orchestration pipeline: plan -> execute -> synthesize."""
        plan = await self._plan(query, discord_id)
        logger.info(
            "Plan: agents=%s, parallel=%s, synthesis=%s",
            plan.agents, plan.parallel, plan.needs_synthesis,
        )

        results = await self._execute(plan, query, discord_id)

        if len(results) == 1:
            single = next(iter(results.values()))
            return AgentResult(
                answer=single.answer,
                agent_name=single.agent_name,
                tool_calls_made=single.tool_calls_made,
                iterations=single.iterations,
                raw_data=single.raw_data,
            )

        synthesized = await self._synthesize(query, results)

        all_tool_calls = []
        total_iterations = 0
        agent_names = []
        for name, result in results.items():
            agent_names.append(name)
            all_tool_calls.extend(result.tool_calls_made)
            total_iterations = max(total_iterations, result.iterations)

        return AgentResult(
            answer=synthesized,
            agent_name="+".join(agent_names),
            tool_calls_made=all_tool_calls,
            iterations=total_iterations,
        )
