# WU-CLI-SMOKE-01 Plan Fix Artifact — AgentCodex

## Metadata

- Gate：plan review fix
- Work unit：WU-CLI-SMOKE-01 context slot / FMP / scene tool filtering follow-up
- Fix agent：AgentCodex
- Target plan artifact：`docs/host/wu-cli-smoke-01-context-slot-fmp-scene-filter-plan.md`
- Review artifacts：
  - `docs/reviews/plan-review-20260707-151057.md`
  - `docs/reviews/wu-cli-smoke-01-context-slot-fmp-scene-filter-plan-review-ds.md`
- Scope：只修正 plan artifact 并新增本 fix artifact；未实现生产代码，未修改测试，未 commit，未 push，未创建 issue/PR。

## Current Code Fact Check

- `dayu/config/prompts/base/soul.md` 当前不含 `{{base_user}}`，因此 DS-F01 as written 与当前代码事实不一致。
- `prompt.json` 当前 `tool_tags_any` 为 `["fins-read", "web", "utils"]`，没有 `fins-download`、`fins-preprocess` 或 manifest 字面 `fins-upload`。
- `get_current_time` 工具实际 tags 为 `utils` 和 `time`；manifest 当前用 `"utils"` tag 选中它。
- `base_user` 当前残留在 12 个 manifest、3 个 CLI 模块、tests 和 `utils/smoke_host_public_multiturn.py`，计划已要求 implementation 后用 `rg -n "base_user" dayu/config/prompts dayu/cli tests utils` 验证零残留或只剩明确非 LLM-facing 文档引用。

## Finding Fix Status

| Finding | Controller decision | Fix status | Plan change |
|---|---|---|---|
| MiMo F01 | accepted | 已修复 | 明确 `base/tools.md` 的 `<when_tag fins>` 粒度不足；要求拆分为 `<when_tag fins-read>` 与 `<when_tag ingestion>`，或对长事务工具用 `<when_tool>` 精确包裹；验收 prompt 只选 `fins-read` 时不得看到 download/preprocess/upload 指引。 |
| MiMo F02 | accepted | 已修复 | 增加 checkpoint `2a61fbfd` 当前状态说明：`prompt.json` 已无 `fins-download`/`fins-preprocess`；当前不存在 manifest 字面 `fins-upload`；implementation 只验证和保护状态，不移除不存在的 tag；upload 暴露面不扩大。 |
| MiMo F03 | accepted in substance | 已修复 | 显式量化 `base_user` 范围为 12 个 manifests、3 个 CLI 模块、tests、utils smoke；列出 12 个 manifest 文件；要求 `rg -n "base_user" dayu/config/prompts dayu/cli tests utils` 预期零残留或只剩明确非 LLM-facing 文档引用。 |
| MiMo F04 | accepted | 已修复 | 指定 `<when_tag>` 实现路径：在 `ScenePrepare` 内先选 tools，再遍历 `catalog.tools` 基于 selected tool names 构建 `selected_tags`，不新增不必要 public API。 |
| MiMo F05 | accepted | 已修复 | 模块收敛为 `dayu.service.scene_context`；定义 `EntrypointContextSlotRequest` 字段：`ticker`、`now`、`fmp_api_key`、`fmp_timeout_seconds`。 |
| MiMo F06 | accepted | 已修复 | 精确定义空 slot 行：原始行 strip 后完全匹配 `{{slot_name}}` 且替换值为空才删除；固定执行顺序；覆盖前导空白、fragment 全空、行内其它文本等边界。 |
| MiMo F07 | accepted | 已修复 | 测试要求从 raw marker 存在迁移/补充为 prepared output 不含 marker；raw asset marker 可继续存在，定义为控制语法。 |
| DS-F02 | accepted | 已修复 | 与 MiMo F06 合并处理；plan 现在指定 per-fragment 过滤、替换、空行清理、空 fragment 丢弃、最终空行归一的顺序。 |
| DS-F03 | accepted | 已修复 | 指定 `current_time` LLM-facing 格式：中文可读、`Asia/Shanghai`、24 小时制、中文星期、不投影 ISO、不暗示财报事实。 |
| DS-F04 | accepted | 已修复 | 指定 env var 名称为 `FMP_API_KEY`；Fins resolver 显式接收 `api_key`，不隐式读 env；若需要常量，在公共配置/契约位置新增或使用已有常量。 |
| DS-F05 | accepted | 已修复 | 模块名收敛为 `dayu.service.scene_context`。 |
| DS-F06 | accepted | 已修复 | 说明 OLD `list[str]` 改为 `tuple[str, ...]` 是为了 public immutable contract。 |
| DS open question: utils/time | accepted | 已修复 | 明确 `utils/time` 不是 manifest 字面 tag；工具实际 tags 是 `utils` 和 `time`，manifest 当前用 `"utils"` 选中 `get_current_time`。 |
| DS residual risk: FMP timeout | accepted | 已修复 | 指定 FMP resolver timeout 可配置；Service slot path 默认小于等于 5 秒；失败 fallback 到 ticker-only subject，不向 LLM 暴露错误。 |
| DS-F01 as written | rejected / corrected | 已处理 | Plan 明确当前 `base/soul.md` 不含 `{{base_user}}`，不要列为必须修改文件；仅当 implementation 前重新核实到代码变化才允许修改。 |

## RF-01 Follow-up

- 来源：`docs/reviews/wu-cli-smoke-01-context-slot-fmp-scene-filter-plan-rereview-mimo.md` RF-01。
- Controller decision：作为 plan clarification 接受，但不采纳 RF-01 建议的 manifest-only `selected_tags` 语义。
- Resolution：plan 现在明确 `<when_tag TAG>` 仍基于实际选中工具及其 catalog tags。`selected_tags` 不得只从 manifest `tool_tags_any` 派生，因为 scene 通过显式工具名选中工具时，仍应展示该工具 tags 对应的 tag-scoped instructions。
- Safeguard：plan 现在把 RF-01 防护点放在 prompt asset discipline 与测试上：`base/tools.md` 必须使用 `<when_tag fins-read>`、`<when_tag ingestion>` 或长事务 tool-specific blocks；测试必须断言 prepared prompt output 不向 prompt scene 泄露 download/preprocess/upload 指引，并且 raw `base/tools.md` 不再包含混合用途 broad `<when_tag fins>` block。
- 生产代码变更：本 follow-up 无。
- 测试代码变更：本 follow-up 无。

## Residual Risks

| Risk | Classification | Owner / Destination |
|---|---|---|
| 真实 FMP/LLM smoke 依赖外部 key 与网络 | covered by later approved slice | S3 中作为 optional real smoke；自动测试必须 fake HTTP / monkeypatch 覆盖。 |
| upload 暴露面仍未扩大 | assigned to later work unit | 用户如需 upload scene 暴露，需要单独裁决本地文件授权与路径安全 UX。 |
| 条件块未来可能需要嵌套 | assigned to later work unit | 当前 non-goal；本 work unit fail closed，不支持嵌套。 |

## Validation

Required validation for this plan-fix gate:

```bash
git diff --check -- docs/host/wu-cli-smoke-01-context-slot-fmp-scene-filter-plan.md docs/reviews/wu-cli-smoke-01-context-slot-fmp-scene-filter-plan-fix-codex.md
```

Implementation tests and pyright are intentionally not run in this gate because the user explicitly requested plan fix only and no production/test implementation.

## Completion Status

- Accepted findings fixed in plan artifact：yes
- Rejected/corrected finding recorded：yes
- Production code changes：none
- Test changes：none
- Commit/push/issue/PR：none
- Next entry point：plan re-review, if the controller requests it
