# Aggregate Deepreview — AgentDS

## Scope

- **Mode**: Current changes (aggregate gate of WU-SEMANTIC-OWNERSHIP-01)
- **Branch**: `phaseflow/host-issues-control`
- **Base**: `b1a0631f397967e7530b676a90ef7467d83a1817^`
- **Accepted HEAD**: `85aa7184a694448a5b27da7cca52f753f84d6e20`
- **Accepted tree**: `0db1c91f92dca594cf77c74bbde8f5b4fc42710d`
- **Aggregate parent**: `3410d7422655c56bdf13c643f77c27f40b9d4550`
- **Review range**: `b1a0631f397967e7530b676a90ef7467d83a1817^..85aa7184a694448a5b27da7cca52f753f84d6e20`
- **Changed production Python**: 223 files (exact 219 per Controller)
- **Output file**: `docs/reviews/wu-semantic-ownership-01-aggregate-deepreview-ds.md`
- **Reviewer**: AgentDS (独立执行，无 subagents)

### Truth Sources Used

按 Controller authorization 优先级读取：

1. `AGENTS.md`
2. `docs/host/issues-implementation-control.md` — 部分读取（超 256KB）
3. `docs/phaseflow-umbrella-optimization-control.md`
4. `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md`
5. `docs/host/design.md` — 部分读取（超 256KB）
6. `docs/engine/design.md`
7. `docs/tool/design.md`
8. `docs/fins/design.md`
9. `docs/ui/design.md`
10. Accepted aggregate fix plan 与 Controller validation artifacts

三路原始 overdesign review 未直接读取；严格以 Controller discussion 为最终产品裁决。

### Excluded from Review

- AgentMiMo deepreview artifact（不得读取）
- Controller-owned dirty paths（全部 immutable）
- `docs/reviews/wu-semantic-ownership-01-aggregate-regression-*` artifacts（只作测试证据引用，不作 code/design review 输入）
- Topic 8/9 在当前 range 无代码变更，只做 crosscheck
- Issue 142/151/175/177/178 和 Web/WeChat/render trackers 只校验是否被偷带，不深挖各 Issue 的实现内容

---

## Verification

### HEAD / Tree / Staged / Dirty

```
HEAD       = 85aa7184a694448a5b27da7cca52f753f84d6e20  ✓
TREE       = 0db1c91f92dca594cf77c74bbde8f5b4fc42710d  ✓
STAGED     = (empty)                                    ✓
DIRTY      = docs/host/issues-implementation-control.md  (Controller-owned)
UNTRACKED  = 5 Controller-owned artifacts                (declared immutable)
```

### Immutable Dirty Hashes Verified

```
M  docs/host/issues-implementation-control.md
?? docs/reviews/wu-semantic-ownership-01-aggregate-deepreview-controller-authorization.md
?? docs/reviews/wu-semantic-ownership-01-aggregate-regression-final-validation-codex.md
?? docs/reviews/wu-semantic-ownership-01-aggregate-regression-final-validation-controller-authorization.md
?? docs/reviews/wu-semantic-ownership-01-aggregate-regression-final-validation-controller-validation.md
?? docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-accepted-commit-controller-validation.md
```

---

## Findings

### 1-MATERIAL-[中] Evidence block `.text` 与 typed material 的 exact match 校验缺少 immutable rendering 保障

- **入口/函数**: `run_input_material_block()` → `RunInputMaterialBlock.__post_init__()`
- **文件(行号)**: `dayu/host/compact_material.py:287-289`
- **输入场景**: 调用方构造 evidence block 时同时传入 `text` 和 `accepted_tool_evidence`
- **实际分支**: `RunInputMaterialBlock.__post_init__()` 执行 `if self.text != render_accepted_tool_evidence_for_llm(self.accepted_tool_evidence): raise ValueError(...)`
- **预期行为**: block.text 必须由 `render_accepted_tool_evidence_for_llm()` 唯一产生，不能由调用方任意组装
- **实际行为**: 当前校验是构造期一致性检查，但 `render_accepted_tool_evidence_for_llm` 的输出格式是固定的四行中文文本（`工具名称：...` / `查询语义：...` / `业务来源：...` / `工具结果：...`）。如果该 renderer 的实现发生变更，所有调用方必须同步更新传入的 `text`。renderer 的输出格式是 frozen dataclass 的纯函数，当前没有机制防止调用方传入"与 renderer 输出一致但现在 renderer 已变更"的文本。
- **直接证据**: `compact_material.py:287-289` 的 `if self.text != render_accepted_tool_evidence_for_llm(...)` 校验
- **影响**: 中 — renderer 变更时，调用方构造的 `text` 会与运行时校验不一致导致 `ValueError`。但由于 `render_accepted_tool_evidence_for_llm` 是纯函数（无状态、无随机、无 I/O），且所有构造路径都走 `run_input_material_block()` 这个单一 helper，实际只有 `compact_material.py` 和 `run_input.py`（fallback path）会构造 evidence block。当前所有调用方都通过 `run_input_material_block()` helper 构造，该 helper 直接使用 renderer 输出作为 `text` 传入。因此校验不是重复定义真源——而是确保人类调用方错误绕过 helper 时能 fail closed。不做修改。
- **建议改法和验证点**: 不修改。当前 single-helper 构造 + fail-closed 校验是正确的 defense-in-depth 模式。
- **修复风险**: N/A
- **严重程度**: 中（material observation，不要求修复）
- **裁决**: **material observation** — 当前设计是正确防御，不是缺陷。`render_accepted_tool_evidence_for_llm()` 是 single source of truth；`text` 必须通过该函数产生；校验确保不会因人类错误绕过。

### 2-MATERIAL-[中] `_execution_health.py` 中 `mark_ready()` 与 `report_fatal()` 之间缺少对 TOCTOU 的显式设计说明

- **入口/函数**: `HostExecutionHealthGate.mark_ready()` / `HostExecutionHealthGate.report_fatal()`
- **文件(行号)**: `dayu/host/_execution_health.py:131-149` (mark_ready), `169-193` (report_fatal)
- **输入场景**: 理论场景——如果 `mark_ready()` 被从异步上下文调用，可能被 `report_fatal()` 抢占
- **实际分支**: `mark_ready()` 在无锁状态下执行 read-check-write；`report_fatal()` 在 `async with self._admission_lock` 内执行状态写入
- **预期行为**: 在同步 startup 路径中，`mark_ready()` 在 event loop 启动前被调用；`report_fatal()` 只在 event loop 运行后可达，因此不会并发。但代码中没有文档化这一时序假设。
- **实际行为**: 当前实际执行路径安全——`open_host()` 同步调用 `mark_ready()`，之后才启动 event loop 和 scheduler critical tasks。但 future reader 可能不察觉该时序约束。
- **直接证据**: `_execution_health.py:131-149` 的 `mark_ready()` 不获取锁；`dispatch.py` 中 `HostDispatchScheduler.open()` 实例化 scheduler 后由 opener 调用 `mark_ready()`
- **影响**: 低 — 当前无实际并发风险；缺少显式文档说明时序假设
- **建议改法和验证点**: 在 `mark_ready()` 的 docstring 中显式说明"必须由 opener 在 event loop 启动前同步调用；不可从异步上下文调用"
- **修复风险**: 低（纯文档补充）
- **严重程度**: 中（maintainability — design assumption not documented）

### 3-MATERIAL-[低] `_require_compact_memory_event_ref_consistency` 在 compact 或 memory 为 None 时不检查

- **入口/函数**: `_require_compact_memory_event_ref_consistency()`
- **文件(行号)**: `dayu/host/run_input.py:3055-3090`
- **输入场景**: memory snapshot 或 compact artifact 为 None（例如首个 Run 尚未 compact）
- **实际分支**: `RunInputBuilder.build_run_input_messages()` 无条件调用 `_require_compact_memory_event_ref_consistency()`，当 memory 有 `latest_compaction_event_ref` 但 compact 的 `compaction_event_ref` 为 None（或反过来）时，会抛出 `MemoryProjectionRepairRequired`
- **预期行为**: 尚未 compact 或 compact 与 memory 一致时不应触发 repair
- **实际行为**: 需查看函数体内如何处理双方均为 None 的场景。函数体中的逻辑：若 `memory.latest_compaction_event_ref` 和 `compact.compaction_event_ref` 均为 None，则不触发 repair（一致）。若一方有值而另一方为 None，则触发 repair。该行为是正确的——memory 认为已 compact 但 compact provider 认为尚未 compact（或相反）表示存在 inconsistent state。
- **直接证据**: 函数代码路径
- **影响**: 低 — 正确行为，边界情况正确 fail closed
- **建议改法和验证点**: 不修改。逻辑正确。
- **修复风险**: N/A
- **严重程度**: 低（material observation — confirmed correct, no repair needed）

---

## Adversarial Failure Pass

### Coverage Summary

沿以下维度对 full range 执行 adversarial failure pass：

| 维度 | 覆盖 | 状态 |
|------|------|------|
| auth/permissions/trust boundary | Web egress policy, Fins path containment, init lock | 无泄露 finding |
| data loss/corruption/duplication | Fins atomic transaction, evidence digest chain, wait observation timeout→backoff | 无 finding |
| rollback/retry/partial failure | Init whole-tree staging, Fins commit/rollback batch capability, observation retry/backoff | 无 finding |
| race conditions/ordering | Execution health gate admission lock, init TOCTOU protection, compaction_operation attempt-linked cancellation | `mark_ready()` 缺少显式时序文档 (Finding 2) |
| empty/null/timeout/cancellation | Doc tool `actual_limit=0` heap behavior, wait poller observation timeout, scheduler unavailable wake | 无 finding |
| duplicate/conflicting params | Tool call idempotency, Fins duplicate external identity fail closed | 无 finding |
| version skew/schema drift | Compact payload strict field-set parse, compact vNext schema version check | 无 finding |
| observability gaps | Poller boundary_rejections counter, execution health fatal reporting, scheduler critical task supervision | 无 finding |
| external inconsistency | `render_accepted_tool_evidence_for_llm` single rendering, block.text exact match validation | 无 finding |
| external protocol boundary | HKEX cumulative continuation with consistent-hasNext-loaded-count validation | 无 finding |
| overcoupling | Browser/private-network decoupled, compact semantic parse decoupled from memory projection, tool_call_request owned by separate writer module | 无 finding |
| semantic ownership drift | See §Semantic Ownership Drift below | 无新增 drift |
| statically provable performance | Doc directory heap bounded to `actual_limit`, Doc stream chunk `64 * 1024` | 无 finding |
| test gaps | See §Residual Risk below | — |

### Gemini Quota / Provider Adherence

确认 Gemini 为低 budget 测试账号；`NO_CODE / NON_BLOCKING`。代码中无针对 Gemini quota 的 retry、config change 或特殊 handling。不报告。

### AR-F06 / AR-F07

- **AR-F06**: Host scheduler/lifecycle residual 状态一致——scheduler 仍通过 `_execution_health` gate 做 critical task supervision，但不改变 Host 对工具执行的强约束真源定位。不报告。
- **AR-F07**: Windows release blocker。代码中 `upload_script.py:35-42` 的 `current_upload_script_platform()` 正确按 `os.name == "nt"` 分派 POSIX/Windows 路径。Darwin skip 本身不包装为 finding。

### API Key / Header Exposure

已验证：Config internal SQLite / EventLog 中的 API key/header 存储是 trusted-internal 域，不进入 Tool Trace、audit、public HostEvent/UI、memory/compact/evidence、LLM-facing material 或 operator log。`web_diagnostics.py` 中的 `_SENSITIVE_HEADER_FRAGMENTS` 正确过滤敏感 header。不报告。

---

## Semantic Ownership Drift

### Topic-by-Topic Ownership Verification

**Topic 1 — Doc input budgets**
- `max_source_bytes` 和 `max_directory_entries` 已从产品代码完全移除（`rg` 零命中）
- Doc 工具 LLM-facing description 已改为中文本，包含 `total`/`returned`/`scanned_entries`/`scan_complete` 等业务可读字段说明
- `ToolTruncateSpec` 的 owner 仍在 Tool config，Doc producer 不再预截断
- **无 ownership drift**

**Topic 2 — Web policy**
- 私网端口/DNS/browser/proxy/challenge 策略全部由 `tool_discovery.json` 的 `web-tools.config` 拥有
- `WebEgressPolicy` 是单次 HTTP 调用授权的唯一 owner
- `WebResourceBudget` 按 http/browser/diagnostics 三组拆分，每组独立 typed value
- `WebDiagnosticProjection` 为 diagnostic artifact 提供稳定 v2 schema
- `browser_enabled` 与 `allow_private_network_url` 已解耦
- 存储状态 lifecycle 未实现（Issue #178）
- **无 ownership drift**

**Topic 3 — Host LLM-safe arguments**
- `_INTERNAL_EVIDENCE_SOURCE_PREFIXES` 已移除
- `_llm_facing_evidence_source_text` 已移除（不再通过前缀匹配过滤 source text）
- `AcceptedToolEvidenceLLMMaterial` 为 LLM-facing evidence 提供 typed, validated source-to-renderer pipeline
- 参数黑名单修复逻辑已移除；LLM-safe 语义由 source owner（tool schema, prompt assets, ToolRuntime）负责
- Tool schema description 已改为中文业务可读文本（例如 `fetch_more` description）
- **无 ownership drift** — 语义 owner 已从下游黑名单修复迁移到 source owner

**Topic 4 — OpaqueEvidenceRef**
- `_INTERNAL_SOURCE_REF_KINDS` 已移除
- Opaque refs 不再被渲染为 business source
- `ACCEPTED_EVIDENCE_SOURCE_UNAVAILABLE_TEXT` 为统一的 source unavailable 文案
- Memory fact rendering 不再包含 `evidence_kind`（该枚举已从 compact candidate 移除）
- Memory `ForwardIntent.intent_type` 和 `status` 改为 typed `ForwardIntentTypeVNext`/`ForwardIntentStatusVNext`
- Memory `ReferenceContinuityItem.reason` 改为 typed `ReferenceContinuityReasonVNext`
- `CompactArtifactView.messages` 已移除——compact 语义通过 memory projection pipeline 进入 LLM context
- **无 ownership drift**

**Topic 5 — Wait poller**
- `with_entrypoint_wait_poller_policy()` 已移除——poller 策略现在从 `host_runtime.json` 进入
- `AdmissionPolicy` 提升为独立模块 `dayu.host.queue_policy.RunQueuePolicy`
- `WaitPollerRuntimePolicy` 所有字段为 required（无默认值）
- `WaitAdapterSnapshot` 替代 raw `WaitRecordRow` 传给 adapter（adapter 不再读取 Host durable row）
- `WaitBoundaryDecision` 为 wait 时间边界唯一 typed 判定
- Observation timeout 不再 terminalize wait→LOST；改为 release with backoff
- `WaitObservationRunner` 提供 bounded observation 并发控制
- `is_terminal_run_status` 提升到 `dayu.host.api` 作为公共 helper
- **无 ownership drift** — 配置 owner 已从 Service ad-hoc 迁移到 `host_runtime.json`；时间边界 owner 在 `wait_boundary.py`

**Topic 6 — Fins contracts**
- `_fs_identity.py` 为 external identity → filesystem key mapping 的唯一 owner
- `SourceSnapshotFileDescriptor` 提供无路径的文件描述符
- `BatchToken` 使用显式 batch capability（不再有 ambient ContextVar authority）
- HKEX cumulative continuation 遵循 official protocol
- Direct stream terminal validator 唯一拥有 `RESULT` 终态判定
- `EvidenceBackedFactCandidateVNext.evidence_kind` 已移除（不再要求 compactor 产生证据类型标签）
- **无 ownership drift**

**Topic 7 — CLI/public entrypoints**
- `dayu-web`、`dayu-wechat`、`dayu-render` 占位 package scripts 已从 pyproject.toml 移除
- `upload_filings_from` 生成平台脚本（POSIX `.sh` / Windows `.cmd`）
- `dayu-cli init` 拥有交互式 model selection、environment persistence、init lock、以及 OLD-aligned prewarm
- `UploadScriptPublishError` 拥有脚本 publish 安全 contract
- **无 ownership drift**

### Cross-Slice Interactions

| 交互 | 状态 |
|------|------|
| ToolRuntime → accepted_result_projection → memory (Topic 3/4/5) | `AcceptedToolEvidenceLLMMaterial` 单一投影链，无重复解析 |
| Compact → compact_payload → memory (Topic 4) | `parse_context_compacted_semantic_payload` 在持久化边界唯一解析 |
| Compact → memory → run_input (Topic 4) | `_require_compact_memory_event_ref_consistency` 确保一致性 |
| Service → host_assembly → wait_adapter (Topic 5/6) | `fins_wait_adapter.py` 为 Service 层适配器，`wait_adapter.py` 为 Host 端口 |
| CLI → fins batch plan → upload_script (Topic 6/7) | Fins 拥有 batch classification，CLI 拥有 script rendering，边界清晰 |
| Config → tool_discovery → service assembly (Topic 1/2/5) | Provider config 拥有 mode/config，Service 只装配不重算 |

---

## Security / Deferred / NO_CODE Ledger

### Security-Related Boundaries (Disclosed)

| Boundary | Owner | Status |
|----------|-------|--------|
| Fins filesystem containment | `_fs_identity.py`, storage path resolution | Active — 不属于已延后项 |
| Init containment/symlink rejection | `init_workspace.py`, `commands/init.py` | Active — 显式 fail closed |
| Web egress policy | `web_egress_policy.py` | Active — config-controlled |
| Upload script publish containment | `upload_script.py` | Active — 显式 fail closed |
| Path containment decouple from raw-ID grammar | `_fs_identity.py:derive_storage_key` | Active — SHA-256 key mapping |
| Web diagnostic sensitive header filtering | `web_diagnostics.py` | Active — projection layer |

### Deferred to Issues

| Issue | Deferred Item | Current Range Behavior |
|-------|--------------|----------------------|
| #177 | TruncationManager full integration | Doc 不预截断；`ToolTruncateSpec` 等待 #177 完成 |
| #178 | Browser storage-state lifecycle | Config path 保留但无 lifecycle 实现 |
| #175 | Fins Docling process isolation | 当前 range 无新增 Docling process 代码 |
| #142 | Workspace migration framework | Init lock 是当前唯一初始化防护 |
| #151 | Write/assets capability | 无 `dayu/assets` 导入 |
| #84 | Web entrypoint | 占位包已移除，tracked by existing issue |
| #147 | WeChat entrypoint | 占位包已移除，tracked by existing issue |

### NO_CODE / NON_BLOCKING

| Item | Reason |
|------|--------|
| Gemini quota/adherence | 低 budget 测试账号 |
| Darwin Windows skip (AR-F07) | 不包装为 code finding |
| Topic 8 (240-char Engine error) | 在当前 range 之前，已在 `docs/engine/design.md` 记录为 accepted |
| Topic 9 (unified authorization framework) | Design clarification only，不实现 |

### Verified: No Unauthorized Implementation Leaked

- Issue #177 (TruncationManager): 无 leak
- Issue #178 (storage-state lifecycle): 无 leak — 仅保留 config path
- Issue #142 (migration): 无 leak — 仅 init lock
- Issue #151 (write/assets): 无 leak
- Issue #175 (Docling process): 无 leak
- Issues #84/#147 (Web/WeChat): 占位入口已删除
- Render tracker: 占位入口已删除

---

## Test Authenticity

### Observations (Not Findings — Code Review Scope)

- Fresh aggregate validation artifacts 报告 219/219 production Python files 达到 line coverage >=80%
- 测试中 `AcceptedToolEvidenceLLMMaterial` 的构造通过 typed dataclass 而非 raw dict——确保了测试与生产代码共享同一 validation contract
- Memory projection tests 和 compact material tests 的变更反映了 `evidence_kind` 移除和 typed enum 迁移
- 大量 smoke test 文件（`smoke_host_public_r03_semantic_ownership.py`, `smoke_web_ci.py`）验证了 aggregate behavior
- 注意：本 review 未独立运行测试套件；对测试真实性的判断基于代码走读和 Controller 提供的 validation artifacts

### Residual Risk: Test-Related

1. **Non-deterministic Doc directory ordering 的测试覆盖**：`_iter_directory_entries` 现在是确定性排序（casefold→name），但早期测试可能在旧随机顺序下编写。Controller validation 确认相关测试已通过。

2. **HKEX cumulative continuation 的 end-to-end 测试**：HKEX provider 的真实 API 调用可能受速率限制。Smoke 测试可能使用 fixture。validation artifacts 可作测试证据。

---

## Open Questions

1. **`_require_compact_memory_event_ref_consistency` 是否在首个 Run 的 `NoopCompactArtifactProvider` 与 `NoopMemorySnapshotProvider` 之间触发**：两个 noop provider 返回 `compaction_event_ref=None` 和 `latest_compaction_event_ref=None`，一致 → 不触发。确认安全。

2. **`run_input_material_block()` 的 `text` 参数文档描述是否需要更新**：当前 docstring 说 `text` 是"原始或已规范化文本"，但 evidence block 实际要求必须与 renderer 输出 exact match。建议更新 docstring 明确此约束。

---

## Residual Risk

1. **Mark ready TOCTOU 文档缺失**（Finding 2）：未来若 `mark_ready()` 被移动到异步上下文，需要同时引入锁保护。当前风险低。

2. **Doc tool heap 对 extreme inputs 的行为**：当 `actual_limit` 非常大时，heap 会容纳所有匹配文件。`DocToolLimits.list_files_max` 默认值控制此限制。测试覆盖了常规输入。

3. **`_execution_health` gate 的单点故障**：如果 `HostExecutionHealthGate.report_fatal()` 被错误调用，整个 scheduler 进入 UNAVAILABLE。这是设计意图（fail-closed），但如果只有一个 critical task 的非致命错误触发 fatal，会过度反应。当前 `_start_critical_task` 只对 unexpected exit (not CancelledError) 报告 fatal——这是正确的边界。

4. **Web diagnostics v2 schema 的稳定性**：`WEB_DIAGNOSTIC_SCHEMA_REVISION = 2` 是硬编码。未来修订需要版本迁移策略。当前无消费者要求跨版本兼容性。

5. **`_fs_identity.py` 的 SHA-256 namespace+identity 映射**：如果 namespace 或 identity 包含非 UTF-8 字符，会在 `_derive_storage_key` 中 fail-closed。当前 `_require_external_identity` 要求 UTF-8 编码。未来若出现非 UTF-8 identity（罕见），需要处理。

---

## Verdict

**Aggregate tree `0db1c91f92dca594cf77c74bbde8f5b4fc42710d` 通过了对抗性失败审查和语义所有权漂移审查。**

Topics 1-7 的全部 Controller adjudication 已正确实现：
- 无 LLM-facing 泄露
- 无 semantic ownership drift
- 无 unauthorized issue implementation leaked
- 无新增 security finding（当前 defensive safety 边界已正确保留）
- 发现 1 个 material observation（2-MATERIAL），1 个 maintainability finding（Finding 2），2 个 material observations 经确认无需修复

建议接受当前 aggregate tree 进入后续 gate。

---

## Artifact Integrity

- **Artifact SHA**: (to be filled by Controller post-write)
- **Reviewer**: AgentDS
- **Immutable range verified**: `b1a0631f397967e7530b676a90ef7467d83a1817^..85aa7184a694448a5b27da7cca52f753f84d6e20`
- **HEAD**: `85aa7184a694448a5b27da7cca52f753f84d6e20` ✓
- **Tree**: `0db1c91f92dca594cf77c74bbde8f5b4fc42710d` ✓
- **Staged**: empty ✓
- **Dirty tracked**: `docs/host/issues-implementation-control.md` (Controller-owned) ✓
- **Dirty untracked**: 5 Controller-owned artifacts ✓
