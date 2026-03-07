"""Punch memory system: stores and retrieves context across sessions."""
from __future__ import annotations

import logging
from punch.db import Database

logger = logging.getLogger("punch.memory")


class Memory:
    def __init__(self, db: Database):
        self.db = db

    async def store(self, key: str, content: str, category: str = "general",
                    source_task_id: int | None = None) -> int:
        memory_id = await self.db.create_memory(
            key=key, content=content, category=category,
            source_task_id=source_task_id,
        )
        logger.info(f"Stored memory #{memory_id}: {key}")
        return memory_id

    async def search(self, query: str, category: str | None = None,
                     limit: int = 5) -> list[dict]:
        return await self.db.search_memories(query=query, category=category, limit=limit)

    async def get_context(self, query: str, limit: int = 3) -> str:
        """Build a context string from relevant memories for injection into prompts."""
        memories = await self.search(query, limit=limit)
        if not memories:
            return ""
        parts = ["## Relevant context from past tasks:\n"]
        for m in memories:
            parts.append(f"- **{m['key']}** [{m['category']}]: {m['content'][:500]}")
        return "\n".join(parts)

    async def store_from_task(self, task_id: int, key: str, content: str,
                              category: str = "task_result") -> int:
        """Store a memory linked to a completed task."""
        return await self.store(key=key, content=content, category=category,
                                source_task_id=task_id)
