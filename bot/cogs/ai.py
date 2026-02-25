"""AI commands: ask, search, generate."""

from typing import Optional

import discord
from discord.ext import commands
from discord.commands import SlashCommandGroup

from bot.utils.embeds import error_embed, problem_embed
from services.leetcode import LeetCodeAPIError


class AICog(commands.Cog):
    """AI-powered LeetCode assistance."""

    ai_group = SlashCommandGroup("ai", "AI LeetCode assistant commands")

    def __init__(self, bot: discord.Bot):
        self.bot = bot

    def _get_ai_service(self):
        """Get AI service from bot."""
        return getattr(self.bot, "ai_service", None)

    @ai_group.command(name="ask", description="Ask AI about LeetCode (concepts, solutions, hints)")
    async def ask(
        self,
        ctx: discord.ApplicationContext,
        question: discord.Option(str, description="Your question"),
        problem_slug: discord.Option(str, description="Problem slug for context (optional)", required=False) = None,
    ) -> None:
        """Ask the AI a LeetCode question."""
        await ctx.defer()
        ai = self._get_ai_service()
        if not ai or not ai.is_available():
            await ctx.respond(embed=error_embed("AI is not configured. Set OPENAI_API_KEY in .env"))
            return

        problem_context = None
        if problem_slug:
            try:
                prob = await self.bot.leetcode.get_problem(problem_slug)
                problem_context = f"Title: {prob.title}\nDifficulty: {prob.difficulty}\nContent: {prob.content[:2000] if prob.content else ''}"
            except LeetCodeAPIError:
                pass

        reply = await ai.ask(question, problem_context)
        if len(reply) > 1900:
            reply = reply[:1900] + "..."
        await ctx.respond(reply)

    @ai_group.command(name="search", description="Search LeetCode problems using natural language")
    async def search(
        self,
        ctx: discord.ApplicationContext,
        query: discord.Option(str, description='e.g. "DP problems about knapsack"'),
    ) -> None:
        """Search problems via natural language."""
        await ctx.defer()
        ai = self._get_ai_service()
        if not ai:
            await ctx.respond(embed=error_embed("AI service not available"))
            return

        difficulty, tag_slug, problems = await ai.search_problems(query)
        if not problems:
            await ctx.respond(embed=error_embed("No problems found matching your query."))
            return

        results = problems[:5]
        lines = []
        for p in results:
            title = p.get("title", "Unknown")
            slug = p.get("title_slug", p.get("titleSlug", ""))
            diff = p.get("difficulty", "?")
            url = p.get("url", f"https://leetcode.com/problems/{slug}/")
            lines.append(f"• [{title}]({url}) ({diff})")
        body = "\n".join(lines)
        if len(body) > 1500:
            body = body[:1500] + "..."
        embed = discord.Embed(
            title="Search Results",
            description=body,
            color=discord.Color.blue(),
        )
        filters = []
        if difficulty:
            filters.append(f"Difficulty: {difficulty}")
        if tag_slug:
            filters.append(f"Topic: {tag_slug}")
        if filters:
            embed.set_footer(text=" | ".join(filters))
        await ctx.respond(embed=embed)

    @ai_group.command(name="generate", description="Get AI-suggested practice problem")
    async def generate(
        self,
        ctx: discord.ApplicationContext,
        topic: discord.Option(str, description="Topic slug (e.g. dynamic-programming)", required=False) = None,
        difficulty: discord.Option(
            str,
            choices=[
                discord.OptionChoice("Easy", "Easy"),
                discord.OptionChoice("Medium", "Medium"),
                discord.OptionChoice("Hard", "Hard"),
            ],
            required=False,
        ) = None,
    ) -> None:
        """Generate a problem suggestion."""
        await ctx.defer()
        ai = self._get_ai_service()
        if not ai:
            await ctx.respond(embed=error_embed("AI service not available"))
            return

        reply = await ai.generate_suggestion(topic=topic, difficulty=difficulty)
        if len(reply) > 1900:
            reply = reply[:1900] + "..."
        await ctx.respond(reply)


def setup(bot: discord.Bot) -> None:
    """Load the AI cog."""
    from services.ai import AIService
    import config

    bot.add_cog(AICog(bot))
    bot.ai_service = AIService(config.OPENAI_API_KEY, bot.leetcode)
