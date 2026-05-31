# Code Review

## Scope

- Mode: current changes (Slice 2 only)
- Branch: `fix/wu-runtime-02-lane-clock-cancellation`
- Base: `main`
- Output file: `docs/reviews/wu-runtime-02-code-review-slice2-ds-20260601.md`
- Included scope:
  - `dayu/runtime/lane.py` — Slice 2 unstaged diff: bounded outer-cancellation cleanup timeout, observer callbacks, private `_OuterCancellationCleanupTimeoutError`
  - `tests/runtime/test_lane.py` — Slice 2 unstaged diff: new cleanup timeout tests, TTL tests (Slice 1), updated repeated-cancel test
  - `tests/README.md` — lane 测试覆盖描述同步
  - Implementation artifact: `docs/reviews/wu-runtime-02-implementation-slice2-codex-20260601.md`
- Excluded scope:
  - `docs/host/host-core-followup-implementation-control.md` — controller bookkeeping, not in review scope
  - `docs/host/design.md` — Slice 1 artifact, not in review scope
  - Slice 1 committed changes (`_LaneClock` UTC, TTL tests)
  - `tests/runtime/test_lane_multiprocess.py` — not modified by Slice 2
- Parallel review coverage: 无（单人 review，scope 集中在单文件模块级私有变更）

## Findings

### 001-未修复-低-observer 只捕获 RuntimeLaneError，非预期异常类型会导致 done callback 未处理异常

- **入口/函数**: `_consume_abandoned_claim_task`, `_consume_abandoned_release_task`, `_consume_abandoned_refresh_task`
- **文件(行号)**: `dayu/runtime/lane.py:1215-1241`, `1270-1298`, `1322-1349`
- **输入场景**: 被放弃等待的 claim / release / refresh task 因非 `RuntimeLaneError` 异常失败（例如 `sqlite3.Error` 未被正确包装、或未来新增代码路径引入的其它 `Exception` 子类）。
- **实际分支**: `task.cancelled()` 为 False（任务未被取消），进入 `try: claim = task.result()`，异常类型不匹配 `except RuntimeLaneError`，异常从 done callback 逃逸。
- **预期行为**: done callback 不应抛异常；应消费所有异常类型并记录诊断日志，防止 `Task exception was never retrieved` 或 asyncio unhandled callback 警告。
- **实际行为**: 若 `task.result()` 抛出非 `RuntimeLaneError` 的异常（如裸 `Exception`、`BaseException` 子类），异常不被 catch，导致 unhandled exception in callback，且该 late failure 不会出现在 lane 诊断日志中。
- **直接证据**:
  - `_consume_abandoned_claim_task` (line 1230): `except RuntimeLaneError` 只捕获 RuntimeLaneError
  - `_consume_abandoned_release_task` (line 1289-1290): `except RuntimeLaneError` 只捕获 RuntimeLaneError
  - `_consume_abandoned_refresh_task` (line 1339-1340): `except RuntimeLaneError as exc` 只捕获 RuntimeLaneError
  - 当前所有同步函数（`_try_claim_once_sync`、`_release_claim_sync`、`_refresh_token_sync`）将 `sqlite3.Error` 包装为 `RuntimeLaneError`（line 698、796、938），因此在当前实现下此异常类型不会命中该 gap。但 observer 作为防御性收口没有理由只信任调用链的异常包装约定。
- **影响**: 当前生产代码不触发；但若未来修改同步函数引入新异常类型，或在 `to_thread` 框架层面抛出新异常（如 Python 版本升级引入的运行时异常），late failure 将在静默中丢失诊断日志，仅留下 asyncio 的未处理异常警告。
- **建议改法和验证点**:
  - 在每个 `_consume_abandoned_*_task` 中将 `except RuntimeLaneError` 改为 `except BaseException`，但仍保持 `task.cancelled()` 在前以排除 CancelledError。
  - 或在 `except RuntimeLaneError` 之后增加 fallback `except BaseException as exc` 并记录 generic late failure 诊断。
  - 验证：构造一个 task 以非 RuntimeLaneError 异常失败，注册 observer，等待 done callback 触发，断言日志包含该异常信息且无 unhandled exception 警告。
- **修复风险（低）**: 改动仅影响 done callback 日志消费路径，不改变任何状态机行为或 public API。
- **严重程度（低）**: 当前无法触发，属于防御性缺口；但作为 runtime infrastructure 的收口路径，容忍度应更低。

### 002-未修复-低-_release_untracked_claim 内 cancel 路径异常链丢失

- **入口/函数**: `LaneController._release_untracked_claim`
- **文件(行号)**: `dayu/runtime/lane.py:924-929`
- **输入场景**: untracked claim 的 release task 在取消后以 `RuntimeLaneError` 失败。
- **实际分支**: 进入 `except asyncio.CancelledError as cancelled` 内的 `except RuntimeLaneError`（line 924），执行 `_LOGGER.exception(...)` 和 `raise cancelled`。
- **预期行为**: 应与同文件中 `_try_claim_once`（line 628）和 `_refresh_token`（line 750）一致，使用 `raise cancelled from exc` 将 RuntimeLaneError 链接到 CancelledError 的 `__cause__`。
- **实际行为**: `raise cancelled`（无 `from exc`）仍然对外抛出 CancelledError，语义正确；但 `__cause__` 未设置，异常链中看不到 RuntimeLaneError 的原因信息。`_LOGGER.exception` 已在日志中保留完整 traceback，信息未丢失。
- **直接证据**: 对比 line 628 `raise cancelled from exc` 与 line 929 `raise cancelled`。同文件中 `_release_token`（line 849）也存在相同的不带 `from exc` 模式。
- **影响**: 纯调试/诊断体验差异；不影响运行时行为或状态正确性。
- **建议改法和验证点**: 将 line 929 和 line 849 的 `raise cancelled` 改为 `raise cancelled from exc`，与 line 628/750 一致。验证：对应测试中 `exc_info.value.__cause__` 不再是 None。
- **修复风险（低）**: 仅增加异常链，不改变异常类型或控制流。
- **严重程度（低）**: 不影响 correctness，属于 internal consistency 维护性问题。

### 003-未修复-低-_consume_abandoned_claim_task 中 claim.acquired=False 且 task 有结果的静默消费

- **入口/函数**: `_consume_abandoned_claim_task`
- **文件(行号)**: `dayu/runtime/lane.py:1236-1241`
- **输入场景**: 被放弃的 claim task 完成且 `claim.acquired is False`（capacity 满）。
- **实际分支**: `claim.acquired and claim.claim_id is not None` 为 False，函数直接 return，不记录任何日志。
- **预期行为**: 当 claim 未获取时仍然可以记录 debug/info 级别日志确认 observer 已消费该 late result（可选改进）。
- **实际行为**: 静默 return。不影响正确性（capacity 满时不占用额外资源），但减少了 cleanup 路径的可观测性。
- **直接证据**: line 1237-1241，只有 `claim.acquired` 分支有日志，非 acquired 路径无任何记录。
- **影响**: 极低。late claim fail（non-acquired）是正常竞争结果，不需要 TTL fallback 警告；但从运维角度，完全静默不利于确认 observer 确实消费了 late task。
- **建议改法和验证点**: 可选：增加 `_LOGGER.debug(...)` 记录 `lane_name` + "abandoned claim task did not acquire (capacity full)"。
- **修复风险（低）**: 仅新增一条 debug 级别日志。
- **严重程度（低）**: 可观测性轻微不足，不影响正确性。

## Open Questions

1. **重复 cancel 导致 `_await_task_after_outer_cancellation` 内 `asyncio.sleep` 被取消的路径未覆盖测试。** 当前测试 `test_await_task_after_outer_cancellation_yields_before_retry` 只覆盖了外层 CancelledError 被 catch 后调用 sleep yield 的正常路径（sleep 未被再次 cancel）。嵌套 cancel 路径（line 1170-1173：sleep 被 cancel 且 task.done() 为 True 时返回 task.result()）缺少显式测试。由于内层 sleep 时长只有 `_OUTER_CANCELLATION_SETTLE_SLEEP_SECONDS` (0.01s)，触发此路径需要精确的二次 cancel 时间，属低概率但 behavior contract 应覆盖。

2. **`_observe_abandoned_refresh_task` observer 的 late success/lost 行为缺少独立测试。** 现有测试覆盖了 claim 路径（`test_cancel_during_claim_cleanup_timeout...`）和 tracked release 路径（`test_release_token_cleanup_timeout...`），但缺少 refresh cleanup timeout 后 observer 消费 late refresh 结果的独立测试。当前依赖 `test_refresh_cancel_cleanup_*` 覆盖的是 cleanup 成功完成（不进入 observer）的路径。

## Residual Risk

- **observer 闭包引用泄漏**：检查确认所有 observer lambda 只捕获 primitive 值（`lane_name`、`claim_id`、`operation`）或非循环引用的函数（`_consume_abandoned_*`），不捕获 `task`、`token`、`controller` 等对象，不会形成闭包引用泄漏。**风险：无。**

- **late successful tracked release 后 token.released 不更新**：按 approved plan 设计，tracked release cleanup timeout 后即使底层 release 成功，observer 也不更新 `token.released`。测试 `test_release_token_cleanup_timeout_preserves_held_token_for_retry` 已验证：late DB release 成功后 `token.released` 保持 `False`，后续 retry `token.release()` 可幂等成功。**风险：已接受（plan-approved behavior），通过 TTL stale cleanup 兜底。**

- **cleanup timeout 后底层线程仍在运行**：plan 明确选择不强制 kill 线程。测试 `test_await_task_after_outer_cancellation_times_out_without_cancelling_task` 已验证 timeout 后底层 task 未被 cancel。所有测试在释放阻塞 Event 后均验证了资源清理。**风险：已接受（plan-approved behavior）。**

- **`_release_untracked_claim` 在 cancel 路径中的 CancelledError 传播链**：若 `_release_untracked_claim` 的 release task 本身在取消后以 cleanup timeout 结束，其内部 `raise cancelled from exc` 产生一个新的 CancelledError（非最初 `_try_claim_once` 中捕获的 `cancelled_1`）。此新 CancelledError 穿透 `_try_claim_once` 的 `except RuntimeLaneError` handler 向上传播。由于两个 CancelledError 在 Python 3.11+ 中语义等价（均为取消信号），且诊断信息在日志中保留，不影响 caller 行为。**风险：低。**

- **pyright / import boundary / `__all__` 检查**：pyright 通过（0 errors, 0 warnings, 0 informations）。无新增 `dayu.engine/host/service/ui/fins` 导入。`__all__` 未变更，私有 `_OuterCancellationCleanupTimeoutError` 未加入 public API。**风险：无。**

## Conclusion: PASS

未发现 blocking 或高危 severity 的 finding。3 个低严重度 finding（observer 防御性捕获 gap、异常链 inconsistency、capacity full 静默消费）均不阻塞 merge。建议在后续 slice 或独立 cleanup 中处理 001 和 002。

核心行为验证通过：
- `_await_task_after_outer_cancellation` 有界等待，timeout 后不 cancel 底层 task
- 所有 call site（`_try_claim_once`、`_refresh_token`、`_release_token`、`_release_untracked_claim`）timeout 后对外抛 `CancelledError`，且 `from _OuterCancellationCleanupTimeoutError`
- tracked release timeout 不标记 `token.released`，保留 retry 能力
- observer 正确注册并消费 late result/exception（`RuntimeLaneError` 范围内）
- 测试覆盖 helper timeout、public claim cleanup timeout、tracked release cleanup timeout + retry，使用 `threading.Event` 同步不依赖 random sleep，所有阻塞线程在测试结束前释放
