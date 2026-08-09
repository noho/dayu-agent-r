# PR 190 F11/F12 Plan Re-Review — Controller Fix Verification

## Re-review identity

- **Re-review type**: Independent adversarial plan re-review（Review B 原 reviewer）
- **Target plan**: `docs/gateflow/pr-190-f11-f12-interactive-memory-plan-20260805.md`（controller fix 修订版）
- **Controller artifact**: `docs/gateflow/pr-190-f11-f12-plan-review-adjudication-20260805.md`
- **Original review**: `docs/reviews/plan-review-20260805-144405.md`（Review B, 7 findings + 3 open questions）
- **Plan base commit**: `3087b1b983a97ce5012d54e818795f4755434a98`
- **Branch**: `codex/interactive-oracle`
- **PR**: https://github.com/noho/dayu-agent-r/pull/190
- **Review timestamp**: 2026-08-05T15:06:52+08:00
- **Re-review artifact**: `docs/reviews/plan-rereview-20260805-ds.md`
- **Reviewer**: Claude (planreview skill) — adversarial posture; constructively skeptical, evidence-based

## Scope

逐项核对原 Review B 的 7 个 findings（B-01 到 B-07）与 3 个 open questions 的 controller 裁决与 plan delta；adversarial 检查修订是否引入新 blocker。重点覆盖用户指定的八个领域：registry supersession/current stable predicate resolution、Host-internal digest 零 LLM 泄漏、single structure owner、caps DTO、fresh Tool Trace v2、full keyset exhaustion、atomic v3 migration、Oracle pending 不阻塞 final closeout。

不覆盖：Review A 的 10 个 findings（已在 controller adjudication 中逐项裁决，本 re-review 范围外）；已实现的 F01-F10 代码。

## Inputs verified

| 真源 | 读取范围 | 用途 |
|---|---|---|
| 修订 plan (`pr-190-f11-f12-interactive-memory-plan-20260805.md`) | 完整 495 行 | 逐 finding 核对 delta |
| Controller adjudication (`pr-190-f11-f12-plan-review-adjudication-20260805.md`) | 完整 216 行 | 核对每项裁决、证据与 plan delta |
| Original Review B (`plan-review-20260805-144405.md`) | 完整 241 行 | 原 finding 基准 |
| `docs/cli_ci.md` §4.3-4.6 | 完整 155 行 (lines 290-445) | 验证 registry supersession 合规性 |
| `dayu/host/compaction.py` | `CompactCandidateV2` type chain、`COMPACT_OUTPUT_SCHEMA_V2` | 验证 v2 contract 现状 |
| `dayu/engine/contracts/runner.py` | `AsyncRunner` Protocol | 验证 `@runtime_checkable` |
| `dayu/host/compaction_terminal.py` | `_read_operation_terminal_rows` | 验证既有 keyset exhaustion 模式 |

## Item-by-item disposition

### B-01 — S3 原子迁移切片过粗（原 HIGH）

- **Controller decision**: `rejected-with-reason`
- **Controller evidence**: 拆分会制造双 contract 或半迁移 accepted 状态（adjudication line 117-119）；fresh schema 与单一 owner 优先于小 commit 形式
- **Plan delta (lines 327-336)**:
  - 明确理由："任何 S3a 式 checkpoint 都会保留 v2 active owner 同时引入未消费 v3 contract，或让 parser/prompt/persistence 不同步"
  - Worktree 内部实施顺序：types → all consumers+prompt → delete v2 → hash/tests
  - Rollback："只丢弃该 slice 尚未提交的 intended diff，恢复到 S2 accepted commit"
  - 分类为 accepted engineering risk，由两路 review + aggregate deepreview 缓解
- **Verification**: Controller reasoning 成立。拆 checkpoint 确实会产生 v2 active + v3 defined 的中间态。Plan 现在包含显式内部顺序（4 步）和明确回滚策略（恢复到 S2，不保留部分 v3 文件）。不是新 blocker。
- **Disposition**: `evidence-invalid`（原 finding 的拆分建议被 controller 拒绝且 plan 提供了更安全的替代方案）

### B-02 — Repair digest 暴露歧义（原 HIGH）

- **Controller decision**: `accepted`
- **Controller evidence**: Host design 与项目 LLM-facing 约束均要求治理 digest 不进入模型上下文（adjudication line 124-126）
- **Plan delta (lines 150-151, 161, 439)**:
  - State machine 图中改为 "same Host-internal request digest" / "same Host-internal boundary digest"
  - 显式声明："request digest 与 source-boundary digest 只存在于 Host 内部 `CompactionRequest` binding、audit 和 request serialization；二者绝不进入 LLM-facing initial/repair system 或 user 文本"
  - 强制要求："owner test 必须对 captured runner input 做反泄漏断言，证明 exact digest values 与 generic digest 字段名均不存在"
  - Invariants 新增 line 439: "request/source-boundary digest 只属于 Host binding/audit/serialization，绝不进入 LLM-facing initial/repair 消息"
- **Verification**: 歧义已完全消除。"Host-internal" 限定词出现在 state machine diagram 和所有相关段落。反泄漏 owner test 提供了可执行的验证手段。LLM-facing 零泄漏由 invariant 强制保证。
- **Disposition**: `fixed`

### B-03 — S0 design update 粒度不足（原 MEDIUM）

- **Controller decision**: `accepted`
- **Controller evidence**: Host §24/25 与 Engine §2/4/6/7/8/15 分别承诺不同 owner/contract（adjudication line 131-133）
- **Plan delta (lines 195-215)**:
  - 9 项精确 Host design edit list：§14.1（Tool Trace）、§24.2（LLM-facing hard boundary）、§24.3（整节 v2→v3 替换）、§24.4（Snapshot schema）、§24.5（五类 Memory）、§24.6（Prompt Assembly）、§24.7（测试边界）、§25（Context Governance）、§25.1（Compact Event 响应路径）
  - 5 项精确 Engine design edit list：§2/§4（AgentRunRequest）、§6（Agent loop）、§7（Runner Protocol）、§8（RunnerSpec）、§15（Context Compaction）
  - 显式删除规则："S0 必须删除或替换所有与新 contract 冲突的 v2 normative 文字，不能仅在后文追加 v3 导致双设计真源"
- **Verification**: Edit list 现在精确到具体章节号与变更内容。每项有明确的替换/新增/删除语义。实施 Agent 可以逐项执行。双设计真源风险被显式删除规则覆盖。
- **Disposition**: `fixed`

### B-04 — F11 pagination max pages 未指定（原 MEDIUM）

- **Controller decision**: `rejected-with-reason`
- **Controller evidence (adjudication lines 137-140)**:
  - 既有 canonical owner（`compaction_terminal.py::_read_operation_terminal_rows`、`proactive_compaction.py::_read_operation_rows`）使用固定 page size + 单调 `after_event_sequence` + short-page exhaustion
  - 不设任意总页数 cap
  - 任意 10 页 cap 会把后置真实 terminal 误判 missing，破坏 F11 exact resolution
- **Plan delta (lines 80-84)**:
  - 复用既有 keyset exhaustion 模式
  - "使用固定正数 page size 与 `after_event_sequence` 单调 cursor，直到返回 page 长度小于 page size 才算完整 exhaustion"
  - "不设任意'最多 N 页'总扫描上限。每页有界，但必须读尽该 parent Run 的两类 canonical rows"
  - "empty/invalid cursor、full page 后 cursor 不严格增大或 reader 返回 sequence 不大于 cursor 时抛 `HostDurableError`，不得把未完成扫描当作 terminal missing"
  - "只有完整 exhaustion 后确实没有 matching terminal...才返回 None；不新增 scan-cap limitation"
  - S1 owner tests 增加（line 246）:"目标 terminal 位于一个及多个 full page 之后仍可解析；full page 后 cursor 严格推进；empty page 结束；注入重复/倒退 cursor 或不推进 page fail closed；不存在任意 page-count 提前截断或 scan-cap limitation"
- **Verification**: Controller reasoning 成立。原 finding 的核心假设（无限分页风险）未考虑两点关键约束：(a) 只扫描两类事件（`CONTEXT_COMPACTED` + `CONTEXT_COMPACTION_ATTEMPT_REJECTED`），不是所有事件；(b) 单 parent Run 内两类事件总数受 compaction operation attempt budget 约束。Plan 复用的既有 exhaustion 模式已被既有代码和测试验证。Full-page cursor 单调推进 + short-page 终止 + corruption fail-closed 保证 determinism。新增 owner tests 覆盖 multi-full-page 与 corruption 路径。
- **Disposition**: `evidence-invalid`（原 finding 的风险评估未充分考虑既有 event-type 约束和既有代码 precedent）

### B-05 — Structured-output capability 证据未引用（原 MEDIUM）

- **Controller decision**: `accepted`
- **Controller evidence (adjudication lines 145-148)**: DeepSeek 两份官方页面明确 `json_object` request shape
- **Plan delta (lines 179-180)**:
  - 引用 DeepSeek 官方 [JSON Output guide](https://api-docs.deepseek.com/guides/json_mode/) 与 [Create Chat Completion reference](https://api-docs.deepseek.com/api/create-chat-completion)
  - 引用 OpenAI 官方 [Structured Outputs guide](https://developers.openai.com/api/docs/guides/structured-outputs) 作为 generic transport design evidence（不授权当前 catalog model 能力）
  - Mimo=`none` 改写为："Mimo=`none` 表示 capability unknown 时的保守值，不是'实测不支持'"
  - S4 要求验证本仓库实际 endpoint/model/options 装配
- **Verification**: DeepSeek 官方 URL 已引用。OpenAI 文档角色已明确界定。Mimo 保守语义已澄清。Capability 矩阵现在有可追溯的 evidence chain。
- **Disposition**: `fixed`

### B-06 — Superseded 语义保留方式未明确（原 LOW）

- **Controller decision**: `rejected-with-reason`
- **Controller evidence (adjudication lines 151-154)**: 用户已确认删除不可严格验证的 model-produced ledger；Host 只有 provenance 补集事实，没有可靠自然语言/subject matcher
- **Plan delta (lines 103, 107, 358-359)**:
  - Line 103: `CompactForwardIntentStatusV3` 保留 `open/blocked/superseded`，但 "该 status 只描述待办自身状态，严禁用 `superseded` 伪装 evidence correction/drop reason"
  - Line 107: "rolling correction 只通过 accepted current replacement provenance 与 old labels 的 Host-derived omission 表达"
  - S4 rolling correction evidence 精确化为（lines 358-359）："新口径/current replacement provenance 被 retained；旧口径 source labels 出现在 Host-derived omitted；compact artifact、Memory、post-compact RunInput 与跨进程 reconnect 均不再包含旧结论。不得要求或生成 subjective `superseded` reason。"
- **Verification**: Controller reasoning 成立。原 finding 建议恢复 superseded 语义，但 controller 指出 Host 无法可靠区分 superseded vs redundant vs out_of_scope——这是 v2 的根本问题。Plan 的替代方案（downstream absence + Host-derived omission）是可测试的、确定性的。Forward-intent status 已限域为 intent tracking。S4 evidence 要求已精确化。
- **Disposition**: `evidence-invalid`（原 finding 建议的方向被 controller 拒绝，plan 提供了更严格、可测试的替代方案）

### B-07 — Repair prompt 结构未指定（原 LOW）

- **Controller decision**: `accepted`
- **Controller evidence (adjudication lines 158-161)**: 自足 repair 与 single structure source 必须同时成立
- **Plan delta (lines 158-160)**:
  - "initial 与 repair 共用同一个 packaged system contract，以及同一次 `compact_structure.py` 生成的 concrete template/schema source"
  - "Host 分别渲染 initial user body 与 repair user body，禁止复制第二份手写 output shape"
  - Initial user body 内容指定：同一 immutable v3 input、真实 caps、五类字段含义、nullable clear semantics、provenance 规则、同源 template、最小完整示例
  - Repair user body 内容指定：同一 immutable v3 input、同源完整 template/字段规则、前次 attempt number、bounded/redacted issues、whole-candidate replacement 要求
  - Owner tests (line 338) 覆盖："initial/repair 共用 system contract 与同一 structure template/schema"
- **Verification**: Shared system contract + same structure source + Host-rendered user bodies 避免了双份手写 output shape 漂移。Repair 自足性由 "同源完整 template/字段规则" 保证。Two-body rendering 由 Host 控制，不依赖模型隐式记忆。
- **Disposition**: `fixed`

### Open Question 1 — DeepSeek json_object + temperature=0.4

- **Resolution** (plan line 462): "DeepSeek 是否在当前 temperature/stream/options 组合下稳定返回 JSON 由 S4 真实观察回答；官方 capability 只授权发送 json_object，不替代运行证据。"
- **Disposition**: `resolved` — 官方文档提供 capability 授权，S4 提供真实稳定率观察。设计上不依赖特定 temperature 行为。

### Open Question 2 — Mimo future capability

- **Resolution** (plan line 463): "Mimo 未来若取得 structured-output 直接能力证据，只需后续独立 catalog 配置变更；本 WU 不加入 probe 机制或预留 provider 分支。"
- **Disposition**: `resolved` — config-driven design 使未来 capability 变更为纯数据变更，不需要代码改动。

### Open Question 3 — S5 Oracle 拒绝回路

- **Resolution** (plan lines 365-366, 460, 464):
  - S5 不等待 Oracle controller adjudication
  - Implementation/evidence 可 closeout 但 replacement scenarios 保持 `unadjudicated`/`needs-more-evidence`
  - Oracle 拒绝时创建 follow-up WU，不篡改本 WU 已验证事实
- **Disposition**: `resolved` — S5 的三态分离（implementation/observation/oracle）与回退路径清晰。

---

## Focus area adversarial checks

### 1. Registry supersession / current stable predicate resolution

- **检查**: Plan S5 lines 376-387 的 lifecycle delta。
- **验证**: `cli_ci.md:303,307` 定义 `superseded` 为 "曾被接受，但已被新版本替代"；`cli_ci.md:444` 定义只有 `accepted` 记录参与正式 verdict。Plan 的 `core@1→superseded, core@2→accepted, supersedes=core@1` 完全合规。`cli_ci.md:307` 要求 "不得原地改写旧 oracle"——plan 保留旧 entry 全部 predicates/evidence/adjudication 原文。
- **Stable predicate resolution** (line 387): 611 records 的 `accepted_oracle_refs` 保留历史版本（裁决时依据），当前 verdict 按 stable predicate id 连接到唯一 `status=accepted` 且未被 supersede 的 oracle version。core@1 superseded → 全部 768 refs 的当前解析自然落到 core@2。S5 validation 验证 0 dangling、0 duplicate current owner。与 `cli_ci.md:444` "只有 `accepted` 记录参与正式 verdict" 一致。
- **Removed-ledger scan** (lines 389-390): 直接依赖只有 `drop-superseded@1`、`drop-policy-limit@1`、predicate ids `interactive.29`/`interactive.30`。`tool-trace-formal@1` 因 F11 版本化 supersede，不属于 removed-ledger 依赖。实施时全量扫描并报告任何额外直接依赖。
- **Verdict**: 无新 blocker。Registry lifecycle 与 predicate resolution 合规且可验证。

### 2. Host-internal digest 零 LLM 泄漏

- **检查**: Plan lines 150-151, 161, 439；Invariants line 439。
- **验证**:
  - "Host-internal" 限定词出现在 state machine diagram 两个位置（lines 150-151）
  - 显式声明 "绝不进入 LLM-facing initial/repair system 或 user 文本" (line 161)
  - 反泄漏 test 覆盖两个维度：exact digest value 不存在 AND generic digest field name 不存在 (line 161)
  - Invariant 已冻结 (line 439)
- **Verdict**: 无新 blocker。零泄漏由 invariant、显式声明和双维度 owner test 三层保证。

### 3. Single structure owner

- **检查**: Plan lines 111-118, 158, 338。
- **验证**:
  - `compact_structure.py` 只拥有 JSON 结构（template/schema/parser），不拥有 typed domain dataclass
  - `compaction.py` 只拥有 `CompactCandidateV3` 与 typed children
  - 单向 import: `compact_structure.py → compaction.py`；禁止反向 import
  - Template、schema、parser 全部从同一组 immutable exact structural descriptors 派生
  - JSON Schema 是 immutable canonical JSON value，固定 name `dayu_context_compaction_output_v3` 和 canonical digest
  - Initial/repair 都消费同一次 structure projection，禁止复制第二份手写 output shape (line 158)
  - Owner tests (line 338) 覆盖：template/schema/parser key 集同源、schema immutable/canonical、name/digest/transport 同源、input mutation 不改变 owner-held schema
- **Verdict**: 无新 blocker。Single owner 设计清晰，单向依赖，三层（template/schema/parser）同源且 testable。

### 4. Caps DTO

- **检查**: Plan lines 95-97, 338。
- **验证**:
  - `CompactOutputCapsV3` 是 immutable boundary DTO，不是 caps 第二 owner
  - `MemoryProjectionPolicy` 唯一拥有数值、default、validation 与 policy digest
  - DTO 不定义 default、不做数值校验、不做独立配置读取
  - 构造只通过 `context_governance.py::compact_output_caps_v3_from_memory_policy(policy)` 机械投影
  - `compaction.py` 只定义 DTO，`memory.py` 继续可消费 compaction domain types，二者不互相 import
  - 循环依赖由 Context Governance（已同时依赖两侧）作为直接上游投影边界解决
  - Owner tests 覆盖 "policy → `CompactOutputCapsV3` 逐字段相等且 DTO 无 default/validation" (line 338)
- **Verdict**: 无新 blocker。Single policy owner + immutable DTO + mechanical projection 的设计避免了双 owner 和循环依赖。

### 5. Fresh Tool Trace v2

- **检查**: Plan lines 87, 246。
- **验证**:
  - "删除 v1 reader/validation，不保留双读、兼容 parser 或 adapter"
  - "所有 producer、JSON renderer、Markdown renderer、evidence harness consumer 与 tests 在 S1 同步切到 v2"
  - S1 owner tests 覆盖 "fresh analysis v2 producer/JSON/Markdown/tests 同切且 v1 构造/读取失败" (line 246)
  - 与 adjudication evidence #7 一致：当前 `ToolTraceAnalysisReport.__post_init__` 硬校验 schema version 1
- **Verdict**: 无新 blocker。Fresh cut 策略彻底，全量 consumer 同步切换。

### 6. Full keyset exhaustion

- **检查**: Plan lines 80-84, 246, 436。
- **验证**:
  - 固定正数 page size + `after_event_sequence` 单调 cursor
  - 读尽条件：page 长度 < page size
  - Empty/short page 仅表示正常 exhaustion
  - 异常检测：empty/invalid cursor、full page 后 cursor 不严格增大、reader 返回 sequence 不大于 cursor → 全部 `HostDurableError` fail closed
  - 不设任意总页数 cap
  - 完整 exhaustion 后才返回 None
  - S1 tests 覆盖 multi-full-page、non-progress、damage、不存在 scan-cap limitation
  - Invariant (line 436): "F11 canonical terminal scan 只允许每页有界的 keyset exhaustion；不得加入任意总页数 cap"
- **Verdict**: 无新 blocker。Exhaustion 模式完备：正常终止条件（short page）、异常检测（cursor 不推进）、确定性保证（每页有界 + monotonic cursor）、不可绕过（invariant）。

### 7. Atomic v3 migration

- **检查**: Plan lines 327-336, 474。
- **验证**:
  - 单一 accepted atomic slice 的决策有 explicit rationale (line 327)
  - 内部顺序固定：types → all consumers+prompt → delete v2 → hash/tests
  - 全部在未提交 worktree diff 中完成，不形成中间 checkpoint
  - Rollback: 丢弃该 slice 未提交 intended diff，回到 S2 accepted commit；不保留部分 v3 文件，不触碰用户 dirty files
  - 风险分类为 accepted engineering risk，由 "固定内部顺序、未提交 diff 回滚、两路独立 review 与 aggregate deepreview 缓解" (line 474)
- **Verdict**: 无新 blocker。与原 review 相比，现在多了 explicit rationale、内部顺序、rollback strategy 和 risk classification。这是一个 controlled risk，不是语义 blocker。

### 8. Oracle pending 不阻塞 final closeout

- **检查**: Plan lines 365-366, 384, 460, 464, 487, 494。
- **验证**:
  - S5 不等待 Oracle controller adjudication
  - 三个 replacement scenarios 在 S4 observation 后为 `unadjudicated`（证据完整时）或 `needs-more-evidence`（证据不完整时），绝不标 `accepted`
  - "这不阻塞本 work unit 的 implementation/evidence final closeout" (line 384)
  - 三态分离报告：`implementation=PASS|FAIL`、`real_observation=complete|partial`、`oracle=pending`，"不得合并为单一 ready" (line 385)
  - 后续 Oracle 拒绝 → follow-up WU，"不倒推本 WU 已验证的 implementation 事实" (line 464)
  - Final closeout 中 "未来 Oracle controller 可保持 pending，不是本 work unit final closeout 的前置" (line 494)
- **Verdict**: 无新 blocker。三态分离清晰，pending 不阻塞 closeout，回退路径明确。与 `cli_ci.md` 的 calibration workflow 一致。

---

## New blocker scan

对修订后 plan 做 adversarial scan，检查是否引入原 review 未覆盖的新问题：

1. **S2 Protocol breaking change 完整性**: Plan line 172 要求 `AsyncRunner.call` 增加 "required、无 default 的 keyword-only `structured_output`"，同步更新 Protocol、唯一实现、Agent call site、所有 fake/stub。`@runtime_checkable` Protocol 不验证签名——pyright 是唯一防线。Plan line 272 增加 stop condition："任何 call site 仍依赖旧 signature 时 S2 不得进入 review"。**评估**: 不是 new blocker。Plan 正确识别了依赖 pyright 的风险并设置了显式 gate condition。

2. **S0 §25 edit 范围**: Plan S0 edit list item 8 要求 "将 accept owner、coverage partition、caps/usage audit、repair binding 与 single-terminal 路径全部切到 v3"。§25 当前有 360 行设计文字，涉及 usage-anchored sizing、fallback tiers、reactive multi-pass 等与 v2/v3 无关的复杂机制。实施 Agent 需要区分哪些段落是 v2-specific（需删除）vs v3-relevant（需保留并改写）。**评估**: 不是 new blocker。S0 edit list 的粒度是 "§25" 级——足够定位但需要实施 Agent 的判断。这属于 implementation detail，不是 plan 的设计缺陷。如果实施中出错，S0→S3 的 review gate 会捕获。

3. **`docs/cli_ci.md` 更新边界**: Plan S5 allowed files 包括 `docs/cli_ci.md`（"仅同步当前 registry 使用说明/版本关系"）。但 `cli_ci.md` 是 CLI CI 的总控文档，有独立的更新约束。Plan 的修改范围是 "仅同步当前 registry 使用说明/版本关系"——这是一个 bounded change。**评估**: 不是 new blocker。修改范围明确受限。

4. **611 records predicate resolution 的 edge case**: Plan line 387 说 "0 dangling、0 duplicate current owner"。假设 stable predicate id 集合在 core@2 中不完全覆盖（某个 predicate 只在 core@1 中定义但在 core@2 中被删除），则该 predicate 的 current accepted owner 会是 dangling。**评估**: 不是 new blocker。Plan 已要求 S5 validation 检查 0 dangling。如果发现 dangling，会被 S5 validation 捕获并必须在 closeout 前处理。

5. **`compact_structure.py` 单向 import `compaction.py`**：Plan line 111 说单向 import。但 `parse_compact_candidate_v3` 返回 `CompactCandidateV3`——这要求 `compact_structure.py` import `compaction.py` 的 typed domain types。Plan 确认了这个方向。`compaction.py` 不 import `compact_structure.py`——structure 只是 JSON 辅助，domain types 不需要知道 JSON 结构。**评估**: 不是 new blocker。依赖方向正确。

---

## Residual risks（修订后）

原 review 中列出的 residual risks 在修订 plan 中的处理状态：

| 原 risk | 修订后状态 |
|---|---|
| S3 atomic migration 失败回滚 | Plan 已补充回滚策略（line 336）；分类为 accepted engineering risk（line 474） |
| Mimo 无 structured output 时的 compact 质量 | 保留为 residual risk #1；S4 真实观察 |
| Host-derived omission 不证明业务不重要 | 保留为 residual risk #2 |
| 旧 workspace DB 不可读 | 保留为 residual risk #3；细化：只影响 compact artifact/session replay，不声称整个 DB 不可打开 |
| Tool Trace analysis v2 下游消费者 | 保留为 residual risk #4 |
| 真实 provider 波动 | 保留为 residual risk #5 |
| Mimo none 语义澄清 | 新增 residual risk #6 |
| S3 大 diff review 面 | 新增 residual risk #7 |
| Replacement scenario unadjudicated | 新增 residual risk #8 |

所有 residual risks 都有明确的 owner、handling 或 follow-up WU 指向。

---

## Open questions（修订后）

Plan 的 Open questions 节（lines 454-464）已将原 3 个 open questions 的结果冻结为设计决策。当前没有 blocking open questions。

---

## Final re-review conclusion

**结论：PASS**

理由：

1. **原 7 个 findings 全部关闭**：3 个 `fixed`（B-02 digest 泄漏、B-03 S0 粒度、B-05 capability 证据、B-07 repair 结构）、4 个 `evidence-invalid`（B-01 S3 拆分被 controller 以充分理由拒绝、B-04 pagination cap 被既有 code precedent 证伪、B-06 superseded 语义被用户裁决排除）。没有 still-open finding。

2. **原 3 个 open questions 全部 resolved**：DeepSeek temperature 行为归 S4、Mimo future capability 归独立 catalog change、S5 Oracle 拒绝回路已建立。

3. **八个 focus area 逐一通过**：registry supersession 与 cli_ci.md 合规、digest 零泄漏三层保证、single structure owner 单向依赖、caps DTO 单 policy owner、fresh Tool Trace v2 全量同步、keyset exhaustion 完备、atomic v3 migration controlled risk、Oracle pending 三态分离。

4. **无 new blocker**：修订后的 plan 在 scope、ownership、contracts、slices、state machines、tests、invariants、registry、rollback 和 closeout 方面均 code-generation-ready。

Plan 可以推进到 implementation gate（S0 accepted commit）。
