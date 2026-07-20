# WU-SEMANTIC-OWNERSHIP-01 P3-E S3 Implementation - AgentCodex

## 状态

ready-for-controller-validation

## First-principles / owner boundary

S3 的问题成立：Fins direct stream 的 `RESULT` 是 direct stream 协议事实，不是财报业务事实。缺失 `RESULT` 或重复 `RESULT` 说明 stream producer / wrapper 违反了 terminal contract；如果 runtime、Service 或 CLI 合成一个 `failure RESULT`，就会把协议错误伪装成业务失败，污染用户可见终态和调用方的退出语义。

owner boundary：

- `dayu.fins.direct_events` 拥有跨 Fins runtime / Service / CLI 共享的 direct stream typed event 与 protocol error contract。
- `FinsIngestionRuntime._run_direct_stream(...)` 是 producer queue 到 `AsyncIterator[FinsEvent]` 的 runtime owner，负责唯一 terminal `RESULT` 协议校验。
- `dayu.service.fins_direct._ensure_result_event(...)` 是 Service direct helper 的 upstream typed stream guard，负责在 runtime 被 mock 或其它 runtime 违反 contract 时继续 fail closed。
- CLI 只负责 product command exit / rendering；它不能定义第二套 protocol exception，也不能为同一 protocol fact 伪造 business `RESULT`。

## `_DirectStreamProducerDone` lifecycle audit

源代码证据基于当前实现行号：

- sentinel 类型与 queue item：
  - `dayu/fins/ingestion_runtime.py:1297-1301` 定义 `_DirectStreamProducerDone` 和 `_DirectStreamQueueItem`。

- normal producer completion puts exactly one sentinel：
  - `_run_direct_stream_producer(...)` 只在 wrapper `finally` 中投递 sentinel：`dayu/fins/ingestion_runtime.py:2750-2762`。
  - 业务 producer 本身不直接投递 `_DirectStreamProducerDone`；runtime wrapper 是唯一正常 sentinel 写入点。

- producer exception paths put sentinel after surfacing exception through queue/runtime error path：
  - producer exception 被 wrapper 捕获并通过 `_emit_direct_result(... status=FAILURE ...)` 转成业务 failure RESULT：`dayu/fins/ingestion_runtime.py:2750-2760`。
  - 同一 wrapper 的 `finally` 随后投递 `_DirectStreamProducerDone`：`dayu/fins/ingestion_runtime.py:2761-2762`。
  - 这保持业务执行异常仍是业务 failure RESULT；S3 只把 missing / duplicate terminal protocol violation 改为 typed protocol error。

- terminal `RESULT` producer paths promptly reach sentinel：
  - download producer 在 cancel / provider failure / success 分支分别 emit RESULT 后 return 或函数结束：`dayu/fins/ingestion_runtime.py:2798-2822`。
  - preprocess producer 在 cancel / failed summary / success 分支 emit RESULT 后 return 或函数结束：`dayu/fins/ingestion_runtime.py:2856-2880`。
  - upload producer 在 cancel / unsupported runtime / failed upload / success 分支 emit RESULT 后 return 或函数结束：`dayu/fins/ingestion_runtime.py:2910-2966`。
  - 这些路径均回到 wrapper `finally` 投递 sentinel。

- no producer relies on current early break after first `RESULT` for cleanup：
  - direct cleanup 不在 producer 的 RESULT 之后执行，而在 wrapper `finally` 的 sentinel 投递和 consumer `finally` 的 cancellation state 更新中执行：`dayu/fins/ingestion_runtime.py:2729-2730` 与 `dayu/fins/ingestion_runtime.py:2761-2762`。
  - 新 consumer loop 不再 early break；它缓存首个 RESULT，继续 drain 到 sentinel：`dayu/fins/ingestion_runtime.py:2701-2728`。

- queue fallback sentinel：
  - `_direct_queue_get(...)` 在 thread 已退出且 queue empty 时返回 `_DirectStreamProducerDone()`：`dayu/fins/ingestion_runtime.py:4538-4543`。这是防止 producer 线程异常退出但 sentinel 未入队时 consumer 永久等待的 fallback。

结论：drain-until-sentinel 不依赖 downstream timeout；normal / business-failure producer 都会到达 sentinel。新增 no-hang 测试覆盖正常 producer 的 progress + RESULT 路径。

## Implementation summary

生产代码：

- `dayu/fins/direct_events.py`
  - 新增 `FinsDirectStreamProtocolErrorKind(str, Enum)`：`MISSING_RESULT`、`DUPLICATE_RESULT`。
  - 新增 `FinsDirectStreamProtocolError(ValueError)`，包含 typed attributes：`reason`、`operation_kind`、`message`，并校验 enum 类型与非空 message。
  - 更新 `__all__`。

- `dayu/fins/ingestion_runtime.py`
  - `_run_direct_stream(...)` 缓存首个 `RESULT`，继续读取直到 `_DirectStreamProducerDone`。
  - 重复 `RESULT` 抛 `FinsDirectStreamProtocolError(DUPLICATE_RESULT, ...)`。
  - sentinel 后缺失 `RESULT` 抛 `FinsDirectStreamProtocolError(MISSING_RESULT, ...)`。
  - sentinel 后只 yield 一个 buffered `RESULT`。
  - 删除 `_direct_missing_result_event(...)`。

- `dayu/service/fins_direct.py`
  - `_ensure_result_event(...)` 同样缓存首个 `RESULT` 并 drain runtime stream。
  - duplicate / missing `RESULT` 抛 shared `FinsDirectStreamProtocolError`。
  - 删除 `_missing_result_event(...)`。
  - `FinsDirectUsageError` 保留为 Service 参数 misuse。

- `dayu/cli/commands/fins.py`
  - 删除 `FinsDirectStreamContractViolation`。
  - CLI catch / render `FinsDirectStreamProtocolError`，返回 command failure。
  - CLI local no-result fallback 也构造 shared `FinsDirectStreamProtocolError(MISSING_RESULT, operation_kind, ...)`。
  - 新增 command name 到 `FinsOperationKind` 的显式映射，避免 no-event stream 时猜测 operation kind。

测试：

- `tests/fins/test_fins_ingestion_runtime.py`
  - missing RESULT 改为 expected typed `MISSING_RESULT`。
  - 新增 duplicate RESULT producer test，断言 `DUPLICATE_RESULT`。
  - 新增 normal drain-until-sentinel no-hang 测试。

- `tests/service/test_fins_direct.py`
  - missing / duplicate RESULT 改为 typed protocol error。
  - business failure RESULT pass-through 测试保持不变。

- `tests/cli/test_fins_commands.py`
  - CLI no-result contract violation 改为 typed protocol error。
  - 新增 Service typed protocol error 透传到 CLI failure 且不伪造 business result 的测试。

README：

- `dayu/fins/README.md`：direct stream stale text 更新为 missing / duplicate `RESULT` 抛 typed protocol error。
- `dayu/service/README.md`：`fins_direct` stale synthetic missing result text 更新为 typed protocol error。
- `tests/README.md`：同步 Fins direct / ingestion runtime 覆盖摘要。

## Validation commands/results

```bash
source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_runtime.py tests/service/test_fins_direct.py tests/cli/test_fins_commands.py -q
```

结果：`124 passed, 3 warnings in 3.21s`

warnings：来自 `edgar` package 的 deprecation warning，非本次变更引入。

```bash
rg -n "_DirectStreamProducerDone|FinsDirectStreamContractViolation|FinsDirectStreamProtocolError|_direct_missing_result_event|_missing_result_event" dayu/fins dayu/service dayu/cli tests/fins tests/service tests/cli
```

结果分类：

- `_DirectStreamProducerDone`：仅在 `dayu/fins/ingestion_runtime.py` sentinel type、queue item、consumer drain、producer finally 和 `_direct_queue_get(...)` fallback 中出现，均为预期。
- `FinsDirectStreamProtocolError` / `FinsDirectStreamProtocolErrorKind`：出现在 shared contract、runtime、Service、CLI catch/render、README 和 tests，均为预期 typed contract use。
- `FinsDirectStreamContractViolation`：无匹配。
- `_direct_missing_result_event`：无匹配。
- `_missing_result_event`：无匹配。

```bash
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
```

结果：`0 errors, 0 warnings, 0 informations`

备注：pyright 提示存在新版本 `v1.1.409 -> v1.1.411`，不影响当前检查结果。

```bash
git diff --check
```

结果：通过，无输出。

## Coverage result

```bash
source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_runtime.py tests/service/test_fins_direct.py tests/cli/test_fins_commands.py --cov=dayu.fins.direct_events --cov=dayu.fins.ingestion_runtime --cov=dayu.service.fins_direct --cov-report=term-missing -q
```

结果：`124 passed, 3 warnings in 4.03s`

- `dayu/fins/direct_events.py`: 92%
- `dayu/fins/ingestion_runtime.py`: 90%
- `dayu/service/fins_direct.py`: 92%
- total: 90%

## README decision

- `dayu/fins/README.md`：已更新。该 README 的职责包含 `dayu.fins` package direct stream contract，旧文本明确说 missing result 会收口为 failure result，已 stale。
- `dayu/service/README.md`：已更新。该 README 虽不在 AGENTS 触发列表中，但 plan 指定且当前文本明确描述 `fins_direct` synthetic missing result，属于 Service developer contract。
- `tests/README.md`：已更新。测试覆盖摘要从 synthetic failure result 改为 typed protocol error，属于该 README 记录测试分层与覆盖范围的职责。
- 根 `README.md` / `dayu/README.md`：未更新。未命中最终用户工作流或总览架构边界变化；source scan 未发现 stale missing-result 文本。

## Propagation audit

- 产生：Fins direct producer 通过 `_emit_direct_result(...)` 产出业务 terminal RESULT；producer wrapper 通过 `_DirectStreamProducerDone` 标记 stream producer 完成。
- 校验：`FinsIngestionRuntime._run_direct_stream(...)` 是 first owner，校验 missing / duplicate RESULT 并抛 shared typed protocol error；`dayu.service.fins_direct._ensure_result_event(...)` 是 Service direct boundary guard，继续对 runtime stream fail closed。
- 投影 / 退出：CLI catch shared `FinsDirectStreamProtocolError` 并渲染 command failure，不再引入 CLI-local second exception，也不伪造 business `RESULT`。
- 业务 failure：真实 download / preprocess / upload 业务失败仍由 producer 产出 `FinsEventType.RESULT` + `FinsResultStatus.FAILURE`，Service 与 CLI pass through。
- 文档 / 测试：README 和 tests 摘要同步到 typed protocol error，避免文档或测试继续暗示 synthetic business failure。

## Source scan classification

`rg` 输出中剩余匹配均为 expected：

- `dayu/fins/direct_events.py`：typed error contract 和 `__all__`。
- `dayu/fins/ingestion_runtime.py`：sentinel lifecycle、runtime duplicate/missing protocol error。
- `dayu/service/fins_direct.py`：Service boundary duplicate/missing protocol error。
- `dayu/cli/commands/fins.py`：CLI catch/render 与 local no-result fallback 的 shared protocol error。
- `tests/fins` / `tests/service` / `tests/cli`：missing / duplicate protocol error assertions。
- `dayu/fins/README.md` / `dayu/service/README.md`：developer contract text。

No stale matches：

- `FinsDirectStreamContractViolation`
- `_direct_missing_result_event`
- `_missing_result_event`

## Residual risk

- Runtime duplicate detection now delays yielding terminal RESULT until sentinel. Target tests and no-hang test pass, and lifecycle audit shows current producers reach sentinel promptly. If future producers emit RESULT and then perform long blocking work before returning, this contract will surface that lifecycle bug instead of hiding it downstream.
- Producer execution exceptions continue to be represented as business failure RESULT. This is existing Fins business-error behavior and intentionally separate from stream protocol violation.

