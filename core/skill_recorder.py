"""
Skill Recorder: Records operation methods in the skills folder.
When AI understands and executes a task, it saves the method as a reusable skill.

Skill format: JSON files in data/skills/ with an index.
Each skill describes HOW to perform a task type.
"""
import os
import json
import datetime
import logging
import threading
from typing import List, Dict, Optional, Any
from pathlib import Path

import config

logger = logging.getLogger(__name__)


class Skill:
    """Represents a recorded operational skill."""

    def __init__(
        self,
        name: str,
        description: str,
        steps: List[str],
        category: str = "general",
        keywords: List[str] = None,
        examples: List[str] = None,
        use_count: int = 0,
        created_at: str = None,
        updated_at: str = None,
    ):
        self.name = name
        self.description = description
        self.steps = steps
        self.category = category
        self.keywords = keywords or []
        self.examples = examples or []
        self.use_count = use_count
        self.created_at = created_at or datetime.datetime.now().isoformat()
        self.updated_at = updated_at or self.created_at

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "description": self.description,
            "steps": self.steps,
            "category": self.category,
            "keywords": self.keywords,
            "examples": self.examples,
            "use_count": self.use_count,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "Skill":
        return cls(
            name=d.get("name", "unnamed"),
            description=d.get("description", ""),
            steps=d.get("steps", []),
            category=d.get("category", "general"),
            keywords=d.get("keywords", []),
            examples=d.get("examples", []),
            use_count=d.get("use_count", 0),
            created_at=d.get("created_at"),
            updated_at=d.get("updated_at"),
        )

    def skill_filepath(self) -> str:
        """Get the filepath for this skill's JSON file."""
        safe_name = self.name.replace(" ", "_").replace("/", "_").lower()
        return os.path.join(config.SKILLS_DIR, f"{safe_name}.json")

    def save(self):
        """Save skill to its JSON file."""
        os.makedirs(config.SKILLS_DIR, exist_ok=True)
        self.updated_at = datetime.datetime.now().isoformat()
        filepath = self.skill_filepath()
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
        logger.debug(f"Skill saved: {filepath}")


class SkillRecorder:
    """
    Records, retrieves, and manages skills in the skills folder.
    Skills are indexed for fast lookup.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._skills: Dict[str, Skill] = {}  # name -> Skill
        self._load_all()

    def _load_all(self):
        """Load all skill files from the skills directory."""
        if not os.path.exists(config.SKILLS_DIR):
            return

        loaded = 0
        for filepath in Path(config.SKILLS_DIR).glob("*.json"):
            if filepath.name == "index.json":
                continue
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                skill = Skill.from_dict(data)
                self._skills[skill.name] = skill
                loaded += 1
            except Exception as e:
                logger.warning(f"Failed to load skill {filepath}: {e}")

        logger.info(f"Loaded {loaded} skills from {config.SKILLS_DIR}")
        self._save_index()

    def _save_index(self):
        """Save index of all skills."""
        index = {
            "skills": [
                {
                    "name": s.name,
                    "description": s.description,
                    "category": s.category,
                    "keywords": s.keywords,
                    "use_count": s.use_count,
                    "updated_at": s.updated_at,
                }
                for s in self._skills.values()
            ],
            "total": len(self._skills),
            "last_updated": datetime.datetime.now().isoformat(),
        }
        try:
            os.makedirs(config.SKILLS_DIR, exist_ok=True)
            with open(config.SKILLS_INDEX_FILE, "w", encoding="utf-8") as f:
                json.dump(index, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save skill index: {e}")

    def record(
        self,
        name: str,
        description: str,
        steps: List[str],
        category: str = "general",
        keywords: List[str] = None,
        example_instruction: str = None,
    ) -> Skill:
        """
        Record a new skill or update existing one.
        Returns the skill object.
        """
        with self._lock:
            if name in self._skills:
                # Update existing skill
                skill = self._skills[name]
                skill.description = description
                skill.steps = steps
                skill.category = category
                if keywords:
                    # Merge keywords
                    existing = set(skill.keywords)
                    skill.keywords = list(existing | set(keywords))
                if example_instruction and example_instruction not in skill.examples:
                    skill.examples.append(example_instruction)
                    if len(skill.examples) > 10:
                        skill.examples = skill.examples[-10:]
                logger.info(f"Skill updated: {name}")
            else:
                # Create new skill
                skill = Skill(
                    name=name,
                    description=description,
                    steps=steps,
                    category=category,
                    keywords=keywords or [],
                    examples=[example_instruction] if example_instruction else [],
                )
                self._skills[name] = skill
                logger.info(f"New skill recorded: {name}")

            skill.save()
            self._save_index()
            return skill

    def record_from_analysis(
        self,
        instruction: str,
        analysis: Dict[str, Any],
    ) -> Optional[Skill]:
        """
        Record a skill from an AI analysis result.
        analysis should have: skill_name, skill_description, steps
        """
        skill_name = analysis.get("skill_name", "").strip()
        if not skill_name:
            return None

        description = analysis.get("skill_description", instruction[:100])
        steps = analysis.get("steps", [instruction])
        if isinstance(steps, str):
            steps = [steps]

        # Derive category from instruction keywords
        category = self._infer_category(instruction)
        keywords = self._extract_keywords(instruction)

        return self.record(
            name=skill_name,
            description=description,
            steps=steps,
            category=category,
            keywords=keywords,
            example_instruction=instruction,
        )

    def search(self, query: str, max_results: int = 5) -> List[Dict]:
        """Search skills by name, description, or keywords."""
        query_lower = query.lower()
        results = []

        for skill in self._skills.values():
            score = 0
            if query_lower in skill.name.lower():
                score += 3
            if query_lower in skill.description.lower():
                score += 2
            if any(query_lower in k.lower() for k in skill.keywords):
                score += 1
            if any(query_lower in e.lower() for e in skill.examples):
                score += 1

            if score > 0:
                results.append((score, skill.to_dict()))

        results.sort(key=lambda x: (-x[0], -x[1]["use_count"]))
        return [r[1] for r in results[:max_results]]

    def get(self, name: str) -> Optional[Skill]:
        """Get a skill by name."""
        return self._skills.get(name)

    def mark_used(self, name: str):
        """Increment use count for a skill."""
        with self._lock:
            if name in self._skills:
                self._skills[name].use_count += 1
                self._skills[name].save()
                self._save_index()

    def get_all(self) -> List[Dict]:
        """Get all skills sorted by use count."""
        return sorted(
            [s.to_dict() for s in self._skills.values()],
            key=lambda s: -s["use_count"],
        )

    def get_categories(self) -> Dict[str, int]:
        """Get skill counts by category."""
        cats: Dict[str, int] = {}
        for skill in self._skills.values():
            cats[skill.category] = cats.get(skill.category, 0) + 1
        return cats

    @property
    def count(self) -> int:
        return len(self._skills)

    def _infer_category(self, instruction: str) -> str:
        """Infer skill category from instruction text."""
        instruction_lower = instruction.lower()
        categories = {
            "file": ["ファイル", "フォルダ", "保存", "開く", "コピー", "移動", "削除",
                     "file", "folder", "save", "open", "copy", "move", "delete"],
            "browser": ["ブラウザ", "ウェブ", "検索", "URL", "タブ",
                        "browser", "web", "search", "url", "tab"],
            "editor": ["エディタ", "コード", "編集", "テキスト",
                       "editor", "code", "edit", "text"],
            "system": ["システム", "設定", "インストール", "起動",
                       "system", "settings", "install", "launch"],
            "communication": ["メール", "チャット", "送信", "返信",
                              "email", "chat", "send", "reply"],
        }

        for category, keywords in categories.items():
            if any(kw in instruction_lower for kw in keywords):
                return category

        return "general"

    def _extract_keywords(self, instruction: str) -> List[str]:
        """Extract meaningful keywords from instruction."""
        # Simple keyword extraction: words > 2 chars
        import re
        words = re.findall(r'\w+', instruction)
        keywords = []
        stop_words = {"を", "の", "に", "は", "が", "で", "と", "から", "まで",
                      "the", "a", "an", "is", "are", "to", "for"}
        for word in words:
            if len(word) > 2 and word.lower() not in stop_words:
                keywords.append(word)
        return list(set(keywords))[:10]
