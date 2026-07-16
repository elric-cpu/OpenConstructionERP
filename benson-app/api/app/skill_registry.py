import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .domain import Role
from .policy import ActionRisk


class SkillDefinition(BaseModel):
    id: str
    label: str
    category: str
    description: str
    risk: ActionRisk = ActionRisk.INTERNAL
    allowed_roles: set[Role]
    source_path: str
    required_context: list[str] = Field(default_factory=list)
    enabled: bool = True


class SkillRegistry:
    def __init__(self, definitions: list[SkillDefinition], source_commit: str):
        self.definitions = definitions
        self.source_commit = source_commit
        self._by_id = {definition.id: definition for definition in definitions}

    def get(self, skill_id: str) -> SkillDefinition | None:
        return self._by_id.get(skill_id)

    def visible_to(self, role: Role) -> list[SkillDefinition]:
        return [
            skill
            for skill in self.definitions
            if skill.enabled and role in skill.allowed_roles
        ]


@lru_cache(maxsize=8)
def load_registry(path_value: str) -> SkillRegistry:
    path = Path(path_value).resolve()
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return SkillRegistry(
        definitions=[SkillDefinition.model_validate(item) for item in data["skills"]],
        source_commit=str(data["source_commit"]),
    )
