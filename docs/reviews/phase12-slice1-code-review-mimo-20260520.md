# Phase 12 Slice 1 Code Review

## Scope

- Mode: current changes
- Branch: `docs/phase12-design-discussion`
- Base: `main`
- Output file: `docs/reviews/phase12-slice1-code-review-mimo-20260520.md`
- Included scope:
  - `dayu/contracts/tool_source.py` (new) — canonical `ToolBundleSourceKind` / `ToolBundleSourceRef` ownership
  - `dayu/contracts/__init__.py` — package re-export of canonical source ref types
  - `dayu/host/tooling.py` — migration from local source ref definitions to canonical contracts import
  - `dayu/host/__init__.py` — unchanged, continues re-exporting source ref types from `dayu.host.tooling`
  - `dayu/runtime/tools_discovery.py` (new) — provider spec / callable protocol, import path / entry point resolution, `ToolBundle` aggregation
  - `dayu/runtime/__init__.py` — docstring update for tools_discovery capability
  - `tests/runtime/test_tools_discovery.py` (new) — provider aggregation, import path, entry point, duplicate identity, duplicate tool name, disabled, empty
  - `tests/host/test_tooling_options.py` — added canonical source ref identity assertion
  - `dayu/README.md` — runtime / contracts boundary and extension entry sync
  - `docs/host/implementation-control.md` — controller status update
  - `docs/reviews/phase12-slice1-implementation-codex-20260520.md` — implementation artifact (evidence only)
- Excluded scope: digest/reserved-name (Slice 2), ConfigLoader (Slice 3), ScenePrepare (Slice 4)
- Parallel review coverage: 无

## Findings

### 1-未修复-中-`_resolve_import_path` 未包装 `ModuleNotFoundError`

- **入口/函数**: `_resolve_import_path()` → `resolve_provider_callable()` → `ToolsDiscovery.discover()`
- **文件(行号)**: `dayu/runtime/tools_discovery.py:305`
- **输入场景**: provider import path 指向不存在的 Python 模块（例如 `"nonexistent_pkg.module:provider_fn"`）
- **实际分支**: `importlib.import_module(module_name)` 在 line 305 直接抛出 `ModuleNotFoundError`
- **预期行为**: 按 docstring（line 299: `:raises ToolsDiscoveryError:`）和 `tools_discovery` 的统一错误契约，所有 discovery 阶段错误应包装为 `ToolsDiscoveryError`，使调用方可以统一捕获
- **实际行为**: `ModuleNotFoundError` 以原始异常类型传播，调用方 `except ToolsDiscoveryError` 无法捕获
- **直接证据**:
  - `dayu/runtime/tools_discovery.py:305`: `module = importlib.import_module(module_name)` — 无 try/except 包装
  - `dayu/runtime/tools_discovery.py:299`: docstring 声明 `:raises ToolsDiscoveryError:` 但实际还可能抛出 `ModuleNotFoundError`
  - 验证：`_resolve_import_path('nonexistent_module_xyz:attr')` 抛出 `ModuleNotFoundError`，而非 `ToolsDiscoveryError`
- **影响**: 调用方预期 `ToolsDiscoveryError` 统一覆盖配置/解析错误的错误处理路径会被击穿；API 契约不完整
- **建议改法和验证点**:
  - 在 `importlib.import_module(module_name)` 外加 `try/except (ImportError, ModuleNotFoundError)` 包装为 `ToolsDiscoveryError`，保留 `from exc` 链
  - 补充对应测试：import path 指向不存在模块时应抛出 `ToolsDiscoveryError`
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

## Open Questions

- 无

## Residual Risk

- `_require_non_empty_text` / `_require_optional_non_empty_text` helper 函数在 `dayu/contracts/tool_source.py` 与 `dayu/runtime/tools_discovery.py` 中存在相同实现。当前可维护，若后续 contracts 公共校验 helper 增多，可考虑收敛到 contracts 内部共享模块。
- `discover_from_bindings()` line 230 的 `if not binding.spec.enabled: continue` 与 `discover()` line 205 的过滤逻辑重复。作为 public method 的防御性检查可接受，但增加了两条路径的维护一致性要求。
- Package entry point 测试使用 monkeypatch 的 `importlib.metadata.entry_points`，不验证真实安装包 metadata。真实插件分发路径可在后续 ConfigLoader / packaging 集成测试覆盖。
- `ToolsDiscoveryProviderOutput.source_refs` 类型为 `tuple[ToolBundleSourceRef, ...]`，但 `ToolsDiscovery` 不校验 source_refs 中的 `source_kind` 值与 provider 实际来源是否一致。当前设计由 provider 自声明，可接受。

## Validation Commands / Results

| 命令 | 结果 |
| --- | --- |
| `pytest tests/runtime/test_tools_discovery.py tests/host/test_tooling_options.py tests/host/test_package_exports.py -q` | 26 passed in 0.56s |
| `python -m pyright dayu/contracts dayu/runtime dayu/host tests/runtime tests/host` | 0 errors, 0 warnings, 0 informations |
| `pytest tests/runtime/test_import_boundary.py tests/runtime/test_weak_typing_guard.py -q` | 6 passed in 0.60s |
| `python -c "from dayu.host import ToolBundleSourceKind, ToolBundleSourceRef; from dayu.contracts import ToolBundleSourceKind as CK, ToolBundleSourceRef as CR; print(ToolBundleSourceKind is CK, ToolBundleSourceRef is CR)"` | `True True` |
| `git diff --check` | clean |
| 手动验证 `_resolve_import_path('nonexistent_module_xyz:attr')` | 抛出 `ModuleNotFoundError`（未包装为 `ToolsDiscoveryError`） |
| 手动验证 provider 返回空 `source_refs` 时 `discover_from_bindings` 行为 | 抛出 `ToolsDiscoveryError: provider test must return non-empty source_refs` |
| 手动验证所有 specs disabled 时 `discover()` 返回值 | `source_refs=()`, `definitions=()`, `provider_reports=()` |

## Verdict

**PASS**（含 1 项中等 non-blocking finding）

Blocking findings count: **0**

Finding 1（`ModuleNotFoundError` 未包装）是中等严重程度的 API 契约缺陷，不阻塞当前 slice 合并，但建议在 Slice 1 accepted commit 或后续 fix 中修复。该 finding 的修复风险低，改法明确，不影响其它逻辑。
