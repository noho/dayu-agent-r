# Code Review — WU-CLI-SMOKE-01 S1

## Scope

- Mode: current changes
- Branch: `phase/host-issues-control`
- Base: `8015049c`（当前 HEAD）
- Output file: `docs/reviews/wu-cli-smoke-01-context-slot-fmp-scene-filter-s1-code-review-mimo.md`
- Included scope: workspace unstaged changes since `8015049c`，共 7 文件 +466/-33 行
- Excluded scope: 无
- Parallel review coverage: 无

## Findings

未发现阻塞性问题。以下为非阻塞 findings。

### 001-未修复-低-infer scene 不再选择 download/preprocess 工具

- **入口/函数**: `prepare_scene()` → `_select_tools()` → `infer.json` manifest
- **文件(行号)**: `dayu/config/prompts/manifests/infer.json`，`tests/runtime/test_scene_assets_migration.py:285-311`
- **输入场景**: `scene_id="infer"`
- **实际分支**: infer manifest `tool_tags_any` 从 `["fins", "web"]` 改为 `["fins-read", "web"]`，`_select_tools` 只选择 `fins-read` 和 `web` 标签工具
- **预期行为**: 按 plan 意图，infer 只做 read-only 判断，不应选择长事务工具
- **实际行为**: `start_fins_download`、`start_fins_preprocess`、`get_current_time` 不再出现在 infer 的 `tool_selection.tool_names` 中
- **直接证据**: `infer.json` 的 `tool_tags_any: ["fins-read", "web"]`（无 `utils`）；`_fake_tool_catalog` 中 `get_current_time` 标签为 `utils`/`time`，不匹配 `fins-read` 或 `web`。旧测试 `assert "get_current_time" in selected` 已改为 `assert "get_current_time" not in selected`（line 307）。
- **影响**: infer 场景运行时不再有 download/preprocess/get_current_time 工具可用。与 plan 一致，但若下游 Host/Service 有代码假设 infer 可调用这些工具，需同步调整。
- **建议改法和验证点**: 无需代码修改；需确认下游无硬依赖。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 002-未修复-低-interactive 必填 slot 断言从 fins_default_subject 改为 base_user

- **入口/函数**: `prepare_scene()` → `_render_fragment_content()` → context slot 校验
- **文件(行号)**: `tests/service/test_entrypoint_runtime_interactive_path.py:265-278`
- **输入场景**: `scene_id="interactive"`，`context_slot_values={}`
- **实际分支**: 旧测试期望 `ScenePrepareError` 匹配 `fins_default_subject`，新测试匹配 `base_user`
- **预期行为**: interactive manifest 的 required context_slots 只有 `base_user`（无 `fins_default_subject`），空 values 应在 `base_user` 上 fail closed
- **实际行为**: 测试已更正为 `match="base_user"`、`context_slot_values={}`
- **直接证据**: line 268 `with pytest.raises(ScenePrepareError, match="base_user")` 与 line 274 `context_slot_values={}`
- **影响**: 旧测试断言错误（interactive 从未需要 `fins_default_subject`）。更正消除了隐性错误断言。
- **建议改法和验证点**: 确认 `interactive.json` manifest 的 context_slots 只有 `base_user`。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## 无实质缺陷确认

以下维度均通过审查，未发现实质缺陷：

- **条件块解析器正确性**: `_filter_condition_blocks()` 使用状态机逐字符扫描，正确处理 open/close marker 匹配、错配检测、未闭合检测和嵌套拒绝。`_CONDITION_OPEN_MARKER_PATTERN` 与 `_CONDITION_CLOSE_MARKER_PATTERN` 互斥且覆盖所有合法 marker 形态。
- **Fail-closed 行为**: 6 种 malformed marker 输入（未闭合、裸 close、错配 close、嵌套、空名、多参数）均抛 `ScenePrepareError`，由 `test_condition_blocks_malformed_markers_fail_closed` 参数化覆盖。
- **selected tools/tags 语义**: `mode=all` 返回 `None`（全量），`mode=none` 返回空集合，`mode=select` 返回白名单+tag 并集。`_selected_tool_tags()` 基于实际选中工具的 catalog tags 聚合，语义正确。
- **prompt 暴露面**: prompt scene 选中 `fins-read`/`web`/`utils` 标签工具，不选中 `fins-download`/`fins-preprocess`/`fins-upload`；`<when_tag fins-read>` 保留 read-only 指引，`<when_tool start_fins_download/preprocess/upload>` 被过滤。interactive/wechat 额外保留 download/preprocess 指引。所有 marker 不进入 prepared output。
- **分层边界**: `scene_prepare.py` 不 import Host/Engine/Fins/Storage/Service，`_filter_condition_blocks` 只做纯文本操作。
- **AGENTS.md 合规**: 新增函数均有中文 docstring、完整类型签名，无 `Any`/`object`/`getattr`/`hasattr`，无兼容性 shim。

## Open Questions

- 旧 infer manifest 的 `tool_tags_any` 是否曾包含 `utils`？旧测试 `assert "get_current_time" in selected` 暗示旧 manifest 可能选中了 `get_current_time`，但当前 manifest 和新测试一致认为不应选中。若旧 manifest 确实包含 `utils`，则此行为变更需在 plan 中显式记录。

## Residual Risk

- `content_digest` 使用原始 fragment 内容（过滤前）计算，但 digest payload 包含 `selected_tool_names`，因此不同 tool selection 产生不同 digest。无碰撞风险。
- `mode=none` 场景下 tools.md 的全局规则段（`## 全局规则`）仍保留，因不在条件块内。这是设计意图还是需要额外处理，取决于产品决策。
- 无嵌套条件块支持；若未来需要嵌套语义需重新设计 parser。当前 fail-closed 行为是正确防御。

## 补充验证

review 期间独立执行完整验证：

```bash
pytest tests/runtime/test_scene_prepare.py tests/runtime/test_scene_tool_selection.py \
       tests/runtime/test_scene_assets_migration.py \
       tests/service/test_entrypoint_runtime_prompt_path.py \
       tests/service/test_entrypoint_runtime_interactive_path.py
# => 64 passed, 3 warnings (edgar deprecation, unrelated)

pyright
# => 0 errors, 0 warnings, 0 informations

git diff --check
# => passed
```
