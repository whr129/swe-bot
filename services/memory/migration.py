"""One-time migration from JSON file-based memory to ChromaDB.

Run directly:  python -m services.memory.migration
"""

import json
import logging
import sys
from pathlib import Path

logger = logging.getLogger("leetbot.memory.migration")

OLD_DATA_ROOT = Path(__file__).resolve().parent.parent.parent / "data" / "memory"


def migrate(memory_manager: "services.memory.MemoryManager") -> dict[str, int]:
    """Migrate legacy JSON memory into the ChromaDB-backed MemoryManager.

    Returns a summary dict with counts of migrated items.
    """
    stats: dict[str, int] = {"conversations": 0, "preferences": 0, "errors": 0}

    if not OLD_DATA_ROOT.exists():
        logger.info("No legacy memory directory found at %s; nothing to migrate.", OLD_DATA_ROOT)
        return stats

    for namespace_dir in sorted(OLD_DATA_ROOT.iterdir()):
        if not namespace_dir.is_dir():
            continue
        agent_name = namespace_dir.name
        logger.info("Migrating namespace: %s", agent_name)

        conv_dir = namespace_dir / "conversations"
        if conv_dir.exists():
            for conv_file in sorted(conv_dir.glob("*.json")):
                try:
                    user_id = int(conv_file.stem)
                except ValueError:
                    continue
                try:
                    entries = json.loads(conv_file.read_text())
                except (json.JSONDecodeError, OSError) as e:
                    logger.warning("Failed to read %s: %s", conv_file, e)
                    stats["errors"] += 1
                    continue
                for entry in entries:
                    q = entry.get("q", "")
                    a = entry.get("a", "")
                    ts = entry.get("ts")
                    if not q and not a:
                        continue
                    meta = {}
                    if ts:
                        meta["timestamp"] = ts
                    memory_manager.add_conversation(
                        user_id=user_id,
                        question=q,
                        answer=a,
                        agent_name=agent_name,
                        metadata=meta,
                    )
                    stats["conversations"] += 1

        pref_dir = namespace_dir / "preferences"
        if pref_dir.exists():
            for pref_file in sorted(pref_dir.glob("*.json")):
                try:
                    user_id = int(pref_file.stem)
                except ValueError:
                    continue
                try:
                    raw = json.loads(pref_file.read_text())
                except (json.JSONDecodeError, OSError) as e:
                    logger.warning("Failed to read %s: %s", pref_file, e)
                    stats["errors"] += 1
                    continue
                for key, val_obj in raw.items():
                    value = val_obj.get("val", val_obj) if isinstance(val_obj, dict) else val_obj
                    memory_manager.save_preference(user_id, key, value)
                    stats["preferences"] += 1

    logger.info(
        "Migration complete: %d conversations, %d preferences, %d errors",
        stats["conversations"],
        stats["preferences"],
        stats["errors"],
    )
    return stats


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    import config
    from services.memory import MemoryManager

    mm = MemoryManager(
        persist_dir=config.CHROMA_PERSIST_DIR,
        openai_api_key=config.OPENAI_API_KEY or None,
        embedding_model=config.EMBEDDING_MODEL,
        short_term_ttl_days=config.MEMORY_SHORT_TERM_TTL_DAYS,
        recall_limit=config.MEMORY_RECALL_LIMIT,
    )
    stats = migrate(mm)
    print(f"Done: {stats}")


if __name__ == "__main__":
    main()
