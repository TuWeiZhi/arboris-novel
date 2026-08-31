# Arboris 改进方案（治理闭环 + 检索增强 + 遗留）

> 本文档是对 Scriverse 设计思路（非代码）吸收后的落地设计。目标不是仿写 Scriverse，
> 而是补上 arboris 的核心缺口：**让 AI 产出变成作者可治理的资产**。
> 排序：核心主线（①→②→③）→ 次优先（④⑤）→ 更远（⑥⑦⑧⑨）→ 遗留（⑩）。

---

## 核心主线

### ① 记忆/设定的「证据 + 锁定 + 待确认」治理闭环

**目标**：AI 定稿时自动生成的设定/角色状态更新，变成「作者可确认、可锁定、可溯源」，防 AI 污染权威记忆。

**现状**
- `CanonEntry`（`models/canon.py`）：有 `status`/`hard_rule`/`valid_from_until`，**无 `evidence`、无 `locked`**。
- `CharacterState`（`models/memory_layer.py`）：AI 在 `FinalizeService._save_character_state` 直接写入，**无确认态、无锁定、无来源**。
- `Foreshadowing`：已有 `is_manual`/`ai_confidence`/`author_note`，**无 `locked`、无 `evidence`**。
- `ProjectMemory.global_summary`/`plot_arcs`：AI 自动写，`version` 字段仅乐观锁，无证据。

**方案**
1. `CanonEntry` 新增：`evidence`（JSON，`[{chapter_number, quote}]`）、`locked`（bool，默认 False）。
   `status` 扩展新增 `pending`（待确认）。**迁移**：Alembic 加列，均为可空/有默认，向后兼容。
2. `CharacterState` 新增：`confirmed`（bool，默认 True 以兼容存量）、`locked`（bool）、`source`（`manual`/`ai`）、`evidence`（JSON）。
   `FinalizeService` 写角色状态时：`source='ai'`、`confirmed=False`（待确认）。
3. `Foreshadowing` 新增：`locked`（bool）。`evidence` 已有 `ai_confidence`，不加独立 evidence（伏笔用 `ForeshadowingResolution` 的章节引用已够）。
4. **读路径**：`utils/character_state.get_project_raw_state_text` 默认只读 `confirmed=True` 的记录；未确认的仍保留（不丢数据），但标注。
5. **决策（不做）**：`ProjectMemory.global_summary` 保持自动（它是「摘要」不是「事实」，锁定意义小）；`plot_arcs` 的未回收伏笔继续以 `Foreshadowing` 表为权威源，不在 plot_arcs 里再造 evidence。

**契约变化**
- `CanonEntry`/`CharacterState`/`Foreshadowing` 新增可选字段 → schema/API 响应向后兼容（新增字段，不删旧）。
- `FinalizeService` 行为变化：角色状态由「直接权威」变「默认待确认」→ **这是行为变化，需在最终报告标注**。

**影响面**
- 必须修改：3 个 model + `finalize_service` + `character_state` 读路径 + canon/foreshadowing API schema。
- 需要验证：存量项目读路径不回退；定稿后角色状态不再直接进权威读路径。
- 仍待调查：前端 canon 编辑（⑩）与确认流如何联动。

**取舍**：只治理「权威事实」（CanonEntry）与「角色状态」（CharacterState）；摘要类自动更新保持不变，避免全量实体版本化（那是⑥）。

---

### ② 一致性/现实审核 → `review_items` 问题清单

**目标**：一致性检查（含现实常识审核）结果可持久化、可追踪、可闭环。

**现状**：`ConsistencyService.check_consistency` 返回 violations 后即结束，`get_violation_statistics` 是空桩；无落库、无前端展示。

**方案**
1. 新表 `review_items`：
   `id, project_id, chapter_number, item_type(consistency|realism|ooc), severity, category, title, description, evidence_json, suggestion, status(pending|resolved|ignored), resolution_note, created_at, updated_at`。
2. `ConsistencyService.check_consistency` 结果落库（新增参数 `persist: bool = True`；检查本身失败不落库）。`realism` 类别由现实审核维度产生。
3. API：
   - `GET /api/review/items?project_id=&status=&item_type=`
   - `PATCH /api/review/items/{id}`（body: `{status, resolution_note}`）
4. 前端：`NovelDetail` 新增「问题清单」section，逐条 `resolved`/`ignored`。

**契约变化**：新表 + 新 API（纯新增）；现有 `/api/review/consistency` 保持返回 violations，同时落库。

**影响面**：必须改 `consistency_service` + `review` router + 新 model/迁移；前端新增 section。

---

### ③ 角色身份一致性审计（OOC 检测）

**目标**：用已有的 8 维 DNA 档案做参照，检测本章角色行为/对话是否违背 DNA（OOC）。

**现状**：8 维 DNA 已在 `BlueprintCharacter.extra.dna_profile`（本次会话已实现 AI 生成），但仅作「生成参考」，无「审计」环节。

**方案**
1. 新服务 `character_identity_audit_service.py`：
   输入 = 本章正文 + 出场角色的 `dna_profile`（经 `writer_context_builder._build_character_profiles` 同类格式化）；
   LLM 输出 violations：`{character, dimension, severity, description, evidence_quote, suggestion}`。
2. 新端点 `POST /api/review/character-identity`（body: `{project_id, chapter_number, chapter_text}`），与 six-dimension/consistency 平级。
3. 结果落 `review_items`（`item_type='ooc'`）。
4. （可选，后续）接入 `PipelineOrchestrator` 的 `preset=enhanced/ultimate` 阶段。

**契约变化**：新服务 + 新端点（纯新增）。

---

## 次优先

### ④ 角色别名归一化

**目标**：同一角色多个称呼（"张三"/"三哥"/"张老板"）归一，检索/关系/伏笔按归一化名命中。

**现状**：`BlueprintCharacter.name` 单名，`CanonEntry.aliases` 有别名但无归一查询；`CharacterKnowledgeManager` 无归一。

**方案（轻量，不做独立表）**
1. 新增工具 `utils.name_normalize.normalize_name(text)`：去空白、统一常见称谓（哥/姐/老板/师傅等后缀可配置剥离）、小写（英文）。
2. `BlueprintCharacter` 新增 `aliases`（JSON，默认 list），写入 `extra.aliases` 而非新列（沿用现有 extra 惯例）。
3. 应用点：`WriterContextBuilder` 可见性判断、`CharacterKnowledgeManager.mention_character`、`Foreshadowing` 相关角色匹配、`KnowledgeRetrievalService` 检索词生成，统一走 `normalize_name` 比对。

**契约变化**：新增工具 + `aliases` 软字段（extra 内，无迁移）；检索行为变化（更宽松命中）。

**取舍**：不做独立 `character_names` 表（Scriverse 的归一表），arboris 项目级角色用 `extra.aliases` + 归一函数足够，避免过度设计。

---

### ⑤ 检索增强——关键词硬触发（修正为「小硬化」）

**现状（已核实）**：canon 检索**已经有关键词硬触发**：
- `CanonService._score_entry`：`hard_rule` 固定 100 分（强制选中）、关键词命中 title/aliases/keywords/tags 固定 80 分。
- `ChapterContextAssembler._get_canon_context` 已把 outline/summary/writing_notes/chapter_mission/characters/relationships 组装成 `query_text`。

**剩余缺口**：`select_relevant_entries` 的 `limit=12` 会**截断** hard_rule（若硬规则 > 12 条时，可能漏掉部分硬规则）。

**方案**
- 把「硬规则」与「关键词命中」分两路查询：硬规则无条件全量注入（不设 limit），关键词命中条目受 limit 约束。
- 改动点：`CanonService.select_relevant_entries` 拆成 `select_hard_rules`（无 limit）+ `select_relevant_entries`（关键词，受 limit），`build_prompt_context` 合并两者。

**契约变化**：canon 上下文注入内容可能增多（硬规则不再被截断）——行为增强，无破坏。

---

## 更远（P2，可缓）

### ⑥ 实体版本化（通用）
`entity_versions(entity_type, entity_id, version_no, snapshot_json, source, change_note)`；`CharacterState`/`CanonEntry` 变更时写快照。与①的 `source` 字段协同，做「可回滚」。**缓做**：先做①的确认/锁定，版本化按需再上。

### ⑦ 时间线多轨道 + time_sort
`TimelineEvent` 加 `track_name`（轨道名，默认主线）+ `time_sort`（float 相对排序）+ 内联 `causes_json`。**后端先行，前端看板缓做**。

### ⑧ 混合检索（关键词 + 向量融合）
在⑤的硬触发基础上，向量召回结果按关键词命中加权融合。**缓做**：⑤的硬触发已覆盖主要痛点，融合收益边际，等有真实漏检案例再上。

### ⑨ 读者画像数据驱动
`ReaderSimulatorService.READER_PROFILES` 改为从 seed/配置读取（导入 `参考资料/番茄读者画像 json` 为静态 seed）。**需数据源**：先做静态 seed，联网爬虫按需再接。

---

## 遗留

### ⑩ 前端编辑入口
- `hard_rule`：`CanonSection.vue` **已有 checkbox** ✓（无需做）。
- `realism_level`（小说宪法）：前端**无任何宪法编辑入口** → 需在 `WorldSettingSection` 或新增宪法编辑区加 `realism_level` 选择器（写实/半写实/低现实/自由）。
- `mission_constraints`（章节蓝图，现实审核章级覆盖）：`ChapterOutlineSection` 需加「本章现实约束 override/豁免域」编辑。
- `canon locked/evidence`（①新增字段）：`CanonSection.vue` 加 `locked` 开关 + `evidence` 展示。

---

## 实施顺序与验证

1. **①**（地基）→ ② → ③（主线，依赖①的字段但可并行做 schema）。
2. **④⑤**（检索侧，独立）。
3. **⑩**（前端，依赖①③的后端字段）。
4. **⑥⑦⑧⑨**（更远，视情况）。

每个改动：
- 后端：Alembic 迁移（若加列/加表）+ 单元/集成测试（`backend/tests`）。
- 前端：`npm run type-check` + `npm run build`。
- 全部完成后统一提交（复用既有 commit 授权流程）。

> 备注：Scriverse 为 AGPL-3.0，本方案只吸收设计思想，不复制其代码或表结构。
