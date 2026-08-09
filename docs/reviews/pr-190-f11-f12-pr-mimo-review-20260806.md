# PR 190 F11/F12 MiMo Review

## Scope

- Mode: PR Review
- PR: #190 — `fix(cli): close interactive conformance gaps`
- Author: noho
- Head branch: `codex/interactive-oracle`
- Base branch: `main`
- Exact head: `9fa3ff799506e66f995b4156dbb960c98c2f737e`
- Local HEAD parity: **PASS** — local `git rev-parse HEAD` equals exact head
- Review date: 2026-08-06
- Output file: `docs/reviews/pr-190-f11-f12-pr-mimo-review-20260806.md`
- Included scope: F11/F12 work-unit commits from `3087b1b9` onward (14 commits); cumulative earlier F01–F10 scope verified for coherence
- Parallel review coverage: 4 subagents — F11 compactor response identity, F12 compaction v3 contract, Engine structured output contract, PR claims/secrets verification

## PR Verification Checks

| Check | Status | Evidence |
|-------|--------|----------|
| Local exact-head parity | **PASS** | `git rev-parse HEAD` = `9fa3ff799506e66f995b4156dbb960c98c2f737e` |
| PR state OPEN + draft | **PASS** | `gh pr view 190` returns `state=OPEN, isDraft=true` |
| No merge/ready/approval action | **PASS** | `mergedAt=null, closedAt=null, reviewDecision=""` |
| Registry digest: `cli_ci_oracles.json` | **PASS** | `sha256sum` = `3404e241dbd71c6244da24b0dbb080022d4c57b36f040ac3456e7a18dbc97acf` (exact match) |
| Registry digest: `cli_ci_scenarios.json` | **PASS** | `sha256sum` = `f4363fc5e7026ad075f4b7f855342cae493a4852d21bd72ef6e53b3f2d588e37` (exact match) |
| Immutable evidence root digest | **PASS** | `38f0b01f12c2ab55ce1af3c16080b71013d1a19512d65051f5532b747f71da0d` referenced in committed docs |
| Immutable evidence report digest | **PASS** | `bbaa52a04100932c09e0a8e20d19c81ed6d865378db502bc6d4f1936c9694411` referenced in committed docs |
| Secrets/private SQLite scan | **PASS** | No `.sqlite3` files committed; no secret values in codebase |
| Missing files check | **PASS** | `gh pr diff 190 --name-only` matches `git diff main..HEAD --name-only` |
| Oracle state verification | **PASS** | 4 oracles, superseded preserved, 3 replacement scenarios unadjudicated, both registries `calibration` |
| Gateflow artifact durability | **PASS** | 130 PR-190 artifacts committed (88 reviews + 42 gateflow) |
| PR body claims vs code | **PASS** | All stated claims verified against implementation |
| No unpushed changes | **PASS** | Working tree clean at exact head |

## Findings

### 1-未修复-中-force-answer fallback 路径原样透传 structured_output

- **入口/函数**: `_AsyncAgent._run_force_answer` → `_run_runner_iteration`
- **文件(行号)**: `dayu/engine/agent.py` (2389–2394, 1345)
- **输入场景**: `AgentRunRequest` 携带 `structured_output`（如 `JsonObjectStructuredOutputRequest`），当 iterations 耗尽或连续工具批次失败触发 `FORCE_ANSWER` fallback
- **实际分支**: `_run_force_answer` 调用 `_run_runner_iteration`，后者在第 1345 行将 `self._request.structured_output` 原样传给 Runner
- **预期行为**: force-answer fallback 是"尽力拿到最终回答"的降级路径。在 `JsonSchemaStructuredOutputRequest`（带严格 schema）场景下，fallback 路径应剥离或降级 structured_output，否则 provider 可能因 schema 约束拒绝请求或返回无法满足 schema 的内容
- **实际行为**: structured_output 原样透传。当前配置下 DeepSeek 使用 `JsonObjectStructuredOutputRequest()`（无 schema 约束，仅要求返回 JSON），Mimo 使用 `None`，因此 **当前不会触发问题**。但若未来模型配置 `json_schema` capability，`JsonSchemaStructuredOutputRequest` 会携带严格 schema 透传到 force-answer 路径，可能导致 provider 拒绝或 LLM 无法在 fallback prompt 下满足 schema
- **直接证据**: `agent.py:1345` — `structured_output=self._request.structured_output`；`agent.py:2389` — `_run_force_answer` 调用 `_run_runner_iteration` 无 override；`llm_compaction.py:577–587` — `_structured_output_request_v3` 按 capability 选择 request 类型
- **影响**: 当前无功能影响（`json_object` mode 下 force-answer 仍返回 JSON）。**潜在风险**：若 `json_schema` capability 被启用，force-answer 路径可能导致 compaction 提案失败
- **建议改法和验证点**: 在 `_run_force_answer` 中将 `structured_output` 设为 `None` 传给 `_run_runner_iteration`，或新增 override 参数。验证点：构造带 `JsonSchemaStructuredOutputRequest` 的 `AgentRunRequest`，触发 force-answer fallback，断言 Runner 收到的 `structured_output` 为 `None`
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中（当前无影响，`json_schema` 启用后升级为高）

### 2-未修复-低-Tool Trace 分析对单个 malformed terminal 为 fail-closed

- **入口/函数**: `_resolved_compactor_response_from_row`
- **文件(行号)**: `dayu/host/durable/tool_trace.py` (707–710)
- **输入场景**: `CONTEXT_COMPACTION_ATTEMPT_REJECTED` terminal 的 `proposal_manifest_ref` 为 `None`（Host 在 proposal manifest 创建前即拒绝 attempt）
- **实际分支**: 第 707 行检查 `binding.proposal_manifest_ref is None` 时抛出 `CompactorResponseResolutionError`，该异常是 `HostDurableError` 子类，在 `_load_hot_snapshot` 被捕获并转为 `ToolTraceAnalysisInputError(HOT_STORE_READ_FAILED)`
- **预期行为**: 单个 malformed terminal 不应导致整个 session 的 Tool Trace 分析 fatal failure
- **实际行为**: fail-closed 设计——单个异常 terminal 导致整个分析 fatal。`CompactorResponseResolutionError` 是 `HostDurableError` 子类，被 `_load_hot_snapshot:568` 的 `except (HostDurableError, OSError)` 捕获
- **直接证据**: `tool_trace.py:707` — `raise CompactorResponseResolutionError(...)`；`tool_trace.py:139` — `class CompactorResponseResolutionError(HostDurableError)`；`tool_trace_analysis_input.py:568` — `except (HostDurableError, OSError) as exc: raise ToolTraceAnalysisInputError(..., reason=HOT_STORE_READ_FAILED)`
- **影响**: 若生产环境存在 proposal manifest 创建前失败的 terminal（罕见但可能），整个 Tool Trace 分析会 fatal
- **建议改法和验证点**: 当前为 fail-closed 语义，符合设计意图。若需降级，应在 `_read_hot_snapshot_in_transaction` 中单独 catch `CompactorResponseResolutionError` 并转为 limitation + diagnostic。验证点：构造 `proposal_manifest_ref=None` 的 rejected terminal fixture，确认分析是否仍能完成
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低（fail-closed 设计，触发条件罕见）

### 3-未修复-低-Rejected + successful_response_identity 路径缺测试覆盖

- **入口/函数**: `_compactor_response_summaries`
- **文件(行号)**: `dayu/host/tool_trace_analysis_rules.py` (285–347)
- **输入场景**: `ATTEMPT_REJECTED` disposition 且 `successful_response_identity` 不为 `None`（Engine 调用成功但 Host 拒绝 proposal）
- **实际分支**: 第 309 行 `successful = response.successful_response_identity` 不为 `None`，所有 identity 字段被投影到 summary
- **预期行为**: `CanonicalCompactionTerminalBinding` 允许 `ATTEMPT_REJECTED` 携带非空 `successful_response_identity`（`context_events.py:1654–1658`），表示 Engine 已成功获取 response 但 Host 因 policy/quality 原因拒绝了 proposal
- **实际行为**: `ToolTraceCompactorResponseSummary.__post_init__`（`tool_trace_analysis_contracts.py:512–525`）对 `disposition=ATTEMPT_REJECTED` + `identity != None` 组合不拒绝。**逻辑正确**，但测试未覆盖此路径
- **直接证据**: `context_events.py:1654–1658` — rejected terminal 允许 `successful_response_identity` 非空；`tool_trace_analysis_contracts.py:512–525` — contract 校验不拒绝此组合；测试文件中无此路径用例
- **影响**: 代码逻辑正确，但若此路径被意外修改破坏，无回归保护
- **建议改法和验证点**: 在 `test_tool_trace_analysis_rules.py` 中增加 `ATTEMPT_REJECTED + successful_response_identity != None` 测试用例。验证点：disposition 为 `attempt_rejected`，但 `effective_provider/model/runner_request_identity` 均非空且 JSON/Markdown 输出正确
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低（逻辑正确，缺测试覆盖）

### 4-未修复-低-`parse_conversation_compact_output_vnext` 的 `request` 参数未参与解析逻辑

- **入口/函数**: `parse_conversation_compact_output_vnext`
- **文件(行号)**: `dayu/host/llm_compaction.py` (798–819)
- **输入场景**: LLM 返回 JSON 文本后调用解析
- **实际分支**: 第 811 行只做 `isinstance` 校验，第 814 行直接调用 `parse_compact_candidate_v3(final_answer)`，`request` 参数在解析过程中完全不参与
- **预期行为**: `request` 参数要么参与解析约束，要么接口设计应去掉该参数
- **实际行为**: `request` 只用于类型守卫，parse 逻辑完全与 input 解耦。接口过度承诺——调用方误以为传入 `request` 会影响解析语义
- **直接证据**: `llm_compaction.py:814` — `parse_compact_candidate_v3(final_answer)` 不接受 `request`；`llm_compaction.py:811` — `isinstance` 校验后无后续使用
- **影响**: 接口设计具有误导性。当前功能正确但维护者可能误以为 `request` 参与解析
- **建议改法和验证点**: 移除 `parse_conversation_compact_output_vnext` 的 `request` 参数，让调用方只传 `final_answer`。验证点：移除后所有测试仍通过
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 5-未修复-低-`_structure_error_path` 依赖字符串前缀解析提取 JSON path

- **入口/函数**: `_structure_error_path`
- **文件(行号)**: `dayu/host/llm_compaction.py` (855–863)
- **输入场景**: strict parser 抛出 `ValueError` 后提取 path
- **实际分支**: 第 860 行 `suffix = message.partition(":")[2].strip()`，然后判断是否以 `$` 开头
- **预期行为**: path 提取应基于结构化数据（如异常属性），而非从脱敏后的字符串中反推
- **实际行为**: `_structure_validation_report` 先用 `_safe_outcome_text` 截断 error message 到 240 字符，再从截断文本中提取 path。如果截断发生在 `$` 之前，path 回退为 `$`
- **直接证据**: `llm_compaction.py:828–829` — `_safe_outcome_text(str(error))` 截断到 240 字符；`llm_compaction.py:860` — 从截断结果中提取 path
- **影响**: 修复 feedback 中的 `json_path` 在极端长文本场景下可能丢失精确性，降级为根路径 `$`
- **建议改法和验证点**: 让 `compact_structure.py` 的 parser 在抛出异常时携带结构化 path 信息（自定义异常类属性），而非依赖 message 字符串反推。验证点：构造 path 超过 240 字符的 error case，确认 feedback 中 path 仍精确
- **修复风险（低/中/高）**: 中
- **严重程度（低/中/高/严重）**: 低（触发概率极低，parser error message 通常远短于 240 字符）

### 6-未修复-低-`_structure_validation_report` 的 code 映射与 parser 实现强耦合

- **入口/函数**: `_structure_validation_report`
- **文件(行号)**: `dayu/host/llm_compaction.py` (822–852)
- **输入场景**: strict parser 抛出异常后映射 issue code
- **实际分支**: 第 830 行 `prefix = message.partition(":")[0]`，然后用 `code_by_prefix` dict 映射
- **预期行为**: code 映射应基于结构化异常类型或错误码，不依赖 message 文本
- **实际行为**: `_safe_outcome_text` 的 `redact_sensitive_diagnostic_values` 可能修改 message 前缀，导致 code 映射回退到默认值 `INVALID_FIELD_TYPE`
- **直接证据**: `compact_structure.py:218` — `raise ValueError(f"invalid_json: {exc.msg}")` 将 code 写在冒号前；`llm_compaction.py:841–842` — 默认回退值
- **影响**: 若 LLM 输出包含敏感值恰好出现在 error message 的 code 前缀位置，脱敏后 code 映射不精确
- **建议改法和验证点**: 让 parser 抛出自定义异常（如 `CompactParseError(code, path, message)`），从异常属性读取 code。验证点：构造 error message 前缀包含敏感值的 case，确认 code 映射仍正确
- **修复风险（低/中/高）**: 中
- **严重程度（低/中/高/严重）**: 低（触发概率极低）

### 7-未修复-低-`build_compact_repair_feedback_v3` 极端边界可能 RuntimeError

- **入口/函数**: `build_compact_repair_feedback_v3`
- **文件(行号)**: `dayu/host/context_governance.py` (192–195)
- **输入场景**: 所有 issues 总字符数超过 8192，且只剩 1 个 issue 且无 source_labels
- **实际分支**: 第 193–195 行检查 `len(only_issue.source_labels) == 0` 时抛出 `RuntimeError`
- **预期行为**: 应有确定性终止条件，不应抛出未预期的 RuntimeError
- **实际行为**: 若单个 issue 的完整序列化（code + json_path + message + source_labels）超过 8192 且无 source_labels 可移除，抛出 RuntimeError。实际概率极低——单个 issue 约 750 字符，远低于 8192
- **直接证据**: `context_governance.py:192–195` — `raise RuntimeError("bounded repair feedback exceeds total character cap")`
- **影响**: 极端边界下可能抛出未预期的 RuntimeError 而非确定性 failure
- **建议改法和验证点**: 将 RuntimeError 替换为确定性 truncated feedback（保留 code 和 path，截断 message）。验证点：构造极端 case 确认不触发 RuntimeError
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低（实际触发概率极低）

### 8-未修复-低-Engine structured output 双枚举 by-value cast 无编译期守护

- **入口/函数**: `_runner_spec_from_model` / `runner_spec_from_json`
- **文件(行号)**: `dayu/runtime/config_loader.py` (108–113) / `dayu/engine/contracts/structured_output.py` (19–31) / `dayu/service/host_assembly.py` (1807)
- **输入场景**: 任一枚举新增成员，另一枚举未同步更新
- **实际分支**: `StructuredOutputCapability(model.structured_output_capability.value)` — 新成员时 `StrEnum` 构造 `raise ValueError`
- **预期行为**: 两个枚举成员集应保持同步
- **实际行为**: 枚举分别定义在 `dayu.runtime`（不得 import `dayu.engine`）和 `dayu.engine.contracts`。by-value cast 运行时报错，无编译期守护。当前成员集一致（`NONE`, `JSON_OBJECT`, `JSON_SCHEMA`）
- **直接证据**: `config_loader.py:108` — `StructuredOutputCapabilityConfig`；`structured_output.py:19` — `StructuredOutputCapability`；`host_assembly.py:1807` — by-value cast
- **影响**: 维护风险。新增 capability 级别时需同步修改两处
- **建议改法和验证点**: 保持当前架构，在测试中断言两个枚举成员值集合一致。验证点：config_loader 测试断言 `StructuredOutputCapabilityConfig` 成员值集合与 `StructuredOutputCapability` 一致
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低（架构约束导致的合理取舍）

## PR Body Claims Verification

| Claim | Status | Evidence |
|-------|--------|----------|
| F11: public compactor response identity sourced from `SuccessfulRunnerResponseIdentity` | **PASS** | `tool_trace.py:699–730` — all identity fields from `SuccessfulRunnerResponseIdentity` |
| F11: no identity inferred from config/adjacent events/timestamps/provider names | **PASS** | All fields traced to typed resolver, no inference |
| F11: no raw provider request/response/endpoint/headers/credentials exposed | **PASS** | White-list projection only in `_compactor_response_json` and `_render_compactor_responses` |
| F12: v3 structure descriptor single source of truth | **PASS** | `compact_structure.py:75–398` — `_ROOT` descriptor derives template/schema/rules/parser |
| F12: omission/drop-reason ledger removed | **PASS** | `_ROOT` descriptor has 6 fields, no omission/drop-reason; `CompactCandidateV3` has no related fields |
| F12: Host Context Governance owns all stated responsibilities | **PASS** | `context_governance.py` — acceptance/caps/repair/coverage/terminal all owned |
| F12: fresh schema only, no v2 alias/compatibility/reader/wrapper/shim | **PASS** | No v2 references in F12 implementation files |
| Prompt: system 2510→822 bytes, user 13919→3337 bytes | **PASS** | `conversation_compaction.md` and `conversation_compaction_user.md` confirm reduction |
| DeepSeek uses native JSON structured output; Mimo on prompt + strict validation | **PASS** | `models.json` — DeepSeek `json_object`, Mimo `none` |
| `session_summary=null` retains full-replacement semantics | **PASS** | `compaction.py:1434–1440` — null summary clears prior summary |
| Registry: `cli.interactive.core-execution@2` accepted, predicates 29/30 carry F11/F12 | **PASS** | `cli_ci_oracles.json` oracle 3, status `accepted` |
| 3 replacement scenarios unadjudicated | **PASS** | `cli_ci_scenarios.json` — 3 scenarios with `status: "unadjudicated"` |
| Both registries `calibration` | **PASS** | Both JSON files have `registry_status: "calibration"` |
| Secret scan: 0 findings | **PASS** | No secrets in committed code |
| 4 private `dayu_host.sqlite3` quarantined | **PASS** | No `.sqlite3` files in git history |
| Public/canonical F11 equality: 0 mismatches | **PASS** | Test `test_compactor_response_summary_json_markdown_share_safe_typed_source` verifies |

## Cumulative Earlier Scope (F01–F10) Coherence

Earlier F01–F10 scope remains coherent on this branch:

- All F01–F10 Gateflow artifacts are committed and durable
- No F01–F10 contracts were reopened by F11/F12
- The cumulative diff (220 files, +25920/-3570) includes F01–F10 changes that are consistent with their accepted review history
- Oracle supersession graph is acyclic and symmetric
- No backward dependency violations detected

## Uncovered Areas

1. **Engine structured output integration tests**: No tests cover `AgentRunRequest` + `structured_output` through the `_AsyncAgent` state machine, particularly the force-answer fallback path
2. **Rejected + identity path**: `ATTEMPT_REJECTED` + `successful_response_identity != None` not covered by tests
3. **F12 test gaps**: blank text for non-summary sections, empty JSON object `{}`, reactive repair exhaustion → fallback, null session_summary memory projection, full pipeline integration

## Open Questions

- 无。所有 findings 均基于直接证据，无阻碍 confident judgment 的未决问题。

## Residual Risk

- Finding 1（force-answer 透传 structured_output）为潜在风险，当前配置不触发但未来 `json_schema` capability 启用后可能升级
- Finding 2（fail-closed terminal）为设计选择，非缺陷
- Engine structured output 集成层面缺少端到端测试
- F12 测试覆盖 gaps 为建议补充项，不影响当前 correctness

## Overall Assessment

PR 190 F11/F12 work unit 的实现质量高：

- **语义所有权清晰**: F11 的 response identity 严格来自 `SuccessfulRunnerResponseIdentity` 单一真源；F12 的 v3 structure descriptor 是 template/schema/rules/parser 的唯一真源
- **分层架构合规**: Engine 不做业务 schema 校验，Host Context Governance 唯一拥有 acceptance/caps/repair/coverage
- **fresh schema only**: 无 v2 alias、兼容 reader、wrapper、loose parser 或 downstream repair
- **adversarial failure paths**: malformed JSON、duplicate keys、unknown keys、blank text、exceeded caps、repair exhaustion、deterministic fallback 均有确定性处理
- **PR body claims 准确**: 所有声明均可在代码/测试/证据中找到直接支撑
- **无安全问题**: 无 secrets 泄露、无 private SQLite 发布、无缺失文件

8 个 findings 均为低或中严重度，无阻塞 merge 的严重缺陷。建议在后续迭代中补充测试覆盖和接口清理。
