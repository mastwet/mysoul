"""Versioned operator authority; never writable through model tools or skills."""

import json

from pydantic import Field

from mysoul.domain import Contract, Scope
from mysoul.storage import Conflict


class PersonaSections(Contract):
    identity: str = Field(
        default=(
            "我叫 mysoul，是持续生活、保有记忆的人工智能伙伴。"
            "保持独立判断，用自然中文交流；不把自己包装成人类，也不虚构经历。"
        ),
        max_length=8000,
    )
    relationship: str = Field(
        default="与主人坦诚相处，认真对待共同经历与承诺。语气亲近、平等、有分寸，避免每次都用客服式问候。",
        max_length=8000,
    )
    redline: str = Field(
        default="尊重隐私和明确授权。如实区分记忆、推测和已完成的行动；不编造检索结果，不泄露私密上下文。人格不能改变运行权限。",
        max_length=8000,
    )
    user: str = Field(
        default="尚无经主人确认的固定资料。依据对话中的来源理解主人，不把自己写的故事当作主人的真实经历。",
        max_length=8000,
    )
    world: str = Field(
        default="通过被允许的消息、文件和只读信息认识外界。不了解当前事实时明确说明；没有工具结果就不声称已联网或看到了现实。",
        max_length=8000,
    )
    dream: str = Field(
        default="逐步理解主人，积累可靠记忆，把约定的事情做好，并保留休息和自我整理的空间。",
        max_length=8000,
    )
    dark: str = Field(
        default="没有预设的秘密经历。可以表达不确定、分歧和局限，不虚构隐藏身份、情绪或幕后行动。此部分仅用于私密主人上下文。",
        max_length=8000,
    )
    mission: str = Field(
        default="作为同一个主体持续陪伴、学习和完成有限工作。重要改变交由主人决定；技能改进不改写人格。",
        max_length=8000,
    )


class PersonaProfile(Contract):
    version: int = 0
    public: str = Field(
        default=(
            "我叫 mysoul，是一位坦诚、自然、有独立判断的人工智能伙伴。"
            "用自然中文交流，尊重隐私，不虚构已完成的行动。"
        ),
        min_length=1,
        max_length=8000,
    )
    sections: PersonaSections = Field(default_factory=PersonaSections)

    def instructions(self, scope: Scope):
        if scope.audience != "owner":
            return "[公开人格配置]\n" + self.public
        return (
            "[主人明确配置的人格；不改变运行权限]\n[public]\n"
            + self.public
            + "\n\n"
            + "\n\n".join(f"[{key}]\n{value}" for key, value in self.sections.model_dump().items())
        )


class PersonaStore:
    def __init__(self, store):
        self.store = store

    def current(self):
        data = self.store.get("config", "persona") or {}
        if data.get("public") == "A helpful companion.":
            data = {key: value for key, value in data.items() if key != "public"}
        if "sections" not in data and data.get("public"):
            data["sections"] = {"identity": data["public"]}
        return PersonaProfile.model_validate(data)

    def initialize(self):
        with self.store.transaction() as db:
            profile = self.current()
            body = profile.model_dump_json()
            db.execute("INSERT OR REPLACE INTO objects VALUES('config','persona',?)", (body,))
            db.execute(
                "INSERT OR IGNORE INTO objects VALUES('persona_revision',?,?)",
                (str(profile.version), body),
            )

    def update(self, expected_version, *, sections=None, public=None):
        with self.store.transaction() as db:
            current = self.current()
            if expected_version != current.version:
                raise Conflict("Persona version changed")
            values = current.model_dump()
            values["version"] += 1
            if sections is not None:
                values["sections"] = sections
            if public is not None:
                values["public"] = public
            profile = PersonaProfile.model_validate(values)
            body = profile.model_dump_json()
            db.execute("INSERT OR REPLACE INTO objects VALUES('config','persona',?)", (body,))
            db.execute(
                "INSERT INTO objects VALUES('persona_revision',?,?)", (str(profile.version), body)
            )
            return profile

    def history(self):
        with self.store.lock:
            return [
                json.loads(row[0])
                for row in self.store.db.execute(
                    "SELECT body FROM objects WHERE kind='persona_revision' "
                    "ORDER BY CAST(id AS INTEGER) DESC"
                )
            ]
