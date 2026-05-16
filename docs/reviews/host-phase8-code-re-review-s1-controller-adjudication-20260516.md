# Host Phase 8 P8-S1 Code Re-review Controller Adjudication - 2026-05-16

## Gate

当前 gate：P8-S1 `Projection Runner / Checkpoint / Typed Consumer Contracts` code re-review after accepted fix。

Implementation artifact：

- `docs/reviews/host-phase8-implementation-s1-projection-runner-20260516.md`

Code review / fix artifacts：

- `docs/reviews/host-phase8-code-review-s1-mimo-20260516.md`
- `docs/reviews/host-phase8-code-review-s1-ds-20260516.md`
- `docs/reviews/host-phase8-code-review-s1-controller-adjudication-20260516.md`
- `docs/reviews/host-phase8-fix-s1-projection-runner-20260516.md`

Code re-review artifacts：

- `docs/reviews/host-phase8-code-re-review-s1-mimo-20260516.md`
- `docs/reviews/host-phase8-code-re-review-s1-ds-20260516.md`

## Controller Verdict

PASS。P8-S1 implementation + fix 可以进入 accepted slice commit gate。

MiMo 与 DS 均确认 P8S1-CR-001、P8S1-CR-002、P8S1-CR-003 已修复，未引入 scope creep、新 production 变更或新增
blocking issue。

## Accepted Finding Verification

| Finding | Status | Evidence |
| --- | --- | --- |
| P8S1-CR-001 duplicate checkpoint advance test gap | fixed | 新增重复推进同一 `event_sequence` 时抛出 `HostDurableError` 的测试；两路 re-review 均确认覆盖 `event_sequence <= checkpoint` 的 `==` 分支。 |
| P8S1-CR-002 non-positive event_sequence test gap | fixed | 新增 `event_sequence=0` 与 `event_sequence=-1` 参数化测试；两路 re-review 均确认覆盖 checkpoint advance 输入边界。 |
| P8S1-CR-003 checkpoint CHECK branch test gap | fixed | 新增 `checkpoint_event_sequence=0 + checkpoint_event_id != NULL` 与 `checkpoint_event_sequence>0 + checkpoint_event_id IS NULL` 两个 `IntegrityError` 断言；两路 re-review 均确认 DDL CHECK 分支已覆盖。 |

## Residual Risks And Owners

- P8-S2：`stream_run_events` EventLog cursor truth 与 projection checkpoint / failure 独立性。
- P8-S3：RunResult / Session timeline read model consumers 与 repair helper。
- Phase 9：automatic after-commit projection catch-up / composition wiring。

这些 residual risks 均已有后续 owner，不阻塞 P8-S1 accepted slice commit。

## Validation

AgentCodex fix validation：

```bash
source .venv/bin/activate && pytest tests/host/test_durable_schema.py tests/host/test_projection_checkpoint.py tests/host/test_projection_runner.py tests/host/test_import_boundary.py tests/host/test_weak_typing_guard.py -q
```

Result：31 passed。

```bash
source .venv/bin/activate && python -m pyright dayu/host tests/host
```

Result：0 errors。

```bash
git diff --check
```

Result：clean。

Controller 在 accepted slice commit 前需复跑上述验证。
