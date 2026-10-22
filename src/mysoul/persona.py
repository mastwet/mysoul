"""Versioned persona authority with evidence-bound automatic evolution."""

import json
from hashlib import sha256
from typing import Literal

from pydantic import Field

from mysoul.domain import Contract, Scope, now, uid
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


class PersonaChange(Contract):
    target: Literal["identity", "relationship", "dark", "world", "user_observations"]
    text: str = Field(max_length=8000)
    reason: str = Field(min_length=1, max_length=1000)
    evidence_refs: list[str] = Field(min_length=1, max_length=32)


class ReflectionDecision(Contract):
    changes: list[PersonaChange] = Field(default_factory=list, max_length=5)
    note: str = Field(default="", max_length=4000)
    reason: str = Field(min_length=1, max_length=1000)


def content_hash(value):
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


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
    user_observations: str = Field(default="", max_length=8000)

    def instructions(self, scope: Scope):
        if scope.audience != "owner":
            return "[公开人格配置]\n" + self.public
        return (
            "[当前版本人格；不改变运行权限]\n[public]\n"
            + self.public
            + "\n\n"
            + "\n\n".join(f"[{key}]\n{value}" for key, value in self.sections.model_dump().items()
                            if key != "world")
            + "\n\n[user_observations: model-inferred, not owner-confirmed]\n"
            + self.user_observations
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

    def update(self, expected_version, *, sections=None, public=None, user_observations=None):
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
            if user_observations is not None:
                values["user_observations"] = user_observations
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


    def changes(self):
        return sorted(self.store.all("persona_change"), key=lambda r: r["created_at"], reverse=True)

    def apply_evolution(self, expected_version, expected_epoch, operation_id, changes, refs,
                        *, expected_base_hash=None, source_window=None):
        changes = [PersonaChange.model_validate(c) for c in changes]
        candidate_hash = content_hash({"changes": [c.model_dump() for c in changes],
                                       "refs": refs, "base": expected_version})
        receipt = self.store.get("persona_change", operation_id)
        if receipt:
            if receipt["candidate_hash"] != candidate_hash:
                raise Conflict("Operation ID already binds a different candidate")
            if receipt["status"] in {"applied", "no_change"}:
                return PersonaProfile.model_validate(
                    self.store.get("persona_revision", str(receipt["version"])))
            raise Conflict("Candidate was already rejected; prepare a new run")
        record = {"id": operation_id, "created_at": now().isoformat(), "actor": "automatic",
                  "base_version": expected_version, "candidate_hash": candidate_hash,
                  "source_window": source_window, "refs": refs, "changes": [],
                  "status": "rejected", "version": None, "base_hash": expected_base_hash}
        try:
            with self.store.transaction() as db:
                current = self.current()
                record["base_hash"] = content_hash(current.model_dump())
                if (current.version != expected_version
                        or (expected_base_hash and expected_base_hash != record["base_hash"])
                        or db.execute("SELECT epoch FROM subjects WHERE id='mysoul'")
                        .fetchone()[0] != expected_epoch):
                    raise Conflict("Persona base or owner epoch changed")
                if len({c.target for c in changes}) != len(changes):
                    raise ValueError("Duplicate persona targets")
                values = current.model_dump()
                for change in changes:
                    if not set(change.evidence_refs) <= set(refs):
                        raise ValueError("Persona citation is outside admitted source window")
                    for ref in change.evidence_refs:
                        if not self.store.evidence(ref).permitted(Scope()):
                            raise ValueError("Persona evidence scope denied")
                    target = values if change.target == "user_observations" else values["sections"]
                    new_text = change.text
                    if change.target == "world":
                        old = target[change.target]
                        addition = change.text.strip()
                        new_text = old if not addition or addition in old.split("\n\n") else (
                            old + "\n\n" + addition if old else addition)
                    record["changes"].append({"target": change.target,
                                              "old": target[change.target], "new": new_text,
                                              "reason": change.reason,
                                              "evidence_refs": change.evidence_refs})
                    target[change.target] = new_text
                changed = values != current.model_dump()
                if changed:
                    values["version"] += 1
                updated = PersonaProfile.model_validate(values)
                if changed:
                    db.execute("INSERT OR REPLACE INTO objects VALUES('config','persona',?)",
                               (updated.model_dump_json(),))
                    db.execute("INSERT INTO objects VALUES('persona_revision',?,?)",
                               (str(updated.version), updated.model_dump_json()))
                record.update(status="applied" if changed else "no_change", version=updated.version)
                db.execute("INSERT INTO objects VALUES('persona_change',?,?)",
                           (operation_id, json.dumps(record, ensure_ascii=False)))
                return updated
        except (ValueError, KeyError) as exc:
            record["status"] = "conflict" if isinstance(exc, Conflict) else "rejected"
            record["error"] = str(exc)[:300]
            self.store.put_new("persona_change", operation_id, record)
            raise

    def rollback(self, expected_version, target_version):
        with self.store.transaction() as db:
            current = self.current()
            if current.version != expected_version:
                raise Conflict("Persona version changed")
            target = self.store.get("persona_revision", str(target_version))
            if target is None:
                raise KeyError(target_version)
            restored = PersonaProfile.model_validate(target)
            restored.version = current.version + 1
            db.execute("INSERT OR REPLACE INTO objects VALUES('config','persona',?)",
                       (restored.model_dump_json(),))
            db.execute("INSERT INTO objects VALUES('persona_revision',?,?)",
                       (str(restored.version), restored.model_dump_json()))
            changes = [
                {"target": key, "old": value, "new": restored.sections.model_dump()[key],
                 "reason": f"Owner rollback to revision {target_version}", "evidence_refs": []}
                for key, value in current.sections.model_dump().items()
                if restored.sections.model_dump()[key] != value
            ]
            for key in ("public", "user_observations"):
                if getattr(current, key) != getattr(restored, key):
                    changes.append({"target": key, "old": getattr(current, key),
                                    "new": getattr(restored, key), "reason": "Owner rollback",
                                    "evidence_refs": []})
            record = {"id": uid(), "created_at": now().isoformat(), "actor": "owner_rollback",
                      "base_version": current.version, "version": restored.version,
                      "target_version": target_version, "status": "applied", "changes": changes,
                      "refs": [], "base_hash": content_hash(current.model_dump()),
                      "candidate_hash": content_hash(restored.model_dump())}
            db.execute("INSERT INTO objects VALUES('persona_change',?,?)",
                       (record["id"], json.dumps(record, ensure_ascii=False)))
            return restored
