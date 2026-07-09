# Code Re-Review (Placement Residual Fix Verification)

## Metadata

- **Reviewer**: AgentDS（targeted re-review）
- **Work unit**: WU-CLI-SMOKE-01 `{{fins_default_subject}}` scene placement fix
- **Review target**: workspace changes（placement review residual 修复）
- **Original placement review**: `docs/reviews/wu-cli-smoke-01-context-slot-placement-review-ds.md`
- **Accepted residual**: invariant 未检查展开后 system prompt 结构
- **Branch**: `phase/host-issues-control`
- **Review date**: 2026-07-07

## Scope

- **Mode**: current changes（targeted re-review）
- **Base**: placement fix 后的 workspace state
- **Output file**: `docs/reviews/wu-cli-smoke-01-context-slot-placement-rereview-ds.md`
- **Included scope**: `tests/runtime/test_scene_assets_migration.py`（新增 `test_prepared_fins_default_subject_does_not_interrupt_scene_contract` 测试）
- **Excluded scope**: 11 个 scene `.md` 文件（未改）、生产代码（未改）、README（未改）
- **Parallel review coverage**: 无；单 reviewer 逐条走读

## Accepted Residual: Fix Verification

### Residual: invariant 未检查展开后 system prompt 结构

**Status: ✅ 已关闭**

新增测试 `test_prepared_fins_default_subject_does_not_interrupt_scene_contract`（`test_scene_assets_migration.py:371-411`），验证真实 ScenePrepare 展开后 subject 块不插入到 scene H1 与执行契约正文之间。

#### 测试结构

```
遍历所有 manifest
  → 跳过不声明 fins_default_subject 的 scene
  → 读取 scene fragment 文件
  → 提取 scene_title（H1 首行）
  → 提取 first_contract_line（首个执行契约正文行）
  → 用完整 Markdown 块覆盖 fins_default_subject slot 值
  → 调用 prepare_scene() — 真实 ScenePrepare 展开
  → 在 system_prompt 中定位三个关键位置：
      scene_title_index    — scene H1 标题
      first_contract_index — 首个执行契约正文行
      subject_title_index  — "# 当前分析对象"（subject 块 H1）
  → 验证排序：scene_title < first_contract < subject_title
  → 验证 subject 块恰好出现一次（title + body 各一次）
  → prompt scene 专项：最后一个 bullet 在 subject 块之前
```

#### 关闭 residual 的证据

原 residual 描述："invariant 测试未检查展开后的实际 system prompt 结构"。新测试通过以下断言直接关闭：

| 断言 | 验证内容 | 类型 |
|---|---|---|
| `scene_title_index < first_contract_index < subject_title_index` | subject 块在契约正文之后，不在 H1 与正文之间 | **核心 ordering** |
| `system_prompt.count(_FINS_DEFAULT_SUBJECT_TITLE) == 1` | subject H1 恰好出现一次（未重复注入） | 完整性 |
| `system_prompt.count("你正在分析的是 V（Visa Inc.）。") == 1` | subject 正文恰好出现一次 | 完整性 |
| `prompt_output_index < subject_title_index`（仅 prompt） | bullet-list 场景最后一条契约正文仍在 subject 之前 | 场景特化 |

关键断言 `scene_title_index < first_contract_index < subject_title_index` 直接证明：在真实 ScenePrepare 展开后，scene H1 标题最先出现 → 执行契约正文紧随其后 → subject 块位于末尾。subject 块没有插入到 H1 与契约正文之间。

#### 覆盖范围

- **遍历所有声明 scene**：通过 `_iter_manifest_paths()` + `_manifest_declares_context_slot` 过滤，对全部 11 个声明 `fins_default_subject` 的 scene 执行 ✓
- **使用真实 ScenePrepare**：调用 `prepare_scene(ScenePrepareRequest(...))`，非 mock ✓
- **使用真实 slot 展开值**：注入完整 Markdown 块 `"# 当前分析对象\n你正在分析的是 V（Visa Inc.）。"`，非占位测试字符串 ✓
- **保留 source placement invariant**：`test_fins_default_subject_slot_is_rendered_by_declaring_scenes`（源文件占位符位置 invariant）未修改，新测试为附加层 ✓

#### 脆弱性评估

| 潜在脆弱点 | 评估 | 风险 |
|---|---|---|
| `_FINS_DEFAULT_SUBJECT_MARKDOWN` 硬编码 subject 文本 | 该文本是 `fins_default_subject()` 的确定论输出；格式变更属于设计变更，常量集中定义，更新成本低 | 低 |
| `_PROMPT_OUTPUT_CONTRACT_LINE = "- 输出 Markdown 格式。"` | prompt.md 最后一条 bullet 的精确文本；若 prompt.md 编辑修改该行，`system_prompt.index(...)` 抛出 `ValueError`，测试清晰失败 | 低 |
| `system_prompt.index(first_contract_line, scene_title_index)` 依赖 `first_contract_line` 在 system_prompt 中唯一 | `index` 从 `scene_title_index` 开始搜索，找到第一个匹配；即使 `first_contract_line` 在 system prompt 中多次出现（如通用短语），找到的第一个即为契约正文起始位置，不影响 ordering 断言 | 无 |
| `system_prompt.index(_FINS_DEFAULT_SUBJECT_TITLE, scene_title_index)` 与 scene H1 同名冲突 | 所有 scene H1 标题均为 scene-specific（如"审计执行契约"），无一为"当前分析对象"；且 `count == 1` 作为双重保险 | 无 |
| `_required_context_slot_values` 返回可变 dict | 每次调用创建新 dict（`values: dict[str, str] = {}`），测试间无污染 | 无 |

**未发现过度脆弱或错误假设。**

#### 新问题检查

- **生产代码变更**：零。diff 仅含 `test_scene_assets_migration.py` 新增测试和 11 个 scene `.md` placement（已在 placement review 中通过）。✓
- **测试隔离**：`_required_context_slot_values` 每次返回新 dict，覆写 slot 值不影响其他测试。✓
- **无副作用**：`prepare_scene` 为纯函数，不写文件、不修改全局状态。✓
- **interactive/wechat 正确排除**：`if not _manifest_declares_context_slot(...): continue` 跳过不声明 subject 的 scene。✓

## Validation

```
tests/runtime/test_scene_assets_migration.py + test_scene_prepare.py:  51 passed (placement fix 50 + 新增 1)
tests/service/test_entrypoint_runtime_prompt_path.py:                   (subset of 41 passed)
tests/cli/test_prompt_command.py:                                       (subset of 41 passed)
pyright:                                                                0 errors, 0 warnings
git diff --check:                                                      passed
```

## Findings

未发现实质性问题。

原 placement review 的 residual "invariant 未检查展开后 system prompt 结构" 已通过 `test_prepared_fins_default_subject_does_not_interrupt_scene_contract` 关闭。新测试使用真实 ScenePrepare 展开、遍历全部 11 个声明 scene、保留 source placement invariant、无过度脆弱或错误假设、无新问题引入。

## Open Questions

无。

## Residual Risk

1. **Prompt 场景特化断言依赖硬编码 bullet 文本**（`_PROMPT_OUTPUT_CONTRACT_LINE`）：若 prompt.md 编辑修改最后一条 bullet，测试通过 `ValueError` 清晰失败而非静默通过，属于 fail-loud。不视为缺陷，但值得在 prompt.md 修改 checklist 中记录。

## Conclusion

**Pass** — 0 findings。Placement review residual 已关闭。

### Completion Report

- **Artifact path**: `docs/reviews/wu-cli-smoke-01-context-slot-placement-rereview-ds.md`
- **Conclusion**: Pass
- **Residual closed**: 1/1（invariant 未检查展开后 system prompt 结构 → `test_prepared_fins_default_subject_does_not_interrupt_scene_contract`）
- **New blockers**: 0
- **New residual risks**: 1（prompt 场景特化断言依赖硬编码 bullet 文本，fail-loud 非静默）
