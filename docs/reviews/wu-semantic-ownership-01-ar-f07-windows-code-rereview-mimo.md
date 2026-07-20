# WU-SEMANTIC-OWNERSHIP-01 AR-F07 Windows code re-review (AgentMiMo final)

## 结论

`PASS / ACCEPTED_CODE_FINDING=0 / NO_NEW_MATERIAL_FINDING`

本次 re-review 对同一 immutable implementation snapshot 执行独立完整审查。F01—F04 仍然正确；MiMo-01 path-hash 裁决有直接证据支撑；DS open questions 的 no-code 裁决成立；无新 material finding、needs-evidence code finding、scope drift、deferred drift 或 security drift。

## 审查范围

- Mode: current changes (WU-SEMANTIC-OWNERSHIP-01 AR-F07 Windows fix re-review)
- Branch: `phaseflow/host-issues-control`
- Base HEAD: `07db7af3855b7fc80a24d74a3214bef215752d8d`
- Output file: `docs/reviews/wu-semantic-ownership-01-ar-f07-windows-code-rereview-mimo.md`
- Included scope: 8 tracked changed files (unstaged diff)
- Parallel review coverage: 无

## Immutable snapshot 独立验证

以下全部由本 reviewer 独立从工作树重新计算：

| 验证项 | 命令 | 结果 |
|---|---|---|
| tracked binary diff SHA-256 | `git diff --binary \| shasum -a 256` | `18876f5b596a430588bdafa390d1e0cbbd19534864718fdfca9a271585dc00e5` ✅ |
| canonical eight-path-list SHA-256 | `git diff --name-only \| LC_ALL=C sort \| shasum -a 256` | `b9f39d742e80f57b427d0632e12b8e24bf731d2a502b0247a74cec4706fb2001` ✅ |
| tracked changed paths | `git diff --name-only` | 精确 8 个 ✅ |
| staged paths | `git diff --cached --name-only` | 0 ✅ |

8 个文件内容哈希全部精确匹配 Codex artifact 记录值：

| Path | 独立计算 SHA-256 | 匹配 |
|---|---|---|
| `.github/workflows/r11-upload-script-windows.yml` | `0897e4152c8a878bf2203b176072558cf7d6537f855762170f0804a10c6388b2` | ✅ |
| `.github/workflows/r12-init-windows.yml` | `3a14172f84a338d40f12c4cd2e056dbe6dde255168e8366ac60b6a017f438da6` | ✅ |
| `dayu/cli/init_workspace.py` | `355b7af3c84151de7926fdc93f9d833a814648b46036e82cdfb58336a9c88d26` | ✅ |
| `dayu/cli/run_keys.py` | `e0f9f97c17dca9dc5f4b24329b96fdd8216cea193dd020e8382582d10bf53627` | ✅ |
| `tests/README.md` | `0bd909af6ee2dcf6e99a281a9fa3ebc2c398805e84289580b972ceef409fe382` | ✅ |
| `tests/cli/test_init_smoke.py` | `b5a82e8b2385d909070a3429a58fe4e67bcbead1b6c737ca841e8aafc4c06ec4` | ✅ |
| `tests/cli/test_init_workspace.py` | `fefdc334dd7a07b1720cb6545b1473fe3b7482270974c8975d6e8647c74cb630` | ✅ |
| `tests/cli/test_run_keys.py` | `2f4c746aa8c2fb34b59bec9994dc750b51cace64b61a2f90b9d6896ee9c020e9` | ✅ |

## 四项 Windows finding 独立复核

### AR-F07-WIN-F01: Windows import/collection

**实现审查**: `init_command.py:107-114` — POSIX 顶层条件导入 `capability` 与 `factory`，`else: pass` 建立 non-POSIX no-op boundary。`init_workspace.py:173-175` — `_reparse_tag` 在 non-Windows 下 `return 0`。`_PathIdentity` dataclass（`init_workspace.py:43-52`）提供 `file_attributes` 与 `reparse_tag` 默认值。

**test_init_smoke.py** 新增 4 个 Windows-only 测试：`test_windows_real_four_state_and_config_reload`、`test_windows_real_preseeded_junction_fails_closed`、`test_windows_real_symlink_privilege_or_fail_closed`、`test_windows_real_workspace_root_identity_drift_is_rejected`。这些测试使用 `platform.system() != "Windows"` skip，不在 macOS 上伪装通过。

**结论**: POSIX 条件导入边界正确；non-POSIX no-op 语义正确；Windows `_PathIdentity` 收集与 `_validate_ordinary_tree` 消费链路语义一致。PASS。真实 Windows import/collection 待 rerun release evidence。

### AR-F07-WIN-F02: cmd execution gate

**实现审查**: `r11-upload-script-windows.yml:43-59` — `cmd.exe /d /c ver` 强制 exit 0，help 仅分类 0/1，非零 exit 非 1 时仍 fail closed（`Write-Error "dayu-cli ver exited with unexpected code $LASTEXITCODE"`）。`r12-init-windows.yml:43-52` — 同一结构。

**结论**: YAML 解析通过；exit code 分类逻辑正确；fail-closed 行为正确。PASS。真实 PowerShell/cmd 语义待 Windows rerun。

### AR-F07-WIN-F03: registry round-trip/cleanup

**实现审查**: `run_keys.py:454-484` — `_delete_registry_value_and_verify_absent` 执行三步协议：
1. `delete` → 接受 `{0, 1}`（实际删除或原本不存在）；
2. `query /v` → 必须返回 `1`（精确 value 不存在）；
3. `query`（父 key）→ 必须返回 `0`（父 key 可访问）。

错误消息只投影 `env_name`，不回显 command output（`test_init_smoke.py:907` 断言 `"test-secret" not in message`）。

**测试**: `test_registry_cleanup_accepts_deleted_or_already_absent_value`（parametrized 0/1）覆盖成功路径；`test_registry_cleanup_rejects_unproved_absence_without_command_output` 覆盖 4 种失败路径（delete 失败、value 仍存在、verification 失败、key access 失败）。

**结论**: 三步协议语义正确；fail-closed 正确；secret 脱敏正确。PASS。真实 Windows registry 语义待 rerun。

### AR-F07-WIN-F04: Windows flush/publication rollback

**实现审查**: `init_workspace.py:994-1011` — 新增 `_staged_file_sync_open_flags` 函数：
- Windows: `O_RDWR`（支持真实 `os.fsync`）
- POSIX: `_READ_ONLY_OPEN_FLAGS | os.O_NOFOLLOW`（只读 + 防跟随链接）
- 调用 `_validate_platform` 做平台白名单校验

`_sync_staged_config`（`init_workspace.py:976`）调用该函数替代原来内联的条件逻辑。

语义 ownership 链路：`_staged_file_sync_open_flags` 产生平台 open flags → `_sync_staged_config` 消费。无 semantic drift。

**结论**: 平台分支正确；`O_RDWR` vs `O_RDONLY|O_NOFOLLOW` 语义正确；`_validate_platform` fail-closed 正确。PASS。真实 Windows flush 待 rerun。

## MiMo-01 path-list hash 裁决复核

**裁决**: `REJECTED_AS_VERIFICATION_COMMAND_ERROR / NO_CODE_ACTION`

**直接证据**:
1. 本 reviewer 独立执行 `git diff --name-only | LC_ALL=C sort | shasum -a 256` 得到 `b9f39d74...2001`，与 Controller、DS、Codex 四方一致。
2. 同时匹配 binary diff `18876f5b...00e5`（包含路径与内容），证明无工作树漂移或漏审路径。
3. MiMo 初审报告的 `2cfef7ff...` 不是当前 canonical command 的结果。

**结论**: Controller 裁决有充分直接证据支撑。不同值来自验证命令差异，不构成 tree drift 或代码 finding。

## DS open questions 裁决复核

### DS Open Question 1: PowerShell `$LASTEXITCODE`

**裁决**: `NON_BLOCKING_EXTERNAL_VALIDATION_POINT / NO_CODE_ACTION`

**直接证据**: `r11-upload-script-windows.yml:47` 使用 `shell: pwsh`，`$LASTEXITCODE` 在 `ver` 执行后立即捕获。`r12-init-windows.yml:46` 同一结构。当前不为假想 runner 降级添加 fallback 是正确的 fail-closed 策略。

**结论**: 裁决成立。

### DS Open Question 2: Windows open-time no-follow

**裁决**: `NON_BLOCKING_EXISTING_ORDER_INVARIANT / NO_CODE_ACTION`

**直接证据**: `_sync_staged_config` 先执行 `_validate_ordinary_tree`（完整 reparse/junction/symlink 验证），再遍历 transaction-private staging，打开后用 `fstat` 验证 regular file。当前 diff 只将 Windows descriptor 从只读改为可 flush（`O_RDWR`），不改变 containment 或调用顺序。

**结论**: 裁决成立。

### DS observations: registry key existence / cross-platform flag coverage

**裁决**: `NON_BLOCKING_OBSERVATIONS / NO_CODE_ACTION`

**直接证据**: registry cleanup 以精确 value query absent + 父 key 可访问共同证明 cleanup 成功；父 key 不可访问时 fail closed。这是明确环境前提假设，不是可吞掉的错误。

**结论**: 裁决成立。

## Adversarial failure pass

对 8 个变更文件执行 adversarial 审查：

- **semantic ownership drift**: 未发现。`_staged_file_sync_open_flags` 由 owner 产生平台 open flags，`_sync_staged_config` 消费。`_PathIdentity` 由 `_path_identity` 产生，`_validate_ordinary_tree` 消费。registry cleanup 由 `_delete_registry_value_and_verify_absent` 自包含三步协议。无 fallback、特例、`hasattr/getattr`、loose parsing 或兼容 shim。
- **architecture boundary**: 未发现反向依赖或跨层穿透。`run_keys.py` 使用 `subprocess.run` 调用 `reg.exe`，不 import Windows-specific 模块。
- **concurrency / idempotency**: `_sync_staged_config` 在 transaction-private staging 内操作，`_publish_replace` 有完整 exception handler 和 `_rollback_on_publication_failure`。registry cleanup 幂等（delete 0/1 + query absent）。
- **security / secret leakage**: 错误消息只投影变量名，不回显 command output。测试断言 `"test-secret" not in message`。
- **branch ordering / dispatch**: `_staged_file_sync_open_flags` 先 `_validate_platform`（白名单），再 `==` 分支。`_validate_ordinary_tree` 的 Windows 分支在 `_PathIdentity.file_attributes` 检查后立即 fail closed。无宽条件抢先命中。
- **parameter effectiveness**: `_staged_file_sync_open_flags(platform_system)` 参数来源清晰（`WorkspaceTransactionRequest.platform_system`），经 `_validate_platform` 校验后直达消费点。

## Scope / deferred / security drift 检查

- **scope drift**: 无。变更限于 8 个文件，全部为 Windows platform support 相关。`tests/README.md` 更新记录 Windows platform constraint，属于 tests README 职责范围。
- **deferred drift**: 无。所有 deferred items（真实 Windows rerun）在 artifacts 中明确标注为 release evidence，不伪装为 code finding。
- **security drift**: 无。secret 脱敏模式一致；registry cleanup fail-closed；junction/symlink fail-closed。

## Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

- 真实 Windows R11/R12 rerun 尚未执行。F01 import/collection、F02 cmd execution、F03 registry cleanup、F04 staged flush/publication rollback 的 Windows 平台真实语义仍需 release evidence 证明。这是已知 deferred item，不是 code finding。
- macOS 上 `test_windows_real_*` 测试全部 skip，不构成 coverage gap（skip 是正确行为）。

## Final disposition

| 类别 | 数量 | 状态 |
|---|---:|---|
| accepted code finding | 0 | closed |
| rejected-with-reason | 1 | closed (MiMo-01 path-hash，有直接证据) |
| non-blocking open question/observation | 3 | owner/status 已明确 |
| needs real Windows rerun | 1 | AR-F07 release evidence；非 code finding |
| new material finding | 0 | — |

**PASS**。同一 immutable tracked tree 已通过 MiMo final re-review。
