"""AI cog: /ask command with multi-agent orchestration."""

import discord
from discord.ext import commands

from bot.utils.embeds import error_embed

AGENT_COLORS = {
    "leetcode": discord.Color.green(),
    "stock": discord.Color.gold(),
    "news": discord.Color.blue(),
    "alerts": discord.Color.purple(),
}


class AICog(commands.Cog):
    """AI-powered assistance via multi-agent orchestration."""

    def __init__(self, bot: discord.Bot):
        self.bot = bot

    def _get_orchestrator(self):
        return getattr(self.bot, "orchestrator", None)

    @discord.slash_command(
        name="ask",
        description="Ask the AI anything (LeetCode, stocks, news, alerts...)",
    )
    async def ask(
        self,
        ctx: discord.ApplicationContext,
        question: discord.Option(str, description="Your question or request"),
    ) -> None:
        await ctx.defer()

        orchestrator = self._get_orchestrator()
        if not orchestrator or not orchestrator.is_available():
            await ctx.respond(embed=error_embed("AI is not configured. Set OPENAI_API_KEY in .env"))
            return

        result = await orchestrator.run(query=question, discord_id=ctx.author.id)

        answer = result.answer
        if len(answer) > 1900:
            answer = answer[:1900] + "..."

        footer_parts = [f"Agent: {result.agent_name}"]
        if result.tool_calls_made:
            tool_names = list(dict.fromkeys(tc["tool"] for tc in result.tool_calls_made))
            footer_parts.append(f"Tools: {', '.join(tool_names)}")
        footer_parts.append(f"Steps: {result.iterations}")

        primary_agent = result.agent_name.split("+")[0]
        color = AGENT_COLORS.get(primary_agent, discord.Color.blurple())
        embed = discord.Embed(description=answer, color=color)
        embed.set_footer(text=" | ".join(footer_parts))
        await ctx.respond(embed=embed)


def setup(bot: discord.Bot) -> None:
    """Load the AI cog and initialize the multi-agent orchestrator."""
    from openai import AsyncOpenAI

    import config
    from agents.leetcode import LeetCodeAgent
    from agents.stock import StockAgent
    from agents.news import NewsAgent
    from agents.alerts import AlertAgent
    from agents.orchestrator import Orchestrator
    from services.memory import MemoryManager

    client = AsyncOpenAI(api_key=config.OPENAI_API_KEY) if config.OPENAI_API_KEY else None

    memory = MemoryManager(
        persist_dir=config.CHROMA_PERSIST_DIR,
        openai_api_key=config.OPENAI_API_KEY or None,
        embedding_model=config.EMBEDDING_MODEL,
        short_term_ttl_days=config.MEMORY_SHORT_TERM_TTL_DAYS,
        recall_limit=config.MEMORY_RECALL_LIMIT,
    )

    agents = {
        "leetcode": LeetCodeAgent(
            client=client,
            memory=memory,
            leetcode=bot.leetcode,
            model=config.AI_MODEL,
            max_iterations=config.AGENT_MAX_ITERATIONS,
        ),
        "stock": StockAgent(
            client=client,
            memory=memory,
            stock_service=bot.stock_service,
            model=config.AI_MODEL,
            max_iterations=config.AGENT_MAX_ITERATIONS,
        ),
        "news": NewsAgent(
            client=client,
            memory=memory,
            news_service=bot.news_service,
            model=config.AI_MODEL,
            max_iterations=config.AGENT_MAX_ITERATIONS,
        ),
        "alerts": AlertAgent(
            client=client,
            memory=memory,
            alert_service=bot.alert_service,
            model=config.AI_MODEL,
            max_iterations=config.AGENT_MAX_ITERATIONS,
        ),
    }

    bot.orchestrator = Orchestrator(
        agents=agents,
        client=client,
        memory=memory,
        model=config.AI_MODEL,
    )
    bot.add_cog(AICog(bot))
