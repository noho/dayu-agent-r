# Code Review

## Scope

- Mode: current changes
- Branch: `phase/host-issues-control`
- Base: placement review 后 Controller 接受的测试补强项
- Output file: `docs/reviews/wu-cli-smoke-01-context-slot-placement-rereview-mimo.md`
- Included scope: `tests/runtime/test_scene_assets_migration.py` 新增测试
- Excluded scope: 生产逻辑（未改动）、scene files（已在 placement review 中验证）
- Parallel review coverage: 无

## Review Context

- DS placement review artifact: `docs/reviews/wu-cli-smoke-01-context-slot-placement-review-ds.md`
- MiMo placement review artifact: `docs/reviews/wu-cli-smoke-01-context-slot-placement-review-mimo.md`
- Fix artifact: `docs/reviews/wu-cli-smoke-01-context-slot-placement-fix-codex.md`

## Pre-review Validation

总控复验已通过，本次 review 独立验证：

```
tests/runtime/test_scene_assets_migration.py tests/runtime/test_scene_prepare.py:  51 passed
tests/service/test_entrypoint_runtime_prompt_path.py tests/cli/test_prompt_command.py:  41 passed
pyright:  0 errors
git diff --check:  passed
```

## 审查重点验证

### 1. 新测试是否覆盖 DS 提出的缺口：展开后 subject 块不插入到 scene H1 与执行契约正文之间

**Status: ✅ Verified**

**Evidence:**

1. **DS 提出的缺口**：
   - `docs/reviews/wu-cli-smoke-01-context-slot-placement-review-ds.md:215`: "invariant 测试未检查占位符展开后的实际 system prompt 结构：当前测试只验证 scene `.md` 文本中占位符的相对位置，未通过 `ScenePrepare` 展开后检查 system prompt 是否确实将 subject 块放在末尾且不打断执行契约。"

2. **新测试覆盖**：
   - `test_prepared_fins_default_subject_does_not_interrupt_scene_contract`（line 371-411）
   - 真实调用 `prepare_scene()` 展开占位符
   - 检查 `system_prompt` 中 `scene_title_index < first_contract_index < subject_title_index`
   - 验证 subject 块不在 scene H1 与执行契约正文之间

3. **测试逻辑验证**：
   - 运行时验证确认：`scene_title_index (4337) < first_contract_index (4349) < subject_title_index (4460)`
   - 对 prompt scene 额外验证：`prompt_output_index (4441) < subject_title_index (4460)`

**Conclusion:** 新测试覆盖了 DS 提出的缺口，通过真实 ScenePrepare 展开后验证 system_prompt 结构。

### 2. 是否遍历所有声明 fins_default_subject 的 scene，并保留 source placement invariant

**Status: ✅ Verified**

**Evidence:**

1. **遍历所有 manifests**：
   - `for path in _iter_manifest_paths()`: 遍历所有 manifest 文件
   - `if not _manifest_declares_context_slot(manifest, _FINS_DEFAULT_SUBJECT_SLOT): continue`: 只处理声明 `fins_default_subject` 的 scene

2. **保留 source placement invariant**：
   - `test_fins_default_subject_slot_is_rendered_by_declaring_scenes`（line 345-365）仍然存在
   - 验证 `placeholder_index > _first_contract_content_line_index(lines)`
   - 验证 `placeholder_index == _last_non_empty_line_index(lines)`

3. **新增测试补充**：
   - `test_prepared_fins_default_subject_does_not_interrupt_scene_contract` 在 source invariant 基础上
   - 增加了真实 ScenePrepare 展开后的验证

**Conclusion:** 测试遍历所有声明 `fins_default_subject` 的 scene，保留了 source placement invariant，并新增了展开后验证。

### 3. 测试是否过度脆弱或引入错误假设

**Status: ✅ Verified**

**Evidence:**

1. **不过度脆弱**：
   - 使用 `_FINS_DEFAULT_SUBJECT_TITLE = "# 当前分析对象"` 作为锚点
   - 使用 `_FINS_DEFAULT_SUBJECT_MARKDOWN` 作为测试输入
   - 不依赖特定行号，只验证相对位置关系

2. **不引入错误假设**：
   - 假设 scene H1 标题是 `lines[0]`：正确，所有 scene 都以 H1 标题开始
   - 假设 `_first_contract_content_line_index` 返回首个执行契约正文行：正确，辅助函数跳过空行、标题和占位符
   - 假设 `_FINS_DEFAULT_SUBJECT_TITLE` 在 system_prompt 中只出现一次：验证 `system_prompt.count(_FINS_DEFAULT_SUBJECT_TITLE) == 1`

3. **Fail-closed 设计**：
   - `_first_contract_content_line_index` 找不到正文时抛出 `AssertionError`
   - `_last_non_empty_line_index` 空文件时抛出 `AssertionError`
   - `system_prompt.index()` 找不到锚点时抛出 `ValueError`

**Conclusion:** 测试不过度脆弱，不引入错误假设，采用 fail-closed 设计。

### 4. 是否有新问题

**Status: ✅ Verified**

**Evidence:**

1. **测试全部通过**：
   - Runtime scene tests: 51 passed（新增 1 个测试）
   - Prompt path and CLI tests: 41 passed
   - pyright: 0 errors
   - git diff --check: passed

2. **无新增生产逻辑**：
   - 只修改了测试文件
   - 未改动 scene files、manifests 或生产代码

3. **无新增依赖**：
   - 测试使用已有的 `prepare_scene`、`ScenePrepareRequest` 等
   - 未引入新的测试工具或框架

**Conclusion:** 未发现新问题。

## New Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

无。新测试覆盖了 DS 提出的缺口，通过真实 ScenePrepare 展开后验证 system_prompt 结构，且不过度脆弱。

## Conclusion

**Pass**

所有审查重点均通过验证：

1. ✅ 新测试覆盖了 DS 提出的缺口：展开后 subject 块不插入到 scene H1 与执行契约正文之间
2. ✅ 测试遍历所有声明 `fins_default_subject` 的 scene，并保留 source placement invariant
3. ✅ 测试不过度脆弱，不引入错误假设
4. ✅ 未发现新问题

测试补强完成，可以进入下一步。

### Completion Report

- **Artifact path**: `docs/reviews/wu-cli-smoke-01-context-slot-placement-rereview-mimo.md`
- **Conclusion**: Pass
- **New blockers**: 0
- **Residual risks**: 无
