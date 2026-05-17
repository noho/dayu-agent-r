# P9.5 Aggregate Deepreview Controller Adjudication

## 范围

- Work unit: P9.5 Pre-P10 Cross-Repository Hardening PR
- 设计真源: `docs/host/design.md`
- 总控文档: `docs/host/implementation-control.md`
- Aggregate review artifacts:
  - `docs/reviews/p9-5-aggregate-deepreview-mimo-20260517.md`
  - `docs/reviews/p9-5-aggregate-deepreview-ds-20260517.md`
- Accepted-finding fix re-review artifacts:
  - `docs/reviews/p9-5-aggregate-fix-rereview-mimo-20260517.md`
  - `docs/reviews/p9-5-aggregate-fix-rereview-ds-20260517.md`

## 结论

P9.5 aggregate deepreview gate 通过。MiMo 的 F1/F2/F3 裁决为 accepted 并已修复；MiMo F4/F5/F6 裁决为 non-blocking no-fix；F7 随 F1 修复自动消解。AgentMiMo 与 AgentDS 对 accepted-finding fix 的 re-review 均为 PASS，0 blocking / high / medium / low finding。

## Finding 裁决

| Finding | Severity | Controller 裁决 | 处理 |
|---|---:|---|---|
| MiMo F1: EventLog canonical inline payload 阈值硬编码默认值 | MEDIUM | accepted | 移除 EventLog 模块默认常量，通过 `HostDurableStoreOptions.payload_policy.payload_inline_threshold_bytes` -> `HostTransactionRunner` -> `HostTransaction` 注入，并由 EventLog validation 读取当前 transaction 阈值。 |
| MiMo F2: dispatch waiting / worker accepted CAS 缺少 `cancelled_event_sequence IS NULL` | LOW | accepted | 两个 WHERE guard 补齐 `cancelled_event_sequence IS NULL`，与 dispatching guard 对齐。 |
| MiMo F3: 截断后仍超限时 cursor 泄漏 | LOW | accepted | `_store_cursor` 后的替换失败与超限 failure path 均清理未返回 cursor。 |
| MiMo F4: `fetch_more` 先加载再检查 inline size | LOW | rejected-as-current-fix | 当前实现必须先 materialize continuation 才能按 canonical tool outcome 投影计算 inline size；`request.limit` 已有上界。streaming size check 属后续性能优化，不阻塞当前 PR。 |
| MiMo F5: `RunSuspendedData` 分支 iteration check 可读性弱 | INFO | no-fix | 该 check 对 `ToolAwaitingData` 分支仍有行为意义；当前统一后置检查无错误行为。 |
| MiMo F6: schema v7 -> v8 无 migration | INFO | rejected-as-intended | 项目 schema 约束要求按 fresh schema 起库，禁止旧库兼容读取。 |
| MiMo F7: EventLog class 前空行 | STYLE | fixed-by-F1 | F1 移除常量后已满足 class 前空行要求。 |
| DS aggregate review | - | PASS | 无 finding。 |

## 修复摘要

- `dayu/host/durable/transaction.py`: `HostTransactionRunner` 保存 durable store 注入的 payload inline 阈值，并在 write/read transaction wrapper 上暴露 `payload_inline_threshold_bytes`。
- `dayu/host/durable/connection.py`: 从 `HostDurableStoreOptions.payload_policy.payload_inline_threshold_bytes` 显式注入 transaction runner。
- `dayu/host/durable/event_log.py`: canonical fact inline payload size guard 读取当前 `HostTransaction` 阈值，不再导入或硬编码默认值。
- `dayu/host/durable/state.py`: dispatch waiting / worker accepted CAS 补齐 `cancelled_event_sequence IS NULL`。
- `dayu/host/tool_runtime.py`: 截断 failure path 清理未返回 cursor。
- `tests/host/test_event_log_store.py`: 增加自定义 store policy 阈值验证。
- `tests/host/test_toolruntime_executor.py`: 增加截断后仍超限 cursor cleanup 验证。
- `dayu/host/README.md` 与 `tests/README.md`: 同步当前行为与测试覆盖事实。

## 验证

- `source .venv/bin/activate && pytest tests/host/test_event_log_store.py tests/host/test_durable_transaction.py tests/host/test_toolruntime_executor.py tests/host/test_run_attempt_transitions.py -q`: 77 passed
- `source .venv/bin/activate && pytest -q`: 1068 passed
- `source .venv/bin/activate && python -m pyright dayu tests`: 0 errors / 0 warnings / 0 informations
- `git diff --check`: clean

## 剩余风险

无当前 P9.5 PR blocking residual risk。MiMo F4 的 streaming / incremental `fetch_more` size optimization 属性能 hardening，不改变 Host truth、EventLog、ToolRuntime accept path 或 public contract；当前不作为 P9.5 阻塞项。
