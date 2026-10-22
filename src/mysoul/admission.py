"""Single-subject coroutine admission; owner epoch preemption stays independent."""

import asyncio
from contextlib import contextmanager
from functools import wraps

from mysoul.storage import Conflict


class SubjectAdmission:
    def __init__(self):
        self.owner = None
        self.kind = None
        self.depth = 0

    @property
    def busy(self):
        return self.owner is not None

    def available(self):
        return self.owner is None or self.owner is asyncio.current_task()

    @contextmanager
    def hold(self, kind):
        if not self.available():
            raise Conflict("One subject activity at a time; wait for current work to settle")
        self.owner = asyncio.current_task()
        self.kind = kind
        self.depth += 1
        try:
            yield
        finally:
            self.depth -= 1
            if not self.depth:
                self.owner = self.kind = None


def admitted(kind):
    def decorate(method):
        @wraps(method)
        async def invoke(self, *args, **kwargs):
            with self.admission.hold(kind):
                return await method(self, *args, **kwargs)

        return invoke

    return decorate
