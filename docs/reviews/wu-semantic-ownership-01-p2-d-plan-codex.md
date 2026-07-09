# WU-SEMANTIC-OWNERSHIP-01 P2-D Plan - AgentCodex

## Goal / Motivation / Success Signal

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P2-D`
- Gate: plan
- Residual owner: P2-C review 阶段记录的 public compact smoke residual
- Plan decision: `ready-for-controller-review`

动机成立，严重性评估正确。当前失败不是测试夹具过严，也不是 compact material 局部字段漏判，而是 accepted tool result 的共享可读投影对 source-unavailable 语义没有给出稳定 LLM-facing 文本，导致直接消费者之一的 compact material 在 evidence block 必填校验处 fail closed。

直接失败信号：

- `tests/host/test_public_compact_smoke.py::test_post_compaction_fact_reuse_uses_raw_accepted_tool_evidence`
- second terminal 为 `HostEventKind.FAILED`
- log 指向 pre-dispatch compact material source failed
- traceback 落在 `dayu/host/compact_material.py::_accepted_tool_evidence_delta_blocks`，向 `run_input_material_block(... readable_source_text=projection.source.text)` 传入 `None`，触发 `RunInputMaterialBlock.__post_init__` 的 evidence material 非空校验。

成功信号：

- accepted-result projection 对 `source.state=UNAVAILABLE` 也返回业务中性、非内部治理字段的 LLM-facing `source.text`。
- compact material、RunInputBuilder、Conversation Memory、Tool Trace / Read API 等消费者继续从同一个 `project_accepted_tool_result(...)` 派生 query/status/source/result 语义，不各自补造 source。
- public compact smoke 能从 raw accepted tool evidence 生成 compact fact，并在后续 RunInput / memory 中复用该 fact。
- LLM-facing source 不暴露 `event_id`、payload ref、digest、cursor、policy、ToolRuntime / Host governance 字段。

## Non-goals / Scope Boundary

- 不修改 durable `TOOL_RESULT_ACCEPTED` schema，不迁移旧库，不兼容旧 source 语义。
- 不改变 accepted evidence envelope 的 provenance / ref / digest 职责；envelope 仍只提供 Host 内部 provenance mapping。
- 不在 compact material、RunInputBuilder、Memory、Tool Trace 或测试 fixture 内用特例分支补默认 source。
- 不把 unavailable source 伪装成财报事实、文档事实或工具结果事实；只能表达“业务来源未提供 / 不可安全展示”这一投影状态。
- 不修改 compactor prompt、compact proposal schema 或 public API。

## Design Alignment

- `docs/host/design.md` 规定 `post_compact_delta_material` 至少包含 readable accepted tool evidence，且用户可见 material 不得包含 attempt id、execution id、cursor、compact failure、projection diagnostic、payload ref、digest、event id 或 Host 内部治理状态。
- `docs/host/design.md` 规定 `evidence_material` 渲染 accepted tool evidence block，raw evidence 内容来自 `TOOL_RESULT_ACCEPTED` canonical fact 指向且 digest 校验通过的 payload / raw result descriptor；accepted evidence envelope 不作为 lossy result preview 或事实内容容器。
- `docs/host/design.md` 规定 semantic query 缺失时 compact evidence projection 可退回 bounded arguments projection 或业务中性不可读说明，但不得渲染 tool_call_id、payload ref、digest、cursor 或 Host 内部账本字段。source-unavailable 应遵循同一 LLM-facing 降级原则。
- `dayu/host/README.md` 已记录 accepted 工具结果投影给 Tool Trace、Read API、Conversation Memory、RunInputBuilder 与 compact material 时，LLM-facing 查询语义、状态语义、结果摘要和业务 source 由 Host 统一投影；下游只消费该投影。

结论：最佳实践是在 projection owner 处提供 source-unavailable 的共享业务语义，而不是让 compact material 或测试夹具发明一份 source。

## First-principles Judgment and Direct Code Evidence

当前问题真实存在：

- `dayu/host/accepted_result_projection.py` 的模块 docstring 声明它把 envelope、request atom、raw outcome、query、status 与 source 投影成下游共享 typed view。
- `AcceptedToolResultSourceProjection.text` 当前类型为 `str | None`，docstring 写明无业务 source 时为 `None`。
- `_source_projection(...)` 在 envelope 缺失或 business source refs 被过滤为空时返回 `text=None`，并通过 `state=UNAVAILABLE` / `diagnostic_reason` 表达原因。
- `dayu/host/compact_material.py::_accepted_tool_evidence_delta_blocks(...)` 消费 `project_accepted_tool_result(...)` 后，把 `projection.source.text` 作为 `RunInputMaterialBlock.readable_source_text`。
- `RunInputMaterialBlock` 虽然字段类型整体允许 `readable_source_text: str | None`，但当 `section is EVIDENCE_MATERIAL` 时明确要求 `readable_source_text` 非空。accepted evidence material 的 source 是 evidence block contract 的必填 LLM-facing 字段。
- `tests/host/test_accepted_result_projection.py` 当前已经覆盖 source refs 为空时 `projection.source.text is None`。这说明缺陷不是 compact material 偶发路径，而是 projection contract 与 evidence material consumer contract 不一致。

为什么不能在 test fixture 或 compact material 下游止血：

- test fixture 改 source refs 只能让这个 smoke 通过，真实工具结果仍可能没有业务 source refs，缺陷会在生产 compact pre-dispatch 路径复现。
- compact material 用 `projection.source.text or "..."` 看似可行，但会把 source-unavailable 文案的所有权放到单个消费者，Memory / Tool Trace / Read API 仍会看到另一套语义。
- compact material 若使用 event id、payload ref、digest、cursor 或 envelope locator 伪造 source，会违反 LLM-facing 文本约束，把 Host 内部 provenance 当成业务来源。
- owner boundary 要求多个消费者需要同一语义时复用同一个 source-of-truth / projection helper；此处 direct consumers 已经共享 `project_accepted_tool_result(...)`，修复必须落在该 owner。

## Root Cause

Root cause 是 accepted-result projection 的 source contract 半收紧：

- query 已有 `ACCEPTED_EVIDENCE_QUERY_UNAVAILABLE_TEXT`，即 request atom / semantic query 不可用时仍返回非空、业务中性、LLM-facing 文本。
- source 只有 `state=UNAVAILABLE` 与 `diagnostic_reason`，但 `text=None`，没有等价的业务中性 LLM-facing 文本。
- compact evidence material 的 public contract 需要完整 evidence block，包括 readable tool name、query、source、result；projection 返回 `None` 导致下游 fail closed。

这不是 compact material 应该允许空 source。evidence material 面向 compactor 和后续 LLM，需要每个 evidence block 具有稳定、可引用的 source 字段；缺 source 时应明确表达“业务来源不可用”，而不是省略字段或注入内部 ref。

## Owner Boundary

语义：accepted tool evidence 的 LLM-facing source。

- 第一次产生事实：ToolRuntime / Host accept path 写入 `TOOL_RESULT_ACCEPTED` payload、accepted evidence envelope 和 raw outcome。它产生工具结果事实与可选 source refs / locator refs。
- 校验事实：accepted evidence envelope 校验 producer ref、tool identity、result ref / digest；request atom 校验 session / run / attempt / execution / tool_call_id / tool_name / normalized args digest；raw outcome 通过 payload descriptor digest 读取。
- 持久化事实：`TOOL_RESULT_ACCEPTED` canonical EventLog row 与 payload descriptor / raw outcome 是 durable truth。
- 共享投影 owner：`dayu/host/accepted_result_projection.py::project_accepted_tool_result` 负责把 durable truth 投影成 LLM-safe query/status/source/result 语义。
- 下游消费者：compact material、RunInputBuilder、Conversation Memory、Tool Trace / Read API 只消费 projection；不能重新从 payload / envelope / refs 猜 source 文本。

## Recommended Implementation

推荐方案：收紧 projection contract，让 `AcceptedToolResultSourceProjection.text` 从 `str | None` 改为 `str`，并新增唯一 source-unavailable LLM-facing 文案常量，例如：

```python
ACCEPTED_EVIDENCE_SOURCE_UNAVAILABLE_TEXT = "业务来源不可用；工具结果未提供可安全展示的来源。"
```

实现决策：

1. 在 `dayu/host/accepted_result_projection.py` 增加 source-unavailable 常量，并导出。
2. 将 `AcceptedToolResultSourceProjection.text` 类型收紧为 `str`，docstring 改为“LLM-facing source 文本；无业务 source 时为业务中性 unavailable 文案”。
3. 保留 `AcceptedToolResultSourceState.AVAILABLE / UNAVAILABLE` 与 `diagnostic_reason`，用它们表达 unavailable 的结构化状态和内部诊断原因。
4. `_source_projection(...)` 在 envelope 缺失或 visible business source refs 为空时返回 `text=ACCEPTED_EVIDENCE_SOURCE_UNAVAILABLE_TEXT`，`state=UNAVAILABLE`，`diagnostic_reason` 分别为现有原因。
5. `_readable_ref_text(...)` 继续过滤 internal source ref kinds，不把 `event`、`eventlog`、`payload`、`artifact`、`digest` 等内部 provenance 变成 LLM-facing source。
6. compact material 不新增 fallback branch；继续传 `projection.source.text`。这样它消费的是同源 projection，而不是 invent source。
7. Tool Trace / Memory / RunInput tests 断言 unavailable source 文本来自 projection 常量，同时继续禁止 event id、payload ref、digest、cursor、wait / poll / runtime governance 字段出现在 LLM-facing 文本中。

为什么选择收紧为 `str`：

- evidence material contract 实际已经要求 source 非空；继续保留 `str | None` 会让每个消费者都必须判断 `None`，并倾向于局部 fallback。
- `state` 与 `diagnostic_reason` 已足够表达 unavailable；`text` 作为 LLM-facing 字段应始终可消费。
- query projection 已使用同样模式：`text: str` + `state` + `diagnostic_reason`。source projection 与 query projection 对齐后，direct consumers 的 contract 更简单。
- 这不是过度设计；它只是把已有 projection owner 的字段从半结构化修正为完整结构化，不新增抽象层、不新增 schema，也不改变 durable truth。

备选方案及拒绝理由：

- 保持 `text: str | None`，新增 helper `source_text_for_llm(projection.source)`：可以保持 single source of truth，但会引入第二个 projection helper，且所有消费者都必须迁移，否则仍有漏点。当前 `AcceptedToolResultSourceProjection` 本身就是 source 投影值对象，直接收紧字段更小、更一致。
- 仅在 compact material 内补 unavailable 文案：拒绝。会造成 compact material 与 Memory / Tool Trace / Read API 语义漂移。
- 使用 event id、payload ref、digest、cursor、policy、ToolRuntime / Host governance 字段作为 source：拒绝。它们是内部 provenance 或治理诊断，不是业务 source，也不能进入 LLM-facing source。

## Affected Files / Modules

Production:

- `dayu/host/accepted_result_projection.py`
  - 新增 source-unavailable 常量。
  - 收紧 `AcceptedToolResultSourceProjection.text` 类型与 docstring。
  - 调整 `_source_projection(...)` unavailable 分支。
  - 更新 `__all__`。
- `dayu/host/compact_material.py`
  - 预计无需行为修改；只在 pyright 暴露类型或 docstring 不一致时做最小同步。
- `dayu/host/durable/memory.py`
  - 直接消费 `projection.source.text` 并写入 `_MemoryProjectionPayloadView.evidence_source_text`。
  - 预计无需行为修改；必须验证 source-unavailable projection 后 memory 投影继续与 accepted-result projection 同源一致。
  - implementation 必须检查并按需更新 memory projection `evidence_source_text` docstring，说明 accepted-result 正常路径由 projection owner 保证非空 source text；字段整体仍可保留 `str | None`，用于覆盖非 accepted-result、初始构造或 fallback 路径。
- `dayu/host/compaction.py` / `dayu/host/run_input.py` / `dayu/host/compact_pipeline.py`
  - 预计无需行为修改；作为受影响消费者验证其继续消费非空 source 文本。
- `dayu/host/README.md`
  - implementation 后必须先按 README 更新约束检查。预计无需更新，因为 README 已记录统一 projection owner；若实现使 source-unavailable contract 成为稳定开发接口，可在 Host memory / context governance 相关章节补一句当前代码事实。

Tests:

- `tests/host/test_accepted_result_projection.py`
  - 修改 source refs 为空的断言：`projection.source.text == ACCEPTED_EVIDENCE_SOURCE_UNAVAILABLE_TEXT`，`projection.source.state is UNAVAILABLE`，并继续断言内部 refs 被过滤。
  - 增加或扩展 direct consumer equivalence test，覆盖 unavailable source 在 compact material / run input text / memory / tool trace 中同源出现。
- `tests/host/test_compact_material.py`
  - 增加 focused test：accepted evidence 缺业务 source refs 时，pre-dispatch compact material builder 不 fail closed，evidence block 的 `readable_source_text` 等于 projection 常量。
- `tests/host/test_run_input_builder.py`
  - 覆盖 accepted tool evidence block source-unavailable 仍能进入 RunInput，并禁止内部 refs 泄漏。
- `tests/host/test_memory_projection.py`
  - 覆盖 Conversation Memory 对 source-unavailable 的文本与 projection 一致，且不重建 payload / event refs。
  - 若 `dayu/host/durable/memory.py` 更新了 `evidence_source_text` docstring，测试仍只断言业务投影行为，不为 docstring 改动补无效断言。
- `tests/host/test_tool_trace_projection.py` / `tests/host/test_tool_trace_queries.py`
  - 如现有 trace summary 暴露 source 文本，更新或补充 unavailable source 断言；若只暴露 state / refs，则确认不需要修改。
- `tests/host/test_public_compact_smoke.py`
  - 保留 targeted smoke，不用改 fixture 使其携带 source refs；该 smoke 应证明真实 residual 已被 owner 修复。
- `tests/README.md`
  - implementation 后按 README 更新边界检查。预计无需更新，因为不新增测试层级、运行方式或维护规则。

Plan artifact:

- 本 gate 只新增 `docs/reviews/wu-semantic-ownership-01-p2-d-plan-codex.md`，不修改 production / test / README。

## Implementation Slices

建议单 slice 完成。

理由：

- 这是一个单字段语义 contract 收紧，production 改动集中在 projection owner。
- tests 必须与 contract 同步，否则中间状态会在 pyright 或消费者测试中失败。
- 不涉及 durable schema、Host public API、Engine contract 或跨层装配。

Slice P2-D-S1:

- Objective: projection source-unavailable contract 收紧并验证所有 direct consumers 同源。
- Allowed production files: `dayu/host/accepted_result_projection.py`；仅当类型同步需要时允许最小触碰 `dayu/host/compact_material.py`；仅当 docstring 同步需要时允许最小触碰 `dayu/host/durable/memory.py` 的 memory projection `evidence_source_text` 说明，不做行为修改。
- Allowed tests: 上述 Host projection / compact material / run input / memory / trace / public compact smoke 相关测试。
- Non-goals: 不修改 fixtures 来绕过 source-unavailable；不新增 compatibility helper；不改 durable schema。
- Completion signal: focused tests、targeted smoke、pyright、`git diff --check` 全部通过。

## Validation Plan

Implementation 后必须执行：

```bash
source .venv/bin/activate && pytest tests/host/test_public_compact_smoke.py::test_post_compaction_fact_reuse_uses_raw_accepted_tool_evidence -q
source .venv/bin/activate && pytest tests/host/test_accepted_result_projection.py -q
source .venv/bin/activate && pytest tests/host/test_compact_material.py tests/host/test_run_input_builder.py tests/host/test_memory_projection.py -q
source .venv/bin/activate && pytest tests/host/test_tool_trace_projection.py tests/host/test_tool_trace_queries.py -q
source .venv/bin/activate && pyright
git diff --check
```

Expected assertions:

- targeted public compact smoke 的 first / second / third terminal 都为 `SUCCEEDED`，compactor material 有 evidence material，后续 RunInput 包含从 raw accepted tool evidence 生成的 stable fact。
- accepted-result projection tests 证明 available source 保持业务 source refs，unavailable source 统一为 source-unavailable 常量，state / diagnostic_reason 仍可区分 envelope missing 与 business source unavailable。
- compact material evidence block 的 `readable_source_text` 永远来自 projection；source unavailable 时不 crash、不泄漏 internal refs。
- memory / run input / trace 中同一 accepted result 的 query/status/source/result 与 projection 一致。
- pyright 无新增或扩散报错。

Required source-leak scan:

```bash
rg -n "event_id|payload_ref|payload_digest|cursor|policy|ToolRuntime|Host governance|digest" dayu/host/accepted_result_projection.py tests/host/test_accepted_result_projection.py
```

该扫描必须覆盖 `dayu/host/accepted_result_projection.py` 和 `tests/host/test_accepted_result_projection.py`，防止 production 文案或测试期望意外认可内部 refs。扫描结果只作辅助审查，不作为机械 pass/fail；最终以 LLM-facing 输出断言为准。

## README / Docs Decision

- `dayu/host/` production 修改触发 `dayu/host/README.md` 检查。当前 README 已说明 accepted tool result 的 query/status/result/source 由 Host 统一投影，预计无需更新；若 implementation 新增 public constant 并在开发者契约中稳定使用，可做最小补充。
- `tests/` 修改触发 `tests/README.md` 检查。预计无需更新，因为只补充现有 Host 测试，不新增层级、运行方式或维护规则。
- 不更新根 README、`dayu/README.md`、`docs/host/design.md` 或 `docs/engine/design.md`；设计真源已支持该 owner boundary。

## Propagation Audit

P2-D 修复后必须逐段确认：

1. accepted payload / envelope / raw outcome:
   - `TOOL_RESULT_ACCEPTED` payload / accepted evidence envelope / raw outcome 仍是 durable truth。
   - source refs / locator refs 只作为 raw provenance 输入，内部 ref kinds 不直接进入 LLM-facing source。
2. accepted-result projection:
   - `project_accepted_tool_result(...)` 读取 digest-checked payload / request atom / envelope。
   - query/status/result/source 一次性投影完成。
   - source available 时输出业务 source refs；source unavailable 时输出唯一 source-unavailable LLM-facing 文案，并用 state / diagnostic_reason 记录诊断。
3. compact material pack:
   - `_accepted_tool_evidence_delta_blocks(...)` 使用 projection 的 `result_text`、`query.text`、`source.text` 构造 evidence material block。
   - canonical refs / payload refs 只保留为内部 provenance，不进入 source 文本。
4. compactor proposal:
   - compactor material 的 evidence section 包含 raw accepted tool evidence、query、source-unavailable 文案和 prompt-local label。
   - fake / real compactor proposal 只引用 prompt-local labels，不读取 canonical refs 作为业务事实。
5. accepted compact fact:
   - accepted compact output 的 evidence-backed fact 只基于 evidence material 的业务内容与 label map。
   - unavailable source 文案不能升级为财报事实或结论，只能作为该 evidence block 的来源状态说明。
6. follow-up RunInput / memory / trace visible output:
   - 后续 RunInput 通过 Conversation Memory / compacted view 看到同一 stable fact。
   - Conversation Memory、RunInputBuilder、Tool Trace / Read API 的 readable query/status/source/result 都从 projection 派生。
   - 不出现“compact 正确但 memory 错误”或“trace 正确但 RunInput 错误”的双语义。

## Risks / Open Questions

- 风险：现有测试断言 `projection.source.text is None`，需要按新 contract 改为 unavailable 文案。该变更是期望的 contract 收紧，不是兼容破坏。
- 风险：Memory 或 trace 当前可能不展示 source 文本；如果消费者没有 source 字段，只需证明它没有重建或泄漏内部 refs，不强行新增展示能力。
- 风险：source-unavailable 文案的中文措辞必须保持业务中性，避免暗示工具结果无效。建议使用“业务来源不可用；工具结果未提供可安全展示的来源。”这类状态说明。
- Blocking open questions: 无。

## Completion Report Format

Implementation closeout 应报告：

- 改了哪些 production/test/README 文件。
- `AcceptedToolResultSourceProjection.text` 是否已收紧为 `str`，source-unavailable 常量文本是什么。
- propagation audit 结果。
- 执行的 validation commands 与结果。
- README 检查结论。
- residual risks / uncovered areas。
