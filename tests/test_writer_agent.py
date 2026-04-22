from __future__ import annotations

import unittest
from unittest.mock import patch

from src.agents.writer_agent import WriterAgent
from src.schemas import (
    ChapterRollup,
    DetailOutline,
    InternalReasoningPackage,
    ProjectRecord,
    SceneBrief,
    SceneDraft,
    WriterContext,
    WriterPacket,
)
from src.schemas.tool_io import RagSearchResult


def build_project() -> ProjectRecord:
    return ProjectRecord(
        project_id="demo",
        title="Writer Agent Demo",
        premise="A fugitive disciple escapes a dying sect.",
        genre=["xianxia"],
        tone="tense",
    )


def build_detail_outline() -> DetailOutline:
    return DetailOutline(
        chapter_id=6,
        title="Frost Gate",
        chapter_goal="Break through the frozen gate and confirm the inheritance clue.",
        internal_reasoning_package=InternalReasoningPackage(
            current_progress_assessment="The protagonist is transitioning from pursuit to first counterplay.",
            outline_alignment=["This chapter should turn flight into deliberate risk."],
            foreshadowing_targets=["The bronze token is reacting more strongly."],
            continuity_risks=["Do not forget the lingering rib injury."],
        ),
        writer_packet=WriterPacket(
            chapter_id=6,
            chapter_title="Frost Gate",
            chapter_goal="Break through the frozen gate and confirm the inheritance clue.",
            scene_briefs=[
                SceneBrief(
                    scene_id=1,
                    title="Snow Ridge Standoff",
                    location="Snow ridge",
                    characters=["Lin Ye", "Su Wan"],
                    objective="Cross the ridge while hiding their injuries and intentions.",
                    must_include=["The bronze token heats under Lin Ye's palm."],
                    avoid=["Resolve the inheritance mystery too early."],
                    desired_length=1500,
                ),
                SceneBrief(
                    scene_id=2,
                    title="Frozen Gate",
                    location="Frozen cavern gate",
                    characters=["Lin Ye", "Su Wan"],
                    objective="Open the gate at a cost and end on a fresh threat.",
                    must_include=["The gate responds to blood and spirit pressure."],
                    avoid=["Reveal the mastermind."],
                    desired_length=1600,
                ),
            ],
            style_rules=["Keep scenes grounded and tactile."],
            continuity_notes=["Lin Ye is still carrying a rib injury from the ambush."],
            forbidden_reveals=["Do not reveal the mastermind."],
            retrieved_context=[],
        ),
        ending_hook="A second pulse answers from deeper inside the cavern.",
        user_constraints=["Keep the prose immersive."],
    )


class FakeContextAssembler:
    def build_writer_context(self, **_: object) -> WriterContext:
        detail_outline = build_detail_outline()
        return WriterContext(
            project_meta={
                "project_id": "demo",
                "title": "Writer Agent Demo",
                "premise": "A fugitive disciple escapes a dying sect.",
                "genre": ["xianxia"],
                "tone": "tense",
            },
            chapter_id=detail_outline.chapter_id,
            title=detail_outline.title,
            chapter_goal=detail_outline.chapter_goal,
            writer_packet=detail_outline.writer_packet.model_dump(mode="json")
            | {
                "retrieved_context": [
                    "Lin Ye still carries the heated bronze token from the ridge pursuit.",
                    "Su Wan is hiding how much the blood oath is constraining her.",
                ]
            },
            ending_hook=detail_outline.ending_hook,
            user_constraints=detail_outline.user_constraints,
            story_facts=[
                "Lin Ye's ribs are still injured from the last ambush.",
                "The bronze token reacts to his blood.",
                "The sect elders are close behind.",
            ],
            character_snapshot=[
                "Lin Ye: injured ribs; carrying the bronze token; under pursuit.",
                "Su Wan: blood oath under pressure; helping Lin Ye hide their trail.",
            ],
            world_snapshot=[
                "The snow ridge path is unstable and exposed.",
                "The frozen gate is tied to an old inheritance vault.",
            ],
            active_threads=[
                "Who left the inheritance behind is still unknown.",
                "The blood oath may force Su Wan to betray someone soon.",
            ],
            style_rules=["Keep scenes grounded and tactile."],
            source_chunk_ids=["0004_01", "0005_02"],
        )


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.scene_counter = 0
        self.settings = type(
            "Settings",
            (),
            {"writer_model": "fake-writer"},
        )()

    def chat_model(self, **kwargs):
        response_model = kwargs["response_model"]
        self.calls.append(response_model.__name__)
        if response_model is SceneDraft:
            self.scene_counter += 1
            return SceneDraft(
                scene_id=self.scene_counter,
                title=f"Scene {self.scene_counter}",
                markdown_body=(
                    f"# Scene {self.scene_counter}\n\n"
                    f"Scene prose {self.scene_counter}. The moment breathes before the next move."
                ),
                scene_summary=f"Scene {self.scene_counter} summary.",
                new_facts=[f"Scene fact {self.scene_counter}"],
                foreshadow_candidates=[f"Scene foreshadow {self.scene_counter}"],
            )
        if response_model is ChapterRollup:
            return ChapterRollup(
                summary="Lin Ye reaches the frozen gate and opens it at a cost.",
                new_facts=["The frozen gate requires blood and spirit pressure."],
                foreshadow_candidates=["A deeper pulse answers from the inheritance vault."],
            )
        raise AssertionError(f"Unexpected response_model: {response_model}")


class WriterAgentTestCase(unittest.TestCase):
    def test_writer_agent_writes_scene_by_scene_and_rolls_up_chapter(self) -> None:
        agent = WriterAgent(client=FakeClient(), context_assembler=FakeContextAssembler())
        detail_outline = build_detail_outline()

        with patch.object(WriterAgent, "_retrieve_context", return_value=RagSearchResult(query="", hits=[])):
            artifact = agent.write_chapter(project=build_project(), detail_outline=detail_outline)

        self.assertIn("Scene prose 1.", artifact.markdown_body)
        self.assertIn("Scene prose 2.", artifact.markdown_body)
        self.assertNotIn("# Scene 1", artifact.markdown_body)
        self.assertEqual(
            artifact.summary,
            "Lin Ye reaches the frozen gate and opens it at a cost.",
        )
        self.assertEqual(
            artifact.referenced_chunks,
            ["0004_01", "0005_02"],
        )
        self.assertIn("Scene fact 1", artifact.new_facts)
        self.assertIn("The frozen gate requires blood and spirit pressure.", artifact.new_facts)
        self.assertEqual(agent.client.calls, ["SceneDraft", "SceneDraft", "ChapterRollup"])


if __name__ == "__main__":
    unittest.main()
