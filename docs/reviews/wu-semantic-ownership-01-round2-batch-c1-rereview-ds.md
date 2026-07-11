# Re-Review — WU-SEMANTIC-OWNERSHIP-01 Round 2 Batch C1 Review Fix

## Scope

- Mode: current changes (re-review of review-fix)
- Branch: `phaseflow/host-issues-control`
- Base: `HEAD` (workspace uncommitted changes)
- Output file: `docs/reviews/wu-semantic-ownership-01-round2-batch-c1-rereview-ds.md`
- Reviewing agent: AgentDS
- Reviewed artifacts:
  - `docs/reviews/wu-semantic-ownership-01-round2-batch-c1-code-review-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-round2-batch-c1-code-review-ds.md`
  - `docs/reviews/wu-semantic-ownership-01-round2-batch-c1-code-review-controller-adjudication.md`
  - `docs/reviews/wu-semantic-ownership-01-round2-batch-c1-review-fix-codex.md`
  - `docs/reviews/wu-semantic-ownership-01-round2-batch-c1-review-fix-controller-validation.md`
- Accepted findings re-reviewed: DS-C1-01, C1-REVIEW-01, DS-C1-02, C1-REVIEW-02/DS-C1-03
- Scope boundary: 只审查 C1 review-fix 是否关闭 accepted findings，不修改代码。

## Re-Review Method

对每个 accepted finding，沿实际代码路径逐条验证：
- 定义位置（enum/class/field）
- 使用位置（raise/catch/counter/setter）
- 测试断言是否反映 owner 级 contract
- 确认旧行为已移除且无残留

## Re-Review Evidence

### DS-C1-01: 边界拒绝有显式 durable outcome/counter 且不递增 adapter_errors

**判定：已关闭。**

| 验证点 | 文件(行号) | 证据 |
| --- | --- | --- |
| `WaitPollLastOutcome.BOUNDARY_REJECTED` 枚举值 | `dayu/host/durable/state.py:197` | `BOUNDARY_REJECTED = "boundary_rejected"` |
| schema CHECK 新增 `boundary_rejected` | `dayu/host/durable/schema.py:863` | `'boundary_rejected',` in CHECK IN list |
| `_release_expired_or_invalid_boundary` 使用 BOUNDARY_REJECTED outcome | `dayu/host/wait_adapter.py:1220` | `outcome=WaitPollLastOutcome.BOUNDARY_REJECTED` |
| `poll_once` 新增 `boundary_rejections` 计数器 | `dayu/host/wait_adapter.py:908` | `boundary_rejections = 0` |
| 边界拒绝递增 `boundary_rejections` 而非 `adapter_errors` | `dayu/host/wait_adapter.py:931` | `boundary_rejections += 1`（对比 `:908` adapter_errors 初始化为 0 且未递增） |
| `WaitPollerDiagnosticsSnapshot.boundary_rejections` 字段 | `dayu/host/wait_adapter.py:491` | `boundary_rejections: int` |
| 所有 diagnostics 构造函数传递 `boundary_rejections` | `dayu/host/wait_adapter.py:1773,1797,1829,1858,1894,1924` | 逐行验证通过 |
| 测试：expired wait 断言 `adapter_errors == 0` + `boundary_rejections == 1` | `tests/host/test_wait_adapter_polling.py:1291-1292` | `assert result.adapter_errors == 0` 和 `assert result.boundary_rejections == 1` |
| 测试：invalid wait 断言 `adapter_errors == 0` + `boundary_rejections == 1` | `tests/host/test_wait_adapter_polling.py:1333-1334` | 同上模式 |
| 测试：durable `poll_last_outcome` 为 BOUNDARY_REJECTED | `tests/host/test_wait_adapter_polling.py:1298,1338` | `wait_record.poll_last_outcome is WaitPollLastOutcome.BOUNDARY_REJECTED` |
| durable 序列化测试覆盖 | `tests/host/test_wait_record_state.py:421-426` | serialize/deserialize roundtrip for BOUNDARY_REJECTED |

### C1-REVIEW-01: 不可达 STALE_CALLBACK 公共状态及 Service 映射已移除

**判定：已关闭。**

| 验证点 | 文件(行号) | 证据 |
| --- | --- | --- |
| `STALE_CALLBACK` 不再在 `WaitCallbackAdapterStatus` 枚举中 | `dayu/host/wait_callback.py:35-52` | 枚举成员列表无 `STALE_CALLBACK` |
| Service HTTP 映射不再引用 `STALE_CALLBACK` | `dayu/service/wait_callback_endpoint.py:748-752` | 410 仅映射 `LATE_WAIT_CANCELLED` 和 `LATE_WAIT_LOST` |
| 全仓 Python 代码零 `STALE_CALLBACK` / `stale_callback` 引用 | `grep -rn "STALE_CALLBACK\|stale_callback" --include="*.py"` | 空输出（仅 design docs 和 review artifacts 的 `.md` 中仍有历史引用，属于正常文档留存） |
| Service 测试无 STALE_CALLBACK 用例 | `tests/service/test_wait_callback_endpoint.py` | grep 确认零引用 |

### DS-C1-02: self-close 使用 typed internal exception，非 RuntimeError message matching

**判定：已关闭。**

| 验证点 | 文件(行号) | 证据 |
| --- | --- | --- |
| `_WaitPollerSelfCloseError(RuntimeError)` 类型定义 | `dayu/host/wait_adapter.py:87-88` | `class _WaitPollerSelfCloseError(RuntimeError):` |
| 消息常量重命名为 `_WAIT_POLLER_SELF_CLOSE_MESSAGE`（语义更精确） | `dayu/host/wait_adapter.py:82-84` | `_WAIT_POLLER_SELF_CLOSE_MESSAGE = "wait poller supervisor cannot close from its own thread"` |
| `close()` raise typed exception | `dayu/host/wait_adapter.py:1468` | `raise _WaitPollerSelfCloseError(_WAIT_POLLER_SELF_CLOSE_MESSAGE)` |
| `_run_loop` typed except 分支 | `dayu/host/wait_adapter.py:1538` | `except _WaitPollerSelfCloseError as exc:` |
| 测试断言 typed exception type | `tests/host/test_wait_poller_runtime.py:908` | `diagnostics.last_error_type == "_WaitPollerSelfCloseError"` |
| 测试断言 self-close 仍为 fatal（round_errors=0, fatal_errors=1） | `tests/host/test_wait_poller_runtime.py:906-907` | `diagnostics.fatal_errors == 1` + `diagnostics.round_errors == 0` |

### C1-REVIEW-02 / DS-C1-03: 可恢复 round_errors 与 fatal_errors 分离

**判定：已关闭。**

| 验证点 | 文件(行号) | 证据 |
| --- | --- | --- |
| `WaitPollerDiagnosticsSnapshot.round_errors: int` 字段 | `dayu/host/wait_adapter.py:495` | `round_errors: int` |
| `_diagnostics_with_round_error` 递增 `round_errors`，保持 `fatal_errors` 不变 | `dayu/host/wait_adapter.py:1928-1929` | `round_errors=diagnostics.round_errors + 1` + `fatal_errors=diagnostics.fatal_errors` |
| `_diagnostics_with_fatal_error` 递增 `fatal_errors`，保持 `round_errors` 不变 | `dayu/host/wait_adapter.py:1898-1899` | `round_errors=diagnostics.round_errors` + `fatal_errors=diagnostics.fatal_errors + 1` |
| 所有 diagnostics 构造函数传递 `round_errors` | `dayu/host/wait_adapter.py:1777,1807,1839,1868,1898,1928` | 逐行验证通过 |
| `_initial_diagnostics` 初始化为 0 | `dayu/host/wait_adapter.py:1777` | `round_errors=0` |
| `_diagnostics_with_status` 透传 | `dayu/host/wait_adapter.py:1807` | `round_errors=diagnostics.round_errors` |
| 测试：transient exception → `round_errors == 1`, `fatal_errors == 0`, status `RUNNING` | `tests/host/test_wait_poller_runtime.py:933-935` | `diagnostics.round_errors == 1` + `diagnostics.fatal_errors == 0` + `diagnostics.status is RUNNING` |
| 测试：self-close → `round_errors == 0`, `fatal_errors == 1`, status `FAILED` | `tests/host/test_wait_poller_runtime.py:905-907` | 反向验证——fatal 路径不递增 round_errors |

## Findings

未发现实质性问题。4 个 accepted findings 均已正确关闭。

## Open Questions

无。

## Residual Risk

1. **`WaitCallbackAdapterStatus.STALE_CALLBACK` 移除是 breaking change**：若存在外部消费者通过 `from dayu.host import WaitCallbackAdapterStatus` 并检查 `STALE_CALLBACK`，升级后会在运行时收到 `AttributeError`。全仓 Python 代码已确认零引用，但无法排除外部仓库的依赖。Review-fix codex 已将此记录为 owner decision，controller 已接受。

2. **`WaitPollLastOutcome.BOUNDARY_REJECTED` schema CHECK 变更**：新增枚举值更新了 SQLite CHECK 约束。与现有数据库的兼容性取决于 schema migration 策略——若存在使用旧 schema 的持久化数据库，CHECK 约束不一致可能导致插入失败。此风险在 DS-C1-01 原始 finding 中已标注"修复风险（低）"，controller 接受后已纳入 fix scope。

3. **Batch C2 范围未覆盖**：本次 re-review 仅覆盖 C1 review-fix 的 4 个 accepted findings，不涉及 Batch C2（dispatch、promotion、cancel predispatch、tool accept duplicate index、Engine retry）。

## Conclusion

- **conclusion**: WU-SEMANTIC-OWNERSHIP-01 Round 2 Batch C1 review-fix 正确关闭了全部 4 个 accepted findings。DS-C1-01（BOUNDARY_REJECTED outcome + counter）、C1-REVIEW-01（STALE_CALLBACK 移除）、DS-C1-02（typed self-close exception）、C1-REVIEW-02/DS-C1-03（round_errors 与 fatal_errors 分离）均通过直接代码证据和测试断言验证。无新增问题，无未关闭的 accepted finding。
- **findings count**: 0
- **accepted findings closed**: 4/4（DS-C1-01、C1-REVIEW-01、DS-C1-02、C1-REVIEW-02/DS-C1-03）
- **artifact**: `docs/reviews/wu-semantic-ownership-01-round2-batch-c1-rereview-ds.md`
- **residual risk**: STALE_CALLBACK 移除对外部消费者是 breaking change（全仓内零引用）；BOUNDARY_REJECTED schema CHECK 变更的 database migration 兼容性；Batch C2 未覆盖
- **no code changes confirmation**: 本次 re-review 未修改任何代码。仅产出 review artifact。
