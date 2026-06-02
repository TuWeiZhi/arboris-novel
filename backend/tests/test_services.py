"""服务层测试：角色状态、一致性检查、缓存。"""
import pytest
from types import SimpleNamespace
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.chapter_context_assembler import (
    ChapterContextAssembler,
    _check_embedding_compatibility,
)
from app.services.canon_service import CanonService
from app.models.canon import CanonEntry
from app.models.project_memory import ProjectMemory
from app.models.memory_layer import CharacterState
from app.utils.character_state import get_project_raw_state_text


class TestCharacterState:

    async def test_empty_project(self, session: AsyncSession):
        assert await get_project_raw_state_text(session, "nonexistent") is None

    async def test_from_project_memory_extra(self, session: AsyncSession):
        session.add(ProjectMemory(
            project_id="p1",
            global_summary="test",
            extra={"raw_state_text": "hero: healthy"},
        ))
        await session.flush()
        assert await get_project_raw_state_text(session, "p1") == "hero: healthy"

    async def test_fallback_to_character_state(self, session: AsyncSession):
        session.add(CharacterState(
            project_id="p2",
            character_name="hero",
            chapter_number=1,
            extra={"raw_state_text": "hero: wounded"},
        ))
        await session.flush()
        assert await get_project_raw_state_text(session, "p2") == "hero: wounded"

    async def test_all_aggregate_priority(self, session: AsyncSession):
        session.add(CharacterState(
            project_id="p3",
            character_name="__all__",
            chapter_number=2,
            extra={"raw_state_text": "all: summary"},
        ))
        session.add(CharacterState(
            project_id="p3",
            character_name="hero",
            chapter_number=1,
            extra={"raw_state_text": "hero: details"},
        ))
        await session.flush()
        assert await get_project_raw_state_text(session, "p3") == "all: summary"


class TestChapterContextAssembler:

    async def test_allowed_new_characters_are_visible_after_mission(
        self,
        session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ):
        assembler = ChapterContextAssembler(
            session=session,
            llm_service=SimpleNamespace(),
            prompt_service=SimpleNamespace(),
        )

        async def fake_generate_chapter_mission(**_kwargs):
            return {"macro_beat": "intro", "allowed_new_characters": ["NewChar"]}

        monkeypatch.setattr(
            assembler,
            "_generate_chapter_mission",
            fake_generate_chapter_mission,
        )

        config = SimpleNamespace(
            enable_constitution=False,
            enable_persona=False,
            enable_foreshadowing=False,
            enable_faction=False,
            enable_memory=False,
            enable_rag=False,
            rag_mode="simple",
            version_count=1,
        )
        blueprint = {
            "characters": [
                {"name": "OldChar", "identity": "old"},
                {"name": "NewChar", "identity": "new"},
            ],
            "relationships": [
                {"from": "OldChar", "to": "NewChar", "description": "hidden"}
            ],
        }

        ctx = await assembler.assemble(
            project_id="p-new-character",
            chapter_number=1,
            user_id=1,
            writing_notes="保持悬念",
            outlines_map={},
            chapters=[],
            blueprint_dict=blueprint,
            project_schema=SimpleNamespace(),
            outline_title="开端",
            outline_summary="第一章开始",
            config=config,
            visibility_context={},
            chapter_mission_inputs={
                "introduced_characters": [],
                "all_characters": ["OldChar", "NewChar"],
            },
        )

        visible_names = [
            character["name"]
            for character in ctx.writer_blueprint.get("characters", [])
        ]
        assert visible_names == ["NewChar"]
        assert "NewChar" not in ctx.forbidden_characters
        assert "OldChar" in ctx.forbidden_characters

    async def test_canon_context_is_injected_into_prompt(
        self,
        session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ):
        session.add(CanonEntry(
            project_id="p-canon",
            category="rule",
            title="雾钟",
            content="雾钟响三次后，城门必须关闭。",
            keywords=["雾钟"],
            hard_rule=True,
            status="active",
            visibility="pov_safe",
        ))
        await session.flush()

        assembler = ChapterContextAssembler(
            session=session,
            llm_service=SimpleNamespace(),
            prompt_service=SimpleNamespace(),
        )

        async def fake_generate_chapter_mission(**_kwargs):
            return {"macro_beat": "alarm", "allowed_new_characters": []}

        monkeypatch.setattr(
            assembler,
            "_generate_chapter_mission",
            fake_generate_chapter_mission,
        )

        config = SimpleNamespace(
            enable_constitution=False,
            enable_persona=False,
            enable_foreshadowing=False,
            enable_faction=False,
            enable_memory=False,
            enable_rag=False,
            rag_mode="simple",
            version_count=1,
        )

        ctx = await assembler.assemble(
            project_id="p-canon",
            chapter_number=3,
            user_id=1,
            writing_notes="雾钟第一次响起。",
            outlines_map={},
            chapters=[],
            blueprint_dict={"characters": [], "relationships": []},
            project_schema=SimpleNamespace(),
            outline_title="城门之前",
            outline_summary="主角听见雾钟。",
            config=config,
            visibility_context={},
            chapter_mission_inputs={
                "introduced_characters": [],
                "all_characters": [],
            },
        )

        assert ctx.canon_context is not None
        assert "雾钟响三次后" in ctx.canon_context
        assert "小说圣经 / Canon" in ctx.prompt_input


class TestCanonService:

    async def test_hard_rule_and_keyword_matches_respect_chapter_window(
        self,
        session: AsyncSession,
    ):
        session.add_all([
            CanonEntry(
                project_id="p-canon-service",
                category="rule",
                title="星门限制",
                content="星门每天只能开启一次。",
                hard_rule=True,
                status="active",
                visibility="pov_safe",
            ),
            CanonEntry(
                project_id="p-canon-service",
                category="item",
                title="黑钥",
                content="黑钥可以打开旧城地下门。",
                keywords=["黑钥"],
                status="active",
                visibility="pov_safe",
                valid_from_chapter=2,
                valid_until_chapter=5,
            ),
            CanonEntry(
                project_id="p-canon-service",
                category="location",
                title="旧港",
                content="旧港在第十章后被封锁。",
                keywords=["旧港"],
                status="active",
                visibility="pov_safe",
                valid_from_chapter=10,
            ),
        ])
        await session.flush()

        service = CanonService(session)
        context = await service.build_prompt_context(
            "p-canon-service",
            chapter_number=3,
            query_text="主角握住黑钥。",
        )

        assert context is not None
        assert "星门每天只能开启一次" in context
        assert "黑钥可以打开旧城地下门" in context
        assert "旧港在第十章后被封锁" not in context


class TestEmbeddingCompatibility:

    async def test_embedding_compatibility_uses_vector_store_contract(self):
        class FakeLLMService:
            def __init__(self):
                self.dimension_model = None

            async def get_embedding_model_name(self):
                return "nomic-embed-text:latest"

            async def get_embedding_dimension(self, model=None):
                self.dimension_model = model
                return 768

        class FakeVectorStore:
            def __init__(self):
                self.called_with = None

            async def check_model_compatibility(self, current_model, current_dimension):
                self.called_with = (current_model, current_dimension)
                return {
                    "compatible": True,
                    "current_model": current_model,
                    "current_dimension": current_dimension,
                }

        llm_service = FakeLLMService()
        vector_store = FakeVectorStore()

        result = await _check_embedding_compatibility(vector_store, llm_service)

        assert llm_service.dimension_model == "nomic-embed-text:latest"
        assert vector_store.called_with == ("nomic-embed-text:latest", 768)
        assert result["compatible"] is True
