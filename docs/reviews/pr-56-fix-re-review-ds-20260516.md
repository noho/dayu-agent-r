# PR 56 Fix Re-Review — DS F1/F2 Targeted

## Scope

- Original reviews: `docs/reviews/pr-56-deepreview-ds-20260516.md`, `docs/reviews/pr-56-deepreview-mimo-20260516.md`
- Fix artifact: `docs/reviews/pr-56-fix-digest-and-poll-lost-20260516.md`
- Affected files:
  - `dayu/host/waiting.py` — digest 校验从弱校验改为 `is_sha256_digest`
  - `tests/host/test_wait_awaiting_accept.py` — 新增非 hex digest 拒绝测试
  - `tests/host/test_wait_adapter_polling.py` — 新增 WaitPollLost → RUN_LOST 测试
- Re-review mode: targeted fix verification + regression check
- Output file: `docs/reviews/pr-56-fix-re-review-ds-20260516.md`

## DS F1-Low: Digest 校验不一致 — FIXED

### 修复审查

| 维度 | 修复前 | 修复后 |
|------|--------|--------|
| 校验代码 | `not value.startswith("sha256:") or len(value) != 71` | `not is_sha256_digest(value)` |
| 真源 | 本地弱条件 | 复用 `dayu.host.durable.codec.is_sha256_digest` |
| 正则 | 无 | `^sha256:[0-9a-f]{64}$` |
| 导入 | 无新导入 | `from dayu.host.durable.codec import is_sha256_digest` (第 41-43 行) |

`is_sha256_digest` 真源确认：`dayu/host/durable/codec.py:93-100` 使用 `re.compile(r"^sha256:[0-9a-f]{64}$").fullmatch(value)`，与 `dayu/host/api.py:_require_sha256_digest` 的语义等价。

### 测试覆盖

新增 `test_awaiting_accept_candidate_rejects_non_hex_digest`（`test_wait_awaiting_accept.py` 第 155-168 行）：

- 输入：`"sha256:" + "g" * 64`（含非法十六进制字符 `g`）
- 断言：`pytest.raises(ValueError, match="tool_schema_digest must be sha256 digest")`
- 旧校验（`startswith("sha256:") + len == 71`）**会错误通过**，新校验正确拒绝。

### 裁决：FIXED。修复 root cause——复用 durable digest 真源，消除 Host 内部校验语义分叉。测试覆盖修复前会漏过的输入场景。

## DS F2-Low: WaitPollLost 未经测试覆盖 — FIXED

### 修复审查

新增 `test_poll_adapter_lost_result_closes_run`（`test_wait_adapter_polling.py` 第 167-208 行）：

- 构造 `WaitPollLost` 含完整的 `ResolveWaitLostOutcome`：
  - `reason_code="adapter_lost"`
  - `message="external job status is no longer observable"`
  - `provider_status_ref=WaitProviderStatusRef(adapter_key=..., status_ref="provider-status-lost", status_digest=...)`
- 注入到 `_SequenceAdapter`，运行 `poller.poll_once()`
- 断言链：
  - `result.resolved == 0`，`result.lost == 1` — 正确分类为 lost
  - `adapter.poll_count == 1` — adapter 确实被执行
  - `wait_record.status is WaitRecordStatus.LOST` — wait record 被原子收口为 LOST
  - `snapshot.status is RunStatus.LOST` — Run 被原子收口为 LOST

覆盖的代码路径：`WaitPoller.poll_once()` 第 351 行 `adapter.poll_wait(record)` → 第 355 行 `isinstance(poll_result, WaitPollLost)` → 第 358-364 行构造 `ResolveWaitRequest` → 第 365 行 `resolve_wait(...)` → `waiting.py` lost 路径 → RUN_LOST。

### 裁决：FIXED。测试覆盖 poller 驱动的 WaitPollLost → resolve_wait → RUN_LOST 完整路径，关闭原 review 中最大的测试缺口。

## DS F3–F8 Deferred 评估

| Finding | 处置 | 评估 |
|---------|------|------|
| F3 cross-test import coupling | Deferred | 合理。不影响生产正确性，提取 helper 需重排多个测试文件，属于后续测试结构 cleanup。 |
| F4 resolve_wait bypass admission | Deferred | 合理。架构一致性优化，无功能影响，可在后续 hardening 中处理。 |
| F5 outcome isinstance 展开元组 | Deferred | 合理。四种 outcome 类型已稳定，未来扩展罕见，当前硬编码无成本。 |
| F6 resume insert 在 CAS 之前 | Deferred | 合理。事务内操作顺序无外部可见差异，可读性改进可择机处理。 |
| F7 await_kind 缺 CHECK | Deferred | 合理。await_kind 由 ToolAwaitSpec 定义，不由 Host 控制值空间，有意为之。 |
| F8 if 链可读性 | Deferred | 合理。纯风格问题。 |

所有 deferred 项均为低/信息性严重度，不阻塞 PR merge。

## 回归验证

| 命令 | 结果 |
|------|------|
| `pytest tests/host/test_wait_awaiting_accept.py tests/host/test_wait_adapter_polling.py tests/host/test_resolve_wait_command.py -q` | 15 passed |
| `pytest tests/host -q` | 391 passed（与修复前一致，无回归） |
| `pyright dayu/host/waiting.py tests/host/test_wait_awaiting_accept.py tests/host/test_wait_adapter_polling.py` | 0 errors, 0 warnings, 0 informations |
| `pyright dayu/ tests/ utils/` | 0 errors, 0 warnings, 0 informations |
| `git diff --check` | 通过 |

## Open Questions

无。

## Verdict

**PASS — 所有 accepted findings 已确认修复，无回归。**

- DS F1：root-cause 修复已完成，复用 durable digest 真源 `is_sha256_digest`，测试覆盖修复前会漏过的非 hex digest 场景。
- DS F2：WaitPollLost → poller → resolve_wait → RUN_LOST 路径已有直接测试覆盖。
- DS F3–F8 均按低/信息性严重度合理 deferred，不阻塞 merge。
- 391 tests passed，0 pyright errors，`git diff --check` clean。
