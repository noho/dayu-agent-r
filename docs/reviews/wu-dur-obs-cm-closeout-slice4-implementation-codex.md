# WU-OBS-P00 Slice 4 implementation artifact

## Gate

- gate: implementation
- work unit: WU-OBS-P00 Runner Call Input Reconstruction Signals
- slice: Slice 4 Tool Trace Reconstruction Signal Projection
- branch: `phaseflow/wu-dur-obs-cm-closeout`
- status: implemented

## Scope

Changed files:

- `dayu/host/tool_trace.py`
- `dayu/host/durable/tool_trace.py`
- `tests/host/test_tool_trace_projection.py`
- `tests/host/test_tool_trace_queries.py`
- `dayu/host/README.md`
- `tests/README.md`
- `docs/reviews/wu-dur-obs-cm-closeout-slice4-implementation-codex.md`

No edits were made outside the allowed production, test, doc, and artifact files.

## First-principles judgment

目标成立。Slice 1-3 已让 Host durable path 产生 runner-call manifest ref、digest、message count、role sequence digest、input projection digest、projector metadata 和 non-complete diagnostic。Tool Trace 是 committed EventLog 的 read model；它应复制这些定位与诊断信号，供 WU-OBS-00 / analyzer fixture 判定 `complete`、`limited_signal`、`mismatch`，但不能反向成为 EventLog、recovery、memory、dispatch 或 Run state truth。

当前实现不需要 schema 变更。`host_tool_trace_hot.trace_summary_json` 已是 hot JSON projection，cold JSONL 也已有 `trace_summary`，可以在限定文件内承载 read-model signal 与 typed query helper。

## Implementation summary

- 在 `dayu/host/durable/tool_trace.py` 新增 typed runner-call reconstruction 查询契约：
  - `RunnerCallReconstructionStatus`
  - `RunnerCallReconstructionDiagnosticReason`
  - `RunnerCallReconstructionMissingAtomKind`
  - `RunnerCallReconstructionMissingRefKind`
  - `RunnerCallReconstructionConsumerBoundary`
  - `ProjectorMetadataSummary`
  - `RunnerCallReconstructionDiagnostic`
  - `RunnerCallReconstructionSignal`
  - `RunnerCallReconstructionSignalPage`
  - `read_runner_call_reconstruction_signals_by_run(...)`
- 查询 helper 只读取 Tool Trace hot projection，不读取 EventLog payload body、manifest body、Engine memory、prompt builder 或当前代码重渲染结果。
- 在 `dayu/host/tool_trace.py` 收紧 runner-call projection：
  - `validation_status` 必须是 `complete`、`limited_signal` 或 `mismatch`。
  - 非 `complete` signal 必须带 typed diagnostic object；缺失时 fail closed。
  - diagnostic reason / missing atom kind / missing ref kind 使用封闭枚举校验。
  - Tool Trace 查询边界固定输出 `consumer_boundary="tool_trace_query"`。
  - projector metadata 只复制 `projector_metadata_id`、`projector_id`、`projector_schema_version`、`projector_digest`、`purpose`。
  - producer-boundary 的 `runner_call_projection_artifact` ref 标签在 Tool Trace query contract 中归一为 `artifact_ref`。
- 未内联长 prompt、完整 messages、provider raw payload、完整工具结果或 manifest body。

## Tests

新增和更新覆盖：

- runner-call complete signal 的 manifest ref / digest / message count / role digest / input projection digest / projector metadata projection。
- `limited_signal` diagnostic projection 与 query-facing `artifact_ref` 归一。
- 非 complete runner-call signal 缺 typed diagnostic 的 fail-closed hardening。
- `mismatch` diagnostic 的 observed / expected count 与 digest。
- 按 Run 查询 `complete`、`limited_signal`、`mismatch` typed reconstruction signals。

Validation executed:

```bash
source .venv/bin/activate && pytest tests/host/test_tool_trace_projection.py tests/host/test_tool_trace_queries.py
source .venv/bin/activate && pyright
git diff --check
```

Results:

- targeted pytest: 15 passed
- pyright: 0 errors, 0 warnings
- git diff --check: passed

## README sync decision

- `dayu/host/README.md`: updated because production Host Tool Trace query behavior changed.
- `tests/README.md`: updated because Host test coverage for Tool Trace reconstruction query and fail-closed diagnostic behavior changed.
- Root `README.md` and `dayu/README.md`: not updated because no user-facing CLI/config entry or stable layer relationship changed.
- `docs/host/design.md`: intentionally not edited per Slice 4 instruction.

## Residual risks

- WU-DUR-P01-S2-R1: fixed in current slice. Tool Trace projection now fails closed when a non-complete runner-call diagnostic payload lacks a diagnostic object, covered by `test_tool_trace_rejects_non_complete_runner_call_without_diagnostic`.
- Full analyzer report: covered by later approved work / non-goal. This slice exposes typed query/helper surface only.
- Full manifest body verification and ref resolution: covered by later analyzer / WU-OBS-00 work. Tool Trace remains a read model and does not become durable truth or recovery truth.
- Compact evidence query readability: covered by later Slice 5; this slice does not change LLM-facing compact evidence text.

## Completion status

Implemented. No blocker was encountered within the allowed file set.
