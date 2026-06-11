# WU-OBS-SIGNALS-01 Aggregate Deepreview Fix Re-review Controller Adjudication

## Verdict

PASS。WU-OBS-SIGNALS-01 aggregate deepreview gate 通过，可进入 draft PR gate。

## 输入

- AgentMiMo re-review: `docs/reviews/wu-obs-signals-p01-p04-aggregate-deepreview-rereview-mimo.md`
- AgentDS re-review: `docs/reviews/wu-obs-signals-p01-p04-aggregate-deepreview-rereview-ds.md`
- Fix artifact: `docs/reviews/wu-obs-signals-p01-p04-aggregate-deepreview-fix-codex.md`
- Controller adjudication: `docs/reviews/wu-obs-signals-p01-p04-aggregate-deepreview-controller-adjudication.md`

## 裁决

两路 re-review 均为 PASS，Findings 为 None。

Controller 接受 re-review 结论：

- `dayu.host.tool_trace_signals` 只依赖标准库，属于 Host 内部共享 signal contract，不进入 `dayu.runtime`，不引入跨层依赖。
- `tool_runtime.py`、`engine_ingest.py`、`tool_trace.py` 迁移到共享常量后，四类 signal 的 JSON shape、schema version、status、failure kind、bounded text digest 与截断规则保持不变。
- ToolRuntime 校验异常仍为 `ValueError`，Tool Trace projection 校验异常仍为 `HostDurableError`。
- P01/P02/P03/P04 的来源约束未扩大，没有 raw args / raw stream 泄漏。
- README 不更新裁决成立：本次是 Host 内部 contract 去重，不新增稳定 developer-facing 接口、测试层级或运行规则。

## DS 注意级 residual 处理

AgentDS 提到 `BoundedTraceSignalText` 与 `bound_trace_signal_text` 从原模块私有符号变为 `dayu.host.tool_trace_signals` 模块级公开名。Controller 不将其登记为 active residual risk：

- 新模块位于 `dayu.host`，模块 docstring 已明确“只承载 Host 内部多生产者/消费者共享的 Tool Trace signal 字段值、schema version 与 bounded text 裁剪规则”。
- 当前引用方仅为 Host 内部模块。
- 把 Host 内部共享契约做成模块级符号是当前修复的目的，不是对 Service / UI / Engine / tools 的公共 API 承诺。

若未来出现 Host 外部引用，再按 import boundary 或 package export 规则处理；当前无 ownerless residual。

## Validation

Controller 采信并已自行运行同类验证：

```text
source .venv/bin/activate && python -m pytest tests/host/test_engine_ingest_mapping.py tests/host/test_tool_trace_projection.py tests/host/test_tool_trace_queries.py tests/host/test_toolruntime_executor.py tests/host/test_toolruntime_accept_barrier.py tests/host/test_phase6_toolruntime_integration.py
160 passed

source .venv/bin/activate && pyright
0 errors, 0 warnings, 0 informations

git diff --check
OK
```

AgentMiMo 独立复验：160 tests passed、pyright 0 errors、diff check OK。

AgentDS 独立复验：160 tests passed、affected-file pyright 0 errors。

## Remaining Risk

无新增 active residual risk。

WU-OBS-00 analyzer 未落地仍是既有 pending-prerequisite，不是 WU-OBS-SIGNALS-01 的 blocker。

