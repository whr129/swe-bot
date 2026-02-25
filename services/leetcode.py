"""LeetCode API service - fetches problems and user data via REST API."""

import json
import random
from dataclasses import dataclass
from typing import Any, Optional

import aiohttp


@dataclass
class Problem:
    """Represents a LeetCode problem."""

    id: str
    frontend_id: str
    title: str
    title_slug: str
    url: str
    difficulty: str
    content: Optional[str] = None
    topic_tags: Optional[list[dict]] = None
    ac_rate: Optional[float] = None
    paid_only: bool = False


@dataclass
class DailyChallenge:
    """Today's daily coding challenge."""

    date: str
    link: str
    question: dict


@dataclass
class UserProfile:
    """LeetCode user profile and stats."""

    username: str
    total_solved: int
    easy_solved: int
    medium_solved: int
    hard_solved: int
    acceptance_rate: float
    ranking: Optional[int] = None
    avatar: Optional[str] = None


class LeetCodeService:
    """Service for interacting with LeetCode data."""

    def __init__(self, base_url: str = "https://leetcode-api-pied.vercel.app"):
        self.base_url = base_url.rstrip("/")
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={"User-Agent": "LeetBot/1.0 Discord Bot"}
            )
        return self._session

    async def close(self) -> None:
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def _get(self, path: str, params: Optional[dict] = None) -> Any:
        """Make a GET request to the LeetCode API."""
        session = await self._get_session()
        url = f"{self.base_url}{path}"
        try:
            async with session.get(url, params=params) as resp:
                resp.raise_for_status()
                return await resp.json()
        except aiohttp.ClientError as e:
            raise LeetCodeAPIError(f"LeetCode API error: {e}") from e

    async def get_daily(self) -> DailyChallenge:
        """Get today's daily coding challenge."""
        data = await self._get("/daily")
        return DailyChallenge(
            date=data.get("date", ""),
            link=data.get("link", ""),
            question=data.get("question", {}),
        )

    async def get_problem(self, id_or_slug: str) -> Problem:
        """Get a problem by ID or slug."""
        data = await self._get(f"/problem/{id_or_slug}")
        if isinstance(data, dict) and "error" in data:
            raise LeetCodeAPIError(data.get("error", "Problem not found"))
        ac_rate = None
        if "stats" in data and data["stats"]:
            try:
                stats = json.loads(data["stats"])
                ac_rate = float(stats.get("acRate", "0%").rstrip("%"))
            except (json.JSONDecodeError, ValueError):
                pass
        return Problem(
            id=str(data.get("id", data.get("questionId", ""))),
            frontend_id=str(data.get("frontend_id", data.get("questionFrontendId", ""))),
            title=data.get("title", ""),
            title_slug=data.get("title_slug", id_or_slug),
            url=data.get("url", f"https://leetcode.com/problems/{id_or_slug}/"),
            difficulty=data.get("difficulty", "Unknown"),
            content=data.get("content"),
            topic_tags=data.get("topic_tags", data.get("topicTags", [])),
            ac_rate=ac_rate or data.get("ac_rate"),
            paid_only=data.get("paid_only", data.get("isPaidOnly", False)),
        )

    async def get_problems(
        self,
        limit: int = 100,
        difficulty: Optional[str] = None,
    ) -> list[dict]:
        """Get list of problems with optional filters."""
        params = {"limit": limit}
        if difficulty:
            params["difficulty"] = difficulty
        data = await self._get("/problems", params=params)
        return data if isinstance(data, list) else []

    async def get_problems_by_tag(self, tag: str, limit: int = 50) -> list[dict]:
        """Get problems by topic tag slug."""
        data = await self._get(f"/problems/tag/{tag}", params={"limit": limit})
        if isinstance(data, dict) and "problems" in data:
            return data["problems"]
        return data if isinstance(data, list) else []

    async def get_random_problem(
        self,
        difficulty: Optional[str] = None,
        tag: Optional[str] = None,
    ) -> Problem:
        """Get a random problem with optional filters."""
        if tag and not difficulty:
            problems = await self.get_problems_by_tag(tag, limit=100)
        elif tag and difficulty:
            problems = await self.get_problems_by_tag(tag, limit=200)
            problems = [p for p in problems if p.get("difficulty") == difficulty]
        else:
            data = await self._get("/random", params={"difficulty": difficulty} if difficulty else {})
            if isinstance(data, dict) and "title_slug" in data:
                return await self.get_problem(data["title_slug"])
            problems = await self.get_problems(limit=500, difficulty=difficulty)

        if not problems:
            raise LeetCodeAPIError("No problems found matching filters")

        chosen = random.choice(problems)
        slug = chosen.get("title_slug", chosen.get("titleSlug", ""))
        problem_id = chosen.get("id", chosen.get("questionFrontendId", ""))
        return await self.get_problem(slug or str(problem_id))

    async def get_user_profile(self, username: str) -> UserProfile:
        """Get user profile and stats."""
        data = await self._get(f"/user/{username}")
        if isinstance(data, dict) and "error" in data:
            raise LeetCodeAPIError(data.get("error", "User not found"))

        submit_stats = data.get("submitStats", data.get("submit_stats", {}))
        ac_submissions = submit_stats.get("acSubmissionNum", [])
        total = easy = medium = hard = 0
        for stat in ac_submissions:
            count = stat.get("count", 0)
            diff = stat.get("difficulty", "")
            if diff == "All":
                total = count
            elif diff == "Easy":
                easy = count
            elif diff == "Medium":
                medium = count
            elif diff == "Hard":
                hard = count

        ranking = data.get("ranking")
        if "profile" in data and isinstance(data["profile"], dict):
            ranking = ranking or data["profile"].get("ranking")
            avatar = data["profile"].get("userAvatar")
        else:
            avatar = data.get("avatar")

        return UserProfile(
            username=data.get("username", username),
            total_solved=total or (easy + medium + hard),
            easy_solved=easy,
            medium_solved=medium,
            hard_solved=hard,
            acceptance_rate=0.0,
            ranking=ranking,
            avatar=avatar,
        )

    async def search_problems(self, query: str) -> list[dict]:
        """Search problems by query string."""
        data = await self._get("/search", params={"query": query})
        return data if isinstance(data, list) else []


class LeetCodeAPIError(Exception):
    """Raised when LeetCode API returns an error."""

    pass
