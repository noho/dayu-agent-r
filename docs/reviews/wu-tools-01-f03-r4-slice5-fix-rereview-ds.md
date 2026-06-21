# Fix Re-Review — WU-TOOLS-01-F03-R4 Slice 5

## Scope

- Mode: fix re-review only（仅复查 AgentCodex 对已接受 MiMo F1/F2 的修复）
- Branch: `phase/wu-tools-01-f03-r4`
- Base: working tree post AgentCodex fix（含 Slice 5 原始改动 + fix 增量）
- Prior review artifacts:
  - `docs/reviews/wu-tools-01-f03-r4-slice5-code-review-mimo.md`（含 F1、F2 两项 accepted finding）
  - `docs/reviews/wu-tools-01-f03-r4-slice5-code-review-ds.md`（0 blocking findings，确认与 MiMo 一致）
- Fix artifact: `docs/reviews/wu-tools-01-f03-r4-slice5-fix-codex.md`
- Output file: `docs/reviews/wu-tools-01-f03-r4-slice5-fix-rereview-ds.md`
- Included scope:
  - `tests/fins/test_fins_storage_provider.py` — F1 negative assertion
  - `tests/tools/test_doc_tools_provider.py` — F2 partial limits fallback test
  - `docs/reviews/wu-tools-01-f03-r4-slice5-fix-codex.md` — fix claims 与 validation 报告
- Excluded scope:
  - Slice 6 docs/design
  - Slice 5 原始实现（已在 prior review 中通过）
  - 未修改的生产代码

## Verification Method

逐条对照 fix artifact 的三个 change claim 和 validation claim，读取对应代码位置确认实际改动与声称一致。随后做 adversarial 检查：新 assertion 是否真的覆盖了 finding 指出的回归路径、是否存在误报（false positive）、helper 实现是否正确、是否引入了与 prior review 结论冲突的新问题。

## Findings

### F1 Verification: `processor_cache_max_entries` negative assertion

- **位置**: `tests/fins/test_fins_storage_provider.py:1160-1163`
- **证据**:
  ```python
  for definition in definitions.values():
      truncate = definition.truncate
      assert isinstance(truncate, ToolTruncateSpec)
      assert "processor_cache_max_entries" not in truncate.limits
  ```
- **验证**:
  - 遍历 `definitions.values()` 即全部 9 个 Fins read tool definitions，不做抽样。
  - 对每个 definition 先用 `isinstance(truncate, ToolTruncateSpec)` 做类型守卫，再用 `not in` 做键集合 negative assertion。
  - 9 个可见 limit 的 positive assertion（lines 1151-1159）完全保留，无删减。
  - `processor_cache_max_entries=16` 仍在 config 中传入（line 1135），确保测试配置覆盖完整的 limits payload。
- **与 MiMo F1 要求对照**: MiMo F1 要求 "对每个工具的 `truncate.limits` 键集合断言不含 `processor_cache_max_entries`"。实现遍历全部 definitions 并逐条断言 `not in`，覆盖度超过 MiMo 建议（MiMo 允许只对任意一个工具断言键集合）。
- **结论**: ✅ F1 已关闭。

### F2 Verification: `test_doc_provider_partial_limits_fall_back_to_defaults`

- **位置**: `tests/tools/test_doc_tools_provider.py:1008-1040`
- **证据**:
  ```python
  defaults = doc_tools.DocToolLimits()
  # limits config 只传 list_files_max=99
  assert _parameter_maximum(definitions["list_files"], "limit") == 99
  assert _parameter_maximum(definitions["get_file_sections"], "limit") == defaults.get_sections_max
  assert _parameter_maximum(definitions["search_files"], "limit") == defaults.search_files_max_results
  assert _truncate_limit(definitions["read_file"], "max_chars") == defaults.read_file_max_chars
  assert _truncate_limit(definitions["read_file_section"], "max_chars") == defaults.read_file_section_max_chars
  ```
- **验证**:
  - 只传 `list_files_max=99`（line 1023），其余 4 个 limits 字段缺失。
  - 显式值 `99` 用字面量断言（line 1030）。
  - 4 个缺省字段全部通过 `defaults.<field>` 引用 dataclass 默认值断言（lines 1031-1040），覆盖 parameter schema maximum（2 个工具）和 truncate spec limit（2 个工具）。
  - `defaults` 从 `doc_tools.DocToolLimits()` 构造（line 1016），不是硬编码字面量，若默认值被意外修改测试仍能正确检测。
- **与 MiMo F2 要求对照**: MiMo F2 要求 "只传 `list_files_max=99`，断言 `list_files` parameter maximum 为 99 且其他工具使用 dataclass 默认值"。实现完全匹配，且额外覆盖了 truncate 层面的 fallback（`read_file`、`read_file_section`），超出 MiMo 最低要求。
- **结论**: ✅ F2 已关闭。

### No Production Code Changed by Fix

- **证据**: `git diff HEAD -- dayu/tools/doc_provider.py` 显示该文件改动为 Slice 5 原始 fail-fast 实现（`return ToolsDiscoveryProviderOutput(...)` → `raise ValueError(...)`、docstring 更新、`_EMPTY_ALLOWED_PATHS_ERROR` 常量），与 fix artifact 的 3 项 change claim 无交集。fix 只修改了两个测试文件。
- **结论**: ✅ 无生产代码被 fix 修改。

### Validation Sufficiency

- **Fix artifact 报告的验证**:
  - `pytest tests/tools/test_doc_tools_provider.py tests/fins/test_fins_storage_provider.py -q` → 57 passed, 3 warnings（warnings 来自 `edgar` 依赖既有 deprecation）
  - `pytest tests/runtime/test_config_loader.py tests/tools/test_combined_tools_acceptance.py -q` → 49 passed, 3 warnings
  - `pyright dayu tests utils` → 0 errors, 0 warnings, 0 informations
- **验证覆盖判断**: 57 passed 包含了新增的 2 个测试（F1 negative assertion loop 在已有测试函数内，F2 是独立新测试函数），以及全部既有测试无回归。ConfigLoader 和 combined acceptance 测试也通过，确认跨模块无破坏。pyright 清洁。
- **结论**: ✅ Validation 充分，覆盖了 fix 改动面和回归面。

## Open Questions

无。

## Residual Risk

- `processor_cache_max_entries` 对 Fins processor LRU cache 的实际行为影响仍需更重的 runtime cache 集成测试覆盖。当前保护层仅在 ToolDefinition 投影层面，不在 cache 驱逐行为层面。此风险已在 Slice 5 prior review 和 fix artifact 中一致声明，不属于 fix re-review 新发现。
- 两项新增测试 helpers（`_truncate_limit` 在 Fins 测试文件、`_parameter_maximum` / `_truncate_limit` 在 Doc 测试文件）与 Slice 5 原始改动中的 helper 实现完全一致，无重复实现分歧。

## Verdict

**F1 已关闭，F2 已关闭，通过。**

AgentCodex fix 完全按 MiMo F1/F2 要求实施：F1 在 `test_fins_provider_explicit_limits_shape_truncate_specs` 末尾增加了遍历全部 9 个 ToolDefinition 的 `processor_cache_max_entries not in truncate.limits` negative assertion，同时保留全部 9 个可见 limit positive assertion；F2 新增了 `test_doc_provider_partial_limits_fall_back_to_defaults`，证明了单项显式 limit 覆盖默认值、缺失字段回退到 `DocToolLimits()` 默认值的完整行为。无生产代码被修改，validation 充分（全部测试通过，pyright 清洁），无新引入问题。
