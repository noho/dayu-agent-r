# Interactive Conversation Memory closure F10：implementation artifact

## Gate

- Gate：Gateflow implementation completed / code-review handoff。
- Work unit：Interactive Conversation Memory closure F10。
- Base：accepted F09 commit `d04f7531`；当前 `HEAD` 仍为该 commit，未提交。
- Plan truth：原 accepted plan
  `wu-interactive-memory-closure-f08-f10-plan-codex.md`，以及总控已接受的
  `wu-interactive-memory-closure-f10-plan-amendment-controller-adjudication.md`、
  controller 与 fix-controller。
- Completion status：`COMPLETED`。原 `F10-BLOCK-001` 已由 accepted amendment 解除，
  implementation 与 owner validation 完成。
- Current gate / next entry point：code review；本 artifact 不宣称 review、deepreview 或
  final closeout 已完成。

## Scope

Production 只修改 F10 六个 Host owner 文件：

- `dayu/host/compaction.py`
- `dayu/host/compact_material.py`
- `dayu/host/compact_pipeline.py`
- `dayu/host/context_governance.py`
- `dayu/host/compaction_operation.py`
- `dayu/host/dispatch.py`

Owner tests 修改：

- 原 F10 列表：`test_compact_material.py`、`test_compact_pipeline.py`、
  `test_compaction_operation.py`、`test_dispatch_scheduler.py`、
  `test_llm_compaction.py`。
- controller amendment 明确扩入：`test_compaction_contract.py`、
  `test_public_compact_smoke.py`，只迁移双 digest strict contract 与 LLM-facing 隔离断言。
- 用户后续明确授权：`test_runner_call_hot_payload_contract.py`，迁移完整 Host suite 暴露的
  6 个 F09 compactor manifest fixture consumers；没有扩大 production boundary。

稳定事实文档修改 `docs/host/design.md`、`dayu/host/README.md`、`tests/README.md`，并更新本
artifact。Engine、Memory projector、RunInput consumer、compact v2 output schema、正式 CLI
scenario、frozen oracle/evidence 均未修改。

## Motivation 与 owner 判定

F10 动机成立。旧 recovery selector 可以按 block 截断同一 completed Run 的 turn group；
reduced boundary 在自身 coverage 上合法，却不能证明它覆盖完整 root group。该路径可能把部分
事实链提交为 durable accepted compact truth。

语义 owner 保持单一：

- material/selector owner 产生 turn-group membership、collective exclusion、strict-prefix
  atomic selection 与 selected-block provenance；
- pipeline 在仍持有 canonical source snapshot 时验证完整 partition 与 proof；
- Context Governance 产生 candidate accept/reject 与 bounded repair feedback；
- operation 在 provider 前和 durable accept 前防御验证 root/pass/pack；
- dispatcher 只负责 feedback binding、attempt schedule 与既有 terminal/fallback 收口；
- Memory、RunInput、Engine 不做兼容、重算或下游补偿。

## Implementation

### 1. Atomic selection contract

- 新增 strict frozen `TurnGroupMembership`、root/transient selection scope，并与
  `CompactSegmentSelection` 属于同一 canonical contract。
- selector 第一阶段按稳定 material 顺序归并 turn groups/singletons，再以固定 precedence
  做 collective exclusion；任一 group member 命中 current/protected/already-represented/
  previous/not-in-segment 即整组排除。
- 第二阶段按 atomic unit 做 strict prefix item/char budget；item 使用真实 block 数。
  exact cap 可选，首个 oversized unit 也不越 cap、不拆组、不跳过，之后 eligible units 全部
  `budget_limit`。
- missing turn-group id、重复 block id、partial root group、selected/excluded overlap 或 omission
  均 fail closed。`excluded_reason_codes` 在 constructor 中先 key-sort copy，再以
  `MappingProxyType` 冻结；stored order、JSON 与 digest 共用 canonical order。
- canonical source snapshot 不删除 raw blocks；tier 1–3 只消费 atomic selection view，
  tier 4/5 fallback 或 fail-closed 仍从完整 snapshot 派生。

### 2. Selected-block provenance amendment

- 新增 strict frozen
  `SelectedBlockProvenance(block_id, canonical_source_refs, packed_content_digest)`；root selection
  按 selected block stable order 保存 proof，serialization/request digest 包含 proof。
- compact-material owner 只定义一个
  `_packed_content_digest(block: RunInputMaterialBlock) -> str`：ordinary block hash packed text，
  accepted evidence hash最终 `result_text`。`RunInputMaterialBlock.content_digest` 的四行业务可读
  source-boundary 语义不变。
- 同一 helper 直接服务 amendment 指定的四个调用点：selected proof producer、
  `_compact_material_block`、`_pack_evidence_blocks`、
  `_provenance_from_evidence_blocks`。
- pipeline 从 frozen source snapshot 重建 expected proof，拒绝 unknown id、等数量替换、
  membership/partition/ref/digest 漂移。
- selected packer 完全移除文本与 current-input dedup；same-text/different-ref blocks 原样保留。
  selected history/evidence 与 current anchor 共享 canonical ref 时，pipeline 在 request 构造后、
  operation 在 provider 前均 fail closed。
- proof 只进入 Host-internal request/digest，不进入 `llm_material_json()`、repair JSON 或 v2
  output schema。

### 3. Reactive pass 与 durable root boundary

- reactive per-block selection 明确为 transient，并绑定 immutable root selection digest；
  `_single_block_segment_selection` 只能从 root proof 按 block id 精确取一个 entry。
- `_operation_pass_requests` 验证每个 transient proof 是 root proof 的逐字段 exact subset，
  全体 pass 对 root proof 与 source boundary 均无重叠、无遗漏；每个 pass 在任一 provider call
  前验证 proof 与自身 material pack。
- operation root guard 验证 root scope、trigger、完整 turn-group 二分、selected proof 与最终
  pack refs/final-pack digest，并在最终 accepted result 返回前再次执行同一验证。
- contract mismatch 使用既有 non-repairable `proposal_failed` transport，provider count 为零、
  `next_repair_feedback=None`，不把异常抛出 scheduler。transient accepted truth 不写 artifact、
  Memory 或 terminal；只有 aggregate root 可产生 durable accepted truth。

### 4. Dual-digest feedback binding 与 terminal

- `CompactRepairFeedbackV2` 与 `build_compact_repair_feedback_v2` 新 schema 强制非空
  `request_digest`、`source_boundary_digest`；没有 default、optional shim、alias 或旧 digest
  fallback。
- 同一 immutable root request 的 repair 保留 feedback；request、tier 或 source boundary 任一
 变化即清空。绕过 dispatcher 的 mismatch 在 operation provider 前 defensive fail closed。
- 唯一 LLM repair projector 仍只投影 `required_action` 与 `issues`，两个治理 digest 不暴露给
  LLM。
- dispatcher 收到 non-repairable result 后停止 schedule，沿既有 terminal permit 只写一个
  failed terminal，再进入既有 raw-window fallback 或 fail closed；不新增 terminal/schema。

### 5. F09 fixture consumer migration

完整 Host suite 暴露的 6 个 failures 来自 `_compactor_manifest` 测试 fixture 删除当前必填
`runner_call_projection_artifact_*` 字段。fixture 现按 F09 canonical manifest contract提供
compactor-specific ref/digest/size；production recorder/resolver 未增加兼容 fallback。

## Direct-caller audit

`rg` 核对 `build_compact_repair_feedback_v2(` 的全部直接调用者：

- production：`dayu/host/compaction_operation.py` 四条 reject/routing 路径；每条显式传入产生
  feedback 的 pass/root request digest 与 source-boundary digest。
- tests：`test_llm_compaction.py` 两处、`test_public_compact_smoke.py` 两处、
  `test_compaction_contract.py` 一处、`test_compaction_operation.py` 一处。

没有其它同类 owner-test consumer；没有默认值、compat 或生产范围扩张。

## Owner test matrix

已覆盖：mixed collective exclusions、输入顺序稳定、exact/oversized char/item caps、strict
prefix、missing group id、selection digest、sorted-copy/read-only mapping、ordinary/evidence
final-pack digest、unknown id 复用真实 refs/digest、ref/digest tamper、whole-group same-count swap、
same-text/different-ref、same canonical current ref、root→root feedback retain、root/tier/boundary
clear、direct/dispatcher defensive mismatch、partial root、reactive exact partition与每-pass pack
tamper、raw snapshot retention/tier fallback、aggregate-root-only accepted truth 与 single terminal。

## Validation

### Tests

- F10 focused owner suite（含 amendment 与 F09 fixture consumers）：
  `337 passed, 1 skipped in 3.52s`。skip 为 opt-in real compactor smoke；按要求未运行。
- 完整相关 Host suite：`2385 passed, 1 skipped, 6 deselected in 98.33s`。
- 覆盖率 owner suite：`418 passed, 1 skipped in 6.06s`。
- 覆盖率：
  - `compact_material.py` 86%
  - `compact_pipeline.py` 92%
  - `compaction.py` 84%
  - `compaction_operation.py` 86%
  - `context_governance.py` 89%
  - `dispatch.py` 83%
  - 总计 85%

coverage instrumentation 最初两次触发一个既有非目标测试的 10ms lane timeout；该测试验证
empty-window enqueue，不验证 timeout。测试 fixture 现只在该 test 显式使用 1s lane deadline；
专门的 lane-timeout owner tests 与 production timeout 未改，随后覆盖率组合全绿。

### Type、lint、compile 与 JSON

- 全仓 pyright：724 files analyzed，0 errors、0 warnings、0 informations。
- F10 精确 production/tests pathspec Ruff check：通过。
- `compileall -q dayu tests utils`：通过。
- `json.tool`：workspace manifest、CLI oracle、CLI scenarios 均通过。
- `git diff --check`：通过。

全树 `ruff check dayu tests utils` 仍报告 95 个既有错误，全部位于 F10 精确 pathspec 外；
F10 pathspec 单独为 green。全树 `ruff format --check` 报 499 个既有文件需格式化。F10
pathspec 中 formatter 仍列出 `compaction.py`、`test_compact_pipeline.py`、
`test_compaction_contract.py`、`test_public_compact_smoke.py`、
`test_runner_call_hot_payload_contract.py`；逐一对 `git show d04f7531:<path>` 执行相同检查，
这 5 个 base 文件全部原样失败。为遵守 scope 与两份扩容测试“只迁移 strict contract”的限制，
没有做全文件机械格式化；本 slice 新增且 base 原本 format-clean 的三个文件已运行 formatter，
全部 F10 文件的 Ruff lint check 均通过。

### Frozen baseline 与 diff

- `docs/cli_ci_oracles.json`：
  `da04923193a04c0e33eca9c60e0d8eb919b74963b2c2f4170954be2f07261201`
- `docs/cli_ci_scenarios.json`：
  `7c991d14ebc79f9f8e8c66d9eb94c10156c5a36eecd3bb11df24ed18cbca2093`
- `docs/reviews/wu-interactive-memory-closure-f08-f10.md`：
  `95a09543fc7f1a2a09f99dbe2c2c014e71ac22f2c386dc5364f6a1a2d14b1b08`

三份 implementation-frozen baseline 与 accepted checkpoint 一致。只读 observed behavior 与
report freeze 也已重新取 hash；未修改。未运行五条正式 CLI scenarios，未改 evidence status，
未 commit。

## Docs decision

- `docs/host/design.md`：更新完整 turn-group atomic selection、selected proof、transient exact
  partition、双 digest binding 与 aggregate-root durable accept；同时移除与 F10 冲突的
  selected evidence-block split 描述。
- `dayu/host/README.md`：记录当前 Host selection/proof/provider guard/feedback binding 事实。
- `tests/README.md`：把 conformance 范围更新为 F06–F10，并记录稳定 owner matrix。
- Engine、分层、CLI 与安装入口均未改变，因此 Engine/root/dayu README 不触发。

## Finding disposition

- `F10-BLOCK-001`：`fixed`。accepted amendment 提供最小 Host-internal
  block→refs/final-pack-digest bridge；pipeline 与 operation 的反例 tests 已闭合。
- `F10-FIND-002`：`fixed`。selected packer 不再以相同文本或 current ref 删除单个 group
  member；不同 ref 保留，同 current ref 在 owner boundary fail closed。
- mutable `excluded_reason_codes`：`fixed`。sorted copy + read-only mapping；外部原 mapping 与
 直接写入均不能改变 selection。
- F09 hot-payload fixture consumers：`fixed`。6 个 deterministic failures 已按当前 strict
  manifest contract 迁移，完整 Host suite green。

## Residual risks 与 handoff

- 真实 provider 对 F08/F09/F10 的行为与五条正式 CLI scenarios 仍属后续 evidence/readiness
  gate；本次按明确禁令未运行。
- 全树 Ruff lint/format 是 accepted base 的仓库级债务，不能在 F10 scope 内机械修复；F10
  精确 lint 与所有 correctness/type/test/coverage gates 均 green。
- implementation 尚未经过本 slice 的两路 code review、fix/re-review 与 deepreview；当前正确
  停点是 code-review handoff，不是 accepted slice commit 或 final closeout。

## Completion status

F10 implementation 已完成，原 BLOCKED 状态关闭；workspace 保留未提交 diff，下一步进入
code review。没有提交，没有运行正式 scenarios。
