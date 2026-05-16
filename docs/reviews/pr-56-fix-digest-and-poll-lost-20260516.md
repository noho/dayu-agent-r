# PR 56 Fix - Digest Validation And Poll Lost Coverage

日期：2026-05-16

## Scope

- PR：[#56](https://github.com/noho/dayu-agent-r/pull/56)
- Review artifacts：
  - `docs/reviews/pr-56-deepreview-mimo-20260516.md`
  - `docs/reviews/pr-56-deepreview-ds-20260516.md`
- Accepted current fixes：
  - DS F1-Low：`ToolAwaitingAcceptCandidate` digest 校验弱于 public API digest 校验。
  - DS F2-Low：`WaitPollLost` poller path 缺少直接测试覆盖。

## 改动

- `dayu/host/waiting.py`
  - `ToolAwaitingAcceptCandidate.__post_init__` 不再用 `startswith("sha256:") + len == 71` 做弱校验，改为复用 `dayu.host.durable.codec.is_sha256_digest(...)`，与 durable digest 真源保持一致。
- `tests/host/test_wait_awaiting_accept.py`
  - 新增 `test_awaiting_accept_candidate_rejects_non_hex_digest`，验证非十六进制 digest 被拒绝。
- `tests/host/test_wait_adapter_polling.py`
  - 新增 `test_poll_adapter_lost_result_closes_run`，验证 `WaitPollLost` 经 poller 调用 public `resolve_wait` 后把 wait record 收口为 `LOST`，Run 收口为 `LOST`。

## 裁决

- F1 accepted and fixed。
  - 理由：这是低成本 root-cause 修正，复用已有 durable digest 真源，避免 Host 内部 digest 校验语义分叉。
- F2 accepted and fixed。
  - 理由：poller explicit lost branch 是 Phase 7 adapter contract 的一部分，补直接测试能关闭 plan 覆盖缺口。
- F3 cross-test helper import coupling deferred。
  - 理由：当前测试 helper 跨文件复用已在 P7-S4 / P7-S5 中形成局部惯例，不影响生产正确性。提取共享 helper 会同时重排多个测试文件，属于后续测试结构 cleanup，不阻塞 PR 56。
- DS F4-F8 均为低严重度 / 信息性维护建议，不影响 Phase 7 exit；保留为后续 hardening / cleanup。

## 验证

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
