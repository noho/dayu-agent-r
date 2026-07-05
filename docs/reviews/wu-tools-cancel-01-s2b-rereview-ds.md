# WU-TOOLS-CANCEL-01 S2B Re-review — AgentDS

## Verdict

**PASS**

所有 controller 接受的 findings 均已正确修复且通过验证。POSIX FIFO 路径变更存在 test-induced broadening 风险，但 blast radius 小且受治理，不阻塞 gate。

## Scope

- **Mode**: S2B fix re-review only（不修改代码、不 stage、不 commit、不 push）
- **Branch**: `phase/wu-tools-cancel-01`
- **Base**: `main`
- **Review inputs**:
  - `docs/reviews/wu-tools-cancel-01-s2b-code-review-mimo.md`（AgentMiMo S2B review）
  - `docs/reviews/wu-tools-cancel-01-s2b-code-review-ds.md`（AgentDS S2B review）
  - `docs/reviews/wu-tools-cancel-01-s2b-fix-codex.md`（Codex fix report）
  - workspace diff: `dayu/tools/doc_tools.py`, `tests/tools/test_doc_tools_provider.py`, `tests/README.md`
- **Excluded scope**: 已提交的 S2A1/S2A2 commits、`dayu/host/tool_runtime.py`、其他未修改文件
- **Parallel review coverage**: 无

## Controller Accepted Findings — Verification

### F1 / DS-01: process-backed failed envelope hint 结构化丢失

**Controller 裁决**: 不修改 Host process envelope 契约；验证 message 保留原 hint 文本；记录 residual owner/destination。

**验证结果**: ✅ 通过

**证据**:
- `_process_failed_envelope()`（`doc_tools.py:912-916`）调用 `_process_failure_message(failure)` 将 hint 嵌入 message
- `_process_failure_message()`（`doc_tools.py:919-938`）在 `failure.hint` 非 None 且非空白时拼接 `"{message} Hint: {hint}"` 格式
- fallback path `_invoke_doc_business()`（`doc_tools.py:911-918`）仍通过 `failed_outcome(hint=error.hint)` 保留结构化 hint；双路径语义明确：process-backed 用 message-embedded workaround，fallback 用结构化 hint
- 测试 `test_doc_process_target_nonexistent_allowed_path_keeps_file_not_found`（`test_doc_tools_provider.py:1285-1300`）断言 `"Verify the file path and retry." in str(envelope["message"])`
- 测试 `test_doc_process_target_argument_validation_failure_embeds_hint`（`test_doc_tools_provider.py:1303-1318`）断言 `"Add required fields and retry: file_path." in str(envelope["message"])`
- Fix artifact（`wu-tools-cancel-01-s2b-fix-codex.md:L30`）明确记录 residual owner：后续 Host process envelope contract hardening

**已关闭**: F1 不再需要在 S2B 中处理。

---

### F2 / DS-02: cancel late-result 测试只覆盖 fake slow target

**Controller 裁决**: 新增真实 Doc `_DocProcessTargetFactory`/`_DocProcessTarget` 通过 ToolRuntime 的 cancel 测试。

**验证结果**: ✅ 通过

**证据**:
- 测试 `test_doc_toolruntime_cancel_terminates_real_doc_target_blocked_on_fifo`（`test_doc_tools_provider.py:1522-1572`）:
  1. 使用 `discover_tools(_spec(tmp_path))` 产出真实 `ToolDefinition`，**不替换** `definition.execution`
  2. 通过 `DefaultToolRuntimeFactory` 构造生产级 ToolRuntime
  3. POSIX 下创建 FIFO `blocked.md`（在 allowed root 内）
  4. 通过真实 `ToolRuntimeHandle.tool_executor.execute()` 执行 `read_file`
  5. 子进程真实阻塞在 FIFO 文件打开/读取边界
  6. 父进程取消后异步 task 快速返回 governed cancel
  7. 断言 `elapsed < 2.0`、`hint == "tool_runtime_cancelled"`、仅 1 个 accept candidate、`reason_code == "tool_runtime_cancelled"`
  8. 非 POSIX 平台 `pytest.skip`（不算假证据）
- 同时保留了 fake `_SlowProcessTargetFactory` 测试 `test_doc_toolruntime_cancel_returns_governed_failure_without_late_accept`（`test_doc_tools_provider.py:1461-1519`）作为 framework-level 快速回归测试
- 两个测试互补：fake 测试保证 cancel governance 契约不退化；FIFO 测试证明真实 Doc subprocess 阻塞在文件 I/O 时 cancel 仍有效

**已关闭**: F2 不再需要在 S2B 中处理。

---

### F3: `_DocCancelledError` re-raise 在 process target 路径不可达

**Controller 裁决**: 添加注释说明。

**验证结果**: ✅ 通过

**证据**:
- `_execute_doc_business_value()` L1029-1032:
  ```python
  except _DocCancelledError:
      # 该分支服务 direct callable fallback；process target 使用不可取消 token，
      # 真实取消由父进程 process capsule 独占治理。
      raise
  ```
- 注释准确描述双路径语义：fallback callable 使用真实 `CancellationToken`（可触发 `_DocCancelledError`），process target 使用 `_DocProcessCancellationToken`（永不触发）
- 代码路径验证：`_DocProcessTarget.__call__`（L380）传入 `_DocProcessCancellationToken()`；`_DocProcessCancellationToken.is_cancelled()`（L288）始终返回 `False`

**已关闭**: F3 不再需要在 S2B 中处理。

---

### F4: `_DocProcessTarget.__call__` 中 timeout_seconds 赋值后删除

**Controller 裁决**: 删除死代码。

**验证结果**: ✅ 通过

**证据**:
- `_DocProcessTarget.__call__()`（`doc_tools.py:352-393`）中不再有 `timeout_seconds = self.timeout_seconds; del timeout_seconds`
- `timeout_seconds` 字段仍保留在 dataclass（L350: `timeout_seconds: float | None`），docstring（L336-337）明确标注"仅作为可序列化上下文留痕，真实 timeout 仍由父进程 Host capsule 独占治理"
- `_DocProcessTargetFactory.build_process_target()`（L243-249）仍将 `context.timeout_seconds` 传入 target，确保 Host 投影上下文正确传递（即使子进程内不使用它作为 timeout 真源）

**已关闭**: F4 不再需要在 S2B 中处理。

---

### DS-03: process target 参数校验失败路径缺少测试

**Controller 裁决**: 补充测试。

**验证结果**: ✅ 通过

**证据**:
- `test_doc_process_target_argument_validation_failure_embeds_hint`（`test_doc_tools_provider.py:1303-1318`）:
  1. 使用 `discover_tools` 产出的真实 `_DocProcessTargetFactory` / `_DocProcessTarget`
  2. 传入空 arguments `{}`（缺少 `file_path`）
  3. `_run_definition_process_target()` 调用真实 `target()`
  4. 验证 envelope `status == "failed"`、`error_type == "invalid_argument"`
  5. 验证 message 包含原参数修复提示 `"Add required fields and retry: file_path."`
- 代码路径覆盖：`_DocProcessTarget.__call__()`（L373-393）→ `_execute_doc_business_value()`（L1007-1009）→ `validate_and_project_arguments()` → `ToolArgumentValidationFailure` → `raise _DocBusinessFailure(...)` → `_DocProcessTarget.__call__()` catches `_DocBusinessFailure`（L382-383）→ `_process_failed_envelope(failure)`（L912-916）

**已关闭**: DS-03 不再需要在 S2B 中处理。

---

## New Finding: FIFO 路径验证变更

### R1-INFO-LOW-POSIX FIFO 许可为 test-induced broadening

- **入口/函数**: `_is_supported_doc_file_path`
- **文件(行号)**: `dayu/tools/doc_tools.py:1332-1355`
- **输入场景**: 对 `read_file` 工具传入 POSIX FIFO 路径（在 allowed root 内且路径存在）
- **实际分支**: `candidate.is_file()` 对 FIFO 返回 `False` → `tool_name == READ_FILE_TOOL_NAME` 为 `True` → `stat.S_ISFIFO(candidate.stat().st_mode)` 返回 `True` → 函数返回 `True` → 路径被接受，进入 `_read_file_business()` → `open(fifo_path)` 阻塞等待 writer
- **预期行为**: 按 Doc 工具语义（读取文档文件），FIFO（IPC 原语）不应被视为合法读目标
- **实际行为**: `read_file` 接受 FIFO 并阻塞，依赖父进程 Host capsule 的 cancel/timeout 治理终止子进程

**这是什么变更**:

`_is_supported_doc_file_path` 将 `read_file` 的文件类型检查从 `Path.is_file()`（仅普通文件）扩宽为"普通文件 OR POSIX FIFO"。变更的**唯一生产动机**是让 cancel 测试能够用真实 Doc process target + 确定性阻塞 I/O fixture（FIFO）替代 fake `_SlowProcessTargetFactory`。

**代码路径分析**:

1. 路径 `_project_doc_paths`（L1302）原本调用 `candidate.is_file()`，现改为 `_is_supported_doc_file_path(tool_name, candidate)`
2. 该检查发生在 containment（L1279-1289）和 existence（L1290-1295）之后
3. 只有 `read_file` 受益于 FIFO 扩宽；`_is_supported_doc_file_path` L1350-1351 对其他工具立即返回 `False`
4. FIFO 阻塞后的治理链：子进程 `open()` 阻塞 → 父进程 `wait_for_or_cancel()` 检测取消 → `terminate()` / `kill()` 子进程 → governed cancel outcome

**风险评估**:

| 维度 | 评估 |
|---|---|
| 安全边界 | containment check（L1279-1289）是主要安全边界，**未变更**。FIFO 仍需在 allowed root 内 |
| 攻击面 | 若攻击者能在 allowed root 内创建 FIFO，已有写权限；此时可做的破坏远超创建 FIFO（替换文档、创建恶意 symlink 等）。实际攻击面增加**可忽略** |
| 生产影响 | 生产环境文档目录不存在 FIFO。LLM 不会自主指定 FIFO 路径。变更对正常生产流程**零影响** |
| 行为退化 | 旧行为：`read_file` 对 FIFO 返回 `"Path argument 'file_path' must point to a file: ..."`。新行为：阻塞后被父进程 cancel。两者均为可恢复失败（一个立即返回 error，一个 timeout 后返回 cancelled），对 LLM 而言都是"操作未成功，需重试"。**非实质性退化** |
| 可逆性 | 若后续需要收紧，只需在 `_is_supported_doc_file_path` 中删除 `stat.S_ISFIFO` 分支，恢复 `candidate.is_file()` 检查。**零成本回退** |
| 语义纯度 | FIFO 是 IPC 原语而非文档，从 Doc tool 语义角度看不够纯净。这是主要批评点 |

**判断**: 这是一个**可接受的低风险 test-induced broadening**。原因：

1. 安全边界（containment）未变，FIFO 扩宽仅影响 `read_file`
2. 没有已知生产场景会在 allowed roots 内创建 FIFO
3. 即使 FIFO 被读，阻塞行为由 Host cancel/timeout 治理，不是无限挂起
4. 变更使 cancel 测试能覆盖真实 Doc subprocess I/O 阻塞路径，显著提升测试质量（从 framework-only fake target → 真实 subprocess + 真实 I/O 阻塞）
5. 未来可零成本回退

**不建议本轮修改**。若后续有独立 concern，可在 `_is_supported_doc_file_path` docstring 中标注"FIFO 接受为测试阻塞 I/O fixture 服务，非生产文档语义"。

- **严重程度（低）**:

---

## F3/F4 Cleanup 语义影响确认

以下是对 controller 要求"验证 comments/dead-code cleanup 未 alter production semantics"的逐项确认：

| 变更 | 旧行为 | 新行为 | 语义变更 |
|---|---|---|---|
| F3 comment（L1029-1032） | 无注释，`except _DocCancelledError: raise` | 添加注释说明该分支服务 fallback callable | 无。纯文档补充 |
| F4 dead-code removal | `timeout_seconds = self.timeout_seconds; del timeout_seconds` | 两行删除 | 无。原代码赋值后立即删除，从未使用 |
| `_argument_failed_outcome` / `_path_failed_outcome` 删除 | 在 callable 内调用，将 validation/path 失败投影为 outcome | 已删除；逻辑移入 `_execute_doc_business_value`，通过 `_DocBusinessFailure` 抛出 | 无。语义完全等价：callable → `_invoke_doc_business` → `business_call`（内含 `_execute_doc_business_value`）→ `_DocBusinessFailure` → `_invoke_doc_business` catches → `failed_outcome()`；process target → `_DocProcessTarget.__call__` → `_execute_doc_business_value` → `_DocBusinessFailure` → `_process_failed_envelope()` |
| `_invoke_doc_business` `raw_value` 不再调 `_project_tool_response_paths` | `_project_tool_response_paths(tool_name, raw_value)` 在 `_invoke_doc_business` return 前 | 直接 return `raw_value`；路径投影已由 `_execute_doc_business_value`（L1063）在 `business_call` 内完成 | 无。投影仅执行一次，从 outer 移到 inner，结果等价 |
| `_build_*_definition` 参数从单个 limit 值改为 `limits: DocToolLimits` | `_build_list_files_definition(max_files, ...)` | `_build_list_files_definition(limits, ...)` | 无。各函数内部通过 `limits.list_files_max` 等提取所需值，值本身不变 |

**确认**: F3/F4 及关联 cleanup 的语义变更均为**零**。

---

## Open Questions

1. **FIFO 回退策略**: 若未来 code review 或安全审计要求收紧 read_file 文件类型检查，回退方式为删除 `_is_supported_doc_file_path` 中 `stat.S_ISFIFO` 分支并恢复 `candidate.is_file()`，同时需要将 FIFO cancel 测试改为使用大文件+慢 encoding 或 monkeypatch 实现。建议当前不阻塞 gate，但可记录为 follow-up 改进项。

## Residual Risk

1. **Host process failed envelope 结构化 hint**: 与 MiMo review 和 Codex fix report 一致。当前 Doc process-backed 路径通过 `"Hint: ..."` suffix 保留 hint 文本，但 `ToolFailedOutcome.result.hint` 在 Host `_failed_outcome_from_process_envelope` 中固定为 `None`。后续需 Host process envelope contract work unit 跟进。

2. **非 POSIX 平台 FIFO 测试**: 新测试 `test_doc_toolruntime_cancel_terminates_real_doc_target_blocked_on_fifo` 在非 POSIX 平台 `pytest.skip`。当前 CI（macOS/Linux）覆盖 POSIX，Windows 上真实 Doc target cancel 测试空缺。已有 `test_doc_toolruntime_cancel_returns_governed_failure_without_late_accept`（fake target）作为跨平台框架级覆盖。

3. **Docling processor SIGTERM 响应**: 与 DS original review 一致。真实 Doc target cancel 测试（FIFO）覆盖了文件 I/O 阻塞的 cancel 场景，但不覆盖 `create_doc_file_processor()` 在 SIGTERM 下的行为。这是 process-backed 架构的固有风险，非本轮引入。

4. **测试未覆盖的工具**: `list_files`、`search_files`、`read_file_section` 的 process target 成功路径仍无直接测试（只有 `read_file` fast path 和 `get_file_sections` processor path 有）。代码路径共享 `_execute_doc_business_value()` → `_route_doc_business()`，风险低但非零。

5. **FIFO production behavior change**: 见 Finding R1。风险低，但建议在 `_is_supported_doc_file_path` 或相关 code review 记录中标注 FIFO 接受的测试动机。

## Validation

- `pytest tests/tools/test_doc_tools_provider.py -q`: **46 passed in 2.38s**（含 FIFO cancel 测试）
- `pytest tests/tools/test_doc_tools_provider.py -q -k "fifo" -v`: **1 passed**（macOS POSIX）
- Fix artifact（Codex）报告: `pyright 0 errors, 0 warnings, 0 informations`
- Fix artifact（Codex）报告: `pytest tests/host/test_toolruntime_executor.py -q: 55 passed`
