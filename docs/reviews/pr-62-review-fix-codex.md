# PR 62 Review Fix - AgentCodex

## Source Review Artifacts

- `docs/reviews/pr-62-deepreview-mimo.md`：结论 FAIL。
- `docs/reviews/pr-62-deepreview-ds.md`：结论 PASS，含 high findings。

## Accepted Findings

- A / MiMo #1：删除 `HostHandle` 兼容别名与 public export。
- A / MiMo #2：从 `dayu.host.api.__all__` 移除 internal / low-level 类型。
- A / MiMo #3：从 package-root 与 `api.__all__` 移除 `HostInput` public export。
- A / MiMo #4：从 `read_api.__all__` 移除 `stream_run_events`。
- A / MiMo #5：清理 `dayu/host/__init__.py` 中旧 Phase 4 语义。
- B / DS F1：fake compactor 的 `budget_after_compact` 与真实 LLM compactor hard clamp 对齐。
- C / DS F2：reactive compaction 写回前增加 stale `input_event_sequence` guard。
- D / MiMo #8：runtime lane cancellation cleanup 显式 `raise cancelled`。
- E / manual smoke blocker：诊断并修复 round2 `submit_followup` accepted 后未 committed 的阻断。

## Fix Status

- A：已修复。`HostHandle` alias 删除；`HostInput` 不再从包根或 `api.__all__` 公开；`HostCommandFacet`、`HostCommandHandleOptions`、`HostEventStream`、`HostEventView`、`HostLocalExecutionOptions`、`StartRunRequest` 不再进入 `api.__all__`；`read_api.__all__` 只保留 `get_run` / `get_session`；README 与 export 测试已同步。
- B：已修复。`FakeContextCompactor` 使用 `min(estimated // 2, hard_threshold_tokens - 1)` 并保持非负 clamp；新增 fake clamp 测试。
- C：已修复。reactive pending 保存 expected input event sequence；LLM compaction 返回后在写事务内重查 Run status 与 input sequence，stale 时写 `CONTEXT_COMPACTION_FAILED(failure_reason=stale_compaction_result)`，不写 `CONTEXT_COMPACTED`，不启动 recovery Attempt；新增 stale sequence 竞争测试。
- D：已修复。`dayu/runtime/lane.py` cancellation cleanup 分支改为显式 `raise cancelled`。
- E：已修复。根因不是 DeepSeek/network；round2 admission 失败来自大 `USER_INPUT_ACCEPTED` canonical payload 超过 inline threshold。新增 `dayu.host.payload_resolution.event_payload_object`，admission 对超限用户输入写 SQLite payload descriptor，dispatch / engine_ingest / RunInputBuilder 读取时跟随 descriptor。

## Changed Files

- `dayu/host/api.py`
- `dayu/host/__init__.py`
- `dayu/host/read_api.py`
- `dayu/host/fake_compaction.py`
- `dayu/host/engine_ingest.py`
- `dayu/host/admission.py`
- `dayu/host/dispatch.py`
- `dayu/host/run_input.py`
- `dayu/host/payload_resolution.py`
- `dayu/runtime/lane.py`
- `tests/host/test_package_exports.py`
- `tests/host/test_compaction_contract.py`
- `tests/host/test_engine_ingest_mapping.py`
- `tests/host/test_admission_queue.py`
- `dayu/README.md`
- `dayu/host/README.md`
- `tests/README.md`
- `docs/reviews/dayu-readme-sync-codex.md`
- `docs/reviews/pr-62-review-fix-codex.md`

## Validation

- `source .venv/bin/activate && pytest tests/host/test_package_exports.py tests/host/test_compaction_contract.py tests/host/test_engine_ingest_mapping.py tests/host/test_admission_queue.py tests/runtime/test_lane.py -q`
  - Result: `107 passed in 1.08s`
- `source .venv/bin/activate && pyright dayu/host dayu/runtime tests/host/test_package_exports.py tests/host/test_compaction_contract.py tests/host/test_engine_ingest_mapping.py tests/host/test_admission_queue.py tests/runtime/test_lane.py`
  - Result: `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - Result: passed
- `source .venv/bin/activate && python utils/smoke_host_public_multiturn.py --log-level DEBUG`
  - Result: `SMOKE PASS public Host handle completed three-turn closure`

## Manual Smoke Diagnosis

- Reproduced blocker before fix: log reached `SMOKE ROUND_START label=round2-memory-and-compact` and `host.command.accepted operation=submit_followup` but failed before `host.command.committed`.
- Direct traceback showed `HostPayloadReferenceError: EventLog canonical_fact payload_json exceeds inline payload limit; use payload_ref and payload_digest for large canonical content` from `EventLogStore.append_event` while appending `USER_INPUT_ACCEPTED`.
- Evidence excludes provider/network as root cause: round1 DeepSeek HTTP returned 200 and completed; failure occurred before round2 dispatch / runner call.
- Root cause: smoke 的 round2 prompt 触发 `payload_inline_threshold_bytes=4096`，但 admission 仍把完整 `display_text` / `user_prompt` 写入 inline canonical payload。
- After fix: round2 出现 `host.command.committed`，三轮 closure 完成，compact artifact 文件数为 1，最终 `SMOKE PASS`。

## Residual Risks

- `stream_run_events` 函数定义仍保留在 `dayu.host.read_api`，但不再进入 `__all__`；内部 diagnostic / 低层测试仍可显式模块路径导入。
- `HostInput` 类定义仍保留在 `dayu.host.api`，供低层 `StartRunRequest` 与内部 admission 路径使用；不再作为 public export。
- manual smoke 依赖真实 DeepSeek provider，已在本次环境通过；CI 若缺少 API key 仍需要独立 provider-smoke 策略治理。
