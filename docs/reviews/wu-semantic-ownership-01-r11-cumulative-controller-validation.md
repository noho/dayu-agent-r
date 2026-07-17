# WU-SEMANTIC-OWNERSHIP-01 / R11 cumulative Controller validation

## 1. Validation target

- umbrella internal remediation sub-WU：`R11 upload script / placeholder removal`
- accepted plan：`docs/host/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan.md`
- accepted plan HEAD：`7972c3c0ba8628173fc91c362b9394655f60678e`
- final implementation tree：I1 `8` paths + I2 `15` paths，one shared path，`22` unique product/test/README/packaging/workflow paths
- AgentCodex evidence：`docs/reviews/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-i2-implementation-codex.md`，268 lines / 18,421 bytes / SHA-256 `57fb654d2f484da7e72340eadfba6f8edab37b8aefb90cb784a7dae7667aa3ba`
- stopped product binary diff SHA-256：`6c8284c6fdcfc4661a0bcd00f1c155d34985fa4af81fa400158ce3a034acd0e6`

本验证只决定 immutable cumulative tree 是否可进入双路完整 code review；不接受实现、不授权 stage/commit、R12、push 或 PR。

## 2. Scope / owner / lock validation

Controller 完整读取 AgentCodex evidence，并独立核对：

- branch 与 HEAD匹配；staged set empty；
- exact allocation为 I1 `8`、I2 `15`、shared `1`、union `22`；
- 两个 authorized untracked product additions是 `.github/workflows/r11-upload-script-windows.yml` 与 `dayu/cli/upload_script.py`；
- six placeholder files在 working tree absent且 tracked diff为 deletion；
- seven non-shared I1 hashes、shared test、workflow、tests README与 FMP sentinel均匹配 authorization；
- shared `tests/cli/test_arg_parsing.py` 的 I2 delta只属于 `test_root_readme_matches_current_cli_public_contract`；
- product/test/README/packaging/workflow binary diff在 validation前后均保持 `6c8284c6...d0e6`；
- Service/Host/Engine/runtime/config/tool/UI/constraints/design owner无 R11 diff；
- Controller control、accepted plan与既有 artifacts未被 AgentCodex覆盖。

## 3. Independent Controller validation

### 3.1 Focused tests、coverage、static checks

Controller 在 activated `.venv` 独立执行 accepted plan command：

| Gate | Result |
|---|---|
| Ruff version | `ruff 0.15.11` |
| focused I1+I2/public packaging/FMP | `153 passed, 2 skipped, 3 warnings in 13.21s` |
| from-zero coverage tests | `145 passed, 2 skipped, 3 warnings in 13.91s` |
| `dayu/fins/upload_batch.py` | `95.2532%` |
| `dayu/cli/commands/fins.py` | `90.0442%` |
| `dayu/cli/arg_parsing.py` | `99.6599%` |
| `dayu/cli/upload_script.py` | `91.3669%` |
| full pyright | `0 errors, 0 warnings, 0 informations` |
| scoped Ruff | `All checks passed!` |
| `git diff --check HEAD` | PASS |
| staged set | empty |

四个 changed production Python whole-file coverage均 `>=80.00%`。

### 3.2 Independent fresh wheel runtime gate

Controller 使用独立的 `workspace/tmp/r11-controller-*` directories重新执行：

1. `pip wheel --no-deps --no-build-isolation` build exact-one wheel；
2. fresh venv只对 exact built wheel执行一次以 `constraints/lock-macos-arm64-py311.txt` 约束的 normal install；
3. `pip check` 返回 `No broken requirements found.`；
4. 顶层 CLI help与 `upload_filings_from --help` 均 exit 0；
5. `dayu.web`、`dayu.wechat`、`dayu.render` importability全部 absent；
6. archive `METADATA` / entrypoints / extracted paths / `RECORD` placeholder oracles全部为零。

该独立 gate未使用 runtime `--no-deps`、重复 install、lazy import、fallback、fixture/sys.path shim或 lock/workflow修改。

### 3.3 Agent full validation复核

AgentCodex 的 related/full结果为：

- related：`2 failed, 1468 passed, 3 skipped`；
- full：`2 failed, 5054 passed, 5 skipped, 5 deselected`；
- failures只包括 `test_prepare_host_admin_loads_only_host_runtime_without_models_or_secrets` 与 `test_service_does_not_import_forbidden_layers`；
- 六个直接 Service/runtime/test owner files working blobs逐一等于 HEAD；没有第三项或 R11-scoped failure；
- three POSIX real smokes PASS；local Windows matrix `1 passed, 2 skipped`，two skips仅因 macOS无真实 `cmd.exe`。

Controller 接受其分类为既有非 R11 baseline，但不把 repository suite宣称为全绿，也不关闭真实 Windows release gate。

## 4. README / security / deferred decisions

- 四份 README变更都命中并遵守各自 owner / trigger；root README current contract同时覆盖 batch-only `--infer`、FMP配置、`.sh` / `.cmd` executable workflow和旧 JSON argv协议删除。
- filesystem containment、symlink checks、atomic same-directory replace/rollback、argv quoting/injection防护与 secret non-persistence保留。
- six placeholder packages/scripts/grammar/unavailable文案已删除；真实 Web/WeChat/render能力仍由既有 tracker承接。
- Issue 142/151/175/177/178、Topic 8/9 code、统一 tool authorization、workspace trust、shell sandbox均未实现。
- 本 WU 没有删除现有 Web防御策略、path containment、DNS/peer/resource budget或其它既有局部安全机制。

## 5. Residual / release gate

- accepted/open local implementation finding before review：`0`；
- unclassified local residual：`0`；
- repository baseline：两项 existing Service failures，owner不在 R11；
- Windows：`PENDING_RELEASE_BLOCKER`。真实 GitHub-hosted `windows-latest` / `cmd.exe` run尚未发生，不能由 macOS skip或local renderer tests替代。

## 6. Verdict

**PASS / READY_FOR_DUAL_COMPLETE_IMMUTABLE_CUMULATIVE_CODE_REVIEW**

review target必须保持 immutable：22-path implementation tree、AgentCodex evidence、Controller validation、stopped diff lock与staged-empty均不得变化。Reviewer verdict不独立授权修复、stage、commit、R12、push或 PR。
