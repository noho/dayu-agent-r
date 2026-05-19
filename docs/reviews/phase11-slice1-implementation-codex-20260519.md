# Phase 11 Slice 1 Implementation Artifact

## Scope

- Work unit: Phase 11 Host Lifecycle / Recovery / Multi-process Hardening。
- Gate: Slice 1 implementation。
- Agent: AgentCodex。
- Accepted plan: `docs/host/phase11-host-lifecycle-recovery-plan.md` at commit `9223cbf`。
- Boundary: 未提交、未 push、未创建 PR、未进入 review 或下一 slice。

## Changed Files

- `dayu/host/durable/liveness.py`
- `dayu/host/recovery_process.py`
- `dayu/host/dispatch.py`
- `tests/host/test_host_instance_liveness.py`
- `tests/host/test_recovery_orphan_classifier.py`
- `dayu/host/README.md`
- `docs/reviews/phase11-slice1-implementation-codex-20260519.md`

## Implemented Plan Items

- 收紧 Host instance lifecycle：
  - `_REGISTER_RUNNING_SOURCE_STATUSES` 仅保留 `RUNNING`。
  - `STOPPING -> RUNNING` repeated register 现在返回结构化 `HostInstanceLifecycleConflictError`。
  - `RUNNING` repeated register 仍保持幂等 refresh。
- 新增 typed process proof foundation：
  - `ProcessEvidence`
  - `ProcessLivenessProbe`
  - `StdlibPidLivenessProbe`
  - `DurableOrphanCandidate`
  - `OrphanClassificationPolicy`
  - `PositiveOrphanProof | OwnerStillLive | OrphanProofInconclusive`
- 新增只读 positive orphan classifier：
  - 覆盖 missing owner、missing liveness row、heartbeat 未 stale、heartbeat stale alone、pid missing、pid live without identity、pid identity matched、pid reused start-token mismatch、pid reused boot-id mismatch、probe error。
  - classifier 不写 DB，不推进 Run / Attempt 状态。
- 加固 dispatch Host instance identity：
  - `process_start_token` 改为 `uuid4().hex`，与 `host_instance_id` 分开生成。
  - 移除 `dispatch-{host_handle_id}` 可预测 token。
  - runtime lane owner 同步使用该进程启动 token 作为诊断身份。
- 增加 dispatch heartbeat lifecycle：
  - scheduler open 后启动 Host instance heartbeat background task。
  - refresh 使用当前 scheduler 自己的 `HostInstanceIdentity`。
  - retry-exhausted refresh failure 结构化 warning 后下一轮重试。
  - fatal heartbeat exception 结构化 error，并 best-effort 只将当前 scheduler 自己的 instance 标记为 `STOPPING`。
  - scheduler close 先 best-effort mark `STOPPING`，关闭 task / worker / lane 后 best-effort mark `STOPPED`。

## Validation

```bash
source .venv/bin/activate && pytest tests/host/test_host_instance_liveness.py tests/host/test_recovery_orphan_classifier.py -q
```

Result: `30 passed in 0.40s`

```bash
source .venv/bin/activate && pytest tests/host/test_dispatch_scheduler.py::test_scheduler_close_suppresses_handle_close_exception -q
```

Result: `1 passed in 0.28s`

```bash
source .venv/bin/activate && python -m pyright dayu/host tests/host
```

Result: `0 errors, 0 warnings, 0 informations`

```bash
git diff --check
```

Result: passed with no output.

## Docs Decision

- Updated `dayu/host/README.md` because `dayu/host/dispatch.py` and Host recovery foundation changed current Host developer-facing mechanisms.
- The update is intentionally narrow: it records Host instance liveness heartbeat, high-entropy process token, and read-only orphan classifier semantics. It does not document startup recovery scan, CAS closeout, or recovery dispatch because those are not implemented in Slice 1.

## Residual Risks / Owners

- Startup recovery scan, CAS recheck, `ATTEMPT_LOST -> RUN_RECOVERING / RUN_LOST`, and recovery dispatch remain Slice 2 / Slice 3 owners.
- `RECOVERING` cancel and graceful shutdown public-contract hardening remain Slice 4 owner.
- The stdlib pid probe only proves pid existence. pid reused mismatch requires a stronger platform probe that can observe start token or boot id; the classifier supports that capability, but this slice does not add platform-specific process fingerprinting.
- Existing external uncommitted change in `docs/host/implementation-control.md` was present before this work and was not modified by this slice.

## Conclusion

HANDOFF_IMPLEMENTED
