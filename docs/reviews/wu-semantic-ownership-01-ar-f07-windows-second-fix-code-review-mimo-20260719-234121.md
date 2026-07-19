# Code Review

## Scope

- Mode: current changes
- Branch: `phaseflow/host-issues-control`
- Base: `ac5e755ba7148a5d2f30f3f11222548b3c57cd9e`
- Output file: `docs/reviews/wu-semantic-ownership-01-ar-f07-windows-second-fix-code-review-mimo-20260719-234121.md`
- Included scope:
  1. `.github/workflows/r11-upload-script-windows.yml`
  2. `.github/workflows/r12-init-windows.yml`
  3. `dayu/cli/main.py`
  4. `dayu/cli/upload_script.py`
  5. `tests/README.md`
  6. `tests/cli/test_arg_parsing.py`
  7. `tests/cli/test_upload_filings_from_command.py`
  8. `docs/host/issues-implementation-control.md`
  9. `docs/reviews/wu-semantic-ownership-01-ar-f07-windows-second-fix-codex.md`（AgentCodex artifact）
  10. `docs/reviews/wu-semantic-ownership-01-ar-f07-windows-second-fix-controller-validation.md`（Controller validation）
- Excluded scope: 无
- Parallel review coverage: 无

## 已完整核对的真源

- `AGENTS.md`（语义所有权、编码硬约束、测试与验证）
- `docs/host/issues-implementation-control.md`（AR-F07 当前 gate 与 evidence 状态）
- `docs/reviews/wu-semantic-ownership-01-ar-f07-windows-second-fix-codex.md`（AgentCodex 第二轮 fix artifact）
- `docs/reviews/wu-semantic-ownership-01-ar-f07-windows-second-fix-controller-validation.md`（Controller validation）
- 第二轮真实 Windows evidence 的 JUnit/environment 文档（artifact 中记录）
- 10 个 target paths 的完整工作区当前状态与 `git diff` 输出

## Findings

未发现实质性问题。

以下是对 Controller 要求挑战的五项边界的逐项 adversarial 分析，每项给出直接证据或"无 defect"结论：

### 挑战 1：真实 cmd batch phase ordering 下 caret/percent/CRT 是否成立

**分析路径**：`_quote_windows_batch_argument` → batch 文件写入 → cmd.exe percent expansion → cmd.exe caret 解析 → CRT `CommandLineToArgvW` → 目标进程 argv。

- **Percent doubling**：renderer 把 `%` 替换为 `%%`（`upload_script.py:228-229`）。cmd.exe 的 percent expansion 阶段把 `%%` 还原为 `%`。这是 batch percent 的标准行为，不依赖 CRT 解析。
- **Caret-protected quote**：renderer 输出 `^"` 作为 quote 字符（`upload_script.py:215,223,235`）。cmd.exe 的 caret 解析阶段把 `^"` 视为 "literal `"`，不切换 quote state"。cmd 因此不持有 renderer 的 quote state，不会把后续 `&` 当命令分隔符。cmd 去掉 `^` 后把裸 `"` 传给 CRT，CRT 按标准 quote 规则解析。
- **Body metacharacter caret**：renderer 对 `^&|<>()` 加 caret（`upload_script.py:229-230`）。cmd 的 caret 阶段把这些 `^X` 还原为 literal `X`。这些字符在 batch body 中是 cmd metacharacter，但被 caret 保护后不会被 cmd 解释。
- **CRT backslash-quote**：renderer 实现标准 CRT `\"` 规则（`upload_script.py:222-223`）。连续 `\` 后遇 `"` 时，`\` 数量翻倍再加一个 `\` 前缀 `"`，这正是 CRT 的 "2N 个 `\` → N 个 literal `\` + quote 为 literal；2N+1 个 `\` → N 个 literal `\` + quote 为 delimiter toggle" 规则。
- **两层解码分离**：test oracle `_decode_windows_batch_fixed_token`（`test_upload_filings_from_command.py:952-978`）先做 batch percent/caret 解码，再由 `_parse_single_windows_crt_argument` 做 CRT 解码。两层解码器独立实现、不复用 production helper，避免自证。
- **真实 cmd.exe 证据**：`test_windows_cmd_script_round_trips_adversarial_argv_with_real_cmd`（`test_upload_filings_from_command.py:767-824`）在真实 `cmd.exe /d /c` 下运行，覆盖 empty、space、中文、literal quote、trailing backslash、literal percent、`!`、`&`、`|`、`^`、`(`、`)`、`<`、`>` 共 13 种 fixed argv，并断言 `rows == [[*fixed, *appended]]`。该测试是 Windows-only（`skipif os.name != "nt"`），本地无法运行但作为真实 Windows gate 存在。

**结论**：设计变换在 batch percent → cmd caret → CRT quote 三层语义上自洽。真实 cmd.exe round-trip 测试存在且覆盖全 metacharacter。本地 oracle 只证明设计变换，不声明 Windows pass；真实 pass 由 R11/R12 rerun 关闭。无 defect。

### 挑战 2：literal quote 后元字符

**分析路径**：argument = `quote"value` → renderer → batch file → cmd.exe → CRT。

- renderer 对 `"` 的处理：先输出 `\\` * (backslash_count * 2 + 1) 再输出 `^"`（`upload_script.py:222-223`）。当 backslash_count=0 时，输出 `\^"`。
- 对 `quote"value`：renderer 输出 `^"quote\^"value^"`。
- cmd caret 阶段：`^"` → literal `"`，`\` → literal `\`，`^"` → literal `"`，其余字符不变。cmd 传给 CRT：`"quote\"value"`。
- CRT 解析：开头 `"` 进入 quoted state，`quote` → literal，`\"` → literal `"`（backslash-quote escape），`value` → literal，结尾 `"` → exit quoted state。结果：`quote"value`。正确。
- 真实 cmd 测试覆盖了 `quote"value` 作为 fixed argv，并断言 round-trip 成功（`test_upload_filings_from_command.py:791`）。

**结论**：literal quote 后的元字符由 caret 保护正确处理。无 defect。

### 挑战 3：raw percent-star appended argv 边界与 injection

**分析路径**：`{fixed} %*`（`upload_script.py:200`）+ caller-provided appended argv。

- `%*` 是 raw batch 变量展开，代表 "所有 appended 参数"。这是 batch 设计的核心 passthrough 机制，不是安全漏洞。
- 真实 cmd 测试用 `appended = ("appended value", f"& type nul > {marker}")` 验证（`test_upload_filings_from_command.py:813`）。断言：`rows == [[*fixed, *appended]]` 且 `not marker.exists()`。
- injection marker `& type nul > marker` 被传入 `cmd.exe /d /c script.cmd appended value "& type nul > marker"`。cmd.exe 把整个 `%*` 展开为 `appended value "& type nul > marker"` 传给 Python 脚本。`&` 在 appended argv 中不被解释为命令分隔符，因为 cmd 已经完成了 percent expansion 和命令分割。marker 文件不存在证明没有注入。
- `DisableDelayedExpansion`（`upload_script.py:22`）确保 `!` 不被二次展开。test 覆盖了 `!` 作为 fixed argv（`test_upload_filings_from_command.py:793`）。

**结论**：raw `%*` 是 intentional passthrough 设计，injection marker 测试直接证明 appended argv 中的 `&` 不被解释为命令分隔符。无 defect。

### 挑战 4：CLI TextIOWrapper owner / 嵌入与错误行为

**分析路径**：`main()` → `_configure_cli_standard_stream(sys.stdout)` → `stream.reconfigure(encoding="utf-8", errors="strict")`。

- **Owner 唯一性**：`_configure_cli_standard_stream` 在 `main()` 最前面调用（`main.py:84-85`），先于参数解析、usage/help 和命令输出。console script `dayu-cli = dayu.cli.main:main` 与 `python -m dayu.cli -> run_module() -> main()` 共用同一 owner。
- **isinstance 守卫**：只对 `io.TextIOWrapper` 实例调用 `reconfigure`（`main.py:152`）。`StringIO`、`BytesIO`、pytest capture 等非 wrapper 保持原样。test `test_cli_standard_stream_owner_preserves_non_wrapper_capture`（`test_arg_parsing.py:538-550`）直接证明。
- **cp1252 → UTF-8 round-trip**：test `test_cli_standard_stream_owner_reconfigures_real_wrapper_to_strict_utf8`（`test_arg_parsing.py:513-535`）从 `cp1252/strict` 的真实 `TextIOWrapper(BytesIO)` 出发，写入 `"初始化完成：中文输出"` 后断言底层 bytes 是严格 UTF-8。直接证明 Windows redirected stream 的 charmap 编码问题被修复。
- **错误传播**：`reconfigure` 的 `OSError`/`ValueError` 透传到 `main()` 的外层 except（`main.py:137-140`）。`main()` 的 docstring 明确记录了这两种异常（`main.py:80-81`）。没有 catch、没有 fallback、没有 `hasattr/getattr`。
- **时序安全**：reconfigure 在任何 CLI 输出之前调用。Windows runner 的 redirected stdout 在进程创建时就是 `TextIOWrapper`，reconfigure 把它从 locale charmap 切换到 UTF-8。

**结论**：CLI stream owner 是唯一进程边界、唯一 reconfigure 入口；非 wrapper capture 保持原样；错误透传。无 defect。

### 挑战 5：PowerShell ProcessStartInfo 双流 / exit code / 输出 / 资源

**分析路径**：`Invoke-CmdEvidence` → `ProcessStartInfo` → `Process.Start()` → async stdout/stderr drain → `WaitForExit()` → `Dispose()`。

- **ArgumentList 逐个 Add**：`foreach ($argument in $ArgumentList) { [void]$startInfo.ArgumentList.Add($argument) }`（workflow:69-71）。.NET `ArgumentList.Add` 自动转义每个参数，不拼接 shell 字符串，不存在注入面。
- **UseShellExecute=false + 双流 redirect**：`$startInfo.UseShellExecute = $false`、`$startInfo.RedirectStandardOutput = $true`、`$startInfo.RedirectStandardError = $true`（workflow:66-68）。直接创建 cmd.exe 进程，不经过 pwsh shell。
- **Async drain 防 deadlock**：`$stdoutTask = $process.StandardOutput.ReadToEndAsync()` 和 `$stderrTask = $process.StandardError.ReadToEndAsync()` 在 `WaitForExit()` 之前启动（workflow:76-77）。两个流的缓冲区被独立 drain，不会因一个流满而阻塞另一个流。
- **精确 exit code**：`return $process.ExitCode`（workflow:86）。`$verExitCode -ne 0` 断言 ver 精确 0（workflow:102-104），`$cmdHelpExitCode -ne 1` 断言 help 精确 1（workflow:109-111）。不使用 `$LASTEXITCODE`、不全局忽略 native failure。
- **资源释放**：`finally { $process.Dispose() }`（workflow:88-90）。无论 Start/Read/Wait 是否异常，Process 对象都被释放。
- **UTF-8 无 BOM 写入**：`[System.Text.UTF8Encoding]::new($false)`（workflow:83-85）。明确无 BOM，与 Python UTF-8 读取兼容。
- **不弱化后续 gate**：capability step 之后的 pytest step 不设 `continue-on-error`、不修改 `$ErrorActionPreference`、不设 `$PSNativeCommandUseErrorActionPreference`。help exit 被精确分类后才继续。

**结论**：ProcessStartInfo 精确控制进程创建、双流异步 drain 防 deadlock、精确 exit code 判定、finally Dispose 释放资源。无 defect。

## Open Questions

无。

## Residual Risk

1. **Windows-only 真实 cmd 测试无法本地运行**：`test_windows_cmd_script_round_trips_adversarial_argv_with_real_cmd` 和 `test_windows_generated_script_runs_real_cli_into_temp_storage` 标记 `skipif os.name != "nt"`。本地 oracle 只证明设计变换，不声明 Windows pass。三项 WIN2-F01/F02/F03 的最终 closure 必须由修改后 R11/R12 的真实 `windows-latest` rerun 证明。
2. **Workflow 纯字符串断言**：`test_r11_workflow_uses_fail_closed_exact_cmd_process_probe` 用字符串存在性检查 workflow YAML，不做 PowerShell AST 解析。断言覆盖了关键 ProcessStartInfo 属性、ArgumentList 调用和 exit code 条件；但对于复杂的 PowerShell 逻辑（如 async drain 时序），字符串断言无法证明行为正确性。这由 R11 真实 runner 验证闭环。
3. **`cmd.exe /?` exit code 稳定性**：workflow 断言 help exit exact 1。如果未来 Windows 版本改变 cmd.exe help 的 exit code，workflow 会 fail-closed。这是 intentional 设计，不是 defect。
