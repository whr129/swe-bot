"""Discord embed helpers."""

from typing import Optional

import discord


def problem_embed(
    title: str,
    url: str,
    difficulty: str,
    frontend_id: str,
    topic_tags: Optional[list] = None,
    content: Optional[str] = None,
    ac_rate: Optional[float] = None,
) -> discord.Embed:
    """Create an embed for a LeetCode problem."""
    color = {
        "Easy": discord.Color.green(),
        "Medium": discord.Color.gold(),
        "Hard": discord.Color.red(),
    }.get(difficulty, discord.Color.blurple())

    embed = discord.Embed(
        title=f"{frontend_id}. {title}",
        url=url,
        description=content[:500] + "..." if content and len(content) > 500 else content or "No description",
        color=color,
    )
    embed.add_field(name="Difficulty", value=difficulty, inline=True)
    if ac_rate is not None:
        embed.add_field(name="Acceptance", value=f"{ac_rate:.1f}%", inline=True)
    if topic_tags:
        tags = ", ".join(t.get("name", t) for t in topic_tags[:5])
        embed.add_field(name="Topics", value=tags, inline=False)
    return embed


def daily_embed(
    title: str,
    url: str,
    difficulty: str,
    date: str,
    content: Optional[str] = None,
    topic_tags: Optional[list] = None,
) -> discord.Embed:
    """Create an embed for the daily challenge."""
    return problem_embed(
        title=title,
        url=f"https://leetcode.com{url}" if not url.startswith("http") else url,
        difficulty=difficulty,
        frontend_id="Daily",
        topic_tags=topic_tags,
        content=content,
    )


def user_stats_embed(
    username: str,
    total_solved: int,
    easy_solved: int,
    medium_solved: int,
    hard_solved: int,
    acceptance_rate: float,
    ranking: Optional[int] = None,
) -> discord.Embed:
    """Create an embed for user stats."""
    embed = discord.Embed(
        title=f"LeetCode Profile: {username}",
        url=f"https://leetcode.com/{username}/",
        color=discord.Color.blue(),
    )
    embed.add_field(name="Total Solved", value=str(total_solved), inline=True)
    embed.add_field(name="Easy", value=str(easy_solved), inline=True)
    embed.add_field(name="Medium", value=str(medium_solved), inline=True)
    embed.add_field(name="Hard", value=str(hard_solved), inline=True)
    embed.add_field(name="Acceptance Rate", value=f"{acceptance_rate:.1f}%", inline=True)
    if ranking:
        embed.add_field(name="Ranking", value=f"#{ranking}", inline=True)
    return embed


def error_embed(message: str) -> discord.Embed:
    """Create an embed for error messages."""
    return discord.Embed(
        title="Error",
        description=message,
        color=discord.Color.red(),
    )
