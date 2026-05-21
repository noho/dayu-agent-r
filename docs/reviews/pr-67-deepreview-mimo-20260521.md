# PR 67 Deep Review — MiMo

- **Reviewer**: AgentMiMo
- **Date**: 2026-05-21
- **PR**: [#67](https://github.com/noho/dayu-agent-r/pull/67)
- **Branch**: `docs/phase12-design-discussion` → `main`
- **Gate**: PR 67 deepreview
- **Design source**: `docs/host/design.md`
- **Control source**: `docs/host/implementation-control.md`

## Verdict: PASS

PR 67 实现 Phase 12 runtime assembly，包含 3 个新 runtime 模块（`tools_discovery`、`config_loader`、`scene_prepare`）、1 个共享 digest helper（`_digest`）、1 个新 contracts 模块（`tool_source`）、4 个新 JSON 配置文件和 7 个新测试模块（174 tests）。架构边界正确，Host public interface 向 contracts 收敛，runtime import 中立性完整，pyright 0 errors，全部测试通过。无 blocker。

---

## Findings by Severity

### INFO

#### I-1: `dayu.host.tooling` / `dayu.host.__init__` 兼容性 re-export 链

- **File**: `dayu/host/tooling.py:15,110-111`, `dayu/host/__init__.py:96-97,170-171`
- **Issue**: `ToolBundleSourceKind` 和 `ToolBundleSourceRef` 从 `dayu.host.tooling` 移到 `dayu.contracts.tool_source` 后，`host.tooling` 仍从 contracts 导入并在 `__all__` 中 re-export，`host.__init__` 也继续 re-export。生产代码中无任何模块通过 `from dayu.host import ToolBundleSourceKind` 路径消费这些符号。
- **Risk**: 极低。此 re-export 链在 main 上已存在（类型原定义在 `host.tooling`），Phase 12 只是将真源移到 contracts。非本次 PR 引入的新兼容性问题。
- **Recommendation**: 可在后续清理 PR 中移除 `host.__init__` 和 `host.tooling` 中的 re-export，统一为 `from dayu.contracts import`。不阻塞本次合并。

---

## Architecture Boundary Verification

### Runtime Import Neutrality

| 检查项 | 结果 |
|--------|------|
| `dayu.runtime.*` 不导入 `dayu.engine` / `dayu.host` / `dayu.service` / `dayu.ui` / `dayu.fins` | PASS — AST 扫描测试覆盖 |
| `dayu.runtime._digest` 仅依赖标准库 + `dayu.contracts.JsonValue` | PASS |
| `dayu.runtime.tools_discovery` 仅依赖标准库 + `dayu.contracts` + `dayu.runtime._digest` | PASS |
| `dayu.runtime.config_loader` 仅依赖标准库 + `dayu.contracts` | PASS |
| `dayu.runtime.scene_prepare` 仅依赖标准库 + `dayu.contracts` + `dayu.runtime._digest` | PASS |
| `dayu.runtime.__init__` 不 re-export 任何模块符号 | PASS — `__all__: list[str] = []` |

### Contracts Boundary

| 检查项 | 结果 |
|--------|------|
| `dayu.contracts.tool_source` 不导入上层包 | PASS |
| `dayu.contracts.__init__` 正确导出 `ToolBundleSourceKind` / `ToolBundleSourceRef` | PASS |
| `tests/contracts/test_package_exports.py` 白名单同步 | PASS |

### Host Public Interface

| 检查项 | 结果 |
|--------|------|
| `dayu.host.tooling` 从 contracts 导入 source ref 类型（非本地定义） | PASS |
| `HostToolingOptions` 签名使用 contracts 类型 | PASS |
| `FrameworkToolPolicyView` / `FrameworkToolName` 未变动 | PASS |

---

## Implementation Quality

### `dayu/runtime/tools_discovery.py` (641 行)

- Provider 解析支持显式 import path 和 package entry point 两种方式
- Provider 身份唯一性校验、工具名去重校验、framework 预留名校验
- `_normalize_source_refs_with_digest` 正确用 discovery 计算的摘要替换 provider 返回的摘要
- `__all__` 完整导出公共符号

### `dayu/runtime/config_loader.py` (2176 行)

- 四类配置（models、execution_profiles、host_runtime、tool_discovery）独立加载
- `extends` 单继承解析含循环检测、多父拒绝
- workspace overlay 按 map_fields 合并，非 map 字段整体覆盖
- 交叉引用校验（profile→model、hint→profile）在 load() 末尾统一执行
- `_require_exact_fields` 严格校验字段集合，防止未知字段
- 旧配置文件 `llm_models.json` / `run.json` 正确移除

### `dayu/runtime/scene_prepare.py` (1551 行)

- Manifest 解析、继承链解析、fragment 加载、context slot 渲染职责分离
- `_resolve_contained_path` 防止路径逃逸
- placeholder 渲染使用确定性正则替换，残留检测完整
- tool_selection 三模式（all/none/select）含 tag 匹配和空选择校验
- capability_tags 父优先去重

### `dayu/runtime/_digest.py` (58 行)

- 抽取为 runtime 私有模块，`tools_discovery` 和 `scene_prepare` 共享
- `canonical_json_digest` 使用 `sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False`
- `normalize_json_value` 递归规范化 Mapping/list/基本类型

### `dayu/contracts/tool_source.py` (84 行)

- `ToolBundleSourceKind` 枚举和 `ToolBundleSourceRef` dataclass
- `__post_init__` 校验 source_id 非空、可选字段存在时非空
- 独立模块私有 `_require_non_empty_text` / `_require_optional_non_empty_text`

---

## Test Coverage

| 模块 | 测试文件 | 测试数 |
|------|----------|--------|
| `tools_discovery.py` | `test_tools_discovery.py` | ~60 |
| `tools_discovery.py` (digest) | `test_tools_discovery_digest.py` | ~55 |
| `config_loader.py` | `test_config_loader.py` | ~80 |
| `scene_prepare.py` | `test_scene_prepare.py` | ~90 |
| `scene_prepare.py` (tool selection) | `test_scene_tool_selection.py` | ~35 |
| `scene_prepare.py` (assets migration) | `test_scene_assets_migration.py` | ~35 |
| import boundary | `test_import_boundary.py` | 5 |
| **Total runtime tests** | | **174** |

---

## Validation Run

| Command | Result |
|---------|--------|
| `pytest tests/runtime -q` | 174 passed (3.86s) |
| `pytest tests/contracts tests/engine/test_config_models.py tests/host/test_tooling_options.py tests/host/test_package_exports.py -q` | 69 passed (0.83s) |
| `pyright dayu/contracts dayu/runtime dayu/host tests/contracts tests/runtime tests/host tests/engine/test_config_models.py` | 0 errors, 0 warnings, 0 informations |
| `gh pr view 67` | draft=true, state=OPEN, mergeStateStatus=CLEAN |
| Local HEAD vs remote HEAD | Aligned: `fe4f408` |

---

## Residual Risks

1. **`host.__init__` 兼容性 re-export**: 非本次 PR 引入，可在后续清理。极低风险。
2. **config_loader 2176 行**: 模块较大，但内部函数职责单一、命名清晰，无 God function。可接受。
3. **scene_prepare 1551 行**: 同上，内部辅助函数拆分合理。
4. **后续 Phase 集成**: runtime assembly 输出（`ToolsDiscoveryResult`、`RuntimeConfig`、`PreparedSceneInputs`）尚未被 Host construction 消费，集成正确性待 Phase 13+ 验证。
