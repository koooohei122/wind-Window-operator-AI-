"""
Memory Manager: Maintains short-term and long-term memory text files.
- Short-term: recent operation analysis memos (max 100 entries, 500 chars each)
- Long-term: consolidated patterns and important findings (max 100 entries, 500 chars each)
Automatically promotes recurring patterns from short-term to long-term memory.
"""
import os
import json
import datetime
import threading
import logging
from typing import List, Dict, Optional, Any
from pathlib import Path

import config

logger = logging.getLogger(__name__)


def truncate(text: str, max_chars: int = None) -> str:
    limit = max_chars or config.MAX_MEMORY_CHARS
    return text[:limit] if len(text) > limit else text


class MemoryEntry:
    """A single memory entry."""

    def __init__(
        self,
        content: str,
        entry_type: str = "operation",
        timestamp: str = None,
        tags: List[str] = None,
        count: int = 1,
    ):
        self.content = truncate(content)
        self.entry_type = entry_type  # operation, pattern, skill, recommendation
        self.timestamp = timestamp or datetime.datetime.now().isoformat()
        self.tags = tags or []
        self.count = count  # How many times this pattern appeared

    def to_dict(self) -> Dict:
        return {
            "content": self.content,
            "type": self.entry_type,
            "timestamp": self.timestamp,
            "tags": self.tags,
            "count": self.count,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "MemoryEntry":
        return cls(
            content=d.get("content", ""),
            entry_type=d.get("type", "operation"),
            timestamp=d.get("timestamp", datetime.datetime.now().isoformat()),
            tags=d.get("tags", []),
            count=d.get("count", 1),
        )


class MemoryStore:
    """Thread-safe JSON-backed memory store."""

    def __init__(self, filepath: str, max_entries: int = None):
        self.filepath = filepath
        self.max_entries = max_entries or config.MAX_MEMORY_ENTRIES
        self._lock = threading.Lock()
        self._entries: List[MemoryEntry] = []
        self._load()

    def _load(self):
        """Load entries from file."""
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._entries = [MemoryEntry.from_dict(d) for d in data.get("entries", [])]
                logger.debug(f"Loaded {len(self._entries)} entries from {self.filepath}")
            except Exception as e:
                logger.error(f"Failed to load memory from {self.filepath}: {e}")
                self._entries = []

    def _save(self):
        """Save entries to file."""
        try:
            os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
            data = {
                "entries": [e.to_dict() for e in self._entries],
                "last_updated": datetime.datetime.now().isoformat(),
                "count": len(self._entries),
            }
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save memory to {self.filepath}: {e}")

    def add(self, entry: MemoryEntry) -> bool:
        """Add a new entry. Returns True if added successfully."""
        with self._lock:
            # Check for duplicate (same content type)
            for existing in self._entries:
                if existing.content == entry.content:
                    existing.count += 1
                    existing.timestamp = entry.timestamp
                    self._save()
                    return True

            # Enforce max entries (remove oldest if needed)
            while len(self._entries) >= self.max_entries:
                # Remove oldest entry with lowest count
                self._entries.sort(key=lambda e: (e.count, e.timestamp))
                self._entries.pop(0)

            self._entries.append(entry)
            self._save()
            return True

    def get_all(self) -> List[Dict]:
        """Get all entries as dicts (newest first)."""
        with self._lock:
            return [e.to_dict() for e in reversed(self._entries)]

    def get_recent(self, n: int = 10) -> List[Dict]:
        """Get the N most recent entries."""
        return self.get_all()[:n]

    def search(self, keyword: str) -> List[Dict]:
        """Search entries by keyword."""
        with self._lock:
            keyword_lower = keyword.lower()
            return [
                e.to_dict()
                for e in self._entries
                if keyword_lower in e.content.lower()
                or any(keyword_lower in t.lower() for t in e.tags)
            ]

    def get_frequent(self, min_count: int = 2) -> List[Dict]:
        """Get entries that appear frequently (candidates for long-term memory)."""
        with self._lock:
            return [
                e.to_dict()
                for e in self._entries
                if e.count >= min_count
            ]

    @property
    def count(self) -> int:
        return len(self._entries)

    def clear(self):
        with self._lock:
            self._entries = []
            self._save()


class MemoryManager:
    """
    Manages both short-term and long-term memory.
    Short-term: recent raw operation memos
    Long-term: consolidated patterns promoted from short-term
    """

    def __init__(self):
        self.short_term = MemoryStore(config.SHORT_TERM_MEMORY_FILE)
        self.long_term = MemoryStore(config.LONG_TERM_MEMORY_FILE)
        self._promote_lock = threading.Lock()

    def add_operation_memo(
        self,
        analysis: Dict[str, Any],
        tags: List[str] = None,
    ) -> bool:
        """
        Add an operation analysis memo to short-term memory.
        Automatically promotes to long-term if pattern recurs.
        """
        # Build compact memo content (max 500 chars)
        parts = []
        if analysis.get("state"):
            parts.append(f"状態:{analysis['state'][:80]}")
        if analysis.get("purpose"):
            parts.append(f"目的:{analysis['purpose'][:80]}")
        if analysis.get("suggestion"):
            parts.append(f"提案:{analysis['suggestion'][:80]}")

        content = " / ".join(parts)
        content = truncate(content)

        entry_tags = tags or []
        if analysis.get("pattern"):
            entry_tags.append(analysis["pattern"][:50])

        entry = MemoryEntry(
            content=content,
            entry_type="operation",
            tags=entry_tags,
        )

        result = self.short_term.add(entry)

        # Check if we should promote to long-term
        self._maybe_promote()

        return result

    def add_skill_memo(self, skill_name: str, description: str) -> bool:
        """Add a skill learning event to long-term memory."""
        content = truncate(f"スキル習得: {skill_name} - {description}")
        entry = MemoryEntry(
            content=content,
            entry_type="skill",
            tags=["skill", skill_name],
        )
        return self.long_term.add(entry)

    def add_recommendation(self, recommendation: str) -> bool:
        """Add a recommendation to short-term memory."""
        content = truncate(f"推薦: {recommendation}")
        entry = MemoryEntry(
            content=content,
            entry_type="recommendation",
        )
        return self.short_term.add(entry)

    def add_pattern(self, pattern: str, tags: List[str] = None) -> bool:
        """Directly add a discovered pattern to long-term memory."""
        content = truncate(f"パターン: {pattern}")
        entry = MemoryEntry(
            content=content,
            entry_type="pattern",
            tags=tags or [],
        )
        return self.long_term.add(entry)

    def _maybe_promote(self):
        """Promote frequently occurring short-term entries to long-term memory."""
        with self._promote_lock:
            frequent = self.short_term.get_frequent(
                min_count=config.SHORT_TERM_PROMOTE_THRESHOLD
            )
            for item in frequent:
                # Check if not already in long-term
                existing = self.long_term.search(item["content"][:50])
                if not existing:
                    promoted_content = truncate(
                        f"[昇格パターン] {item['content']}"
                    )
                    long_entry = MemoryEntry(
                        content=promoted_content,
                        entry_type="pattern",
                        tags=item.get("tags", []) + ["promoted"],
                        count=item.get("count", 1),
                    )
                    self.long_term.add(long_entry)
                    logger.info(f"Promoted to long-term memory: {item['content'][:60]}")

    def get_context_for_analysis(self) -> str:
        """Build a context string from recent memories for AI analysis."""
        recent_short = self.short_term.get_recent(5)
        recent_long = self.long_term.get_recent(3)

        parts = []
        if recent_long:
            parts.append("【長期パターン】")
            for m in recent_long:
                parts.append(f"  - {m['content'][:100]}")
        if recent_short:
            parts.append("【直近の操作】")
            for m in recent_short:
                parts.append(f"  - {m['content'][:100]}")

        return "\n".join(parts)

    def get_summary(self) -> Dict[str, Any]:
        """Get memory statistics summary."""
        return {
            "short_term_count": self.short_term.count,
            "long_term_count": self.long_term.count,
            "short_term_max": config.MAX_MEMORY_ENTRIES,
            "long_term_max": config.MAX_MEMORY_ENTRIES,
            "recent_operations": self.short_term.get_recent(3),
        }

    def export_text_report(self) -> str:
        """Export memory contents as human-readable text."""
        lines = [
            "=" * 60,
            f"Wind Window Operator AI - メモリレポート",
            f"生成日時: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "=" * 60,
            "",
            f"▼ 長期メモリ ({self.long_term.count}/{config.MAX_MEMORY_ENTRIES}件)",
            "-" * 40,
        ]
        for i, entry in enumerate(self.long_term.get_all(), 1):
            lines.append(
                f"{i:3d}. [{entry['timestamp'][:16]}] {entry['content']}"
            )

        lines += [
            "",
            f"▼ 短期メモリ ({self.short_term.count}/{config.MAX_MEMORY_ENTRIES}件)",
            "-" * 40,
        ]
        for i, entry in enumerate(self.short_term.get_all(), 1):
            lines.append(
                f"{i:3d}. [{entry['timestamp'][:16]}] {entry['content']}"
            )

        return "\n".join(lines)
