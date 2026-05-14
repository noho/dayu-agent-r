# Gateflow Controller Re-Review Adjudication: Host P3-S4 Admission And Queue Promotion

- **gate**: code re-review adjudication
- **work unit**: Host Phase 3 Session / Run / Attempt 状态机与 Admission
- **assigned slice**: P3-S4 Admission And Queue Promotion
- **review artifact**: `docs/reviews/gateflow-code-review-host-p3-s4-admission-queue-mimo-20260514.md`
- **controller adjudication artifact**: `docs/reviews/gateflow-code-review-host-p3-s4-admission-queue-controller-adjudication-20260514.md`
- **fix artifact**: `docs/reviews/gateflow-fix-host-p3-s4-admission-queue-20260514.md`
- **re-review artifact**: `docs/reviews/gateflow-code-re-review-host-p3-s4-admission-queue-mimo-20260514.md`
- **controller**: Codex
- **artifact path**: `docs/reviews/gateflow-code-re-review-host-p3-s4-admission-queue-controller-adjudication-20260514.md`

## Controller Conclusion

P3S4-C-001 已修复。Queued idempotency retry 后现在立即断言 EventLog row count 未变化，direct retry 的 no-extra-events 断言也保留。P3-S4 可以进入 README / 总控状态同步和本地最终验证；验证通过后创建 accepted slice commit。

## Finding Closure

| Finding | Initial Decision | Re-Review Result | Final Status | Owner |
|---------|------------------|------------------|--------------|-------|
| P3S4-C-001 | accepted | fixed | closed-fixed | AgentCodex |
| F001 observation | deferred | unchanged | deferred | P3-S5 owner |
| F002 observation | accepted-as-non-issue | unchanged | closed-non-issue | controller |

## Evidence

- `test_duplicate_idempotency_returns_same_run_without_extra_events` 在 queued retry 后立即断言 `_event_count(...) == before_queued_retry`。
- direct retry 仍保留 `_event_count(...) == before_direct_retry`。
- 修复未修改 `dayu/host/admission.py`，未扩大生产 scope。
- MiMo re-review 验证通过：
  - `source .venv/bin/activate && pytest tests/host/test_admission_queue.py tests/host/test_run_attempt_transitions.py -q`
  - `source .venv/bin/activate && python -m pyright dayu/host tests/host`
  - `git diff --check`

## Residual Risks / Follow-Up Owners

- **P3-S5 owner**: terminal / cancel 后自动 promotion trigger 尚未实现；`AdmissionWakeupPort.wake_queue_promotion` 当前只是端口和测试 spy 能力。
- **P3-S6 owner**: 更完整的多进程 admission race、idempotency race 与 queue promotion race 由 multiprocess slice 覆盖。
- **Phase 4 / public API owner**: P3-S4 只提供 internal admission service，不提供 public Host command facade。

## Next Gate

同步 `dayu/host/README.md`、`tests/README.md` 与 `docs/host/implementation-control.md` 当前事实，然后执行本地最终验证并 commit。
