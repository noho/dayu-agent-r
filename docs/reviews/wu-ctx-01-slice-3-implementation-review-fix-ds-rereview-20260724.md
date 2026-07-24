# WU-CTX-01 Slice 3 Implementation Review Fix — DS 路定向 Re-review

## 1. Scope

- **被审对象**：Codex fix artifact
  `docs/reviews/wu-ctx-01-slice-3-implementation-review-fix-codex.md` 声明的
  `CTRL-S3-IMPL-01` 修复。
- **变更文件**：`dayu/host/context_anchor.py`、
  `tests/host/test_context_anchor.py`。
- **Base**：`126e67ca`（accepted Slice 2）。
- **上游参考**：
  - AgentMiMo review：`docs/reviews/code-review-20260724-071249.md`
  - AgentDS review（本路初始）：
    `docs/reviews/code-review-20260724-071353.md`
  - Controller adjudication：
    `docs/reviews/wu-ctx-01-slice-3-implementation-review-controller-adjudication.md`
  - Codex fix artifact：
    `docs/reviews/wu-ctx-01-slice-3-implementation-review-fix-codex.md`
- **排除**：`docs/host/issues-implementation-control.md`（Controller-owned）。

## 2. 逐项核对

### CTRL-S3-IMPL-01：cursor 与 MAX_CONTEXT_TOKEN_COUNT 解耦

**核对结论：已关闭。** 直接证据：

- `context_anchor.py:181-183` — `candidate_input_cursor` 仅通过
  `_require_non_negative_int` 校验，无 `MAX_CONTEXT_TOKEN_COUNT` 比较。
  旧代码中存在 `if self.candidate_input_cursor > MAX_CONTEXT_TOKEN_COUNT: raise ValueError(...)` 的分支已删除。
- `_require_non_negative_int`（`context_anchor.py:1393-1406`）正确拒绝
  `bool`（TypeError）、负数（ValueError），接受 `0` 和任意大正整数。
- `MAX_CONTEXT_TOKEN_COUNT` import（`context_anchor.py:23`）仍保留且仅
  服务于三个正确 consumer（见下条）。

### MAX_CONTEXT_TOKEN_COUNT 三个正确消费者完整性

**核对结论：完整无回归。** 三个正确 consumer 逐项确认：

| # | 位置 | 语义 | 状态 |
|---|------|------|------|
| 1 | `context_anchor.py:193-194` | `context_window_size > MAX_CONTEXT_TOKEN_COUNT` | ✅ 保留 |
| 2 | `context_anchor.py:263-264` | `CompatibleContextAnchor` usage/conservative anchor token | ✅ 保留 |
| 3 | `context_anchor.py:1003-1005` | strict parsed usage prompt/completion/total token | ✅ 保留 |

### 新增 owner-level tests

**核对结论：两个新增测试均正确锁定 owner boundary。**

**`test_query_event_cursor_is_independent_from_token_ceiling`**（`test_context_anchor.py:76-111`）：
- `MAX_CONTEXT_TOKEN_COUNT + 1` 作为 `candidate_input_cursor` → 构造成功，assert 通过
- 同一值作为 `context_window_size` → `ValueError("context_window_size exceeds supported range")`
- **验证了 cursor 与 token ceiling 的语义分离**：相同数值在 cursor owner boundary 合法，
  在 window token owner boundary 被拒。

**`test_query_event_cursor_fails_closed_at_typed_boundary`**（`test_context_anchor.py:114-149`）：
- `True`（bool）→ `TypeError`，match `"ContextAnchorQuery.candidate_input_cursor"`
- `-1`（negative）→ `ValueError`，match `"ContextAnchorQuery.candidate_input_cursor"`
- **验证了 cursor 的 strict non-bool/non-negative typed boundary**：在
  `ContextAnchorQuery` owner boundary（而非下游 resolver 或 budget 模块）fail closed。

### current_run_id / candidate_input_digest docstring 澄清

**核对结论：docstring 澄清准确，未引入错误的历史 digest 相等比较。**

- `ContextAnchorQuery` docstring（`context_anchor.py:142-148`）：
  - `current_run_id`: "调用方从当前complete candidate冻结的Host Run typed identity；
    **不与历史anchor Run id做相等比较**。"
  - `candidate_input_digest`: "调用方从当前complete candidate冻结的input digest
    typed identity；**不与历史anchor input digest做相等比较**。"
  - `candidate_input_cursor`: "resolver允许读取的最大EventLog sequence；**它不是
    token count**。"
- `_compatibility_mismatch`（`context_anchor.py:1080-1116`）：未新增任何
  `query.current_run_id` 或 `query.candidate_input_digest` 的相等比较。
  兼容性维度仍为 provider、model、context_window_size、estimator_id/version、
  request_semantics_digest 五项。

### DS-03/04/05 拒绝项确认未实施

**核对结论：三项均未实施，符合 Controller 裁决。**

- **DS-03**（overload 表达 `anchor_resolution`/`fallback_reason` 联合）：
  `context_budget.py` 未新增 `@overload` 装饰器，`build_context_sizing_result_from_atoms`
  签名未变。
- **DS-04**（`manifest_event.event_sequence == 0` fallback）：
  `engine_ingest.py:3827` 无 guard；`context_anchor.py` 无 `candidate_input_cursor == -1`
  特殊处理。
- **DS-05**（损坏 link 的 loose parsing）：
  `_build_scan_items`（`context_anchor.py:553-558`）损坏 link 仍直接产生
  `_Barrier(ITERATION_LINK_INVALID)`，不尝试从 partial payload 提取 identity。

### 范围漂移检查

**核对结论：无范围漂移。**

- `git diff 126e67ca --stat -- dayu/host/ tests/host/` 显示 17 个 changed
  production/test 文件 — 全部属于 Slice 3 初始实现的 §8.4 allowlist。
  Codex fix 仅修改了 `context_anchor.py` 和 `test_context_anchor.py`（两个
  untracked 文件在初始实现中已存在），与 fix artifact 声明一致。
- `resolve_context_anchor` 算法（`context_anchor.py:370-440`）、
  `_build_scan_items`（`context_anchor.py:512-639`）、
  `_call_item`（`context_anchor.py:642-796`）、
  `_compatibility_mismatch`（`context_anchor.py:1080-1116`）全部逻辑不变。
- `CompatibleContextAnchor.__post_init__` 的 token MAX 校验（lines 263-264）不变。
- `_parse_usage_evidence` 的 token MAX 校验（lines 1003-1005）不变。

### 初始实现回归检查

**核对结论：无初始实现回归。**

- 全部 21 个 test_context_anchor 测试通过（`21 passed in 0.43s`）。
- pyright 针对两个 fix-target 文件：`0 errors, 0 warnings, 0 informations`。
- 初始 DS review 的 5 个低严重度 findings（DS-01~DS-05）中：
  - DS-01 doc 歧义已通过 docstring 澄清关闭
  - DS-02 通过 `CTRL-S3-IMPL-01` 关闭
  - DS-03/04/05 被 Controller 明确 reject，未实施
- 初始 DS review verdict（PASS，0 correctness blocker）仍成立且无新增反例。

## 3. Verdict

**PASS — 0 findings。**

`CTRL-S3-IMPL-01` 已完全关闭：cursor 与 `MAX_CONTEXT_TOKEN_COUNT` 的语义
owner 耦合已删除；cursor 严格受 non-bool/non-negative EventLog sequence
boundary 约束且由 owner-level tests 锁定；三个 token/window `MAX_CONTEXT_TOKEN_COUNT`
consumer 完整保留；docstring 澄清了 current candidate identity 字段的语义
边界且未引入错误的历史 digest 相等比较。拒绝项（DS-03/04/05）未实施；无范围
漂移或初始实现回归。

## 4. Artifact

- 本文件：
  `docs/reviews/wu-ctx-01-slice-3-implementation-review-fix-ds-rereview-20260724.md`
