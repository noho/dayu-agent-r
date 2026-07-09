# WU-CLI-SMOKE-01 Plan Re-Review #2 (RF-01 Targeted) — AgentDS

## Review Metadata

- **Reviewer**: AgentDS (targeted plan re-review, RF-01 follow-up only)
- **Timestamp**: 20260707-153416 CST
- **Fixed plan**: `docs/host/wu-cli-smoke-01-context-slot-fmp-scene-filter-plan.md`
- **Fix artifact**: `docs/reviews/wu-cli-smoke-01-context-slot-fmp-scene-filter-plan-fix-codex.md`
- **Prior rereviews**:
  - `docs/reviews/wu-cli-smoke-01-context-slot-fmp-scene-filter-plan-rereview-ds.md`
  - `docs/reviews/wu-cli-smoke-01-context-slot-fmp-scene-filter-plan-rereview-mimo.md`
- **Scope**: 只验证 RF-01 Controller 裁决是否在 fixed plan 中正确落地；不实现、不改代码、不 commit、不 push、不创建 issue/PR。

## Controller RF-01 Decision (Recap)

| 决策点 | Controller 裁决 |
|--------|----------------|
| `selected_tags` 语义 | 基于实际选中工具的 catalog tags，**不**使用 manifest-only `tool_tags_any` |
| 防护手段 | prompt asset discipline + 测试：`base/tools.md` 不得有混合用途 broad `<when_tag fins>` block；prepared prompt output 不得向 prompt scene 泄露 download/preprocess/upload 指引 |

## RF-01 修复验证

按 Controller 四个决策点逐项验证：

### 决策点 1：`<when_tag TAG>` 基于实际选中工具的 catalog tags

- **Plan line 41-42**：明确 `<when_tag TAG>` 语义基于实际选中工具及其 catalog tags；显式工具名选中时，该工具携带的 tags 也应让对应 `<when_tag>` block 生效。
- **Plan line 73-75**：`selected_tags` 遍历 `catalog.tools`，用 selected tool names 构建；`mode=all` / 显式工具名等非 tag-selection 路径选中的工具也必须贡献自身 catalog tags。
- **Plan line 80**：`<when_tag TAG>` 匹配规则为 `TAG` 在 selected tools 聚合出的 `selected_tags` 中。
- ✅ **已正确落地**。

### 决策点 2：不使用 manifest-only `tool_tags_any` 语义

- **Plan line 75**：显式写"`selected_tags` 不得只取 manifest `tool_tags_any`"。
- ✅ **已正确落地**。

### 决策点 3：prompt asset discipline — 无 broad `<when_tag fins>` block

- **Plan lines 89-91**：read-only 财报指引用 `<when_tag fins-read>` 包裹；长事务指引用 `<when_tag ingestion>` 或精确 `<when_tool start_fins_download>` / `<when_tool start_fins_preprocess>` 包裹；不使用 `<when_tag fins>` 包住混合 read+ingestion 的大段说明；S1 应移除 `base/tools.md` 中混合用途 broad `<when_tag fins>` block。
- **Plan line 250**：asset migration 测试应检查 `base/tools.md` 不再存在混合 read 与 ingestion 语义的 broad `<when_tag fins>` block。
- ✅ **已正确落地**。

### 决策点 4：prepared output 不泄露 download/preprocess/upload 指引

- **Plan lines 247-249**：prepared prompt output 不得因为 read-only 工具携带 broad `fins` tag 而泄露 download/preprocess/upload 等长事务指引。
- **Plan line 252**：所有 prepared prompt 不包含 `<when_tag` / `<when_tool` / closing marker。
- ✅ **已正确落地**。

## 新观察（不构成 RF-01 Blocker）

### OBS-01：`ingestion` tag 不存在于任何工具，`<when_tag ingestion>` 需额外处理

- **位置**: Plan line 91 推荐 `<when_tag ingestion>` 作为长事务指引包裹方案之一；`base/tools.md` line 67 已有 `<when_tag ingestion>` block。
- **代码事实**: 经 grep 确认，当前所有 fins 工具的 tags 均不含 `ingestion`：
  - read tools: `("fins", "fins-read")`
  - download tools: `("fins", "fins-download")`
  - preprocess tools: `("fins", "fins-preprocess")`
  - upload tools: `("fins", "fins-upload")`
- **影响**: 若 implementation agent 选用 `<when_tag ingestion>` 而不给 download/preprocess 工具新增 `ingestion` tag，则该 block 在 S1 实施条件块过滤后将**永不渲染**——包括 interactive/wechat 场景。等同于 download/preprocess 指引在所有场景中被静默删除。
- **缓解**: Plan 同时给出 `<when_tool start_fins_download>` / `<when_tool start_fins_preprocess>` 精确包裹方案，该方案无需新增 tag，可直接工作。测试（interactive/wechat 场景应包含 download/preprocess 指引）也会在实施阶段捕获此问题。
- **建议**: Implementation agent 应优先使用 `<when_tool>` 精确包裹方案；若选用 `<when_tag ingestion>`，必须在 plan 或 implementation artifact 中明确要求为 download/preprocess 工具新增 `ingestion` tag。
- **严重程度**: 低 — 有可用替代方案，测试会捕获。

## Conclusion

**pass**

RF-01 Controller 裁决的四个决策点均在 fixed plan 中正确落地，无未解决项。发现一个与 `ingestion` tag 相关的低风险观察（OBS-01），不阻塞 RF-01，不影响实施启动。

## Completion Report

- **Artifact path**: `docs/reviews/wu-cli-smoke-01-context-slot-fmp-scene-filter-plan-rereview2-ds.md`
- **Conclusion**: **pass**
- **RF-01 status**: 已修复 — Controller 四个决策点全部正确落地
- **Blockers**: 0
- **New observations**: 1（OBS-01，低风险，不阻塞）
