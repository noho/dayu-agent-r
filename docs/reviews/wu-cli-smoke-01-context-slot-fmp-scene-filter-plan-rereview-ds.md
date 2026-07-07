# WU-CLI-SMOKE-01 Plan Re-Review — AgentDS

## Review Metadata

- **Reviewer**: AgentDS (plan re-review)
- **Date**: 2026-07-07 15:21 CST
- **Fixed plan artifact**: `docs/host/wu-cli-smoke-01-context-slot-fmp-scene-filter-plan.md`
- **Prior DS review**: `docs/reviews/wu-cli-smoke-01-context-slot-fmp-scene-filter-plan-review-ds.md`
- **Fix artifact (Codex)**: `docs/reviews/wu-cli-smoke-01-context-slot-fmp-scene-filter-plan-fix-codex.md`
- **MiMo review (context)**: `docs/reviews/plan-review-20260707-151057.md`
- **Re-review scope**: verify all controller-accepted findings are fixed; identify remaining blockers

## Controller Adjudication Recap

| Finding | Source | Decision |
|---------|--------|----------|
| MiMo F01 (`<when_tag fins>` granularity) | MiMo | Accepted |
| MiMo F02 (checkpoint state sync) | MiMo | Accepted |
| MiMo F03 (`base_user` residual scope) | MiMo | Accepted |
| MiMo F04 (`selected_tags` implementation path) | MiMo | Accepted |
| MiMo F05 (`EntrypointContextSlotRequest` fields) | MiMo | Accepted |
| MiMo F06 (empty slot line cleanup) | MiMo | Accepted |
| MiMo F07 (prepared output marker tests) | MiMo | Accepted |
| DS-F02 (空 slot 行两种机制) | DS | Accepted (merged with MiMo F06) |
| DS-F03 (`current_time` format) | DS | Accepted |
| DS-F04 (FMP API key env var name) | DS | Accepted |
| DS-F05 (module name convergence) | DS | Accepted |
| DS-F06 (`tuple[str, ...]` rationale) | DS | Accepted |
| DS utils/time tag semantics | DS | Accepted |
| DS FMP timeout precision | DS | Accepted |
| DS-F01 (`soul.md` missing from affected files) | DS | Rejected as written; broader `base_user` scope via MiMo F03 |

## Verified Code Facts (Re-confirmed)

- `dayu/config/prompts/base/soul.md`: **零** `base_user` 引用，与 plan 一致。
- `dayu/service/`: **零** `base_user` 引用，与 plan 的 `rg` 范围一致。
- `prompt.json` `tool_tags_any`: `["fins-read", "web", "utils"]`，与 plan 记录的 checkpoint `2a61fbfd` 状态一致。
- `base_user` 残留范围经 `rg` 确认：12 manifests、3 CLI 模块、`tests/`、`utils/smoke_host_public_multiturn.py`，与 plan line 29 一致。

## Finding-by-Finding Verification

### MiMo F01 — `<when_tag fins>` block 粒度不足 → **已修复** ✅

- **Plan 修复位置**: lines 41-42, 87-91, 244-247
- **验证**: Plan 明确要求 `base/tools.md` 不得继续使用粗粒度 `<when_tag fins>`；必须拆分为 `<when_tag fins-read>` 与 `<when_tag ingestion>`，或对长事务工具用 `<when_tool start_fins_download>` / `<when_tool start_fins_preprocess>` 精确包裹。Expected assertions 要求 prompt `system_prompt` 包含 read-only 指引但不包含 download/preprocess/upload 指引。
- **结论**: 规格充分，可直接实施。

### MiMo F02 — S1 引用已不存在的 tag 和 checkpoint 状态不同步 → **已修复** ✅

- **Plan 修复位置**: lines 24-27, 230-231
- **验证**: Plan 新增"当前代码事实与 checkpoint 同步"章节，明确 `prompt.json` 当前无 `fins-download`/`fins-preprocess`，不存在 manifest 字面 `fins-upload`。S1 明确"只验证并保护该状态，不安排删除不存在的 tag"。
- **结论**: 与 checkpoint 状态已同步。

### MiMo F03 — `base_user` 删除范围被低估 → **已修复** ✅

- **Plan 修复位置**: lines 29, 167-180, 282-283, 295, 305, 329, 344, 361
- **验证**: Plan 显式量化范围为 12 manifests、3 CLI 模块、tests、utils smoke。S3 逐文件列出 12 个 manifest。多处嵌入 `rg -n "base_user" dayu/config/prompts dayu/cli tests utils` 验证命令，预期零残留或只剩明确非 LLM-facing 文档引用。
- **独立验证**: 本 re-review 重新运行 `rg -n "base_user" dayu/config/prompts dayu/cli tests utils dayu/service`，确认 `dayu/service/` 零残留，plan 的 `rg` 范围准确。
- **结论**: 范围完整，验证命令充分。

### MiMo F04 — `<when_tag>` 实现路径未指定 → **已修复** ✅

- **Plan 修复位置**: lines 73-74
- **验证**: Plan 指定"在过滤函数内部遍历 `catalog.tools`，用 selected tool names 构建 `selected_tags: frozenset[str]`，不要为此新增不必要的 `SceneToolCatalog` public API"。
- **结论**: 实现路径明确，不引入不必要的 API 膨胀。

### MiMo F05 — `EntrypointContextSlotRequest` 字段未规格化 → **已修复** ✅

- **Plan 修复位置**: lines 124-131
- **验证**: Plan 明确定义四个字段：`ticker: str | None`、`now: datetime | None`、`fmp_api_key: str | None`、`fmp_timeout_seconds: float`。每个字段的含义和约束均已说明。
- **结论**: Public contract 完整，可直接生成 dataclass。

### MiMo F06 — 空 slot 行清理规则不精确 → **已修复** ✅

- **Plan 修复位置**: lines 98-114
- **验证**: Plan 指定固定 6 步执行顺序（per-fragment 条件块过滤 → placeholder 替换 → 空 slot 行清理 → 丢弃全空 fragment → `"\n\n"` join → 最终空行归一）。空 slot 行精确定义为"原始行去掉前后空白后完全匹配 `{{slot_name}}` 且替换值为 `""`"。边界 case 覆盖：fragment 全空、前导空白、行内其它文本且 slot 为空、条件块删除后多个空行。
- **结论**: 规则精确、可测试、无歧义。

### MiMo F07 — prepared output marker 测试缺口 → **已修复** ✅

- **Plan 修复位置**: lines 232, 247
- **验证**: Plan 要求"测试从 raw marker 存在迁移或补充为 prepared output 不含 marker"；expected assertions 包含"所有 prepared prompt 不包含 `<when_tag` / `<when_tool` / closing marker"。
- **结论**: 测试边界从 asset 级别推进到 prepared output 级别。

### DS-F02 — 空 slot 行两种机制不可组合 → **已修复** ✅

- **Plan 修复位置**: 与 MiMo F06 合并处理，lines 98-114
- **验证**: 已在 MiMo F06 中确认。两个规则已统一为单一 6 步流水线，不再存在独立的 post-filter compression 和 post-render line removal。
- **结论**: 已合并修复，无残留歧义。

### DS-F03 — `current_time` LLM-facing 格式未指定 → **已修复** ✅

- **Plan 修复位置**: lines 138-139
- **验证**: Plan 指定精确格式 `# 当前时间\n现在是 2026年7月7日 15:08（Asia/Shanghai，星期二）。`，约束为 `Asia/Shanghai`、24 小时制、中文星期、不投影 ISO、不伪装财报事实。
- **结论**: 格式规范完整，可直接编写测试断言。

### DS-F04 — FMP API key env var 名称未指定 → **已修复** ✅

- **Plan 修复位置**: lines 143-145
- **验证**: Plan 指定环境变量名称为 `FMP_API_KEY`，与 OLD 行为一致。若需常量则新增 `FMP_API_KEY_ENV: Final[str] = "FMP_API_KEY"`。明确 Fins resolver 不得隐式读 env。
- **结论**: 名称和注入路径均已明确。

### DS-F05 — Service slot 模块名二选一未收敛 → **已修复** ✅

- **Plan 修复位置**: lines 118, 279
- **验证**: Plan 已收敛到 `dayu.service.scene_context`。所有引用点一致使用该名称。
- **结论**: 已收敛，无残留候选名。

### DS-F06 — `tuple[str, ...]` 类型变更未说明理由 → **已修复** ✅

- **Plan 修复位置**: line 161
- **验证**: Plan 说明"OLD 的 `list[str]` 改为 `tuple[str, ...]`，原因是新 public contract 应为不可变输出，避免调用方修改 resolver 返回对象"。
- **结论**: 理由已记录，类型变更透明。

### DS utils/time tag 语义澄清 → **已修复** ✅

- **Plan 修复位置**: lines 27-28
- **验证**: Plan 明确 `utils/time` 不是 manifest 字面 tag，只是说明"utils/time 工具能力"的自然语言缩写。工具实际 tags 是 `utils` 和 `time`，manifest 当前用 `"utils"` 选中 `get_current_time`。
- **结论**: 语义澄清充分，不会误导 implementation agent。

### DS FMP timeout 精度 → **已修复** ✅

- **Plan 修复位置**: lines 127-128, 146, 285
- **验证**: Plan 多处明确 FMP resolver timeout 可配置，Service slot path 默认 ≤ 5 秒，失败 fallback 到 ticker-only subject，不向 LLM 暴露错误。
- **结论**: 超时策略完整，覆盖配置、默认值和 fallback 路径。

### DS-F01 (rejected) — `soul.md` 遗漏 → **已正确处理** ✅

- **Plan 处理位置**: lines 28-29, 196, 330
- **验证**: Plan 明确当前 `soul.md` 不含 `{{base_user}}`（独立 grep 确认），不列为必须修改文件。仅当 implementation 前 grep 发现事实变化才允许修改。更广泛的 `base_user` 删除范围已通过 MiMo F03 覆盖。
- **结论**: Controller 的拒绝理由（soul.md 当前无 base_user）与代码事实一致，plan 正确反映了这一裁决。

## New Observations (Below Finding Threshold)

以下观察不构成 finding，不阻塞实施：

1. **FMP HTTP client 默认实现未指定**: Plan 定义了 `FmpHttpClientProtocol`，但未指定不传 `opener` 时的默认 HTTP 实现。Implementation agent 可自然选择 `urllib.request`（标准库，与 OLD 一致）。风险极低。

2. **`fmp_timeout_seconds` 默认值**: Plan 说"默认必须小于等于 5 秒"但未给出精确默认值（如 `5.0`）。Implementation agent 可自然推断为 `5.0`。风险极低。

3. **`rg` 验证命令不含 `dayu/service/`**: 独立 grep 确认 `dayu/service/` 当前零 `base_user` 引用，故不需要包含。若 implementation 过程中在 `dayu/service/` 新增了 `base_user` 引用，implementation agent 应自行扩展验证范围。

## Architecture Boundary Re-check

Plan 修复后未改变分层边界。重新确认：

- `dayu.runtime.scene_prepare`：只做层中立条件块过滤、placeholder 渲染、空行清理。不 import 业务包。✅
- `dayu.service.scene_context`：Service 层 slot assembly，消费 CLI/Fins resolver 输入，返回 LLM-facing 文本。✅
- `dayu.fins.resolver`：Fins 公共契约子包，不依赖 Service/CLI/Host/Engine。✅
- `dayu.cli`：调用 Service scene context builder，不再手写 LLM-facing slot 细节。✅

## Slice Readiness Re-check

| Slice | 目标 | 文件列表 | 测试命令 | 完成信号 | 阻断条件 | 评估 |
|-------|------|---------|---------|---------|---------|------|
| S1 | 条件块过滤 + prompt 暴露面闭环 | 10 文件，精确列出 | 5 个 pytest 文件 | tests 通过 + 无 Service 二次解释 | 条件块需 manifest schema 新字段则停 | ✅ 就绪 |
| S2 | FMP resolver + Service slot 文本生成 | 15 文件，精确列出 | 8 个 pytest 文件 + rg 验证 | slot 生成只有单一 Service 真源 | FMP 慢请求阻塞 CLI 则停 | ✅ 就绪 |
| S3 | Assets/manifests/docs 对齐 + 全量验证 | 7 类别，精确列出 | 全量 pytest + pyright + rg + git diff | 所有验证通过 + README 更新 | README 约束与代码冲突则停 | ✅ 就绪 |

S1 和 S2 可独立并行实施（S1 改 runtime，S2 改 fins/service/CLI），S3 依赖 S1/S2 完成后做最终对齐。

## Conclusion

**pass**

所有 14 项 controller-accepted findings 均已在 fixed plan 中正确修复，无未解决项。DS-F01 的拒绝理由与代码事实一致，plan 正确处理。未发现新的阻断性问题。Plan 已达到 code-generation-ready 状态，可安全交给 implementation agent。

## Completion Report

- **Artifact path**: `docs/reviews/wu-cli-smoke-01-context-slot-fmp-scene-filter-plan-rereview-ds.md`
- **Conclusion**: **pass**
- **Unresolved accepted findings**: 0
- **New blockers**: 0
- **Residual risks** (延续自前序 review，已在 plan 中记录):
  - FMP API 配额/rate-limit → plan 已覆盖短超时 + fallback
  - upload 暴露面不扩大 → plan 已明确 non-goal
  - 条件块未来嵌套需求 → plan 已明确当前 non-goal，fail closed
  - 真实 FMP/LLM smoke 依赖外部 key → plan 已明确自动测试用 fake HTTP，手工 smoke 不进 CI
