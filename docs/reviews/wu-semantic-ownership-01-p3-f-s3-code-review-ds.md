# Code Review — WU-SEMANTIC-OWNERSHIP-01 P3-F S3

## Scope

- Mode: current changes (unstaged + uncommitted, since `3b2779e4`)
- Branch: `phaseflow/host-issues-control`
- Base commit: `3b2779e4` (P3-F S2 completion)
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-f-s3-code-review-ds.md`
- Included scope: 4 files (+83/-21)
- Excluded scope: untracked files per handoff
- Parallel review coverage: 无

## Verdict

**PASS** — S3 正确将 transient unavailable 的 terminal timeout 判定从 Fins adapter 内部 `created_at` 窗口移到 Host wait record 的 `deadline_at` / `expires_at` 真源。无 material defect，无 owner boundary 违规，无 LLM-facing 泄漏。

---

## Findings

未发现实质性问题。

逐项检查 S3 review focus 中的所有要求：

### 1. Fins adapter 消费 Host `deadline_at` first, then `expires_at`

`_wait_boundary_lost`（`wait_adapter.py:609-629`）的边界选择逻辑：

```python
boundary_text = (
    wait_record.deadline_at
    if wait_record.deadline_at is not None
    else wait_record.expires_at
)
```

- `deadline_at` 非 `None` → 只用 `deadline_at`，忽略 `expires_at`
- `deadline_at` 为 `None` → 回退到 `expires_at`
- 与 `dayu/host/wait_callback.py:_stale_status_or_none` 的 precedence 一致

测试 `test_fins_wait_poll_adapter_transient_unavailable_uses_host_wait_boundaries` 验证了优先级：`future_deadline_poll` 用例中 `deadline_at=future` + `expires_at=past` → 返回 `WaitPollNotReady`（只读 `deadline_at`，未来值优先于过期 `expires_at`）。✅

### 2. Invalid present boundary fails closed to lost

```python
try:
    boundary = parse_utc_timestamp(boundary_text)
except ValueError:
    return True  # lost
```

- `deadline_at="invalid-deadline"` → `parse_utc_timestamp` 抛 `ValueError` → `True`（lost）
- `expires_at="invalid-expires"` → 同上
- 测试覆盖：`invalid_deadline_poll`、`invalid_expires_poll` 均断言 `WaitPollLost`

空字符串 `""` 同样经 `parse_utc_timestamp` 失败 → lost。✅

### 3. No boundary + old `created_at` stays not-ready

```python
if boundary_text is None:
    return False  # not ready
```

- 无 `deadline_at` 且无 `expires_at` → `boundary_text is None` → `False`（not ready）
- `created_at` 完全不参与判定
- 测试覆盖：`no_boundary_old_created_poll` 中 `created_at` 设为 1 年前 → 仍返回 `WaitPollNotReady`

旧的行为（300 秒 `created_at` 窗口后 lost）已完全移除。✅

### 4. Old `_TRANSIENT_PENDING_MAX_SECONDS` / `_transient_pending_expired` removed

```bash
rg -n '_TRANSIENT_PENDING_MAX_SECONDS|_transient_pending_expired' dayu tests
# exit code 1 — zero matches
```

- `_TRANSIENT_PENDING_MAX_SECONDS` 常量已删除（原 `wait_adapter.py:105`）
- `_transient_pending_expired` 函数已删除（原 `wait_adapter.py:609-621`），替换为 `_wait_boundary_lost`
- `_timestamp_or_now` 仍保留，用于 observation handle 时间戳（非 timeout 判定）

### 5. No LLM-facing leakage of wait governance terms

- `_lost_outcome()` 返回 `ResolveWaitLostOutcome(error_code="fins_observation_lost", message="Fins observation is no longer available.")` — 不暴露 `deadline_at`、`expires_at` 时间戳、wait record id、Host governance 术语
- `_poll_error_result` 对 lost 和 not-ready 均使用同一 `_lost_outcome()`，不区分 transient/permanent lost
- `_MESSAGE_FINS_OBSERVATION_LOST` 常量 `"Fins observation is no longer available."` 是业务可读文本，不含内部标识

### 6. Test coverage matrix

| 场景 | 预期 | 断言 |
| --- | --- | --- |
| `deadline_at` 在未来 | `WaitPollNotReady` | ✅ |
| `deadline_at` 在过去 | `WaitPollLost` | ✅ |
| `deadline_at=None`, `expires_at` 在过去 | `WaitPollLost` | ✅ |
| `deadline_at` 文本非法 | `WaitPollLost` | ✅ |
| `expires_at` 文本非法 | `WaitPollLost` | ✅ |
| 无边界 + 很旧的 `created_at` | `WaitPollNotReady` | ✅ |

---

## Owner Boundary Assessment

| 边界 | Owner | S3 实现 | 证据 |
| --- | --- | --- | --- |
| Wait deadline / expiry truth | Host wait record (`WaitRecordRow`) | Fins adapter 只读取 `deadline_at` / `expires_at` | `wait_adapter.py:618-622` |
| Transient unavailable → lost 判定 | Host boundary（adapter 消费） | `_wait_boundary_lost` 按 Host 边界判断 | `wait_adapter.py:609-629` |
| Transient unavailable → not-ready | Adapter（无 Host 边界时保持 pending） | `boundary_text is None → False` | `wait_adapter.py:623-624` |
| Terminal wait resolution | Host poll / resolve / cancel | Adapter 只返回 `WaitPollNotReady` / `WaitPollLost`，不写 Host record / EventLog / 恢复 generator | `wait_adapter.py:399-403` |
| LLM-facing output | Adapter 不投影 governance terms | `_lost_outcome` 仅含 `"fins_observation_lost"` + 业务可读消息 | `wait_adapter.py:96-99` |

## Propagation Audit

1. **Producer**: Host `_wait_record_row(...)` 从 `candidate.await_spec.deadline` 写入 `deadline_at`，写 `expires_at=None`
2. **Durable truth**: `WaitRecordRow.deadline_at` / `expires_at`
3. **Adapter consumption**: `_poll_error_result` → `_wait_boundary_lost(wait_record)` → 按 deadline-first / expires-second 判断
4. **Projection**: 返回 `WaitPollNotReady`（无 Host 边界 / 未来边界）或 `WaitPollLost(_lost_outcome())`（过期 / 非法边界）
5. **Host resolution**: Host poller 继续拥有 wait terminal governance

结论：wait boundary truth 从 Host 真源派生，一条链路到底，无分支、无 fallback、无 adapter-owned timeout。

## Adversarial Failure Pass

- **Host 不提供 deadline/expires**: `boundary_text is None` → `False` → not-ready → Host poller cadence + claim TTL + cancel/close lifecycle 控制。不产生 phantom lost。✅
- **deadline_at 空字符串**: `None` 检查通过（空字符串不是 `None`）→ `parse_utc_timestamp("")` 失败 → `True` (lost)。fail-closed。✅
- **deadline_at 为未来但 expires_at 为过去**: `deadline_at` 优先，忽略 `expires_at` → future boundary → not-ready。✅
- **`parse_utc_timestamp` 内部异常**: 只捕获 `ValueError`；其他异常（如 `TypeError`）会传播到 `_poll_error_result` → 上层异常处理。边缘情况但正常路径不受影响。（`parse_utc_timestamp` 实现只对格式非法抛 `ValueError`，`None` 已在调用前过滤。）✅
- **`WaitRecordRow.deadline_at` 类型与 `parse_utc_timestamp` 兼容**: `WaitRecordRow.deadline_at` 是 `Optional[str]`，`parse_utc_timestamp` 接受 `str`。类型兼容。✅

## README Update

`dayu/fins/README.md` 更新两处：
- `TRANSIENT_UNAVAILABLE` 描述从"有界窗口内 not ready"改为"消费 Host deadline/expires 边界"
- Wait adapter 段落补充"等待 deadline / expiry 的 durable truth 属于 Host wait record"

更新在 `dayu/fins/` README 约束范围内，准确反映 S3 行为变更。✅

## Open Questions

无。

## Residual Risk

- **No-boundary transient unavailable 可能长期 not-ready**: 当 Host await spec 不提供 deadline 时，`deadline_at=None` 且 `expires_at=None`，transient unavailable 会无限期保持 not-ready。这是有意的 owner boundary 选择——Fins adapter 不拥有 terminal timeout。实际轮询由 Host `WaitPollerRuntimePolicy.not_ready_observe_interval_seconds`、claim TTL、cancel / close lifecycle 控制。
- **`expires_at` 当前 Host creation path 写 `None`**: S3 实现支持该字段供未来 Host-owned expiry truth 消费，但当前生产路径不会触发 `expires_at` 分支。
- **`parse_utc_timestamp` 的 non-ValueError 异常传播**: `_wait_boundary_lost` 只捕获 `ValueError`；若 Host codec 未来抛出其他异常类型，会传播到 `_poll_error_result` 的上层。当前 Host codec 实现只对格式非法抛 `ValueError`，风险极低。
