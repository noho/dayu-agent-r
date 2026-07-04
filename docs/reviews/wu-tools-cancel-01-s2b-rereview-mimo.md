# WU-TOOLS-CANCEL-01 S2B Fix Re-Review — AgentMiMo

## Scope

- Mode: current changes (workspace diff, uncommitted)
- Branch: `phase/wu-tools-cancel-01`
- Base: `main`
- Review date: 2026-07-04 21:41 CST
- Included files:
  - `dayu/tools/doc_tools.py` (S2B fix)
  - `tests/tools/test_doc_tools_provider.py` (S2B fix tests)
  - `tests/README.md` (trigger update)
- Review inputs:
  - `docs/reviews/wu-tools-cancel-01-s2b-code-review-mimo.md` (MiMo 原始 review)
  - `docs/reviews/wu-tools-cancel-01-s2b-code-review-ds.md` (DS 原始 review)
  - `docs/reviews/wu-tools-cancel-01-s2b-fix-codex.md` (Codex fix artifact)
- Parallel review coverage: 无

## Findings

未发现实质性问题。

以下是对 controller 接受/handled 的各 finding 的逐项验证结论：

### F1 hint: process failed envelope 保留原始 hint 文本 ✅ CLOSED

- **验证路径**: `_DocProcessTarget.__call__` → `_process_failed_envelope` → `_process_failure_message`
- **直接证据**:
  - `doc_tools.py:1237-1238`: `_process_failure_message` 拼接 `f"{failure.message} Hint: {failure.hint}"`
  - `test_doc_process_target_nonexistent_allowed_path_keeps_file_not_found`: 断言 `"Verify the file path and retry." in str(envelope["message"])`
  - `test_doc_process_target_argument_validation_failure_embeds_hint`: 断言 `"Add required fields and retry: file_path." in str(envelope["message"])`
- **结论**: hint 文本在 process failed envelope 的 `message` 字段中完整保留。未修改 Host process envelope 契约，符合 controller 裁决"不在此 S2B 要求 Host 契约变更"。Residual owner 已记录为后续 Host envelope contract hardening。

### F2 real Doc cancel: 真实 Doc target + FIFO 阻塞 I/O + governed cancel ✅ CLOSED

- **验证路径**: `test_doc_toolruntime_cancel_terminates_real_doc_target_blocked_on_fifo`
- **直接证据**:
  - L1216: `output = discover_tools(_spec(tmp_path))` — 使用真实 `discover_tools` 产出的定义，**未替换** execution
  - L1214-1215: `os.mkfifo(fifo_path)` 创建 POSIX FIFO，路径在 allowed root 内
  - `_is_supported_doc_file_path` 允许 `read_file` 的 FIFO 路径通过校验
  - 真实 `_DocProcessTargetFactory` / `_DocProcessTarget` 被 Host capsule spawn 到子进程
  - 子进程 `_read_file_business` → `open(fifo_path)` 阻塞在 FIFO 读取（无 writer）
  - 父进程 `token.cancel("doc process cancel")` → Host capsule terminate → kill
  - `elapsed < 2.0` 证明快速终止；`hint == "tool_runtime_cancelled"` + `reason_code == "tool_runtime_cancelled"` 证明 governed closeout
  - `len(accept_port.candidates) == 1` 证明无 late accept
- **结论**: 测试使用真实 Doc process target 而非 fake replacement，通过 FIFO 产生确定性阻塞 I/O，证明 governed cancel + no late accept。符合 F2 要求。

### F3 `_DocCancelledError` re-raise 注释 ✅ CLOSED

- **验证路径**: `_execute_doc_business_value` L1029-1032
- **直接证据**: `doc_tools.py:1029-1032` 注释 `# 该分支服务 direct callable fallback；process target 使用不可取消 token，真实取消由父进程 process capsule 独占治理。`
- **结论**: 注释准确说明该分支仅对 fallback callable 路径有效。生产语义未改变。

### F4 `timeout_seconds` 死代码删除 ✅ CLOSED

- **验证路径**: `_DocProcessTarget.__call__`
- **直接证据**: 当前 L352-393 的 `__call__` 方法中无 `timeout_seconds = self.timeout_seconds; del timeout_seconds`。`timeout_seconds` 仍为 `_DocProcessTarget` 的可序列化字段（L350），但子进程内不作为独立 timeout 真源。
- **结论**: 死代码已删除，生产语义未改变。

### DS-03 参数校验失败 envelope ✅ CLOSED

- **验证路径**: `test_doc_process_target_argument_validation_failure_embeds_hint`
- **直接证据**:
  - L1313: `_call("read_file", {})` — 缺少必填 `file_path`
  - `_execute_doc_business_value` → `validate_and_project_arguments` 返回 `ToolArgumentValidationFailure` → `raise _DocBusinessFailure(validation.error, validation.message, validation.hint)`
  - `_DocProcessTarget.__call__` 捕获 → `_process_failed_envelope` → `{"status": "failed", "error_type": "invalid_argument", "message": "... Add required fields and retry: file_path."}`
- **结论**: 参数校验失败 envelope 的 `status`、`error_type`、`message`（含 hint 文本）均被测试覆盖。

## FIFO 路径校验变更专项审查

Controller 要求额外审查：`_is_supported_doc_file_path` 允许 POSIX FIFO 作为 `read_file` 可读文件节点，是否属于可接受的生产行为变更。

### 审查结论：可接受，风险可控

**代码路径追踪**:

1. `_project_doc_paths` L1302-1305: `parameter_name != "directory" and not _is_supported_doc_file_path(tool_name, candidate)` — 调用点
2. `_is_supported_doc_file_path` L1332-1355: FIFO 检查仅对 `read_file` 生效（`if tool_name != READ_FILE_TOOL_NAME: return False`）
3. FIFO 必须已通过白名单 containment 校验（`_is_relative_to(candidate, root)`）和存在性校验（`candidate.exists()`）

**安全性分析**:

| 维度 | 评估 |
|------|------|
| 攻击面 | FIFO 必须在 allowed root 白名单内，调用者无法创建任意 FIFO |
| 工具范围 | 仅 `read_file`，`list_files` / `get_file_sections` / `search_files` / `read_file_section` 仍只接受普通文件 |
| 子进程阻塞 | FIFO 无 writer 时 `open()` 永久阻塞，但 timeout 由父进程 Host capsule 独占治理（terminate + kill） |
| 语义差异 | FIFO 非 seekable，`start_line` / `end_line` 参数可能不生效（`read_file` 的 `_read_file_business` 按行读取，FIFO 按流读取） |

**风险判断**:

- FIFO 阻塞风险已由 Host capsule timeout 兜底，不会导致子进程泄漏。
- `start_line` / `end_line` 在 FIFO 上可能不按预期工作（无法 seek），但这是边缘场景，且 LLM 不会主动对 FIFO 路径使用行范围参数。
- 变更范围精确：只扩大 `read_file` 在显式白名单内的可治理阻塞 I/O 覆盖，不改变 Host / Engine 契约，不改变其它工具行为。
- 该变更是为了支持确定性真实阻塞 I/O 测试 fixture，测试价值大于边缘语义风险。

**结论**: 生产行为变更可接受。FIFO 支持是 process-backed cancel 测试的必要条件，风险由白名单 containment 和 Host capsule timeout 双重约束。

## Residual Risk

1. **Host process failed envelope hint 结构化丢失**: 未修改。当前通过 `message` 字段保留 hint 文本。Residual owner：后续 Host process envelope contract hardening。
2. **非 POSIX 平台 FIFO 测试 skip**: `test_doc_toolruntime_cancel_terminates_real_doc_target_blocked_on_fifo` 在非 POSIX 平台 skip。当前开发平台已运行并通过。
3. **FIFO 上 `start_line` / `end_line` 语义**: `read_file` 的行范围参数在 FIFO 上可能不按预期工作，但此为极端边缘场景。

## Verdict

**PASS**

F1-F4、DS-03 均已按 controller 裁决正确处理。FIFO 路径校验变更经审查为可接受的测试支持变更，风险由白名单 containment 和 Host capsule timeout 双重约束。无阻塞 gate 的实质问题。
