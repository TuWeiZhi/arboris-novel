"""服务层测试：角色状态、一致性检查、缓存。"""
import pytest
from types import SimpleNamespace
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.chapter_context_assembler import (
    ChapterContextAssembler,
    _check_embedding_compatibility,
)
from app.services.canon_service import CanonService
from app.services.realism_service import resolve_realism_config, render_realism_section
from app.services.novel_service import NovelService
from app.models.canon import CanonEntry
from app.models.constitution import NovelConstitution
from app.models.chapter_blueprint import ChapterBlueprint
from app.models.novel import BlueprintCharacter
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


class TestRealismService:

    async def test_no_constitution_disabled(self, session: AsyncSession):
        config = await resolve_realism_config(session, "p-none")
        assert config.enabled is False
        assert render_realism_section(config) == ""

    async def test_global_realistic_enabled_without_element_rules(self, session: AsyncSession):
        session.add(NovelConstitution(project_id="p-real", realism_level="写实"))
        await session.flush()

        config = await resolve_realism_config(session, "p-real")
        assert config.enabled is True
        assert config.effective_strength == "critical"
        assert "未配置自定义现实规则" in config.element_rules_text
        assert "现实常识一致性" in render_realism_section(config)

    async def test_element_rules_filtered_by_chapter_and_exempt_domain(self, session: AsyncSession):
        session.add(NovelConstitution(project_id="p-elem", realism_level="写实"))
        session.add(CanonEntry(
            project_id="p-elem",
            category="physics",
            title="人靠嘴吃饭",
            content="进食必须通过口腔。",
            hard_rule=True,
        ))
        session.add(CanonEntry(
            project_id="p-elem",
            category="biology",
            title="光合作用",
            content="特殊种族可光合作用。",
            hard_rule=True,
            valid_from_chapter=5,
        ))
        session.add(ChapterBlueprint(
            project_id="p-elem",
            chapter_number=1,
            mission_constraints={"realism_exempt_domains": ["biology"]},
        ))
        await session.flush()

        config = await resolve_realism_config(session, "p-elem", chapter_number=1)
        categories = [entry.category for entry in config.element_rules]
        # biology 被本章豁免；即便不豁免，也因 valid_from_chapter=5 在第1章不生效
        assert "physics" in categories
        assert "biology" not in categories
        assert "physics" in config.element_rules_text

    async def test_chapter_override_off_disables_even_with_global(self, session: AsyncSession):
        session.add(NovelConstitution(project_id="p-off", realism_level="写实"))
        session.add(ChapterBlueprint(
            project_id="p-off",
            chapter_number=2,
            mission_constraints={"realism_override": "off"},
        ))
        await session.flush()

        config = await resolve_realism_config(session, "p-off", chapter_number=2)
        assert config.enabled is False
        assert render_realism_section(config) == ""

    async def test_moderate_level_renders_major(self, session: AsyncSession):
        session.add(NovelConstitution(project_id="p-mixed", realism_level="半写实"))
        await session.flush()

        config = await resolve_realism_config(session, "p-mixed")
        assert config.enabled is True
        assert config.effective_strength == "major"
        assert "major" in render_realism_section(config)


class TestCharacterDNA:

    async def test_get_character_not_found(self, session: AsyncSession):
        service = NovelService(session)
        assert await service.get_character("p-none", "不存在") is None

    async def test_set_character_dna_preserves_extra(self, shared_engine):
        from sqlalchemy.ext.asyncio import async_sessionmaker
        factory = async_sessionmaker(shared_engine, expire_on_commit=False)
        async with factory() as s:
            s.add(BlueprintCharacter(
                project_id="p-dna",
                name="李明",
                identity="程序员",
                personality="内向",
                extra={"alias": "明哥"},
            ))
            await s.flush()

            service = NovelService(s)
            character = await service.set_character_dna(
                "p-dna",
                "李明",
                {"core_fear": "害怕失败", "inner_desire": "渴望被认可"},
            )
            assert character is not None
            assert character.extra["alias"] == "明哥"  # 保留原有 extra 列中的键
            assert character.extra["extra"]["dna_profile"]["core_fear"] == "害怕失败"
            await s.rollback()  # 隔离清理，避免污染共享引擎

    async def test_set_character_dna_not_found_returns_none(self, session: AsyncSession):
        service = NovelService(session)
        assert await service.set_character_dna("p-none", "不存在", {"a": "b"}) is None
