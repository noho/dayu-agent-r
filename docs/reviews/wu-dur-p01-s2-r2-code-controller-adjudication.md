# WU-DUR-P01-S2-R2 code review controller adjudication

## 结论

`accept`。当前 implementation 通过 code review gate，可以进入提交与 PR 更新。

## 依据

- AgentMiMo code review artifact：`docs/reviews/wu-dur-p01-s2-r2-code-review-mimo.md`，结论 `accept`。
- AgentDS code review artifact：`docs/reviews/wu-dur-p01-s2-r2-code-review-ds.md`，结论 `ACCEPT`。
- Controller 复核期间发现并已修复两个 fail-closed 边界：
  - 既有 `validation_status="mismatch"` link 重放不得追加 accepted `ITERATION_STARTED` preview。
  - mismatch link 与 `ENGINE_EVENT_REJECTED` 不得 seed continuation prior observation。

## 裁决

阻断项：无。

非阻断项：

- MiMo 指出 mismatch link replay 的 rejected reason 使用 `runner_call_manifest_mismatch`，而非 `runner_call_iteration_link_conflict`。Controller 裁决为非阻断：该路径仍表达同一个 prepared manifest 与 Engine observation 不一致的 fail-closed 事实，且测试已覆盖重放不会写 preview。
- DS 指出 `_append_iteration_started_events` 分支密度较高，以及 accepted preview replay 依赖 EventLogStore 同体幂等。Controller 裁决为非阻断：当前行为由 focused tests 与 EventLog append contract 覆盖，后续如继续扩展可再做结构提取。

## 验证

Controller 已重新运行：

```bash
source .venv/bin/activate && pytest tests/host/test_engine_ingest_mapping.py -k "iteration_started or runner_call_manifest"
source .venv/bin/activate && pytest tests/host/test_run_input_builder.py tests/host/test_tool_trace_projection.py tests/host/test_tool_trace_queries.py tests/host/test_public_tool_wiring_smoke.py -k "runner_call or tool_wiring or system"
source .venv/bin/activate && pyright
rg "_runner_call_manifest_matches_iteration|payload_iteration_id is None and iteration_index == 0" dayu/host/engine_ingest.py
git diff --check
```

结果：

- focused Engine ingest tests：13 passed。
- RunInputBuilder / Tool Trace / public wiring selected tests：10 passed。
- pyright：0 errors。
- fallback static search：无匹配。
- diff check：通过。

## 剩余风险

- Tool Trace 最小实现仍不强制投影 `RUNNER_CALL_INPUT_ITERATION_LINKED`；link event 已作为 durable truth 写入，Tool Trace 投影可由后续 owner 扩展。
- `_append_iteration_started_events` 分支密度较高；当前不做结构性重构，避免在本 WU 末尾引入无必要行为风险。
