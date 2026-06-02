# 长篇小说生产线待改进路线图

本文档用于把外部方法论中的可借鉴点沉淀为 Arboris 的可执行改进项。目标不是再增加一个孤立的生成器，而是把现有的蓝图、RAG、记忆、伏笔、审计和人工定稿流程收束成一条更稳定的长篇创作生产线。

## 现状判断

项目已经具备长篇写作流水线的基础骨架：

- `PipelineOrchestrator` 负责统一编排章节生成、评审、优化和一致性检查。
- `ChapterContextAssembler` 负责组装蓝图、上章摘要、章节导演脚本、RAG、项目记忆和结构化记忆。
- `KnowledgeRetrievalService` 已有“两层 RAG”：检索词生成、向量检索、LLM 过滤、POV 可见性裁剪。
- `ProjectMemory`、`ChapterSnapshot`、`FinalizeService` 已形成“定稿后更新全局摘要、角色状态、剧情线和向量库”的闭环。
- `Foreshadowing`、`CausalChain`、`TimelineEvent` 已具备伏笔、因果和时间线管理的雏形。

主要缺口是：权威设定没有统一的“小说圣经”入口；检索仍偏向向量相似度，缺少关键词硬触发；事件记忆还不是可审计的时序知识图谱；周期审计与人工定稿状态还没有被产品流程强约束。

## P0：统一小说圣经 / Lorebook

### 目标

建立项目级 Canon 层，作为世界规则、人物状态、地点、势力、物品、线索、风格约束的权威来源。每次章节生成只注入相关 canon 摘录，而不是把整个蓝图粗暴塞进 prompt。

### 建议数据模型

新增 `CanonEntry`，也可先用 `ProjectMemory.extra["canon_entries"]` 做轻量 MVP。

推荐字段：

| 字段 | 说明 |
| --- | --- |
| `project_id` | 所属项目 |
| `category` | `character/location/faction/rule/item/clue/event/style` |
| `title` | 条目名 |
| `content` | 原子化设定正文 |
| `aliases` | 别名、简称、旧称 |
| `keywords` | 硬触发关键词 |
| `tags` | 主题标签 |
| `status` | `active/changed/retired/spoiler` |
| `valid_from_chapter` | 从第几章开始成立 |
| `valid_until_chapter` | 到第几章结束，空值表示仍然有效 |
| `last_verified_chapter` | 最近一次人工确认章节 |
| `hard_rule` | 是否作为强约束注入 |
| `visibility` | `author_only/pov_safe/public` |
| `source` | 来源：蓝图、人工录入、定稿抽取、审计修正 |
| `relations` | 相关人物、地点、势力、物品、线索 |

### 服务改造

- 新增 `CanonService`：负责 CRUD、关键词触发、按章节有效性筛选、硬规则导出。
- 在 `FinalizeService` 定稿后抽取候选 canon 更新，但默认进入“待确认”状态，避免 AI 自动污染权威设定。
- 在 `ChapterContextAssembler` 中新增 `canon_context`，优先注入：
  1. 本章大纲/写作指令命中的硬规则；
  2. POV 角色相关的人物状态；
  3. 本章地点、势力、道具、线索条目；
  4. 即将到期或必须回收的伏笔条目。

### API / UI

- 后端：`/api/projects/{project_id}/canon`
- 前端：在小说详情页新增“小说圣经”页签，支持分类、关键词、章节状态、人工确认。
- 章节生成页展示“本章将注入的 canon 摘录”，允许作者生成前手动增删。

### 验收标准

- 生成一章前能看到本章实际注入的 canon 条目。
- 角色名、核心道具、硬世界规则能被关键词稳定触发。
- AI 抽取的新设定不会直接覆盖权威 canon，必须经过人工确认或明确配置自动通过。

## P1：混合检索升级

### 目标

把现有向量 RAG 升级为“关键词硬触发 + 向量召回 + 重排 + POV/剧透过滤”的混合检索。长篇小说里，人物名、伏笔、专有名词、世界规则比语义相似度更重要，必须可控。

### 检索流程

1. 从章节标题、摘要、写作指令、`ChapterMission` 中抽取显式实体。
2. 用 `CanonEntry.keywords/aliases`、角色名、地点名、势力名做硬触发。
3. 用现有 `VectorStoreService` 做语义召回。
4. 合并去重，按来源赋权：
   - 硬规则 canon：最高；
   - 活跃伏笔、角色当前状态：高；
   - 上章摘要和结尾：高；
   - 向量 chunk：中；
   - 远期历史摘要：低。
5. 用 LLM 或轻量规则重排，移除重复、过期、POV 不可见内容。

### 涉及模块

- `KnowledgeRetrievalService`：增加硬触发入口和检索结果来源权重。
- `ChapterContextAssembler`：把 `canon_context` 与 `knowledge_context` 分层注入。
- `VectorStoreService`：为 chunk metadata 补充人物、地点、事件、canon id。
- `ChapterIngestionService`：定稿入库时写入更丰富 metadata。

### 验收标准

- 只要本章写作指令包含某角色/地点/道具名，对应 canon 条目必定进入候选上下文。
- 检索结果能标明来源和权重，便于调试。
- 向量库失效时，关键词触发和上章桥接仍可正常工作。

## P1：时序知识图谱 MVP

### 目标

借鉴 DOME 的“时序知识图谱记忆”思路，但采用项目现有结构小步实现。先不引入复杂 GraphRAG，先把定稿后的关键事件抽取成可审计的事件四元组。

### 建议事件结构

可新增 `StoryEvent`，或扩展现有 `TimelineEvent`：

| 字段 | 说明 |
| --- | --- |
| `subject` | 主体：角色/势力/物品 |
| `action` | 行为或状态变化 |
| `object` | 客体 |
| `chapter_number` | 来源章节 |
| `story_time` | 故事内时间 |
| `location` | 发生地点 |
| `event_type` | `state_change/reveal/conflict/movement/relationship/foreshadowing` |
| `confidence` | 抽取置信度 |
| `source_excerpt` | 原文证据短摘 |
| `canon_links` | 关联 canon 条目 |

### 定稿后处理

`FinalizeService` 在创建 `ChapterSnapshot` 后增加事件抽取步骤：

1. 抽取本章关键事件。
2. 更新角色位置、知识、关系、物品和健康状态。
3. 新增或解决 `CausalChain`。
4. 对新事件运行轻量冲突检查：
   - 同一角色同一时间出现在两个地点；
   - 已死亡/失效对象继续参与事件；
   - 角色知道了 POV 上不该知道的信息；
   - 伏笔提前回收或逾期未推进。

### 验收标准

- 每章定稿后至少生成 3-10 条关键事件，且带原文证据。
- 一致性检查能引用具体事件记录，而不是只读长摘要。
- 角色位置、已知秘密、道具持有等状态可以追溯到来源章节。

## P1：每 3-5 章周期审计

### 目标

把“全量审计”从可选能力变成稳定流程。长篇创作中，单章质量检查不够，必须定期检查连续性账本。

### 审计触发

- 默认每 5 章触发一次。
- 作者可在项目设置中改为 3、4、5、10 章。
- 出现高危信号时提前触发：
  - 逾期伏笔数量超过阈值；
  - 一致性评分低于阈值；
  - 角色状态抽取失败；
  - 定稿更新关键步骤失败。

### 审计内容

- 世界规则：是否出现硬规则冲突。
- 角色：位置、动机、能力、知识、关系是否连贯。
- 伏笔：新埋、强化、回收、逾期、误回收。
- 因果链：是否存在没有后果的重大事件。
- 时间线：故事内时间推进是否合理。
- 节奏：高潮/铺垫/过渡是否分布失衡。
- AI 味：机械连接词、总结式结尾、全知旁白、抽象情绪词。

### 输出结构

建议新增 `PeriodicAuditReport`：

```json
{
  "range": "1-5",
  "overall_status": "healthy/warning/critical",
  "critical_issues": [],
  "warnings": [],
  "canon_updates_pending": [],
  "foreshadowing_actions": [],
  "character_state_fixes": [],
  "next_chapter_constraints": []
}
```

### 涉及模块

- 复用 `ChapterReviewService`、`ConsistencyService`、`ForeshadowingService`、`PacingController`。
- 在 `FinalizeService` 成功后判断是否触发审计。
- 将审计产出的 `next_chapter_constraints` 注入后续 `ChapterMission`。

### 验收标准

- 第 5、10、15 章定稿后自动生成审计报告。
- 报告中的“下一章约束”能进入下一次章节生成上下文。
- 高危问题不会被静默吞掉，前端必须提示作者处理。

## P2：人工定稿闭环强化

### 目标

明确 AI 是受监管的执行者，只有作者确认后的内容才进入长期记忆、向量库和 canon。

### 状态机

建议把章节状态明确为：

```text
draft_generated -> ai_reviewed -> author_editing -> ready_to_finalize -> finalized
```

只有 `finalized` 才触发：

- `ProjectMemory.global_summary` 更新；
- 角色状态更新；
- 剧情线和伏笔账本更新；
- 向量库写入；
- 章节快照创建；
- 事件图谱抽取；
- 周期审计判断。

### UI 改进

- 在章节工作台明确显示“草稿不会进入长期记忆”。
- “应用优化”和“定稿入库”分开，避免优化结果直接污染记忆。
- 定稿前展示“本章将更新的记忆项”，作者可取消明显错误的抽取结果。

### 验收标准

- 未定稿章节不会被 RAG 检索到。
- 作者能看到并确认定稿抽取结果。
- 修改已定稿章节时，旧向量、旧快照、旧事件必须同步失效或版本化。

## P2：Prompt 与风格约束清理

### 目标

把“去 AI 味”从泛泛提示变成可测试的风格约束。重点不是欺骗检测器，而是减少机械、解释性、全知式文本。

### 建议改造

- 将禁用词、禁用句式、POV 禁令维护为 `style_guardrails`。
- 在 `writer_persona` 中允许作者配置：
  - 句长偏好；
  - 对话密度；
  - 感官偏好；
  - 禁用表达；
  - 角色口癖和语言边界。
- 在 `AIReviewService` 或 `SixDimensionReviewService` 中增加“文本机械感”维度。

### 可检测规则

- 禁用总结式章节结尾。
- 禁用“显而易见、综上、值得注意、然而、不仅如此”等机械连接词。
- 统计抽象情绪词密度，如“恐惧、愤怒、震惊、绝望”，提示改为身体反应和动作。
- 识别全知旁白，如“与此同时、另一边、他并不知道”。

### 验收标准

- 评审报告能列出具体触发句子。
- 自动修复只修改问题段落，不重写整章。
- 作者可按项目关闭或调整风格规则。

## P3：数据验证与网文卖点

### 目标

把“题材 + 卖点”从前置头脑风暴升级为项目级参考资料。该能力需要联网或外部数据时，应独立于章节生成，不应阻塞主流程。

### MVP

- 在概念阶段新增“卖点假设”字段：
  - 目标读者；
  - 核心爽点；
  - 同类作品；
  - 避雷点；
  - 前 10 章留存钩子。
- 允许作者手动录入市场参考，不自动联网。
- 后续可增加可选的联网调研工作流，结果作为 `author_reference`，不作为硬 canon。

### 验收标准

- 章节导演脚本能读取“核心爽点”和“避雷点”。
- 市场参考与小说 canon 分开存储，避免把外部资料误当世界设定。

## 实施顺序

1. **小说圣经 MVP**：先做数据结构、CRUD、手动录入和章节注入预览。
2. **关键词硬触发**：接入 `KnowledgeRetrievalService`，解决专有名词召回不稳定。
3. **定稿确认页**：让作者确认记忆、canon、伏笔、事件抽取结果。
4. **周期审计**：每 5 章自动跑一次，输出下一章约束。
5. **事件四元组**：从定稿章节抽取关键事件，逐步替代长摘要式一致性检查。
6. **风格 guardrails**：把去 AI 味规则做成可配置、可检测、可定位的问题列表。

## 风险与边界

- 不建议一开始引入 CrewAI/LangGraph 重写编排层，当前 `PipelineOrchestrator` 已足够承载多阶段流程。
- 不建议立刻替换向量库。现有 libSQL 向量方案可以继续用，先补 metadata 和关键词触发。
- 不建议让 AI 自动改写 canon。权威设定必须由作者确认，自动抽取只能作为候选。
- DOME/GraphRAG 思路应先做事件图谱 MVP，再根据效果决定是否引入复杂图检索。

## 与现有模块的映射

| 改进项 | 现有基础 | 建议新增/改造 |
| --- | --- | --- |
| 小说圣经 | `NovelBlueprint`, `ProjectMemory`, `NovelConstitution` | `CanonEntry`, `CanonService`, canon 注入预览 |
| 混合检索 | `KnowledgeRetrievalService`, `VectorStoreService` | 关键词硬触发、来源权重、重排、metadata |
| 时序知识图谱 | `TimelineEvent`, `CausalChain`, `CharacterState` | `StoryEvent` 四元组、事件冲突检查 |
| 周期审计 | `ChapterReviewService`, `ConsistencyService` | `PeriodicAuditReport`, 定稿后自动触发 |
| 人工定稿 | `FinalizeService`, `ChapterSnapshot` | 状态机、定稿确认页、抽取结果审核 |
| 风格约束 | `writer_persona`, `writing_v2`, `six_dimension_review` | `style_guardrails`, 机械感检测、局部修复 |

