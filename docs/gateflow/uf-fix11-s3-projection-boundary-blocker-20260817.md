# UF-FIX11 S3 projection boundary blocker

## 状态

- classification：`plan slice boundary blocker`
- gate：UF-FIX11 S3 implementation
- 状态：paused
- 实现动作：已停止；production、test、README 均无修改
- Git 动作：未 stage、commit、push，未创建 PR

## 直接代码与调用链证据

真实 direct upload 投影链为：

```text
DefaultFinsIngestionRuntime direct upload
  -> upload_runner.run_upload(...)
  -> FinsUploadResultSummary
  -> ingestion_runtime._direct_upload_terminal_events(summary=...)
  -> ingestion_runtime._direct_result_event(...)
  -> FinsResultSummary(...)
  -> FinsEvent.result
```

关键代码位置：

- `dayu/fins/ingestion_runtime.py:4508-4518`：`run_upload` 返回 typed `summary`，并把同一对象传入 `_direct_upload_terminal_events`。
- `dayu/fins/ingestion_runtime.py:6510-6517`：`_direct_upload_terminal_events` 的参数直接包含 `FinsUploadResultSummary`。
- `dayu/fins/ingestion_runtime.py:6547-6559`：该 helper 调用 `_direct_result_event`；当前只传 status/details/failure 等字段，没有 warning 参数。
- `dayu/fins/ingestion_runtime.py:6434-6444`：`_direct_result_event` 当前签名没有 warning 参数。
- `dayu/fins/ingestion_runtime.py:6497-6506`：`FinsResultSummary` 的真实 production 构造发生在该 helper 内。

以下为本次只读检查得到的 production helper `rg` 全集：

```text
$ rg -n "_direct_upload_terminal_events|_direct_result_event" dayu
dayu/fins/ingestion_runtime.py:4513:        terminal_progress, terminal_result = _direct_upload_terminal_events(
dayu/fins/ingestion_runtime.py:6231:        event = _direct_result_event(
dayu/fins/ingestion_runtime.py:6434:def _direct_result_event(
dayu/fins/ingestion_runtime.py:6510:def _direct_upload_terminal_events(
dayu/fins/ingestion_runtime.py:6547:    result_event = _direct_result_event(
```

以下为 `FinsResultSummary` production/test 构造点的 `rg` 全集：

```text
$ rg -n "FinsResultSummary\\(" dayu tests
tests/cli/test_fins_commands.py:958:        result=FinsResultSummary(
tests/cli/test_fins_commands.py:3841:        result=FinsResultSummary(
dayu/fins/ingestion_runtime.py:6497:        result=FinsResultSummary(
dayu/fins/ingestion_runtime.py:7229:    return FinsResultSummary(
dayu/fins/ingestion_runtime.py:7284:    return FinsResultSummary(
dayu/fins/ingestion_runtime.py:7333:    record.result = FinsResultSummary(
tests/cli/test_output.py:168:        result=FinsResultSummary(
tests/cli/test_output.py:263:    failed_summary = FinsResultSummary(
tests/cli/test_output.py:281:        result=FinsResultSummary(
tests/service/test_fins_wait_adapter.py:312:    result = FinsResultSummary(
tests/service/test_fins_wait_adapter.py:396:    result = FinsResultSummary(
tests/service/test_fins_wait_adapter.py:443:                result=FinsResultSummary(
tests/service/test_fins_wait_adapter.py:758:    return FinsResultSummary(
tests/service/test_fins_direct.py:268:        result=FinsResultSummary(
tests/service/test_fins_direct.py:1014:        FinsResultSummary(
tests/fins/test_fins_direct_stream.py:144:    return FinsResultSummary(
tests/fins/test_fins_ingestion_tools.py:433:    return FinsResultSummary(
```

## 为什么 `direct_events.py` 无法独自完成

`dayu/fins/direct_events.py` 只定义 `FinsResultSummary`、`FinsEvent` 与 validated stream contract。只读 `rg` 结果表明，该模块没有 `FinsUploadResultSummary` 引用；production 中拥有 typed upload summary 并构造 direct result 的位置都在 `ingestion_runtime.py`。

因此，仅在 `direct_events.py` 给 `FinsResultSummary` 增加 warnings 字段与 success-only invariant，只能建立目标 contract，不能把真实 `FinsUploadResultSummary.warnings` 复制进去。让 `direct_events.py` 反向 import `ingestion_runtime.py` 会形成错误依赖或循环依赖，也不能改变真实构造点仍未传值的事实。

## 不可接受的替代方案

- 从 `details` 推断：details 是展示投影，不是 warning 事实 owner；解析展示文本会制造第二套隐式协议，并违反 typed copy 要求。
- 从 raw request 推断：请求只能表达 submitted intent，不能证明 publication-lock 后最终公司名是否采用；这会绕过已冻结的 publication-final owner。
- 全局默认传空：给所有 `FinsResultSummary` 默认 `warnings=()` 可保持旧构造点可运行，但真实成功 upload warning 会在 direct/CLI/tool 链静默丢失，不能满足同源传播。
- compatibility shim：wrapper、facade、全局 side channel 或下游 fallback 都会隐藏缺失的 owner-boundary 参数，违反项目禁止兼容 shim、禁止下游补偿与严格分层约束。

## 最小 plan amendment 建议

只修正 S3 的 symbol boundary，不扩大文件、业务目标或 warning owner：

1. 把 `dayu/fins/ingestion_runtime.py::_direct_upload_terminal_events` 纳入 S3，允许其把 `FinsUploadResultSummary.warnings` 机械复制给 direct result builder。
2. 把 `dayu/fins/ingestion_runtime.py::_direct_result_event` 的必要 typed warning 参数与 `FinsResultSummary` 构造投影纳入 S3。
3. non-upload callsites 应显式传 `warnings=()`，还是由 helper 提供 `warnings=()` 默认值，属于 public construction strictness 与漏传风险的取舍，必须由 plan review 裁决；implementation 不先行决定。
4. 对应测试仍严格限制在 accepted S3 现有 allowed test files，不新增或修改 `tests/service/test_fins_direct.py`、`tests/fins/test_fins_ingestion_tools.py` 等越界文件。
5. 冻结的 `FinsUploadPipelineResult` parser、warning codec、四个 `SourceKind` callsite、Host/Engine/material/oracle/scenario/frozen evidence 均不纳入 amendment。

## 工作树与下一入口

- 当前工作树应保持零 implementation diff；唯一允许的未跟踪变更是本 blocker artifact。
- 未运行 focused/combined tests、coverage、pyright 或完整 validation，因为 S3 在任何实现修改前已按 stop condition 暂停。
- 下一入口：plan amendment 与 plan review 明确接受上述 direct typed copy symbols 及 non-upload callsite 参数策略后，才可重新进入 S3 implementation。
