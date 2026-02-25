#!/usr/bin/env python3
"""Entry point to run the LeetBot."""

import asyncio
import logging
import sys

# Ensure project root is on path
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import discord.errors
import config
from bot.main import create_bot, setup_cogs

logger = logging.getLogger("leetbot")


async def main() -> None:
    """Run the bot."""
    token = (config.DISCORD_TOKEN or "").strip().replace("\n", "").replace("\r", "")
    # Remove quotes if user wrapped the token
    if token.startswith('"') and token.endswith('"'):
        token = token[1:-1].strip()
    if token.startswith("'") and token.endswith("'"):
        token = token[1:-1].strip()
    if not token or token in ("your_discord_bot_token", ""):
        logger.error(
            "DISCORD_TOKEN is not set or invalid. Copy .env.example to .env and add your bot token from "
            "https://discord.com/developers/applications"
        )
        return
    # Discord bot tokens are typically 59-72 chars; client secrets are different
    if len(token) < 50:
        logger.warning("Token seems short (%d chars). Make sure you copied the BOT token, not the Client ID.", len(token))

    bot = create_bot()
    setup_cogs(bot)
    try:
        await bot.start(token)
    except discord.errors.LoginFailure:
        logger.error(
            "Invalid Discord token (401). Common fixes:\n"
            "  - Use the BOT token (Bot tab) NOT Client ID or Client Secret\n"
            "  - Click 'Reset Token' then copy the new one immediately\n"
            "  - In .env use: DISCORD_TOKEN=paste_here (no quotes, entire line = token only)\n"
            "  - Check for extra spaces or missing chars when pasting"
        )
        return
    except Exception as e:
        logger.exception("Bot failed: %s", e)
        raise
    finally:
        await bot.leetcode.close()
        study = getattr(bot, "study_service", None)
        if study and hasattr(study, "close"):
            await study.close()


if __name__ == "__main__":
    asyncio.run(main())
