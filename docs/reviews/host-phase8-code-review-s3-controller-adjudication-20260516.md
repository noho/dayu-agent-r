# Host Phase 8 P8-S3 Code Review Controller Adjudication - 2026-05-16

## Gate

当前 gate：P8-S3 `Minimal RunResult / Session Timeline Read Model / Repair` code review。

Implementation artifact：

- `docs/reviews/host-phase8-implementation-s3-read-model-repair-20260516.md`

Code review artifacts：

- `docs/reviews/host-phase8-code-review-s3-mimo-20260516.md`
- `docs/reviews/host-phase8-code-review-s3-ds-20260516.md`

Truth plan：

- `docs/host/phase8-projection-core-event-stream-plan.md`

## Controller Verdict

P8-S3 implementation 符合核心 plan：RunResult / Session timeline projection 是派生 read model，不是 governance truth；repair
从 EventLog replay，不读取 projection 作为输入；未新增 public timeline facade；terminal conflict 不静默覆盖；public read
truth boundary 保持不变。

两路 review 均 PASS。DS 提出 1 个当前应修复的测试覆盖 finding，以及 1 个低风险 plan wording / implementation granularity
observation。裁决：进入 P8-S3 fix gate，只补 `optional_payload_text` 非法 typed value 的测试覆盖，不修改生产逻辑。

## Accepted Findings

### P8S3-CR-001: Invalid display_text typed value failure path lacks test coverage

来源：DS finding 001。

裁决：accepted current fix。

理由：plan 要求 `USER_INPUT_ACCEPTED.display_text` 只从 typed payload 字段读取，缺失时为 NULL，非法 typed value 应 fail
projection，不能静默拼接 raw payload。生产代码已有 `HostDurableError` 分支，但缺少回归测试。该分支是防止 raw text
synthesis / silent fallback 的边界，应补测试。

修复要求：在 `tests/host/test_projection_read_model.py` 增加非法 `display_text` 值测试，覆盖数字或空字符串时
`MinimalReadModelProjectionConsumer` 通过 runner 记录 projection failure，checkpoint 不推进，并且不写 timeline item。

## Rejected Findings

### P8S3-CR-002: repair batch transaction granularity differs mildly from plan wording

来源：DS finding 002。

裁决：rejected-as-non-blocking / accepted as residual observation。

理由：当前 `ProjectionRunner.run_once(..., limit=batch_size)` 逐 EventLog row 使用独立 `HostTransactionRunner.run_write()`
提交；这比 plan wording 中“每批独立 transaction”粒度更细，但满足真正的 root invariant：每个 event 的 projection write 与
checkpoint advance 在同一事务内，失败后 checkpoint 停在最后成功 event，下一次 repair 可继续。实现没有长事务风险，也没有数据
损坏风险。P8-S3 不允许修改 `dayu/host/projection.py`，因此不要求当前改造 batch-transaction runner。

后续 owner：Phase 13 / Phase 15 若需要 heavy sink 或 batch-atomic repair，再重新评估 runner batch transaction 模式。

## Deferred Findings

- `get_run` 接入 `RunResult` summary refs 仍按 implementation artifact 保持延后；当前 public read truth boundary 不变。
- 自动 after-commit projection catch-up 仍由 Phase 9 owner。

## Fix Scope

允许：

- `tests/host/test_projection_read_model.py`
- `docs/reviews/host-phase8-fix-s3-read-model-repair-20260516.md`

禁止：

- 修改生产代码。
- 修改 README、plan、design、implementation-control 或其它 review artifacts。
- commit、push、PR 或进入下一 gate。

## Required Validation

```bash
source .venv/bin/activate
pytest tests/host/test_durable_schema.py tests/host/test_projection_checkpoint.py tests/host/test_projection_runner.py tests/host/test_projection_read_model.py tests/host/test_public_event_stream.py tests/host/test_public_run_api.py tests/host/test_public_session_api.py tests/host/test_package_exports.py tests/host/test_import_boundary.py tests/host/test_weak_typing_guard.py -q
python -m pyright dayu/host tests/host
git diff --check
```
