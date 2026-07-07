# Plan Re-Review: WU-CLI-SMOKE-01 Context Slot / FMP / Scene Tool Filtering

## Re-Review Metadata

- **Reviewer**: AgentMiMo
- **Timestamp**: 20260707-152246
- **Fixed plan artifact**: `docs/host/wu-cli-smoke-01-context-slot-fmp-scene-filter-plan.md`
- **Fix artifact**: `docs/reviews/wu-cli-smoke-01-context-slot-fmp-scene-filter-plan-fix-codex.md`
- **Prior review**: `docs/reviews/plan-review-20260707-151057.md`
- **DS review**: `docs/reviews/wu-cli-smoke-01-context-slot-fmp-scene-filter-plan-review-ds.md`
- **Controller adjudication**: Accepted MiMo F01-F07, accepted DS-F02-F06 + utils/time + FMP timeout; rejected DS-F01 as written

## Re-Review Scope

验证所有 accepted findings 是否已在 fixed plan 中正确修复，并识别剩余 blocker。

## Accepted Findings 修复验证

| # | Finding | 修复验证 | 结论 |
|---|---------|---------|------|
| MiMo F01 | `<when_tag fins>` 粒度不足 | Plan line 89-90 要求拆分为 `<when_tag fins-read>` 与 `<when_tag ingestion>` 或精确 `<when_tool>` | ⚠️ 有新发现，见 RF-01 |
| MiMo F02 | checkpoint 2a61fbfd 状态不同步 | Plan line 25-26 明确 `prompt.json` 已无 `fins-download`/`fins-preprocess`；不存在字面 `fins-upload`；只验证不删除 | ✅ 已修复 |
| MiMo F03 | `base_user` 范围低估 | Plan line 29 量化为 12 manifests + 3 CLI + tests + utils smoke；line 329 列出全部 12 个 manifest 文件名；line 296/344 要求 `rg -n "base_user"` 零残留 | ✅ 已修复 |
| MiMo F04 | `selected_tags` 实现路径缺失 | Plan line 73 指定"遍历 `catalog.tools`，用 selected tool names 构建 `selected_tags: frozenset[str]`" | ⚠️ 有新发现，见 RF-01 |
| MiMo F05 | `EntrypointContextSlotRequest` 字段未定义 | Plan line 125-128 定义 4 个字段：`ticker`、`now`、`fmp_api_key`、`fmp_timeout_seconds` | ✅ 已修复 |
| MiMo F06 | 空 slot 行清理规格不足 | Plan line 97-113 定义精确规则、执行顺序、边界 case 和测试覆盖要求 | ✅ 已修复 |
| MiMo F07 | prepared output marker 测试缺口 | Plan line 232-233 明确"测试从 raw marker 存在迁移/补充为 prepared output 不含 marker" | ✅ 已修复 |
| DS-F02 | 空 slot 行清理两种机制交互 | 已合并到 MiMo F06 修复中，Plan line 97-113 统一定义 | ✅ 已修复 |
| DS-F03 | `current_time` 格式未指定 | Plan line 138-139 指定格式：`# 当前时间\n现在是 2026年7月7日 15:08（Asia/Shanghai，星期二）。` | ✅ 已修复 |
| DS-F04 | FMP env var 名称未指定 | Plan line 143 明确 `FMP_API_KEY`；line 144 要求公共常量或已有常量 | ✅ 已修复 |
| DS-F05 | 模块名二选一未收敛 | Plan line 118 收敛为 `dayu.service.scene_context` | ✅ 已修复 |
| DS-F06 | `tuple` 类型变更未说明理由 | Plan line 161 说明"OLD 的 `list[str]` 改为 `tuple[str, ...]`，原因是新 public contract 应为不可变输出" | ✅ 已修复 |
| DS utils/time | `utils/time` tag 语义 | Plan line 27 明确 `utils/time` 不是 manifest 字面 tag；工具实际 tags 是 `utils` 和 `time` | ✅ 已修复 |
| DS FMP timeout | FMP 超时精度 | Plan line 128/146 指定 `fmp_timeout_seconds: float`，Service path 默认 ≤ 5 秒 | ✅ 已修复 |

## 新发现

### RF-01-未修复-中-`selected_tags` 计算路径未指定，导致 `<when_tag>` 过滤语义存在歧义

- **位置**: Plan "Scene 条件块过滤" line 73; "过滤规则" line 80-81; `base/tools.md` line 39-65
- **问题类型**: 契约缺失
- **当前写法**: Plan line 73 指定"在过滤函数内部遍历 `catalog.tools`，用 selected tool names 构建 `selected_tags: frozenset[str]`"。line 80-81 定义 `<when_tag TAG>` 过滤规则为"仅当 `TAG` 在 selected tools 聚合出的 `selected_tags` 中保留 block body"。
- **反例/失败场景**: 代码事实：
  - `fins_tools.py:53`: read-only 工具 tags = `("fins", "fins-read")` — 同时携带 `fins` 和 `fins-read`
  - `download_tools.py:179`: download 工具 tags = `("fins", "fins-download")`
  - `preprocess_tools.py:177`: preprocess 工具 tags = `("fins", "fins-preprocess")`
  - `prompt.json` 的 `tool_tags_any` = `["fins-read", "web", "utils"]`

  若 `selected_tags` = 所有 selected tools 的 tags 并集，则 prompt scene 的 `selected_tags` = `{"fins", "fins-read", "web", "utils", ...}`。此时：
  1. Plan 要求将 `<when_tag fins>` 重命名为 `<when_tag fins-read>`。重命名后 `<when_tag fins-read>` 可被正确匹配（因为 `fins-read` ∈ `selected_tags`）。
  2. 但 `fins` ∈ `selected_tags`，若未来有人在 `tools.md` 新增 `<when_tag fins>` block，该 block 也会被 prompt scene 匹配，破坏 read/ingestion 隔离。
  3. `mode=all` 时 `selected_tags` 为全量 catalog tags 并集，包含 `fins-download`、`fins-preprocess`、`fins-upload`、`ingestion` 等，所有条件块都会被保留。

  Plan 的实现路径描述（line 73）只说了"遍历 `catalog.tools` 构建 `selected_tags`"，但未明确是取 `tool_tags_any`（manifest 声明的标签选择条件）还是取 selected tools 的全量 tags 并集。两种实现导致不同的过滤语义。
- **为什么有问题**: `<when_tag>` 的设计意图是"本 scene 选中的标签类别对应的指引才保留"。若 `selected_tags` 包含 selected tools 的全量 tags，则 `<when_tag>` 退化为"本 scene 选中的工具所属的任何标签类别对应的指引都保留"，语义更宽，无法精确隔离。Plan 的 F01 修复（重命名 marker）只有在 `selected_tags` = `tool_tags_any` 时才完全解决问题。
- **直接证据**:
  - `dayu/fins/tools/fins_tools.py:53`: `FINS_TOOL_TAGS = ("fins", "fins-read")`
  - `dayu/fins/tools/download_tools.py:179`: `tags=("fins", "fins-download")`
  - Plan line 73: "用 selected tool names 构建 `selected_tags`" — 未定义构建语义
  - Plan line 80: "`<when_tag TAG>`：仅当 `TAG` 在 selected tools 聚合出的 `selected_tags` 中" — 未定义"聚合"语义
- **影响**: 实施 Agent 可能采用"全量 tags 并集"实现，导致 `mode=all` 场景下所有条件块都被保留，或未来新增 `<when_tag fins>` block 时被 prompt scene 意外匹配。
- **建议改法和验证点**:
  1. Plan 应明确 `selected_tags` 的计算语义。推荐方案：`selected_tags` 取 `tool_tags_any`（manifest 声明的标签选择条件），不取 selected tools 的全量 tags 并集。理由：`<when_tag>` 的语义是"本 scene 声明关注的标签类别"，与 `tool_tags_any` 对齐。
  2. 若采用此方案，`<when_tag fins>` 重命名为 `<when_tag fins-read>` 后，prompt scene 的 `selected_tags` = `{"fins-read", "web", "utils"}`，`fins` 不在其中，ingestion 指引被正确过滤。
  3. `mode=all` 时 `selected_tags` = catalog 全量 tags 并集（Plan line 81 已覆盖）；`mode=none` 为空集；`mode=select` 为 `tool_tags_any`。
  4. 验证：prompt scene 的 `system_prompt` 不包含 `fins` tag 对应的 ingestion 指引；`mode=all` scene 的 `system_prompt` 包含所有指引。
- **修复风险（低/中/高）**: 低 — 只需在 Plan 中补充一行 `selected_tags` 计算语义
- **严重程度（低/中/高/严重）**: 中 — 不阻塞实施启动，但实施 Agent 需自行决定语义，可能选错

## Architecture Boundary Review (re-review)

Plan 的分层落点经验证正确：
- `dayu.runtime.scene_prepare` 只做层中立条件块过滤 — `scene_prepare.py` 不 import 任何业务包 ✅
- `dayu.fins.resolver` 放 FMP 公司信息 public contract — 当前不存在，需新建 ✅
- `dayu.service.scene_context` 放 LLM-facing slot function — 当前不存在，需新建 ✅

## Overcoupling Review (re-review)

3 slices 耦合度经验证合理：
- S1（runtime 过滤）独立于 S2（FMP resolver + slot builder）✅
- S3（docs + validation）依赖 S1/S2 ✅
- S2 内部 FMP resolver 与 slot builder 可通过 fallback 解耦 ✅

## Code Fact Verification Summary

| 代码事实 | Plan 声称 | 验证结果 |
|---------|----------|---------|
| `prompt.json` tool_tags_any | `["fins-read", "web", "utils"]` | ✅ 一致 |
| `soul.md` 不含 `{{base_user}}` | Plan line 28 | ✅ 一致 |
| `base_user` 在 12 个 manifest 中 | Plan line 29/329 | ✅ 一致（grep 确认 12 个） |
| `base_user` 在 3 个 CLI 模块中 | Plan line 29 | ✅ 一致（prompt.py/interactive.py/session.py） |
| `base_user` 不在任何 `.md` fragment 中 | Plan 未显式声明 | ✅ grep 确认零结果，删除 manifest slot 不会导致 unresolved placeholder |
| `fins-download`/`fins-preprocess` 在 interactive/wechat 中 | Plan line 231 | ✅ 一致 |
| `fins-upload` 不存在于 manifest | Plan line 25 | ✅ 一致 |
| read-only 工具同时携带 `fins` 和 `fins-read` tag | Plan 未显式声明 | ✅ `fins_tools.py:53` 确认 |
| `dayu/fins/resolver/` 不存在 | Plan line 150-154 | ✅ 需新建 |
| `dayu/service/scene_context.py` 不存在 | Plan line 118 | ✅ 需新建 |
| `FMP_API_KEY` 不存在于 codebase | Plan line 143 | ✅ 新 env var |

## Conclusion

**pass-with-findings**

所有 14 个 accepted findings 均已在 fixed plan 中正确修复。Plan 的 root cause 识别准确，分层落点正确，slices 切分合理，checkpoint 状态同步，`base_user` 范围量化充分，契约规格完整。

发现 1 个新 finding（RF-01）：`selected_tags` 计算路径的语义未明确定义。这是 F01 修复的伴生问题——Plan 要求重命名 `<when_tag fins>` 为 `<when_tag fins-read>`，但未明确 `selected_tags` 是取 `tool_tags_any` 还是 selected tools 的全量 tags 并集。两种实现导致不同过滤语义。修复风险低，建议 Plan 补充一行语义说明。

## Completion Report

- **Artifact path**: `docs/reviews/wu-cli-smoke-01-context-slot-fmp-scene-filter-plan-rereview-mimo.md`
- **Conclusion**: pass-with-findings
- **Unresolved accepted findings**: 0（全部 14 个已修复）
- **New blockers**: 0
- **New non-blocking findings**: 1（RF-01 中）
- **Residual risks**:
  - RF-01 `selected_tags` 语义歧义 — 建议 Plan 补充后即可实施
  - FMP API 配额/rate-limit — Plan 已覆盖（短超时 + fallback）
  - upload 暴露面 — Plan 已明确不扩大
  - 条件块嵌套 — Plan 已明确为 non-goal
