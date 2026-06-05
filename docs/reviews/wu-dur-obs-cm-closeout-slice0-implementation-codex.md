# WU-DUR-P01 / WU-OBS-P00 / WU-CM-01-F02 / WU-CM-01-F01 Slice 0 Implementation

## Slice 状态

- slice id: implementation Slice 0 - design contract writeback
- status: complete
- agent: AgentCodex
- accepted plan commit: `c1e9de3f`
- plan artifact: `docs/host/wu-dur-obs-cm-closeout-plan.md`
- design source updated: `docs/host/design.md`

## 变更文件

- `docs/host/design.md`
- `docs/reviews/wu-dur-obs-cm-closeout-slice0-implementation-codex.md`

未修改生产代码、测试、README、control doc、plan artifact、其它 review artifact，也未 commit、push、创建 PR 或进入后续 slice。

## design.md 变更章节

- `13.1 Payload 存储`
  - 写入 runner-call manifest 存储形态。
  - 写入 `runner_call_input_manifest`、`runner_call_projection_artifact`、`tool_call_arguments_json`、`tool_call_semantic_query_text`、`compactor_input_projection` descriptor / artifact 边界。
  - 明确完整 rendered messages 只能是派生 artifact，不是 EventLog hot payload 或 recovery truth。

- `13.2 Canonical Event 最小集合`
  - 新增 `RUNNER_CALL_INPUT_ASSEMBLED`。

- `13.3 Canonical Event Contract Matrix`
  - 新增 `RUNNER_CALL_INPUT_ASSEMBLED` 矩阵行，并明确无 Run / Attempt 状态副作用。
  - 扩展 `TOOL_CALL_REQUESTED`，纳入 accepted arguments atom 与 optional semantic query atom。
  - 写入 scalar aliases 与显式 `ToolCallArgumentsAtom` 字段契约。

- `14.1 Tool Trace Hot / Cold Storage`
  - 写入 runner-call reconstruction signal contract。
  - 写入 `RunnerCallReconstructionDiagnostic` 的状态、原因、missing atom/ref、count/digest mismatch 与 consumer boundary。

- `23.1 Runner-call Input Assembly Manifest`
  - 写入完整 `RunnerCallInputAssemblyManifest`、`RunnerCallMessageEntry`、`ProjectorMetadata` 契约。
  - 写入 role sequence digest canonicalization。
  - 写入 source refs、projector metadata、manifest size-boundary 与 no-full-message invariant。
  - 写入 closed `RunnerCallKind` 与 `RunnerCallTriggerReason` 分类。

- `24.2 LLM-facing Compact I/O 硬边界`
  - 写入 compact material / query_text 边界。
  - 明确 F02 根因是 `query_text` 缺少 durable arguments / semantic query 的业务可读表达，不是 `tool_name` 缺失。

- `25 Context Governance`
  - 写入 `CompactorRunnerCallIdentity`。
  - 明确 compactor runner-call identity 只补充 `CONTEXT_COMPACTED`，不替代 compact truth。

## Accepted Plan Contract Mapping

- EventLog / canonical event matrix:
  - 已写入 `RUNNER_CALL_INPUT_ASSEMBLED`，hot payload 只保存 refs / digests / validation status。
  - 已明确无 Run / Attempt 状态副作用，不驱动 recovery / memory / lifecycle / dispatch。

- `TOOL_CALL_REQUESTED` payload contract:
  - 已写入 `ToolCallArgumentsAtom`。
  - 已写入 `payload_inline_threshold_bytes` 的 inline/ref 判定。
  - 已写入 descriptor kinds `tool_call_arguments_json` 与 `tool_call_semantic_query_text`。
  - 已明确 `semantic_input_digest` 不等同于可读 semantic query preimage。

- RunInputBuilder / runner-call manifest:
  - 已写入 `RunnerCallInputAssemblyManifest`、`RunnerCallMessageEntry`、`ProjectorMetadata`。
  - 已写入 role sequence digest canonicalization、source refs、projector metadata、manifest size-boundary 与 no-full-message invariant。

- RunnerCallKind + RunnerCallTriggerReason:
  - 已写入 closed kind / trigger reason 枚举。
  - 已明确 forced answer、length continuation、retry/replay/resume 是 trigger reason，不与 kind 重叠。

- Context Governance / compact:
  - 已写入 `CompactorRunnerCallIdentity`，覆盖 parent run/session、operation id、compactor engine run id、attempt number、request digest、compactor input projection ref、accepted compact ref 与 rejected diagnostic ref。
  - 已明确它与 `CONTEXT_COMPACTED` 的补充关系。

- Tool Trace / reconstruction signals:
  - 已写入 Tool Trace signal fields 与 consumer boundary。
  - 已写入 `RunnerCallReconstructionDiagnostic`，包含 `complete`、`limited_signal`、`mismatch`。

- LLM-facing boundary:
  - 已写入 compact material / prompt / query_text 的自解释边界。
  - 已明确禁止暴露 EventLog ids、refs、digests、cursors、policy names、projector metadata 与 Host internal ledger details。
  - 已明确 F02 根因。

- Slice 0.5 design review acceptance criteria:
  - `docs/host/design.md` 中已可检查 contract shape、inline/ref boundary、kind/trigger classification、compactor identity、Engine vs Host ownership 与 LLM-facing boundary。

## Validation Performed

- 对照 `docs/host/wu-dur-obs-cm-closeout-plan.md` Consolidated Contract Appendix 检查 `docs/host/design.md` 写回内容。
- 运行 targeted `rg` 检查以下 contract 是否写入：
  - `RUNNER_CALL_INPUT_ASSEMBLED`
  - `ToolCallArgumentsAtom`
  - `RunnerCallInputAssemblyManifest`
  - `RunnerCallMessageEntry`
  - `ProjectorMetadata`
  - `RunnerCallKind`
  - `RunnerCallTriggerReason`
  - `CompactorRunnerCallIdentity`
  - `RunnerCallReconstructionDiagnostic`
  - descriptor kinds 与 F02 query_text boundary
- 检查 `git diff -- docs/host/design.md`。
- 运行 `git diff --check -- docs/host/design.md`，无 whitespace error。
- 未运行 `pytest` 或 `pyright`：本 slice 是文档设计写回，未修改生产代码或测试，且任务说明允许此 slice 不跑 pytest/pyright 但必须说明。

## Docs / README Decision

未更新 README。本 slice allowed files 只允许 `docs/host/design.md` 与本 implementation artifact；本次变更是设计真源写回，不改变用户手册、包 README、CLI、配置入口或测试工作流。

## Residual Risks And Next Gate Readiness

- residual risk: provider-specific assistant `tool_calls` / reasoning content 在 Engine 只暴露 raw provider state 时仍按计划 deferred；design 用 `provider_specific_atom_deferred` 表达 limited-signal，未引入 untyped Host bags。
- residual risk: 具体 schema name / version 仍需 Slice 1-7 implementation 和 review 与 design contract 对齐。
- next gate readiness: ready for Slice 0.5 design review.
