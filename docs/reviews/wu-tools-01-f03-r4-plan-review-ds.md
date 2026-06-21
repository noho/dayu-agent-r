# WU-TOOLS-01-F03-R4 Plan Review — AgentDS

## Review Metadata

- **Reviewed target**: `docs/host/host-issues/wu-tools-01-f03-r4-tools-discovery-spec-plan.md`
- **Work unit**: WU-TOOLS-01-F03-R4 Tools Discovery Spec Semantics Cleanup
- **Review agent**: AgentDS
- **Timestamp**: 20260621-072125
- **Design truthes consulted**: `docs/host/design.md`, `docs/engine/design.md`
- **Control truth consulted**: `docs/host/issues-implementation-control.md`
- **Code evidence consulted**: `dayu/config/tool_discovery.json`, `dayu/runtime/config_loader.py`, `dayu/runtime/tools_discovery.py`, `dayu/service/host_assembly.py`, `dayu/fins/tools/provider.py`, `dayu/fins/tools/upload_provider.py`, `dayu/fins/tools/upload_tools.py`, `dayu/tools/doc_provider.py`, `dayu/tools/doc_tools.py`, `dayu/fins/tools/fins_limits.py`, `docs/host/design.md` (ToolsDiscovery section, line 2058)

## Scope of Review

Full adversarial plan review covering:

- Code-generation readiness: can an implementation agent execute without re-designing?
- Design truth alignment: ConfigLoader raw read, Service effective mapping, ToolsDiscovery pure aggregation
- User-confirmed goals: remove `allow_empty`, `include_read_tools`, `allowed_upload_roots`; `workspace_root` default `"workspace/"`; OLD limits migration
- Non-goal preservation: no permissions, no Host/Engine contract changes, no old schema compat, no scene `tool_selection.allow_empty` change
- Slice boundaries, ordering, allowed files, test coverage, README triggers
- Special challenges: Doc provider `enabled=false`, ToolsDiscovery fail-fast on empty, upload default registration

## Assumptions Tested

| # | Assumption | Verdict |
|---|-----------|---------|
| A1 | ConfigLoader's `_require_required_and_optional_fields` will reject unknown `allow_empty` after removal from required set | **Confirmed** — the function already rejects unknown fields; removal from `required` set makes `allow_empty` unknown → fail-fast |
| A2 | `ToolsDiscovery._validate_provider_output` can simply drop the `spec.allow_empty` check and always reject empty | **Confirmed** — line 544 of `tools_discovery.py` becomes `if not output.definitions:` which always raises |
| A3 | Empty final bundle when all providers disabled is preserved via the existing `if not definitions: ToolBundle(..., _allow_empty=True)` path | **Confirmed** — lines 264-268 of `tools_discovery.py` |
| A4 | Fins providers will get absolute `workspace_root` after Service effective resolution | **Confirmed** — plan correctly describes resolution in `_effective_tool_provider_config` |
| A5 | Upload repository write boundary is not affected by allowlist removal | **Confirmed** — upload still goes through `FinsIngestionRuntime` → repository protocols |
| A6 | Doc provider with empty `allowed_paths` currently returns empty definitions and depends on `allow_empty=true` | **Confirmed** — line 46-52 of `doc_provider.py` |
| A7 | Packaged Doc/Fins limits defaults match OLD values | **Confirmed** — `DocToolLimits` defaults (line 94-98 of `doc_tools.py`) and `FinsToolLimits` defaults (lines 25-34 of `fins_limits.py`) match plan's listed values |
| A8 | Web-tools provider always returns non-empty definitions | **Unverified** — plan asserts without code evidence; `dayu/tools/web.py` not consulted |
| A9 | Fins download/preprocess providers never return empty when given valid absolute workspace_root | **Not explicitly verified in plan** — plan doesn't discuss these providers' empty-output behavior |

## Findings

### F1 — Doc provider `enabled=false` decision fork unresolved — MEDIUM

- **位置**: Plan Slice 1 lines 164-167; Risks section lines 584-586
- **问题类型**: 不可直接实施 / 切片过粗
- **当前写法**:
  > "The conservative plan uses `enabled=false` for packaged `doc-tools`"
  > "Set packaged `doc-tools.enabled=false` unless implementation proves enabled Doc provider no longer returns empty with empty `allowed_paths`."
  > "Implementation owner must either make Doc provider fail fast when enabled with empty paths and keep default disabled, or revise product defaults explicitly."

- **反例/失败场景**: Implementation agent 读到这三处不一致的描述，需要自行裁决是选 `enabled=false` 还是让 Doc provider fail fast on empty paths。两个选项的代码路径不同：前者改一行 JSON（`"enabled": false`），后者要改 `doc_provider.py` 的 `discover_tools()` 在 `allowed_paths` 为空且 enabled 时 raise 而非返回空。若 implementation agent 选错方向，review agent 会因 plan 未收敛而要求返工。

- **为什么有问题**: Plan 是 code-generation-ready 的 contract，不应包含 implementation agent 需要自行裁决的设计分支。当前 plan 同时描述了 "preferred" 路径和一个 "or" 备选路径，且 risks 章节又把选择权交给 implementation owner。

- **直接证据**: 
  - Plan line 164-167: 明确定义了两个 option
  - Plan line 584-586: "Implementation owner must either make Doc provider fail fast when enabled with empty paths and keep default disabled, or revise product defaults explicitly"
  - `doc_provider.py` line 46-52: 当前 enabled + empty allowed_paths → 返回空 definitions

- **影响**: 实施 Agent 跑偏 / review 不可验收 / 后续返工

- **建议改法和验证点**: Plan 必须收敛到单一决策。推荐明确写：`doc-tools.enabled=false` 作为 packaged default，Doc provider 在 enabled + empty allowed_paths 时 fail fast（修改 `discover_tools()` 在 `if not allowed_roots:` 分支 raise 而非返回空）。两者都做，不留分支。验证点：ConfigLoader 加载 packaged default 时 `doc-tools.enabled=false`；直接构造 enabled spec + empty paths 调用 Doc provider 时 raise。

- **修复风险**: 低 — 只需改 plan 文本，不涉及代码
- **严重程度**: 中 — blocking，implementation agent 不应自行做设计裁决

---

### F2 — Slice 2 与 Slice 3 之间存在导入断点 — MEDIUM

- **位置**: Plan Slice 2 lines 219-258; Slice 3 lines 260-302
- **问题类型**: 切片过粗 / 不可直接实施
- **当前写法**: Slice 2 从 `ToolsDiscoveryProviderSpec` 删除 `allow_empty` 字段；Slice 3 从 `host_assembly.py::_tool_discovery_specs()` 删除 `allow_empty=provider_config.allow_empty` 映射。

- **反例/失败场景**: Slice 2 完成后、Slice 3 执行前，`host_assembly.py` line 937 仍然写 `allow_empty=provider_config.allow_empty`，但 `ToolsDiscoveryProviderSpec` 已不接受该参数。任何 import `host_assembly` 的模块（包括 `dayu.service` 包初始化、smoke 脚本、CLI 入口）都会在 import 时抛出 `TypeError`。Slice 2 的 focused tests（`tests/runtime/test_tools_discovery.py`）可能不 import `host_assembly` 因此通过，但代码库整体处于不可导入状态。

- **为什么有问题**: Plan 声称每个 slice 应 "可独立验证的行为闭环"（control doc Slice 切分原则）。Slice 2 和 Slice 3 之间存在硬依赖：`ToolsDiscoveryProviderSpec` 的字段删除与 `host_assembly.py` 的调用点删除必须原子完成，否则 import 链断裂。

- **直接证据**:
  - `tools_discovery.py` line 105: `allow_empty: bool = False` — Slice 2 删除此行
  - `host_assembly.py` line 937: `allow_empty=provider_config.allow_empty` — Slice 3 删除此行
  - Control doc line 135-136: "slice 应大到能形成可测试的语义闭环，小到能一次实现、一次验证、一次 review"

- **影响**: 实施 Agent 跑偏（要么在 Slice 2 中被迫修改 host_assembly.py 越界，要么在两个 slice 之间代码库处于 broken state）/ review 不可验收

- **建议改法和验证点**: 
  1. 合并 Slice 2 和 Slice 3 为一个 slice（两者加起来 < 200 行改动，context 可控）；或
  2. 在 Slice 2 中增加 `host_assembly.py` 的同步修改（允许文件列表扩展），Slice 3 只做 workspace path resolution 逻辑变更。
  验证点：合并后 slice 的 focused tests 包含 `test_tools_discovery.py` + `test_host_assembly.py`，两者同时通过。

- **修复风险**: 低 — plan 文本调整
- **严重程度**: 中 — blocking，slice 边界需要调整才能独立验证

---

### F3 — Web-tools "always returns non-empty" 假设未经代码验证 — LOW

- **位置**: Plan line 169-170
- **问题类型**: 契约缺失 / 测试缺口
- **当前写法**:
  > "For `web-tools`, keep enabled default if provider always returns non-empty `search_web` / `fetch_web_page`. Remove only `allow_empty`."

- **反例/失败场景**: `dayu/tools/web.py` 的 `discover_tools()` 可能存在返回空 definitions 的代码路径（例如：配置缺失、网络检查失败、依赖不可用）。如果在某个条件下 web provider 返回空，删除 `allow_empty` 后会导致 ToolsDiscovery 在 web provider 处 fail fast。

- **为什么有问题**: Plan 以未经验证的假设为前提做决策。"if provider always returns non-empty" 不是从代码证据推导的结论，而是 wishful thinking。如果假设错误，implementation 阶段会发现 web provider 需要额外处理（要么 disabled by default，要么修改 provider 逻辑），这是 plan 应提前发现的。

- **直接证据**: Plan 的 Affected Files 中没有列出 `dayu/tools/web.py`；代码证据章节（lines 57-67）没有引用 web provider 源码

- **影响**: 实施中发现问题 → 返工 / 需要额外 plan fix

- **建议改法和验证点**: 在 plan 进入 implementation 前，读 `dayu/tools/web.py` 的 `discover_tools()` 确认所有代码路径是否可能返回空 definitions。若确认永远非空，在 plan 中记录具体证据；若存在空返回路径，在 plan 中裁决处理方式（默认禁用 web-tools / 修改 provider fail fast / 其他）。

- **修复风险**: 低 — 读一个文件即可收敛
- **严重程度**: 低 — 非 blocking，但应在 implementation 前收敛

---

### F4 — Fins download/preprocess providers 的空输出行为未在 plan 中讨论 — LOW

- **位置**: Plan 整体；packaged config 中 `financial-download-tools` 和 `financial-preprocess-tools` 当前 `allow_empty: true`
- **问题类型**: 契约缺失
- **当前写法**: Plan 只详细讨论了 read provider（`include_read_tools` 删除）和 upload provider（`allowed_upload_roots` 删除），对 download 和 preprocess provider 只在 affected files 中列出 `dayu/fins/tools/download_provider.py` 和 `dayu/fins/tools/preprocess_provider.py` 为 "likely unchanged but must be checked"。

- **反例/失败场景**: download 和 preprocess provider 当前也配置了 `allow_empty: true`。如果这两个 provider 在某些条件下返回空 definitions（例如：workspace_root 解析失败但被 allow_empty 掩盖），删除 `allow_empty` 后它们会在 ToolsDiscovery 中 fail fast。

- **为什么有问题**: Plan 删除了全局 `allow_empty` 但只逐 provider 分析了 read/upload/doc/web，遗漏了 download 和 preprocess。虽然它们大概率不会返回空（因为需要有效 workspace_root 才能构造 runtime），但 plan 应显式确认而非留给 implementation agent 发现。

- **直接证据**: 
  - `tool_discovery.json` lines 17-37: download 和 preprocess 都有 `"allow_empty": true`
  - Plan lines 81-88: download/preprocess provider 列为 "likely unchanged but must be checked"

- **影响**: 实施中发现问题 → 轻微返工

- **建议改法和验证点**: 读 `download_provider.py` 和 `preprocess_provider.py` 的 `discover_tools()` 确认是否可能返回空。在 plan 中显式记录结论。若两者永远非空，plan 只需确认；若有空返回路径，提前裁决。

- **修复风险**: 低
- **严重程度**: 低 — 非 blocking

---

### F5 — Upload 默认注册后 scene tool exposure 风险识别但未要求验证 — LOW

- **位置**: Plan Risks section lines 597-600
- **问题类型**: 测试缺口
- **当前写法**:
  > "If packaged `financial-upload-tools` now registers by default, scenes still decide selected tools. Product owner should confirm default scenes do not expose upload where not intended. This WU must not solve that by provider allowlist."

- **反例/失败场景**: 当前 upload provider 因为 `allowed_upload_roots=[]` 返回空工具集，upload tool 不会被任何 scene 选中。删除 allowlist 后，`start_fins_upload` 始终在 discovered bundle 中。如果某个现有 scene 使用 `mode="all"` 或 `tool_tags_any` 匹配了 `"fins"` 标签，upload tool 会被 LLM 看到并可能被调用。

- **为什么有问题**: Plan 正确识别了风险但把验证完全推给 product owner，没有要求在 implementation 或 test 中验证默认 scene manifest 的 tool selection 是否会意外暴露 upload。至少应该有一个 grep/assertion 确认。

- **直接证据**: Plan line 600: "This WU must not solve that by provider allowlist." — 正确；但不等于不需要验证
- `upload_tools.py` line 179: tags 包含 `"fins"` 和 `"fins-upload"`

- **影响**: 部署后 upload tool 意外暴露给 LLM

- **建议改法和验证点**: 在 Slice 5 或 Slice 8 的验证步骤中增加：检查默认 scene manifests 的 `tool_selection`，确认没有 scene 通过 `mode="all"` 或 tag 匹配意外包含 `start_fins_upload`。或至少记录当前 scene manifest 的工具选择方式作为验证基线。

- **修复风险**: 低
- **严重程度**: 低 — 非 blocking，已识别为 residual risk

---

### F6 — `workspace_root` 相对路径解析基准未完全明确 — LOW

- **位置**: Plan Slice 3 lines 149-153; Risks section lines 585-586
- **问题类型**: 不可直接实施
- **当前写法**:
  > "if relative, resolve against Service request/runtime `workspace_root` using `_resolve_project_path`-equivalent semantics"
  > "Implementation owner must verify whether `"workspace/"` resolves to `<project_root>/workspace` or should resolve to the effective Dayu workspace root."

- **反例/失败场景**: `ServiceOpenHostAssemblyRequest.workspace_root` 的含义是什么？是项目根目录（如 `~/workspace/dayu-agent-r/`）还是 Dayu workspace 目录？`"workspace/"` 拼接后是 `~/workspace/dayu-agent-r/workspace/` 还是其他路径？如果 implementation agent 选错基准，Fins workspace 会指向错误目录，所有 Fins 工具都会在错误路径上操作。

- **为什么有问题**: Plan 说 "using `_resolve_project_path`-equivalent semantics" 但没有给出具体函数签名或引用。Risks 章节也承认 "Implementation owner must verify"。这意味着 implementation agent 需要自行查找或设计解析函数，增加跑偏风险。

- **直接证据**: 
  - Plan line 153: "using `_resolve_project_path`-equivalent semantics" — 无具体引用
  - Plan line 585-586: "Implementation owner must verify whether `"workspace/"` resolves to..."

- **影响**: 实施 Agent 跑偏 / Fins workspace 路径错误 / 后续返工

- **建议改法和验证点**: 在 plan 中明确：`"workspace/"` 应 resolve 到 `<workspace_root>/workspace/`（即 Service request 的 workspace_root 参数）。在 Slice 3 的验证中增加具体 assertion：传入 `workspace_root=/path/to/project`，期望 effective config 的 `workspace_root` 为 `/path/to/project/workspace`。

- **修复风险**: 低 — 明确一句话即可
- **严重程度**: 低 — 非 blocking，但 implementation agent 需要此澄清

---

## Open Questions

1. **Q1**: `dayu/tools/web.py` 的 `discover_tools()` 是否在任何条件下返回空 definitions？若会，plan 需更新 web-tools 的处理方式。
2. **Q2**: `dayu/fins/tools/download_provider.py` 和 `dayu/fins/tools/preprocess_provider.py` 是否在任何条件下返回空 definitions？需在 plan 中显式确认。

## Residual Risks

| Risk | Severity | Suggested Owner |
|------|----------|----------------|
| Upload 默认注册后 scene tool exposure 扩大 | 中 | Product owner / scene manifest owner；需确认默认 scene 不会意外暴露 upload tool |
| Provider dataclass 默认值与 packaged config 默认值漂移 | 低 | Slice 6 的测试断言应锁定 packaged defaults == dataclass defaults |
| workspace overlay 中残留旧 `allow_empty` 字段导致启动失败 | 低 | rollout notes / workspace migration guide（非代码层面） |
| 删除 allowlist 后 LLM 可请求上传任意本地路径 | 中 | Future Host/policy design（已在 plan non-goals 中记录） |

## Uncovered Areas

1. **web-tools provider 源码** — plan 未读 `dayu/tools/web.py`，无法确认 "always returns non-empty" 假设
2. **download/preprocess provider 空输出行为** — plan 未逐 provider 确认
3. **Fins upload `delete` action with files after allowlist removal** — `_upload_files_from_arguments` 仍然拒绝 delete + files 组合（line 427-429），但 `_resolve_upload_file_path` 替换后是否仍保持 `is_file()` + size 校验？plan 提到 "rejects missing, directory, empty, and delete-with-files cases" (line 541)，但新函数签名从 `_resolve_upload_path(raw_path, allowed_upload_roots=...)` 变为 `_resolve_upload_file_path(raw_path)`，丢失了 allowlist containment check 但保留了文件校验。这部分 plan 描述正确但需 implementation agent 仔细处理。
4. **Scene manifest tool_selection.allow_empty** — plan 正确列为 non-goal，但未确认当前是否有 scene 依赖 provider-level `allow_empty` 来让 scene `allow_empty` 生效。两者是独立语义，但值得在 implementation 前确认。

## Verdict

**PASS-WITH-FINDINGS**

Blocking findings: **2** (F1, F2). Both require plan text changes, not design rework:

- **F1** (Doc provider fork): Converge to single decision — `doc-tools.enabled=false` packaged default AND Doc provider fail-fast on enabled + empty allowed_paths.
- **F2** (Slice 2/3 import breakage): Merge Slice 2 and Slice 3, or add `host_assembly.py` to Slice 2's allowed files for the `allow_empty` mapping removal.

Non-blocking findings (F3-F6) can be resolved in plan-fix or deferred to implementation with explicit notes.

### Gate Entry Condition

进入 **plan accepted/fix gate** 的条件：F1 和 F2 被 controller 裁决（accepted / rejected-with-reason / deferred-with-owner），plan 文本相应更新。F3-F6 至少被显式裁决，不要求全部 resolved。无新 design decision 需要回写设计真源。
