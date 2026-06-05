# WU-DUR / WU-OBS / WU-CM Closeout Slice 7 Blocker

## Gate

- gate: implementation
- work unit: WU-CM-01-F01 public smoke correctness closeout
- slice: Slice 7
- status: blocked
- artifact path: `docs/reviews/wu-dur-obs-cm-closeout-slice7-blocker-codex.md`

## First-Principles Judgment

Slice 7 的动机成立。最终 public smoke 不能只证明 Host public API 返回成功，还必须证明发送给 runner / compactor 的 LLM-facing input 满足设计真源：runner-call messages 可解释、compact evidence query 具备业务可读语义、compactor prompt 和 material 不暴露内部实现或迁移术语。

当前 gate 不能完成 implementation acceptance。直接原因不是 smoke 断言缺失，而是生产 compact instruction contract 仍把内部 Python schema 名称投影进 LLM-facing material JSON。修复该 root cause 需要修改 `dayu/host/compaction.py` 或相关生产 compact instruction contract，超出本 Slice 允许文件。按本轮边界要求，必须停止并报告 blocker，不能扩大 scope。

## Direct Evidence

- `dayu/host/compaction.py` 中 `CompactInstructionVNext.output_schema_name` 默认值为 `CONVERSATION_COMPACT_OUTPUT_SCHEMA_NAME_VNEXT`。
- 同一类的 `to_json()` 返回 `{"output_schema_name": self.output_schema_name, "compact_goal": self.compact_goal}`。
- `ConversationCompactInputVNext.to_json()` 把 `"instruction": self.instruction.to_json()` 写入 LLM-facing JSON object。
- `CONVERSATION_COMPACT_OUTPUT_SCHEMA_NAME_VNEXT` 的值是 `ConversationCompactOutputVNext`，这是内部 Python 类型 / schema 名称，不是当前任务必要的业务可读语义。
- `tests/host/test_public_compact_smoke.py` 的 fake compactor 通过 `_material_json_from_compactor_request()` 解析 compactor user prompt 中的 material JSON；因此该 runtime material JSON 路径会暴露上述字段，而不仅是 prompt 模板残留。

## Blocker Reason

Active residual `WU-CM-01-F02-S6-R1` 仍为 blocking：

> Runtime compactor material JSON still exposes `ConversationCompactOutputVNext` through `instruction.output_schema_name`.

该问题不能通过只修改以下 Slice 7 允许文件正确解决：

- `tests/host/public_smoke_support.py`
- `tests/host/test_public_compact_smoke.py`
- `tests/host/test_public_open_host_multiturn_smoke.py`
- `tests/host/test_public_tool_wiring_smoke.py`
- `utils/smoke_host_public_conversation_memory.py`
- `utils/smoke_host_public_diagnostics.py`
- `utils/smoke_host_public_conversation_memory_scenarios.py`
- `utils/smoke_host_public_multiturn.py`

在这些文件中新增断言只能把问题暴露为失败测试，不能移除 LLM-facing 内部术语。root cause owner 应回到生产 compact instruction contract rescope。

## Changed Files

- `docs/reviews/wu-dur-obs-cm-closeout-slice7-blocker-codex.md`

未修改生产 Host 代码、public smoke tests 或 utility smoke scripts。

## Applicability Results

| entry | runner call | compact | result |
| --- | --- | --- | --- |
| `utils/smoke_host_public_conversation_memory.py` | applicable when run normally | applicable through pressure path | `--help` passes; default help states fresh `workspace/tmp` smoke workspace unless `--reuse-session` is requested. Full run can require provider/runtime config and was not executed after blocker classification. |
| `utils/smoke_host_public_diagnostics.py` | not applicable | not applicable | Shared diagnostics printer only; no standalone CLI smoke, no `open_host`, no runner call, no compact trigger. Precise N/A reason: helper only prints duplicate governance assembly diagnostics for an existing `OpenHostOptions`. |
| `utils/smoke_host_public_conversation_memory_scenarios.py` | applicable when run normally | applicable for `--suite long` / `--pressure-mode auto` | `--help` passes; default help states fresh `workspace/tmp` smoke workspace unless `--reuse-session` is requested. Full run can require provider/runtime config and was not executed after blocker classification. |
| `utils/smoke_host_public_multiturn.py` | applicable when run normally | applicable through second-round memory / compact pressure path | `--help` passes; default help states fresh `workspace/tmp` smoke workspace unless `--reuse-session` is requested. Full run can require provider/runtime config and was not executed after blocker classification. |

## Validation

Commands run:

```bash
git branch --show-current
git status --short
source .venv/bin/activate && python utils/smoke_host_public_conversation_memory.py --help
source .venv/bin/activate && python utils/smoke_host_public_diagnostics.py --help
source .venv/bin/activate && python utils/smoke_host_public_conversation_memory_scenarios.py --help
source .venv/bin/activate && python utils/smoke_host_public_multiturn.py --help
source .venv/bin/activate && pyright
git diff --check
```

Results:

- branch: `phaseflow/wu-dur-obs-cm-closeout`
- preflight working tree before artifact: clean
- `smoke_host_public_conversation_memory.py --help`: passed
- `smoke_host_public_diagnostics.py --help`: exited 0 with no output because the file is a shared helper, not a CLI
- `smoke_host_public_conversation_memory_scenarios.py --help`: passed
- `smoke_host_public_multiturn.py --help`: passed
- `pyright`: passed with 0 errors, 0 warnings, 0 informations
- `git diff --check`: passed

Not run:

- affected public smoke pytest files: not run because implementation acceptance is blocked before test changes; running existing tests would not resolve `WU-CM-01-F02-S6-R1`.
- full utility smoke runs: not run because they may require provider/runtime configuration and the gate is already blocked by production contract scope.

## README Decision

No README update. This blocker artifact changes review documentation only and does not change test behavior, utility CLI behavior, project usage, public Host/Engine/Tool Trace boundary, or README-owned stable documentation.

## Residual Risks

- `WU-CM-01-F02-S6-R1`: unclassified for acceptance would block closeout; classified here as requiring production compact instruction contract rescope before WU-CM-01-F01 final public smoke acceptance.
- Public smoke one-system-message / manifest count / role digest assertions remain unimplemented in this Slice 7 pass because the blocker stops implementation before modifying smoke tests.
- Utility smoke full-run validation remains uncovered; owner remains Slice 7 after the production compact instruction blocker is resolved.

## Completion Status

blocked
