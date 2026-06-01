# Code Review

## Scope

- **Mode**: current changes
- **Branch**: `fix/wu-runtime-02-lane-clock-cancellation`
- **Base**: `main`
- **Output file**: `docs/reviews/wu-runtime-02-code-review-slice2-mimo-20260601.md`
- **Included scope**: Slice 2 diff (`dayu/runtime/lane.py`, `tests/runtime/test_lane.py`, `tests/README.md`, implementation artifact `docs/reviews/wu-runtime-02-implementation-slice2-codex-20260601.md`)
- **Excluded scope**: `docs/host/host-core-followup-implementation-control.md` dirty bookkeeping (controller state)
- **Parallel review coverage**: 无

## Findings

### 001-未修复-低-observer 只捕获 RuntimeLaneError，其它异常在 done callback 中被静默吞没

- **入口/函数**: `_consume_abandoned_claim_task`、`_consume_abandoned_release_task`、`_consume_abandoned_refresh_task`
- **文件(行号)**: `dayu/runtime/lane.py`（1215-1241, 1270-1298, 1322-1349）
- **输入场景**: 被放弃等待的底层 task 抛出 `RuntimeLaneError` 以外的异常（如 `Exception` 子类）
- **实际分支**: `task.result()` 抛出非 `RuntimeLaneError` 异常 → 不被 `except RuntimeLaneError` 捕获 → 异常在 done callback 上下文中传播
- **预期行为**: observer 应消费所有 `task.result()` 可能抛出的异常，确保诊断日志不遗漏
- **实际行为**: 只捕获 `RuntimeLaneError`；其它异常落入 asyncio done callback 的默认异常处理（打印到 stderr 但不记录到 `_LOGGER`），导致诊断信息丢失
- **直接证据**: 三个 `_consume_abandoned_*_task` 函数的 `except` 分支均只写 `except RuntimeLaneError`
- **影响**: 当前 sync 函数只抛 `RuntimeLaneError` 及其子类，实际触发概率极低；但若未来 sync 函数引入其它异常类型，observer 将静默失效，诊断日志丢失，无法判断 abandoned task 的最终状态
- **建议改法和验证点**: 将 `except RuntimeLaneError` 改为 `except Exception`（或 `except BaseException` 若需覆盖 `KeyboardInterrupt` 等），保持日志级别和 extra 信息不变。验证：构造 sync 函数抛出非 `RuntimeLaneError` 异常的测试，确认 observer 日志记录了该异常
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

- 无

## Residual Risk

- Cleanup timeout 刻意不杀死底层 Python thread；abandoned untracked claim 的容量回收依赖现有 TTL stale cleanup。这是 approved plan 的设计决策，不是遗漏。
- Late successful tracked release 被 observer 消费但不修改 `LaneClaimToken.released`；token 保持可重试状态，符合 plan 要求。
- 未新增 DB schema 或 public API 迁移覆盖，因本 slice 仅做私有 runtime 控制流变更。

## Conclusion: PASS

未发现 blocking finding。实现正确覆盖了 plan 要求的有界等待、repeated cancel 不吞取消、timeout 后不取消底层 task、对外保持 `CancelledError` 语义、token 状态保留、observer 消费 late result/exception。测试覆盖了 helper timeout、public claim cleanup timeout、tracked release cleanup timeout，不依赖随机 sleep，不留下 pending task/thread。`__all__`、runtime import boundary、pyright 均无变化。
