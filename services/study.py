"""Study plan service with PostgreSQL storage."""

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

import asyncpg
from services.leetcode import LeetCodeService


@dataclass
class StudyPlan:
    """User study plan."""

    id: int
    discord_id: int
    leetcode_username: str
    plan_name: str
    created_at: datetime


@dataclass
class PlanProgress:
    """Study plan progress summary."""

    total_added: int
    completed: int
    streak_days: int
    last_activity: Optional[date]


class StudyService:
    """Service for study plan CRUD and progress tracking."""

    def __init__(self, database_url: str, leetcode: LeetCodeService):
        self.database_url = database_url
        self.leetcode = leetcode
        self._pool: Optional[asyncpg.Pool] = None

    async def _get_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            self._pool = await asyncpg.create_pool(
                self.database_url,
                min_size=1,
                max_size=5,
                command_timeout=60,
            )
            await self.init_db()
        return self._pool

    async def close(self) -> None:
        """Close the connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None

    async def init_db(self) -> None:
        """Create tables if they don't exist."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    discord_id BIGINT PRIMARY KEY,
                    leetcode_username VARCHAR(100) NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS study_plans (
                    id SERIAL PRIMARY KEY,
                    discord_id BIGINT NOT NULL REFERENCES users(discord_id) ON DELETE CASCADE,
                    plan_name VARCHAR(200) NOT NULL DEFAULT 'default',
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    UNIQUE(discord_id, plan_name)
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS plan_problems (
                    id SERIAL PRIMARY KEY,
                    plan_id INT NOT NULL REFERENCES study_plans(id) ON DELETE CASCADE,
                    problem_id VARCHAR(50) NOT NULL,
                    problem_slug VARCHAR(200) NOT NULL,
                    difficulty VARCHAR(20),
                    added_at TIMESTAMPTZ DEFAULT NOW(),
                    completed_at TIMESTAMPTZ,
                    UNIQUE(plan_id, problem_slug)
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS progress (
                    discord_id BIGINT NOT NULL,
                    activity_date DATE NOT NULL,
                    problems_solved INT DEFAULT 0,
                    PRIMARY KEY (discord_id, activity_date)
                )
            """)

    async def start_plan(
        self,
        discord_id: int,
        leetcode_username: str,
        plan_name: str = "default",
    ) -> StudyPlan:
        """Create or get a study plan for a user."""
        pool = await self._get_pool()
        plan_name = plan_name or "default"
        plan_name = re.sub(r"[^\w\s-]", "", plan_name)[:200] or "default"

        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO users (discord_id, leetcode_username)
                VALUES ($1, $2)
                ON CONFLICT (discord_id) DO UPDATE SET leetcode_username = $2
                """,
                discord_id,
                leetcode_username.strip()[:100],
            )
            row = await conn.fetchrow(
                """
                INSERT INTO study_plans (discord_id, plan_name)
                VALUES ($1, $2)
                ON CONFLICT (discord_id, plan_name) DO UPDATE SET plan_name = EXCLUDED.plan_name
                RETURNING id, discord_id, plan_name, created_at
                """,
                discord_id,
                plan_name,
            )
            if not row:
                row = await conn.fetchrow(
                    "SELECT id, discord_id, plan_name, created_at FROM study_plans WHERE discord_id = $1 AND plan_name = $2",
                    discord_id,
                    plan_name,
                )

        return StudyPlan(
            id=row["id"],
            discord_id=row["discord_id"],
            leetcode_username=leetcode_username,
            plan_name=row["plan_name"],
            created_at=row["created_at"],
        )

    async def add_problem(
        self,
        discord_id: int,
        problem_id_or_slug: str,
    ) -> Optional[str]:
        """Add a problem to the user's study plan. Returns error message or None on success."""
        pool = await self._get_pool()
        try:
            prob = await self.leetcode.get_problem(problem_id_or_slug)
        except Exception as e:
            return f"Problem not found: {e}"

        async with pool.acquire() as conn:
            plan = await conn.fetchrow(
                "SELECT id FROM study_plans WHERE discord_id = $1 ORDER BY created_at DESC LIMIT 1",
                discord_id,
            )
            if not plan:
                return "No study plan found. Use /study start first."

            try:
                await conn.execute(
                    """
                    INSERT INTO plan_problems (plan_id, problem_id, problem_slug, difficulty)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (plan_id, problem_slug) DO NOTHING
                    """,
                    plan["id"],
                    prob.frontend_id,
                    prob.title_slug,
                    prob.difficulty,
                )
            except Exception as e:
                return str(e)
        return None

    async def get_progress(self, discord_id: int) -> Optional[PlanProgress]:
        """Get user's study progress."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT COUNT(*) as total,
                       COUNT(completed_at) as completed
                FROM plan_problems pp
                JOIN study_plans sp ON pp.plan_id = sp.id
                WHERE sp.discord_id = $1
                """,
                discord_id,
            )
            total = rows[0]["total"] if rows else 0
            completed = rows[0]["completed"] if rows else 0

            last_activity = await conn.fetchval(
                "SELECT activity_date FROM progress WHERE discord_id = $1 ORDER BY activity_date DESC LIMIT 1",
                discord_id,
            )
            streak = 0
            if last_activity:
                today = date.today()
                delta = (today - last_activity).days
                if delta <= 1:
                    streak = 1
                    d = last_activity
                    while True:
                        prev = await conn.fetchval(
                            "SELECT activity_date FROM progress WHERE discord_id = $1 AND activity_date < $2 ORDER BY activity_date DESC LIMIT 1",
                            discord_id,
                            d,
                        )
                        if prev and (d - prev).days == 1:
                            streak += 1
                            d = prev
                        else:
                            break

        return PlanProgress(
            total_added=int(total),
            completed=int(completed),
            streak_days=streak,
            last_activity=last_activity,
        )

    async def get_next_problem(self, discord_id: int) -> Optional[dict]:
        """Get next recommended problem (first incomplete in plan, or random)."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT pp.problem_slug, pp.difficulty
                FROM plan_problems pp
                JOIN study_plans sp ON pp.plan_id = sp.id
                WHERE sp.discord_id = $1 AND pp.completed_at IS NULL
                ORDER BY pp.added_at ASC
                LIMIT 1
                """,
                discord_id,
            )
        if row:
            try:
                prob = await self.leetcode.get_problem(row["problem_slug"])
                return {
                    "title": prob.title,
                    "url": prob.url,
                    "difficulty": prob.difficulty,
                    "frontend_id": prob.frontend_id,
                    "topic_tags": prob.topic_tags,
                }
            except Exception:
                pass
        try:
            prob = await self.leetcode.get_random_problem()
            return {
                "title": prob.title,
                "url": prob.url,
                "difficulty": prob.difficulty,
                "frontend_id": prob.frontend_id,
                "topic_tags": prob.topic_tags,
            }
        except Exception:
            return None
