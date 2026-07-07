# Code Review

## Scope

- Mode: current changes
- Branch: phase/host-issues-control
- Base: main
- Output file: docs/reviews/wu-cli-smoke-01-current-time-tool-boundary-review-ds.md
- Review focus: `current_time` 与 `get_current_time` 语义边界修正
- Included scope:
  - `dayu/config/prompts/manifests/*.json` — 所有 scene manifest tool_selection 与 context_slots
  - `dayu/config/prompts/scenes/*.md` — 所有 scene prompt {{current_time}} placeholder
  - `dayu/config/prompts/base/tools.md` — `<when_tool get_current_time>` LLM-facing 指引
  - `dayu/service/scene_context.py` — `current_time()` 渲染文本
  - `dayu/tools/utils/provider.py` — `get_current_time` tool description 与 schema
  - `dayu/config/tool_discovery.json` — utils-tools provider 注册
  - `tests/runtime/test_scene_assets_migration.py` — 迁移测试
  - `tests/runtime/test_scene_prepare.py` — 场景装配测试
  - `tests/runtime/test_scene_tool_selection.py` — 工具选择测试
  - `tests/service/test_entrypoint_runtime.py` — 入口运行时测试
  - `tests/service/test_entrypoint_runtime_prompt_path.py` — prompt 路径测试
  - `tests/service/test_entrypoint_runtime_interactive_path.py` — interactive 路径测试
  - `tests/service/test_host_assembly.py` — host 装配测试
  - `dayu/config/README.md` — config README
  - `tests/README.md` — tests README
- Excluded scope: 与 `current_time` / `get_current_time` 无关的 phase/host-issues-control 分支其他改动（CLI、Engine、Host、Fins resolver 等）
- Parallel review coverage: 无

## Findings

### 01-未修复-中-infer 与 write scene 的 fins_default_subject slot 在 placeholder 之后缺失渲染验证

- **入口/函数**: `ScenePrepareRequest` → `prepare_scene()` → context slot 替换
- **文件(行号)**: `tests/runtime/test_scene_assets_migration.py` 中 `test_infer_manifest_selects_read_and_web_without_long_transaction_or_upload` 未验证 `fins_default_subject` 展开
- **输入场景**: `infer` 或 `write` scene 通过 entrypoint 传入 `fins_default_subject` slot value，但 `infer.md` / `write.md` 的 `{{fins_default_subject}}` 位于 `{{current_time}}` 之后，且 slot 展开语义依赖 ScenePrepare 的 `context_slot_values` 按名替换
- **实际分支**: `test_infer_manifest_selects_read_and_web_without_long_transaction_or_upload` 只验证 tool_selection（`assert "get_current_time" not in selected`），不验证 `fins_default_subject` 实际写入 system_prompt
- **预期行为**: `fins_default_subject` 应出现在最终 system_prompt 中
- **实际行为**: 测试未覆盖此路径；若 manifest 误删 `fins_default_subject` slot，当前测试套件不会捕获
- **直接证据**: `test_infer_manifest_selects_read_and_web_without_long_transaction_or_upload`（scene_assets_migration.py:615-638）仅断言 tool_selection 与 system_prompt 中的工具排除，无限定 `fins_default_subject` 内容断言。对比 `test_prepared_current_time_does_not_interrupt_scene_contract` 已有全面 slot 顺序断言（覆盖全部 scene），但该测试不直接验证 `fins_default_subject` 文本存在性
- **影响**: 低 — 当前 manifest 配置正确，`fins_default_subject` 未被误删；但缺乏防御性测试覆盖，未来 manifest 变更可能静默丢失该 slot 而不被测试捕获
- **建议改法和验证点**: 在 `test_infer_manifest_selects_read_and_web_without_long_transaction_or_upload` 中增加 `assert _FINS_DEFAULT_SUBJECT_MARKDOWN in result.system_prompt` 或类似断言。同理 `write` 相关测试
- **修复风险（低）**: 纯测试补充，不涉及生产代码
- **严重程度（中）**: 防御性覆盖缺失，当前无实际 bug

### 02-未修复-低-infer scene 的 tool_selection 从显式工具名切换到标签时丢失了 start_fins_download / start_fins_preprocess

- **入口/函数**: `infer.json` manifest → `ScenePrepare` tool_selection
- **文件(行号)**: `dayu/config/prompts/manifests/infer.json:17-25`
- **输入场景**: infer scene 运行时，模型需要长事务下载/预处理财报
- **实际分支**: 新版 `infer.json` 的 `tool_tags_any: ["fins-read", "web"]` 不再包含 `"fins-download"` / `"fins-preprocess"` 标签
- **预期行为**: infer 场景是推理/分类任务，按场景语义不应暴露 download / preprocess 工具。但旧版 manifest 显式列出了这些工具名，需要确认是否是**有意移除**
- **实际行为**: `start_fins_download` 和 `start_fins_preprocess` 从 infer 场景可用工具中移除
- **直接证据**: diff 显示旧 infer.json 的 `tool_names` 显式包含 `start_fins_download` 和 `start_fins_preprocess`，新版 `tool_tags_any` 不包含对应标签；infer.md 场景描述只提及 "优先读取最新年报" 且不涉及下载/预处理工作流
- **影响**: 如果 infer 场景确实不应调用 download/preprocess（场景描述支持此判断），则无影响；如果 infer 在某些路径需要这些工具，则功能受损。当前 infer.md 不引用 download/preprocess 工作流，倾向于认为这是**有意且正确的清理**
- **建议改法和验证点**: 确认 infer 场景设计意图。若是有意移除，关闭此 finding；若需保留，将 `"fins-download"` / `"fins-preprocess"` 加入 `tool_tags_any`
- **修复风险（低）**: 只需要确认设计意图
- **严重程度（低）**: 大概率是有意清理，当前无已知功能受损

## Open Questions

1. **infer 场景是否曾依赖 `start_fins_download` / `start_fins_preprocess`？** diff 显示这两个工具被移除，但 infer.md 场景描述未提及下载流程。需要确认这是有意清理还是遗漏。
2. **`confirm` / `regenerate` / `repair` / `write` 场景同样从显式工具名切换到标签**，是否经过完整的功能回归？当前测试只验证了工具选择正确性和 system prompt 不包含被排除工具的指引，未覆盖这些场景在真实 LLM 调用中的行为。

## Residual Risk

1. **无 `get_current_time` 工具的场景中，LLM 可能因 `{{current_time}}` 文本提到"该时间不会自动更新"而产生困惑或自行编造当前时间**。当前缓解措施：tool description 和 tools.md 的边界说明仅对 interactive/wechat 可见（因为只有它们选择该工具并保留 `<when_tool get_current_time>` 块）；prompt 等场景完全看不到 `get_current_time` 的任何指引，模型不会知道此工具存在，因此不会被诱导调用。风险较低但非零——若模型训练数据中包含"当系统说时间不更新时应该调工具"的模式，可能产生幻觉调用。

2. **`utils` 标签作为通用工具标签的未来扩展风险**：当前只有 `get_current_time` 挂载在 `utils` 标签下。如果未来新增 `utils` 标签工具（例如计算器、单位转换），它们将自动对 interactive/wechat 场景可见。这是设计预期（`utils` 为通用工具标签），但需要意识到标签语义的扩展效应。

3. **测试覆盖集中在 `test_scene_assets_migration.py`**，该测试使用 `_fake_tool_catalog()` 而非真实 `ToolsDiscovery` 的完整工具目录。真实工具标签映射的变化（例如 `get_current_time` 的 `time` 标签被某个 manifest 选择）不会被这些测试捕获。`test_packaged_select_manifests_use_tag_only_tool_selection` 只验证 manifest 的 `tool_names` 为空，不验证标签覆盖完整性。

## Review Conclusion

**Pass** — 当前改动正确实现了用户裁决的语义边界：

1. ✅ `prompt` manifest 的 `tool_tags_any` 从 `["fins-read", "web", "utils"]` 改为 `["fins-read", "web"]`，不再选择 `get_current_time`
2. ✅ `interactive` / `wechat` manifest 保持 `"utils"` 标签，继续选择 `get_current_time`
3. ✅ 所有其他 scene manifest（audit, confirm, decision, fix, infer, overview, regenerate, repair, write, smoke）均不通过 `utils` 标签选择 `get_current_time`
4. ✅ `current_time()` 渲染文本新增说明："这是对话开始时的当前时间；回答"现在/今天/当前时间"默认使用它；该时间不会自动更新。" — 纯 LLM-facing，无内部术语
5. ✅ `get_current_time` tool description 明确调用边界："只有用户明确要求获取此刻最新时间，或要求在等待、查询、下载、上传、处理等动作完成后再确认时间时才调用。普通"现在/今天/当前时间"问题如果不需要重新确认，就使用已给出的当前时间，不调用本工具。"
6. ✅ `tools.md` `<when_tool get_current_time>` 块提供一致的调用指引
7. ✅ 所有 15 个 scene prompt 的 `{{current_time}}` placeholder 与对应 manifest 的 `current_time` context_slot 声明完全对齐
8. ✅ `fins_default_subject` 未被破坏：interactive/wechat/smoke 场景本就不要求该 slot（确认于 `_NO_DEFAULT_SUBJECT_SCENES`）
9. ✅ 测试覆盖：prompt 不选（`test_prompt_prepared_output_filters_long_transaction_guidance`、`test_prompt_runtime_uses_real_prompt_manifest_required_slots`）、interactive 仍选（`test_interactive_runtime_uses_real_manifest_required_slots`）、文本无内部术语（`test_current_time_rendering_explains_static_boundary_without_internal_terms`）、tool description 规则（`test_get_current_time_tool_description_explains_refresh_boundary`）、全量 scene 遍历验证（`test_get_current_time_tool_is_selected_only_for_interactive_wechat_scenes`）
10. ✅ README 更新：`dayu/config/README.md` 正确反映只有 `interactive` / `wechat` 选择 `get_current_time`；`tests/README.md` 反映测试覆盖变化
11. ✅ pyright 0 errors / 0 warnings；全部 121 个相关测试通过

两个 findings（01 防御性测试覆盖缺失、02 infer 工具列表变更意图确认）均为低/中严重度且不阻塞合入。建议在后续迭代中补充 01 的测试覆盖。
