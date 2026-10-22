from mysoul.config import Settings
from mysoul.domain import Goal, StepDecision
from mysoul.service import SoulService


async def test_real_workspace_artifact_and_tool_feedback(tmp_path):
    async with SoulService(Settings(data_dir=tmp_path)) as soul:
        soul.model.steps.extend(
            [
                StepDecision(
                    tool="write_file", arguments={"path": "report.txt", "text": "measured result"}
                ),
                StepDecision(tool="read_file", arguments={"path": "report.txt"}),
                StepDecision(done=True),
            ]
        )
        activity = await soul.start_goal(Goal(objective="write and verify a report"))
        assert activity.status == "completed"
        assert (tmp_path / "workspace/report.txt").read_text() == "measured result"
        assert "measured result" in soul.model.payloads[-1]
        assert len(activity.effect_ids) == 2
