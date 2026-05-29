# Deep Review: Service 层、项目配置与测试覆盖

**审查日期**: 2026-05-29
**审查范围**: `dayu/service/`, `pyproject.toml`, `pyrightconfig.json`, 测试覆盖分析
**审查模式**: All Repository Mode - Evidence-based adversarial failure pass

---

## 1. Service 层审查 (`dayu/service/`)

### 1.1 Import 边界合规性 ✅ PASS

**证据**: AST 扫描 `dayu/service/host_assembly.py` 的所有 import：

| 依赖来源 | 模块 |
|----------|------|
| `dayu.contracts` | `ToolBundle`, `ToolBundleSourceRef`, `ToolDefinition` |
| `dayu.engine` | `AgentFallbackMode`, `AgentPolicy`, `RunnerCallOptions`, `RunnerSpec`, `provider_request_extension_from_json` |
| `dayu.host` | `api`, `context_policy`, `local_proxy`, `memory`, `tooling` |
| `dayu.runtime` | `assembly`, `config_loader`, `location`, `scene_prepare`, `tools_discovery` |

**结论**: 无 `dayu.config`、`dayu.ui`、`dayu.fins` 导入。边界测试 `test_service_does_not_import_forbidden_layers` 正确覆盖。

### 1.2 类型安全 ✅ PASS

- pyright 对 `dayu/service/` 报告 0 个诊断
- `test_weak_typing_guard` 通过 AST 扫描确认无 `Any`/`object`/裸容器注解
- 所有函数均有完整类型注解和返回值注解

### 1.3 Docstring 完整性 ✅ PASS

- 模块级 docstring 完整，说明了 Service 层定位和边界约束
- 所有公共函数和私有函数均有完整中文 docstring，包含参数、返回值、异常说明
- dataclass 字段均有 docstring 说明

### 1.4 安全性分析

#### 1.4.1 `_render_headers` secret 处理 ✅ PASS

**证据** (L939-964):
- 验证 `api_key` 非空且非纯空白
- 对 `api_key` 执行 `strip()` 清理
- 检测未解析的 `{{ENV_VAR}}` 占位符并抛出 `ValueError`
- 无 secret 日志泄漏

#### 1.4.2 `_resolve_project_path` 绝对路径处理 ⚠️ LOW RISK

**证据** (L1096-1116):
```python
def _resolve_project_path(workspace_root, configured_path):
    path = pathlib.Path(configured_path)
    if path.is_absolute():
        return path  # 直接返回，无验证
```

**问题**: 绝对路径绕过了 `relative_to` 逃逸检查。攻击者可通过配置 `sqlite.path: "/etc/passwd"` 指向任意路径。

**缓解因素**:
1. 配置来源是受信任的 workspace config 文件
2. Host runtime config 通常不受用户直接控制
3. 生产环境中 SQLite 路径由运维配置

**建议**: 考虑对绝对路径增加白名单验证或至少记录警告。

#### 1.4.3 `_resolve_prompt_asset_path` 路径安全 ✅ PASS

**证据** (L598-623):
- 禁止空路径
- 禁止绝对路径
- 使用 `resolve()` + `relative_to()` 防止目录逃逸
- 测试覆盖了空路径、绝对路径、`../` 逃逸三种场景

### 1.5 host_assembly 设计质量

#### 1.5.1 职责分离 ✅ PASS

- `discover_service_tools`: 纯工具发现
- `compose_open_host_options`: 完整 Host opener 装配
- `compose_submit_followup_request`: per-run followup 装配
- 私有函数职责单一，无 God function

#### 1.5.2 错误处理 ✅ PASS

- 16 个 raise 语句（14 个 ValueError, 2 个 RuntimeAssemblySelectionError）
- 所有错误消息包含具体上下文（字段名、值、期望）
- fail-fast 设计：配置非法时立即抛出，不静默降级

#### 1.5.3 Compactor scene 验证 ✅ PASS

**证据** (L640-689): 逐字段验证 compactor scene agent_policy：
- `max_iterations` 必填
- `continuation_max_attempts` 必填
- `allow_tool_calls` 必填
- `tool_execution_timeout_seconds` 必填
- `fallback_mode` 必填
- `fallback_prompt` 必填
- `continuation_prompt` 必填
- `max_consecutive_failed_tool_batches` 必填

---

## 2. 项目配置审查

### 2.1 pyproject.toml

#### 2.1.1 依赖声明 ✅ PASS
- 运行依赖版本约束合理（下界 + 上界）
- 测试依赖包含 `pytest-asyncio`、`pytest-cov`、`pytest-mock`、`pytest-timeout`
- 开发依赖包含 `pyright`、`ruff`、`black`

#### 2.1.2 pytest 配置 ⚠️ ISSUE

**问题**: `pyproject.toml` L137-138 引用 `pytest.ini` 但文件不存在：
```toml
[tool.pytest.ini_options]
# 具体 pytest 设置见 pytest.ini（保留为单一事实源）。
minversion = "7.4"
```

**影响**: pytest 配置分散，`minversion` 在 pyproject.toml 但其他配置可能在不存在的 pytest.ini 中。

**建议**: 要么创建 pytest.ini 并将所有配置移入，要么将所有配置统一到 pyproject.toml。

### 2.2 pyrightconfig.json

#### 2.2.1 覆盖范围 ✅ PASS
- `include`: `["dayu", "tests", "utils"]` 覆盖所有关键目录
- `exclude`: 正确排除 `workspace`、`__pycache__`、`.venv`

#### 2.2.2 类型检查模式 ⚠️ RECOMMENDATION

**问题**: 未设置 `typeCheckingMode`，默认为 `"basic"` 模式。

**建议**: 考虑设置为 `"strict"` 以获得更严格的类型检查，符合项目"禁止 `Any`/`object`"的编码约束。

---

## 3. 测试覆盖分析

### 3.1 Service 层测试覆盖 ✅ GOOD

| 测试文件 | 测试数 | 状态 |
|----------|--------|------|
| `test_host_assembly.py` | 19 | ✅ 全部通过 |
| `test_import_boundary.py` | 1 | ✅ 通过 |
| `test_weak_typing_guard.py` | 1 | ✅ 通过 |
| **总计** | **21** | **26 passed (含参数化)** |

**错误路径覆盖**: 10 个错误路径测试 vs 9 个成功路径测试，比率 1.11（良好）。

**测试的错误路径**:
- compactor scene 缺少 system prompt fragment
- compactor scene 缺少 agent_policy
- compactor agent_policy 缺少必填字段（3 个参数化）
- API key 缺失/空白
- 未解析的 env 占位符
- prompt asset 路径非法（3 个参数化）
- 工具发现缺少 source refs
- provider 缺少 location
- profile/model 窗口不兼容
- project path 逃逸

### 3.2 全仓覆盖缺口

**统计**: 112 个 dayu/ 模块，179 个测试文件。

**缺少直接测试的模块** (35 个):

| 包 | 模块 | 风险评估 |
|----|------|----------|
| contracts | `json_value`, `tool_await`, `tool_executor` | 低（可能被间接覆盖） |
| engine | `_default_runner`, `agent`, `provider_extensions` | 中 |
| engine/contracts | `agent_policy`, `engine_events`, `finish_reason`, `partial_tool_call`, `runner`, `tool_records` | 中 |
| engine/runners/openai | 12 个模块（`_types`, `cancellation_helpers`, `error_classifier`, `http_client`, 等） | 高（核心 runner 逻辑） |
| host | `_event_payload`, `_execution_config_projection`, `_public_validation` | 低（私有 helper） |
| host | `compact_payload`, `compaction_evidence`, `context_events`, `context_governance` | 中 |
| host/durable | `codec`, `errors`, `run_transition` | 中 |
| host | `evidence`, `opaque_ref`, `payload_resolution`, `read_api`, `recovery_process`, `terminal_summary_payload` | 中 |
| runtime | `_digest`, `assembly`, `location` | 低（可能被间接覆盖） |

**说明**: 许多 host 模块通过集成测试间接覆盖（`test_phase5/6/7_integration`, `test_public_*_smoke`）。

### 3.3 测试质量问题

#### 3.3.1 孤立的 `assert x is not None` ⚠️ MODERATE

**统计**: 56 个文件中 153 处孤立的 `assert x is not None`（无后续断言验证属性）。

**示例**:
```python
assert compactor_baseline is not None
# 后续直接访问属性，但没有显式断言
```

**影响**: 如果 `compactor_baseline` 类型错误地变为非 None 但结构错误，测试可能误通过。

**建议**: 在 `assert is not None` 后增加对关键属性的断言。

#### 3.3.2 `pytest.raises` 缺少 `match=` ⚠️ MODERATE

**统计**: 55 个文件中 263 处 `pytest.raises` 没有 `match=` 参数。

**影响**: 无法确认抛出的异常是否是预期的那个异常（可能捕获了意外的同类型异常）。

**建议**: 为关键错误路径的 `pytest.raises` 添加 `match=` 参数。

#### 3.3.3 测试导入私有 helper ⚠️ LOW

**证据**: `test_host_assembly.py` 导入 8 个私有函数（`_` 前缀）：
- `_agent_fallback_mode_from_config`
- `_compactor_agent_policy_from_scene_inputs`
- `_compactor_prompts_from_scene_inputs`
- `_render_headers`
- `_resolve_prompt_asset_path`
- `_resolve_project_path`
- `_tool_discovery_specs`
- `_tooling_options_from_discovery`

**Private/Public 比率**: 1.60（高于理想值 1.0）

**影响**: 测试与实现细节耦合，重构时需要同步更新测试。

**说明**: 对于 composition helper 这种场景，测试私有函数的边界验证是合理的，因为这些函数承载了关键的安全/正确性逻辑。

### 3.4 Mock 使用 ✅ GOOD

Service 层测试无 mock 使用，全部使用真实对象和真实配置文件，测试质量高。

---

## 4. 发现汇总

### 4.1 必须修复 (Must Fix)

无。

### 4.2 建议修复 (Should Fix)

| # | 问题 | 位置 | 严重性 |
|---|------|------|--------|
| S1 | pytest.ini 不存在但被 pyproject.toml 引用 | `pyproject.toml:137` | 低 |
| S2 | `_resolve_project_path` 绝对路径无验证 | `dayu/service/host_assembly.py:1108-1109` | 低 |

### 4.3 建议改进 (Nice to Have)

| # | 问题 | 位置 | 严重性 |
|---|------|------|--------|
| N1 | pyright 未设置 `typeCheckingMode: "strict"` | `pyrightconfig.json` | 信息 |
| N2 | 56 个测试文件有孤立 `assert is not None` | `tests/` | 低 |
| N3 | 55 个测试文件的 `pytest.raises` 缺少 `match=` | `tests/` | 低 |
| N4 | 35 个 dayu/ 模块缺少直接测试 | `dayu/` | 中 |

---

## 5. 验证清单

- [x] Service 层 import 边界合规（无 config/ui/fins 导入）
- [x] Service 层 pyright 零诊断
- [x] Service 层 26 个测试全部通过
- [x] Service 层弱类型守卫通过
- [x] host_assembly 所有函数有完整 docstring
- [x] secret 处理无泄漏风险
- [x] 路径解析有逃逸保护（prompt asset）
- [x] pyright 覆盖所有 dayu/ 子目录
- [x] 测试无 mock 使用

---

## 6. 结论

**Service 层质量**: 优秀。import 边界严格、类型安全、docstring 完整、错误处理健壮、测试覆盖充分。

**配置质量**: 良好。pyright 覆盖范围完整，但 pytest 配置有轻微不一致。

**测试覆盖**: 良好。Service 层测试质量高（无 mock、错误路径覆盖充分），但全仓有 35 个模块缺少直接测试（部分被集成测试间接覆盖）。

**整体评估**: 无需阻塞性问题。建议修复 pytest 配置不一致和考虑绝对路径验证。
