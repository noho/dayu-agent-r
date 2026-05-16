# PR 56 Fix Re-Review — F1/F2 Targeted Verification

日期：2026-05-16

## Scope

- Mode: targeted re-review
- PR: #56
- Fix artifact: `docs/reviews/pr-56-fix-digest-and-poll-lost-20260516.md`
- Original reviews:
  - `docs/reviews/pr-56-deepreview-ds-20260516.md`
  - `docs/reviews/pr-56-deepreview-mimo-20260516.md`
- Re-review focus: F1/F2 fix verification、回归检查、F3~F8 deferral 合理性
- Output file: `docs/reviews/pr-56-fix-re-review-mimo-20260516.md`

## F1 Fix Verification — digest 校验一致性

**原 finding**: `ToolAwaitingAcceptCandidate.__post_init__` 使用 `startswith("sha256:") + len == 71` 弱校验，不检查十六进制字符集。

**修复内容**: `dayu/host/waiting.py:240` 改用 `is_sha256_digest(value)`。

**验证**:

1. `is_sha256_digest` 定义于 `dayu/host/durable/codec.py:93-100`，内部使用 `_SHA256_DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")` 的 `fullmatch`。
2. 该 pattern 与 `dayu/host/api.py:49` 的 `_require_sha256_digest` 使用同一正则 — **校验语义完全一致**。
3. import 变更：新增 `from dayu.host.durable.codec import is_sha256_digest`（`waiting.py:43`）。
4. 旧代码 `not value.startswith("sha256:") or len(value) != 71`（2 行 diff context）替换为 `not is_sha256_digest(value)`（1 行）。
5. 新增测试 `test_awaiting_accept_candidate_rejects_non_hex_digest`（`test_wait_awaiting_accept.py:154-167`）：
   - 构造 `tool_schema_digest="sha256:" + "g" * 64`（非十六进制字符）
   - 断言 `pytest.raises(ValueError, match="tool_schema_digest must be sha256 digest")`
   - 测试正确命中 `is_sha256_digest` 返回 False 的分支

**结论**: **F1 FIXED**。修复是 root-cause 级别 — 复用 durable digest 真源函数，消除校验语义分叉。测试覆盖了非十六进制字符的拒绝路径。

## F2 Fix Verification — WaitPollLost 测试覆盖

**原 finding**: `WaitPoller.poll_once` 的 `WaitPollLost` 分支（`wait_adapter.py:366-367`）无直接测试覆盖。

**修复内容**: `tests/host/test_wait_adapter_polling.py` 新增 `test_poll_adapter_lost_result_closes_run`。

**验证**:

1. 新测试（`test_wait_adapter_polling.py:167-206`）完整覆盖 poll lost 路径：
   - `_seed_waiting_run` 创建 WAITING Run + wait record
   - `_SequenceAdapter` 返回 `WaitPollLost(ResolveWaitLostOutcome(reason_code="adapter_lost", ...))` 含 `WaitProviderStatusRef`
   - `poller.poll_once()` 触发 poller → adapter poll_wait → WaitPollLost → 构造 `ResolveWaitRequest(outcome=ResolveWaitLostOutcome)` → `resolve_wait`
   - 断言：`result.resolved == 0`、`result.lost == 1`、`adapter.poll_count == 1`、`wait_record.status is WaitRecordStatus.LOST`、`snapshot.status is RunStatus.LOST`
2. 测试使用 `_SequenceAdapter`（与现有 `test_poll_adapter_ready_result_resolves_wait` 相同模式），通过 `WaitPollLost` 而非 `WaitPollReady` 验证 lost 收口。

**结论**: **F2 FIXED**。测试直接覆盖 poller → resolve_wait → RUN_LOST 的端到端路径，关闭了原 review 识别的覆盖缺口。

## F3 / F4~F8 Deferral 合理性

| Finding | 严重度 | Deferral 理由 | 评估 |
|---------|--------|--------------|------|
| F3 cross-test helper import coupling | 低 | 测试 helper 跨文件复用已形成惯例，提取会重排多个文件，不阻塞 PR | ✅ 合理 |
| F4 resolve_wait 绕过 admission service | 低 | 功能正确，架构一致性问题，不阻塞 Phase 7 exit | ✅ 合理 |
| F5 isinstance 硬编码四元组 | 低 | 四种 outcome 类型已完成且稳定，仅影响未来扩展 | ✅ 合理 |
| F6 resume transition 操作顺序 | 低 | 事务内原子性保证，纯可读性 | ✅ 合理 |
| F7 await_kind 缺少 DDL CHECK | 信息 | await_kind 来自工具侧，Host 不控制值空间 | ✅ 合理 |
| F8 _resolve_outcome_json if 链 | 信息 | 穷尽性可读性，非功能缺陷 | ✅ 合理 |

所有 deferral 均为低/信息严重度，不影响 Phase 7 exit criteria，有明确后续 owner。

## 回归检查

- `pytest tests/host/test_wait_awaiting_accept.py tests/host/test_wait_adapter_polling.py tests/host/test_resolve_wait_command.py -q` → **15 passed** ✓
- `pytest tests/host -q` → **391 passed**（原 389 + 2 新增测试）✓
- `python -m pyright dayu/host/waiting.py tests/host/test_wait_awaiting_accept.py tests/host/test_wait_adapter_polling.py` → **0 errors, 0 warnings, 0 informations** ✓
- `python -m pyright dayu/ tests/ utils/` → **0 errors, 0 warnings, 0 informations** ✓
- `git diff --check` → 通过 ✓
- `git diff --stat HEAD` → 3 files changed, 72 insertions(+), 2 deletions(-) — 最小化 targeted fix ✓

## 结论

**PASS。**

F1 和 F2 均已正确修复。F1 复用 durable digest 真源 `is_sha256_digest`，消除校验语义分叉，测试覆盖非十六进制拒绝。F2 新增 `WaitPollLost` 端到端测试，关闭 poller lost 路径覆盖缺口。F3~F8 deferral 合理，均为低/信息严重度。未引入回归（391 passed, 0 pyright errors）。Fix 是最小化 targeted 改动（3 files, +72/-2），不改变生产行为语义。
