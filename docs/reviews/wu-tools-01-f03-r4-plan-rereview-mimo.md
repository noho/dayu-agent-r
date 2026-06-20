# WU-TOOLS-01-F03-R4 Plan Re-review — AgentMiMo

## Reviewed Target And Scope

- **Target**: `docs/host/host-issues/wu-tools-01-f03-r4-tools-discovery-spec-plan.md`
- **Scope**: Re-review after plan-fix gate.验证 7 个 accepted findings 是否已在 plan 中修复，判断修复后 plan 是否 code-generation-ready。
- **Prior review**: `docs/reviews/wu-tools-01-f03-r4-plan-review-mimo.md`
- **Plan-fix**: `docs/reviews/wu-tools-01-f03-r4-plan-fix-codex.md`
- **Control truth**: `docs/host/issues-implementation-control.md` WU-TOOLS-01-F03-R4 Controller plan-review judgment
- **Re-review timestamp**: 20260621-073322

## Re-review Scope

只验证 accepted findings 是否已修复，不重新扩大范围。只报告新发现的 blocking 问题（如果它们直接来自 plan-fix 变更或会阻止 implementation）。

## Prior Finding Final Status

### F01 — wait adapter effective config — 已修复

**验证方法**：检查 plan Exact Implementation Decisions 第 7 点和 Slice 2 的 wait adapter 路径描述。

**Evidence**：

- Decision 7 明确要求：`_fins_wait_adapter_registry_from_provider_configs(...)` 必须接收经过 `_effective_tool_provider_config(...)` 处理后的 configs，不得读取 raw packaged `"workspace/"`。
- Slice 2 "Exact changes" 第 3 点明确：`assemble_effective_tool_provider_configs(...)` 产出 effective configs → `ServiceDiscoveredTools.effective_provider_configs` → `_tooling_options(...)` / `_fins_wait_adapter_registry_from_provider_configs(...)` 消费 effective tuple。
- Slice 2 "Tests / validation" 包含：wait adapter registry construction 使用同一 effective absolute workspace root 且不再看到 raw relative `"workspace/"`。

**结论**：修复完整。两条路径（discovery 和 wait adapter）都消费同一个 effective config tuple，不存在 raw `"workspace/"` 泄漏到 wait adapter 的路径。

---

### F02 — workspace/ 解析基准 — 已修复

**验证方法**：检查 Decision 5 的解析语义描述和 Slice 2 的测试断言。

**Evidence**：

- Decision 5 明确语义：`"workspace/"` 是相对路径，以 Service request/runtime `workspace_root` 为基准。当 `workspace_root=/path/to/project` 时，effective Fins `workspace_root` 为 `/path/to/project/workspace`。
- Decision 5 同时规定：相对路径且 Service request/runtime `workspace_root` 为 `None` 时，在 Service assembly 中 fail fast with precise message。
- Decision 5 规定：绝对路径 `~` 展开后 `resolve(strict=False)`；相对路径用与 `_resolve_project_path(...)` 相同的 containment semantics 解析。
- Slice 2 "Tests / validation" 包含：packaged `"workspace/"` 在 Service `workspace_root=/path/to/project` 下解析为 `/path/to/project/workspace` 且 raw config 不被 mutate。

**结论**：修复完整。语义明确，open question 已从"implementation owner must verify"提升为 plan 层面的确定决策。

---

### F03 — default scene upload exposure 验证 — 已修复

**验证方法**：检查 Slice 4 scene manifest 处理逻辑和测试验证步骤。

**Evidence**：

- Decision 13 详细记录了 manifest evidence：当前默认 scenes 通过 broad `"fins"` tag 匹配工具，`start_fins_upload` 标签含 `"fins"`，因此 upload 默认注册后会被默认 scene 选中。
- Decision 13 要求：用显式 `tool_names` 替代 broad `"fins"` tag 选择，只保留 Fins read/download/preprocess 工具和 web 工具的 tag 选择。
- Slice 4 "Exact changes" 包含：`ScenePrepare` 相关的 manifest 修改和测试断言，证明默认 scenes 不再通过 broad `"fins"` tag 选中 `start_fins_upload`。
- Slice 4 "Tests / validation" 包含：explicit manifest check with catalog containing all tools，断言 no default scene selects `start_fins_upload`。

**结论**：修复完整。scene exposure 从 residual risk 提升为 current-WU implementation item，有具体实施步骤和验证命令。

---

### DS F1 — Doc provider 单一路径 — 已修复

**验证方法**：检查 Decision 10 的 Doc provider 行为描述。

**Evidence**：

- Decision 10 要求：packaged `doc-tools.enabled=false`，且 enabled Doc provider 在 `allowed_paths` missing/empty 时必须 fail fast with Doc-specific error `doc provider config.allowed_paths must contain at least one path when doc-tools is enabled`。
- Decision 10 明确：不得让 implementation 在 `enabled=false` 和 provider fail-fast 之间选择，两者都是 required。
- Slice 5 包含：Doc provider 测试覆盖 enabled + empty `allowed_paths` raises Doc-specific error 而非返回 empty definitions。

**结论**：修复完整。单一路径明确，implementation agent 不需要做二选一裁决。

---

### DS F2 — allow_empty 删除 slice 原子性 — 已修复

**验证方法**：检查 Slice 1 的允许文件列表和 exact changes。

**Evidence**：

- Slice 1 包含 `tool_discovery.json`、`config_loader.py`、`tools_discovery.py`、`host_assembly.py` 和相关测试，确保 provider-level `allow_empty`、`ToolsDiscoveryProviderSpec.allow_empty` 和 `host_assembly.py` mapping 在同一 slice 删除。
- Slice 1 "Data flow" 明确：codebase must remain importable and Service tool discovery callable after this slice；no intermediate state where spec no longer accepts `allow_empty` but `host_assembly.py` still passes it。

**结论**：修复完整。三个删除点在同一 slice，不会产生中间不可导入状态。

---

### DS F3 — Web provider 非空证据 — 已修复

**验证方法**：检查 Decision 11 和 plan "First-principles Judgment And Direct Code Evidence" 中的 Web provider 描述。

**Evidence**：

- Decision 11 记录：packaged import path `dayu.tools.web:discover_tools` 转发到 `dayu/tools/web/provider.py`，`_validate_web_definitions(...)` 要求工具名精确为 `("search_web", "fetch_web_page")`，无正常空输出路径。
- "Direct Code Evidence" 第 8 点确认相同证据。

**结论**：修复完整。Web provider 空输出风险已通过直接代码证据排除，plan 正确保留了该 provider 的默认 enabled 行为。

---

### DS F4 — download/preprocess 非空证据 — 已修复

**验证方法**：检查 Decision 12 和 plan "Direct Code Evidence" 中的 download/preprocess 描述。

**Evidence**：

- Decision 12 记录：`financial-download-tools` 和 `financial-preprocess-tools` 各自在有效绝对 `workspace_root` 下返回 exactly one awaiting tool definition。
- "Direct Code Evidence" 第 9 点确认：`download_provider.py` 返回 `(build_fins_download_tool(...),)`，`preprocess_provider.py` 返回 `(build_fins_preprocess_tool(...),)`，两者没有空 definitions 分支。

**结论**：修复完整。download/preprocess provider 空输出风险已通过直接代码证据排除。

---

## New Findings

### F04-新发现-低-Scene manifest 显式 tool_names 列表完整性未在 plan 中显式枚举

- **位置**: Decision 13 / Slice 4
- **问题类型**: 测试缺口
- **当前写法**: Decision 13 列出了"Use explicit `tool_names` for `list_documents`, `get_document_sections`, `read_section`, `search_document`, `list_tables`, `get_table`, `get_page_content`, `get_financial_statement`, `query_xbrl_facts`, `start_fins_download` and `start_fins_preprocess`"，但这些工具名来自 plan 的直接代码证据，而非 manifest 文件本身的 tool_names 列表。
- **反例/失败场景**: 如果某个默认 scene manifest 的 `tool_names` 中已经包含了某个 Fins 工具名（而非仅靠 tag 匹配），那么改为显式 `tool_names` 时需要保留原有的显式名称。Implementation agent 如果只按 Decision 13 的列表替换，可能会遗漏已经显式命名的工具。
- **为什么有问题**: 这不是 plan 的结构性缺陷，而是 implementation agent 需要在实现时核对 manifest 文件的细节。Decision 13 已经给出了正确的工具名列表和预期行为，implementation agent 在修改 manifest 时需要读取当前 manifest 文件确认。
- **直接证据**: plan "Direct Code Evidence" 第 10 点已记录当前 manifests 的 `tool_tags_any` 使用情况。
- **影响**: 低。Implementation agent 在 Slice 4 修改 manifest 时自然会读取当前文件内容，不太可能遗漏。
- **建议改法和验证点**: plan 已经足够。Slice 4 的 manifest check 验证命令能捕获遗漏。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 低。不阻塞 implementation。

---

## Residual Risks / Uncovered Areas

1. **Upload local file read authorization**（plan 已记录为 deferred）：未来 Host / policy 设计。无 owner，plan 正确标记为 non-goal。
2. **Provider dataclass defaults 与 packaged defaults drift**：plan 通过测试 assert packaged defaults 降低 drift 风险，长期仍需维护纪律。不阻塞 implementation。
3. **Scene manifest 显式 tool_names 的完整枚举**（见 F04）：implementation agent 在 Slice 4 修改 manifest 时需核对当前文件。Slice 4 的验证命令能捕获遗漏。不阻塞 implementation。

## Plan Review Conclusion

**Verdict**: `pass`

**Blocking findings**: 0

**Non-blocking new findings**: 1（F04 低严重程度，不阻塞 implementation）

**可进入 accepted plan commit gate**：是。

所有 7 个 accepted findings 已修复，修复方式与 plan-fix artifact 描述一致。plan 是 code-generation-ready 的，implementation agent 可以按 Slice 1–7 顺序执行。唯一的非阻塞新发现（F04）是 implementation 时 manifest 文件核对细节，Slice 4 的验证命令足以捕获潜在遗漏。

**Artifact path**: `docs/reviews/wu-tools-01-f03-r4-plan-rereview-mimo.md`
