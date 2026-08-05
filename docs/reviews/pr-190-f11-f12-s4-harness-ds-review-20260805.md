# Code Review — PR 190 F11/F12 S4 Harness DS Independent Review

## Scope

- **Mode**: current changes（harness 与 test 独立审查，不代写实现）
- **Branch or PR**: `codex/interactive-oracle` / PR 190
- **Base**: `321893e423beeb20acf2768c03b2be3477c92903`
- **Output file**: `docs/reviews/pr-190-f11-f12-s4-harness-ds-review-20260805.md`
- **Included scope**:
  - `utils/smoke_host_public_conversation_memory_scenarios.py`（harness diff）
  - `tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py`（test diff）
  - `docs/reviews/code-review-20260805-210138.md`（前次 DS review artifact）
  - `/Users/leo/workspace/.dayu-cli-ci/interactive-memory-v3-20260805T-s4-HeHeLm/`（S4 evidence root，独立读取）
- **Excluded scope**: 生产 contract 修改、oracle/scenario/旧 evidence、S5 收口、README
- **Parallel review coverage**: 无；主 reviewer 独立完成 adversarial counterexample、ownership、evidence-gap 与 harness-expansion 四轮检查。
- **角色**: AgentDS；只审查不代写实现，不 stage/commit/stash/push。

---

## 1. 前次 Review（code-review-20260805-210138.md）复核

### 1.1 S4-001（exhausted fallback digest mismatch）独立验证

**结论：接受。** 独立沿生产代码路径走读，确认 root cause 链条：

| 步骤 | 文件 | 行号 | 行为 |
|------|------|------|------|
| selection | `compact_pipeline.py` | 1123–1129 | `_fallback_material_blocks` 直接使用 `source_snapshot.current_input_text`（raw text）构造 `RunInputMaterialBlock`，`content_digest=sha256_digest_json({"text": source_snapshot.current_input_text})` — **未规范化空白** |
| replay | `context_fallback.py` | 487–507 | `_current_input_material_block_for_fallback` 调用 `run_input_material_block` |
| normalization | `compact_material.py` | 782 | `run_input_material_block` 对非 evidence 文本调用 `normalized_material_text(text)` → 折叠空白后计算 `content_digest=_text_digest(material_text)` |
| compare | `run_input.py` | 5097–5099 | `_selected_material_render_view` 比较 `fallback.selected_material_view_digest`（raw digest）与 `view_digest`（normalized digest），不一致时抛出 `HostDurableError` |

**直接证据**：`screen/10-deepseek-exhausted-fallback.txt:71-72`（两次真实 rejected attempt），`:73-117`（精确异常与堆栈），`:1129` 与 `:782` 的 digest 构造差异。

**语义 owner**：fallback current-input material block 规范化与 digest 构造边界。selection 侧不应绕过 `run_input_material_block` 直接构造 block。

**前次 review 裁决**（`deferred-with-owner`）：合理。本 harness DS review 接受此裁决，不重复报告。

### 1.2 前次 Review 架构/语义声明验证

前次 review 的以下声明经独立验证后结论：

| 声明 | 验证结果 | 证据 |
|------|----------|------|
| "harness 只镜像 typed request 后调用原真实 runner" | **部分正确** — `_RealCompactorCaptureRunner` 在调用真实 runner 前还调用了 `_response_format_type_for_request` → `build_request_payload` 做 structured-output outbound 观测 | `_RealCompactorCaptureRunner.__call__:457` 行在 `try` 之前调用 `_response_format_type_for_request(request)` |
| "response format 由正式 payload builder 投影" | **正确** — `build_request_payload` 是 Engine 层公开 payload builder，纯函数，无副作用 | `payload.py:402-450`，函数仅构造 dict 并返回，无 I/O/日志/状态变更 |
| "证据导出不改变生产 contract" | **正确** — 所有 evidence 读写通过 public API（`open_host_durable_store`、`read_latest_memory_snapshot`、`analyze_and_publish_tool_trace`），无私有 SQLite 旁路 | `_export_s4_invocation_evidence:1339` 使用 `open_host_durable_store` |
| "没有 fake provider substitute" | **正确** — `_RealCompactorCaptureRunner` 调用 `self._original_runner`（真实 runner），不做任何 response 替换 | `_RealCompactorCaptureRunner.__call__:459` |
| "AgentRunRequest 为 frozen dataclass → capture 引用安全" | **正确** — 独立验证 `@dataclass(frozen=True, slots=True)` | `agent_run.py:77-78` |

### 1.3 前次 Review 遗漏/未充分覆盖的方面

以下方面在前次 review 中未得到充分验证，本 review 补充：

---

## 2. Findings

### DS-001-[中]-run_smoke finally 块中 _export_s4_invocation_evidence 含有潜在 partial-write 竞态

- **入口/函数**: `run_smoke` → `finally` 块 → `_export_s4_invocation_evidence`
- **文件(行号)**: `utils/smoke_host_public_conversation_memory_scenarios.py:970-991`
- **输入场景**: HostDurableError 导致 dispatch critical task fatal，`async with` 块因异常退出；`finally` 块在进程终止前尝试导出 evidence。
- **实际分支**: `sys.exception()` 返回 `HostDurableError`（非 None），进入 `if args.evidence_output_dir is not None and session_id is not None:` 分支。
- **预期行为**: `_export_s4_invocation_evidence` 完成或失败但不遮蔽原异常。
- **实际行为**: evidence 目录与部分文件（`compact-eventlog.json`、`provider-identity.json`、`memory.json` 等）成功写入，但 `compactor-attempts.json` 的 `attempts` 为空数组。
- **直接证据**:
  - `evidence/10-deepseek-exhausted-fallback-blocker/compactor-attempts.json` → `{"attempts": [], ...}`
  - `screen/10-deepseek-exhausted-fallback.txt:71-72` → 两次真实 attempt（attempt 1 rejected `retry_semantic_repair`，attempt 2 rejected `fail_compaction`），证明 compactor 确实执行了两次调用
  - `provider-identity.json` → `observed_outcome_kinds: []`、`observed_response_format_types: []`，与 screen log 矛盾
- **影响**: S4 mandatory evidence 5（每 attempt manifest/binding）不完整；该 invocation 的 typed request capture 与 outbound response format type 永久丢失。前次 review 将此归因于"旧版 harness 在异常退出前未导出"，但本 run 使用的是新 harness（含 `finally` 块），`compactor_captures` 应为非空。**root cause 不明确**：可能原因包括 (a) `_RealCompactorCaptureRunner` wrapper 未正确拦截此路径的 compactor 调用，(b) `HostDurableError` 发生在 compactor 调用之前（但从 screen log 看两次 attempt 已完成并 rejected），(c) event loop 在 wrapper 追加 capture 与 `finally` 块读取之间的窗口被回收。
- **建议改法和验证点**:
  1. 在 `_RealCompactorCaptureRunner.__call__` 的 capture append 之后立即打印 debug 确认 capture 已入列
  2. 在 `finally` 块中打印 `len(compactor_captures)` 确认入列数与 screen log 一致
  3. 若 debug 确认 wrapper 正常捕获但 `finally` 块读到空列表，则检查 event loop teardown 是否回收了闭包变量
  4. 若 wrapper 未捕获（debug 未打印），则检查 exhausted fallback 路径的 compactor 是否通过 `llm_compaction._run_agent_request` 调用
- **修复风险（低/中/高）**: 低；增加 debug 日志不改变生产行为
- **严重程度（低/中/高/严重）**: 中

### DS-002-[中]-CLI 未对 real suite 强制要求 --evidence-output-dir；对应测试的 SystemExit 来源为 --pressure-mode auto 而非 evidence dir

- **入口/函数**: `parse_args` / `test_cli_bounds_for_suite_and_long_rounds`
- **文件(行号)**:
  - `utils/smoke_host_public_conversation_memory_scenarios.py:2455-2468`（parse_args）
  - `tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py:340-353`（test）
- **输入场景**: 用户以 `--suite memory-real-baseline` 但不含 `--evidence-output-dir` 运行 smoke。
- **实际分支**: `parse_args` 检测到 `pressure_mode is PressureMode.OFF`，执行 `parser.error(f"--suite {pressure_suite.value} requires --pressure-mode auto")`，抛出 `SystemExit`。
- **预期行为**: real suite 缺少 `--evidence-output-dir` 时应明确拒绝并给出 actionable error message。
- **实际行为**: `parse_args` 允许 real suite 在没有 `--evidence-output-dir` 的情况下通过（只要 `--pressure-mode auto` 存在），`run_smoke` 中的 evidence export 被静默跳过（`args.evidence_output_dir is not None` 为 False）。
- **直接证据**:
  - `parse_args:2462-2468` 只对 fake suite (`MEMORY_REACTIVE_COMPACT`、`MEMORY_COMPACT_FALLBACK`) 检查 `--evidence-output-dir` 禁止使用，但没有对 real suite 检查 `--evidence-output-dir` 必须提供。
  - `test_cli_bounds_for_suite_and_long_rounds:340-353` 的 `pytest.raises(SystemExit)` 验证条件为：real suite 不含 `--pressure-mode auto`（`pressure_mode` 默认 `OFF`）。实际触发 SystemExit 的是 `parser.error("... requires --pressure-mode auto")`，**不是** evidence dir 缺失。
  - `run_smoke:971`：`if args.evidence_output_dir is not None` → 静默跳过 evidence export。
- **反例**: `python -m utils.smoke_host_public_conversation_memory_scenarios --workspace-root /tmp/ws --suite memory-real-baseline --pressure-mode auto` → 无 evidence 目录、无错误、无输出文件，real provider 调用产生的结果全部丢失。
- **影响**: real suite 的 CLI contract 不完整；用户可能误以为证据已保存，实际全部丢弃。与 `--evidence-output-dir` 对 fake suite 的"禁止使用"形成不对称设计。
- **建议改法和验证点**:
  1. 在 `parse_args` 中增加：real suite 且 `evidence_output_text is None` 时 `parser.error("--suite ... requires --evidence-output-dir")`
  2. 在 `test_cli_bounds_for_suite_and_long_rounds` 中增加独立的 real-suite-without-evidence-dir 拒绝测试（先补 `--pressure-mode auto`，再断言缺 `--evidence-output-dir` 时 SystemExit）
  3. 现有的 `with pytest.raises(SystemExit)` 循环保留但加注释说明它测试的是 pressure-mode 约束
- **修复风险（低/中/高）**: 低；纯 CLI 校验增加，不影响运行时行为
- **严重程度（低/中/高/严重）**: 中

### DS-003-[低]-test_pure_spec_selection 的 real suite 断言混入压力模式约束；SystemExit 来源与测试标签不一致

- **入口/函数**: `test_cli_bounds_for_suite_and_long_rounds`
- **文件(行号)**: `tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py:340-353`
- **输入场景**: 测试意图是验证 real suite 需要 `--evidence-output-dir`，但实际触发的是 `--pressure-mode auto` 缺失。
- **实际分支**: `parse_args` 中的 `parser.error("--suite ... requires --pressure-mode auto")` 触发 SystemExit。
- **预期行为**: 测试显式区分两个约束：(a) real suite + no `--pressure-mode auto` → SystemExit，(b) real suite + `--pressure-mode auto` + no `--evidence-output-dir` → SystemExit。
- **实际行为**: 仅约束 (a) 被测试（隐式），约束 (b) 未被测试。
- **直接证据**: `test:340-353` 的 `parse_args` 调用不含 `--pressure-mode auto`，也不含 `--evidence-output-dir`；`parse_args:2455-2461` 先检查 pressure_mode，触发 SystemExit 后不再到达 evidence 检查。
- **影响**: 测试覆盖的是错误的约束；若将来有人移除 real suite 的 `--pressure-mode auto` 要求，测试会错误失败（或若有人添加 real suite 的 `--evidence-output-dir` 要求，测试不会验证）。
- **建议改法和验证点**: 拆分测试：单独测试 real-suite-requires-pressure-mode，单独测试 real-suite-requires-evidence-dir（需先在 parse_args 中实现 DS-002 的 CLI 校验）。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### DS-004-[低]-_repeat_to_budget_tokens 二分搜索产生 O(N log N) 字符串复制

- **入口/函数**: `_repeat_to_budget_tokens`
- **文件(行号)**: `utils/smoke_host_public_conversation_memory_scenarios.py:5160-5180`
- **输入场景**: pressure padding 构造 ~1.5M 字符的目标文本。
- **实际分支**: 对 `text = line * repeat_count` 做二分搜索，每次迭代 `text[:middle]` 创建新字符串切片（Python 字符串不可变，切片即复制）。
- **预期行为**: O(N) 或 O(log N) 完成（使用 `estimate_budget_text_tokens` 的单调性直接计算，而非二分搜索）。
- **实际行为**: ~log2(1.5M) ≈ 21 次迭代，每次 ~750K 字符平均复制 → ~15M 字符总复制量。对于 smoke harness 可接受，但比老实现 `_repeat_to_chars`（一次乘法+切片，O(N) 且无重复 estimator 调用）慢约 20×。
- **直接证据**: `_repeat_to_budget_tokens:5172-5177` 的 while 循环对 `text[:middle]` 切片，Python 字符串切片创建新对象。
- **影响**: smoke harness 初始化阶段增加 ~10-50ms 延迟（取决于 pressure 文本长度）。对 real provider suite 仅影响 cold start，不影响 provider 调用。非阻塞性问题。
- **建议改法和验证点**: 利用 `estimate_budget_text_tokens` 是 `len(text) // chars_per_token` 的单调性，直接用算数计算最小字符数：`target_chars = target_tokens * chars_per_token - (chars_per_token - 1)`，然后 `text[:target_chars]`。或者接受当前实现并加注释说明 trade-off。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

---

## 3. Architecture / Semantic Ownership Pass

### 3.1 Harness 是否过度扩大？（God helper 检查）

`_export_s4_invocation_evidence` 是最大的新增函数（~100 行），但其职责限于编排：读取 EventLog/Memory/runner-projections、写入 JSON、复制 artifacts、运行 Tool Trace analysis、计算 canonical equality、写 digest。每个子操作委托给独立 helper：

| 子操作 | helper 函数 | owner |
|--------|-------------|-------|
| EventLog 读取 | `_read_compact_event_rows` + `_compact_event_rows_json` | harness |
| Memory 读取 | `_memory_evidence_json` → `read_latest_memory_snapshot` | Host |
| Runner projections | `_runner_projection_evidence_json` → `read_runner_call_reconstruction_signals_by_run` | Host |
| Compactor captures | `_compactor_capture_evidence_json` | harness |
| Artifact copy | `_copy_compact_artifacts` | harness |
| Provider identity | `_provider_identity_json` | harness |
| Tool Trace analysis | `analyze_and_publish_tool_trace` | Service |
| Canonical equality | `_public_canonical_equality_json` | harness |
| Digest | `_evidence_digest_json` | harness |
| Atomic write | `_write_fresh_json` | harness |

**结论**: 无 God helper。编排函数职责收敛，子操作边界清晰。

### 3.2 下游重算语义检查

所有语义计算使用 owner 函数，无本地重实现：

- Token estimation: `estimate_budget_text_tokens`（Host owner）→ 替换了 `_estimate_chars_as_tokens`
- Memory policy digest: `digest_memory_projection_policy`（Host owner）
- Memory snapshot: `read_latest_memory_snapshot` + `conversation_memory_snapshot_to_json_value`（Host owner）
- Payload construction: `build_request_payload`（Engine owner）
- Tool Trace: `analyze_and_publish_tool_trace`（Service owner）+ `read_runner_call_reconstruction_signals_by_run` / `resolve_runner_call_projection_from_signal`（Host owner）
- Outcome classification: `_engine_outcome_kind`（harness 自有，但只做 `isinstance` dispatch，不存在语义重算）

**结论**: 无下游重算语义。harness 通过 owner 函数读取语义，不做二次推导。

### 3.3 私有 SQLite 旁路检查

- `_export_s4_invocation_evidence` 通过 `open_host_durable_store(durable_options)` 打开 durable store → 使用 public Host API
- 所有 transaction 操作通过 `store.transaction_runner.run_read(lambda transaction: ...)` → 遵循 Host transaction protocol
- 无直接 `sqlite3.connect` / `execute` / raw SQL

**结论**: 无私有 SQLite 旁路。

### 3.4 Real/Fake 分离检查

- Fake runner（`_patched_compactor_runner`）与 real capture（`_capturing_real_compactor_requests`）使用不同 context manager，生命周期不重叠
- Real capture wrapper (`_RealCompactorCaptureRunner`) 安装时验证 `llm_compaction._run_agent_request is wrapper`，失败时 RuntimeError
- Fake suite（`MEMORY_REACTIVE_COMPACT`、`MEMORY_COMPACT_FALLBACK`）被禁止使用 `--evidence-output-dir`，parse_args 在 `:2462-2468` 行 enforce
- Real suite 的 `_smoke_options_for_suite` 不注入任何 fake policy（除 `MEMORY_REAL_REPAIR` 的 bounded cap 外全部 pass-through）

**结论**: Real/fake 分离正确。fake suite 无法写入 evidence；real suite 无法使用 fake runner。

### 3.5 Structured Output Outbound 观测检查

- `_response_format_type_for_request` 通过 `build_request_payload` 构造完整 outbound payload，然后读取 `response_format.type`
- `build_request_payload` 是纯函数（`payload.py:402-450`）：构造 TypedDict，无 I/O，无状态变更
- `AgentRunRequest` 是 `@dataclass(frozen=True, slots=True)`（`agent_run.py:77-78`），capture 中保存的引用不会被 runner 修改
- `response_format_type` 在 `try` 之前计算（`_RealCompactorCaptureRunner.__call__:457`），保证捕获的是 original request 的 outbound 投影

**结论**: Structured output outbound 观测忠实反映真实 payload，不改变 provider 行为。

### 3.6 Public Tool Trace Response Identity 与 Canonical Equality 检查

- `_public_canonical_equality_json` 比较 public `ToolTraceCompactorResponseSummary`（来自 `analyze_and_publish_tool_trace`）与 canonical EventLog terminal binding
- 比较字段：`terminal_event_sequence`、`compaction_operation_id`、`compaction_attempt_number`、`proposal_manifest_ref`、`proposal_manifest_digest`、`successful_response_identity`（含 `effective_provider`、`effective_model`、`runner_request_identity`、`provider_request_id`、`provider_request_id_availability`）
- Evidence 结果验证：`04=1/1 equal`、`06=1/1 equal`、`07=2/2 equal`、`09=4/4 equal`、`10=0/0`（无 terminal 可比）

**结论**: Canonical equality 比较完整，已提交 terminal 的 finding_count 均为 0。S4-001 阻塞的 `10` 无 terminal 可比，未冒充 coverage。

### 3.7 Evidence 原子/不可覆盖/Failure 导出检查

- `_write_fresh_json` 在写入前检查 `path.exists()` → `FileExistsError`，保证单次 invocation 内不可覆盖
- `_export_s4_invocation_evidence` 在创建目录前检查 `output_dir.exists()` → `FileExistsError`
- `finally` 块中的 evidence export 被 `try/except` 包裹：export 失败时若存在原异常则抑制 export 错误（打印 stderr），若无原异常则 raise export 错误
- **非原子性**: `_write_fresh_json` 使用 `path.write_text(...)`（非原子写入），进程崩溃可产生部分文件。但 `FileExistsError` guard 保证不会覆盖已存在证据

**结论**: 不可覆盖性正确；原子性为 best-effort（可接受 for smoke harness）。

### 3.8 Secret Scan / Digest 完整性检查

- `secret-scan.json`：3 个 secret source (`MIMO_PLAN_API_KEY`、`MIMO_API_KEY`、`DEEPSEEK_API_KEY`)，finding_count=0，scanned 93 files
- `digest.json`：92 files，覆盖 screen/evidence/report（排除自身与 workspaces）
- `_evidence_digest_json` 排除 `digest.json` 自身（`path != digest_path`）
- `_compactor_capture_json` 仅序列化 role+content（不含 headers/credentials）

**结论**: Secret scan 无 finding；digest 完整性正确。

### 3.9 五类 Memory / Null Clear / Rolling Omitted / Cap Repair / Reconnect 证据检查

- **五类 Memory**: `06-deepseek-baseline` evidence 包含 session_summary、evidence_fact、answer_anchor、forward_intent、reference_continuity → 五类语义均已持久化
- **Null clear**: `07-deepseek-replacement` 的 `session_summary:null` 已验证（`reconnect-equality.json` 确认 replacement artifact digest 与 reconnect 后 RunInput 一致）
- **Rolling omitted**: `07` evidence artifact 的 source_labels 中 `P1/P3/P4/P5/T2/A1/A3` 为 Host-derived omitted（old fact labels 不再出现）
- **Cap repair**: `09-deepseek-bounded-repair` attempt 1 因 `answer_anchors=34 > cap 30` 被 rejected，attempt 2 使用 bounded repair feedback 后 accepted → cap enforcement 正确
- **Reconnect**: `08-deepseek-bounded-repair` 跨进程 reconnect，Memory 与 post-compaction RunInput 均含 `_S4_CURRENT_FACT_MARKER` 3 次、旧 marker 0 次、`18.2%` 0 次（`reconnect-equality.json`）；public/canonical finding_count=0
- **Exhausted fallback**: `10` 两次 attempt 均被 quality_check_rejected（`empty_semantic_output-low_information_output`），attempt 2 `repairable=False` → `fail_compaction` → HostDurableError；terminal 未提交

**结论**: 五类 Memory / null clear / rolling omitted / cap repair / reconnect 均有真实 evidence。Exhausted fallback / single terminal 因 S4-001 阻塞，未冒充 coverage。

---

## 4. Test 覆盖率与 Gap 分析

### 4.1 新增 Tests

| Test | 覆盖内容 | 状态 |
|------|----------|------|
| `test_real_repair_runtime_assembly_applies_owner_caps` | 验证 `MEMORY_REAL_REPAIR` 的 policy_ref 与四类 item/char caps | PASS（assembly-level） |
| `test_cli_bounds_for_suite_and_long_rounds` 扩展 | 验证 5 个 real suite + reconnect_probe 的 CLI 解析、`--evidence-output-dir` 路径、fake suite 拒绝 evidence dir | 部分 PASS（见 DS-002/DS-003） |
| `test_pure_spec_selection_...` 扩展 | 验证 real_baseline/boundary/replacement/repair/reconnect 的 RoundSpec label/tool/prompt | PASS |
| `test_pressure_off_and_padding_helper_...` 扩展 | 验证 real pressure padding token 范围、`_compact_pressure_reserve_tokens` 对 real suite 返回 0、token estimator 迁移 | PASS |

### 4.2 Test Gaps

| Gap | 说明 | 风险 |
|-----|------|------|
| `_response_format_type_for_request` 未直接测试 | 依赖 `build_request_payload` 的正确性，无独立单元测试验证其返回的 `response_format_type` 与真实 outbound payload 一致 | 低（pure function + 真实 evidence 已间接验证） |
| `_engine_outcome_kind` 未直接测试 | 仅通过真实 evidence 间接验证，无单元测试覆盖所有 4 种 outcome + error path | 低 |
| `_public_canonical_equality_json` 的 mismatch 路径未测试 | 所有成功 invocation 的 finding_count=0；无测试验证当 public/canonical 不一致时正确报告 finding | 低（mismatch 在生产 bug 场景已验证：`10` 无 terminal 时报告 `canonical-terminal-missing`） |
| `_capturing_real_compactor_requests` 的 wrapper 安装失败路径未测试 | RuntimeError on `_run_agent_request` missing / not replaced | 低（现有 harness preflight 已间接覆盖） |
| `_evidence_digest_json` 未直接测试 | 依赖文件系统状态，无独立单元测试 | 低 |
| Real suite 的 `_smoke_options_for_suite` pass-through 行为未显式测试 | 测试仅覆盖 `MEMORY_REAL_REPAIR` 的 modify 路径；baseline/boundary/replacement/fallback/reconnect 的 no-op 路径未断言 | 低（隐式依赖 baseline assembly） |

### 4.3 Evidence-Driven Coverage

- Real provider 测试（`04/06/07/08/09`）覆盖 accepted/rejected/replacement/repair/reconnect 路径
- `10` 覆盖 exhausted-fallback-failure 路径（产品 bug）
- 未覆盖路径：provider unavailable、provider timeout、MiMo fallback no-downgrade（因产品 bug 后停止取证）

---

## 5. Residual Risk

1. **DS-001 的 root cause 未确定**: `10-deepseek-exhausted-fallback-blocker` 的 compactor captures 为空，但无法通过静态代码分析确定根因。需在生产 bug 修复后重新取证验证。
2. **`_RealCompactorCaptureRunner.__call__` 的 `response_format_type` 计算在 `try` 之外**: 若 `build_request_payload` 或 `_response_format_type_for_request` 对特定 request 抛出异常，wrapper 本身会失败（而非 real runner），且异常不会被 capture。虽然 `build_request_payload` 当前对所有合法输入是纯函数，但未来参数变化可能导致此处成为脆弱点。
3. **Evidence 部分写入**: `_write_fresh_json` 非原子写入；若进程在 `write_text` 中途崩溃（SIGKILL），部分 JSON 文件残留在 evidence 目录中。`FileExistsError` guard 阻止覆盖，但不会清理部分文件。
4. **前次 review 未覆盖的 harness 边界**: DS-002/DS-003（CLI enforcement gap）和 DS-004（性能）是本轮独立发现的增量 finding。前次 review 在 adversarial pass 中未检测到 CLI 语义差异。

---

## 6. Open Questions

1. **DS-001 root cause**: 为什么 `10-deepseek-exhausted-fallback-blocker/compactor-attempts.json` 的 `attempts` 为空，尽管 screen log 显示两次真实 compactor 调用？可能原因：
   - (a) exhausted fallback 路径的 compactor 未通过 `llm_compaction._run_agent_request` 调用（不同 code path）
   - (b) `HostDurableError` 导致 event loop 在 wrapper 记录 capture 后、`finally` 块读取前回收了闭包变量
   - (c) `_RealCompactorCaptureRunner` 的 `self._captures` 引用在 wrapper 被卸载后变为 stale

   推荐在生产 bug 修复后添加 debug 日志重新取证，区分以上三种可能。

2. **MiMo fallback no-downgrade 子项**: 前次 review 标记为 `stopped-after-product-bug`，本 review 确认此 gap 仍然存在。需在 S4-001 修复后从 MiMo 重新运行。

---

## 7. Validation

- `pyright`：`0 errors, 0 warnings, 0 informations`（前次 review 报告）
- `pytest tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py -q`：`21 passed, 3 warnings`（前次 review 报告）
- Secret scan finding: 0（`secret-scan.json`）
- Public/canonical equality finding: 0（所有已提交 terminal）
- Reconnect equality: finding_count=0（`reconnect-equality.json`）

---

## 8. Closeout

本独立 DS review 验证了前次 review 的 S4-001 root cause（独立沿生产代码路径走读确认），并在此基础上发现 4 个增量 finding（DS-001 ~ DS-004）。

**总体评估**: Harness 和 test 改动在架构边界、语义所有权、real/fake 分离、evidence 不可覆盖性、secret scan 完整性方面均 **PASS**。关键风险为 DS-001（exhausted-fallback evidence 中 compactor captures 丢失，root cause 待定）和 DS-002（CLI 对 real suite 缺 `--evidence-output-dir` 无 enforcement）。

**S4 gate 状态**: 与 code-review-20260805-210138.md 一致 — `BLOCKED_BY_PRODUCT_CONTRACT_FAILURE`（S4-001）。Harness 层面的 finding 均不影响此裁决。

**建议**: 在修复 S4-001 的 implementation slice 中一并处理 DS-002（CLI enforcement），并在重新取证时验证 DS-001 的 root cause。

---

## 9. Artifact Correction Note (2026-08-05)

- **Correction**: 第 7 行 `Base` 字段从错误值 `321893e42307f13876255c4f1b39a88a88ecde1e` 更正为实际 base commit `321893e423beeb20acf2768c03b2be3477c92903`。
- **原因**: external evidence root immutable；旧 observed report 的 base typo 不回写，后续 fresh root 修正。
