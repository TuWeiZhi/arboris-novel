---
epic: null
---

# feat-governance: 治理闭环 + 检索增强 + 遗留

> 跨会话工作游标。恢复工作时先读本文档 + `docs/improvement-plan.md`（全量设计方案）。

## 目标

把 arboris 从「AI 生成优先」补成「AI 产出可治理」：让 AI 定稿时自动生成的设定/状态变成作者可确认、可锁定、可溯源的资产，并让一致性/现实审核结果可闭环。

完整方案与逐项设计见 **`docs/improvement-plan.md`**（已写，覆盖 ①—⑩）。

## 现场（当前事实）

### 已完成

**①「证据 + 锁定 + 待确认」地基**（已实现，未提交）：

| 文件 | 改动 |
|---|---|
| `backend/app/models/canon.py` | `CanonEntry` + `locked`(bool) + `evidence`(JSON) |
| `backend/app/models/foreshadowing.py` | `Foreshadowing` + `locked`(bool) |
| `backend/app/models/memory_layer.py` | `CharacterState` + `confirmed`/`locked`/`source`/`evidence` |
| `backend/alembic/versions/c1d2e3f4a5b6_add_governance_columns.py` | 迁移（加列，带 server_default） |
| `backend/app/services/canon_service.py` | `_apply_entry_data` allowlist 加 `locked`/`evidence` |
| `backend/app/api/routers/projects.py` | `CanonEntryPayload` 加 `locked`/`evidence` |
| `backend/app/services/finalize_service.py` | 定稿角色状态写 `raw_state_source='ai'`、`raw_state_confirmed=False`、`raw_state_evidence=[{chapter_number}]` |

### 关键事实修正（重要，恢复时务必知道）

1. **角色状态读取真源是 `ProjectMemory.extra["raw_state_text"]`（文本 blob），不是结构化的 `CharacterState` 表**。`CharacterState` 表只是 `get_project_raw_state_text` 的回退路径，由 `MemoryLayerService` 写（`services/memory_layer_service.py:108`）。
   → 因此「待确认」标记做在了 `raw_state_text` 所在层（`ProjectMemory.extra`），`CharacterState` 新字段仅作前向兼容。
2. **canon 关键词硬触发已存在**：`CanonService._score_entry` 中 `hard_rule` 固定 100 分、关键词命中 80 分；`ChapterContextAssembler._get_canon_context` 已组装 query_text。**⑤ 只剩「硬规则不被 `limit=12` 截断」这个小硬化**，不是从零实现。
3. `Faction` 模型已支持 `FactionMember`（role/rank/loyalty，多对多）——**不需要引入 Scriverse 的组织系统**。

### 测试基线

- 后端：`backend/` 下 `python -m pytest tests/ -q` → **26 passed**（含之前现实审核 5 个 + 角色 DNA 3 个）。
- 前端：`frontend/` 下 `npm run type-check`、`npm run build` 均通过（最近一次验证）。

## 边界

- **范围内**：`docs/improvement-plan.md` 的 ①—⑩ 全部。
- **明确不做**：照搬 Scriverse 的分析任务族 / 组织系统 / 多轨道时间线 / 角色合并 / SQLite FTS；不复制 Scriverse 代码（AGPL-3.0）。

## 证据

- 设计：`docs/improvement-plan.md`
- 迁移：`backend/alembic/versions/c1d2e3f4a5b6_add_governance_columns.py`
- 测试：26 passed（`backend/tests`）
- **未提交**：① 的模型/迁移/服务改动 + `docs/improvement-plan.md` + 本工作游标，均在 working tree。

## 验收（逐项）

- **①**：CanonEntry/Foreshadowing 可 `locked` 锁定、带 `evidence`；定稿角色状态默认 `confirmed=False`，作者可确认转权威；迁移可 `upgrade/downgrade`。
- **②**：`review_items` 表 + `ConsistencyService` 落库 + `GET/PATCH /api/review/items` + 前端问题清单。
- **③**：`POST /api/review/character-identity` 用 8 维 DNA 检测 OOC，结果落 review_items。
- **④**：`normalize_name` 工具 + `extra.aliases`，检索/关系/伏笔按归一化名命中。
- **⑤**：hard_rule 全量注入（不被 limit 截断）。
- **⑥⑦⑧⑨**：见设计文档（更远，可缓）。
- **⑩**：前端 canon `locked`/`evidence` UI；宪法 `realism_level` 选择器；章节蓝图 `mission_constraints` 编辑。

## 状态与未决

- **① 进度**：地基完成；**剩**「作者确认端点」+ 前端（属⑩）。
- **②③④⑤⑥⑦⑧⑨⑩**：未开始。
- **未决问题**：
  1. ① 的「确认」端点放哪：canon 复用 `status`（加 `pending` 态）？raw_state 需要新端点（如 `POST /api/projects/{id}/characters/state/confirm`）？**建议**：canon 用 `status='pending'`，raw_state 加一个轻量确认端点。
  2. 前端宪法编辑入口（`realism_level`）目前**无任何 UI**，需新建编辑区（可能在 `WorldSettingSection` 或新建）。
  3. 是否按项逐个 commit（当前 ① 未提交，与设计文档混在一起）——**建议**：① 收尾后单独提交，②③ 各自提交。
