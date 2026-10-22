import httpx

from mysoul.config import Settings
from mysoul.domain import Event, Scope, StepDecision
from mysoul.model import ReplayModel
from mysoul.phone.napcat import NapCatPhone
from mysoul.service import SoulService


async def test_opt_in_group_reply_uses_dispatcher_and_scoped_provider_payload(tmp_path):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"retcode": 0, "data": {"message_id": 123}})

    settings = Settings(
        data_dir=tmp_path, backend="napcat", owner_id="42", allowed_groups={"g"}, send_enabled=True
    )
    phone = NapCatPhone(
        "http://127.0.0.1:3000", "key", settings, transport=httpx.MockTransport(handler)
    )
    model = ReplayModel(
        [StepDecision(tool="qq_send", arguments={"text": "public reply"}), StepDecision(done=True)]
    )
    async with SoulService(settings, model=model, phone=phone) as soul:
        soul.recap.publish(0, "PRIVATE-CANARY", [])
        outcome = await soul.receive(
            Event(
                content="@mysoul hello",
                scope=Scope(audience="group", conversation="g"),
                dedup_key="g1",
            )
        )
        assert outcome["choice"] == "sent"
        assert len(calls) == 1
        assert all("PRIVATE-CANARY" not in payload for payload in model.payloads)
        assert soul.status()["effects"][0]["outcome"] == "confirmed"
