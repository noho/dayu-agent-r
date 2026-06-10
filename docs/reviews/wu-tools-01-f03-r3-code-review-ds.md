# WU-TOOLS-01-F03-R3 Code Review Artifact

## Gate / Scope

- Gate: code review
- Work unit: `WU-TOOLS-01-F03-R3`
- Design source: `docs/host/design.md`、`docs/engine/design.md`
- Plan source: `docs/host/wu-tools-01-f03-r3-web-config-search-smoke-plan.md`
- Controller adjudication: `docs/reviews/wu-tools-01-f03-r3-plan-review-controller-adjudication.md`
- Implementation artifact: `docs/reviews/wu-tools-01-f03-r3-implementation-codex.md`
- Review scope: 当前 git diff（8 files, 1806+ 17-）与未跟踪 plan/review/implementation docs

## Controller 复验

- `pytest tests/runtime/test_config_loader.py tests/service/test_host_assembly.py tests/tools/web/test_web_tools_provider.py tests/tools/web/test_smoke_web_ci.py tests/tools/web/test_diagnose_web_access.py -q`: 133 passed, 3 warnings
- `python -m pyright dayu/ tests/ utils/`: 0 errors, 0 warnings, 0 informations
- `python utils/smoke_web_ci.py`: exit 0, summary passed, local_cases 4, external_cases 2, search_cases 4, diagnostic_only 6
- `git diff --check`: passed
- 输出目录: `workspace/output/web_smoke/web-smoke-20260610T063755Z`

---

## Findings

### S1 — Smoke summary `hard_gate_cases` 正确包含 search_cases 的 assembly failure，但需要确认观测路径不被重复计算

- 文件: `utils/smoke_web_ci.py:1970`
- 当前实现:
  ```python
  hard_gate_cases = tuple(local_cases) + tuple(search_cases)
  ```
  这意味着 search provider ConfigLoader 或 discovery 失败（status=failed, exit_code=2）会上升到 smoke exit code 2。
- 分析: Plan Slice 5 step 2 明确要求 "ConfigLoader.load() 或 discover_service_tools() 失败属于 local assembly / infra failure，不归类为 provider diagnostic-only bucket，不得被外部 provider 容错逻辑吞掉。" 当前实现正确遵循该设计。
- 风险: 4 个 search provider case 各自独立调用 `ConfigLoader.load()`。如果包内 `models.json` / `execution_profiles.json` 等非 tool_discovery 配置文件损坏，会产出 4 条重复 failure artifact，每条都带 `exit_code=2`。不过 smoke exit_code 只取 max，不会溢出。
- 处置: 无代码修改需求，设计上可接受。建议后续考虑将 search provider assembly failure 聚合为一条 assembly-sanity case 而不是按 provider 重复。

### S2 — `_run_local_assembly_config_case` 的 assembly 链路真实且不绕过生产装配

- 文件: `utils/smoke_web_ci.py:2266-2466`
- 验证:
  1. `_load_runtime_config_for_overlay` → `ConfigLoader(package_config_dir=_PACKAGE_CONFIG_DIR).load(workspace_config_dir=...)` — 完整加载五类配置。
  2. `_discover_tools_by_name` → `discover_service_tools(config)` — 走 Service 真实工具发现。
  3. `fetch_definition.callable(_tool_call("fetch_web_page", {"url": fixture_urls.html_url}), _tool_context())` — 真实调用闭包。
  4. `truncate_max_chars != _ASSEMBLY_FETCH_TRUNCATE_CHARS` 检查 → 验证 config 进入 truncate spec。
- 证据: pytest 中 `test_web_tool_discovery_config_survives_service_mapping` (test_host_assembly.py:856) 与 `test_config_loader_and_service_discover_web_tools_with_overlay_config` (test_host_assembly.py:890) 各自覆盖 Service mapping 与闭环发现；`test_local_assembly_config_case_writes_overlay_and_truncate_artifact` (test_smoke_web_ci.py:156) 覆盖 smoke 级 assembly case 编排。
- 结论: 链路真实覆盖，不绕过生产装配。通过。

### S3 — 默认 `web-tools.config` 字段完整且 Web tools 保持 disabled

- 文件: `dayu/config/tool_discovery.json:62-78`
- 当前配置:
  ```json
  "config": {
    "provider": "auto",
    "request_timeout_seconds": 20.0,
    "max_search_results": 8,
    "fetch_truncate_chars": 80000,
    "playwright_channel": "chrome",
    "playwright_storage_state_dir": "",
    "allow_private_network_url": false
  }
  ```
  `enabled: false`、`allow_empty: true` 保持不变。
- 断言覆盖: `test_default_runtime_config_files_load_as_typed_views` (test_config_loader.py:400-408) 逐字段验证。
- 结论: 字段完整，Web tools 默认不启用。通过。

### S4 — Typed `search_cases` 未引入 metadata 弱类型口袋

- 文件: `utils/smoke_web_ci.py:433`
- `SmokeSummary.search_cases: tuple[SmokeCaseResult, ...]` — 元素为 `SmokeCaseResult`（frozen slots dataclass，9 个强类型字段）。
- `external_cases` 只保留外部 URL fetch cases，search provider cases 只进入 `search_cases`。
- `SmokeCaseResult` 无 `metadata` 字段。search 细节（provider、api_key_present、error_type 等）只写独立 `web-smoke-search-v1` artifact。
- 测试覆盖: `test_search_provider_cases_are_typed_diagnostic_only` (test_smoke_web_ci.py:224) 断言 `search_cases` 数量、元素类型、与 `external_cases` 隔离。
- 结论: 类型清晰，无弱类型泄漏。通过。

### S5 — Tavily/Serper 缺 key、auth、quota、provider/network failure 均为 diagnostic-only 且不泄漏 secret

- 文件: `utils/smoke_web_ci.py:2742-3063`
- 关键路径:
  1. `_run_single_search_provider_case` 通过 `os.environ.get(api_key_env, "").strip()` 读取 key 存在性，artifact 只写 `api_key_env` 和 `api_key_present: true/false`。
  2. `_classify_search_exception` 优先使用异常类型（`requests.HTTPError` → status_code, `requests.Timeout`/`ConnectionError` → network）做 bucket 分类。
  3. `_classify_search_error_text` 中关键词匹配作为 secondary heuristic。
  4. artifact 不写 key 值、Authorization header、request body。
- 显式 provider fallback 不掩盖 key missing: `_search_failure_case` 中 `api_key_present` 由 env 检查决定（line 2818），不由 provider 内部错误文本决定。
- 所有 search callable failure（除 ConfigLoader/discovery assembly 失败外）均 `exit_code=0`，不改变 local hard gate。
- 结论: 分类确定性合理，secret 不泄漏。通过。

### S6 — pytest 保持 deterministic，不依赖 live network/credential

- 文件: `tests/tools/web/test_smoke_web_ci.py`、`tests/tools/web/test_web_tools_provider.py`
- 所有测试通过 monkeypatch 控制:
  - smoke 测试 monkeypatch `_run_diagnostic_command` / `_running_local_fixture_server` / `_load_runtime_config_for_overlay` / `_discover_tools_by_name`
  - Web provider 测试 monkeypatch `web_tools.search_public_web` / `web_tools._fetch_and_convert_content` / `web_tools._fetch_and_convert_with_playwright`
- 无 `TAVILY_API_KEY` / `SERPER_API_KEY` 依赖。
- 真实 live failure 只在 `python utils/smoke_web_ci.py` 运行时以 diagnostic-only 出现。
- 结论: deterministic，不依赖 live network/credential。通过。

### S7 — AGENTS.md 约束检查

逐一检查:

- **分层约束**: `utils/smoke_web_ci.py` 直接 import `dayu.runtime.config_loader`、`dayu.service.host_assembly`、`dayu.contracts.*`。这是仓库级 smoke harness（`utils/` 下），Plan 与 controller adjudication 明确授权 import ConfigLoader、runtime location helper 与 `discover_service_tools()`，不新增 production helper/wrapper/facade。通过。
- **类型约束**: 无 `Any`、`object`、无类型参数。`_OpenCancellationToken` 使用 `cast(CancellationToken, ...)` 在 smoke harness 中可接受。`JsonObject = dict[str, JsonValue]` 定义清晰。通过。
- **docstring**: 所有新函数提供完整中文 docstring，至少含参数、返回值、异常。通过。
- **无 hasattr/getattr 滥用**: 全文搜索未发现。通过。
- **无魔法数字/字符串**: 所有常量定义为模块级 `Final` 变量。通过。
- **无兼容性代码**: 无 legacy re-export、wrapper、facade。通过。
- **无 extra payload**: 未发现把显式参数放入 extra payload 袋。通过。
- **模块间依赖最小化**: smoke 脚本的依赖是单向的：`dayu.runtime` ← `dayu.service` ← `dayu.contracts`，均遵循架构分层。通过。
- **test_HOST_ASSEMBLY.py import 边界**: `test_host_assembly.py` 新增 import 均在 `dayu.runtime.config_loader`、`dayu.runtime.assembly`、`dayu.runtime.location` 内，均为 Service 层可访问的下层模块。通过。

**未发现问题。**

### S8 — 低严重度观察 (informational)

1. **`_OpenCancellationToken` 重复定义** — `utils/smoke_web_ci.py:227` 与 `tests/tools/web/test_web_tools_provider.py:42` 各自定义了语义一致的 helper class。两者处于不同模块（smoke harness vs test），当前不造成实际维护问题。

2. **Search artifact 中的 provider_config 全量写入** — `_write_search_artifact` (line 3097) 写入 `"provider_config": dict(provider_config)`，包含 `playwright_channel`、`playwright_storage_state_dir` 等非搜索字段。不影响正确性，artifact 可审计。

3. **`--diagnostic-only-external` CLI flag 冗余** — `_options_from_namespace` (line 3464):
   ```python
   diagnostic_only_external=bool(namespace.diagnostic_only_external) or external_url_file is not None,
   ```
   当 `external_url_file` 不为 None（默认值始终不为 None）时 `diagnostic_only_external` 恒为 True。该 flag 是显式语义确认，不引发错误行为。

---

## Open Questions

1. `_summary_from_cases` (line 1970) 将 search_cases 纳入 `hard_gate_cases` 的设计在当前 plan 下正确，但若以后 search provider cases 数量增加，应考虑将 assembly 级失败聚合为一条 sanity case 减少冗余 artifact。

2. `_ASSEMBLY_FETCH_TRUNCATE_CHARS = 3210` 为 smoke harness 常量，与包内默认 `fetch_truncate_chars = 80000` 不一致是预期行为（overlay 使用自定义值验证闭包传递）。无需修改。

---

## Verdict

**pass**

所有重点问题均已验证通过:
- 默认配置字段完整，Web tools 保持 disabled。
- ConfigLoader → discover_service_tools → Web provider → ToolDefinition.callable 链路真实覆盖，smoke 未绕过生产装配。
- Local assembly config hard gate 确实证明 provider config 与 truncate spec 从配置闭进工具。
- Typed `search_cases` 类型清晰，`external_cases` 只表示外部 URL fetch，无 metadata 弱类型口袋。
- Tavily/Serper key/auth/quota/network failure 均为 diagnostic-only，不泄漏 secret，显式 provider fallback 不掩盖 key missing。
- pytest deterministic，不依赖 live network/credential。
- 未违反 AGENTS.md 的分层、类型、docstring、README、无 Any/object/hasattr/getattr 滥用约束。
- 实现 artifact 与 Plan 一致，controller adjudication 要求均已满足。
