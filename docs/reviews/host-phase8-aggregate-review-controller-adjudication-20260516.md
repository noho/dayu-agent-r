# Host Phase 8 Aggregate Review Controller Adjudication - 2026-05-16

## Gate

当前 gate：Phase 8 aggregate deepreview。

Aggregate review artifacts：

- `docs/reviews/host-phase8-aggregate-review-mimo-20260516.md`
- `docs/reviews/host-phase8-aggregate-review-ds-20260516.md`

Truth docs：

- `docs/host/design.md` §14 Observer / Sink / Projection
- `docs/host/design.md` §16 Read Model / Host Event Stream / Outbox
- `docs/host/implementation-control.md` Phase 8
- `docs/host/phase8-projection-core-event-stream-plan.md`

## Controller Verdict

Phase 8 aggregate review 暂不进入 accepted deepreview commit。MiMo 与 DS 均给出 PASS，但两项 finding 应在当前 gate 修复：

1. Schema version 最终应与 Phase 8 plan 对齐为 `5`，而不是 slice 中间状态导致最终为 `6`。
2. Projection runner 对 payload 解析型 `HostDurableError` 应记录 projection failure，不应透传导致无 failure row。

`get_run` 未消费 RunResult projection 是 plan 明确 optional 项，维持 deferred，不进入 fix。

## Accepted Findings

### P8-AGG-F1: ProjectionRunner payload parsing failure should record failure row

来源：DS P8-AGG-F1。

裁决：accepted current fix。

理由：正常 Host append path 应写合法 object payload，但 projection runner 是 committed EventLog consumer 基础设施；corrupt /
手工修改 / 非 object payload 场景下，payload parse failure 不能让 caller 只收到透传异常且无 failure row。设计真源要求 Sink
失败只能更新 sink-local retry / error state，不能影响 EventLog 或治理状态；该类 failure 应纳入 `host_projection_failures`，
checkpoint 不推进。

修复要求：

- 在 `ProjectionRunner` 中把构造 `ProjectionEventView` 期间的 `HostDurableError` 建模为 projection failure。
- 不推进 checkpoint。
- 写入 `host_projection_failures`，failure row 指向失败的 EventLog row。
- 增加测试覆盖非 object / invalid payload row 触发 failure row，caller 不收到透传 `HostDurableError`。

### P8-AGG-F2: Final Phase 8 schema version should align with plan version 5

来源：MiMo 001，DS P8-AGG-F2。

裁决：accepted current fix。

理由：Phase 8 plan 在 §3 明确“Phase 8 implementation 必须将 fresh schema version bump 到 5”。S1 中间 commit bump 到 5
后，S3 又 bump 到 6，是多 slice 开发过程中的局部状态泄漏，不代表外部发布 schema。项目 fresh schema 约束下，当前 branch
最终只需要表达 main schema 4 -> Phase 8 schema 5。没有独立并行 schema 5 变更需要保留空洞版本。

修复要求：

- 将 `HOST_SCHEMA_VERSION` 最终值改回 `5`。
- 更新 schema tests 中的期望版本。
- 确保 fresh bootstrap 仍创建 Phase 8 所有 projection / read model tables。

## Rejected Findings

### P8-AGG-F3: `get_run` does not consume RunResult projection

来源：DS P8-AGG-F3。

裁决：rejected-as-current-fix / deferred。

理由：Phase 8 plan 明确 `get_run` 使用 `host_run_results` summary refs 是 optional，且 implementation 选择保持 public read truth
boundary 不变。当前 RunResult projection 已可构建、重建和测试，但没有被 public snapshot 消费不影响 Phase 8 exit condition。

Owner：Phase 9 / Phase 15 或后续 public read enhancement owner。

## Deferred Residual Risks

- Automatic after-commit projection catch-up：Phase 9 owner。
- Heavy sink / batch-transaction runner：Phase 13 / Phase 15 owner。
- Per-session repair filter：Phase 15 owner。
- RunResult summary refs 接入 public `RunSnapshot`：Phase 9 / Phase 15 或 public read enhancement owner。

## Fix Scope

允许：

- `dayu/host/projection.py`
- `dayu/host/durable/schema.py`
- `tests/host/test_projection_runner.py`
- `tests/host/test_durable_schema.py`
- `docs/reviews/host-phase8-aggregate-fix-20260516.md`

如 schema version change 影响 README / implementation artifact 中的事实性版本描述，可同步修改最小必要文档；否则禁止修改 README。

禁止：

- 修改 Engine、runtime、service、ui、fins。
- 修改 command path、admission、waiting、dispatch、recovery。
- 修改 public read API shape。
- commit、push、PR 或进入下一 gate。

## Required Validation

```bash
source .venv/bin/activate
pytest tests/host/test_durable_schema.py tests/host/test_projection_checkpoint.py tests/host/test_projection_runner.py tests/host/test_projection_read_model.py tests/host/test_public_event_stream.py tests/host/test_public_run_api.py tests/host/test_public_session_api.py tests/host/test_package_exports.py tests/host/test_import_boundary.py tests/host/test_weak_typing_guard.py -q
python -m pyright dayu/host tests/host
git diff --check
```
