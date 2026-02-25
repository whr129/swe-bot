"""Study plan commands."""

import discord
from discord.ext import commands
from discord.commands import SlashCommandGroup

from bot.utils.embeds import error_embed, problem_embed


class StudyCog(commands.Cog):
    """Study plan slash commands."""

    study_group = SlashCommandGroup("study", "Study plan commands")

    def __init__(self, bot: discord.Bot):
        self.bot = bot

    def _get_study_service(self):
        return getattr(self.bot, "study_service", None)

    @study_group.command(name="start", description="Create a study plan and link your LeetCode username")
    async def start(
        self,
        ctx: discord.ApplicationContext,
        leetcode_username: discord.Option(str, description="Your LeetCode username"),
        plan_name: discord.Option(str, description="Plan name", required=False) = None,
    ) -> None:
        """Start a study plan."""
        await ctx.defer()
        service = self._get_study_service()
        if not service:
            await ctx.respond(embed=error_embed("Study service not available."))
            return

        try:
            plan = await service.start_plan(
                ctx.author.id,
                leetcode_username.strip(),
                plan_name or "default",
            )
            await ctx.respond(
                f"Study plan **{plan.plan_name}** created for LeetCode user `{plan.leetcode_username}`. "
                "Use `/study add` to add problems, `/study next` to get the next problem."
            )
        except Exception as e:
            await ctx.respond(embed=error_embed(str(e)))

    @study_group.command(name="progress", description="View your study progress")
    async def progress(self, ctx: discord.ApplicationContext) -> None:
        """Show study progress."""
        await ctx.defer()
        service = self._get_study_service()
        if not service:
            await ctx.respond(embed=error_embed("Study service not available."))
            return

        prog = await service.get_progress(ctx.author.id)
        if not prog:
            await ctx.respond("No study plan found. Use `/study start` first.")
            return

        embed = discord.Embed(
            title="Study Progress",
            color=discord.Color.blue(),
        )
        embed.add_field(name="Problems Added", value=str(prog.total_added), inline=True)
        embed.add_field(name="Completed", value=str(prog.completed), inline=True)
        embed.add_field(name="Streak", value=f"{prog.streak_days} day(s)", inline=True)
        if prog.last_activity:
            embed.set_footer(text=f"Last activity: {prog.last_activity}")
        await ctx.respond(embed=embed)

    @study_group.command(name="add", description="Add a problem to your study plan")
    async def add(
        self,
        ctx: discord.ApplicationContext,
        problem: discord.Option(str, description="Problem ID or slug (e.g. 1, two-sum)"),
    ) -> None:
        """Add a problem to the study plan."""
        await ctx.defer()
        service = self._get_study_service()
        if not service:
            await ctx.respond(embed=error_embed("Study service not available."))
            return

        err = await service.add_problem(ctx.author.id, problem.strip())
        if err:
            await ctx.respond(embed=error_embed(err))
        else:
            await ctx.respond(f"Added problem `{problem}` to your study plan.")

    @study_group.command(name="next", description="Get the next recommended problem")
    async def next_problem(self, ctx: discord.ApplicationContext) -> None:
        """Get next problem from plan or a random one."""
        await ctx.defer()
        service = self._get_study_service()
        if not service:
            await ctx.respond(embed=error_embed("Study service not available."))
            return

        prob = await service.get_next_problem(ctx.author.id)
        if not prob:
            await ctx.respond(embed=error_embed("Could not fetch a problem."))
            return

        embed = problem_embed(
            title=prob["title"],
            url=prob["url"],
            difficulty=prob["difficulty"],
            frontend_id=prob["frontend_id"],
            topic_tags=prob.get("topic_tags"),
        )
        await ctx.respond(embed=embed)


def setup(bot: discord.Bot) -> None:
    """Load the study cog."""
    from services.study import StudyService
    import config

    bot.add_cog(StudyCog(bot))
    bot.study_service = StudyService(config.DATABASE_URL, bot.leetcode)
