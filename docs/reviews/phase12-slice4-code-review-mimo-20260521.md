# Code Review

## Scope

- Mode: current changes
- Branch: `docs/phase12-design-discussion`
- Base: HEAD (`0df0e83`)
- Output file: `docs/reviews/phase12-slice4-code-review-mimo-20260521.md`
- Included scope: `dayu/runtime/scene_prepare.py`（新增）、`tests/runtime/test_scene_prepare.py`（新增）、`tests/runtime/test_scene_tool_selection.py`（新增）、`dayu/runtime/__init__.py`（docstring 更新）、`dayu/README.md`、`dayu/config/README.md`、`tests/README.md`、`tests/runtime/test_import_boundary.py`、`docs/host/implementation-control.md`（文档同步）
- Excluded scope: 无
- Parallel review coverage: 架构边界检查（subagent）、symlink 逃逸防护验证（subagent）、设计文档与计划对齐（subagent）

## Findings

### 1-未修复-低-optional fragment missing on disk 无独立测试

- **入口/函数**: `_load_fragment_contents`（`scene_prepare.py:872`）
- **文件(行号)**: `scene_prepare.py:903`
- **输入场景**: manifest 声明 `required=false` 的 fragment，但对应文件不存在于 `prompt_asset_root`
- **实际分支**: `path.exists()` 返回 `False`，`fragment.required` 为 `False`，执行 `continue` 跳过
- **预期行为**: 跳过该 fragment，不加入 `loaded` 列表，不抛出异常
- **实际行为**: 代码正确执行 `continue`，行为符合预期
- **直接证据**: `scene_prepare.py:894-903`——`if not path.exists():` 分支内，`required=False` 时 `continue`
- **影响**: 无 correctness 风险；代码路径简单（单行 `continue`），但该路径未被任何测试覆盖，未来回归时无保护
- **建议改法和验证点**: 在 `test_scene_prepare.py` 中补充一个测试：manifest 声明 `required=false` 的 fragment，但不创建对应文件，断言装配成功且该 fragment 不出现在 `fragment_refs` 和 `system_messages` 中
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

- 无

## Residual Risk

1. **TOCTOU symlink race**: `_resolve_contained_path` 在 `resolve()` 后到 `path.read_text()` 之间存在理论上的 symlink 替换窗口。这是通用文件系统 race condition，非本模块特有，当前威胁模型下可接受。
2. **`SceneToolCatalog.from_tool_bundle` 无独立单测**: 该 `@classmethod` 只被集成路径隐式覆盖，无直接单元测试验证从 `ToolBundle` 投影到 `SceneToolCatalog` 的行为。当前正确性由类型系统和 `__post_init__` 校验保障。
3. **继承链 context_slots 去重顺序未显式测试**: `test_single_inheritance_merges_parent_first_and_child_overrides` 覆盖了父/子不同 slot 的合并，但未测试父/子声明同名 slot 时父优先保留的场景。去重逻辑 `_dedupe_context_slots` 本身正确，但无回归保护。

## Review Checklist

### 架构边界 — PASS

- `scene_prepare.py` 只 import 标准库和 `dayu.contracts.JsonValue` / `dayu.contracts.ToolBundle`
- 无 `dayu.engine` / `dayu.host` / `dayu.service` / `dayu.ui` / `dayu.fins` 反向依赖
- `dayu/runtime/__init__.py` 不 re-export `scene_prepare` 符号
- 只有测试文件 import `scene_prepare`，无生产代码反向依赖

### API 边界 — PASS

- `ScenePrepareRequest` / `PreparedSceneInputs` 均为 frozen dataclass，typed、可由 Service 显式映射
- 不携带 raw Host patch、callable 或任何非 typed 字段
- `SceneToolCatalog` 只保存 `name` + `tags`，不携带 callable

### manifest 解释权 — PASS

- `extends` 只允许 0 或 1 项，多父项在 `_parse_manifest:638` 和 `_resolve_scene:492` 两处 fail fast
- 循环继承在 `_resolve_scene:488` 通过 stack 检测
- `model` 必须由 concrete scene 显式声明（`_resolved_from_manifest:516-517`），不从父继承
- `runtime` / `conversation` / `tool_selection` 通过 `_resolve_optional_child_value` 支持子覆盖父

### prompt fragment 安全 — PASS

- `_resolve_contained_path:1223` 使用 `Path.resolve()` 处理 symlink 和 `..`，containment check 在 resolve 后执行
- 手动验证 symlink 逃逸被正确阻断
- 绝对路径在 `candidate.is_absolute()` 检查处被拒绝
- required fragment missing 按 `fail_closed` policy 失败（`scene_prepare.py:896-902`）

### context slots — PASS

- required missing: `_render_fragment_content:928-929` 检查并抛出
- unknown placeholder: `_replace_placeholders:968-971` 检查并抛出
- non-string value: `_replace_placeholders:977-978` 检查并抛出
- unresolved placeholder: `_render_fragment_content:937-942` 检查 `{{`/`}}` 残留并抛出
- 不执行表达式，不隐式 fallback，纯确定性文本替换

### tool selection — PASS

- `all` → `tool_names=None`（全量）
- `none` → `tool_names=frozenset()`（禁用）
- `select` → `names ∪ tag-matched`，unknown names fail（`scene_prepare.py:1005-1008`），tag 无匹配 fail（`scene_prepare.py:1010-1014`），`allow_empty=True` 时允许空结果

### digest / source refs — PASS

- `content_digest` 包含 manifest raw、fragment content、context slot values、available tools、selected tool names
- JSON 序列化使用 `sort_keys=True` + 固定 separators，确保稳定性
- source refs 区分 `MANIFEST` / `FRAGMENT` / `ASSEMBLY_INPUT` 三类
- 不误用 `ToolBundleSourceRef`

### 项目硬约束 — PASS

- 全模块中文 docstring，覆盖所有 public class / function / method
- 无 `Any`、`object`、无类型参数、无类型返回值
- 无胶水 seam、无兼容性 re-export / wrapper
- pyright 0 errors

## Verification Commands

```bash
# 已运行
pytest tests/runtime/test_scene_prepare.py tests/runtime/test_scene_tool_selection.py -q
# 21 passed

pytest tests/runtime/test_import_boundary.py tests/runtime/test_weak_typing_guard.py -q
# 8 passed

python -m pyright dayu/runtime/scene_prepare.py
# 0 errors, 0 warnings, 0 informations

git diff --check
# clean
```

## Verdict

**PASS**

Blocking findings count: 0。

1 个低严重度 finding（optional fragment missing 无独立测试）不阻塞 merge，可在后续 slice 或维护中补充。
