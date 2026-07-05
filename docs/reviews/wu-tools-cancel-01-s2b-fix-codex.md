# WU-TOOLS-CANCEL-01 S2B Fix — AgentCodex

## Verdict

READY_FOR_RE_REVIEW

## Scope

本轮只处理 controller 接受的 S2B review findings。未修改 `dayu/host/tool_runtime.py`，未修改 Host process envelope 契约，未 commit / push / PR。

## Changed Files

- `dayu/tools/doc_tools.py`
- `tests/tools/test_doc_tools_provider.py`
- `docs/reviews/wu-tools-cancel-01-s2b-fix-codex.md`

`tests/README.md` 本轮未继续修改；既有 S2B 更新已经覆盖 Doc process-backed / cancel late-result 测试描述。

## Finding Handling

### F1 / DS-01: process-backed failed envelope hint 结构化丢失

状态：已按 controller 裁决处理。

未修改 Host process envelope 契约；当前 S2A 契约仍为 failed envelope `{status, error_type, message}`。补充测试覆盖：

- `test_doc_process_target_nonexistent_allowed_path_keeps_file_not_found`
  - 断言代表性 `file_not_found` process failed envelope 的 `message` 包含原恢复提示 `Verify the file path and retry.`
- `test_doc_process_target_argument_validation_failure_embeds_hint`
  - 断言参数校验失败 process failed envelope 的 `message` 包含原恢复提示 `Add required fields and retry: file_path.`

Residual owner / destination：后续 Host process envelope contract hardening。可由 S2E aggregate residual 或独立 follow-up 承接，目标是在 Host process failed envelope 中结构化表达可选 `hint`，并由 Host capsule 映射到 `ToolFailedOutcome.result.hint`。

### F2 / DS-02: cancel late-result 测试只覆盖 fake slow target

状态：已修复。

新增 `test_doc_toolruntime_cancel_terminates_real_doc_target_blocked_on_fifo`：

- 使用真实 `discover_tools(...)` 产出的 Doc `ToolDefinition.execution`，不替换为 fake factory。
- POSIX 平台下在 allowed root 内创建 FIFO `blocked.md`，通过真实 `_DocProcessTargetFactory` / `_DocProcessTarget` 执行 `read_file`。
- 子进程真实阻塞在 `read_file` 的文件打开 / 读取边界，父进程取消后 ToolRuntime 快速返回 governed cancel。
- 断言 `elapsed < 2.0`、`ToolFailedOutcome.result.hint == "tool_runtime_cancelled"`、accept barrier 只有一次 governed candidate 且 reason code 为 `tool_runtime_cancelled`。
- 非 POSIX 平台按 stop condition 使用 `pytest.skip`，不以 fake target 伪造真实 Doc target 证据。

为支持该确定性真实阻塞 I/O fixture，`read_file` 的 path validation 在保持 allowed root containment 和目录拒绝语义的前提下，额外允许 POSIX FIFO 作为 `read_file` 可读文件节点；其它 Doc tools 仍只接受普通文件。该变更只扩大 `read_file` 在显式白名单内的可治理阻塞 I/O 覆盖，不改变 Host / Engine 契约。

### F3: `_DocCancelledError` re-raise 在 process target 路径不可达

状态：已处理。

在 `_execute_doc_business_value(...)` 的 `_DocCancelledError` 分支补充注释，明确该分支服务 direct callable fallback；process target 使用不可取消 token，真实取消由父进程 process capsule 独占治理。

### F4: `_DocProcessTarget.__call__` 中 timeout_seconds 赋值后删除

状态：已修复。

删除无意义的 `timeout_seconds = self.timeout_seconds; del timeout_seconds` 死代码。`timeout_seconds` 仍保留为 target 的可序列化字段，用于承载 Host 投影上下文，但子进程内不把它作为独立 timeout 真源。

### DS-03: process target 参数校验失败路径缺少测试

状态：已修复。

新增 `test_doc_process_target_argument_validation_failure_embeds_hint`，覆盖缺失 `file_path` 时 process target 返回 `status=failed`、`error_type=invalid_argument`，且 `message` 保留原参数修复提示。

### DS-04: process target generic exception 捕获路径缺少测试

状态：未处理，按 controller 裁决不强制。

该路径需要 monkeypatch 内部 helper 人为制造未预期异常，收益低于当前 fix gate 必要性；本轮不扩大测试面。

## Validation

- `source .venv/bin/activate && pytest tests/tools/test_doc_tools_provider.py -q`
  - `46 passed in 2.43s`
- `source .venv/bin/activate && pytest tests/host/test_toolruntime_executor.py -q`
  - `55 passed in 6.30s`
- `source .venv/bin/activate && pyright`
  - `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - passed

## Residual Risk

- Host process failed envelope 仍无结构化 `hint` 字段；当前 Doc process-backed 路径通过 `message` 保留 hint 文本。Residual owner / destination：后续 Host process envelope contract hardening，由 S2E aggregate residual 或独立 follow-up 承接。
- 非 POSIX 平台无法运行 FIFO 真实阻塞 I/O 测试，测试会 skip；当前开发平台已运行并通过。
