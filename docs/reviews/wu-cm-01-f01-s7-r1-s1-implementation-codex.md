# WU-CM-01-F01-S7-R1-S1 Implementation Codex

## Gate

- gate: implementation
- work unit: `WU-CM-01-F01-S7-R1`
- slice: `S7-R1-S1`
- branch: `phaseflow/wu-dur-obs-cm-closeout`
- design source: `docs/host/design.md`
- accepted plan: `docs/host/wu-cm-01-f01-s7-r1-one-system-message-rescope-plan.md`
- S0 accepted commit: `fc94e597`
- bookkeeping commit: `84de6fcc`
- artifact path: `docs/reviews/wu-cm-01-f01-s7-r1-s1-implementation-codex.md`

## Scope

本轮实施 ordinary public RunInput 的 one-system-message hard contract。动机成立：public smoke 已从真实 `open_host()` / `submit_followup()` runner requests 观测到多条 system message，根因在 `RunInputBuilder.build()` 将 caller prompt、scene、memory、compact、continuity 与 fallback material 直接展开后投给 Engine。

本轮未修改 Engine / Runner public contract、Service/API、Host public request dataclass 或 durable schema；也未删除或放宽 Slice 7 retry 红测。

## Changed Files

- `dayu/host/run_input.py`
  - 在 RunInputBuilder 最终边界新增 `_normalize_ordinary_run_messages()`，从候选 messages 全局抽取 system-scoped material，按设计固定 section 顺序渲染单条 leading system envelope，并保持非 system messages 原序。
  - `RUNNER_CALL_INPUT_ASSEMBLED` recorder 现在消费 normalization 后的最终 `messages`，因此 manifest `message_count`、`message_entries` 与 `role_sequence_digest` 和实际 Engine / Runner 输入同源。
  - scene execution guidance 改为 Host-neutral 业务说明，不再投影 `policy_snapshot_ref`、operation kind、execution target 或 queue policy。
  - memory facts 改为只投影 `claim_text`、事实类型和 prompt-local `Source F<n>` 标签，不再投影 EventLog id / sequence、evidence refs 或 extraction operation ref。
  - accepted compact view 只投影 accepted summary / counts，不再投影 compact artifact ref / digest 或 compacted event cursor。
  - selected recent evidence、fallback accepted tool evidence 和 wait resume material 统一路由到 `Recent Evidence` / `Resume Guidance`，并移除 `tool_call_id`、wait id 与内部恢复字段。
  - envelope 校验包含 deterministic header / separator overhead sanity，以及内部治理标识禁露检查。
- `tests/host/test_run_input_builder.py`
  - 旧多 system / 旧 memory header 断言迁移为 single system envelope、固定 section、role preservation 与内部字段禁露断言。
  - 保留 recent raw user / assistant role continuity 断言。
  - 更新 compact candidate summary 断言，不再期望 LLM-facing summary 暴露 schema version。
- `tests/host/public_smoke_support.py`
  - `assert_at_most_one_system_message()` 增强为：至多一条 system；若存在，必须在 index 0。
- `tests/host/test_public_compact_smoke.py`
  - 保留 public path one-system assertion，fact reuse 断言迁移到 `## Verified Evidence and Facts` section。
- `dayu/host/README.md`
  - 同步 RunInputBuilder ordinary one-system-message envelope 与 LLM-facing internal-field ban。
- `tests/README.md`
  - 同步 public smoke helper 的首位 system contract 与 RunInputBuilder envelope 覆盖范围。
- `docs/host/issues-implementation-control.md`
  - gate bookkeeping 更新到 S1 review gate。

## Contract Status

- Ordinary public `AgentRunRequest.messages`: now at most one `system` message; when present it is first.
- User / assistant continuity roles: preserved.
- Tool role authority: unchanged; ordinary historical evidence still enters system envelope unless Engine contract later supports historical tool role.
- Manifest schema: unchanged; values now reflect normalized final messages.
- Durable schema / migration: unchanged.
- Public Host / Service / Engine dataclasses: unchanged.

## Validation

- `source .venv/bin/activate && pytest tests/host/test_run_input_builder.py tests/host/test_public_tool_wiring_smoke.py tests/host/test_public_open_host_multiturn_smoke.py tests/host/test_public_compact_smoke.py -q`
  - result: `56 passed, 1 skipped in 7.37s`
- `source .venv/bin/activate && pyright`
  - result: `0 errors, 0 warnings, 0 informations`
  - note: pyright only reported an available version update warning.
- `git diff --check`
  - result: passed, no whitespace errors.

## README Sync Decision

- `dayu/host/README.md`: updated because it previously described RunInputBuilder memory fact rendering as exposing `evidence_refs`, extraction operation ref, and EventLog id / sequence, which conflicts with the new ordinary LLM-facing envelope boundary.
- `tests/README.md`: updated because public smoke helper semantics and focused RunInputBuilder coverage changed.
- root `README.md`: not updated; CLI commands, installation, trace/render entry points and user workflows did not change.
- `dayu/README.md`: not updated; `UI -> Service -> Host -> Engine` boundary and composition responsibility did not change.

## Residual Risks

- No blocker found that requires Engine / Runner public contract, schema, Service/API, or cross-layer boundary changes.
- Remaining review focus: verify section routing still matches `docs/host/design.md` §23 section table and §24.6 assembly-order concepts, especially accepted evidence versus recent fallback unique routing.
- Real provider matrix remains environment-gated and was not required for this deterministic production shape slice.

## Status

Implementation complete and ready for S7-R1-S1 code review. No commit was created.
