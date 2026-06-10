# WU-TOOLS-01-F03-R3 Code Review — AgentMiMo

## Scope

- Branch: `wu-tools-01-f03-web-ci-smoke`，未提交改动。
- 设计真源：`docs/host/design.md`、`docs/engine/design.md`
- 总控：`docs/host/issues-implementation-control.md`
- Plan：`docs/host/wu-tools-01-f03-r3-web-config-search-smoke-plan.md`
- Implementation artifact：`docs/reviews/wu-tools-01-f03-r3-implementation-codex.md`

审查范围：`dayu/config/tool_discovery.json`、`utils/smoke_web_ci.py`、`tests/tools/web/test_smoke_web_ci.py`、`tests/tools/web/test_web_tools_provider.py`、`tests/service/test_host_assembly.py`、`tests/runtime/test_config_loader.py`、`tests/README.md`、`docs/host/issues-implementation-control.md`。

---

## Findings

### F1 — search provider diagnostic cases 在 Docling blocker 激活时被跳过

**严重程度：Medium**
**文件：** `utils/smoke_web_ci.py` (`_execute_smoke` 函数，约 line 2669-2685)

当 `_has_docling_invocation_blocker(local_cases)` 为 `True` 时，`_execute_smoke` 提前返回，既不调用 `_run_search_provider_cases()`，也不将 search_cases 传入 `_summary_from_cases()`。这意味着如果 Docling 初始化失败，search provider 诊断也会被一起跳过。

Plan Slice 5 第 7 点明确说："所有 search provider cases 默认进入 diagnostic_only，exit_code=0，不影响 local fetch hard gate。即使 duckduckgo 失败，也只说明外部搜索路径诊断失败。" 这里的"local fetch hard gate"指的是 HTML/PDF/browser local fetch 路径，不是 Docling 初始化。Search provider 路径走的是 `ConfigLoader -> discover_service_tools -> search_web callable`，不依赖 Docling runtime。

当 Docling blocker 激活时，`_execute_smoke` 的 early return 路径没有 search_cases 参数传入 `_summary_from_cases()`，导致 summary JSON 中 `search_cases` 为空数组。用户看到 summary 的 search_cases=0 可能误以为 search diagnostics 没有设计进来。

**建议：** 将 `_run_search_provider_cases()` 的调用移到 `_has_docling_invocation_blocker` 检查之前，或至少在 early return 路径中也调用 search cases 并传入 summary。

---

### F2 — `test_search_provider_cases_are_typed_diagnostic_only` 中 `discovered_configs` 使用 `list[object]`

**严重程度：Low**
**文件：** `tests/tools/web/test_smoke_web_ci.py`（约 line 424）

```python
discovered_configs: list[object] = []
```

应为 `list[RuntimeConfig]`。当前类型为 `list[object]`，后续 `assert len(discovered_configs) == 1` 能通过 pyright 是因为 `object` 允许 `len()`，但丢失了类型信息。同一文件中 `loaded_overlay_dirs: list[Path]` 是正确的写法。

**建议：** 改为 `discovered_configs: list[RuntimeConfig] = []`，并 import `RuntimeConfig`（`smoke.RuntimeConfig` 已作为 type alias 可用）。

---

### F3 — `_classify_search_error_text` 中文硬编码作为分类信号

**严重程度：Low**
**文件：** `utils/smoke_web_ci.py`（`_classify_search_error_text` 函数，约 line 2086-2098）

```python
if "api_key" in normalized and "未配置" in normalized:
    return _BUCKET_PROVIDER_KEY_MISSING
...
if "所有 provider 均不可用" in error_text:
    return _BUCKET_PROVIDER_UNAVAILABLE
```

这两个中文字符串作为 secondary heuristic 用于分类 search provider 错误。它们依赖 `dayu/tools/web/web_search_providers.py` 中当前的错误消息文本。如果上游错误消息被修改（例如翻译成英文或改变措辞），这些 heuristic 会静默失效，落入通用的 `search_tool_execution_error` bucket。

这不是 bug——plan 第 5 节明确说"有限错误文本关键词只作为 secondary heuristic"，且 `_provider_api_key_present()` 和 `_classify_search_exception()` 提供了更可靠的 primary 分类路径。但需要确认这是 intentional trade-off 而不是遗漏。

**建议：** 确认此设计决策后无需修改。若要提高鲁棒性，可考虑让 `web_search_providers.py` 的错误包含结构化 error code 而非纯文本。

---

### F4 — `_OpenCancellationToken` 使用 `cast(CancellationToken, ...)` 绕过类型检查

**严重程度：Low**
**文件：** `utils/smoke_web_ci.py`（`_tool_context()` 函数，约 line 1199）

```python
cancellation_token=cast(CancellationToken, _OpenCancellationToken()),
```

`_OpenCancellationToken` 实现了 `CancellationToken` Protocol 的三个方法，structurally 满足协议。但使用 `cast` 而非直接传入，绕过了 pyright 的结构化类型检查。如果 `CancellationToken` Protocol 新增方法，`_OpenCancellationToken` 不会自动报错。

**建议：** 直接传入 `_OpenCancellationToken()` 不做 cast。如果 pyright 能正确推断 structural subtyping，cast 是多余的；如果不能，说明 Protocol 定义或实现有签名不匹配问题需要修复。

---

### F5 — `_ASSEMBLY_PROVIDER_CONFIG` 使用 module-level mutable dict literal

**严重程度：Low**
**文件：** `utils/smoke_web_ci.py`（约 line 984-992）

```python
_ASSEMBLY_PROVIDER_CONFIG: Final[JsonObject] = {
    "provider": "duckduckgo",
    ...
}
```

`Final` 保证变量绑定不变，但 dict 本身仍是 mutable。`_run_local_assembly_config_case` 中通过 `dict(_ASSEMBLY_PROVIDER_CONFIG)` 做了浅拷贝，安全。但 `_run_search_provider_cases` 中直接构造新的 dict 而非复用此常量，说明两个路径的 config 不一致（assembly 用 `duckduckgo`，search 用 per-provider），这是 intentional 但值得在注释中说明。

**建议：** 无需修改。当前设计是 intentional 的：assembly case 用固定 `duckduckgo` 验证装配链路，search cases 用 per-provider 验证搜索路径。

---

## 按审查重点逐项判断

### 1. 默认 web-tools.config 是否完整且不启用 web-tools

**通过。** `tool_discovery.json` 新增 `provider="auto"`、`fetch_truncate_chars=80000`、`playwright_channel="chrome"`、`playwright_storage_state_dir=""`，与 `WebToolsConfig` 默认值完全一致。`enabled=false` 保持不变。`test_default_runtime_config_files_load_as_typed_views` 断言了所有新字段。

### 2. ConfigLoader -> discover_service_tools -> Web provider -> ToolDefinition.callable 链路

**通过。** 三处测试覆盖：
- `test_config_loader_and_service_discover_web_tools_with_overlay_config`（`test_host_assembly.py`）：overlay 启用 web-tools → `ConfigLoader.load()` → `discover_service_tools()` → 发现 `search_web` / `fetch_web_page`。
- `test_search_web_receives_provider_config`（`test_web_tools_provider.py`）：config 参数闭进 `search_web` callable。
- `test_local_assembly_config_case_writes_overlay_and_truncate_artifact`（`test_smoke_web_ci.py`）：smoke 走完整 assembly 链路，验证 provider config 和 truncate spec。

### 3. local assembly config hard gate 是否证明 config 进入 provider config 和 truncate spec

**通过。** `_run_local_assembly_config_case` 显式断言 `truncate_max_chars == _ASSEMBLY_FETCH_TRUNCATE_CHARS`（3210），不匹配时 bucket 为 `web_assembly_config_mismatch`，exit_code 为 `_EXIT_LOCAL_FAILURE`。Artifact 中 `provider_config.fetch_truncate_chars` 和 `truncate_max_chars` 都记录了实际值。

### 4. typed search_cases，external_cases 是否只表示外部 URL fetch

**通过。** `SmokeSummary` 新增 `search_cases: tuple[SmokeCaseResult, ...]`，类型清晰。`external_cases` 不混入 search provider。`_summary_from_cases` 将 search_cases 独立传入。Artifact 中 search provider 细节（api_key_env、api_key_present、error_type 等）写入独立 artifact 文件，不进入 `SmokeCaseResult` 的弱类型 payload。

### 5. Tavily/Serper 缺 key、auth、quota、provider/network failure 是否 diagnostic-only 且不泄漏 secret

**通过。** Artifact 只写 `api_key_env`（env 变量名）和 `api_key_present`（bool），不写 key 值、Authorization header 或 request body。`_classify_search_exception` 优先用 `HTTPError.response.status_code` 等确定性信号，secondary 用错误文本关键词。Assembly 失败（config/discovery/tool missing）是 `status=failed, exit_code=非0`；搜索执行失败是 `status=diagnostic_only, exit_code=0`。

### 6. pytest 是否 deterministic

**通过。** 所有新增 pytest 通过 monkeypatch 替换 `search_public_web`、`_fetch_and_convert_with_playwright`、`_load_runtime_config_for_overlay`、`_discover_tools_by_name`、`ConfigLoader.load`、`discover_service_tools` 等外部依赖。不做 live network，不依赖真实 API key。真实 smoke live 行为只在 `utils/smoke_web_ci.py` 运行时出现。

### 7. 是否违反 AGENTS.md 约束

**通过，有一个 pyright 边界问题（F2）。** 新增代码全部有中文 docstring，无 `Any`/`object`/`hasattr`/`getattr` 滥用。`_OpenCancellationToken` 的 `cast` 是唯一可能绕过类型检查的点（F4）。无 God object/function，职责分离清晰（assembly case、search case、artifact writer、classifier 各自独立）。`dayu.runtime` 不被 smoke 直接 import 扩展——smoke 只 import `ConfigLoader`、`RuntimeConfig`、`discover_service_tools`，这些是 Service/Runtime 公共 API。

---

## Open Questions

1. **Docling blocker 跳过 search cases 是 intentional 还是遗漏？** Plan 没有显式讨论 Docling blocker 与 search cases 的关系。如果 Docling 初始化失败（如 runtime 不可用），search provider 诊断仍然有价值——它不依赖 Docling。建议确认后决定是否修复 F1。

2. **`cast(CancellationToken, ...)` 是否应该移除？** `_OpenCancellationToken` 的方法签名与 Protocol 完全匹配，structural subtyping 应该自动满足。如果 pyright 对此报错，说明有签名不匹配需要修复；如果不报错，cast 是多余的。

3. **中文错误文本 heuristic 是否需要 upstream 支撑？** 当前 `_classify_search_error_text` 依赖 `web_search_providers.py` 中的中文错误消息。如果 upstream 改措辞，heuristic 静默降级到通用 bucket。这是 intentional trade-off 还是需要结构化 error code？

---

## Verdict

**pass-with-findings**

实现正确覆盖了 Plan 的六个 Slice，config 装配链路有真实 evidence，search provider 诊断有完整分类和 artifact，pytest deterministic，无 secret 泄漏，无分层违反。F1（Docling blocker 跳过 search cases）是唯一需要确认的设计决策，其余为 Low severity 改进建议。Controller 复验的 133 passed / pyright 0 / smoke exit 0 结果可信。
