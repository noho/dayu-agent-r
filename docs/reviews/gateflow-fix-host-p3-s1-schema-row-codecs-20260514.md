# Gateflow Fix: Host P3-S1 Schema And Row Codecs

- **work gate name**: fix
- **work unit**: Host Phase 3 Session / Run / Attempt 状态机与 Admission
- **assigned slice**: P3-S1 Schema And Row Codecs
- **source review artifact path**: `docs/reviews/gateflow-code-review-host-p3-s1-schema-row-codecs-mimo-20260514.md`
- **controller adjudication artifact path**: `docs/reviews/gateflow-code-review-host-p3-s1-schema-row-codecs-controller-adjudication-20260514.md`
- **controller-accepted finding ids**: P3S1-MIMO-001
- **artifact path**: `docs/reviews/gateflow-fix-host-p3-s1-schema-row-codecs-20260514.md`

## Per-Finding Fix Status

### P3S1-MIMO-001-已修复-低-测试未验证 active partial unique index 拒绝 terminal status 组合

- **fix status**: 已修复
- **修复内容**: 在 `tests/host/test_state_schema.py` 增加聚焦测试，验证同一 Session 可以同时持久化一个 active Run 与一个 terminal Run，不触发 `host_runs_one_active_per_session` partial unique index。
- **覆盖边界**: 新测试对 `SUCCEEDED`、`FAILED`、`CANCELLED`、`LOST` 四个 terminal Run status 参数化执行，证明 terminal status 不参与 active partial unique 约束。
- **生产代码变更**: 无。

## Rejected Finding Not Touched

- **P3S1-MIMO-002**: controller 裁决为 `rejected-with-reason`，本 fix 未修改 `_serialize_str_enum` 或任何生产代码。

## Changed Files

- `tests/host/test_state_schema.py`
- `docs/reviews/gateflow-fix-host-p3-s1-schema-row-codecs-20260514.md`

## Validation Commands / Results

- `source .venv/bin/activate && pytest tests/host/test_state_schema.py tests/host/test_durable_schema.py -q`
  - result: passed, `18 passed in 0.15s`
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`
  - result: passed, `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - result: passed, no whitespace errors

## New Risks / Open Questions

- new risks: none
- open questions: none

## Residual Risk Classification

- **P3S1-MIMO-001 residual risk**: none. The accepted test gap is covered for all terminal Run statuses.
- **Phase 3 later-slice behavior**: Session lifecycle command、Run / Attempt transition helpers、Admission、FIFO promotion、cancel、terminal closeout 与 multiprocess race proofs 仍属于后续 slice / phase 范围；本 fix 未改变这些既有 residual risk。

## Finding Title Status Update Result

- `P3S1-MIMO-001`: 本 fix artifact 标记为 `已修复`；source review artifact 未由 fix agent 回写，等待 re-review agent 作为最终状态权威回写。
- `P3S1-MIMO-002`: 未触碰，仍按 controller adjudication 的 `rejected-with-reason` 处理。
