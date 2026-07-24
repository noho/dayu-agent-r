# WU-CTX-01 Slice 3 Implementation Re-Review (MiMo)

## 1. Scope

- Gate：Slice 3 implementation re-review（MiMo 路）。
- Base：accepted Slice 2 protected commit `126e67ca`。
- Controller 裁决：
  `docs/reviews/wu-ctx-01-slice-3-implementation-review-controller-adjudication.md`。
- Fix artifact：
  `docs/reviews/wu-ctx-01-slice-3-implementation-review-fix-codex.md`。
- 审查对象：`dayu/host/context_anchor.py`、`tests/host/test_context_anchor.py`。
- 排除：`docs/host/issues-implementation-control.md`（Controller-owned）。
- 模式：定向双路 re-review，只验证 CTRL-S3-IMPL-01 关闭条件与 reject 项未偷渡。

## 2. CTRL-S3-IMPL-01 关闭验证

### 2.1 EventLog cursor 与 token ceiling 解耦

**结论：通过。**

- `ContextAnchorQuery.__post_init__`（`context_anchor.py:181-183`）对
  `candidate_input_cursor` 调用 `_require_non_negative_int`，不引用
  `MAX_CONTEXT_TOKEN_COUNT`。
- `MAX_CONTEXT_TOKEN_COUNT` 的三个正确消费者未被改动：
  - `context_window_size`（`context_anchor.py:193-194`）
  - `CompatibleContextAnchor` usage/anchor tokens（`context_anchor.py:263-264`）
  - `_parse_usage_evidence` prompt/completion/total tokens（`context_anchor.py:1003-1005`）

### 2.2 bool/negative fail closed

**结论：通过。**

- `_require_non_negative_int`（`context_anchor.py:1403-1406`）：
  - `isinstance(value, bool)` → `TypeError`
  - `value < 0` → `ValueError`
- 测试 `test_query_event_cursor_fails_closed_at_typed_boundary`（`test_context_anchor.py:114-149`）
  parametrize 覆盖 `True → TypeError`、`-1 → ValueError`。

### 2.3 window/usage/anchor token MAX 校验未丢

**结论：通过。**

- `context_window_size > MAX_CONTEXT_TOKEN_COUNT` → `ValueError`
  （`context_anchor.py:193-194`）
- `CompatibleContextAnchor` tokens `> MAX_CONTEXT_TOKEN_COUNT` → `ValueError`
  （`context_anchor.py:263-264`）
- usage tokens `> MAX_CONTEXT_TOKEN_COUNT` → `HostDurableError`
  （`context_anchor.py:1003-1005`）

### 2.4 current_run_id/candidate_input_digest 文档澄清

**结论：通过。**

- `ContextAnchorQuery` docstring（`context_anchor.py:143-153`）明确：
  - `current_run_id`："调用方从当前complete candidate冻结的Host Run typed identity；
    不与历史anchor Run id做相等比较"
  - `candidate_input_digest`："调用方从当前complete candidate冻结的input digest
    typed identity；不与历史anchor input digest做相等比较"
  - `candidate_input_cursor`："resolver允许读取的最大EventLog sequence；它不是
    token count"
- `_compatibility_mismatch`（`context_anchor.py:1080-1116`）不读取
  `candidate_input_digest` 或 `current_run_id`，未新增错误的历史相等
  predicate。

## 3. Reject 项未偷渡验证

### DS-03 overload/wrapper 扩展

**结论：未偷渡。** `build_context_sizing_result_from_atoms` 签名未变更。

### DS-04 sequence=0 fallback

**结论：未偷渡。** `_require_non_negative_int` 允许 0（`value < 0` 才拒绝），
但无 sequence=0 的特殊 fallback 逻辑。

### DS-05 损坏 link loose parsing

**结论：未偷渡。** `_build_scan_items` 中 link parse 失败时直接 append
`_Barrier(reason=ITERATION_LINK_INVALID)`（`context_anchor.py:554-559`），
未从 partial payload 提取 identity。

## 4. 初始实现回归检查

**结论：无回归。**

- `context_anchor.py` 是 untracked 新文件（Slice 3 新增），fix 变更仅限于：
  1. 删除 cursor 对 `MAX_CONTEXT_TOKEN_COUNT` 的依赖
  2. 更新 docstring
- resolver 核心逻辑（`resolve_context_anchor`、`_read_anchor_rows`、
  `_build_scan_items`、`_call_item`、`_compatibility_mismatch`）未被修改。
- 测试从 19 个（initial）增至 21 个（fix 新增 2 个 cursor owner tests），
  覆盖率从 82% 提升至 83%。

## 5. Allowlist 与边界确认

- fix 只修改了 `context_anchor.py`、`test_context_anchor.py` 和本 artifact。
- 其它 production 文件的 diff 来自 Slice 3 initial implementation，非 fix 引入。
- `docs/host/issues-implementation-control.md` 未被修改（Controller-owned dirty
  file，已排除）。

## 6. Verdict

**PASS**

CTRL-S3-IMPL-01 完整关闭：EventLog cursor 与 token ceiling 解耦、bool/negative
fail closed、window/usage/anchor token MAX 校验未丢、query docstring 澄清且未
新增错误历史相等 predicate。Reject 项（DS-03/04/05）未偷渡。初始实现无回归或
新 finding。

**Finding 数：0**

**Residual risk：**
- 与 initial review 相同的长 session keyset scan 性能风险、future parser
  exception audit 面未变化。
- `candidate_input_digest` 仍只作为 query identity 存在，未参与 compatibility
  判定（已由 docstring 澄清，符合 Controller 裁决 DS-01）。

**Artifact 路径：**
`docs/reviews/wu-ctx-01-slice-3-implementation-re-review-mimo.md`
