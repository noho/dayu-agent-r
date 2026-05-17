# P9-S3 Code Review Controller Adjudication

## Verdict

PASS。

P9-S3 `RunInputBuilder MemorySnapshotProvider and Lag Fallback` code review 已完成双路 review、controller fix、双路 re-review。AgentMiMo 与 AgentDS re-review 均为 PASS，remaining blocking findings 为 0。

## Artifacts

- Review: `docs/reviews/p9-s3-code-review-mimo-20260517.md`
- Review: `docs/reviews/p9-s3-code-review-ds-20260517.md`
- Re-review: `docs/reviews/p9-s3-code-rereview-mimo-20260517.md`
- Re-review: `docs/reviews/p9-s3-code-rereview-ds-20260517.md`

## Controller Findings

Accepted and fixed:

- Snapshot ahead-of-required 现在进入 `MemoryProjectionRepairRequired`，reason 为 `SNAPSHOT_AHEAD_OF_REQUIRED`，避免 latest snapshot 泄漏 required cursor 之后的 session facts。
- `stable_layer_size_units` 已在 RunInputBuilder memory renderer 中消费；stable blocks 按 P9 顺序受 cap 约束，超预算 block 记录 `BUDGET_LIMIT_REACHED` transient diagnostic。
- 当前 `USER_INPUT_ACCEPTED` 去重仅使用 event id，删除 `run_id + summary_text` 文本回退，避免误删同 Run 同文本历史 turn。
- `EPISODE_SUMMARY_ACCEPTED` 已抽为模块常量。
- Covered snapshot 测试 helper 改为与生产一致的 `ATTEMPT_STARTED - 1` cursor，并断言 covered path 不产生 inline repair diagnostic。
- 新增 inline delta + stable layer budget exceeded 交叉测试。

Rejected:

- DS 001 中“生产 required cursor 应改为 Run started boundary”的建议不接受。P9 plan 明确规定 `required_event_sequence = current_facts.attempt.started_event_sequence - 1`。Attempt boundary 允许 resume / steer / recovery 新 Attempt 前的 committed facts 进入 memory；Run boundary 不是 P9 当前裁决。

Deferred:

- `_validate_snapshot_cursor` 中正 cursor 缺失 event id 的防御性 guard 在 typed constructor 下不可达，但保留为 durable corruption 防御和 type narrowing；不作为 S3 阻断。
- 更细粒度 cursor corruption 分支测试可作为 Host durable hardening 后续项，不阻断 S3。

## Validation

- `pytest tests/host/test_run_input_builder.py tests/host/test_memory_projection.py tests/host/test_weak_typing_guard.py`: 49 passed。
- `pyright dayu/host/run_input.py dayu/host/memory.py dayu/host/durable/memory.py tests/host`: 0 errors。
- `git diff --check`: clean。

## Residual Risk

- P9-S3 暂不实现 projection repair worker 编排；repair-required 只作为结构化错误暴露，后续 S4 / phase governance 负责接线。
- `stable_layer_size_units` 第一版使用现有 conservative size estimator；真实 token 质量需要后续基于追问质量和 prompt telemetry 小步校准。
