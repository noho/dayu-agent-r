# Code Review — S7-R1-S1 Review-Fix Re-review

## Scope

- Mode: current changes（窄范围复核）
- Branch: `phaseflow/wu-dur-obs-cm-closeout`
- Base: `main`
- Output file: `docs/reviews/wu-cm-01-f01-s7-r1-s1-rereview-ds.md`
- Triggering review-fix artifact: `docs/reviews/wu-cm-01-f01-s7-r1-s1-review-fix-codex.md`
- Primary reviews: `docs/reviews/wu-cm-01-f01-s7-r1-s1-code-review-ds.md`, `docs/reviews/wu-cm-01-f01-s7-r1-s1-code-review-mimo.md`
- Included scope（仅 review-fix 变更）:
  - `dayu/host/run_input.py` — `_non_empty_system_section_blocks` item count 传递、`_system_envelope_overhead` item separator 计入、`_SYSTEM_ENVELOPE_FORBIDDEN_FRAGMENTS` 作为公开可导入常量
  - `tests/host/test_run_input_builder.py` — `_assert_system_content_has_no_internal_refs` 复用 production 常量、新增 `test_system_envelope_boundedness_allows_multiple_items_in_same_section`
  - `docs/reviews/wu-cm-01-f01-s7-r1-s1-review-fix-codex.md` — review-fix 记录
  - `docs/host/issues-implementation-control.md` — 控制文档同步
- Excluded scope: 其余历史 diff、compactor proposal 路径、Engine/Runner/Service 层
- Parallel review coverage: 无（单 reviewer 走读 review-fix 变更与验证数据）

## 复核目标

| # | 复核项 | 裁决 |
|---|--------|------|
| Q1 | DS Finding 01/03：test helper 是否复用 production `_SYSTEM_ENVELOPE_FORBIDDEN_FRAGMENTS` 或等价同步 | **CLOSED** |
| Q2 | DS Finding 02：`_system_envelope_overhead` 是否计入同 section item separator，新测试是否在旧实现下失败、新实现下通过 | **CLOSED** |
| Q3 | 是否引入类型、docstring、CLAUDE.md 或分层问题 | **未发现问题** |
| Q4 | 当前 focused 验证 57 passed 1 skipped、pyright 0、diff check clean 是否足够 | **足够** |

## Findings

### Q1: DS Finding 01/03 复核

**入口/文件**: `tests/host/test_run_input_builder.py`

**证据链:**

1. Test 从 production 导入 `_SYSTEM_ENVELOPE_FORBIDDEN_FRAGMENTS`：
   - `tests/host/test_run_input_builder.py:119` — `_SYSTEM_ENVELOPE_FORBIDDEN_FRAGMENTS` 出现在 import 列表中，来源为 `dayu.host.run_input`
2. `_assert_system_content_has_no_internal_refs` 使用导入的 production 常量：
   - `tests/host/test_run_input_builder.py:3781` — `for fragment in _SYSTEM_ENVELOPE_FORBIDDEN_FRAGMENTS:`
3. Production 禁止片段列表包含 21 个片段（`dayu/host/run_input.py:191-212`），test 不再维护独立副本，直接遍历同一常量
4. `_single_system_content` 在每个 focused 测试的 system content 读取路径中自动调用 `_assert_system_content_has_no_internal_refs`（line 3769），确保所有通过 `_single_system_content` 读取 system envelope 的测试都覆盖完整的 21 项禁止片段

**裁决**: Finding 01 和 Finding 03 同步关闭。test 不再维护独立于 production 的 forbidden fragment 列表，消除了 test 与 production 之间的置信度鸿沟。

### Q2: DS Finding 02 复核

**入口/文件**: `dayu/host/run_input.py:2680-2697` (`_system_envelope_overhead`), `tests/host/test_run_input_builder.py:613-632`

**证据链:**

1. Production overhead 计算已包含同 section item separator:
   - `dayu/host/run_input.py:2694-2696`:
     ```python
     item_separator_chars = sum(
         item_count - 1 for _section, _body, item_count in section_blocks
     )
     ```
   - 每个 section 内 `len(items) - 1` 个 `\n`（对应 `_non_empty_system_section_blocks` line 2637 的 `"\n".join(items)`）
2. `_non_empty_system_section_blocks` 传递 item count:
   - `dayu/host/run_input.py:2637` — `blocks.append((section, "\n".join(items), len(items)))`
3. 新测试 `test_system_envelope_boundedness_allows_multiple_items_in_same_section`:
   - `tests/host/test_run_input_builder.py:613-632`
   - 构造两条无前缀 system message（均落入 `Task Instructions` section），一条 user message
   - 断言 system envelope 内容为 `## Task Instructions\nfirst instruction\nsecond instruction`
   - 断言 user message 原样保留

**旧实现下失败验证（手工计算）**:
- `source_system_chars = 17 + 18 = 35`
- `content_len = 57`（`"## Task Instructions\nfirst instruction\nsecond instruction"`）
- 旧 overhead（无 item separator）= `header_chars = 21` → `source + old_overhead = 56`
- 旧校验: `57 > 56` → `True` → 抛出 `HostDurableError`

**新实现下通过验证**:
- `header_chars = 21`（`len("## ") + len("Task Instructions") + 1`）
- `item_separator_chars = 2 - 1 = 1`
- `overhead = 21 + 0 + 1 = 22` → `source + overhead = 57`
- 新校验: `57 > 57` → `False` → 通过，无异常

**裁决**: Finding 02 关闭。`_system_envelope_overhead` 正确计入同 section item separator 开销；新测试在旧实现下会触发 `HostDurableError`，在新实现下通过。

### Q3: 类型 / docstring / CLAUDE.md / 分层复核

**入口/文件**: `dayu/host/run_input.py` 与 `tests/host/test_run_input_builder.py` 的 review-fix 变更区域

**逐项检查**:

| 检查项 | 文件(行号) | 裁决 |
|--------|-----------|------|
| 所有新函数有中文 docstring | `run_input.py:2490-2495` `_normalize_ordinary_run_messages`, `run_input.py:2534-2539` `_system_envelope_section_and_body`, `run_input.py:2605-2614` `_stripped_prefixed_system_body`, `run_input.py:2623-2629` `_non_empty_system_section_blocks`, `run_input.py:2641-2645` `_render_system_envelope`, `run_input.py:2655-2667` `_validate_system_envelope_content`, `run_input.py:2680-2684` `_system_envelope_overhead`, `run_input.py:2700-2705` `_raise_unsupported_agent_message`, `run_input.py:2762-2768` `_recent_evidence_content`, `run_input.py:2771-2781` `_accepted_tool_evidence_content`; test: `test_run_input_builder.py:3756-3761` `_single_system_content`, `test_run_input_builder.py:3773-3778` `_assert_system_content_has_no_internal_refs` | PASS — 全部中文 docstring，含参数/返回值/异常 |
| 所有函数/方法有完整类型注解 | 同上所有函数签名 | PASS — 无 `Any`、无 `object`、无缺类型参数 |
| `_raise_unsupported_agent_message` 参数类型 `NoReturn` | `run_input.py:2700` `message: NoReturn` | PASS — `NoReturn` 是 Python 类型系统的 bottom type，在 exhaustive type narrowing 后调用点（line 2518）的实参类型为 `Never`，类型检查器接受此签名。运行时函数收到的是实际 `AgentMessage` 实例，`.getattr` 调用安全 |
| 分层边界 | 所有新函数均在 `dayu/host/run_input.py`（Host 层），属于 ordinary RunInput contract 的正常扩展 | PASS — 无跨层穿透、无反向依赖 |
| Test 导入私有 production 常量 | `test_run_input_builder.py:119` 导入 `_SYSTEM_ENVELOPE_FORBIDDEN_FRAGMENTS` | PASS — 该常量既是 production 的 forbidden contract 也是 test 需要验证的 contract，test 导入以消除维护漂移是合理选择 |
| CLAUDE.md 编码硬约束 | 无 `Any`/`object`/缺类型、无魔法数字、无 God function、无兼容性代码 | PASS |

**裁决**: 未发现类型、docstring、CLAUDE.md 或分层问题。

### Q4: 验证数据复核

**当前验证结果**:
- `pytest` focused suite: **57 passed, 1 skipped** in 5.97s
  - 含新增 `test_system_envelope_boundedness_allows_multiple_items_in_same_section`（计入 57）
  - 唯一 skipped: `test_public_compact_smoke.py::test_real_compactor_public_opener_compacts_and_preserves_continuity` — 该测试在 review-fix 前已 skip（environment-gated），非本次变更引入
- `pyright`: **0 errors, 0 warnings, 0 informations**
- `git diff --check`: **clean**（no whitespace errors）

**边界分析**:
- Focused test 覆盖了单 section 双 item 场景（Q2 的 targeted regression test）
- `_single_system_content` 确保所有 focused tests 自动执行 forbidden fragment 检查（Q1 的 defense-in-depth）
- 跳过测试为 `test_public_compact_smoke.py` 中的 environment-gated 测试，与 review-fix 变更无关
- 无新增 skipped 测试

**裁决**: 当前验证足够。review-fix 变更在 focused tests 中有针对性覆盖，pyright 和 diff check 均清洁。

## Open Questions

无。

## Residual Risk

- **已记录但未在本次修复中关闭**: DS Finding 04（prefix-based section routing 的 future-proofing 风险）未被接受为当前 blocker。当前所有 material source 使用模块级常量前缀，冲突概率极低。该风险已在 DS code review 中记录为 deferred。
- **Environment-gated**: `test_real_compactor_public_opener_compacts_and_preserves_continuity` 仍 skip，对应 real provider matrix 验证不在本轮 deterministic shape slice 范围内。

## Conclusion

**PASS**

S7-R1-S1 review-fix 正确关闭了 DS Finding 01（test forbidden fragments 同步）、DS Finding 03（禁止列表维护漂移）和 DS Finding 02（同 section item separator overhead）。未引入类型、docstring、CLAUDE.md 或分层问题。当前 focused 验证 57 passed 1 skipped、pyright 0 errors、diff check clean 足以支持本窄范围复核结论。
