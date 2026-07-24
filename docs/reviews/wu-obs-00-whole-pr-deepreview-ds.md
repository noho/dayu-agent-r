# WU-OBS-00 Whole-PR Deepreview — AgentDS

## Verdict

**needs-fix** — 存在 1 个中等严重度的 cold snapshot 错误覆盖问题和 1 个低严重度语义边界问题，整体实现质量高但不该以当前状态 ship。其余涉及 correctness、stability、maintainability、分层/反向依赖、semantic ownership drift、LLM-facing 文本、只读/lock/SQLite/input integrity、public exports、tests 与 README 的检查面均为 pass。

---

## Scope

- Mode: PR
- Repository: noho/dayu-agent-r
- PR: #186
- Base: main@9588ee7a
- Head: 9519b029
- Output file: docs/reviews/wu-obs-00-whole-pr-deepreview-ds.md
- Included scope: 90 files, +23285/-50
  - Production: 17 files（6 new: contracts/input/rules/analysis/Service/CLI command; 7 modified: connection/transaction/tool_trace durable/tool_trace projection/open_host/__init__; 2 CLI: arg_parsing/main; 1 Host README; 1 Service README）
  - Tests: 8 new files, 3 modified files（4098 lines new tests）
  - Docs: 5 README updates, 1 plan, multiple review artifacts
- Excluded scope: docs/reviews/ 下的 controller adjudication、codex implementation、re-review 等历史 artifact（Controller chain 仅作证据参考，不作为独立审查替代）
- Parallel review coverage: 无（单 AgentDS 独立完整审查）
- Verification executed:
  - `pytest` focused+full matrix: 241 passed, 0 failed
  - `pyright`: 0 errors, 0 warnings
  - `coverage`: contracts 89%, input 84%, rules 94%, analysis 100%, Service 95%, CLI commands 100%（all ≥80%）
  - Workspace directory smoke: JSON valid (765 lines), Markdown non-empty (83 lines)
  - Cold-file smoke: JSON valid, Markdown non-empty
  - `git diff --check`: pass

---

## Findings

### 1-未修复-中-cold snapshot 读取失败时 handle.close() 错误覆盖主错误

- **入口/函数**: `_capture_cold_prefix` → `load_tool_trace_analysis_input`
- **文件(行号)**: `dayu/host/tool_trace_analysis_input.py:792-817`
- **输入场景**: cold JSONL 前缀读取（`_read_exact_prefix`）因 short read / truncate 失败，且随后 `handle.close()` 也因底层 I/O 失败而抛 `OSError`。
- **实际分支**: `try` 块中 `_read_exact_prefix` 或 identity check 抛 `OSError` → `except OSError` 准备构造 `ToolTraceAnalysisInputError(reason=COLD_SNAPSHOT_READ_FAILED, summary="无法从同一 handle 读取完整 cold snapshot prefix.")` → 在 `raise` 前进入 `finally` → `handle.close()` 也抛 `OSError` → `finally` 中 `raise ToolTraceAnalysisInputError(summary="关闭 cold snapshot handle 失败。")`。
- **预期行为**: 主错误（prefix read failure）应作为 primary exception 传播给调用方；close 失败应作为 suppressed secondary detail 或 best-effort 日志，不得覆盖 primary。
- **实际行为**: Python `finally` 中的 `raise` 替换了当前 propagation 中的异常。`__context__` 隐式链保留原始异常，但 primary exception type/message/summary 变为 close failure，导致 operator 和上层 error mapping 看到 "关闭 cold snapshot handle 失败" 而非真正的读取失败原因。
- **直接证据**:
  - `tool_trace_analysis_input.py:792-801` — `except OSError as exc: raise ToolTraceAnalysisInputError(...)` 在 finally 之前。
  - `tool_trace_analysis_input.py:808-817` — `finally: try: handle.close() except OSError as exc: raise ToolTraceAnalysisInputError(...)` 无条件覆盖。
  - Python 语言语义：`finally` 中的 `raise` 替换正在传播的异常（见 [PEP 3134](https://peps.python.org/pep-3134/) 及 Python 异常链文档），虽然 `__context__` 保留但 primary 已被替换。
- **影响**: 真实 cold snapshot 读取失败原因被隐藏，operator 和 `ToolTraceAnalysisInputError.reason/summary` 收到误导性错误描述，诊断和排障方向错误。
- **建议改法和验证点**:
  1. `finally` 中 `handle.close()` 的异常不应重新 raise；应改为 best-effort close（复用 `_close_cold_handle_best_effort` 或在 `finally` 内 `except OSError: pass`）。
  2. 如需保留 close failure 可观测性，可记录 warning 日志但不得替换 primary exception。
  3. 验证：`test_cold_prefix_read_error_not_masked_by_close_failure` —— 使用 mock handle 同时让 read 和 close 失败，断言最终异常 message 为读取相关而非 close 相关，且 `reason=COLD_SNAPSHOT_READ_FAILED`。
- **修复风险（低）**: 仅改变 finally 中 close 失败的传播策略；不影响正常路径。
- **严重程度（中）**: 不影响正常路径正确性，但错误诊断路径存在信息丢失，影响 operators 排障。

### 2-未修复-低-rules 模块导入 `_tool_trace_cold_lock_path` 超出 plan 定义的 consumer set

- **入口/函数**: `build_tool_trace_analysis_report` → `_input_summary`
- **文件(行号)**: `dayu/host/tool_trace_analysis_rules.py:48`; `dayu/host/tool_trace_analysis_rules.py:1927-1931`
- **输入场景**: 所有正常分析路径。
- **实际分支**: `_input_summary` 在 `dataset.cold_snapshot is None`（hot-only 目录输入）时调用 `_tool_trace_cold_lock_path(source.cold_jsonl_path)` 派生 lock path 填入 report 的 `cold_lock_path` 字段。
- **预期行为**: Plan §5.1 和 §12.1 明确 `_tool_trace_cold_lock_path` 是 "Host 内部 producer/reader 复用同一内部 helper"，且 "helper 不从 Host root 导出"、Service/CLI 不调用。plan 未授权 rules 模块（report builder）作为 consumer。
- **实际行为**: rules 模块从 `dayu.host.tool_trace` import 了下划线私有 helper 并使用它。这没有造成 correctness 问题（行为正确），但违反了 plan 的 consumer boundary：plan 只承诺 producer 和 Analyzer input loader（input 模块）复用该 helper，rules 模块作为 report builder 不应依赖 Tool Trace projection 的内部路径派生。
- **直接证据**:
  - `dayu/host/tool_trace_analysis_rules.py:48`: `from dayu.host.tool_trace import _tool_trace_cold_lock_path`
  - Plan §5.1 行 291: "Host 内部 producer/reader 复用同一内部 helper"
  - Plan §12.1 行 1151-1153: "helper 不从 Host root 导出；不改 event filter、cold schema..."
- **影响**: 低——当前行为正确，但 rules 模块对 Tool Trace projection 内部实现的依赖较 plan 更宽，未来若 lock path 派生逻辑变化，rules 模块也被牵连。hot-only 路径下 report 中的 `cold_lock_path` 是"expected"路径（从未实际获取锁），语义上与 `capabilities.cold=false` 一致，但 rule 模块参与路径派生增加了不必要的耦合。
- **建议改法和验证点**:
  1. 方案 A（推荐）：让 input 模块在 `ToolTraceAnalysisDataset` 中新增 `expected_cold_lock_path: Path` 字段，由 `load_tool_trace_analysis_input` 在构造 dataset 时固定；rules 模块只读取 dataset 字段，不再 import `_tool_trace_cold_lock_path`。
  2. 方案 B：若判定 rules 模块在 Host 内部且 uses 属于合理扩展，更新 plan §5.1 记录该 consumer。
  3. 验证：`test_rules_module_does_not_import_tool_trace_internals` 或等价 AST 扫描。
- **修复风险（低）**: 仅移动字段来源，不改行为。
- **严重程度（低）**: 正确性无影响，属于 maintainability/contract boundary 问题。

---

## Rejected / Deferred

### R1: `_revalidate_source` 中的重复 stat 开销

- **位置**: `dayu/host/tool_trace_analysis_input.py:475-499`
- **描述**: `load_tool_trace_analysis_input` 在 Service 已验证 Source 后再次构造并校验 `ToolTraceAnalysisSource`，导致文件存在性 stat 重复。
- **Rejected 理由**: 这不是重复开销错误，而是必要的 TOCTOU 防护。Service discovery 和 Host load 之间有窗口，source 重新校验确保 load 时的输入 state 仍然满足 contract（例如 cold path 未被删除）。plan §7.3 明确要求"存在性变化以 load 时的第二次校验为准"。

### R2: `_deduplicate_cold_records` 在 source key conflict 时保留第一个 record 而非最新

- **位置**: `dayu/host/tool_trace_analysis_input.py:1053-1098`
- **描述**: 同 event_id 不同 digest 的 conflict 记录被丢弃（第二个及后续），只保留第一个。
- **Rejected 理由**: first-writer-wins 是 fail-closed 正确策略。当前 producer 保证同 event_id 只有一条合法 cold line。若出现 conflict，说明输入已损坏或并发异常，此时"不确定哪条对"反而优于"猜测最新那条对"。截断 diagnostic 包含被丢弃 record 的直接证据，operator 可据此判断。

### R3: `_public_payload_measure` 中的 O(N*M) 线性扫描

- **位置**: `dayu/host/tool_trace_analysis_rules.py:1692-1775`
- **描述**: 每个 resolved payload measure 对 `dataset.cold_records` 或 `dataset.hot_rows` 做线性扫描查找 owner。
- **Rejected 理由**: 实际 ranking limit=20，典型 trace 中 records 规模（数十至数百）下 O(N*M) 不可测量。plan §17.1 已将"极大 cold 文件的内存/运行时成本"作为 Issue #36 跟踪的 accepted residual risk。当前不做优化是正确的。

---

## Open Questions

无。所有阻塞性问题已由 code evidence 裁决。

---

## Residual Risk

### 未覆盖或部分覆盖区域

1. **真实 `PROVIDER_PROTOCOL_ERROR` 样本缺失**
   - 当前 workspace 没有真实的 protocol error 样本。规则 `engine.provider_protocol_error` 和 `partial_tool_call_signal` 的 Engine/vendor 路径仅由 owner-level test fixtures 覆盖（`tests/host/test_tool_trace_analysis_rules.py`）。
   - 风险：若真实 protocol error payload 形状与 fixture 不同，可能导致 unknown-field silently dropped 或 iteration_id 提取失败。
   - 缓解：规则使用白名单投影（`_provider_observed`）、显式 nullable 处理和不从 payload 猜语义；plan §17.1 明确"真实样本缺失分类为 uncovered"。Acceptable。

2. **极大 cold 文件 (>100MB) 的完整前缀读取**
   - plan §17.1 明确该风险由 Issue #36 跟踪。
   - 当前所有 smoke 使用 ~25KB cold file。Rules 模块的 run aggregation 全部驻内存。
   - 缓解：首版只针对 operator 日常诊断规模；不做 stream processor 是正确的设计选择。

3. **跨平台 cold snapshot file identity 方案**
   - `ToolTraceColdFileIdentity` 使用 `(st_dev, st_ino)` 作为平台身份。POSIX 下唯一可靠，Windows 下 `st_ino` 语义有限。
   - 当前项目只在 macOS/Linux 运行（`Platform: darwin`），且 plan 未要求 Windows 支持。

4. **JSON/Markdown 双文件非事务**
   - plan §10.3 和 §17.1 明确 accepted residual。JSON 发布成功但 Markdown 发布失败时 operator 得到 JSON+旧 Markdown 或 JSON+无 Markdown。
   - 缓解：typed `ServiceToolTraceAnalysisPublishError` 明确列出已发布路径和失败路径。Acceptable。

### Test gaps（非 finding，仅记录）

- **`_capture_cold_prefix` 中 handle.close() 失败的覆盖**: 当前测试有 `test_cold_prefix_lock_timeout`、`test_cold_prefix_read_failure` 等，但未覆盖"read 和 close 同时失败"的 masking 场景（见 Finding 1）。
- **`_vendor_partial_signal_status` 三个分支的精确覆盖**: `limited_signal`（protocol 缺失 partial）、`available`（present）、`not_applicable`（无 protocol trigger）在 `test_tool_trace_analysis_rules.py` 中有覆盖，但需要确认 fixture 不会把 `not_applicable` 和 `limited_signal` 搞混。

---

## Review Summary

本 PR 的 17 个生产文件变更实现了 Issue #70 要求的分层 Tool Trace Analyzer，覆盖了计划中的 4 个 slice。整体实现质量高：

- **Correctness**: cold snapshot 的 lock/open/fstat/read/close 协议严格保护输入完整性；hot/cold join 使用 event_id 主键 + sequence/ref/digest/identity 六项二次校验；watermark-based `input_changed_during_analysis` 正确区分并发窗口和真正的 hot/cold 不一致；read-only SQLite opener (`mode=ro` + `query_only=ON`) 正确隔离。
- **Stability**: frozen dataclass + strict `__post_init__` 校验确保数据不变量；deterministic finding ordering/id assignment 保障相同输入产生稳定输出；`os.replace` 原子替换报告文件；best-effort cleanup 不删除既有文件。
- **Layering**: CLI → Service → Host 三层依赖方向正确。CLI import boundary 测试阻止 `dayu.host`/`dayu.engine`/`dayu.fins`/`dayu.runtime` 导入；Service 不 import durable internals。
- **Semantic ownership**: input integrity → Host；behavior rules → Host/Engine/Tool per plan attribution table；report schema version 1 → Analyzer owner；lock path derivation → Tool Trace projection owner；SQLite busy timeout → `HostSQLiteStoragePolicy` owner。未发现 semantic ownership drift。
- **LLM-facing text**: Analyzer 是 operator-facing 命令行工具，不产生 LLM-facing prompt/message。Markdown report 的文本为 operator-readable 中文，不包含 raw payload/messages。Markdown escaping 正确。
- **Tests**: 4098 行新测试覆盖 parser、integrity、hot/cold join、watermark、lock/concurrency、resolver、finding rules、vendor block、Service publication（含 partial failure matrix）、CLI import boundary 和命令矩阵。所有测试通过，coverage >=80%。
- **README**: 5 个 README 更新均在对应职责范围内，符合各 README 的 Agent 更新约束。
- **Plan compliance**: 实现与 `docs/host/wu-obs-00-plan.md` 高度一致（见 Verification 节）。

发现 2 个 actionable findings：1 个中等严重度（cold snapshot 错误覆盖）和 1 个低严重度（rules 模块导入边界）。无严重或高严重度 finding。未发现 correctness、security、data loss、protocol 或 state machine 类缺陷。

两个 findings 修复后（Finding 1 必须修、Finding 2 推荐方案 A）可 merge。
