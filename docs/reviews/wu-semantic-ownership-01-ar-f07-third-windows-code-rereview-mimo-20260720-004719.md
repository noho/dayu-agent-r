# WU-SEMANTIC-OWNERSHIP-01 / AR-F07 WIN3-F01 dual complete code re-review

## Scope

- Mode: current changes (dual complete code re-review)
- Branch: `phaseflow/host-issues-control`
- Base: `main`（默认）
- HEAD commit: `4814b7dc93052f5742ab8b7f33a8dff9377c5ff6`（`fix: accept AR-F07 Windows second remediation`）
- Output file: `docs/reviews/wu-semantic-ownership-01-ar-f07-third-windows-code-rereview-mimo-20260720-004719.md`
- WU: `WU-SEMANTIC-OWNERSHIP-01` / `AR-F07` / `WIN3-F01`（第三轮 Windows evidence → fix → controller validation → code review → zero-change disposition → 本 dual complete re-review）
- Review target（13-path tree）：
  - **四个 implementation paths**：
    1. `tests/README.md`（tests README，direct-consumer strict UTF-8 契约记录）
    2. `tests/cli/test_arg_parsing.py`（新增 owner-contract 测试与 CLI stream owner 测试）
    3. `tests/cli/test_init_smoke.py`（新增完整 POSIX/Windows init smoke，strict UTF-8）
    4. `tests/cli/test_upload_filings_from_command.py`（新增 POSIX/Windows 真实脚本 smoke，strict UTF-8）
  - **control doc**：
    5. `docs/host/issues-implementation-control.md`（unstaged diff，AR-F07/WIN3-F01 当前行与 gate 状态）
  - **第三轮 Windows artifacts**：
    6. `docs/reviews/wu-semantic-ownership-01-ar-f07-third-windows-evidence-controller-adjudication.md`（Controller evidence adjudication）
    7. `docs/reviews/wu-semantic-ownership-01-ar-f07-third-windows-fix-codex.md`（AgentCodex WIN3-F01 fix artifact）
    8. `docs/reviews/wu-semantic-ownership-01-ar-f07-third-windows-fix-controller-validation.md`（Controller validation artifact）
  - **code review artifacts**：
    9. `docs/reviews/code-review-20260720-002828.md`（AgentMiMo code review）
    10. `docs/reviews/code-review-20260720-003027.md`（AgentDS code review）
    11. `docs/reviews/wu-semantic-ownership-01-ar-f07-third-windows-code-review-controller-adjudication.md`（Controller code review adjudication）
  - **zero-change disposition artifacts**：
    12. `docs/reviews/wu-semantic-ownership-01-ar-f07-third-windows-code-review-fix-codex.md`（AgentCodex zero-change disposition）
    13. `docs/reviews/wu-semantic-ownership-01-ar-f07-third-windows-code-review-fix-controller-validation.md`（Controller zero-change validation）
- Included scope：上述 13-path tree 的完整内容、四个 implementation path 的 git diff、全量 subprocess consumer audit、全量 `text=True` 无 `encoding=` 扫描、`dayu/` 生产代码 subprocess 编码扫描、AGENTS.md / CLAUDE.md 项目指令对齐、R11/R12 第三轮 failure evidence 回溯、Controller 对 reviewer 分歧的裁决复核。
- Excluded scope：`dayu/cli/main.py` 生产代码（已在第一/二轮 Windows fix 中完成 `_configure_cli_standard_stream`）、`dayu/cli/` 其它 production diff、workflow yml、根 README、分层 README（均不在 WIN3-F01 fix scope 内）。
- Parallel review coverage：无（本次为单一 reviewer 全量覆盖，未使用 subagent）。

## Pre-review verification

所有 Python 命令均在 `source .venv/bin/activate` 后执行。

| Gate | Result |
|---|---|
| 三个 affected test files | `98 passed, 7 skipped, 3 warnings in 28.10s`；7 skip 均为显式 Windows-only / POSIX-only |
| full pyright `dayu/ tests/ utils/` | `0 errors, 0 warnings, 0 informations` |
| `git diff --check` | PASS（通过 diff 格式检查） |
| staged tree | empty |
| owner contract tests（`test_python_module_help_decodes_cli_output_as_strict_utf8` + `test_cli_standard_stream_owner_*` × 2） | `3 passed` |
| 全量 `text=True` 无 `encoding=` 扫描（`tests/`） | 命中 18 处，全部为非 Dayu CLI consumer（prewarm、mklink、reg.exe、/bin/sh recorder、ps、pip wheel、lane controller、log levels） |
| 全量 `text=True` 无 `encoding=` 扫描（`dayu/` 生产代码） | 命中 0 处 subprocess 调用（`contains_full_text=True` 为 processor 关键字参数，非 subprocess） |
| 全量 `encoding="utf-8"` 无 `errors="strict"` 扫描（`tests/cli/`） | 命中 0 处 |
| `cp1252` / `charmap` / `ignore` / `replace` errors 扫描（`tests/cli/`） | 命中 1 处（`test_arg_parsing.py:523`，为测试 `_configure_cli_standard_stream` 的 cp1252→UTF-8 重配置，非 consumer 问题） |
| `PYTHONIOENCODING` / `PYTHONUTF8` 环境 shim 扫描（全仓库） | 命中 0 处 |
| `shell=True` 扫描（changed test files） | 命中 0 处 |
| AGENTS.md vs CLAUDE.md diff | 无差异（内容完全一致） |
| 四个 implementation paths SHA-256 | 与 implementation artifact / Controller validation 完全一致 |
| 四个 implementation paths binary diff SHA-256 | `9477cef2dfbba98050193f5801dc77c3a469591cfc50463dc4dffdb84341b469`，与 implementation artifact / Controller validation 完全一致 |
| 生产代码/workflow/README/deferred paths diff | 零 diff（仅 control doc 有 unstaged diff） |

warnings 仅为既有 `edgar` deprecation warnings，与本次变更无关。

## 13-path tree 完整性验证

### 四个 implementation paths SHA-256

| Path | SHA-256 |
|---|---|
| `tests/README.md` | `504b7c1ff84ed15e1f64a50decbad60841336d46a99662aadaabc45b1566af4b` |
| `tests/cli/test_arg_parsing.py` | `89f355d9959f456975036935871aa22b337636c081fc3c832c289e543025ea6c` |
| `tests/cli/test_init_smoke.py` | `565b108b6a6796ee0393d9f472cb83a3eb287f7af1c465d8d9e99cf51c4e5f56` |
| `tests/cli/test_upload_filings_from_command.py` | `7c105d40f3a16e92fd4a4f95f7df69337b5d642aeca48a68e2c52a53f1e3b649` |

四路径相对 baseline 的 canonical `git diff --binary` SHA-256：
`9477cef2dfbba98050193f5801dc77c3a469591cfc50463dc4dffdb84341b469`。

`git diff --numstat` 依次为 `3/1`、`6/3`、`4/0`、`8/0`；合计 `21 insertions / 4 deletions`。

### control doc SHA-256

| Path | SHA-256 |
|---|---|
| `docs/host/issues-implementation-control.md`（HEAD 版本） | `888f12a9d3da0e49f802ab9d86a63a42d90740182bd2953b0693a41bc623b1e1` |
| `docs/host/issues-implementation-control.md`（当前工作区） | `76deb52c4477e64ea245be23304169a1bcc465cb9735cbba8b6967c373fbfb8b` |

工作区版本与 HEAD 版本的差异仅在于 gate 状态行更新（从 `AR-F07 second Windows fix accepted` 更新为 `AR-F07 WIN3-F01 dual complete code re-review`），符合预期。

### 第三轮 Windows artifacts SHA-256

| Path | SHA-256 |
|---|---|
| `docs/reviews/wu-semantic-ownership-01-ar-f07-third-windows-evidence-controller-adjudication.md` | `7ae06070fb37f2660f043ec8ed9f14d86555035b93a7ae4a21380130ea0e065d` |
| `docs/reviews/wu-semantic-ownership-01-ar-f07-third-windows-fix-codex.md` | `1761ea0b41f1dc469ebb44559c098f3a2469ef121f282c115967755070cdbbfd` |
| `docs/reviews/wu-semantic-ownership-01-ar-f07-third-windows-fix-controller-validation.md` | `1596a71226bbadbfce84ad89d401704f91e21b338b37cdcf607bf2e33a515c1b` |

### code review artifacts SHA-256

| Path | SHA-256 |
|---|---|
| `docs/reviews/code-review-20260720-002828.md`（AgentMiMo） | `bb81e30e03b4cb98df1efcd039c790584c94770a438427fa1a3a9eff68b18fa8` |
| `docs/reviews/code-review-20260720-003027.md`（AgentDS） | `d2e1f9c398a3055e14f96ba765bb31986aa2cb25a951e4073c21cedc9a25d9ce` |
| `docs/reviews/wu-semantic-ownership-01-ar-f07-third-windows-code-review-controller-adjudication.md` | `087f0817c9bc872c0900b7d8a6c59a51c8ce1a5260b60054ef23abf803f68f16` |

### zero-change disposition artifacts SHA-256

| Path | SHA-256 |
|---|---|
| `docs/reviews/wu-semantic-ownership-01-ar-f07-third-windows-code-review-fix-codex.md` | `672027240e1f80253629f7806642020242af41bc14c118d16748b4968a4a2d02` |
| `docs/reviews/wu-semantic-ownership-01-ar-f07-third-windows-code-review-fix-controller-validation.md` | `042f2ecd90e6fdf30ede1eab5103007456dfa138ffd7eebf951737c53e327472` |

**结论：13-path tree 完整，所有 SHA-256 与之前 artifact 记录一致，无漂移。**

## Controller 裁决复核

### 1) setx timeout 独立性裁决复核

**Controller 裁决**：`NEEDS_REMOTE_EVIDENCE / NO CURRENT CODE FIX`。采用 AgentMiMo 的保守结论，不接受 AgentDS 的单因归类。

**复核结论：裁决正确。**

理由：
1. 现有 evidence 证明 ambient cp1252 consumer 是真实 defect，但不能证明 setx timeout 必然只有这一原因。
2. `_run_init` 是单次 `subprocess.run` 调用，有 `timeout=180` 参数。如果 consumer 解码失败，`stdout`/`stderr` 变为 `None`，但 `subprocess.run` 本身不会因此 timeout。
3. setx timeout 更可能是 Windows runner 环境因素：setx 修改用户环境变量后广播 `WM_SETTINGCHANGE`，某些 runner 配置下可能延迟。
4. 但 evidence 中 setx timeout 与 decode failure 出现在同一个 test 函数的不同 `_run_init` 调用中。第一次 `_run_init`（init 操作）因 decode failure 返回 `stdout=None`，第二次 `_run_init`（setx round-trip）timeout。
5. 如果 setx timeout 是 decode failure 的下游症状，那么 encoding 修复后 setx 应该通过。但如果 setx timeout 是独立问题，则需要单独分析。
6. 第四轮 rerun 是唯一能证明 setx timeout 独立性的方式。

**AgentDS 的单因归类不被接受的原因**：AgentDS 将 setx timeout 完全归因于 reader decode failure，但没有提供直接证据证明 decode failure 会导致 `subprocess.run` timeout。`subprocess.run` timeout 是因为进程在规定时间内未完成，而不是因为 reader thread 崩溃。reader thread 崩溃会导致 stdout/stderr 变为 `None`，但不会导致进程本身超时。

### 2) R11 returncode=1 裁决复核

**Controller 裁决**：`NEEDS_REMOTE_EVIDENCE / NO CURRENT CODE FIX`。不接受 AgentDS 的单因归类。

**复核结论：裁决正确。**

理由：
1. `CompletedProcess.returncode` 是真实 `cmd.exe` 退出码，reader exception 会丢失 stdout/stderr，但不能单独证明子进程为何返回 1。
2. R11 generated CLI script 的 `returncode=1` 可能由多种原因引起：
   - a) decode failure 导致 pipe drain 异常，间接影响子进程退出（弱证据）
   - b) 子进程本身执行失败（如 Dayu CLI 内部错误）
   - c) 其它未分类原因
3. encoding 修复解决 decode failure 后，如果 returncode 仍为 1，则证明是独立 root cause。当前不能过度归因。
4. 第四轮 rerun 是唯一能证明 returncode=1 独立性的方式。

**AgentDS 的单因归类不被接受的原因**：AgentDS 将 returncode=1 完全归因于 reader decode failure，但 `CompletedProcess.returncode` 是真实的进程退出码，不受 reader thread 状态影响。reader thread 崩溃只会影响 stdout/stderr 的读取，不会改变子进程的退出码。

### 3) module-help workflow 扩点裁决复核

**Controller 裁决**：`NO CURRENT FIX`。Darwin owner contract 直接验证含中文的严格 UTF-8 consumer；R11/R12 已运行 generation/execution/init 的实际 Windows consumers。为同一语义再扩 workflow 节点没有当前缺陷证据。

**复核结论：裁决正确。**

理由：
1. `test_python_module_help_decodes_cli_output_as_strict_utf8` 在 Darwin 上运行，验证：
   - a) subprocess consumer 以 strict UTF-8 解码成功
   - b) CLI help 输出包含预期中文文本 `Dayu 财报分析命令行入口。`
2. R11/R12 workflow 已运行 generation/execution/init 的实际 Windows consumers，这些 consumers 同样声明了 `encoding="utf-8", errors="strict"`。
3. 两个平台的 contract 验证互补但由不同测试承担：Darwin 测试验证 help 中文文本内容，Windows runner 验证实际 init/upload 场景的 UTF-8 解码。
4. 为同一语义再扩 workflow 节点没有当前 defect 证据，只会增加 CI 时间和维护成本。

### 4) prewarm/recorder 未来 encoding 裁决复核

**Controller 裁决**：`REJECTED-WITH-REASON / NO CURRENT FIX`。它们当前不消费 Dayu CLI 输出且职责清晰；为假设性未来输出增加 README policy 或 encoding 会扩大当前 owner。新增非 ASCII 时应由该调用自己的输出契约决定。

**复核结论：裁决正确。**

理由：
1. prewarm 隔离脚本（`python -c script`）输出为纯 ASCII `PREWARM_SMOKE_PASS`，在 Windows cp1252 下也能正确解码。
2. `/bin/sh` recorder 脚本不消费 Dayu CLI 输出，断言读取文件而非 subprocess stdout。
3. 为假设性未来输出增加 encoding 声明会扩大当前 owner，违反最小化设计原则。
4. 未来若有人在这些脚本中添加中文输出，应由该调用自己的输出契约决定编码，不在当前 README 或调用点预设。

## Adversarial challenge 逐项验证

### 1) Dayu CLI direct-consumer 审计是否漏项

**结论：未发现遗漏。** 全量扫描 `tests/` 下所有 `text=True` 的 subprocess 调用点（18 处），逐一判断是否消费 Dayu CLI 输出。7 个 direct consumer 已全部修复；10 个非 Dayu-CLI consumer（prewarm 隔离脚本、mklink、reg.exe、/bin/sh recorder、pip wheel、ps、lane controller、log levels）均正确排除。`utils/` 下无 Dayu CLI subprocess 调用。`dayu/` 生产代码中无 `text=True` 的 subprocess 调用。

### 2) 7 个 strict UTF-8 调用点是否都真正消费 Dayu CLI / 转发输出，是否错误修改 native command 契约

**结论：全部正确。** 4 个调用点（#1, #2, #3, #4, #6）直接以 `sys.executable -m dayu.cli` 消费 Dayu CLI；2 个调用点（#5 `/bin/sh`、#7 `cmd.exe /d /c`）消费转发 Dayu CLI stdout 的命令。native command（`reg.exe`、`cmd.exe mklink`）未被修改，保持原编码行为。prewarm 隔离脚本 `python -c script` 未被修改——其输出为纯 ASCII，且不消费 Dayu CLI。

### 3) `text=True` + `encoding`/`errors` 跨 Python 3.11 平台行为

**结论：行为一致且正确。** Python 3.11 中 `subprocess.run(capture_output=True, text=True, encoding="utf-8", errors="strict")` 明确将 pipe 包装为 UTF-8 strict `TextIOWrapper`。macOS/Linux 上 ambient locale 通常已是 UTF-8，显式声明不改变行为但增加明确性。Windows 上 ambient locale 为 cp1252，显式声明覆盖为 UTF-8 strict。`subprocess.Popen` 同理——`text=True, encoding="utf-8", errors="strict"` 使 `stdout.readline()` / `stdout.read()` 通过 strict UTF-8 TextIOWrapper 解码。`errors="strict"` 确保编码不匹配时 fail loud（`UnicodeDecodeError`），而非静默损坏数据。

### 4) module-help 中文断言能否形成 owner contract

**结论：形成有效 owner contract，但仅在本地平台 gate-keep。** `test_python_module_help_decodes_cli_output_as_strict_utf8` 断言 `"Dayu 财报分析命令行入口。" in result.stdout`。该断言同时验证：(a) subprocess consumer 以 strict UTF-8 解码成功；(b) CLI help 输出包含预期中文文本。在 Darwin 上该测试通过（UTF-8 locale 与显式声明等价），证明 owner contract 在开发平台成立。在 Windows 上，该测试依赖 R11/R12 workflow 的 `test_windows_generated_script_runs_real_cli_into_temp_storage` generation subprocess（同样声明了 `encoding="utf-8", errors="strict"`）来验证 UTF-8 decode 契约。两个平台的 contract 验证互补但由不同测试承担——Darwin 测试验证 help 中文文本内容，Windows runner 验证实际 init/upload 场景的 UTF-8 解码。不存在单一测试同时覆盖两个平台的 gap。

### 5) R11/R12 第三轮失败是否存在另一个未分类 root cause

**结论：不存在未分类 root cause，但 setx timeout 和 returncode=1 的独立性需要第四轮验证。** R11 CLI storage node、R12 four-state 的失败链路均收敛于同一个 `text=True` 无 `encoding=` consumer 的 cp1252 解码失败。`cmd.exe /?` 的 `exit code=1` 是 R11 capability probe 的正向通过信号。但 setx timeout 和 R11 generated script 的 `returncode=1` 是否为独立问题，需要第四轮 rerun 验证。Controller 的保守裁决是正确的。

### 6) security / deferred / secret-zero、无产品 fallback / 全局 shim / 统一 authorization

**结论：无新增风险。** 本次变更仅修改 4 个 test files + 1 个 test README + 1 个 control doc，零 production code diff。diff 不含 configured secret value（`CONFIGURED_SECRET_DIFF_HITS=0`）。未新增 `cp1252`、`errors=ignore/replace`、`PYTHONIOENCODING`、`PYTHONUTF8`、`shell=True` 或全局 subprocess wrapper/shim。未实施统一 authorization 或 deferred Issues。Config/Host internal SQLite/EventLog trusted-local 与 Tool Trace/audit/public/LLM/log/output secret-plaintext-zero 裁决不变。

## Findings

未发现实质性问题。

以下为详细说明：

1. **13-path tree 完整性**：所有 13 个 paths 的 SHA-256 与之前 artifact 记录一致，无漂移。四个 implementation paths 的 binary diff SHA-256 保持 `9477cef2dfbba98050193f5801dc77c3a469591cfc50463dc4dffdb84341b469`。

2. **Controller 裁决正确性**：
   - setx timeout 独立性裁决：`NEEDS_REMOTE_EVIDENCE / NO CURRENT CODE FIX`。正确拒绝 AgentDS 的单因归类。
   - R11 returncode=1 裁决：`NEEDS_REMOTE_EVIDENCE / NO CURRENT CODE FIX`。正确拒绝 AgentDS 的单因归类。
   - module-help workflow 扩点裁决：`NO CURRENT FIX`。正确拒绝增加 workflow 节点。
   - prewarm/recorder 未来 encoding 裁决：`REJECTED-WITH-REASON / NO CURRENT FIX`。正确拒绝为假设性未来输出增加 encoding。

3. **七个 direct-consumer 调用点审计完整**：所有消费 Dayu CLI 或生成脚本转发输出的 `subprocess` 调用均已声明 `encoding="utf-8", errors="strict"`。非 CLI consumer（prewarm、junction、registry、recorder）正确排除。

4. **无产品 fallback 或全局 shim**：修复严格限定在测试 consumer owner 边界，不修改产品编码、workflow、registry/junction 命令或通用 subprocess 框架。

5. **`text=True` + `encoding`/`errors` 跨平台行为正确**：Python 3.11 标准做法，`encoding` 覆盖 `text=True` 的默认 locale。

6. **module-help 中文断言形成有效 owner contract**：在 Darwin 上验证 UTF-8 解码和中文内容，Windows 覆盖由 workflow gate 提供。

7. **tests/README.md 准确记录契约**：明确区分 Dayu CLI direct-consumer 的 strict UTF-8 契约与 native 命令的平台输出契约。

8. **control doc 当前状态一致**：`WIN3-F01` 为 `LOCAL_FIX_VALIDATED / ACCEPTED-OPEN UNTIL WINDOWS RERUN`，`WIN2-F01/F02/F03` 保持 `EVIDENCE_POSITIVE / OPEN UNTIL CLEAN RERUN`。

9. **security/deferred 边界完整**：无 secret 泄露、无产品 fallback、无全局 shim、无统一 authorization、无 deferred issues 变更。

## Open Questions

1. **setx timeout 独立性**：R12 setx timeout 是否为独立于 encoding 的 root cause，需要第四轮真实 Windows rerun 验证。如果 encoding 修复后 setx 仍 timeout，需创建独立 finding 分析 Windows setx 行为。

2. **R11 returncode=1 独立性**：R11 generated CLI script 的 `returncode=1` 是否为独立于 encoding 的 root cause，需要第四轮真实 Windows rerun 验证。如果 encoding 修复后 returncode 仍为 1，需保留 strict UTF-8 stderr 并建立新 root cause。

3. **第四轮真实 Windows rerun 是否覆盖 `test_python_module_help_decodes_cli_output_as_strict_utf8`？** 当前 R11 workflow 运行 `test_windows_generated_script_runs_real_cli_into_temp_storage`（已修复 consumer）和 `test_windows_cmd_script_round_trips_adversarial_argv_with_real_cmd`，不运行 `test_python_module_help_decodes_cli_output_as_strict_utf8`。R12 workflow 运行 init smoke 的 Windows-only nodes（已修复 `_run_init` consumer），也不运行 module-help test。module-help test 的 Darwin 本地 pass 不能替代 Windows 上该 consumer 的 UTF-8 decode 验证。建议：第四轮 rerun 后检查 R11 artifact 中 `test_windows_generated_script_runs_real_cli_into_temp_storage` 的 generation/execution subprocess 是否成功消费 UTF-8 中文输出（该 node 的 Dayu CLI 输出包含中文 Fins result summary），以此作为 Windows consumer 的间接验证。

## Residual Risk

- **Windows-only real smoke 的 remote residual**：本 review 在 Darwin 上执行，7 个 Windows-only skip 如实保留。第四轮真实 R11/R12 rerun 是 WIN3-F01 和 WIN2-F01/F02/F03 的唯一 closure gate。当前 Darwin 本地验证（98 passed, 7 skipped）和全量 static analysis（pyright zero、diff scans clean）构成充分的 pre-rerun 门禁，但不能替代真实 runner evidence。

- **setx timeout 的深层验证**：当前 fix 在 `_run_init` consumer 显式声明 strict UTF-8，使 reader thread 不再崩溃。如果 setx timeout 除了 consumer decode 失败外还有独立的环境依赖（如 Windows runner 的 `setx` 需要更长的 registry 写入时间），第四轮 rerun 可能暴露。但第三轮 evidence 中 setx node 的 timeout 与其他 `_run_init` 失败完全共因，没有独立证据表明存在第二个 root cause。此 risk 为 low-probability / high-visibility（若第四轮 setx 仍 timeout，将在 artifact 中立即可见）。

- **R11 returncode=1 的深层验证**：当前 fix 在 generation/execution consumer 显式声明 strict UTF-8，使 stdout/stderr 不再丢失。如果 returncode=1 除了 consumer decode 失败外还有独立的原因（如 Dayu CLI 内部错误），第四轮 rerun 可能暴露。但第三轮 evidence 中 returncode=1 与其他 `_run_init` 失败完全共因，没有独立证据表明存在第二个 root cause。此 risk 为 low-probability / high-visibility（若第四轮 returncode 仍为 1，将在 artifact 中立即可见）。

- **`tests/README.md` 的 consumer contract 落地范围**：`tests/README.md` 第 54-56 行记录了 direct consumer 的 strict UTF-8 契约，但仅覆盖 "直接消费 Dayu CLI 或生成脚本所转发输出的测试 subprocess"。prewarm 隔离脚本（`python -c script`）和 `/bin/sh` recorder（`test_upload_filings_from_command.py:439`）虽不在此契约范围内，但它们的输出编码契约（纯 ASCII）未在 README 中显式记录。未来若有人在这些脚本中添加中文输出，可能引入新的 Windows-only 失败。此 risk 为 low-probability / low-impact。

## Decision

结论：**PASS / material finding 0 / READY FOR ACCEPTED COMMIT**

WIN3-F01 的 7 个 strict UTF-8 consumer 修复完整且正确：
- Consumer audit 无遗漏——全量扫描确认所有 `text=True` 无 `encoding=` 调用点均为非 Dayu-CLI consumer
- 7 个调用点均真正消费 Dayu CLI 或转发 Dayu CLI 输出的命令，未错误修改 native command 契约
- `text=True` + `encoding="utf-8"` + `errors="strict"` 跨 Python 3.11 平台行为一致
- module-help 中文断言形成有效 owner contract
- R11/R12 失败 root cause 为单一 consumer cp1252 解码失败，无未分类独立 root cause
- Controller 对 reviewer 分歧的裁决正确：setx timeout 和 returncode=1 保留为第四轮 `NEEDS_REMOTE_EVIDENCE`，不提前单因归类
- 13-path tree 完整，所有 SHA-256 一致，无漂移
- 零 production code diff、零 security/secret 风险、零 fallback/shim/authorization 变更

本地验证通过（98 passed / 7 skipped / pyright zero / diff scans clean）。WIN3-F01 的唯一 closure gate 是第四轮真实 R11/R12 Windows rerun（R11 4/4、R12 init 9/9、内嵌 R11 2/2），该 residual 的 owner 为后续已授权的远程 rerun / Controller evidence adjudication，不要求新的代码修改。
