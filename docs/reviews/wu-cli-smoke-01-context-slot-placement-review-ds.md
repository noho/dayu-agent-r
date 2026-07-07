# Code Review

## Metadata

- **Reviewer**: AgentDS
- **Work unit**: WU-CLI-SMOKE-01 `{{fins_default_subject}}` scene placement fix
- **Review target**: workspace changes（用户确认的 placement 修复）
- **Fix artifact**: `docs/reviews/wu-cli-smoke-01-context-slot-placement-fix-codex.md`
- **Branch**: `phase/host-issues-control`
- **Review date**: 2026-07-07

## Scope

- **Mode**: current changes
- **Base**: S3 命名修复后的 workspace state
- **Output file**: `docs/reviews/wu-cli-smoke-01-context-slot-placement-review-ds.md`
- **Included scope**:
  - 11 个声明 `fins_default_subject` 的 scene `.md` 文件（audit / confirm / decision / fix / infer / overview / prompt / regenerate / repair / smoke_host_public_multiturn / write）
  - `tests/runtime/test_scene_assets_migration.py`（invariant 测试收紧）
- **Excluded scope**: interactive / wechat（未经修改，经 git diff 验证）、manifests（未经修改）、Host/Engine 内部模块、README
- **Parallel review coverage**: 无；单 reviewer 逐条走读

## Review Area 1: Root Cause 判断

### 动机分析

`{{fins_default_subject}}` 的展开产物是完整 Markdown 块：

```markdown
# 当前分析对象
你正在分析的是 V（Visa Inc.）。
```

该块自带 H1 标题（`# 当前分析对象`）。在修复前，占位符位于 scene `.md` 的 H1 标题之后、执行契约正文之前（典型位置：第 3 行）。展开后 LLM 实际看到的 system prompt 结构为：

```markdown
# 审计执行契约

# 当前分析对象
你正在分析的是 V（Visa Inc.）。

## 任务目标
- 基于正文与"证据与出处"文本，输出疑似违规清单。
...
```

问题：`# 当前分析对象` H1 标题被插入到 scene 执行契约标题（`# 审计执行契约`）与执行契约正文（`## 任务目标`）之间，打断了 LLM-facing 契约的结构层级。模型会将 `# 当前分析对象` 视为一个新的顶级 section 开始，而 `## 任务目标` 则变成其子节——这改变了 scene 设计者对执行契约信息架构的意图。

### 根因判定

**Root cause 成立。** 问题出在占位符展开形态（完整 Markdown 块含 H1）与占位符位置（H1 标题正下方）的组合。二者同源：占位符的文本定义在 `dayu/service/scene_context.py:fins_default_subject()`，占位符的位置定义在各 scene `.md` 文件中。修复选择调整位置（将占位符移到 scene 末尾）而非改变展开形态，理由成立——`# 当前分析对象` 作为补充性上下文放在执行契约之后比插入到结构中间更合理。

## Review Area 2: 11 个 Scene 占位符位置

### 逐文件验证

全部 11 个声明 `fins_default_subject` 的 scene 均将占位符从 H1 后（原第 3 行）移动到 scene 末尾（最后一个非空行）：

| Scene | 旧位置 | 新位置 | 前置分隔空行 | Final newline |
|---|---|---|---|---|
| audit.md | H1 后第 3 行 | `## 执行方式` 内容之后 | ✅（1 空行） | ✅ |
| confirm.md | H1 后第 3 行 | `## 执行方式` 内容之后 | ✅（1 空行） | ✅ |
| decision.md | H1 后第 3 行 | `## 输出要求` 内容之后 | ✅（1 空行） | ✅ |
| fix.md | H1 后第 3 行 | 执行契约内容之后 | ✅（1 空行） | ✅ |
| infer.md | H1 后第 3 行 | `## 执行方式` 内容之后 | ✅（1 空行） | ✅ |
| overview.md | H1 后第 3 行 | 执行契约内容之后 | ✅（1 空行） | ✅ |
| prompt.md | H1 后第 3 行 | bullet list 内容之后 | ✅（1 空行） | ✅ |
| regenerate.md | H1 后第 3 行 | 执行契约内容之后 | ✅（1 空行） | ✅ |
| repair.md | H1 后第 3 行 | `## 执行方式` 内容之后 | ✅（1 空行） | ✅ |
| smoke_host_public_multiturn.md | H1 后第 3 行 | bullet list 内容之后 | ✅（1 空行） | ✅ |
| write.md | H1 后第 3 行 | 执行契约内容之后 | ✅（1 空行） | ✅ |

每个文件的 tail -3 输出确认为：
```
[最后一条执行契约正文]

{{fins_default_subject}}
```

### interactive / wechat 未被误改

`git diff -- dayu/config/prompts/scenes/interactive.md dayu/config/prompts/scenes/wechat.md dayu/config/prompts/manifests/interactive.json dayu/config/prompts/manifests/wechat.json` 零输出。未增加 manifest slot，未增加 scene placeholder。

**结论：通过。** 11 个 scene 全部正确移动，interactive/wechat 未受影响。

## Review Area 3: Invariant 测试审查

### 测试变更

旧 invariant（S3 初始版）：
```python
assert placeholder_lines, scene  # 至少一个占位符
assert all(line == _FINS_DEFAULT_SUBJECT_PLACEHOLDER for line in placeholder_lines), scene  # 全部独立行
```

新 invariant：
```python
assert len(placeholder_indexes) == 1, scene                          # 恰好一个占位符
placeholder_index = placeholder_indexes[0]
assert lines[placeholder_index] == _FINS_DEFAULT_SUBJECT_PLACEHOLDER, scene  # 必须是独立行
assert placeholder_index > _first_contract_content_line_index(lines), scene   # 必须在执行契约正文之后
assert placeholder_index == _last_non_empty_line_index(lines), scene          # 必须是最后一个非空行
```

新增三条约束和三个辅助函数：

| 新增约束 | 防御的回归 | 辅助函数 |
|---|---|---|
| 恰好一个占位符 | 多处重复注入 | `_placeholder_line_indexes` |
| 在执行契约正文之后 | 占位符漂回 H1 后 | `_first_contract_content_line_index` |
| 是最后一个非空行 | 占位符漂回 H1 后 + 后续内容插入 | `_last_non_empty_line_index` |

### 辅助函数正确性

**`_first_contract_content_line_index`**：跳过空行、`#` 起始行（Markdown 标题）、占位符自身，返回首个非上述类别的行号。对 11 个 scene 均正确定位到第一条执行契约正文（对 prompt.md 是 `- 你当前处于单轮问答任务。`，对有 `## 任务目标` 的 scene 是该标题行之后的首条正文）。

**`_last_non_empty_line_index`**：从末尾向前扫描，返回首个非空行号。正确处理末尾空行（`splitlines()` 对 `\n` 结尾的字符串不产生尾随空串，对 `\n\n` 结尾产生一个空串——函数跳过空串找到占位符）。

**`_placeholder_line_indexes`**：返回所有包含占位符子串的行号，用于后续 `len(...) == 1` 校验。

### 脆弱性评估

| 风险 | 评估 |
|---|---|
| `placeholder_index == _last_non_empty_line_index` 阻止未来在占位符后追加内容 | **设计取舍，非缺陷**。fix artifact 明确声明："若未来确需在主体上下文之后追加新契约文本，应先重新裁决 LLM-facing 顺序"。该约束在当前设计下正确，移除成本低 |
| `_first_contract_content_line_index` 将 `#` 起始行全部视为标题跳过 | **合理**。scene `.md` 文件为纯 Markdown，`#` 起始行即各级标题。无代码注释或其它 `#` 用法 |
| `len(placeholder_indexes) == 1` 阻止同一 scene 多处渲染 subject | **正确收紧**。同一 scene 多次注入同一 subject 块对 LLM 无益且混乱 |
| interactive/wechat 排除逻辑未变 | `_NO_DEFAULT_SUBJECT_SCENES` 仍为 `frozenset({"interactive", "wechat"})`，双重校验（不声明 + 不渲染）未变 |

**结论：通过。** Invariant 测试能有效防止占位符回到 H1 后，收紧合理，不过度脆弱。

## Review Area 4: README 不更新判断

fix artifact 判断："只调整已有 prompt asset 的 placement 和已有 migration invariant，没有改变 `dayu/config/` 的目录职责、manifest schema、ScenePrepare API、CLI 用户流程或测试分层边界。"

逐项核验：

| README | 更新触发条件 | 是否命中 | 判断 |
|---|---|---|---|
| `dayu/config/README.md` | config 目录职责变化、manifest schema 变化、ScenePrepare API 变化 | 均未命中：占位符行号是 scene `.md` 内部排版细节，README 不记录行号 | 不更新 ✅ |
| `tests/README.md` | 测试覆盖事实变化 | scene asset migration 覆盖区域已在 S3 README 中记录，本次仅收紧已有 invariant 的断言精度，未新增覆盖类别 | 不更新 ✅ |
| 根 `README.md` | 用户可见行为变化 | 占位符位置变化不影响 CLI 行为、输出格式或用户工作流 | 不更新 ✅ |

**结论：通过。** README 不更新的判断成立。

## Review Area 5: Final Newline / LLM-facing 文本结构 / 空 Slot 回归风险

### Final newline

全部 11 个 scene 的末尾均为 `{{fins_default_subject}}\n`（`tail -3` 输出证实最后一行后无多余空行）。编辑器打开文件末尾有且仅有一个换行符，符合 POSIX 惯例。

### LLM-facing 文本结构

修复后的 system prompt 结构变为：

```markdown
# 审计执行契约

## 任务目标
[执行契约正文...]

## 执行方式
[执行契约正文...]

# 当前分析对象
你正在分析的是 V（Visa Inc.）。
```

执行契约正文保持完整，补充性 subject 上下文位于末尾。ScenePrepare 的 `{{fins_default_subject}}` → slot value 替换不会引入格式异常。

**潜在边缘情况**：prompt.md 是唯一使用 bullet list 而非 `##` 标题的 scene。修复后占位符位于 bullet list 之后：

```markdown
# 单轮问答执行契约

- 你当前处于单轮问答任务。
- 本轮回答应直接服务当前问题...
- 输出 Markdown 格式。

{{fins_default_subject}}
```

展开后 subject H1 位于 bullet list 之后——不会插入到 bullet list 中间打断列表结构。✅

### 空 slot 回归风险

当 `fins_default_subject` 为空字符串（无 ticker 场景）时，`{{fins_default_subject}}` 展开为空字符串。scene 末尾变为 `[最后一条正文]\n\n`（占位符位置变为空行）。

- **不会引入额外可见内容**：空字符串不产生 "未指定具体公司" 或其它占位文本 ✅
- **不会产生异常空行**：scene 末尾会多一个空行（占位符所在行变为空行），对 LLM 输入无实质影响 ✅
- **不会打断执行契约**：占位符在末尾，空展开不会插入到契约正文之间 ✅

**结论：通过。** 无 final newline、LLM-facing 文本结构或空 slot 回归风险。

## Adversarial Failure Pass

| 攻击面 | 验证 | 结果 |
|---|---|---|
| 占位符回到 H1 后（未来回归） | invariant `placeholder_index > _first_contract_content_line_index` 阻止 | ✅ |
| 占位符移到中间而非末尾（未来回归） | invariant `placeholder_index == _last_non_empty_line_index` 阻止 | ✅ |
| 同一 scene 多处渲染 subject | invariant `len(placeholder_indexes) == 1` 阻止 | ✅ |
| 声明 slot 但未渲染（contract gap） | invariant `len(placeholder_indexes) == 1` 在 declares_subject 为 True 时强制至少一个 | ✅ |
| interactive/wechat 被误加 slot | invariant `_NO_DEFAULT_SUBJECT_SCENES` 双重校验 | ✅ |
| 空 subject 产生异常文本 | `fins_default_subject(None)` → `""`，ScenePrepare 替换为空 | ✅ |
| `_first_contract_content_line_index` 找不到正文 | 抛出 `AssertionError("scene fragment 缺少执行契约正文")` — fail-closed | ✅ |
| `_last_non_empty_line_index` 空文件 | 抛出 `AssertionError("scene fragment 为空")` — fail-closed | ✅ |

## Open Questions

无。

## Residual Risk

1. **`placeholder_index == _last_non_empty_line_index` 的严格约束**：若未来需要在 subject 块之后追加内容（如 scene-specific footer、disclaimer），需先更新 invariant。fix artifact 已将此记录为已知设计取舍，不视为缺陷。
2. **invariant 测试未检查占位符展开后的实际 system prompt 结构**：当前测试只验证 scene `.md` 文本中占位符的相对位置，未通过 `ScenePrepare` 展开后检查 system prompt 是否确实将 subject 块放在末尾且不打断执行契约。现有 `test_all_migrated_scene_assets_prepare_successfully` 验证 ScenePrepare 能成功装配，但仅检查 `system_prompt` 非空和结构字段存在，不检查 subject 块在 system_prompt 中的相对位置。

## Findings

未发现实质性问题。

Root cause 成立，11 个 scene 全部正确移动占位符，invariant 测试有效收紧且不过度脆弱，README 不更新的判断成立，无 final newline、LLM-facing 文本结构或空 slot 回归风险。

## Conclusion

**Pass** — 0 findings。`{{fins_default_subject}}` scene placement 修复验证通过。

### Completion Report

- **Artifact path**: `docs/reviews/wu-cli-smoke-01-context-slot-placement-review-ds.md`
- **Conclusion**: Pass
- **Blocking findings**: 0
- **Nonblocking findings**: 0
- **Residual risks**: 2（`_last_non_empty_line_index` 严格约束为已知设计取舍、invariant 未验证展开后 system prompt 结构）
