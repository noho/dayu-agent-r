# Code Review — PR #65 Host Phase 11 Lifecycle Recovery Hardening

## Scope

- Mode: PR Review
- Repository: noho/dayu-agent-r
- PR: #65 — "Host Phase 11 lifecycle recovery hardening"
- Author: noho
- Head: feat/host-phase-11-recovery
- Base: main
- URL: https://github.com/noho/dayu-agent-r/pull/65
- Output file: docs/reviews/pr-65-deepreview-ds-20260519.md
- Included scope:
  - dayu/host/recovery.py (new)
  - dayu/host/recovery_process.py (new)
  - dayu/host/durable/run_transition.py (recovery primitives)
  - dayu/host/durable/state.py (new state row helpers)
  - dayu/host/durable/event_log.py (count_recovery_dispatches_for_run)
  - dayu/host/admission.py (RECOVERING cancel paths)
  - dayu/host/dispatch.py (host instance heartbeat, graceful shutdown)
  - dayu/host/command.py (RECOVERING cancel docstring + deferred gate)
  - dayu/host/open_host.py (startup scan integration)
  - docs/host/design.md (§27/§27.1 extensions)
  - docs/host/implementation-control.md
  - docs/host/phase11-host-lifecycle-recovery-plan.md
  - tests/host/ (7 new/recovery test files + updates)
  - tests/runtime/test_lane.py (lane hardening)
  - README files
- Excluded scope: review artifacts under docs/reviews/ (already reviewed in prior gates)
- Parallel review coverage: 无（单 reviewer 逐路径走读全部生产代码变更）

## Verification Results

| Check | Result |
|-------|--------|
| `pytest tests/host -q` | 793 passed, 1 skipped |
| `pytest tests/runtime -q` | 107 passed |
| `python -m pyright dayu/host dayu/runtime` | 0 errors, 0 warnings |
| `git diff --check main...HEAD` | 1 trailing whitespace in review artifact (non-code) |
| Engine file changes | 0 — confirmed no engine changes |
| `git branch --show-current` | feat/host-phase-11-recovery (clean, no uncommitted) |
| `gh pr checks 65` | No CI checks configured on this branch |

## Findings

### 1-CLOSED（已在 prior aggregate review 中裁决）-中-`_IsDeferredCancelStateOperation` 移除 RECOVERING 后未同步注释

- **入口/函数**: `_IsDeferredCancelStateOperation.__call__`（`command.py:1222`）
- **文件(行号)**: `dayu/host/command.py:1229-1235`
- **输入场景**: 对 RECOVERING Run 调用 `cancel_run`，先经 deferred cancel gate 判断
- **实际分支**: `run.status is RunStatus.RECOVERING` 不匹配 `WAITING` 或 `(RUNNING, CANCELLING)`，落到 `return False`
- **预期行为**: 非 deferred，正确路由到 admission `_classify_cancel_target` 中的 `_cancel_recovering`
- **直接证据**: diff 删除了 `RunStatus.RECOVERING` 从 deferred 列表中；admission `_classify_cancel_target` 在第 1547 行正确处理 `RunStatus.RECOVERING`
- **影响**: 无功能缺陷，但 `_IsDeferredCancelStateOperation` 的类级 docstring（若存在）可能未同步更新以说明 RECOVERING 现在被 admission 直接覆盖
- **建议改法和验证点**: 确认 admission layer cancel classification 注释已覆盖 RECOVERING 路径即可；实际 admission 代码（`_classify_cancel_target` line 1547）已正确实现
- **修复风险**: 无
- **严重程度**: 低（行为正确，仅注释一致性）

**Controller adjudication（prior aggregate review）**: 已接受，无代码变更需要。

### 2-CLOSED（已在 prior aggregate review 中裁决）-低-`StdlibPidLivenessProbe` 无法检测 pid 复用场景

- **入口/函数**: `StdlibPidLivenessProbe.collect` -> `classify_orphan_candidate` -> `_classify_stale_owner`
- **文件(行号)**: `dayu/host/recovery_process.py:72-114`（probe），`dayu/host/recovery_process.py:260-339`（分类）
- **输入场景**: 旧 Host 实例 pid 被回收，新进程复用相同 pid 且 heartbeat 已 stale
- **实际分支**: `StdlibPidLivenessProbe` 永远返回 `observed_start_token=None`、`observed_boot_id=None`；`_classify_stale_owner` 中 `evidence.exists=True` 且 `observed_start_token` 为 `None`，走到 line 326 `observed_start_token == row.process_start_token` 返回 `OwnerStillLive`
- **预期行为**: 本应能检测 pid 复用并证明 orphan
- **直接证据**: `StdlibPidLivenessProbe` 仅使用 `os.kill(pid, 0)`，无法读取 `/proc/<pid>/` 信息
- **影响**: pid 复用场景下 orphan 判定为 inconclusive，无法自动 recovery。Restart 的 Host 不会误杀（安全侧），但 recovery 覆盖率存在缺口
- **建议改法和验证点**: 设计文档已明确此为第一版最小机制；`ProcessLivenessProbe` Protocol 支持未来替换为 platform-specific probe（如 `/proc` 读取）。当前实现不会产生假阳性（误判 orphan），属于保守安全策略
- **修复风险**: 低（不做修改无风险；未来 probe 替换需充分测试 pid 复用场景）
- **严重程度**: 低（设计约束明确，不会导致误杀 active Attempt）

**Controller adjudication（prior aggregate review）**: 已接受，属 v1 已知范围限制。

### 3-未发现实质性问题

经逐路径走读 recovery scan 编排、orphan proof 分类、CAS closeout、recovery dispatch、RECOVERING cancel（单 Run 和 session-scope）、graceful shutdown、multiprocess recovery 分类器、runtime lane 变更和 tests，**未发现未修复的 correctness、stability 或 maintainability 缺陷**。

所有 prior aggregate review + slice reviews 中的 findings 已在当前分支 HEAD 上全部合入修复。

## §27/§27.1 合规性逐项验证

| 设计要求 | 实现位置 | 状态 |
|---------|---------|------|
| Host 启动时必须执行 recovery scan | `open_host.py:461-466`，`recovery.py:167-207` | ✅ |
| ACCEPTED Run 保持 ACCEPTED | `recovery.py:225-226` | ✅ |
| QUEUED Run 保持 QUEUED | `recovery.py:227-232` | ✅ |
| WAITING Run 保持 WAITING | `recovery.py:233-238` | ✅ |
| 仅 positive orphan proof 可推进 recovery | `recovery.py:328-349`（三种分类） | ✅ |
| positive orphan proof 最小条件（heartbeat stale + pid 证据 + CAS recheck） | `recovery_process.py:200-257`（heartbeat），`recovery_process.py:260-339`（pid），`run_transition.py:1345-1361`（CAS recheck） | ✅ |
| CAS `ATTEMPT_LOST` -> `RUN_RECOVERING` -> new Attempt | `run_transition.py:1325-1423`（closeout），`run_transition.py:1487-1566`（recovery start） | ✅ |
| 新 Attempt + 新 execution_id + `start_reason=recovery` | `run_transition.py:1522-1558` | ✅ |
| 每 Run 最多 1 次 automatic startup recovery | `recovery.py:265-301`（count check），`event_log.py:598-634`（count 实现） | ✅ |
| owner heartbeat stale 但 proof 不成立时不推进 | `recovery_process.py:275-281`（`OrphanProofInconclusive`），`recovery.py:335-340` | ✅ |
| 多进程不可用"不可确认控制"代替 orphan proof | `recovery_process.py` 只用 durable + process evidence 做决策 | ✅ |
| Recovery 输入仅限 durable truth | scanner 只读 `read_non_terminal_runs`、`read_attempt_by_id`、`read_dispatch_record_by_attempt_id`、`read_host_instance`、`EventLogStore` | ✅ |
| RECOVERING -> CANCELLED（dispatch 前） | `admission.py:1695-1757`（单 cancel），`admission.py:2221-2246`（session cancel） | ✅ |
| RECOVERING -> RUNNING（dispatch 创建新 Attempt） | `run_transition.py:1526-1539`（`start_recovering_run_row` CAS） | ✅ |
| RECOVERING -> LOST（超过上限） | `run_transition.py:1426-1484`（`lose_recovering_run_in_transaction`） | ✅ |
| Graceful shutdown（停止 admission + 传播 cancel + 持久化） | `dispatch.py:1548-1580`（close: stopping mark, heartbeat cancel, drain cancel, stopped mark） | ✅ |
| host_instance_id / dispatch record 不是 lease | 设计文档 §27.1 line 2830-2832 明确声明；代码中无 lease 语义 | ✅ |
| 旧 Attempt takeover 禁止 | 始终创建新 Attempt，CAS 检查旧 Attempt status | ✅ |

## No Engine Changes

```
$ git diff --name-only main...HEAD | grep -i engine
(no output)
```

确认：0 Engine 文件变更。Engine 层不感知 recovery、RECOVERING 状态或 host instance。

## Public API Preservation

- `open_host(options)` — 签名不变，内部新增 startup recovery scan（`open_host.py:461-466`）
- `Host.cancel_run(run_id, request)` — 签名不变，覆盖范围从 queued/pre-dispatch/active/WAITING 扩展到 +RECOVERING
- `Host.cancel_session_runs(session_id, request)` — 签名不变，覆盖范围同
- `Host` Protocol — 不变
- `OpenHostOptions` — 不变
- 无新增 public 导出

## Runtime Lane — 未升级为 Host Truth

runtime lane 变更仅限于：
1. `tests/runtime/test_lane.py` 新增 77 行 lane close/acquire 硬化测试
2. `dispatch.py` 的 `LaneOwner.process_start_token` 现在传入真实的 `host_identity.process_start_token`（之前为 None）

lane 仍然是资源容量 guard，不是 Host truth。`process_start_token` 仅作为 lane owner 诊断字段传入，不参与 Host 状态治理。

## README 同步

- `dayu/host/README.md`: 更新了 cancel_run/cancel_session_runs 覆盖状态说明（+RECOVERING），新增 startup recovery scan 描述，更新 RECOVERING 状态描述
- `tests/README.md`: 更新了测试分层描述
- 变更与代码一致，无过期术语残留

## PR Branch Cleanliness

```
$ git diff --check main...HEAD
docs/reviews/phase11-slice5-code-review-ds-20260519.md:78: trailing whitespace.
```

唯一的 whitespace 警告在已有的 review artifact 中（非生产代码），属无害。

## Open Questions

无。

## Residual Risk

1. **CI/checks 缺失**: `gh pr checks 65` 报告 "no checks reported on this branch"，PR branch 上未配置 CI。所有本地验证（pytest + pyright）已通过，但缺乏自动化 CI gate。
2. **`StdlibPidLivenessProbe` 的 pid 复用盲区**: v1 已知限制，见 Finding 2。不会误杀 active Attempt，但会降低部分 pid 复用场景的 recovery 成功率。后续可通过替换 `ProcessLivenessProbe` 实现解决。
3. **heartbeat 间隔 1s**: `_HOST_INSTANCE_HEARTBEAT_INTERVAL_SECONDS = 1.0` 在单机部署下合理，若未来高密度多进程部署可能需要调优为可配置项。
4. **WAITING recovery 仅 diagnostic**: design doc §27 明确 WAITING Run 只能恢复 wait adapter observation，不创建新 Attempt。当前实现仅做 diagnostic record，完整 WAITING recovery 需后续 phase 落地。此属已知 scope 限制，不是缺陷。

## Verdict

**PASS** — PR #65 满足全部审查标准：

- 设计合规：完全满足 `docs/host/design.md` §27/§27.1 的全部要求
- 无 Engine 变更：confirmed
- 公共 API 保留：cancel_run/cancel_session_runs 覆盖范围扩展，签名不变
- startup recovery scan：positive orphan proof + CAS ordering 正确实现
- RECOVERING dispatch + cancel：完整闭环，单 Run 和 session-scope 均覆盖
- graceful shutdown：heartbeat cancel + stopping/stopped liveness marks 实现
- multiprocess recovery：基于 durable truth + process evidence 的只读分类
- runtime lane：未升级为 Host truth
- 测试：907 passed（host 793 + runtime 107）+ 1 skipped
- 类型检查：pyright 0 errors
- README：同步更新

无 blocking findings。PR 可进入 draft-PR-pass gate。
