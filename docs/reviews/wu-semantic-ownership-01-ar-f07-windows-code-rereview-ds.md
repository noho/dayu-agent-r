# WU-SEMANTIC-OWNERSHIP-01 AR-F07 Windows Fix — AgentDS Final Immutable Re-review

## Scope

- Mode: current changes (immutable re-review of frozen tree)
- Branch: `phaseflow/host-issues-control`
- Base HEAD: `07db7af3855b7fc80a24d74a3214bef215752d8d`
- Review agent: AgentDS (second reviewer, final re-review; read-only, no code/control/PR mutation)
- Output file: `docs/reviews/wu-semantic-ownership-01-ar-f07-windows-code-rereview-ds.md`
- Prior artifacts reviewed:
  - Initial DS review: `docs/reviews/wu-semantic-ownership-01-ar-f07-windows-code-review-ds.md`（外部 SHA-256 `c7aa2111a5bec4dee5d8859d6aff2714ad9b3571bdbf63acef46391bc21b2dfe`）
  - Initial MiMo review: `docs/reviews/wu-semantic-ownership-01-ar-f07-windows-code-review-mimo.md`（外部 SHA-256 `2580709c48b99632f48e91db9a86a835c804b5ee732fefae495479427d6502a2`）
  - Controller adjudication: `docs/reviews/wu-semantic-ownership-01-ar-f07-windows-code-review-controller-adjudication.md`（外部 SHA-256 `5879d308c472ff81ecade68620e657507a15339e413dd8efa225d57b631e55a1`）
  - Codex fix confirmation: `docs/reviews/wu-semantic-ownership-01-ar-f07-windows-code-review-fix-codex.md`（外部 SHA-256 `132cd595c696e0ea014472b3e2443f29e65656ce8b830548d835243554c71f9d`）
  - Controller validation of fix: `docs/reviews/wu-semantic-ownership-01-ar-f07-windows-code-review-fix-controller-validation.md`（外部 SHA-256 `8700fd86377bcdc2ea422ac1c826c2e7e1c070c3ab116ea044dd318bdaf67483`）
  - Codex implementation: `docs/reviews/wu-semantic-ownership-01-ar-f07-windows-fix-codex.md`（外部 SHA-256 `0d1a8793d89072c1bb55687895cea3d42cb4becded04f4afbeba6a4af3ae43bf`）
  - Controller validation (implementation): `docs/reviews/wu-semantic-ownership-01-ar-f07-windows-fix-controller-validation.md`（外部 SHA-256 `a59d6754e7ce50d265a1fb1c6b6ba281015632d5d68ff005542f227abd8def42`）

所有输入 artifact 的外部 SHA-256 与本 session 独立计算值完全一致，artifact chain 完整无损。

### Immutable snapshot re-verification

本轮独立重新计算：

- Tracked binary diff SHA-256: `18876f5b596a430588bdafa390d1e0cbbd19534864718fdfca9a271585dc00e5` → **MATCH** ✓
- Tracked path-list SHA-256: `b9f39d742e80f57b427d0632e12b8e24bf731d2a502b0247a74cec4706fb2001` → **MATCH** ✓
- Exact tracked paths: 8（与冻结列表完全一致）→ **MATCH** ✓
- Staged paths: 0 → **MATCH** ✓
- `git diff --check`: pass → **MATCH** ✓

逐文件内容 SHA-256 与 Codex fix confirmation artifact 冻结值逐一比对：

| Path | 本轮计算 SHA-256 | 冻结值 | 匹配 |
|------|-----------------|--------|------|
| `.github/workflows/r11-upload-script-windows.yml` | `0897e415...88b2` | `0897e415...88b2` | ✓ |
| `.github/workflows/r12-init-windows.yml` | `3a14172f...8da6` | `3a14172f...8da6` | ✓ |
| `dayu/cli/init_workspace.py` | `355b7af3...8d26` | `355b7af3...8d26` | ✓ |
| `dayu/cli/run_keys.py` | `e0f9f97c...3627` | `e0f9f97c...3627` | ✓ |
| `tests/README.md` | `0bd909af...e382` | `0bd909af...e382` | ✓ |
| `tests/cli/test_init_smoke.py` | `b5a82e8b...6ec4` | `b5a82e8b...6ec4` | ✓ |
| `tests/cli/test_init_workspace.py` | `fefdc334...b630` | `fefdc334...b630` | ✓ |
| `tests/cli/test_run_keys.py` | `2f4c746a...20e9` | `2f4c746a...20e9` | ✓ |

**结论：implemented tree 为 zero-change，与 Codex fix confirmation 和 Controller validation 时刻的冻结内容完全一致。无 drift。**

### Included scope（8 changed files）

1. `.github/workflows/r11-upload-script-windows.yml`
2. `.github/workflows/r12-init-windows.yml`
3. `dayu/cli/init_workspace.py`
4. `dayu/cli/run_keys.py`
5. `tests/README.md`
6. `tests/cli/test_init_smoke.py`
7. `tests/cli/test_init_workspace.py`
8. `tests/cli/test_run_keys.py`

### Excluded scope

- 所有 `docs/reviews/` 下的 review/control artifact（输入，非审查对象）
- Untracked files outside review boundary

### Parallel review coverage

单 reviewer 逐文件走读，未使用 subagent 并行。

---

## 重点确认项

### 1. F01—F04 四项修复仍正确

对冻结的 8 个文件逐文件、逐语义 owner 重新走读，每项修复的 owner boundary、实现路径与测试 contract 均与两路初审结论一致。

#### F01 — 非 POSIX conditional imports / name resolution

**PASS / 未漂移。**

- `dayu/cli/run_keys.py`（hash `e0f9f97c...3627`）：`termios`/`tty` 仅在 `if os.name == "posix":` 分支导入，位于模块顶层，非函数内 lazy import。`_POSIX_TERMINAL_CONTROL_AVAILABLE: Final[bool] = os.name == "posix"` 为模块级静态常量，是平台 capability 唯一真源。
- factory `new_running_key_monitor`（line 256）：`_POSIX_TERMINAL_CONTROL_AVAILABLE` 在 `isatty()` 前消费，非 POSIX 固定返回 `NoopRunningKeyMonitor()`。
- `TtyRunningKeyMonitor.start()`（line 151）与 `_restore_terminal_attrs`（line 285）：各自在操作前独立 guard `_POSIX_TERMINAL_CONTROL_AVAILABLE`，防止绕过 factory 直接构造后的终端操作。
- `tests/cli/test_run_keys.py`（hash `2f4c746a...20e9`）：新增 `test_new_running_key_monitor_uses_noop_for_non_posix_tty` 验证 factory 与直接构造两条路径在非 POSIX 均返回 no-op；PTY 测试标记 `@pytest.mark.skipif(os.name != "posix")`。
- 零 `hasattr`/`getattr`/lazy import/下游 fallback。

#### F02 — R11 cmd execution gate / help exit classification

**PASS / 未漂移。**

- `.github/workflows/r11-upload-script-windows.yml`（hash `0897e415...88b2`）：
  - `cmd.exe /d /c ver 2>&1 | Set-Content ... cmd-version.txt` — 真实、无副作用、exit 0 gate。
  - `$LASTEXITCODE -ne 0` → `throw` — fail-closed。
  - `cmd.exe /? 2>&1 | Set-Content ... cmd-help.txt` — 诊断 artifact。
  - `$cmdHelpExitCode` 显式捕获，`-notin @(0, 1)` → `throw` — 未分类退出 fail-closed。
  - 无 `continue-on-error`、`|| true`、pytest gate 弱化。
- `.github/workflows/r12-init-windows.yml`（hash `3a14172f...8da6`）：path filter 与 `Get-FileHash` 均纳入新增文件；test matrix 显式加入 non-POSIX no-op owner node。

#### F03 — registry delete/query/key-access 语义正确性

**PASS / 未漂移。**

- `tests/cli/test_init_smoke.py`（hash `b5a82e8b...6ec4`）：
  - `_delete_registry_value_and_verify_absent`：三步验证状态机 — delete(接受 0/1) → exact value query(必须=1) → 父 key accessibility probe(必须=0)。
  - 幂等性：value 原本不存在时 delete 返回 1，query/v 返回 1，key query 返回 0 → 幂等成功。
  - `_ScriptedRegistryCommandRunner`：测试专用 deterministic stub，`stdout="test-secret-value"` 用于证明错误消息不含 secret。
  - 参数化 owner matrix 6 cases：delete 0/1、delete 2、query/v 0、query/v 2、key 1 — 全部 fail-closed 且只投影变量名。
  - 真实 `setx` round-trip 的 setup/finally 统一复用同一 helper。

#### F04 — Windows O_RDWR + fsync durability owner

**PASS / 未漂移。**

- `dayu/cli/init_workspace.py`（hash `355b7af3...8d26`）：
  - `_staged_file_sync_open_flags(platform_system)`：唯一 owner。`_validate_platform` → Windows 返回 `os.O_RDWR`，Darwin/Linux 返回 `os.O_RDONLY | os.O_NOFOLLOW`，未知平台 fail-closed。
  - `_sync_staged_config`（line 976）：`file_open_flags = _staged_file_sync_open_flags(platform_system)`，不再内联计算 flags。
  - `os.open → fstat S_ISREG → fsync → close` 链不变。publication `os.replace`、backup、rollback、containment、symlink/reparse、cleanup 零改动。
- `tests/cli/test_init_workspace.py`（hash `fefdc334...b630`）：`test_staged_file_sync_open_flags_match_platform_flush_contract` 断言 Windows/POSIX exact flags 与未知平台 fail-closed。

---

### 2. MiMo path-hash 项 rejected-with-reason 的直接证据

Controller 对 MiMo-01（path-list SHA-256 不可复现）裁决为 `REJECTED_AS_VERIFICATION_COMMAND_ERROR / NO_CODE_ACTION`。直接证据链如下：

1. **Controller 独立计算**：在 reviewer 完成前后多次执行 canonical command `git diff --name-only | LC_ALL=C sort | shasum -a 256`，均得到 `b9f39d742e80f57b427d0632e12b8e24bf731d2a502b0247a74cec4706fb2001`，并打印出完全一致的 8 个路径。
2. **AgentDS 独立匹配**：DS 初审独立执行同一 canonical command，得到相同 `b9f39d74...2001`，并列出完全一致的 8 个路径。
3. **Codex fix confirmation 独立匹配**：Codex 在 fix confirmation gate 再次独立计算，得到相同值，并逐文件列出 exact content hashes。
4. **本轮 re-review 独立匹配**：本轮再次执行同一 canonical command，得到 `b9f39d74...2001`，8 个路径完全一致。
5. **MiMo 也匹配了 binary diff**：MiMo 报告的 binary diff SHA-256 `18876f5b596a430588bdafa390d1e0cbbd19534864718fdfca9a271585dc00e5` 与冻结值完全一致。binary diff 包含路径与内容——若工作树漂移或漏审路径，binary diff 不可能匹配。

综合以上 5 点：`b9f39d74...2001` 由 4 次独立计算（Controller、DS、Codex、本轮）一致确认；MiMo 的 `2cfef7ff...` 与 binary diff 匹配矛盾，唯一合理解释是 MiMo 的 path-list 计算命令与 canonical command 不同（如换行符处理、`sort` locale、或误包含 untracked files）。此差异不构成代码、测试、workflow 或 control finding。

**裁决成立。**

---

### 3. DS 初审 open questions no-code 裁决是否成立

#### OQ1：PowerShell `$LASTEXITCODE` 管道行为

Controller 裁决：`NON_BLOCKING_EXTERNAL_VALIDATION_POINT / NO_LOCAL_CODE_ACTION`。

验证：

- R11 workflow 显式声明 `shell: pwsh`（PowerShell 7+），非 `shell: cmd` 或 `shell: powershell`（Windows PowerShell 5.1）。
- PowerShell 7+ 的 `$LASTEXITCODE` 在管道中正确捕获 native command 退出码——这是 documented behavior，非未定义行为。
- 首轮 evidence 中 `cmd-help.txt` 成功捕获（180 行完整帮助输出），间接证明 `$LASTEXITCODE` 在管道中正确工作——若 `$LASTEXITCODE` 未设置，后续 `if ($LASTEXITCODE -ne 0)` 会把 `$null` 当作非零并 throw，workflow 仍 fail-closed。
- 真实 PowerShell 语义由 Windows rerun 提供 release evidence；macOS 本地无法模拟。

**裁决成立。** 这是外部验证依赖，不是代码缺陷。

#### OQ2：Windows open-time no-follow 防护

Controller 裁决：`NON_BLOCKING_EXISTING_ORDER_INVARIANT / NO_CODE_ACTION`。

验证：

- 当前 `_sync_staged_config` 调用顺序（line 965-976）：`_validate_ordinary_tree` → 平台 open flags 计算 → `os.open`。tree validation 在 `os.open` 前已完成 ordinary tree 全量扫描，拒绝 symlink/reparse/special file。
- Windows Python 3.11 中 `os.O_NOFOLLOW` 未定义（Python stdlib 限制），不是代码缺陷。
- 文件位于 transaction-private staging 目录（仅当前进程可访问），不存在并发写入者。
- `os.fstat` 在 open 后再次验证 S_ISREG，提供 TOCTOU 防护。
- DS 初审建议的"docstring 注释记录顺序约束"是文档增强建议，不是当前缺陷。

**裁决成立。** 当前调用顺序安全；假设性未来重构不是当前 code finding。

---

### 4. 无新 material finding

对 7 个审查领域逐项重新走读（与 DS 初审相同的领域划分），确认初审 PASS 结论仍然成立，且本轮未发现初审遗漏的 material finding：

| 审查领域 | 初审结论 | 本轮复查 |
|----------|---------|---------|
| 1. 非 POSIX conditional imports / name resolution | PASS | 仍 PASS；无 drift |
| 2. Windows O_RDWR + fsync durability owner | PASS | 仍 PASS；无 drift |
| 3. Registry delete/query/key-access 语义 | PASS | 仍 PASS；无 drift |
| 4. R11 cmd ver/help LASTEXITCODE / fail-closed | PASS | 仍 PASS；无 drift |
| 5. Tests owner-level / test-only branch / Windows skip | PASS | 仍 PASS；无 drift |
| 6. Topic 1-9 / no-deferred / security / Config-SQLite | PASS | 仍 PASS；无 drift |
| 7. Adversarial failure / race / overdesign / semantic ownership drift | PASS | 仍 PASS；无 drift |

补充验证了以下初审未显式覆盖的点：

- `test_tty_running_key_monitor_close_is_idempotent`（无 `skipif`，在所有平台运行）：验证该测试在非 POSIX 上安全——`TtyRunningKeyMonitor` 构造时不依赖 `termios`，`start()` 检查 capability 后 no-op，`close()` 安全 no-op（`_thread` 为 None）。✓
- `_validate_platform` 接受的平台集合（Windows/Darwin/Linux）与 `_staged_file_sync_open_flags` 的分支覆盖完全一致，无遗漏平台。✓
- `_ScriptedRegistryCommandRunner` 正确实现 `_RegistryCommandRunner` Protocol——signature 匹配，`stdout`/`stderr` 包含 `test-secret-*` 用于安全证明。✓

**Material findings: 0**（与初审一致）。

---

### 5. 无 needs-evidence code finding

本轮复查确认的唯一"需要外部证据"项仍是真实 Windows rerun，这是 AR-F07 release gate，不是 accepted code finding：

- F01 的 Windows import/collection 需要真实 runner 证明 `dayu.cli` 可 import 且 test collection 不再含 `ModuleNotFoundError: termios`。
- F02 的 cmd execution gate 需要真实 runner 证明 `cmd.exe /d /c ver` exit 0、help exit 被正确分类。
- F03 的 registry cleanup 需要真实 runner 证明 `setx` round-trip + 幂等 absent cleanup 完成且 registry 无污染。
- F04 的 Windows flush 需要真实 runner 证明 `O_RDWR` descriptor 可 fsync，transaction 可到达 publication/rollback contract。

以上全部属于 external validation residual，与本轮及初审的 0 accepted code finding 结论一致。本地 macOS skip 未在任何一个 artifact 中被记作 Windows pass。

---

### 6. 无 scope/deferred/security drift

- **Scope drift**：8 个 tracked paths 与计划一致；未新增、删除或重命名文件。未修改 control doc、provider/model/key/retry/quota/budget、Fins business、Web/WeChat/render。
- **Deferred drift**：Issue #142、#151、#175、#177、#178 未被触及。
- **Security drift**：`init_workspace.py` 不接触 secret（模块 docstring 明确声明）；registry cleanup 错误只投影变量名（`test_registry_cleanup_rejects_unproved_absence_without_command_output` 的 `assert "test-secret" not in message` 直接证明）；R11/R12 artifact 只上传变量名和 source hashes，不保存 environment/registry values。
- **Topic 1-9 final disposition**：9 个 topic 均未被本修复触及或改变。

---

## Findings

未发现实质性问题。

---

## Open Questions

无。

DS 初审的两条 open questions 已被 Controller 正确裁决为 non-blocking/no-code，本轮确认裁决成立且无新 open question 产生。

---

## Residual Risk

与 Codex fix confirmation 和 Controller validation 完全一致：

1. **真实 Windows rerun 必须执行**：AR-F07 的四项修复已在唯一 owner boundary 完成，本地 macOS owner tests 全部通过，但 F01—F04 的最终关闭必须由两条真实 Windows rerun（R12 init + R11 upload）及其完整 artifact 提供 release evidence。此 residual 是 AR-F07 release gate，不是 waiver，也不是可被本地 macOS 结果替代的 code finding。

2. **跨平台 flag test 的 Windows 侧 POSIX 分支未直接断言**：`test_staged_file_sync_open_flags_match_platform_flush_contract` 的 POSIX flag 断言在 `if os.name == "posix":` 守卫内，Windows runner 上该分支不被执行。`_staged_file_sync_open_flags` 的确定性极高（platform string → exact flags 的简单映射），R12 workflow 的 `Get-FileHash` 提供跨平台 source identity proof。风险低。

3. **registry key 存在性假设**：`_delete_registry_value_and_verify_absent` 假设 `HKCU\Environment` 父 key 存在。对 Windows smoke test 场景正确；若未来复用至其他 registry key，需增加 key 创建逻辑。当前使用场景无风险。

---

## Classification summary

| 类别 | 数量 | 状态 |
|------|-----|------|
| accepted code finding | 0 | closed |
| rejected-with-reason | 1（MiMo-01） | closed；证据链确认 |
| non-blocking open question | 0（初审 2 条已裁决） | closed |
| new material finding | 0 | — |
| needs-evidence code finding | 0 | — |
| scope/deferred/security drift | 0 | — |
| needs real Windows rerun | 1（AR-F07 release gate） | 非 code finding |

---

## Conclusion

`PASS / ZERO_CHANGE_CONFIRMED / NO_NEW_MATERIAL_FINDING`

AgentDS final immutable re-review 确认：

- 冻结的 8 文件实现树为零变更（zero-change），binary diff、path-list 与逐文件内容 SHA-256 全部与 Codex fix confirmation 和 Controller validation 时刻的冻结值一致。
- F01—F04 四项修复均在正确 semantic owner boundary 处实现，未引入 downstream fallback、lazy import、`hasattr`/`getattr`、兼容 shim 或 test-only production branch。
- MiMo-01 path-hash 项的 rejected-with-reason 裁决有 4 次独立计算的直接证据支撑，裁决成立。
- DS 初审两条 open questions 的 no-code 裁决成立——均为外部验证依赖或假设性未来风险，非当前代码缺陷。
- 本轮逐领域复查未发现初审遗漏的 material finding、needs-evidence code finding、scope drift、deferred drift 或 security drift。
- 真实 Windows rerun 是后续 release evidence，不是可被本地 macOS skip 替代的 code finding。
