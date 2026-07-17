# WU-SEMANTIC-OWNERSHIP-01 / R11 cumulative re-review — AgentMiMo

## 1. Scope 与输入

- Mode: cumulative re-review after R11-DS-F02/F03 fix
- Branch: `phaseflow/host-issues-control`
- HEAD: `7972c3c0ba8628173fc91c362b9394655f60678e`
- Staged: empty
- Binary diff lock: `6065289ee2a2da8d475de29fcd8b5d719ca1f0448e357e885a5ac0156fb6f424`
- Tracked diff: 20 paths（M×13 + D×6）+ untracked new: 2 paths（`dayu/cli/upload_script.py`、`.github/workflows/r11-upload-script-windows.yml`）= cumulative 22 unique paths
- Accepted plan: `docs/host/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan.md`
- Controller adjudication: `docs/reviews/wu-semantic-ownership-01-r11-cumulative-code-review-controller-adjudication.md`
- AgentCodex fix evidence: `docs/reviews/wu-semantic-ownership-01-r11-cumulative-code-review-fix-codex.md`
- Controller validation: `docs/reviews/wu-semantic-ownership-01-r11-cumulative-code-review-fix-controller-validation.md`
- AgentDS initial review: `docs/reviews/wu-semantic-ownership-01-r11-cumulative-code-review-ds.md`
- AgentMiMo initial review: `docs/reviews/wu-semantic-ownership-01-r11-cumulative-code-review-mimo.md`

完整读取全部 22 文件的 working tree 内容，重点验证 R11-DS-F02/F03 fix closure、R11-DS-F01 boundary、CLI/Fins 唯一语义 owner、Windows evidence、argv quoting/secret/containment/atomic publish、placeholder 删除、README/packaging、deferred Issue/Topic 未越界、以及组合行为/回归。

## 2. Finding closure 复核

### 2.1 R11-DS-F01 — REJECTED / NO FIX / boundary preserved

Controller 裁决拒绝。复核确认：

- `dayu/runtime/**` diff 为零。
- `dayu/fins/upload_batch.py` 的 `_lexical_absolute`（line 866）、`_has_internal_symlink`（line 877）、`_is_within`（line 895）与 `dayu/cli/upload_script.py` 的同名函数（lines 312/323/341）继续各自独立存在。
- 两组函数分别服务 Fins source containment policy 与 CLI output publication containment policy，逻辑等价但 owner 分离。
- 无新增 shared helper、runtime module、alias、wrapper 或 fallback。

**Status: CLOSED / boundary preserved**

### 2.2 R11-DS-F02 — FIXED / closed

Root-cause fix 复核：

- `UploadBatchPlanRequest.material_form`（`upload_batch.py:214`）类型为 `str | None`，诚实表达尚未验证的候选。
- `_single_batch_material_form`（`fins.py:1166-1181`）仅做单值检查、trim、uppercase normalization（`normalized[0].upper()`），不再包含 `FINANCIAL_STATEMENTS` / `EARNINGS_CALL` / `EARNINGS_PRESENTATION` 硬编码副本。
- `_validated_material_form`（`upload_batch.py:817-832`）使用 `_MATERIAL_FORM_TYPES`（由 `_MATERIAL_ROUTING_TABLE` line 100-109 自动派生的 frozenset）做唯一值域验证。
- CLI source scan：`rg 'FINANCIAL_STATEMENTS|EARNINGS_CALL|EARNINGS_PRESENTATION' dayu/cli/commands/fins.py` 为 exit 1 / zero output。
- Owner test `test_invalid_material_form_is_rejected_by_fins_owner`（`test_upload_batch.py:176`）直接向 Fins request 传入 `ESG_REPORT`，断言 `UploadBatchPlanUsageError("unsupported material form: ESG_REPORT")`。
- CLI propagation test `test_material_form_candidate_reaches_fins_owner_and_maps_usage_exit`（`test_upload_filings_from_command.py:180`）断言 CLI 将 ` esg_report ` 传播为 `"ESG_REPORT"`，Fins owner 拒绝后 CLI 返回 `EXIT_USAGE_ERROR`，workspace/script 均未产生。

**Status: CLOSED**

### 2.3 R11-DS-F03 — FIXED / closed（local evidence）

Root-cause fix 复核：

- 两个 Windows-only tests（`test_windows_cmd_script_round_trips_adversarial_argv_with_real_cmd`、`test_windows_generated_script_runs_real_cli_into_temp_storage`）使用 `_windows_test_artifact_directory`（`test_upload_filings_from_command.py:63-89`），当 `DAYU_R11_WINDOWS_ARTIFACT_DIR` 存在时写入确定性 `cmd-recorder/` 与 `cli-storage/` 子目录。
- Workflow（`r11-upload-script-windows.yml:83-123`）从 `$env:DAYU_R11_WINDOWS_ARTIFACT_DIR\cmd-recorder` 和 `\cli-storage` 读取精确文件路径，不再使用 `Get-ChildItem -Recurse $env:TEMP`、generic `-Filter` 或 `Copy-Item`。
- Workflow 校验四个 exact files、recorder 单行 oracle、CLI oracle 字段、generated script hash 与 exact portfolio artifact count。
- `%TEMP%|Get-ChildItem.*-Filter|Copy-Item` 对 workflow：zero output（本地 YAML audit）。

**Status: CLOSED / 真实 Windows `cmd.exe` run 仍为 PENDING_RELEASE_BLOCKER**

## 3. Semantic owner 复核

### 3.1 Fins 唯一产生分类/财期/material/skip facts

- `generate_upload_batch_plan`（`upload_batch.py:272`）是唯一入口。
- `_validated_material_form`（line 817）使用 `_MATERIAL_FORM_TYPES`（line 107）做值域验证。
- `_infer_fiscal_fields`（line 467）、`_match_material_form`（line 518）、`_apply_filing_caps`（line 689）、`_apply_material_caps`（line 733）、`_deduplicate_filings`（line 630）全部在 Fins 内闭合。
- Fins 零 CLI/Service/Host/Engine/UI import（`test_upload_batch_module_has_no_reverse_layer_imports` 通过）。

### 3.2 CLI 只消费 typed plan 并机械投影

- `_upload_batch_command_argv`（`fins.py:376`）对 `UploadBatchFilingEntry` / `UploadBatchMaterialEntry` 纯机械投影为 `tuple[str, ...]`。
- `_append_optional_entry_metadata`（line 414）只检查 entry 字段是否为 `None`/`True`，零业务推断。
- CLI 零 filename regex、零 fiscal/material classifier（`test_cli_fins_command_has_no_host_engine_or_storage_imports` 通过）。
- `_single_batch_material_form`（line 1166）不再拥有业务值域副本。

### 3.3 Renderer/publisher 零业务推断

- `render_upload_script`（`upload_script.py:70`）只消费 `tuple[tuple[str, ...], ...]`。
- `_quote_windows_batch_argument`（line 198）纯 quoting 算法。
- `publish_upload_script`（line 98）执行 containment/symlink/atomic replace。
- renderer 零 filename regex/fiscal/material classifier。

## 4. Windows evidence 复核

- Workflow `pull_request.paths` 为 exact 22 paths，无 missing/extra/duplicate。
- Workflow 使用 `DAYU_R11_WINDOWS_ARTIFACT_DIR` 作为唯一证据发布目录。
- Tests 使用 `_windows_test_artifact_directory` 在显式 artifact root 存在时发布确定性 evidence。
- 本地 macOS skip 行为不变；真实 `cmd.exe /d /c` round-trip 尚未发生。
- 状态：**PENDING_RELEASE_BLOCKER** — GitHub Actions 真实 run 通过前不关闭。

## 5. argv quoting / secret / containment / atomic publish 复核

- POSIX renderer：`shlex.join` + `"$@"`；真实 `/bin/sh` adversarial recorder 通过。
- Windows renderer：`_quote_windows_batch_argument`（batch percent + CRT quoting）、`setlocal DisableDelayedExpansion`；`%*` passthrough。
- `list2cmdline`、`shell=True`、`setlocal EnableDelayedExpansion` scan：exit 1 / zero output。
- Publisher：same-directory temp + flush/fsync + `os.replace` + old-target preservation + temp cleanup + POSIX `chmod 0o755`。
- Containment：`_lexical_absolute`、`_has_internal_symlink`、`_is_within` 在 Fins 和 publisher 各自执行。
- Secret scan（FMP_API_KEY / sentinel / provider URL）对 generated script body 和 regeneration comment：exit 1 / zero output。
- POSIX real upload smoke 的 executable body 零 `--infer`/secret/URL。

## 6. Placeholder 删除复核

- 六个 placeholder package 文件 working-tree absent：`dayu/web/__init__.py`、`dayu/web/__main__.py`、`dayu/wechat/__init__.py`、`dayu/wechat/main.py`、`dayu/render/__init__.py`、`dayu/render/render.py`。
- `git ls-files dayu/web dayu/wechat dayu/render` 精确列出 index 中的六个删除项。
- `pyproject.toml` `[project.scripts]` 只有 `dayu-cli`；无 `dayu-web`/`dayu-wechat`/`dayu-render`。
- `pyproject.toml` 无 `web` optional dependency、无 `dayu.render` package-data mapping。
- `requirements.txt` 无 `[web]` extra 消费。
- `test_pyproject_publishes_only_real_console_scripts` 和 `test_wheel_excludes_placeholder_scripts_metadata_and_packages` 通过。
- 两个只读 Web tool negative import-boundary sentinel 各精确命中一次且文件无 diff。

## 7. README / packaging 复核

- 根 README 覆盖 batch `upload_filings_from`、`--infer` + `FMP_API_KEY`、`.sh`/`.cmd` default、`/bin/sh` / `cmd.exe /d /c` 执行、`--action auto`、summary、追加参数、排障。
- `dayu/README.md` 只列真实 package，无 placeholder 稳定边界承诺。
- `dayu/fins/README.md` 说明 typed scan/classification owner、OLD rules/caps/skip contract。
- `tests/README.md` 记录真实 Windows gate workflow、真实 smoke commands。
- README diff 精确为 root / `dayu/` / Fins / tests 四份。

## 8. Deferred Issue / Topic 未越界复核

- Issue 142/151/175/177/178、R12、真实 Web/WeChat/render、Topic 8/9、unified auth 的 production diff 为零。
- `git diff --name-only 2b14b2fbc89654267e3d33daa2ae410ceff45e68 -- dayu/service dayu/host dayu/engine dayu/runtime dayu/config dayu/tool dayu/ui constraints docs/host/design.md docs/engine/design.md docs/tool/design.md docs/fins/design.md docs/ui/design.md`：empty output。
- 只允许 README 删除 placeholder 与 plan 明确 no-touch 说明。

## 9. 组合行为 / 回归复核

- Focused cumulative：155 passed, 2 skipped, 3 warnings
- Related：2 failed, 1470 passed, 3 skipped, 3 warnings
- Full：2 failed, 5056 passed, 5 skipped, 5 deselected, 3 warnings
- 两项 allowed existing failures 精确为：
  1. `test_prepare_host_admin_loads_only_host_runtime_without_models_or_secrets`
  2. `test_service_does_not_import_forbidden_layers`
- 无第三项/new R11 failure。
- 三项 POSIX real smokes（filesystem / recorder / real upload）全部 PASS。
- Fresh exact-wheel constrained normal install + pip check + help + importability + archive gates：PASS。
- Per-file coverage（95.57% / 90.87% / 99.66% / 91.37%）均 ≥80%。
- Full pyright：0 errors。
- Ruff version `0.15.11` 精确匹配；full baseline current-only=0。
- `git diff --check`：PASS。
- Staged manifest：empty。

## 10. Material findings

**0**

本 re-review 未发现新的 material findings。R11-DS-F02/F03 的 fix 实现正确、边界清晰、测试覆盖充分。

## 11. Historical finding closure

| Finding | Status | Evidence |
|---|---|---|
| R11-DS-F01 | REJECTED / NO FIX / boundary preserved | Controller adjudication §2.1；`dayu.runtime` diff zero；Fins/publisher independent containment helpers unchanged |
| R11-DS-F02 | CLOSED / FIXED | `_single_batch_material_form` no hardcoded values；Fins `_validated_material_form` sole value-domain owner；CLI propagation test + Fins owner invalid-value test pass |
| R11-DS-F03 | CLOSED / FIXED（local evidence） | Deterministic artifact locator in tests/workflow；no `%TEMP%` recursive search；real `cmd.exe` run still PENDING_RELEASE_BLOCKER |

## 12. Blocking questions

1. **Windows release blocker**：真实 GitHub `windows-latest` / `cmd.exe` recorder + CLI storage run 未发生。本地 skip、YAML parse、renderer unit evidence 不能关闭此 gate。首次 run 需要 GitHub-hosted runner 执行 workflow。

2. **两项 HEAD-existing Service baseline failures**：`test_prepare_host_admin_loads_only_host_runtime_without_models_or_secrets` 与 `test_service_does_not_import_forbidden_layers` 是 repository baseline，不属于 R11 owner scope。任何声称 full suite green 的 gate 需显式处理这两项 expected failure。

## 13. Final verdict

**PASS — 0 accepted open implementation finding / 0 new blocker**

- R11-DS-F02、R11-DS-F03 已修复并由本次 re-review 确认关闭。
- R11-DS-F01 保持 REJECTED/NO FIX，Controller 裁决边界不变。
- 真实 Windows `cmd.exe` run 仍为 **PENDING_RELEASE_BLOCKER**，本地 evidence 不能关闭。
- R11 accepted implementation commit、R12、stage/commit、push 与 PR 仍未授权；下一入口为 Controller 最终 aggregate 裁决。
