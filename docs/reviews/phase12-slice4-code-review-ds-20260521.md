# Phase 12 Slice 4 Code Review — AgentDS

## Verdict: PASS

Blocking findings count: **0**

## Scope

- **Mode**: current changes (Phase 12 Slice 4 workspace diff vs HEAD)
- **Branch**: `docs/phase12-design-discussion`
- **Base**: HEAD (Slice 4 实现提交)
- **Review focus**: `dayu/runtime/scene_prepare.py`、`tests/runtime/test_scene_prepare.py`、`tests/runtime/test_scene_tool_selection.py`、`tests/runtime/test_import_boundary.py` 增量、README 同步
- **Reviewed files**:
  - `dayu/runtime/scene_prepare.py`（新增，1575 行）
  - `tests/runtime/test_scene_prepare.py`（新增，523 行）
  - `tests/runtime/test_scene_tool_selection.py`（新增，239 行）
  - `dayu/runtime/__init__.py`（module docstring 更新）
  - `dayu/README.md`（scene_prepare 能力说明）
  - `dayu/config/README.md`（scene manifest schema 说明）
  - `tests/README.md`（测试覆盖描述）
  - `tests/runtime/test_import_boundary.py`（新增 scene_prepare 边界覆盖）
  - `docs/host/implementation-control.md`（gate 状态更新）
- **Not reviewed (out of scope)**: `docs/host/design.md` 全文、ConfigLoader/ToolsDiscovery 既有实现、Host public interface、Engine execution path、旧 dayu-agent assets

## 验证命令及结果

| 命令 | 结果 |
|---|---|
| `pytest tests/runtime/test_scene_prepare.py tests/runtime/test_scene_tool_selection.py -q` | 21 passed |
| `pytest tests/runtime/test_import_boundary.py tests/runtime/test_weak_typing_guard.py -q` | 8 passed |
| `python -m pyright dayu/runtime tests/runtime` | 0 errors, 0 warnings, 0 informations |
| `git diff --check` | clean |

## Findings

### 1. 未修复-中-optional fragment 缺失时静默跳过，fragment_refs / source_refs / digest 失去该 fragment 痕迹

- **入口/函数**: `_load_fragment_contents` (line 872)
- **文件(行号)**: `dayu/runtime/scene_prepare.py:888-905`
- **输入场景**: manifest 声明 `required=false` 的 fragment，对应文件在 `prompt_asset_root` 下不存在
- **实际分支**: `not path.exists()` 且 `fragment.required` 为 False → `continue`（line 903）
- **预期行为**: optional fragment 缺失不应导致装配失败，但目前完全不留下该 fragment 的任何痕迹
- **实际行为**: 该 optional fragment 不会出现在 `fragment_refs`、`source_refs` 或 `system_messages` 中。`content_digest` 和 `source_refs` 也不包含该 fragment 的声明信息。对 audit / trace 而言，无法从输出中判断某个 optional fragment 被声明但因文件缺失被跳过。
- **直接证据**: line 888-905：`if not path.exists()` 分支中只对 `required` fragment 报错，对 optional fragment 直接 `continue`，不记录任何信息。
- **影响**: audit / trace 可解释性缺失。若 optional fragment（如可选 disclaimer 或引用说明）因部署问题缺失，外部无法从 `PreparedSceneInputs` 输出诊断。
- **建议改法和验证点**: 考虑在 `fragment_refs` 或 `source_refs` 中保留缺失 optional fragment 的声明记录（标记为缺失），或在 `content_digest` 中包含 "此 fragment 声明了但未加载" 的事实。不改不影响当前 correctness（第一版无 optional fragment 用例），但需要记录为已知限制。
- **修复风险（低）**: 只影响 metadata / refs 输出，不改变 system_messages 内容。
- **严重程度（中）**: 不影响核心装配正确性，但影响可观测性和部署诊断。

### 2. 未修复-低-fragment order 跨继承冲突的错误消息未区分来源 manifest

- **入口/函数**: `_validate_fragment_uniqueness` (line 1261)
- **文件(行号)**: `dayu/runtime/scene_prepare.py:1261-1280`
- **输入场景**: 父 scene 和子 scene 各自声明了相同 order 的 fragment（子只追加，不覆盖，但恰巧 order 冲突）
- **实际分支**: `fragment.order in orders` → raise with `duplicate fragment order in {scene_id}`（line 1278）
- **预期行为**: 错误消息应帮助定位冲突来源（哪个是父的，哪个是子的）
- **实际行为**: 错误消息只给出 scene_id（当前处理的 manifest scene_id，即子的），未列出冲突的父 fragment 信息。定位需回查父 manifest 文件。
- **直接证据**: line 1277-1278：错误消息只含 `scene_id` 和重复 order，不含父 manifest 引用。
- **影响**: 调试时需要手工回查父 manifest 的 fragments 列表，对复杂的继承链稍微增加排查成本。不影响装配正确性。
- **建议改法和验证点**: 在错误消息中附加 duplicated fragment 的 id 和来源 manifest。非 blocker，可在后续迭代中改善。
- **修复风险（低）**: 纯消息改进。
- **严重程度（低）**: 仅影响调试效率，不影响 correctness。

## Open Questions

1. **`ScenePrepareRequest` 中 `scene_manifest_root` 与 `prompt_asset_root` 类型为 `Path`，但未在 `__post_init__` 中校验目录存在性**（line 147-170）。当前设计是 "调用方显式传入"，不校验目录是否存在，到实际读取时 fail fast。是否需要更早的 pre-condition 校验？

2. **`_SceneDefaults` 当前只有 `missing_required_fragment` 一个字段且硬编码只接受 `"fail_closed"`**（line 775-793）。若未来需要 `"warn"` 或 `"skip"` 等策略，是否会扩展，还是一直 fail-closed？

3. **`SceneToolCatalog.from_tool_bundle` 依赖 `ToolBundle.definitions`**（line 108-122）。当前 `ToolDefinition.tags` 的默认值是 `frozenset()`，但 `SceneToolInfo.__post_init__` 对空 tag 名会 fail（line 78-80）。这不会在正常 flow 中触发，但若 future `ToolDefinition` 变更 tags 生成方式可能导致意外。是否需要测试覆盖？

## Residual Risk

1. **Symlink 逃逸测试缺失**：`_resolve_contained_path` 通过 `Path.resolve()` 解析符号链接后做 containment 校验，逻辑正确。但测试 `test_fragment_path_escape_prompt_asset_root_fails` 只覆盖 `../` 相对路径逃逸，未覆盖 symlink 逃逸场景（在临时目录创建 symlink 指向 root 外路径）。建议后续补充 symlink-specific 边界测试。

2. **并发场景未覆盖**：`ScenePrepare` 是纯函数、无状态，天然线程安全。但 manifest 文件在装配过程中被外部并发修改的场景未在测试中模拟。属于 acceptable risk——调用方应在装配前确保文件系统稳定。

3. **大 fragment / 大 context_slot_values 场景未测试**：当前测试的 fragment 内容和 slot values 都很小。超长 fragment（数 MB）或大量 context slots（数百个）的性能和正确性未验证。第一版单 Run scene 场景不会触发此边界，属于后续关注项。

4. **未覆盖旧 dayu-agent scene asset migration（Slice 5）**：按计划归 Phase 12 Slice 5，不在本 slice scope。

5. **未覆盖 Service 映射链**：`PreparedSceneInputs` → `open_host` construction-time inputs 与 per-run request inputs 的映射属于 Service / composition root 职责，不在本 slice。
