# WU-CLI-SMOKE-01 S1 Code Review — AgentDS

## Metadata

- Gate: deepreview (S1 implementation)
- Work unit: WU-CLI-SMOKE-01 context slot / FMP / scene tool filtering follow-up
- Slice: S1
- Reviewer: AgentDS
- Date: 2026-07-07
- Review artifact: `docs/reviews/wu-cli-smoke-01-context-slot-fmp-scene-filter-s1-code-review-ds.md`

## Scope

- Mode: current changes
- Branch: phase/host-issues-control
- Base: 8015049c (plan checkpoint)
- Plan: `docs/host/wu-cli-smoke-01-context-slot-fmp-scene-filter-plan.md`
- Controller adjudication: `docs/reviews/wu-cli-smoke-01-context-slot-fmp-scene-filter-plan-controller-adjudication.md`
- Implementation artifact: `docs/reviews/wu-cli-smoke-01-context-slot-fmp-scene-filter-s1-implementation-codex.md`
- Included scope: all diff files (7 production/test files)
- Excluded scope: 无
- Parallel review coverage: 无

## Review Method

沿 `ScenePrepare.prepare()` → `_filter_condition_blocks()` → `_condition_is_selected()` → `_selected_tool_names()` / `_selected_tool_tags()` 主链路逐行走读，展开入参、条件分支、下游调用、返回值、副作用。随后做 adversarial failure pass：覆盖 malformed/mismatched/nested/empty-name/multi-param marker 场景，all/none/select 三种 mode 下的 selected tools/tags 语义，以及 prompt vs interactive/wechat 暴露面差异。最后检查测试覆盖边界、架构边界和 AGENTS.md 约束。

## Findings

### 01-未修复-低-plan 设计段空 fragment 丢弃与空行归一未在 S1 实现

- **入口/函数**: `ScenePrepare.prepare()` → `system_prompt` 拼接
- **文件(行号)**: `dayu/runtime/scene_prepare.py:519`
- **输入场景**: 条件块过滤后某个 fragment 内容变为空字符串，或 fragment 内出现连续空行。
- **实际分支**: `system_prompt="\n\n".join(rendered_messages)` — 所有 fragment（含空 fragment）参与拼接，不做 `strip()` 后空内容丢弃，不做连续空行压缩。
- **预期行为**: 按 plan 设计段 execution order：步骤 4 "丢弃内容经 `strip()` 后为空的 fragment"；步骤 6 "对最终 `system_prompt` 做空行归一：3 个及以上连续空行压缩为 2 个换行"。
- **实际行为**: 空 fragment 仍参与 join，可能在 `system_prompt` 中产生多余空行。
- **直接证据**: `scene_prepare.py:519` — `"\n\n".join(rendered_messages)` 无空 fragment 过滤，无空行归一。`scene_prepare.py:482-495` — comprehension 未调用 `strip()` 检查。
- **影响**: 当前 prompt assets 不触发此问题（`tools.md` 在条件块之外仍有全局规则文本，不会整体为空）。但若后续 fragment 全部由条件块组成且全部未命中，会产生多余空行。属于 plan 设计意图与 S1 实现之间的已知 scope gap。
- **建议改法和验证点**: 在 S2 或 S3 中补齐步骤 3-6。验证点：构造全部条件块未命中的 fragment，断言其不参与 `system_prompt` join；构造 3 个连续空行场景，断言压缩为 2 个。
- **修复风险（低）**: 纯文本后处理，不影响现有行为。
- **严重程度（低）**: 当前 assets 不触发，属于已知的后续 slice 工作项。implementation artifact 已记录此 deviation。

## Open Questions

无。

## Residual Risk

- **空 fragment 丢弃与空行归一未实现**：见 Finding 01。当前 assets 不触发，但后续新增 prompt fragment 时可能暴露。
- **空 slot 行清理（plan 步骤 3）未实现**：plan 设计段要求 "原始行去掉前后空白后完全匹配 `{{slot_name}}` 且替换值为 `""` 时删除整行"。此逻辑未在 S1 中实现，当前 `fins_default_subject` 变空时可能留下空白行。但 S1 scope 不包含此改动，留待后续 slice。
- **条件块嵌套不在 scope 内**：plan 与 controller adjudication 明确 "条件块不支持嵌套"，当前实现 fail closed 处理嵌套。未来如需嵌套支持需重新设计 parser。
- **`_CONDITION_MARKER_START_PATTERN` 扫描全 fragment 内容**：regex 在 fragment 全文做 `.search()`，包括 condition block body。若 body 中出现字面 `<when_tool` 或 `<when_tag` 子串（如 prompt asset 作者在 body 中解释 marker 语法），会被解析器误判为 marker 并 fail closed。这是 regex-based 解析的固有权衡；当前 prompt assets 不包含此类文本，但建议在 `dayu/config/README.md` 中说明条件块 body 不得包含 raw marker 字面量。风险低，不构成 finding。
- **真实 LLM prompt 检查未覆盖**：S1 依赖 prepared prompt 文本断言，未运行真实 LLM 调用验证最终 prompt 效果。留待 S3 smoke 验证。
- **upload 暴露面未扩大**：符合 plan 非目标，但 `start_fins_upload` 工具仍存在于系统中。若后续有人在 interactive/wechat manifest 中添加 `fins-upload` tag，upload 指引会随 `<when_tag fins-upload>`（如果存在）或直接选中而暴露。当前 `tools.md` 不含 upload 条件块，风险可控。

## Architecture Boundary

- `dayu/runtime/scene_prepare.py` 新增代码不 import `dayu.fins` / `dayu.service` / `dayu.host` / `dayu.engine` / `dayu.ui`。✅
- `_filter_condition_blocks` 只消费 `str`、`frozenset[str]`、`frozenset[str]`，不穿透到业务层。✅
- `_selected_tool_tags` 遍历 `catalog.tools` 聚合 tags，不新增 `SceneToolCatalog` public API。✅
- `_selected_tool_names` 处理 `tool_names=None`（mode=all）的语义，正确返回 `catalog.names()`。✅

## AGENTS.md 约束检查

- 中文 docstring：所有新增函数均有完整中文 docstring，含参数、返回值、异常说明。✅
- 无 `Any`/`object`：所有新签名使用具体类型（`str`、`frozenset[str]`、`bool`）。✅
- 无 `hasattr`/`getattr` 逃逸。✅
- 无兼容性 shim。✅
- 模块间依赖最小化：新增 `_filter_condition_blocks` 及相关辅助函数均为模块级私有函数，不暴露到 `__all__`。✅

## Completion Report

- **Artifact path**: `docs/reviews/wu-cli-smoke-01-context-slot-fmp-scene-filter-s1-code-review-ds.md`
- **Conclusion**: **pass** — 无阻塞性 finding
- **Blocking findings**: 0
- **Non-blocking findings**: 1（plan 设计段空 fragment 丢弃与空行归一未在 S1 实现，属于已知 scope gap）
- **Residual risks**: 5 项（见 Residual Risk 节）

### 验证摘要

| 检查项 | 结果 |
|---|---|
| 条件块过滤正确性（tool/tag 命中/未命中） | ✅ |
| mode=all/none/select 下 selected tools/tags 语义 | ✅ |
| malformed/mismatched/nested/empty-name/multi-param marker fail closed | ✅ |
| prompt 不暴露 download/preprocess/upload 指引 | ✅ |
| interactive/wechat 暴露 download/preprocess 指引 | ✅ |
| prepared output 不含 marker | ✅ |
| 架构边界 | ✅ |
| AGENTS.md 约束 | ✅ |
| pytest (58 + 6 passed) | ✅ |
| pyright (0 errors) | ✅ |
| git diff --check | ✅ |
