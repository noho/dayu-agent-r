# Plan Re-Review 2: WU-CLI-SMOKE-01 — RF-01 Follow-up Verification

## Re-Review Metadata

- **Reviewer**: AgentMiMo
- **Timestamp**: 20260707-153246
- **Fixed plan artifact**: `docs/host/wu-cli-smoke-01-context-slot-fmp-scene-filter-plan.md`
- **Fix artifact**: `docs/reviews/wu-cli-smoke-01-context-slot-fmp-scene-filter-plan-fix-codex.md`
- **Prior rereview**: `docs/reviews/wu-cli-smoke-01-context-slot-fmp-scene-filter-plan-rereview-mimo.md`
- **Scope**: targeted re-review，只验证 RF-01 follow-up

## Controller RF-01 Decision

1. keep `<when_tag TAG>` semantics based on actual selected tools and their catalog tags;
2. do not use manifest-only `tool_tags_any` semantics;
3. safeguard is prompt asset discipline and tests: no broad mixed-purpose `<when_tag fins>` block for read+ingestion, and prepared prompt output must not leak download/preprocess/upload guidance into prompt scene.

## RF-01 修复验证

### 检查项 1：`<when_tag TAG>` 语义基于实际选中工具的 catalog tags

**Plan 当前写法**：

- Line 41: "`<when_tag TAG>` 的语义基于实际选中工具的 catalog tags，并且必须保留这种语义"
- Line 74-75: "用 selected tool names 以及对应工具的 catalog tags 构建 `selected_tags: frozenset[str]`... 显式工具名选择、`mode=all` 或其它非 tag-selection 路径选中的工具，也必须贡献自身 catalog tags"
- Line 82: "`<when_tag TAG>`：仅当 `TAG` 在 selected tools 按 catalog tags 聚合出的 `selected_tags` 中保留 block body；不要从 manifest `tool_tags_any` 单独派生该集合"

**验证结果**：✅ 语义明确。Plan 坚持 `selected_tags` 来自 selected tools 的 catalog tags 并集，不要求 manifest-only 语义。与 controller decision #1 一致。

### 检查项 2：不使用 manifest-only `tool_tags_any` 语义

**Plan 当前写法**：

- Line 75: "`selected_tags` 不得只取 manifest `tool_tags_any`"
- Line 82: "不要从 manifest `tool_tags_any` 单独派生该集合"
- Fix artifact line 45: "plan 现在明确 `<when_tag TAG>` 仍基于实际选中工具及其 catalog tags。`selected_tags` 不得只从 manifest `tool_tags_any` 派生"

**验证结果**：✅ 明确拒绝 manifest-only 语义。与 controller decision #2 一致。

### 检查项 3a：prompt scene 无 broad mixed-purpose `<when_tag fins>` block

**Plan 当前写法**：

- Line 89-92: "read-only 财报工具指引用 `<when_tag fins-read>` 包裹。长事务摄取指引用 `<when_tag ingestion>` 或更精确的 `<when_tool start_fins_download>` / `<when_tool start_fins_preprocess>` 包裹。不使用 `<when_tag fins>` 包住同时覆盖 read 与 ingestion 的大段说明；当前 S1 应移除 `base/tools.md` 中混合 read 与 ingestion 语义的 broad `<when_tag fins>` block"
- Line 249-250: "asset migration 测试应检查 `base/tools.md` 不再存在混合 read 与 ingestion 语义的 broad `<when_tag fins>` block"

**验证结果**：✅ `base/tools.md` 要求拆分 broad `<when_tag fins>` 为 `<when_tag fins-read>` 和 `<when_tag ingestion>`/`<when_tool>`。与 controller decision #3 前半句一致。

**语义推演**：prompt scene 的 `selected_tags` 包含 `{"fins", "fins-read", "web", "utils", ...}`（因为 read-only 工具携带 `("fins", "fins-read")` tags）。拆分后 `tools.md` 不再有 `<when_tag fins>` block，只有 `<when_tag fins-read>` 和 `<when_tag ingestion>`。prompt scene 的 `selected_tags` 包含 `fins-read` 但不包含 `ingestion`，因此 read 指引保留、ingestion 指引过滤。即使未来有人误加 `<when_tag fins>` block，prompt scene 的 `selected_tags` 包含 `fins` 会匹配它——但 asset migration 测试会阻止这种 broad block 进入 `tools.md`，构成双重防护。✅

### 检查项 3b：prepared prompt output 不泄露 download/preprocess/upload 指引

**Plan 当前写法**：

- Line 249: "prepared prompt output 不得因为 read-only 工具携带 broad `fins` tag 而泄露 download/preprocess/upload 等长事务指引"
- Line 252: "所有 prepared prompt 不包含 `<when_tag` / `<when_tool` / closing marker"
- Fix artifact line 46: "测试必须断言 prepared prompt output 不向 prompt scene 泄露 download/preprocess/upload 指引"

**验证结果**：✅ 测试要求覆盖 prepared output 的内容隔离。与 controller decision #3 后半句一致。

### 检查项 4：Fix artifact RF-01 记录与 Plan 一致性

**Fix artifact 当前写法**（line 44-47）：

- Controller decision: "作为 plan clarification 接受，但不采纳 RF-01 建议的 manifest-only `selected_tags` 语义"
- Resolution: "plan 现在明确 `<when_tag TAG>` 仍基于实际选中工具及其 catalog tags"
- Safeguard: "plan 现在把 RF-01 防护点放在 prompt asset discipline 与测试上"

**验证结果**：✅ Fix artifact 正确记录了 controller decision 和 resolution，与 Plan 修改一致。

## Residual Risk 确认

RF-01 的 residual risk 是：若未来有人在 `tools.md` 新增 `<when_tag fins>` block，prompt scene 的 `selected_tags`（包含 `fins`）会匹配它。防护措施：

1. asset migration 测试检查 `tools.md` 不再有 broad `<when_tag fins>` block — Plan line 249-250 ✅
2. prompt scene 的 prepared output 测试断言不含 download/preprocess/upload 指引 — Plan line 249 ✅
3. `<when_tag fins>` 不出现在 `tools.md` 中（Plan 要求拆分）— Plan line 89-92 ✅

三重防护到位，residual risk 可接受。

## Conclusion

**pass**

RF-01 已在 fixed plan 中正确修复。Plan 坚持 `<when_tag TAG>` 语义基于实际选中工具的 catalog tags（controller decision #1），明确拒绝 manifest-only 语义（controller decision #2），并通过 prompt asset 拆分和测试断言确保 broad `<when_tag fins>` block 不进入 `tools.md` 且 prepared prompt output 不泄露长事务指引（controller decision #3）。Fix artifact 记录与 Plan 修改一致。无 blocker。

## Completion Report

- **Artifact path**: `docs/reviews/wu-cli-smoke-01-context-slot-fmp-scene-filter-plan-rereview2-mimo.md`
- **Conclusion**: pass
- **RF-01 status**: 已修复，三个 controller decision 检查项全部通过
- **Blockers**: 0
- **Residual risks**: RF-01 的三重防护到位，residual risk 可接受
