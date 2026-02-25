"""AI service for LeetCode assistance using OpenAI."""

import json
import re
from typing import Optional

from openai import AsyncOpenAI
from services.leetcode import LeetCodeService


class AIService:
    """Service for LLM-powered LeetCode assistance."""

    def __init__(self, api_key: str, leetcode: LeetCodeService):
        self.client = AsyncOpenAI(api_key=api_key) if api_key else None
        self.leetcode = leetcode

    def is_available(self) -> bool:
        """Check if AI features are available."""
        return self.client is not None

    async def ask(self, question: str, problem_context: Optional[str] = None) -> str:
        """Answer a LeetCode-related question."""
        if not self.client:
            return "AI is not configured. Set OPENAI_API_KEY in your .env file."

        system = """You are a helpful LeetCode study assistant. You explain algorithms, data structures,
solution approaches, and coding concepts clearly. Be concise and educational.
If the user asks about a specific problem, use the problem context if provided."""
        messages = [{"role": "system", "content": system}]
        if problem_context:
            messages.append({"role": "user", "content": f"Problem context:\n{problem_context}\n\nUser question: {question}"})
        else:
            messages.append({"role": "user", "content": question})

        try:
            resp = await self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                max_tokens=1500,
            )
            return resp.choices[0].message.content or "No response."
        except Exception as e:
            return f"AI error: {str(e)}"

    async def search_problems(self, query: str) -> tuple[Optional[str], Optional[str], list[dict]]:
        """
        Parse natural language query into difficulty and tags, then fetch problems.
        Returns (difficulty, tag_slug, problems).
        """
        difficulty = None
        tag_slug = None

        if self.client:
            try:
                resp = await self.client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": """Extract LeetCode search filters from the user's natural language.
Reply with ONLY a JSON object: {"difficulty": "Easy"|"Medium"|"Hard"|null, "tag": "slug"|null}
Tag must be a LeetCode topic slug (e.g. dynamic-programming, two-pointers, array).
Use null for any unspecified filter."""},
                        {"role": "user", "content": query},
                    ],
                    max_tokens=100,
                )
                text = resp.choices[0].message.content or "{}"
                match = re.search(r"\{[^}]+\}", text)
                if match:
                    data = json.loads(match.group())
                    difficulty = data.get("difficulty")
                    tag_slug = data.get("tag")
            except Exception:
                pass

        if tag_slug:
            problems = await self.leetcode.get_problems_by_tag(tag_slug, limit=50)
            if difficulty:
                problems = [p for p in problems if p.get("difficulty") == difficulty]
        else:
            problems = await self.leetcode.get_problems(limit=200, difficulty=difficulty)

        return (difficulty, tag_slug, problems)

    async def generate_suggestion(
        self,
        topic: Optional[str] = None,
        difficulty: Optional[str] = None,
    ) -> str:
        """Generate a practice problem suggestion or idea."""
        if not self.client:
            return "AI is not configured. Set OPENAI_API_KEY in your .env file."

        problems = await self.leetcode.get_problems(limit=100, difficulty=difficulty)
        if topic:
            tag_problems = await self.leetcode.get_problems_by_tag(topic.replace(" ", "-"), limit=50)
            if tag_problems:
                problems = [p for p in tag_problems if not difficulty or p.get("difficulty") == difficulty]
                if not problems:
                    problems = tag_problems

        if not problems:
            return "No problems found matching your criteria."

        import random
        chosen = random.choice(problems[: min(20, len(problems))])
        title = chosen.get("title", "Unknown")
        slug = chosen.get("title_slug", chosen.get("titleSlug", ""))
        diff = chosen.get("difficulty", "Unknown")
        url = chosen.get("url", f"https://leetcode.com/problems/{slug}/")

        prompt = f"""Suggest the LeetCode problem: {title} ({diff}).
Why it's good for practice, key concepts to focus on, and a brief hint (don't give the solution)."""
        try:
            resp = await self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=400,
            )
            text = resp.choices[0].message.content or ""
            return f"**{title}** ({diff})\n{url}\n\n{text}"
        except Exception as e:
            return f"**{title}** ({diff})\n{url}\n\n*Could not generate AI suggestion: {e}*"
