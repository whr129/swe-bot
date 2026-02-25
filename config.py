"""Configuration loaded from environment variables."""

import os
from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
LEETCODE_API_BASE = os.getenv("LEETCODE_API_BASE", "https://leetcode-api-pied.vercel.app")
DATABASE_URL = os.getenv("DATABASE_URL", "")
# Set to empty or "false" to run without PostgreSQL (study commands disabled)
DATABASE_ENABLED = DATABASE_URL and DATABASE_URL.strip() not in ("", "false", "0")
