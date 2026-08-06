# PR 190 F13 S2 Implementation

## Gate metadata

- gate: `implementation`
- work unit: F13 S2 — public Tool Trace 同源投影、README 与 integration
- base: `d4b3ee7cb4b959d88323483ffc430a595938b122`
- branch: `codex/interactive-oracle`
- status: `accepted`
- artifact path: `docs/gateflow/pr-190-f13-s2-implementation-20260806.md`
- staging / commit / push: 未执行，符合 controller 交接约束

## Scope and owner decision

S2 的直接代码证据是：Tool Trace accepted terminal resolver 原本只解析 terminal
binding 和 successful response identity，没有公开 accepted replacement 的逐 fact
provenance；Analyzer summary 因此也无法从 typed owner 消费 claim/refs。在 renderer、
dataset 或 raw artifact 层重新解释 payload 会创建第二 provenance owner，不是合法修复边界。

实现因此保持 owner 链单向：

```text
canonical CONTEXT_COMPACTED payload
  -> parse_context_compacted_semantic_payload
  -> accepted_replacement.evidence_facts
  -> ResolvedCompactorEvidenceFact tuple
  -> ToolTraceCompactorResponseSummary exact pass-through
  -> JSON / Markdown claim + canonical_evidence_refs
```

attempt-rejected 不存在 accepted replacement，其 public fact tuple 固定为空。现有
provider/model/Runner request identity、manifest/operation/attempt binding、完整 keyset exhaustion、
duplicate terminal fail-closed 与 stale/late single-terminal owner 未改动。

## Implemented changes

### Public resolver projection

- 在 `dayu.host.durable.tool_trace` 新增 frozen/slots
  `ResolvedCompactorEvidenceFact(claim, canonical_evidence_refs)`，校验非空 claim、
  非空唯一 refs 与严格 tuple/string shape。
- `ResolvedCompactorResponseIdentity` 新增 `accepted_evidence_facts`。accepted terminal
  在同一 read transaction 中调用 `parse_context_compacted_semantic_payload`，并从
  `accepted_replacement.evidence_facts` 机械复制 claim/refs；attempt-rejected 固定投影
  空 tuple。
- malformed accepted replacement、aggregate 或 source boundary 由同一 strict semantic
  parser fail closed，没有 raw payload、aggregate refs 或 artifact fallback。

### Analyzer pass-through and rendering

- `ToolTraceCompactorResponseSummary.accepted_evidence_facts` 直接复用 resolver 的同一
  `ResolvedCompactorEvidenceFact` tuple，rules 不复制 fact DTO，不重算 refs。
- JSON 中每个 accepted fact 仅输出 `claim` 与 `canonical_evidence_refs`；Markdown
  从同一 summary 渲染同样两项。selection label、source raw payload、credential 与
  prompt 不进入 public fact projection。
- 既有 terminal binding、actual provider/model、Runner request identity 和 provider request id
  availability/value 原样保留。

### Owner tests

- accepted resolver 断言 canonical terminal 与 public fact claim/refs exact 一致。
- attempt-rejected 在 no-success 与 post-success identity 两路都断言 facts 为空。
- 分别篡改 accepted replacement refs、accepted aggregate 与 source boundary refs，断言
  resolver fail closed。
- Analyzer rules 断言 summary 与 resolver 复用同一 tuple object，JSON/Markdown 同源且
  fact object 仅含 claim/refs。
- 在邻近 source payload 注入 selection label、raw payload、credential 和 prompt poison，
  断言两种 renderer 均不泄漏；provider/model/response identity 断言保持。

## Changed files

Production:

- `dayu/host/durable/tool_trace.py`
- `dayu/host/tool_trace_analysis_contracts.py`
- `dayu/host/tool_trace_analysis_rules.py`
- `dayu/host/tool_trace_analysis.py`

Tests:

- `tests/host/test_tool_trace_queries.py`
- `tests/host/test_tool_trace_analysis_rules.py`
- `tests/host/test_tool_trace_analysis.py`
- `tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py`

Docs:

- `dayu/host/README.md`
- `dayu/config/README.md`
- `tests/README.md`
- `docs/gateflow/pr-190-f13-s2-implementation-20260806.md`

`dayu/host/tool_trace_analysis_input.py` 与
`tests/host/test_tool_trace_analysis_input.py` 只经验证，无 typed dataset plumbing 需求，因此未修改。

## Review finding fix

### F1 decision

- review artifact: `docs/reviews/pr-190-f13-s2-review-ds-20260806.md`
- finding: AgentDS F1，`MEDIUM / NEEDS_FIX`。
- Controller decision: `accepted`。
- direct evidence: `ToolTraceCompactorResponseSummary.accepted_evidence_facts` 原有
  `= ()` 默认值；未来 accepted summary 构造方如果遗漏该参数，public contract
  会把“未提供 provenance”静默改写为“合法空 facts”。resolver identity 对应字段
  本来就是 required，summary 默认值造成 contract 不一致。

### Scope amendment

- amendment artifact:
  `docs/gateflow/pr-190-f13-s2-scope-amendment-20260806.md`
- AgentMiMo 与 AgentDS 对 amendment 的 re-review 均为 `ACCEPTED`。
- 新增允许文件仅为
  `tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py`，
  且只允许给唯一既有 attempt-rejected summary 构造显式补
  `accepted_evidence_facts=()`。不改 runtime scenario 语义、fixture、provider/tool
  或 acceptance。

### Minimal fix

- 删除 `ToolTraceCompactorResponseSummary.accepted_evidence_facts` 的默认 `= ()`，
  将 provenance tuple 收紧为 required constructor input。
- 在唯一依赖该默认值的 runtime attempt-rejected expected summary 中显式传入
  `accepted_evidence_facts=()`。运行时行为不变，仅将 contract choice 从隐式
  default 改为显式 typed input。
- 未修改任何其它 production/test 行为，未新增 sentinel、compatibility branch
  或 fallback。

## README decision

- `dayu/host/README.md`: 命中 Host public contract 与 Tool Trace/Memory 消费边界；将已落地
  但仍滞留的 v3/accepted-candidate 文本最小更新为 v4 proposal + accepted
  replacement，并记录 public claim/refs 投影。
- `dayu/config/README.md`: 命中 packaged compaction prompt 职责；将 input/output v3 更新为
  v4 七字段、retain selector 与 current-evidence-only new fact 规则。
- `tests/README.md`: 在现有 Tool Trace Analyzer focused 命令中加入 resolver owner test，
  并说明同源投影/fail-closed 覆盖。
- 根 `README.md`、`dayu/README.md` 和 Engine README 未命中用户入口、分层或 Engine
  contract 变更，未修改。

## Validation

- Focused tests:
  `pytest -q tests/host/test_tool_trace_queries.py tests/host/test_tool_trace_analysis_input.py tests/host/test_tool_trace_analysis_rules.py tests/host/test_tool_trace_analysis.py`
  -> `97 passed in 1.01s`
- F1 fix revalidation: 将上述原 97 focused 与
  `tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py`
  合并执行 -> `133 passed, 3 warnings in 7.90s`。warnings 全部来自 `.venv` 中
  `edgar` 的既有 deprecation warning，无项目测试失败。
- Focused coverage: 同一组 tests 覆盖四个改动生产文件 ->
  `tool_trace.py 85%`, `tool_trace_analysis.py 100%`,
  `tool_trace_analysis_contracts.py 88%`, `tool_trace_analysis_rules.py 94%`,
  total `90%`。
- Changed-file Ruff:
  `ruff check dayu/host/durable/tool_trace.py dayu/host/tool_trace_analysis_contracts.py dayu/host/tool_trace_analysis_rules.py dayu/host/tool_trace_analysis.py tests/host/test_tool_trace_queries.py tests/host/test_tool_trace_analysis_rules.py tests/host/test_tool_trace_analysis.py`
  -> `All checks passed!`
- Target pyright: 上述生产/测试 Python 文件 -> `0 errors, 0 warnings, 0 informations`。
- Full pyright: `python -m pyright dayu/ tests/ utils/` ->
  `0 errors, 0 warnings, 0 informations`。
- Compileall: 改动 Python 文件及 S2 四个 focused test 文件 -> pass。
- F1 changed-file Ruff: S2 改动 Python 文件加 amended runtime fixture ->
  `All checks passed!`。
- F1 target pyright: S2 改动 Python 文件加 amended runtime fixture ->
  `0 errors, 0 warnings, 0 informations`。
- F1 full pyright: `python -m pyright dayu/ tests/ utils/` ->
  `0 errors, 0 warnings, 0 informations`。
- F1 compileall: S2 改动 Python 文件、原 focused tests 与 amended runtime fixture -> pass。
- `git diff --check` -> pass。
- Residue scan: allowed production/tests/README 中无 v3、`CompactAcceptedTruthV3`、
  `accepted_candidate`、schema-4 residue；Tool Trace production 未读取
  `accepted_evidence_mapping_refs` 或 raw artifact 来重建逐 fact provenance。
- Scope scan: 实现 diff 只包含原 S2 allowed files、两路 accepted amendment 新允许的
  唯一 runtime fixture 与本 artifact。工作树中另有 Controller/reviewer 交接的
  scope amendment 和两份 review artifacts，本 fix 未修改它们；无其它无关文件。

## Findings and residual risks

- AgentDS F1: `fixed in current slice`；AgentDS 与 AgentMiMo final fix
  re-review 均为 `ACCEPTED`。
- AgentDS F2/F3 与 AgentMiMo 其余结论: `accepted`。
- implementation findings: 无其它未解决 finding。
- S2 residual risks: 无已知未分类 residual risk。
- 真实 provider observation、全部 Host integration/E2E 与全仓最终 residue/truth scan 属于已批准
  S3，分类为 `covered by later approved slice`；S2 未伪造该运行结果。

## Completion signal

S2 的 public Tool Trace provenance projection、owner tests、README 与 F1 最小修复已完成；
两路 final fix re-review 和 Controller 独立复验均为 `ACCEPTED`，无阻塞。下一入口为 S2
accepted checkpoint 与 aggregate deepreview。
