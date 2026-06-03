# WU-ENG-02 Residual Risk Re-Review (MiMo)

## Scope

- Mode: current changes (working tree vs HEAD)
- Branch: phaseflow/wu-eng-02-request-identity
- Base: HEAD (residual risk review fix diff)
- Task: 复审 DS 低严重度 finding 的 fix，确认是否可关闭 residual risk re-review gate
- Included scope:
  - `tests/engine/test_agent_phase3_tool_call.py` — S1-R1 工具超时第三个变体补齐断言
  - `docs/reviews/wu-eng-02-residual-risk-review-fix-codex.md` — fix artifact 准确性
  - `docs/host/issues-implementation-control.md` — 总控文档 gate 与 residual 表
- Excluded scope:
  - 已 merge 的 WU-ENG-02 主体 diff
  - 已 accepted 的 S3-R1 defer 裁决（不在本次复审范围）
- 验证基线: 125 tests passed, pyright 0 errors

## 检查项 1: `test_tool_execution_timeout_wins_over_runner_close_cancel` 断言补齐

**结论: 已修复，与另外两个超时变体一致。**

验证:

- diff 显示该测试在 line 1869-1875 新增了 `runner.request_identities_seen[0] is not None` 断言和 `failed.client_correlation_id == runner.request_identities_seen[0].client_correlation_id` 断言。
- 三个工具超时变体现在结构完全一致：
  - `test_tool_execution_timeout_fails_run_without_tool_result` (line 1800-1803): 已有断言
  - `test_tool_execution_timeout_wins_over_cleanup_cancel` (line 1838-1841): 已有断言
  - `test_tool_execution_timeout_wins_over_runner_close_cancel` (line 1872-1875): 本次补齐
- 三个变体均断言 `client_correlation_id` 来源于 `runner.request_identities_seen[0]`，即第一次 Runner call 的 request identity。语义正确：工具超时发生在工具执行等待阶段，当前工具批由第一次 Runner call 触发。
- `pytest -q` 三变体单独运行和全量受影响测试均通过。

## 检查项 2: Fix Artifact 准确性

**结论: `docs/reviews/wu-eng-02-residual-risk-review-fix-codex.md` 准确记录。**

核对:

- "接受的 finding" 节准确描述了 DS F1：第三变体缺 `client_correlation_id` 断言，是测试覆盖不一致而非生产缺陷。
- S3-R1 defer 记录与总控一致。
- "改动" 节列出的两项变更与 diff 一致：先断言 `request_identities_seen[0] is not None`，再断言 `client_correlation_id` 相等。
- "验证" 节记录 125 tests passed、pyright 0 errors，与本次独立复验一致。

## 检查项 3: 总控文档 gate 与留痕

**结论: 已进入 residual risk re-review gate，fix artifact 已留痕。**

核对:

- 当前状态表：`gate | review`，`implementation status | residual-risk-rereview-in-progress`，`next entry point | residual risk re-review gate for PR 114`。与实际 gate 位置一致。
- Residual Risk 表：
  - WU-ENG-02-S1-R1: `closed`
  - WU-ENG-02-S1-R2: `closed`
  - WU-ENG-02-S2-R2: `closed`
  - WU-ENG-02-S3-R1: `deferred-with-owner`（WU-OBS-00 / GitHub Issue #70）
  - WU-ENG-02-S3-R2: `closed`
- Review artifacts 列表已包含 `docs/reviews/wu-eng-02-residual-risk-review-fix-codex.md`。
- 推进记录已包含 residual risk fix gate 完成记录。

## 检查项 4: Blocking Findings

**结论: 无 blocking finding。**

- DS F1（低严重度测试覆盖缺口）已修复。
- S3-R1 defer 裁决已有明确 owner（WU-OBS-00 / GitHub Issue #70），理由成立（usage observation 语义归属不同于 provider debugging terminal 主链路），不阻塞当前 gate。
- 无新增 finding。

## Verdict

**pass**

WU-ENG-02 residual risk re-review gate 通过。DS 低严重度 finding 已修复，三变体测试覆盖一致，总控文档留痕完整，无 blocking finding。

## 验证命令

```bash
# 受影响测试
source .venv/bin/activate && pytest tests/engine/test_agent_phase3_tool_call.py tests/engine/contracts/test_runner_spec.py tests/engine/runners/openai/test_request_identity.py tests/host/test_run_attempt_transitions.py -q

# 类型检查
source .venv/bin/activate && pyright
```

预期结果: 125 tests passed, pyright 0 errors。
