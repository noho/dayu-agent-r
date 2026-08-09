# Code Review

## Scope

- Mode: current changes (S5/F05 of PR 190)
- Branch: `codex/interactive-oracle`
- Base: `c556df2b`
- Output file: `docs/reviews/wu-cli-conformance-f01-f07-s5-code-review-mimo.md`
- Included scope:
  - `dayu/config/prompts/manifests/interactive.json` (唯一生产变更)
  - `tests/runtime/test_scene_assets_migration.py`
  - `tests/runtime/test_scene_prepare.py`
  - `tests/service/test_entrypoint_runtime_interactive_path.py`
  - `tests/tools/test_combined_tools_acceptance.py`
  - `docs/reviews/wu-cli-conformance-f01-f07-s5-implementation-codex.md` (implementation artifact)
  - Accepted plan §7 (`docs/reviews/wu-cli-conformance-f01-f07-plan-codex.md:582-638`)
  - Frozen oracle predicate `interactive.28-tool-registration-boundary` (`docs/cli_ci_oracles.json`)
  - Frozen scenario `interactive.interactive.tool-registration.no-preprocess` (`docs/cli_ci_scenarios.json`)
  - CLI CI design (`docs/cli_ci.md`)
  - Manifest → discovery → Service → Host → Engine chain (走读 `scene_prepare.py`, `host_assembly.py`, `entrypoint_runtime.py`, `admission.py`, `dispatch.py`, `tool_runtime.py`)
  - Preprocess provider independence (`preprocess_provider.py`, `preprocess_tools.py`, `tool_discovery.json`)
- Excluded scope: 无
- Parallel review coverage: 无

## Findings

未发现实质性问题。

### 验证记录

**1. 唯一生产变更确认**

`git diff c556df2b -- dayu/config/prompts/manifests/interactive.json` 精确为一行删除：从 `tool_tags_any` 移除 `"fins-preprocess"`。`fins-read`、`fins-download`、`web`、`utils` 的值与顺序不变。其它 tag、scene/model/runner hint/agent policy/default/fragment/context slot/config 字段均不变。`git diff c556df2b -- dayu/fins/tools/ dayu/cli/ dayu/service/ dayu/host/ dayu/engine/` 为零 diff。

**2. Manifest → discovery → Service → Host → Engine 链验证**

沿真实代码路径逐行走读：

- `interactive.json` 的 `tool_tags_any` 为 `["fins-read", "fins-download", "web", "utils"]`，无 `"fins-preprocess"`。
- `prepare_scene()` → `_select_tools()` → `catalog.names_for_any_tag({"fins-read", "fins-download", "web", "utils"})`。`start_fins_preprocess` 的 tags 为 `("fins", "fins-preprocess")`（`preprocess_tools.py:172`），与 `tool_tags_any` 交集为空（`isdisjoint=True`），不被选中。
- `discover_service_tools()` 发现所有 provider 的工具，不按 tag 过滤。`start_fins_preprocess` 仍在 discovery bundle 中。
- `compose_submit_followup_request()` 将 `scene_inputs.tool_selection.tool_names` 传入 `SubmitFollowupRequest.tool_names`。
- Host dispatch 的 `_candidate_tool_selection()` 调用 `validate_effective_tool_facts_runtime()` 取得 `selected_business_tool_names`，再由 `EffectiveToolBundleBuilder.build()` 的 `_selected_business_definitions()` 按 name 过滤（`tool_runtime.py:2681`）。最终 `tool_schemas` 不含 `start_fins_preprocess`。

**3. Oracle/Senario 合规**

Oracle predicate `interactive.28-tool-registration-boundary`：
- expected[0] "interactive可以注册财报读取与下载工具，但effective tool set不向Host注册start_fins_preprocess" — 满足。
- expected[1] "start_fins_preprocess实现代码可以保留" — 满足（SHA-256 不变：`f258bd...` / `38b8fb...`）。
- forbidden[0] "interactive scene、tool tag或Service assembly把start_fins_preprocess注册进本次Host Run" — 未违反。
- forbidden[1] "为满足interactive边界而删除独立preprocess工具实现" — 未违反。

**4. 独立 preprocess provider 不受影响**

`test_preprocess_provider_remains_independently_discoverable_and_callable` 直接调用 `preprocess_provider.discover_tools()`，断言返回 `start_fins_preprocess` 定义，且 callable 返回 `ToolAwaitingOutcome`（`await_kind=EXTERNAL_JOB`）。该测试不依赖 manifest，不经过 scene prepare 链。

**5. WeChat 不受影响**

`wechat.json` 的 `tool_tags_any` 仍包含 `"fins-preprocess"`。`test_wechat_prepared_output_keeps_download_preprocess_guidance` 断言 WeChat scene 的 `selected` 包含 `start_fins_preprocess` 且 system prompt 包含预处理指引。

**6. 未在下游按 name 过滤**

`grep -rn "start_fins_preprocess" dayu/service/ dayu/host/ dayu/cli/ dayu/runtime/` 为零命中。过滤纯粹通过 manifest 的 `tool_tags_any` → `names_for_any_tag()` 实现。

**7. 测试不是 mock name set 自证**

- `test_interactive_real_host_effective_schemas_exclude_preprocess`：读取真实 package manifest，走真实 discovery → scene prepare → Service assembly → 真实 Host admission/dispatch，在记录型 deterministic Engine worker 收到的最终 `AgentRunRequest.tool_schemas` 上断言。这是 owner-level integration test，不是 mock name set。
- `test_interactive_manifest_preserves_exact_non_preprocess_tool_selection`：读取真实 `interactive.json` 文件，断言 `tool_selection` 对象结构与值。
- `test_scene_assets_migration.py` 使用 `_fake_tool_catalog()`（手动构造的 `SceneToolCatalog`），但其 tags 与真实 tool definitions 一致。该测试验证 scene prepare 逻辑，不是 tool discovery，fake catalog 是合理的测试夹具。

**8. JSON/类型/test 断言脆弱性**

- `test_interactive_manifest_preserves_exact_non_preprocess_tool_selection` 断言 `tool_selection` 的完整对象（包括 `mode`、`tool_names`、`tool_tags_any`、`allow_empty`）。如果 manifest 新增字段（如 `tool_tags_all`），测试会失败。这是 intentional regression guard，不是脆弱断言。
- 所有测试使用 `frozenset` 或 `in`/`not in` 做 name 断言，不依赖顺序。
- `test_interactive_real_host_effective_schemas_exclude_preprocess` 使用 `frozenset(schema.function.name ...)` 做 name set 断言，不依赖 schema 顺序。

**9. 验证结果**

- JSON：`python -m json.tool` 通过。
- Focused pytest：`79 passed, 3 warnings`（warning 来自 edgar 依赖的既有 deprecation）。
- Focused pyright：`0 errors, 0 warnings, 0 informations`。
- Full pyright：`0 errors, 0 warnings, 0 informations`。
- `git diff --check`：通过。
- 无 staged files。

## Open Questions

无。

## Residual Risk

- **LOW / covered by S8**：frozen scenario 要求在 fixed clean commit 上重跑真实 provider 的 interactive effective tool set 与 download/list/read 跨轮链。S5 已以真实 manifest/discovery/Service/Host/Engine owner test 闭合静态与本地 integration contract，但未越权执行 S8 的 immutable CLI evidence bundle。
- **LOW / covered by S8**：真实 LLM 是否在 download 后选择正确 list/read 路径属于 provider/evidence 稳定性，不是本 slice 的 tool registration owner。最终 schema 已证明能力存在；真实模型行为留给 frozen scenario 重跑。

## Verdict

S5/F05 实现与 accepted plan §7、frozen oracle predicate `interactive.28-tool-registration-boundary` 和 frozen scenario `interactive.interactive.tool-registration.no-preprocess` 完全一致。唯一生产变更确实只删 interactive manifest 的 `fins-preprocess` tag，顺序与其余配置不变。真实 manifest → discovery → Service → Host → Engine effective schema 无 `start_fins_preprocess` 且仍含 download/list/read。独立 preprocess provider/调用与 WeChat 不受影响。未在下游按 name 过滤，未删除实现。测试不是 mock name set 自证。JSON/类型/test 断言不脆弱。未发现实质性问题。
