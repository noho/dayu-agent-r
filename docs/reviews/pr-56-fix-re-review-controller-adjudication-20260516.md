# PR 56 Fix Re-Review Controller Adjudication

日期：2026-05-16

## Scope

- PR：[#56](https://github.com/noho/dayu-agent-r/pull/56)
- Original reviews：
  - `docs/reviews/pr-56-deepreview-mimo-20260516.md`
  - `docs/reviews/pr-56-deepreview-ds-20260516.md`
- Fix artifact：`docs/reviews/pr-56-fix-digest-and-poll-lost-20260516.md`
- Re-review artifacts：
  - `docs/reviews/pr-56-fix-re-review-mimo-20260516.md`
  - `docs/reviews/pr-56-fix-re-review-ds-20260516.md`

## Findings

- PR56-DS-F1：`ToolAwaitingAcceptCandidate` digest 校验弱于 durable / public API digest 真源。
  - 严重性：Low。
  - 裁决：accepted and fixed。
  - 修复：`dayu/host/waiting.py` 复用 `dayu.host.durable.codec.is_sha256_digest(...)`，不再用 prefix + length 弱校验。
  - 测试：`tests/host/test_wait_awaiting_accept.py::test_awaiting_accept_candidate_rejects_non_hex_digest` 覆盖非十六进制 digest 拒绝。
  - 状态：closed。MiMo 与 DS targeted re-review 均确认 fixed。
- PR56-DS-F2：`WaitPollLost` poller path 缺少直接测试覆盖。
  - 严重性：Low。
  - 裁决：accepted and fixed。
  - 修复：`tests/host/test_wait_adapter_polling.py::test_poll_adapter_lost_result_closes_run` 覆盖 `WaitPollLost -> resolve_wait -> WaitRecordStatus.LOST / RunStatus.LOST`。
  - 状态：closed。MiMo 与 DS targeted re-review 均确认 fixed。
- PR56-DS-F3：测试文件跨模块导入 `test_resolve_wait_command.py` 私有 helper。
  - 严重性：Low。
  - 裁决：deferred test cleanup。
  - 理由：当前测试 helper 跨文件复用已在 P7-S4 / P7-S5 形成局部惯例，不影响生产正确性；提取共享 helper 会重排多个测试文件，属于后续测试结构 cleanup。
- PR56-DS-F4 至 F8：架构一致性 / 未来扩展 / 可读性 / 信息性建议。
  - 严重性：Low / Info。
  - 裁决：deferred hardening / cleanup。
  - 理由：均不影响 Phase 7 exit criteria、状态机正确性或 PR merge safety。

## Re-Review Evidence

- MiMo re-review：F1 / F2 fixed，F3-F8 deferral 合理，391 passed，pyright 0，diff check clean。
- DS re-review：F1 / F2 fixed，F3-F8 deferral 合理，391 passed，pyright 0，diff check clean。

## Verification

- `source .venv/bin/activate && pytest tests/host/test_wait_awaiting_accept.py tests/host/test_wait_adapter_polling.py tests/host/test_resolve_wait_command.py -q`
  - 结果：`15 passed`
- `source .venv/bin/activate && pytest tests/host -q`
  - 结果：`391 passed`
- `source .venv/bin/activate && python -m pyright dayu/host/waiting.py tests/host/test_wait_awaiting_accept.py tests/host/test_wait_adapter_polling.py`
  - 结果：`0 errors, 0 warnings, 0 informations`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - 结果：`0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - 结果：通过。

## Verdict

PR 56 review fix gate accepted。可提交 fix commit、更新总控文档、push 到 PR 56。PR 56 当前保持 draft review-ready；是否转 ready-for-review 仍需用户额外授权。
