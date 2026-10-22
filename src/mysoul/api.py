"""Loopback operator API. All private reads and mutations require local authorization."""

import asyncio
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from pydantic import Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from mysoul.config import Settings
from mysoul.domain import Contract, Goal
from mysoul.evolution import RegressionCase
from mysoul.model_settings import ModelUpdate
from mysoul.service import SoulService
from mysoul.storage import Conflict


class ChatInput(Contract):
    text: str = Field(min_length=1, max_length=8000)


class RecapInput(Contract):
    expected_version: int = Field(ge=0)
    text: str = Field(max_length=64000)
    refs: list[str] = []


class RevisionInput(Contract):
    expected_version: int = Field(ge=0)


class ProposalInput(Contract):
    text: str = Field(min_length=1, max_length=16000)
    evidence_refs: list[str]


class ReflectionInput(Contract):
    evidence_refs: list[str]


class CandidateInput(Contract):
    cases: list[RegressionCase] = Field(default_factory=list, max_length=4)


class ApprovalInput(Contract):
    expected_base_hash: str
    approved_candidate_hash: str


class RollbackInput(Contract):
    target_version: str


class ResumeInput(Contract):
    decision: Literal["continue", "replan", "abandon"]


class PersonaInput(Contract):
    public: str = Field(min_length=1, max_length=2000)


class LifeInput(Contract):
    mode: Literal["normal", "quiet", "focused"]
    fatigue: float = Field(ge=0, le=1, allow_inf_nan=False)


def operator_token(settings):
    path = settings.data_dir / "operator.token"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        with path.open("x", encoding="utf-8") as file:
            file.write(secrets.token_urlsafe(32))
    return path.read_text(encoding="utf-8").strip()


def create_app(settings: Settings | None = None, *, token=None, service=None):
    settings = settings or Settings()
    token = token or operator_token(settings)
    csrf = secrets.token_urlsafe(32)
    jobs: set[asyncio.Task] = set()

    @asynccontextmanager
    async def lifespan(app):
        async with service or SoulService(settings) as soul:
            app.state.soul = soul
            app.state.jobs = jobs
            stop = asyncio.Event()
            loop = asyncio.create_task(soul.run_loop(stop))
            yield
            stop.set()
            loop.cancel()
            await asyncio.gather(loop, return_exceptions=True)
            for task in jobs:
                task.cancel()
            if jobs:
                await asyncio.gather(*jobs, return_exceptions=True)

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])
    origins = {f"http://{host}:{settings.port}" for host in ("127.0.0.1", "localhost")}

    @app.middleware("http")
    async def response_policy(request, call_next):
        if request.method in {"POST", "PUT", "PATCH"}:
            if int(request.headers.get("content-length", "0")) > 128000:
                return JSONResponse({"detail": "Request exceeds byte limit"}, status_code=413)
            if len(await request.body()) > 128000:
                return JSONResponse({"detail": "Request exceeds byte limit"}, status_code=413)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        )
        return response

    async def authorize(request: Request):
        bearer = request.headers.get("authorization", "")
        if not secrets.compare_digest(bearer, "Bearer " + token):
            raise HTTPException(401, "Local operator authorization required")
        if request.method != "GET":
            if request.headers.get("origin") not in origins:
                raise HTTPException(403, "Origin denied")
            if not secrets.compare_digest(request.headers.get("x-csrf-token", ""), csrf):
                raise HTTPException(403, "CSRF token required")

    @app.exception_handler(Conflict)
    async def conflict_handler(request, exc):
        return JSONResponse(
            {"detail": "State changed or operation conflicts; reload before retrying"},
            status_code=409,
        )

    @app.exception_handler(PermissionError)
    async def permission_handler(request, exc):
        return JSONResponse({"detail": "Operation outside authorized scope"}, status_code=403)

    @app.exception_handler(KeyError)
    async def missing_handler(request, exc):
        return JSONResponse({"detail": "Resource not found"}, status_code=404)

    @app.exception_handler(ValueError)
    async def value_handler(request, exc):
        return JSONResponse({"detail": "Invalid input or unavailable capability"}, status_code=400)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request, exc):
        # Pydantic's default error includes input values, including submitted credentials.
        return JSONResponse({"detail": "输入格式不正确，请检查字段内容。"}, status_code=422)

    @app.get("/api/model", dependencies=[Depends(authorize)])
    async def model_settings(request: Request):
        return request.app.state.soul.model_configuration.public()

    @app.post("/api/model", dependencies=[Depends(authorize)])
    async def configure_model(body: ModelUpdate, request: Request):
        return await request.app.state.soul.configure_model(body)

    @app.post("/api/model/test", dependencies=[Depends(authorize)])
    async def probe_model(body: ModelUpdate, request: Request):
        return await request.app.state.soul.probe_model(body)

    @app.get("/")
    async def index():
        return FileResponse(Path(__file__).parent / "web/index.html")

    @app.get("/app.js")
    async def javascript():
        return FileResponse(Path(__file__).parent / "web/app.js", media_type="text/javascript")

    @app.get("/style.css")
    async def stylesheet():
        return FileResponse(Path(__file__).parent / "web/style.css", media_type="text/css")

    @app.get("/conversation.mjs")
    async def conversation_module():
        return FileResponse(
            Path(__file__).parent / "web/conversation.mjs", media_type="text/javascript"
        )

    @app.get("/vendor/markdown-it.min.js")
    async def markdown_vendor():
        return FileResponse(
            Path(__file__).parent / "web/vendor/markdown-it.min.js", media_type="text/javascript"
        )

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    guard = [Depends(authorize)]

    @app.get("/api/session", dependencies=guard)
    async def session():
        return {"csrf": csrf}

    @app.get("/api/status", dependencies=guard)
    async def status():
        return app.state.soul.status()

    @app.post("/api/chat", dependencies=guard)
    async def chat(body: ChatInput):
        return await app.state.soul.owner_message(body.text)

    @app.post("/api/recap", dependencies=guard)
    async def recap(body: RecapInput):
        return app.state.soul.recap.publish(body.expected_version, body.text, body.refs)

    @app.post("/api/recap/clear", dependencies=guard)
    async def clear(body: RevisionInput):
        return app.state.soul.recap.clear(body.expected_version)

    @app.get("/api/recap/history", dependencies=guard)
    async def history():
        return app.state.soul.recap.history()

    @app.get("/api/evidence", dependencies=guard)
    async def evidence():
        with app.state.soul.store.lock:
            rows = app.state.soul.store.db.execute(
                "SELECT body FROM evidence ORDER BY rowid DESC LIMIT 100"
            ).fetchall()
        import json

        return [json.loads(r[0]) for r in rows]

    @app.post("/api/persona", dependencies=guard)
    async def persona(body: PersonaInput):
        app.state.soul.store.put("config", "persona", body.model_dump())
        return body

    @app.post("/api/life", dependencies=guard)
    async def life(body: LifeInput):
        soul = app.state.soul
        state = soul.store.load_subject()
        state.mode, state.fatigue = body.mode, body.fatigue
        soul.store.save_transition(state.dispatch_epoch, state)
        return state

    async def background(coroutine):
        try:
            await coroutine
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            app.state.soul.store.put(
                "job_error", __import__("uuid").uuid4().hex, {"error": type(exc).__name__}
            )

    def launch(coroutine):
        task = asyncio.create_task(background(coroutine))
        jobs.add(task)
        task.add_done_callback(jobs.discard)

    @app.post("/api/goals", dependencies=guard, status_code=202)
    async def start_goal(body: ChatInput):
        if jobs or app.state.soul.admission.busy:
            raise Conflict("Foreground task already running")
        goal = Goal(objective=body.text)
        app.state.soul.store.save_goal(goal)
        launch(app.state.soul.start_goal(goal))
        return {"goal_id": goal.id, "status": "queued"}

    @app.post("/api/goals/{goal_id}/cancel", dependencies=guard)
    async def cancel(goal_id: str):
        app.state.soul.executor.cancel(goal_id)
        return {"status": "cancelled"}

    @app.post("/api/activities/{activity_id}/resume", dependencies=guard, status_code=202)
    async def resume(activity_id: str, body: ResumeInput):
        soul = app.state.soul
        activity = soul.store.activity(activity_id)
        if (jobs or soul.admission.busy or activity.status != "suspended"
                or soul.store.goal(activity.goal_id).cancelled):
            raise Conflict("Activity cannot resume")
        launch(soul.executor.resume(activity_id, body.decision))
        return {"status": "queued"}

    @app.get("/api/effects/{action_id}", dependencies=guard)
    async def effect(action_id: str):
        result = app.state.soul.store.effect(action_id)
        if not result:
            raise KeyError(action_id)
        return result

    @app.post("/api/effects/{action_id}/reconcile", dependencies=guard)
    async def reconcile(action_id: str):
        soul = app.state.soul
        return await soul.effects.reconcile(action_id, soul.phone.result)

    @app.get("/api/skills", dependencies=guard)
    async def skills():
        soul = app.state.soul
        proposals = soul.store.all("proposal")
        for proposal in proposals:
            proposal["diff"] = soul.skills.diff(proposal["id"])
        return {
            "active": soul.skills.active(),
            "proposals": proposals,
            "tests": soul.store.all("skill_test"),
            "versions": soul.store.all("skill_version"),
        }

    @app.post("/api/skills/propose", dependencies=guard)
    async def propose(body: ProposalInput):
        return app.state.soul.skills.propose(body.text, body.evidence_refs)

    @app.post("/api/reflection", dependencies=guard)
    async def reflect(body: ReflectionInput):
        return await app.state.soul.reflect(body.evidence_refs)

    @app.post("/api/skills/rollback", dependencies=guard)
    async def rollback(body: RollbackInput):
        return app.state.soul.skills.rollback("work", body.target_version)

    @app.post("/api/skills/{proposal_id}/test", dependencies=guard)
    async def test_candidate(proposal_id: str, body: CandidateInput):
        return await app.state.soul.test_candidate(proposal_id, body.cases or None)

    @app.post("/api/skills/{proposal_id}/approve", dependencies=guard)
    async def approve(proposal_id: str, body: ApprovalInput):
        return app.state.soul.skills.activate(
            proposal_id, body.expected_base_hash, body.approved_candidate_hash
        )

    @app.post("/api/skills/{proposal_id}/reject", dependencies=guard)
    async def reject(proposal_id: str):
        return app.state.soul.skills.reject(proposal_id)

    return app
