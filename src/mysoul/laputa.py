from hashlib import sha256

from mysoul.domain import ContextBudget, ContextBundle, RecapVersion, Scope
from mysoul.memory import MemoryUnavailable
from mysoul.storage import Conflict, StateStore


class ContextOverflow(ValueError):
    pass


class RecapStore:
    def __init__(self, store: StateStore):
        self.store = store
        with store.transaction() as db:
            initial = RecapVersion()
            db.execute(
                "INSERT OR IGNORE INTO recap VALUES(?,?,?)",
                ("mysoul", 0, initial.model_dump_json()),
            )
            db.execute("INSERT OR IGNORE INTO recap_head VALUES('mysoul',0)")

    def current(self) -> RecapVersion:
        with self.store.lock:
            row = self.store.db.execute(
                "SELECT r.body FROM recap r JOIN recap_head h "
                "ON r.subject=h.subject AND r.version=h.version WHERE h.subject='mysoul'"
            ).fetchone()
            return RecapVersion.model_validate_json(row[0])

    def history(self):
        with self.store.lock:
            return [
                RecapVersion.model_validate_json(r[0])
                for r in self.store.db.execute(
                    "SELECT body FROM recap WHERE subject='mysoul' ORDER BY version DESC"
                )
            ]

    def publish(self, expected_version: int, text: str, refs: list[str], *, clear=False):
        if len(text) > 64000:
            raise ContextOverflow("Recap exceeds storage limit; review before publishing")
        with self.store.transaction() as db:
            head = db.execute("SELECT version FROM recap_head WHERE subject='mysoul'").fetchone()[0]
            if head != expected_version:
                raise Conflict("Recap version conflict")
            old = RecapVersion.model_validate_json(
                db.execute(
                    "SELECT body FROM recap WHERE subject='mysoul' AND version=?", (head,)
                ).fetchone()[0]
            )
            for ref in refs:
                if not db.execute("SELECT 1 FROM evidence WHERE id=?", (ref,)).fetchone():
                    raise KeyError(ref)
            version = RecapVersion(
                version=head + 1,
                parent=head,
                text=text,
                refs=refs,
                content_hash=sha256(text.encode()).hexdigest(),
                invalidation_epoch=old.invalidation_epoch + int(clear),
            )
            db.execute(
                "INSERT INTO recap VALUES('mysoul',?,?)",
                (version.version, version.model_dump_json()),
            )
            db.execute("UPDATE recap_head SET version=? WHERE subject='mysoul'", (version.version,))
            return version

    def clear(self, expected_version: int):
        return self.publish(expected_version, "", [], clear=True)


class ContextAssembler:
    def __init__(self, recap: RecapStore, memory, task="", public_persona="A helpful companion."):
        self.recap, self.memory, self.task = recap, memory, task
        self.public_persona = public_persona

    async def build(self, scope: Scope, budget: ContextBudget) -> ContextBundle:
        # Deliberately no summary cache: every admission reads the committed head.
        version = self.recap.current()
        bundle = ContextBundle(scope=scope, task=self.task)
        bundle.instructions += "\n" + self.public_persona
        if scope.audience == "owner":
            bundle.recap = version.text
        if len(bundle.payload()) > budget.max_chars:
            raise ContextOverflow("Required instructions/task/Recap exceed context budget")
        try:
            hits = await self.memory.search(self.task, scope, 10)
        except MemoryUnavailable:
            bundle.recall_status = "unavailable"
            return bundle
        for hit in hits:
            if not hit.permitted(scope):
                continue
            candidate = bundle.model_copy(deep=True)
            candidate.evidence.append(hit)
            if len(candidate.payload()) <= budget.max_chars:
                bundle = candidate
        return bundle
