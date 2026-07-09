# Code Review

## Scope

- Mode: current changes
- Branch: `phase/host-issues-control`
- Base: S3 code review 通过后的 workspace changes（`{{fins_default_subject}}` scene placement 修复）
- Output file: `docs/reviews/wu-cli-smoke-01-context-slot-placement-review-mimo.md`
- Included scope: 11 个 scene files 和 1 个 test file 的 placement 调整
- Excluded scope: interactive/wechat scenes（未被改动）、manifests（未被改动）、CLI/Service 代码（未被改动）
- Parallel review coverage: 无

## Review Context

- Fix artifact: `docs/reviews/wu-cli-smoke-01-context-slot-placement-fix-codex.md`

## Pre-review Validation

总控复验已通过，本次 review 独立验证：

```
tests/runtime/test_scene_assets_migration.py tests/runtime/test_scene_prepare.py:  50 passed
tests/service/test_entrypoint_runtime_prompt_path.py tests/cli/test_prompt_command.py:  41 passed
pyright:  0 errors
git diff --check:  passed
```

## 审查重点验证

### 1. Root cause 是否成立：slot 展开为完整 Markdown 块，把它放在 H1 后会打断 scene 执行契约结构

**Status: ✅ Verified**

**Evidence:**

1. **slot 展开形态**：
   - `dayu/service/scene_context.py:75`: `return f"# 当前分析对象\n你正在分析的是 {normalized_ticker}。"`
   - `dayu/service/scene_context.py:76`: `return f"# 当前分析对象\n你正在分析的是 {normalized_ticker}（{normalized_company_name}）。"
   - 展开后包含 H1 标题 `# 当前分析对象`

2. **旧 placement 的问题**：
   - 旧 `prompt.md` 结构：
     ```
     # 单轮问答执行契约
     {{fins_default_subject}}
     - 你当前处于单轮问答任务。
     ...
     ```
   - 展开后：
     ```
     # 单轮问答执行契约
     # 当前分析对象
     你正在分析的是 V（Visa Inc.）。
     - 你当前处于单轮问答任务。
     ...
     ```
   - 两个 H1 标题相邻，打断了 scene 执行契约结构

3. **新 placement 的正确性**：
   - 新 `prompt.md` 结构：
     ```
     # 单轮问答执行契约
     - 你当前处于单轮问答任务。
     ...
     - 输出 Markdown 格式。
     {{fins_default_subject}}
     ```
   - 展开后：
     ```
     # 单轮问答执行契约
     - 你当前处于单轮问答任务。
     ...
     - 输出 Markdown 格式。
     # 当前分析对象
     你正在分析的是 V（Visa Inc.）。
     ```
   - 执行契约正文完整，subject 信息在最后

4. **运行时验证**：
   - ScenePrepare 测试确认展开后 subject 在 line 150-151
   - Contract content ends around line 148（`- 输出 Markdown 格式。`）
   - Subject is after contract: True

**Conclusion:** Root cause 成立。slot 展开为完整 Markdown 块（含 H1 标题），放在 H1 后会打断 scene 执行契约结构。

### 2. 11 个声明 fins_default_subject 的 scene 是否都把占位符移到主要执行契约正文之后，且 interactive/wechat 未被误改

**Status: ✅ Verified**

**Evidence:**

1. **11 个 scene 已修改**：
   - `audit.md`: 占位符移到 `## 执行方式` 之后
   - `confirm.md`: 占位符移到 `## 执行方式` 之后
   - `decision.md`: 占位符移到 `## 输出要求` 之后
   - `fix.md`: 占位符移到执行方式之后
   - `infer.md`: 占位符移到 `## 执行方式` 之后
   - `overview.md`: 占位符移到执行方式之后
   - `prompt.md`: 占位符移到 `- 输出 Markdown 格式。` 之后
   - `regenerate.md`: 占位符移到执行方式之后
   - `repair.md`: 占位符移到 `## 执行方式` 之后
   - `smoke_host_public_multiturn.md`: 占位符移到 `- 输出 Markdown 格式。` 之后
   - `write.md`: 占位符移到执行方式之后

2. **所有 scene 的占位符都是最后一个非空内容行**：
   - `tail -3` 验证所有 scene 都以 `{{fins_default_subject}}` 后跟空行结束

3. **interactive/wechat 未被误改**：
   - `git diff dayu/config/prompts/scenes/interactive.md dayu/config/prompts/scenes/wechat.md` 返回空
   - 这两个 scene 不声明 `fins_default_subject`，不需要占位符

**Conclusion:** 11 个 scene 都正确地把占位符移到主要执行契约正文之后，interactive/wechat 未被误改。

### 3. tests/runtime/test_scene_assets_migration.py 的 invariant 是否能防止占位符回到 H1 后，同时是否过度脆弱/过度约束

**Status: ✅ Verified**

**Evidence:**

1. **Invariant 设计**：
   - `len(placeholder_indexes) == 1`：只有一个占位符（防止重复）
   - `lines[placeholder_index] == _FINS_DEFAULT_SUBJECT_PLACEHOLDER`：占位符是独立行（防止内联）
   - `placeholder_index > _first_contract_content_line_index(lines)`：占位符在执行契约正文之后（防止回到 H1 后）
   - `placeholder_index == _last_non_empty_line_index(lines)`：占位符是最后一个非空内容行（防止回归）

2. **防止回到 H1 后**：
   - `_first_contract_content_line_index` 跳过空行、Markdown 标题和占位符
   - 返回第一个非空、非标题、非占位符的行号
   - 要求 `placeholder_index > _first_contract_content_line_index(lines)`，确保占位符在正文之后

3. **不过度脆弱/过度约束**：
   - 允许占位符后有空行（final newline）
   - 不要求占位符在特定行号
   - 不要求特定的正文内容
   - 只要求占位符在正文之后且是最后一个非空内容行

4. **测试覆盖**：
   - 测试遍历所有 manifests，验证每个声明 `fins_default_subject` 的 scene 都满足 invariant
   - 测试验证 `_NO_DEFAULT_SUBJECT_SCENES` 中的 scene 不声明不渲染

**Conclusion:** Invariant 能有效防止占位符回到 H1 后，同时不过度脆弱/过度约束。

### 4. README 不更新的判断是否成立

**Status: ✅ Verified**

**Evidence:**

1. **改动范围**：
   - 只调整了 11 个 prompt asset 的 placement
   - 没有改变目录职责、manifest schema、ScenePrepare API、CLI 用户流程或测试分层边界

2. **README 职责**：
   - `dayu/config/README.md`: 说明配置层级、目录结构和 manifest schema
   - `tests/README.md`: 记录测试分层、运行方式与维护约定
   - 本次改动不涉及这些内容

3. **不更新的合理性**：
   - Placement 是 prompt asset 的内部结构调整
   - 不影响外部接口或用户可见行为
   - 不需要更新文档

**Conclusion:** README 不更新的判断成立。

### 5. 是否存在 final newline、LLM-facing 文本结构、空 slot 行清理相关回归风险

**Status: ✅ Verified**

**Evidence:**

1. **Final newline**：
   - 所有 11 个 scene 都以 `{{fins_default_subject}}` 后跟空行结束
   - 这确保了 final newline 存在

2. **LLM-facing 文本结构**：
   - ScenePrepare 测试确认展开后 subject 在执行契约正文之后
   - System prompt 结构正确，不影响 LLM 理解

3. **空 slot 行清理**：
   - ScenePrepare 的空 slot 行清理逻辑未改变
   - 如果 `fins_default_subject` 为空，占位符行会被清理
   - 测试覆盖了空 subject 的场景

4. **回归风险**：
   - 测试 50 passed，覆盖了所有 scene 的 placement
   - 测试 41 passed，覆盖了 prompt path 和 CLI 行为
   - pyright 0 errors，类型检查通过

**Conclusion:** 不存在 final newline、LLM-facing 文本结构、空 slot 行清理相关回归风险。

## New Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

1. **Placement invariant 的未来演进**：当前 invariant 要求占位符是最后一个非空内容行，若未来确需在主体上下文之后追加新契约文本，应先重新裁决 LLM-facing 顺序。这是有意收紧的设计选择，不是 bug。

## Conclusion

**Pass**

所有审查重点均通过验证：

1. ✅ Root cause 成立：slot 展开为完整 Markdown 块，放在 H1 后会打断 scene 执行契约结构
2. ✅ 11 个 scene 都把占位符移到主要执行契约正文之后，interactive/wechat 未被误改
3. ✅ Invariant 能防止占位符回到 H1 后，同时不过度脆弱/过度约束
4. ✅ README 不更新的判断成立
5. ✅ 不存在 final newline、LLM-facing 文本结构、空 slot 行清理相关回归风险

修复正确且完整，可以进入下一步。

### Completion Report

- **Artifact path**: `docs/reviews/wu-cli-smoke-01-context-slot-placement-review-mimo.md`
- **Conclusion**: Pass
- **New blockers**: 0
- **Residual risks**: 1（placement invariant 的未来演进，已记录为有意设计选择）
