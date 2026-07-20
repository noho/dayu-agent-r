# WU-SEMANTIC-OWNERSHIP-01 P3-C plan-fix（AgentCodex）

## Gate metadata

- Work unit：`WU-SEMANTIC-OWNERSHIP-01 / P3-C`。
- Gate：plan-fix only。
- Timestamp：`2026-07-10T16:36:38+08:00`。
- Target：`docs/host/wu-semantic-ownership-01-p3-c-context-compaction-evidence-plan.md`。
- Design sources：`docs/host/design.md`、`docs/engine/design.md`。
- Control source：`docs/host/issues-implementation-control.md`。
- Review inputs：
  - `docs/reviews/wu-semantic-ownership-01-p3-c-plan-review-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-p3-c-plan-review-ds.md`
  - `docs/reviews/wu-semantic-ownership-01-p3-c-plan-review-controller-adjudication.md`
- Write scope：只修改 target plan，并新建本 artifact；未修改生产代码、测试、control
  doc、reviewer artifacts、README 或其它未跟踪文件，未 commit。

## 第一性原理与 owner boundary

动机成立且 controller 严重性判断合理。当前代码不是单纯命名重复，而是同一 accepted
compact/evidence 事实在下游形成多套可独立演进的 projection：blocks 与 typed readable
view 通过字符串往返重建；ordinary input 同时渲染 memory 与 compact artifact；evidence
material 仍以三个 loose readable 字段和三套 renderer 传播。若 plan 不固定 invariant、
异常 owner、删除路径与原子迁移，implementation agent 必须现场发明契约，可能得到“显示
正确但 durable/read model 不同源”的局部止血。

owner boundary 保持为：`CONTEXT_COMPACTED.accepted_candidate` 是 durable compact 事实；
`compact_payload` 严格解析一次；Conversation Memory 与 compact material pair projector
分别产生 ordinary/next-compactor typed projection；RunInputBuilder 只消费 required catch-up
后的 memory projection。Accepted tool result 由 accept barrier 持久化，
`AcceptedToolResultProjection` 产生 typed LLM material，唯一 renderer 产生最终文本。UI、
Service、Engine、Tool Trace 与 fixture 都不是修复 owner。

## Controller accepted plan fixes

### P3-C-PF-01 — fixed

- Direct evidence：`compaction.py:1621` 的 `CompactMaterialPack` 当前只有 blocks；
  `compact_material.py:977` 的 recovery degrade 只过滤 blocks；
  `compact_material.py:3229-3416` 再从 block text 重建 typed view，forward intent/reference
  使用分号 string protocol，anchor reconstruction 丢失真实 children。
- Plan text：6.3 新增 exact invariant：empty/None 等价、allowed kind/section、summary
  presence/text、四类 item count/order/label/text、完整 anchor children/ordinal，以及同一次
  accepted candidate 原子 pair projection。固定唯一
  `transform_previous_compacted_view_pair_for_recovery(...)`，tier2 传 retained labels、tier3
  传空 set；禁止两个独立 filter。
- Exception owner：leaf constructor 的直接类型错误仍为 `TypeError/ValueError`；已持久化
  pair 的 presence/count/kind/label/text/children mismatch 为 durable corruption，
  `CompactMaterialPack`/EventLog-backed adapter 抛 `HostDurableError`。
- Validation text：S2 要求 tier2/tier3 exact pair tests、不同步 fail-closed test 与相应
  source scans。

### P3-C-PF-02 — fixed

- Direct evidence：`run_input.py:337-358` 的 `MemorySnapshotView` 没有 latest compact ref；
  `run_input.py:424-437` 的 `CompactArtifactView` 仍携带 messages；
  `DurableCompactArtifactProvider._load_compact_artifact_tx()` 在 `1614-1627` 构造
  `SystemMessage`；`RunInputBuilder.build()` 在 `1935-1940` 拆包 `*compact.messages`。
- Plan text：6.4 定义两个 ref 只按 event-id 字符串 exact equality，不比较 artifact/
  cursor/sequence；列出 `None/None`、equal non-None、compact-only、memory-only、两个
  non-None mismatch 五格 matrix。后三类复用
  `MemoryProjectionRepairRequired(reason=SNAPSHOT_DAMAGED)` 并由既有 required memory
  catch-up/rebuild/inline-repair caller 处理。
- Concrete deletion：点名删除 provider 内 message renderer/`SystemMessage`/`messages=`，
  删除 `CompactArtifactView.messages` 且不保留空字段；点名删除 builder 的
  `*compact.messages`，ordinary bounded context 只含 memory、protected raw tail、
  continuity。
- Validation text：五个命名 tests 均位于 `tests/host/test_run_input_builder.py`，且进入
  focused 与 aggregate validation。

### P3-C-PF-03 — fixed

- Direct evidence：`compact_material.py:199-298` 的 `RunInputMaterialBlock` 当前携带
  `readable_tool_name/readable_query_text/readable_source_text`，evidence invariant 只检查
  loose fields；`compact_pipeline.py:1101-1122` 与 `run_input.py:2998-3019` 分别读取它们
  重建文本。
- Plan text：6.6 列出完整 evidence contract：三个 identity ref、payload/artifact/source
  provenance 与 `accepted_tool_evidence`。evidence block 必须是
  `EVIDENCE_MATERIAL + ACCEPTED_TOOL_EVIDENCE`、identity/material 完整、
  `text == shared renderer output`；non-evidence block 的全部 evidence fields/provenance
  必须为空。
- Atomic migration：同一 S3 内先定义 typed material/renderer，再迁移 block/event 的全部
  producer/consumer，最后删除三个 loose fields、private renderers 与旧 fixture 参数；不
  允许可 import 的 dual-field contract 跨出 slice。
- Validation text：S3 tests 必须验证 evidence/non-evidence constructor invariant、shared
  renderer equality，以及 `CompactEvidenceBlock` 直接消费 typed fields 而非反解析 text。

### P3-C-PF-04 — fixed

- Direct evidence：`compaction_operation.py:69,1471-1494` 用 `_POST_COMPACT_BASE_MESSAGE_COUNT
  = 2` 估算 accepted compact 后 ordinary dispatch；Host design 第 23 节要求 ordinary
  system-scoped material 合并为一条 system envelope，current input 仍是一条 user
  message。
- Plan text：6.5 将 `2` 明确推导为 `one system envelope + current-input user = 2`，由
  `context_budget` ordinary post-compact estimator 拥有；禁止 caller override，避免同一
  message contract 得出不同预算。
- Validation text：增加 derivation comment 与 drift-oriented test，同时断言实际 ordinary
  message shape 和 overhead；message contract 改变必须迫使 owner 同步修改。

### P3-C-PF-05 — fixed

- Direct evidence：原 plan 只写泛化的 “mismatch repair/fail closed”，没有把 all-None 与
  三类 mismatch 映射到命名 test；现有 `test_run_input_builder.py` 也没有这些名字。
- Plan text：7.1、S2、9 节明确五个测试：
  `test_no_compact_event_and_no_memory_compaction_ref_builds_without_repair`、
  `test_matching_compact_and_memory_compaction_event_refs_build_once`、
  `test_compact_event_without_memory_compaction_ref_requires_repair`、
  `test_memory_compaction_ref_without_compact_event_requires_repair`、
  `test_mismatched_compact_and_memory_compaction_event_refs_require_repair`。
- Validation text：focused command单跑 `tests/host/test_run_input_builder.py`；aggregate
  matrix再次包含该文件。三种 mismatch 还断言 raw-tail/manifest/dispatch side effect 未
  发生。

### P3-C-PF-06 — fixed

- Direct evidence：`compact_material.py:2259-2266` 直接调用
  `accepted_evidence_envelope_from_payload()`，并以
  `str(exc) == ACCEPTED_EVIDENCE_PRODUCER_EVENT_REF_MISMATCH` 做控制流。
- Plan text：S3 Exact changes 点名删除该调用与 catch block；compact evidence block 只
  消费 `AcceptedToolResultProjection.llm_material`，producer mismatch 只由 projection
  owner 捕获 typed exception 并转 `HostDurableError`。
- Validation text：新增 `compact_material.py` 零匹配 source scan；原全 Host string
  protocol scan继续保留为 hard acceptance criterion。

## Residual observations absorbed

1. S2 明确删除 typed pair 迁移后失去消费者的 `_previous_blocks_from_snapshot()`、五个
   `_snapshot_*` text helpers、`_previous_compacted_*_vnext()`、两个 parser 及仅服务该
   string-wire 的 `_PREVIOUS_*` 常量；不把 dead serializer 留给后续 cleanup。
2. S2 明确删除 `compact_material.py` 的五个 `_candidate_*` mapping parsers和 candidate
   字段常量，以及 `run_input.py` 的 raw candidate renderer、nested parser 与 candidate
   字段常量；artifact/ref/governance 字段仍归各自 owner，不做无关横扫。
3. `compaction_operation._POST_COMPACT_BASE_MESSAGE_COUNT` 属于 accepted compact 后
   ordinary dispatch estimator，迁入 `context_budget`；
   `llm_compaction._POST_COMPACT_BASE_MESSAGE_COUNT` 属于 compactor proposal-budget
   语义，P3-C 不移动、不合并、不 re-export。两个同名同值常量没有消费同源证据，不能
   误判为同一 owner。

## Preserved scope and slice structure

- Implementation slices 保持 3 个：S1 typed compact → memory；S2 typed pair/ordinary
  RunInput/budget；S3 typed evidence/renderer/typed mismatch。
- 未增加兼容路径、caller override、unknown fallback、schema migration 或 Tool Trace
  refactor。
- 未授权修改 design/control/reviewer artifacts；next gate 仍是 parallel plan re-review，
  本轮不推进。

## Validation

- `git diff --check`：pass（exit 0，无输出）。
- untracked plan no-index whitespace check：pass（无 whitespace diagnostic；exit 1 仅表示
  与 `/dev/null` 存在内容差异）。
- untracked plan-fix artifact no-index whitespace check：pass（无 whitespace diagnostic；
  exit 1 仅表示与 `/dev/null` 存在内容差异）。
- pytest / pyright：未运行；本 gate 只修改 Markdown plan/review artifact，未修改生产代码
  或测试。

## Residual risks and blocking questions

- fixed in plan：`P3-C-PF-01` 至 `P3-C-PF-06` 与三个相关 residual observations。
- covered by S1：persisted candidate read-side corruption、enum/snapshot drift。
- covered by S2：pair propagation、memory ref repair、duplicate compact renderer、candidate
  parser/string-wire dead code、ordinary post-compact budget owner。
- covered by S3：evidence typed block atomic migration、string exception protocol。
- assigned to P3-E：accepted tool status fallback/raw outcome reconstruction。
- assigned to P3-J：全局 EventLog taxonomy/DDL closed-set。
- Blocking questions：0。

## Gate result

- PF-01：fixed。
- PF-02：fixed。
- PF-03：fixed。
- PF-04：fixed。
- PF-05：fixed。
- PF-06：fixed。
- Implementation slices：3（保持 S1/S2/S3）。
- Blocking questions：0。
- Decision：`ready-for-plan-rereview`。
- Next gate：parallel AgentMiMo + AgentDS plan re-review；本轮未进入。

Artifact path：`docs/reviews/wu-semantic-ownership-01-p3-c-plan-fix-codex.md`。
