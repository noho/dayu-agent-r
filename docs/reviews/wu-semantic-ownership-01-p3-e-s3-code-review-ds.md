# WU-SEMANTIC-OWNERSHIP-01 P3-E S3 Code Review — AgentDS

## Scope

- Mode: current changes (uncommitted workspace diff vs HEAD)
- Branch: `phaseflow/host-issues-control`
- Base: `HEAD` (uncommitted staged changes)
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-e-s3-code-review-ds.md`
- Reviewed artifacts:
  - Plan: `docs/host/wu-semantic-ownership-01-p3-e-tool-result-wait-fins-contracts-plan.md` S3 section
  - Implementation: `docs/reviews/wu-semantic-ownership-01-p3-e-s3-implementation-codex.md`
  - Controller validation: `docs/reviews/wu-semantic-ownership-01-p3-e-s3-controller-validation.md`
- Included files (11 total):
  - `dayu/fins/direct_events.py` — new typed protocol error contract
  - `dayu/fins/ingestion_runtime.py` — runtime drain-until-sentinel protocol enforcement
  - `dayu/service/fins_direct.py` — Service boundary protocol enforcement
  - `dayu/cli/commands/fins.py` — CLI catch/render + `FinsDirectStreamContractViolation` 删除
  - `tests/fins/test_fins_ingestion_runtime.py` — missing/duplicate/no-hang tests
  - `tests/service/test_fins_direct.py` — missing/duplicate protocol error tests
  - `tests/cli/test_fins_commands.py` — CLI protocol error tests
  - `dayu/fins/README.md` — stale text → typed protocol error
  - `dayu/service/README.md` — stale text → typed protocol error
  - `tests/README.md` — coverage summary sync
  - `docs/host/issues-implementation-control.md` — gate bookkeeping only
- Excluded:
  - `docs/cli_ci*`, `docs/reviews/code-review-20260710-*` (unrelated untracked)
  - Already-committed S1/S2 (not regressed by S3 diff)
- Parallel review coverage: 无（单 reviewer 逐路走读）

## Findings

未发现实质性问题。

---

## 1. `FinsDirectStreamProtocolError` contract quality and exports

**验证路径**:

- `dayu/fins/direct_events.py:81-85`: `FinsDirectStreamProtocolErrorKind(str, Enum)` 定义 `MISSING_RESULT = "missing_result"` 与 `DUPLICATE_RESULT = "duplicate_result"` ✅
- `dayu/fins/direct_events.py:88-133`: `FinsDirectStreamProtocolError(ValueError)` 携带 typed attributes `reason`（`FinsDirectStreamProtocolErrorKind`）、`operation_kind`（`FinsOperationKind`）、`message`（`str`）✅
- 构造函数行 122-132:
  - 校验 `isinstance(reason, FinsDirectStreamProtocolErrorKind)`（行 122-125）✅
  - 校验 `isinstance(operation_kind, FinsOperationKind)`（行 126-127）✅
  - 校验 `not message.strip()` → 拒绝空/空白 message（行 128-129）✅
  - 调用 `super().__init__(message)` 保持 `ValueError` 兼容性（行 133）✅
- `__all__` 导出 `FinsDirectStreamProtocolError` 与 `FinsDirectStreamProtocolErrorKind`（行 485-486）✅
- 该 contract 被 runtime（`dayu/fins/ingestion_runtime.py:36-37`）、Service（`dayu/service/fins_direct.py:24-25`）、CLI（`dayu/cli/commands/fins.py:46-47`）统一 import ✅

**结论**: 通过。Typed protocol error contract 完整、类型安全、三 owner 共享同一真源。

---

## 2. Runtime drain-until-sentinel behavior

**验证路径**:

- `dayu/fins/ingestion_runtime.py:2701-2728`: `_run_direct_stream` consumer loop
  - `result_event: FinsEvent | None = None` 缓冲首个 RESULT（行 2701）✅
  - 遇到 `_DirectStreamProducerDone` → `break` 退出 loop（行 2710-2711）✅
  - RESULT 已存在时再遇 RESULT → `raise FinsDirectStreamProtocolError(DUPLICATE_RESULT, ...)`（行 2712-2719）✅
  - 非 RESULT 事件 `yield` 正常投递（行 2721）✅
  - sentinel 后 `result_event is None` → `raise FinsDirectStreamProtocolError(MISSING_RESULT, ...)`（行 2722-2727）✅
  - sentinel 后 `yield result_event` 投递唯一的缓冲 RESULT（行 2728）✅
- `_direct_missing_result_event(...)` **已删除**: 全量 source scan 零命中 ✅
- Lifecycle audit (implementation artifact 已记录完整源代码行引用):
  - Normal producer `finally` 投递 sentinel（`dayu/fins/ingestion_runtime.py:2761-2762`）✅
  - Producer exception 仍生成业务 failure RESULT + `finally` sentinel（`dayu/fins/ingestion_runtime.py:2750-2762`）✅
  - `_direct_queue_get` fallback sentinel（`dayu/fins/ingestion_runtime.py:4538-4543`）防止 producer 线程异常退出时 consumer 永久等待 ✅

**直接证据**:
- `dayu/fins/ingestion_runtime.py:2701-2728`: 完整 drain-until-sentinel consumer loop ✅
- `dayu/fins/ingestion_runtime.py:2714-2718`: duplicate RESULT → typed protocol error ✅
- `dayu/fins/ingestion_runtime.py:2722-2727`: missing RESULT → typed protocol error ✅
- Source scan: `_direct_missing_result_event` production 零命中 ✅

**结论**: 通过。不再静默吞 duplicate RESULT；不再合成 business failure 为 missing RESULT；no-hang 测试覆盖正常 drain-until-sentinel 路径。

---

## 3. Service `_ensure_result_event` boundary

**验证路径**:

- `dayu/service/fins_direct.py:475-511`: `_ensure_result_event`
  - `result_event: FinsEvent | None = None` 缓冲首个 RESULT（行 495）✅
  - RESULT 已存在时再遇 RESULT → `raise FinsDirectStreamProtocolError(DUPLICATE_RESULT, operation_kind, ...)`（行 499-503）✅
  - 旧 `FinsDirectUsageError` 不再用于 stream protocol violation ✅
  - 非 RESULT 事件 `yield` 正常投递（行 504）✅
  - stream 结束后 `result_event is None` → `raise FinsDirectStreamProtocolError(MISSING_RESULT, operation_kind, ...)`（行 507-512）✅
  - stream 结束后 `yield result_event`（行 513）✅
- `_missing_result_event(...)` **已删除**: 全量 source scan 零命中 ✅
- Service 方法（`download`、`preprocess`、`upload` 等）均传入正确的 `operation_kind` ✅

**结论**: 通过。Service boundary 与 runtime 使用同一 shared typed protocol error；不再合成业务 failure result 掩盖协议错误。

---

## 4. CLI boundary

**验证路径**:

- `FinsDirectStreamContractViolation` **已删除**: 全量 source scan 零命中 ✅
- `dayu/cli/commands/fins.py:286-288`: `run_fins_direct_command` 新增 `except FinsDirectStreamProtocolError` 分支，render `exc.message` 并返回 `EXIT_FAILURE` ✅
- `dayu/cli/commands/fins.py:487-505`: `_direct_operation_kind(command_name)` 新增显式 CLI command → `FinsOperationKind` 映射:
  - `download` → `DOWNLOAD`（行 499-500）✅
  - `upload_filing` → `UPLOAD_FILING`（行 501-502）✅
  - `upload_material` → `UPLOAD_MATERIAL`（行 503-504）✅
  - `process` → `PREPROCESS`（行 505-506）✅
  - `process_filing` → `PROCESS_FILING`（行 507-508）✅
  - `process_material` → `PROCESS_MATERIAL`（行 509-510）✅
- `operation_kind` 传播链: `_run_fins_direct_command_async` → `_wait_for_terminal_handling_sigint(operation_kind=...)` → `_consume_fins_direct_events(events, operation_kind=...)` ✅
- `dayu/cli/commands/fins.py:767-773`: `_consume_fins_direct_events` 无 RESULT 时抛 `FinsDirectStreamProtocolError(MISSING_RESULT, operation_kind, ...)` 而非旧 CLI-local exception ✅

**结论**: 通过。CLI 不再定义第二套 protocol exception；shared typed protocol error 是 protocol violation 唯一真源；operation kind 映射完整覆盖 6 个 direct 命令。

---

## 5. Business failure RESULT pass-through

**验证路径**:

- Runtime producer exception path: `_run_direct_stream_producer` 行 2750-2760 仍将 producer 异常转为 business `RESULT(status=FAILURE)` 后投递 sentinel（行 2761-2762）✅
- Runtime consumer: `_run_direct_stream` 只对 missing/duplicate terminal 抛 protocol error；合法的 business RESULT（包括 `FAILURE`/`CANCELLED`）正常缓冲并 yield（行 2712-2721）✅
- Service `_ensure_result_event`: 对合法 RESULT（无论 business success/failure/cancelled）正常缓冲并 yield（行 496-504）✅
- CLI `_consume_fins_direct_events`: 对合法 RESULT 直接 `return event.result`（行 761-767diff 前逻辑未变）✅
- 测试: `test_fins/test_fins_ingestion_runtime.py` 中 business failure 测试（如 `test_direct_download_unsupported_source_returns_failure_result`）未修改，确保 pass-through 行为不变 ✅

**结论**: 通过。Business failure RESULT pass-through 完整保留；protocol error 与 business failure 语义边界清晰。

---

## 6. Test coverage

| 测试 | 文件(行号) | 覆盖语义 |
|---|---|---|
| `test_direct_stream_missing_result_raises_protocol_error` | `test_fins_ingestion_runtime.py:1346` | Runtime missing RESULT → `MISSING_RESULT` typed error |
| `test_direct_stream_duplicate_result_raises_protocol_error` | `test_fins_ingestion_runtime.py:1375` | Runtime duplicate RESULT → `DUPLICATE_RESULT` typed error |
| `test_direct_stream_drains_to_done_before_yielding_result` | `test_fins_ingestion_runtime.py:1422` | Runtime normal drain-until-sentinel no-hang + PROGRESS→RESULT 顺序 |
| `test_stream_without_result_raises_protocol_error` | `test_fins_direct.py:501` | Service missing RESULT → `MISSING_RESULT` typed error |
| `test_duplicate_result_fails_fast` | `test_fins_direct.py:513` | Service duplicate RESULT → `DUPLICATE_RESULT` typed error |
| `test_stream_without_result_returns_protocol_error` | `test_fins_commands.py:881` | CLI no-result → typed protocol error (not CLI-local exception) |
| `test_direct_stream_protocol_error_surfaces_without_business_result` | `test_fins_commands.py:905` | CLI: Service raise `DUPLICATE_RESULT` → CLI failure + 无伪造 business text |

**结论**: 通过。missing/duplicate 在三层（runtime/Service/CLI）均有独立测试覆盖；no-hang normal stream 测试覆盖 drain-until-sentinel；business result 伪造否定测试覆盖 CLI 边界。

---

## 7. README updates

| README | 变更 | 是否在职责范围内 |
|---|---|---|
| `dayu/fins/README.md` | "收口为 failure result" → "抛出 `FinsDirectStreamProtocolError`，不得合成业务 failure result" | ✅ 该 README 记录 Fins direct stream contract |
| `dayu/service/README.md` | "合成清晰 failure result" → "抛出 `FinsDirectStreamProtocolError`" | ✅ 该 README 记录 Service developer contract |
| `tests/README.md` | "合成 failure result" → "typed protocol error"；同步 runtime coverage 摘要 | ✅ 该 README 记录测试覆盖范围 |

**结论**: 通过。三个 README 均移除 stale synthetic failure result 文本，替换为 typed protocol error；均在各自声明的职责范围内。

---

## Open Questions

无。

## Residual Risk

1. **Runtime RESULT yielding now deferred until sentinel**: 正常 producer 在 RESULT 后立即 return 进入 wrapper `finally` → sentinel，延迟极小。若未来 producer 在 emit RESULT 后执行长阻塞操作再 return，consumer 会在 sentinel 前被阻塞——此时该 producer lifecycle bug 在 runtime owner 处暴露，而非被下游 timeout hack 掩盖。这是 plan S3 明确要求的行为变更，非退化。

2. **Service `_ensure_result_event` defer RESULT to end of stream**: 对于合法 stream（RESULT 是 terminal 事件），RESULT 在 stream 中的相对位置与 consumer 之间的 PROGRESS 事件数量均不变。对于 malformed stream（RESULT 后有事件），新行为将 RESULT 放到最后再 yield。由于这类 stream 已违反 protocol，且 runtime 为 first owner 已 enforcing 唯一 terminal RESULT，Service 侧此行为差异仅在 mock/fake runtime 的 malformed 测试场景中可观察，无生产影响。

3. **S3 完成但 P3-E aggregate 未闭合**: S3 是 P3-E 最后一个 slice。S1/S2/S3 各自独立 review 通过，但 P3-E aggregate validation（全量 `pytest` + `rg` aggregate scan + final propagation audit）由后续 gate 执行。

## Conclusion

**PASS**

S3 实现正确完成全部目标：

- **Typed protocol error contract**: `FinsDirectStreamProtocolError` + `FinsDirectStreamProtocolErrorKind` 是跨 runtime/Service/CLI 共享的 protocol violation 真源；构造函数校验 enum 类型与非空 message；`__all__` 完整导出。
- **Runtime**: `_run_direct_stream` drain-until-sentinel；duplicate RESULT → `DUPLICATE_RESULT` typed error；missing RESULT → `MISSING_RESULT` typed error；`_direct_missing_result_event` 已删除。
- **Service**: `_ensure_result_event` 使用同一 shared typed protocol error；`_missing_result_event` 已删除；不再合成 business failure 掩盖协议错误。
- **CLI**: `FinsDirectStreamContractViolation` 已删除；catch/render shared typed protocol error；`_direct_operation_kind` 映射 6 个 command 至正确 `FinsOperationKind`。
- **Business failure pass-through**: 完整的 producer exception → business `RESULT(status=FAILURE)` 路径未改变；runtime/Service/CLI 仅对 missing/duplicate terminal 抛 protocol error。
- **Tests**: missing/duplicate/no-hang 覆盖 runtime + Service + CLI 三层；124 passed + pyright 零错误 + coverage ≥ 90%。
- **README**: 三份 README 移除 stale synthetic result 文本。

所有变更均落在语义 owner boundary：`FinsDirectStreamProtocolError` contract owner = `dayu.fins.direct_events`；runtime first owner = `FinsIngestionRuntime._run_direct_stream`；Service guard = `_ensure_result_event`；CLI projection = catch/render shared error。无语义漂移，无下游特例，无伪造 business result。
