# WU-SEMANTIC-OWNERSHIP-01 AR-F07 Windows code-review fix confirmation

## Gate result

`ZERO_CHANGE / ACCEPTED_CODE_FINDING=0 / READY_FOR_DUAL_RE_REVIEW`

本记录是既有 `WU-SEMANTIC-OWNERSHIP-01` umbrella 下 AR-F07、draft PR 179 的同一
Windows validation-fix follow-up，不创建或替代 WU。Controller 已裁决 accepted code finding
为 0；因此本轮不修改 implementation、test、workflow、README 或 control，只确认同一 immutable
tracked tree 可进入 MiMo/DS 双路 re-review。

基准 HEAD：`07db7af3855b7fc80a24d74a3214bef215752d8d`。

## Review inputs

已完整读取并按 Controller 裁决执行：

| Artifact | SHA-256 |
|---|---|
| `docs/reviews/wu-semantic-ownership-01-ar-f07-windows-code-review-mimo.md` | `2580709c48b99632f48e91db9a86a835c804b5ee732fefae495479427d6502a2` |
| `docs/reviews/wu-semantic-ownership-01-ar-f07-windows-code-review-ds.md` | `c7aa2111a5bec4dee5d8859d6aff2714ad9b3571bdbf63acef46391bc21b2dfe` |
| `docs/reviews/wu-semantic-ownership-01-ar-f07-windows-code-review-controller-adjudication.md` | `5879d308c472ff81ecade68620e657507a15339e413dd8efa225d57b631e55a1` |

Controller 结论为 `PASS / ACCEPTED_CODE_FINDING=0 / ZERO_CHANGE_FIX_GATE_REQUIRED`。

## Immutable tracked snapshot confirmation

本轮重新计算结果：

- `git diff --binary | shasum -a 256`：
  `18876f5b596a430588bdafa390d1e0cbbd19534864718fdfca9a271585dc00e5`，与冻结值一致。
- `git diff --name-only | LC_ALL=C sort | shasum -a 256`：
  `b9f39d742e80f57b427d0632e12b8e24bf731d2a502b0247a74cec4706fb2001`，与冻结值一致。
- tracked changed paths：精确 8 个，无新增、删除或重命名。
- staged paths：0。

Exact path/content hashes：

| Path | SHA-256 |
|---|---|
| `.github/workflows/r11-upload-script-windows.yml` | `0897e4152c8a878bf2203b176072558cf7d6537f855762170f0804a10c6388b2` |
| `.github/workflows/r12-init-windows.yml` | `3a14172f84a338d40f12c4cd2e056dbe6dde255168e8366ac60b6a017f438da6` |
| `dayu/cli/init_workspace.py` | `355b7af3c84151de7926fdc93f9d833a814648b46036e82cdfb58336a9c88d26` |
| `dayu/cli/run_keys.py` | `e0f9f97c17dca9dc5f4b24329b96fdd8216cea193dd020e8382582d10bf53627` |
| `tests/README.md` | `0bd909af6ee2dcf6e99a281a9fa3ebc2c398805e84289580b972ceef409fe382` |
| `tests/cli/test_init_smoke.py` | `b5a82e8b2385d909070a3429a58fe4e67bcbead1b6c737ca841e8aafc4c06ec4` |
| `tests/cli/test_init_workspace.py` | `fefdc334dd7a07b1720cb6545b1473fe3b7482270974c8975d6e8647c74cb630` |
| `tests/cli/test_run_keys.py` | `2f4c746aa8c2fb34b59bec9994dc750b51cace64b61a2f90b9d6896ee9c020e9` |

## Code-review item disposition

### MiMo path-list finding

`REJECTED_AS_VERIFICATION_COMMAND_ERROR / NO_CODE_ACTION`。

不实施原因：Controller 与 DS 使用同一 canonical 命令重新计算后，排序 path-list SHA-256
稳定为 `b9f39d742e80f57b427d0632e12b8e24bf731d2a502b0247a74cec4706fb2001`；本轮再次得到
同值且精确列出相同 8 个 tracked paths。MiMo 报告中的不同值不是 tree drift，不能据此改代码或文件范围。

### DS open question：PowerShell `$LASTEXITCODE`

`NON_BLOCKING_EXTERNAL_VALIDATION_POINT / NO_LOCAL_CODE_ACTION`。

不实施原因：R11 step 明确使用 `shell: pwsh`，pytest 后立即捕获 `$LASTEXITCODE`，非零时仍退出；
`cmd.exe /d /c ver` 是稳定成功语义的 execution gate，`cmd.exe /?` 仅保留 help artifact 并只接受已知
0/1 诊断状态。添加 fallback、忽略错误或另造 wrapper 会弱化现有 gate。真实 PowerShell/cmd 行为由 Windows rerun
关闭，不由 macOS 模拟代替。

### DS open question：Windows open-time no-follow

`NON_BLOCKING_EXISTING_ORDER_INVARIANT / NO_CODE_ACTION`。

不实施原因：`_sync_staged_config` 先验证完整 ordinary tree/reparse，再遍历 transaction-private staging，
打开后以 `fstat` 再证明 regular file；当前变化仅令 Windows 使用可执行真实 flush 的 `O_RDWR` descriptor，
POSIX 仍使用 `O_RDONLY | O_NOFOLLOW`。当前没有 containment、symlink/reparse 或调用顺序缺陷；不为假设性未来
重构增加第二套 policy 或平台 shim。

### DS observations：registry key existence / cross-platform flag coverage

`NON_BLOCKING_OBSERVATIONS / NO_CODE_ACTION`。

不实施原因：registry cleanup 以 exact value query absent 加父 key 可访问共同证明，父 key 不可访问继续
fail closed；这是明确环境前提，不是可以吞掉的错误。平台 flag contract 已由 owner 分支和现有多平台验证分工覆盖；
真实 Windows descriptor、registry 与 cmd 语义仍由同一 Windows rerun 提供 release evidence。

## Four accepted Windows finding dispositions

| Finding | Reconfirmed disposition | 本轮为何不再实施 |
|---|---|---|
| `AR-F07-WIN-F01` | 已修复；真实 Windows import/collection 待 rerun | capability/factory owner 的 POSIX 顶层条件导入与 non-POSIX no-op boundary 保持冻结哈希；owner contract 本轮复跑通过，无 accepted review finding。 |
| `AR-F07-WIN-F02` | 已修复；真实 cmd execution gate 待 rerun | workflow 已用 `cmd.exe /d /c ver` 强校验 exit 0，help 仅分类 0/1，pytest/cmd 真实错误仍 fail closed；YAML 本轮解析通过，无理由改弱 gate。 |
| `AR-F07-WIN-F03` | 已修复；真实 registry round-trip/cleanup 待 rerun | exact-name cleanup 的 deleted/already-absent 与 unproved-absence owner matrix 本轮复跑通过，错误不暴露 secret 明文；真实 registry 证明仍需 Windows。 |
| `AR-F07-WIN-F04` | 已修复；真实 Windows flush/publication rollback 待 rerun | transaction owner 的平台 open flags 与 atomic publication/rollback contract 保持冻结哈希；publication replace rollback owner test 本轮复跑通过。 |

## Lightweight validation

在 macOS、Python 3.11 venv 执行：

| Command | Result |
|---|---|
| `pytest tests/cli/test_run_keys.py tests/cli/test_init_smoke.py::test_registry_cleanup_accepts_deleted_or_already_absent_value tests/cli/test_init_smoke.py::test_registry_cleanup_rejects_unproved_absence_without_command_output tests/cli/test_init_workspace.py::test_publication_replace_failure_rolls_back_original_config -q` | `14 passed, 3 existing edgar deprecation warnings` |
| Ruby `YAML.safe_load` 两份 R11/R12 workflow | 两份均 parsed |
| `git diff --check` | pass |
| `git diff --cached --name-only` | empty |

本轮未重复 full pyright、full CLI 或单文件覆盖率，因为 immutable binary diff 与 8 个内容哈希均未变化；
Controller 已在同一 snapshot 记录 full pyright `0 errors`、focused suite `190 passed, 7 skipped`、scoped Ruff
通过，AgentCodex implementation artifact 已记录 full CLI `513 passed, 7 skipped` 和两份单文件覆盖率达标。

macOS 上不可执行的 Windows-only nodes 未被记作 pass，也未通过 shim 模拟。

## Changed paths and prohibited actions

本次 follow-up 只新增本 artifact：

- `docs/reviews/wu-semantic-ownership-01-ar-f07-windows-code-review-fix-codex.md`

未修改 implementation、test、workflow、README、control 或既有 review artifact；未 stage、commit、push、修改
PR 或触发 workflow。

## Residual and next gate

本地 code-review fix gate 为 ZERO_CHANGE，现有 immutable tracked tree 已 ready for MiMo/DS dual re-review。
AR-F07 仍不能由本地 macOS 结果关闭；最终必须由两条真实 Windows rerun 证明 F01 import/collection、F02 cmd
execution、F03 registry cleanup、F04 staged flush/publication rollback，并上传完整 artifacts。真实 runner 结果是 release
evidence，不是当前 accepted code finding。
