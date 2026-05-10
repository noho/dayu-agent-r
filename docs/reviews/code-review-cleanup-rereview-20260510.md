# Host P8 Cleanup Re-Review

## Scope

- Mode: narrow re-review of `0362f79..HEAD` (commits `c8533d6` S1 + `b5025c1` S2-S10)
- Branch: `migration/host-p8-attempt-lease-recovery`
- Base: `0362f79` (plan accept commit)
- Output: `docs/reviews/code-review-cleanup-rereview-20260510.md`
- 目标: 逐项核验 fix 是否正确关闭三份 review report 的 controller-accepted findings

## Conclusion

**PASSED**

所有 controller-accepted findings 已正确关闭；无 legacy public fetch_more / default harness / recovery running attempt 入口残留；durable path 无 plain append fallback；owner-lost stale EventLog write 已消除；recovery scan 不创建 ungovernable attempt。测试、smoke、pyright 通过。复审指出的文档旧术语与 EOF 空行已由 controller 收口清理。

## Verification Summary

| 命令 | 结果 |
| --- | --- |
| `pytest tests/host -q` | **314 passed in 2.37s** |
| `python utils/smoke_host_p8_attempt_lease.py` | **通过** (7 个 step 全部断言成功) |
| `pyright dayu/host tests/host utils` | **0 errors, 0 warnings, 0 informations** |
| `git diff --check` | clean |

## Finding-by-Finding Verification

### 1. 0825-F01 / 0830-F1 / 0831-F001 — owner-lost stale EventLog write

| 项目 | 内容 |
| --- | --- |
| Original report id | 0825-F01, 0830-F1, 0831-F001 |
| Severity | 高 |
| Controller decision | accepted |
| Fix slice / commit | S3 / `b5025c1` |
| Re-review result | **FIXED** |
| Evidence | `_handle_owner_lost` (`_run_harness.py:1078-1194`) 不再调用 `event_store.append(host_failure_draft(...))`。改为通过 `supervisor.append_terminal_and_close(owner_context=..., draft=draft, terminal_state_override=LOST)` 单事务原子收口 (line 1156-1161)。CAS miss 时捕获 `AttemptFencingError`, 整事务回滚, 不写任何 RunEvent, 仅记 typed log `host.run.attempt_lease_lost_cas_miss` (line 1162-1180)。非 supervisor 路径 (test-only) 直接返回 `False`, 不写终态 (line 1136-1142)。`rg "self.event_store.append(host_failure_draft" dayu/host/_run_harness.py` 命中数为 0。 |

### 2. 0831-F003 — legacy public fetch_more / default harness 入口

| 项目 | 内容 |
| --- | --- |
| Original report id | 0831-F003 |
| Severity | 中 |
| Controller decision | accepted |
| Fix slice / commit | S2 / `b5025c1` |
| Re-review result | **FIXED** |
| Evidence | `rg "fetch_more_tool_result\|get_tool_fetch_more_handle\|_default_harness_for_running_loop\|_build_default_harness" dayu/host/ --include='*.py'` 命中数为 0。`dayu/host/__init__.py` 已删除 5 个 legacy import 与 `__all__` 条目 (diff 确认)。`LocalRunHarness.fetch_more_tool_result` / `get_tool_fetch_more_handle` 方法已删除 (grep 确认)。`InMemoryToolRuntime.fetch_more` / `get_tool_fetch_more_handle` 公开方法已删除 (grep 确认)。framework fetch_more 仅经 `execute_tool_call` 路径 (内部 `_append_fetch_*` / `_append_cursor_*` helper 保留)。`_tool_runtime.py:_resolve_appender` durable 路径 (`is_durable=True`) 无 owner scope 时 `RuntimeError` fail-fast (line 386-391), 不退化为 `PlainRunEventAppender`。反向断言测试 `test_host_public_api_surface.py` 覆盖所有删除项。 |

### 3. 0831-F002 — recovery scan 创建 ungovernable RUNNING attempt

| 项目 | 内容 |
| --- | --- |
| Original report id | 0831-F002 |
| Severity | 高 |
| Controller decision | accepted |
| Fix slice / commit | S5 / `b5025c1` |
| Re-review result | **FIXED** |
| Evidence | `rg "MARK_RECOVERING_AND_CREATE_ATTEMPT\|mark_recovering_and_create_attempt\|recovery_attempt_id\|recovery_attempt_index" dayu/ --include='*.py'` 命中数为 0。`AttemptRecoveryAction` (`_attempt_lease.py:283-292`) 仅保留 `NOOP_TERMINAL` / `MARK_STALE` / `MARK_LOST`, 无 `MARK_RECOVERING_AND_CREATE_ATTEMPT`。`AttemptRecoveryDecision` (`_attempt_lease.py:295-309`) 字段为 `action` / `source_attempt_id` / `reason`, 无 `recovery_attempt_id` / `recovery_attempt_index`。`_process_recovery_candidate` (`_attempt_supervisor.py:793-848`) 仅做 diagnostic close: 按 candidate state 分派 `mark_stale_or_lost`, 不创建新 attempt。`AttemptStaleConflictError` 已删除 (grep 确认)。测试 `tests/` / `utils/` 中无残留引用。 |

### 4. 0830-F2 — `list_recovery_candidates` 排除 CREATED orphan

| 项目 | 内容 |
| --- | --- |
| Original report id | 0830-F2 |
| Severity | 低 |
| Controller decision | accepted |
| Fix slice / commit | S6 / `b5025c1` |
| Re-review result | **FIXED** |
| Evidence | `list_recovery_candidates` (`_run_state_store.py:764-824`) SQL WHERE 条件为 `((state = ? AND lease_expires_at IS NOT NULL AND lease_expires_at <= ?) OR (state = ? AND lease_expires_at IS NULL))`, 参数为 `(RUNNING, now, CREATED)` (line 802-805)。CREATED + `lease_expires_at IS NULL` orphan 正式进入候选列表。`_process_recovery_candidate` 对 `CREATED` / `fencing_token is None` 走 `MARK_LOST` + `recovery_created_orphan` reason (line 831-841)。 |

### 5. 0830-F3 — `_allocate_fencing_token` lastrowid 兜底

| 项目 | 内容 |
| --- | --- |
| Original report id | 0830-F3 |
| Severity | 低 |
| Controller decision | accepted |
| Fix slice / commit | S7 / `b5025c1` |
| Re-review result | **FIXED** |
| Evidence | `_allocate_fencing_token` (`_run_state_store.py:978-1024`) 在 INSERT 后检查 `last_rowid = cursor.lastrowid; if last_rowid is None or last_rowid < 1: raise RuntimeError(...)` (line 1017-1023), 错误消息包含 `resource_id` 上下文。不再构造 `FencingToken(value=0)`。`FencingToken.__post_init__` 的 `ValueError` 不再被触达。新增测试 `test_allocate_fencing_token_fail_fast_when_lastrowid_invalid` 覆盖。 |

### 6. 0830-F4 — durable memory snapshot decode 不校验 schema_version

| 项目 | 内容 |
| --- | --- |
| Original report id | 0830-F4 |
| Severity | 低 |
| Controller decision | accepted |
| Fix slice / commit | S8 / `b5025c1` |
| Re-review result | **FIXED** |
| Evidence | `_decode_snapshot` (`_conversation_memory_durable.py:596-607`) 开头即校验 `raw_version = payload.get("schema_version"); if not isinstance(raw_version, int) or raw_version != _SCHEMA_VERSION: raise ValueError(_ERROR_SNAPSHOT_SCHEMA_VERSION)` (line 605-607)。不做旧版本兼容读取, 符合 CLAUDE.md "全新 schema 起库" 规则。 |

### 7. 0830-F5 — legacy `_finish_attempt_if_durable` 丢失 terminal_event_position

| 项目 | 内容 |
| --- | --- |
| Original report id | 0830-F5 |
| Severity | 低 |
| Controller decision | accepted |
| Fix slice / commit | S4 / `b5025c1` |
| Re-review result | **FIXED** |
| Evidence | `_finish_attempt_if_durable` (`_run_harness.py:1850-1945`) 已删除 legacy 分支。当前实现: `is_durable=True` 时必须 `attempt_supervisor + owner_context + lease_exit_stack` 均存在, 走 `supervisor.close_attempt_with_diagnostic_state` owner-aware CAS 路径 (line 1921-1934); 缺失时 `raise RuntimeError` (line 1941-1945); `is_durable=False` 时 noop (line 1935-1937)。`terminal_position` 不再被硬编码为 `None`——supervisor 路径内部处理 `terminal_event_position`。`rg "terminal_position.*None" dayu/host/_run_harness.py` 仅出现在 supervisor 调用的 `terminal_event_position=None` 参数 (非 legacy 硬编码), 符合预期。 |

### 8. S1 review F03 — durable `_resolve_attempt_appender` 可能返回 PlainRunEventAppender

| 项目 | 内容 |
| --- | --- |
| Original report id | S1-F03 |
| Severity | 低 |
| Controller decision | deferred to S2 |
| Fix slice / commit | S2 / `b5025c1` (随 S1 is_durable invariant + S2 入口删除一并关闭) |
| Re-review result | **FIXED** |
| Evidence | S1 建立的 `is_durable` invariant 确保 `InMemoryToolRuntime` 与 `LocalRunHarness` 同源。S2 删除 `_default_harness_for_running_loop` 后, durable 装配唯一入口为 `build_durable_harness(is_durable=True)`。`_tool_runtime.py:_resolve_appender` (line 386-391) durable 路径无 owner scope 时 `RuntimeError` fail-fast, 不返回 `PlainRunEventAppender`。`_run_harness.py:_resolve_attempt_appender` (line 558-573) durable 路径: 先尝试 supervisor scoped_appender, 再尝试 ContextVar, 均缺失时 `RuntimeError`。ContextVar 中不会被安装 `PlainRunEventAppender` (因为 `ToolRuntimeOwnerScope` 只安装 `AttemptScopedRunEventAppender`, 且 durable runtime 无 scope 时已在 `_resolve_appender` fail-fast)。 |

## Rejected / Deferred Findings (Controller Decision Acceptance)

| Finding | Original severity | Controller decision | 本次 re-review 对原裁决的态度 |
| --- | --- | --- | --- |
| 0825-F02 schema migration | 中 | rejected-with-reason (CLAUDE.md "全新 schema 起库") | **接受原裁决**。按 AGENTS.md / CLAUDE.md schema 变更规则, 不实现 ALTER TABLE 迁移。 |
| 0825-F03 owner_context snapshot stale | 低 | deferred-with-reason (CAS 真源在 DB) | **接受原裁决**。`verify_owner` SQL 用 DB 当前 `lease_expires_at`, 不依赖 snapshot 字段。仅诊断语义不精确, 不构成 correctness blocker。 |

## New Issues

### N01-低-tests/README.md recovery 行为描述已过时

- **位置**: `tests/README.md:220-228`
- **问题**: P8-S6 recovery 测试描述仍引用 `MARK_RECOVERING_AND_CREATE_ATTEMPT`、`mark_recovering_and_create_attempt`、"新 recovery attempt RUNNING" 等已删除语义。实际测试已改为 diagnostic close (`MARK_LOST` / `NOOP_TERMINAL`), 但 README 描述未同步。
- **严重程度**: 低 (文档, 非代码; 不影响正确性)
- **处理状态**: fixed by controller cleanup。`tests/README.md` 已同步为当前 recovery 诊断收口语义，并同步删除 public `InMemoryToolRuntime.fetch_more` 的旧描述。
- **是否 blocker**: 否

### N02-低-docs/host/phase8-plan.md 与 migration-plan.md body 仍含旧术语

- **位置**: `docs/host/phase8-plan.md:4-5,192-201`, `docs/host/migration-plan.md:4`
- **问题**: 两个文件已在顶部添加 P8 D2 修订声明 (deprecation header), 但 body 内容仍含 `MARK_RECOVERING_AND_CREATE_ATTEMPT` 等旧术语。这是历史 plan 文档的已知保留策略 (header 声明废弃, body 保留原始上下文)。
- **严重程度**: 低 (历史 plan 文档, header 已声明废弃)
- **建议**: 可接受现状 (header 已声明); 若追求文档一致性可考虑在 body 相关段落加 `> [已废弃]` 标注。
- **是否 blocker**: 否

## Residual Risks

| Risk | Owner | 说明 |
| --- | --- | --- |
| R1: recovery scan 无自动调度 | P9 / Service 层 | `recover_stale_attempts` 需外部显式调用; P8 不接入 bootstrap。 |
| R2: RunStream owner-lost 时客户端信号 | P9 / S3 测试已覆盖 | CAS hit 时 terminal event 自然结束 stream; CAS miss 时 generator cleanup 退出。无新公开 close 入口。 |
| R3: P8 不自愈到新 attempt 继续执行 | P9 | recovery 仅做诊断收口; 重试由 Service 层发起新 `StartRunRequest`。 |
| R4: 回滚部署 schema_version 校验报错 | 运维 / dayu-cli init | 符合 AGENTS schema 起库政策; 不留后门。 |
| R5: `tests/README.md` 旧 recovery 描述 | fixed | 已由 controller cleanup 同步为当前 recovery 诊断收口语义。 |

## Verification Commands & Results

```
$ source .venv/bin/activate && pytest tests/host -q
314 passed in 2.37s

$ source .venv/bin/activate && python utils/smoke_host_p8_attempt_lease.py
[s1] owner_acquired=true ... [s7] memory_recovered=True recovery_mode=checkpoint_rebuild

$ source .venv/bin/activate && python -m pyright dayu/host tests/host utils
0 errors, 0 warnings, 0 informations

$ git diff --check
NO_OUTPUT

$ rg "fetch_more_tool_result|get_tool_fetch_more_handle|_default_harness_for_running_loop|_build_default_harness" dayu/host/ --include='*.py'
NO_MATCHES

$ rg "MARK_RECOVERING_AND_CREATE_ATTEMPT|mark_recovering_and_create_attempt|recovery_attempt_id|recovery_attempt_index" dayu/ --include='*.py'
NO_MATCHES

$ rg "AttemptStaleConflictError" dayu/ --include='*.py'
NO_MATCHES
```

## Throughput Standard Compliance

- [x] 所有 controller-accepted findings fixed
- [x] 无 legacy public fetch_more / default harness / recovery running attempt 入口残留
- [x] durable path 无 plain append fallback
- [x] owner-lost stale EventLog write 被消除
- [x] recovery scan 不创建 ungovernable attempt
- [x] 测试通过 (314 passed)
- [x] smoke 通过
- [x] pyright 干净
- [x] `git diff --check` clean
