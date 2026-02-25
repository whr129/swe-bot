# LeetBot - LeetCode Discord AI Assistant

A Discord bot that integrates LeetCode with AI capabilities for study assistance.

## Features

- **LeetCode commands** (`/leetcode`): daily challenge, problem lookup, random problem, user stats
- **AI commands** (`/ai`): ask questions, natural-language problem search, practice suggestions
- **Study plan** (`/study`): track progress, add problems, get next recommended problem

## Setup

### Prerequisites

- Python 3.10+
- PostgreSQL (for study plan storage)
- [Discord Bot Token](https://discord.com/developers/applications)
- [OpenAI API Key](https://platform.openai.com/api-keys) (for AI features)

### Installation

**Option A – Automatic setup (recommended):**

```bash
cd leetbot
chmod +x setup_venv.sh && ./setup_venv.sh
```

**Option B – Manual setup:**

```bash
cd leetbot
# Use Python 3.12 (3.14+ has compatibility issues with py-cord)
python3.12 -m venv venv
source venv/bin/activate   # or `venv\Scripts\activate` on Windows
pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org -r requirements.txt
```

### Configuration

1. Copy `.env.example` to `.env`
2. Fill in:

```
DISCORD_TOKEN=your_discord_bot_token
OPENAI_API_KEY=your_openai_api_key
DATABASE_URL=postgresql://user:password@localhost:5432/leetbot
```

3. Create a PostgreSQL database:

```bash
createdb leetbot
```

4. Invite the bot to your server with the `applications.commands` scope.

### Run

```bash
# Use venv's Python directly (avoids conda/system Python conflicts):
./venv/bin/python run.py

# Or use the wrapper:
./run.sh
```

If you see `ModuleNotFoundError: No module named 'discord'`, you're likely using the wrong Python. With conda active, `python` may point to conda. Use `./venv/bin/python run.py` instead.

## Commands

| Command | Description |
|---------|-------------|
| `/leetcode daily` | Today's LeetCode daily challenge |
| `/leetcode problem <query>` | Look up problem by ID or slug |
| `/leetcode random [difficulty] [topic]` | Random problem with optional filters |
| `/leetcode stats [username]` | LeetCode user profile stats |
| `/ai ask <question>` | Ask AI about LeetCode |
| `/ai search <query>` | Search problems with natural language |
| `/ai generate [topic] [difficulty]` | AI-suggested practice problem |
| `/study start <username>` | Create study plan |
| `/study progress` | View your progress |
| `/study add <problem>` | Add problem to plan |
| `/study next` | Get next recommended problem |
