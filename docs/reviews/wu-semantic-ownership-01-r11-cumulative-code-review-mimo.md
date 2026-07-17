# Code Review

## Scope

- Mode: current changes
- Branch: `phaseflow/host-issues-control`
- Base: HEAD `7972c3c0ba8628173fc91c362b9394655f60678e`
- Output file: `docs/reviews/wu-semantic-ownership-01-r11-cumulative-code-review-mimo.md`
- Included scope: 22 unique product/test/README/packaging/workflow paths — I1 8 + I2 15 + shared 1；tracked diff 加 untracked `.github/workflows/r11-upload-script-windows.yml` 与 `dayu/cli/upload_script.py`；binary diff lock `6c8284c6fdcfc4661a0bcd00f1c155d34985fa4af81fa400158ce3a034acd0e6`，staged empty
- Excluded scope: Controller control/authorization artifacts (untracked，不在 product allowlist)；`workspace/tmp/`；`dayu/service/**`、`dayu/host/**`、`dayu/engine/**`、`dayu/runtime/**`、constraints、design docs
- Parallel review coverage: 无（单 reviewer 完整覆盖）

## Findings

**未发现实质性 correctness、stability 或 maintainability defect。**

完整走读 22 个 changed files、所有关键调用者/消费者、reference docs 和 tests 后，以下关键路径均未发现可由直接代码证据支撑的 material finding：

1. **Fins typed OLD 分类 owner** (`upload_batch.py`): 唯一拥有财期推断（`_infer_fiscal_fields` / `_infer_period_from_filename`）、material routing/name（`_match_material_form` / `_derive_material_name`）、同期优先级/去重（`_deduplicate_filings` / `_filing_priority`）、caps（`_apply_filing_caps` annual=5/periodic latest-year+max6, `_apply_material_caps` presentation=6/call=count(filtered)/financial=∞）和 skip reason。CLI 零业务推断，只机械消费 typed plan。tests 断言 owner contract 而非偶然 fixture（Q4 filename/parent oracles、explicit override precedence、priority tie、caps、skip reason codes）。
2. **CLI direct argv builder** (`fins.py:_upload_batch_command_argv`): entry type 唯一决定 `upload_filing`/`upload_material`；canonical+aliases 合为单一 `--ticker` CSV；`auto` 省略 `--action`；optional typed facts 无值不产生 flag；overwrite 只传播到每条 direct upload，不影响 publisher replacement。
3. **FMP-once** (`fins.py:_run_upload_filings_from`): `--infer` 未传时零 resolver/env 访问；传入时读 `FMP_API_KEY`、构造 `FmpCompanyInfoResolver`、调一次 `resolve_company_info`、验证 canonical ticker match、一次性合并显式 aliases 与 resolver aliases。secret/provider URL/推断结果不进入 executable body（只在 regeneration comment 中保留无 secret 的 `--infer` flag）。
4. **POSIX renderer** (`upload_script.py:_render_posix_script`): `shlex.join` + `"$@"`，header `#!/usr/bin/env sh` / `set -eu`。真实 `/bin/sh` adversarial round-trip 测试覆盖空格、中文、单/双引号、尾反斜杠、`$(touch marker)`、`& | ^ ( ) < > %PATH% !`。
5. **Windows renderer** (`upload_script.py:_render_windows_script`): `setlocal DisableDelayedExpansion`（不 re-enable）、自有 batch-percent + CRT quoting（`_quote_windows_batch_argument`）、`%*` passthrough、`REM` comment escape。无 `list2cmdline`、`shell=True` 或 delayed expansion。unit oracle 逐参数验证 CRT round-trip；adversarial matrix 覆盖 `%PATH%`、`!`、`&`。
6. **Publisher** (`upload_script.py:publish_upload_script`): lexical/resolved containment、workspace root-self symlink rejected、internal component/target symlink rejected、external-ancestor symlink allowed、same-directory `tempfile.mkstemp` + `flush` + `fsync` + `os.replace`、POSIX `chmod 0o755`、old-target preservation on failure/KeyboardInterrupt、temp cleanup。
7. **Placeholder closure**: 六文件 working-tree absence + tracked deletion diff；`pyproject.toml` 只保留 `dayu-cli`；`requirements.txt` 无 `[web]` extra 消费；wheel archive/METADATA/entrypoints/RECORD zero placeholder paths；fresh venv constrained install + `pip check` + help + importability。
8. **README contract**: 四份 README 各自遵守 owner/trigger 约束。root README contract test 正向断言 batch-only `--infer`、`FMP_API_KEY`、`.sh`/`.cmd`、`/bin/sh`/`cmd.exe /d /c`；负向断言无 JSON argv `schema_version=1`/`commands`/`"不生成 shell"`。
9. **Tests owner assertions**: `test_upload_batch.py` 断言 typed 三分、Q4 filename/parent oracles、explicit override、priority/stable-path tie、caps、skip reason codes、reverse-import boundary。`test_upload_filings_from_command.py` 断言 POSIX/Windows quoting round-trip、containment/symlink、publisher atomic replace、real `/bin/sh` recorder + real CLI→Service→Fins→temp-storage smoke。
10. **Security**: secret non-persistence（`rg` scan zero hit）、injection marker absence、containment/symlink/atomic write 全部由 focused + real smoke 覆盖。`DisableDelayedExpansion` 正向 oracle。
11. **Deferred boundaries**: Issue 142/151/175/177/178、R12、真实 Web/WeChat/render、Topic 8/9 code、统一 auth 无 production diff。Service/Host/Engine/runtime/config/tool/UI/constraints/design diff 为零。
12. **Repository baseline**: 两项 Service failure（`test_prepare_host_admin_loads_only_host_runtime_without_models_or_secrets` 缺 `wait_poller_policy` fixture、`test_service_does_not_import_forbidden_layers` 命中既有 Service→Fins imports）是 HEAD-existing，六个直接 owner/test files working blobs 等于 HEAD，不归因于 R11。

## Open Questions

- **真实 Windows `cmd.exe` 运行**: PENDING_RELEASE_BLOCKER。本地 macOS 环境下两个 Windows-only nodes（`test_windows_cmd_script_round_trips_adversarial_argv_with_real_cmd`、`test_windows_generated_script_runs_real_cli_into_temp_storage`）明确 skip。真实 `windows-latest` run 必须在后续获授权发布后成功。

## Residual Risk

- **Windows release gate**: 真实 GitHub `windows-latest` / `cmd.exe` 尚未运行。本地 Windows quoting unit oracle 和 macOS skip 不能替代真实 runner 证据。这是 plan §7.2 明确的 `PENDING_RELEASE_BLOCKER`，不因 local skip 关闭。
- **Controller validation 的两项 Service baseline failure**: `test_prepare_host_admin_loads_only_host_runtime_without_models_or_secrets` 缺 `wait_poller_policy` fixture；`test_service_does_not_import_forbidden_layers` 命中三个既有 Service→Fins imports。两者均超出 R11 allowlist，不在本 review 修复 scope。
- **Coverage**: 四个 changed production Python files 全部 `>=80%`（90.04%—99.66%）。

## Verdict

**PASS — 未发现实质性 correctness/stability/maintainability defect。**

22-path immutable cumulative implementation tree 在 Fins typed owner contract、CLI mechanical consumer、POSIX/Windows quoting、containment/symlink/atomic write、placeholder closure、wheel metadata、README contract、tests owner assertions、security gates 和 deferred boundaries 上均通过 evidence-based review。
