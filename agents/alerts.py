"""Personal alert/reminder specialist agent with isolated tools and RAG memory."""

from typing import Any, Optional

from openai import AsyncOpenAI

from agents.base import BaseAgent
from services.alerts import AlertService
from services.memory import MemoryManager

TOOL_DEFINITIONS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "create_price_alert",
            "description": "Create a stock price alert that triggers when a stock goes above or below a target price.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "integer", "description": "Discord user ID"},
                    "symbol": {"type": "string", "description": "Stock ticker symbol, e.g. 'AAPL'"},
                    "direction": {"type": "string", "enum": ["above", "below"], "description": "Trigger when price goes above or below target"},
                    "target": {"type": "number", "description": "Target price"},
                },
                "required": ["user_id", "symbol", "direction", "target"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_reminder",
            "description": "Create a due-date reminder that triggers at a specific date and time.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "integer", "description": "Discord user ID"},
                    "message": {"type": "string", "description": "Reminder message"},
                    "due_date": {"type": "string", "description": "Due date in ISO format (YYYY-MM-DDTHH:MM:SS)"},
                },
                "required": ["user_id", "message", "due_date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_alerts",
            "description": "List all active (non-triggered) alerts for a user.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "integer", "description": "Discord user ID"},
                },
                "required": ["user_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_alert",
            "description": "Delete an alert by its ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "integer", "description": "Discord user ID"},
                    "alert_id": {"type": "string", "description": "The alert ID to delete"},
                },
                "required": ["user_id", "alert_id"],
            },
        },
    },
]


class AlertAgent(BaseAgent):
    name = "alerts"
    tool_definitions = TOOL_DEFINITIONS

    def __init__(
        self,
        client: Optional[AsyncOpenAI],
        memory: MemoryManager,
        alert_service: AlertService,
        model: str = "gpt-4o-mini",
        max_iterations: int = 8,
    ):
        super().__init__(client=client, memory=memory, model=model, max_iterations=max_iterations)
        self.alerts = alert_service

    async def execute_tool(self, name: str, args: dict) -> Any:
        if name == "create_price_alert":
            alert = self.alerts.create_alert(
                user_id=args["user_id"],
                alert_type="price",
                config={
                    "symbol": args["symbol"].upper(),
                    "direction": args["direction"],
                    "target": args["target"],
                },
            )
            return {
                "status": "created",
                "id": alert.id,
                "symbol": args["symbol"].upper(),
                "direction": args["direction"],
                "target": args["target"],
            }

        if name == "create_reminder":
            alert = self.alerts.create_alert(
                user_id=args["user_id"],
                alert_type="reminder",
                config={
                    "message": args["message"],
                    "due_date": args["due_date"],
                },
            )
            return {
                "status": "created",
                "id": alert.id,
                "message": args["message"],
                "due_date": args["due_date"],
            }

        if name == "list_alerts":
            alerts = self.alerts.list_alerts(args["user_id"])
            if not alerts:
                return {"alerts": [], "message": "No active alerts."}
            return {"alerts": alerts}

        if name == "delete_alert":
            deleted = self.alerts.delete_alert(args["user_id"], args["alert_id"])
            if deleted:
                return {"status": "deleted", "id": args["alert_id"]}
            return {"status": "not_found", "id": args["alert_id"]}

        return {"error": f"Unknown tool: {name}"}
