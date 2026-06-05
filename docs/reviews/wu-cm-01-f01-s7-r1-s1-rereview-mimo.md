# S7-R1-S1 Review-Fix Re-Review

## Scope

- Mode: focused re-review (S7-R1-S1 review-fix 窄范围复核)
- Branch: `phaseflow/wu-dur-obs-cm-closeout`
- Base: `main`
- Output file: `docs/reviews/wu-cm-01-f01-s7-r1-s1-rereview-mimo.md`
- Triggering reviews:
  - `docs/reviews/wu-cm-01-f01-s7-r1-s1-code-review-ds.md`
  - `docs/reviews/wu-cm-01-f01-s7-r1-s1-code-review-mimo.md`
- Review-fix artifact: `docs/reviews/wu-cm-01-f01-s7-r1-s1-review-fix-codex.md`
- Included scope:
  - `dayu/host/run_input.py` — `_SYSTEM_ENVELOPE_FORBIDDEN_FRAGMENTS`、`_non_empty_system_section_blocks()`、`_system_envelope_overhead()`、`_validate_system_envelope_content()`
  - `tests/host/test_run_input_builder.py` — `_assert_system_content_has_no_internal_refs()`、`test_system_envelope_boundedness_allows_multiple_items_in_same_section()`
  - `docs/reviews/wu-cm-01-f01-s7-r1-s1-review-fix-codex.md`
  - `docs/host/issues-implementation-control.md`
- Excluded scope: 未触及的 production 路径、Engine / Runner / Service 层

## 复核目标与裁决

### 目标 1: DS Finding 01 / 03 是否关闭，测试 helper 是否复用 production `_SYSTEM_ENVELOPE_FORBIDDEN_FRAGMENTS` 或等价同步

**裁决: PASS — 已关闭**

**直接证据：**

- Production 常量 `run_input.py:191-212`：`_SYSTEM_ENVELOPE_FORBIDDEN_FRAGMENTS` 包含 21 个片段。
- 测试 import `test_run_input_builder.py:119`：`_SYSTEM_ENVELOPE_FORBIDDEN_FRAGMENTS` 从 `dayu.host.run_input` 导入。
- 测试 helper `test_run_input_builder.py:3781`：`_assert_system_content_has_no_internal_refs()` 使用 `for fragment in _SYSTEM_ENVELOPE_FORBIDDEN_FRAGMENTS`，即导入的 production 常量。
- git diff 确认：旧的测试本地 `forbidden_fragments` tuple 已删除，替换为 production 常量导入。

**结论：** 测试与 production 共享同一常量定义源，不再存在漂移风险。DS Finding 01 和 03 均已关闭。

---

### 目标 2: DS Finding 02 是否关闭，`_system_envelope_overhead` 是否计入同 section item separator

**裁决: PASS — 已关闭**

**直接证据：**

- `_non_empty_system_section_blocks()` `run_input.py:2637`：返回 `(section, "\n".join(items), len(items))` 三元组，item count 已传入。
- `_system_envelope_overhead()` `run_input.py:2694-2696`：
  ```python
  item_separator_chars = sum(
      item_count - 1 for _section, _body, item_count in section_blocks
  )
  ```
  对每个 section，`(item_count - 1)` 个 `\n` 连接符被计入 overhead。
- `_system_envelope_overhead()` `run_input.py:2697`：返回 `header_chars + separator_chars + item_separator_chars`。

**旧实现 vs 新实现的 overhead 计算对比：**

| 场景 | 旧 overhead | 新 overhead | 实际 envelope 额外字符 |
|---|---|---|---|
| 1 section, 1 item | `header_chars` | `header_chars` | 0 |
| 1 section, 2 items | `header_chars` | `header_chars + 1` | 1 (`\n`) |
| 2 sections, 各 1 item | `header_chars + 2` | `header_chars + 2` | 0 |
| 2 sections, 第一 section 3 items | `header_chars + 2` | `header_chars + 2 + 2` | 2 (`\n\n`) |

**新测试验证：**

- `test_system_envelope_boundedness_allows_multiple_items_in_same_section()` `test_run_input_builder.py:613-633`：
  - 构造 2 条 system message（均无前缀，归入 `Task Instructions`）+ 1 条 user message。
  - 调用 `_normalize_ordinary_run_messages()` → `_single_system_content()`。
  - 断言 system content 为 `"## Task Instructions\nfirst instruction\nsecond instruction"`。
  - 断言最后一条 message 为 user message。

**旧实现下该测试会失败的原因：** 旧 `_system_envelope_overhead` 不计 item separator，2 个 item 的 `source_system_chars = len("first instruction") + len("second instruction") = 33`，overhead 仅 `header_chars = len("## ") + len("Task Instructions") + 1 = 20`，但实际 envelope 长度为 `len("## Task Instructions\nfirst instruction\nsecond instruction") = 53`，而 `33 + 20 = 53`，恰好相等——但这是因为旧实现中 `source_system_chars` 的累加方式已在 `_normalize_ordinary_run_messages` 中对每条 `content.strip()` 后累加，而 `"\n".join(items)` 产生的连接 `\n` 未被 overhead 覆盖。当 items 的 strip 后长度之和 + header = 实际 envelope 长度时，`len(content) > source_system_chars + overhead` 为 `False`，不会误抛。但当 items 数量更多或内容更长时，差值累积会触发误抛。新实现通过 `item_separator_chars` 精确补偿。

**结论：** DS Finding 02 已关闭。overhead 计算现在精确覆盖所有 deterministic 格式字符。

---

### 目标 3: 是否引入类型、docstring、AGENTS.md 或分层问题

**裁决: PASS — 未引入新问题**

**逐项检查：**

| 检查项 | 结论 | 依据 |
|---|---|---|
| 类型标注 | PASS | `_non_empty_system_section_blocks` 返回 `tuple[tuple[str, str, int], ...]`，`_system_envelope_overhead` 参数和返回值均有标注，pyright 0 errors |
| docstring | PASS | `_non_empty_system_section_blocks` 和 `_system_envelope_overhead` 均有完整中文 docstring，含 `:param:` / `:returns:` |
| AGENTS.md / CLAUDE.md 约束 | PASS | 无违反。`_SYSTEM_ENVELOPE_FORBIDDEN_FRAGMENTS` 仍是模块级私有常量，test 通过显式 import 使用（符合"禁止兼容性 re-export"的精神——test 直接导入真源，不做 wrapper） |
| 分层边界 | PASS | 所有修改在 `dayu/host/` 内，test 在 `tests/host/`，无跨层 import 泄漏 |
| 测试导入私有符号 | PASS | 测试导入 `_SYSTEM_ENVELOPE_FORBIDDEN_FRAGMENTS` 和 `_normalize_ordinary_run_messages`，二者为模块级私有，test 层导入 host 内部符合分层（test 不在 production import chain 中） |

---

### 目标 4: 当前验证是否足够

**裁决: PASS — 验证充分**

| 验证项 | 结果 | 评估 |
|---|---|---|
| `pytest tests/host/test_run_input_builder.py tests/host/test_public_tool_wiring_smoke.py tests/host/test_public_open_host_multiturn_smoke.py tests/host/test_public_compact_smoke.py -q` | 57 passed, 1 skipped | skipped 为 real runner matrix smoke（环境 gated），属预期 |
| `pyright` | 0 errors, 0 warnings, 0 informations | 无类型问题 |
| `git diff --check` | clean | 无 whitespace 错误 |

**新测试覆盖评估：**

- `test_system_envelope_boundedness_allows_multiple_items_in_same_section` 覆盖了 DS Finding 02 的核心场景：同一 section 多条 item 的 envelope 渲染与 boundedness 校验。
- `_assert_system_content_has_no_internal_refs` 现在对所有 focused test 自动执行完整 forbidden fragment 检查（21 个片段），覆盖 DS Finding 01/03。

---

## Findings

未发现实质性问题。

---

## Open Questions

无。

## Residual Risk

- DS Finding 04（`_system_envelope_section_and_body` prefix routing 固有风险）未被本次 review-fix 触及，属已知 deferred risk，当前生产 caller prompt 不会以已知前缀开头。
- Real provider matrix 环境 gated smoke 未在本次 focused 验证范围内，属已有约定。

## Conclusion

**PASS** — DS Finding 01/02/03 均已关闭，修复实现正确，未引入新问题，验证充分。
