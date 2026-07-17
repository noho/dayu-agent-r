# WU-SEMANTIC-OWNERSHIP-01 / R11-I1 Controller checkpoint validation

## 1. 裁决

`PASS / READY_FOR_R11_I2_PACKAGING_IMPLEMENTATION`。

R11-I1 已完成 accepted plan 规定的 atomic Fins typed producer + CLI typed consumer/renderer/publisher cutover。该结论只是 R11 内部 checkpoint，不是 slice acceptance、独立 sub-WU、accepted commit、R11 completion 或 umbrella completion。R11-I1 dirty tree 必须原样保留并继续叠加 R11-I2；最终仍须对完整 R11 cumulative tree 执行双路 code review、finding fix、re-review、aggregate deepreview 与一个 accepted local commit。

## 2. 输入锁与范围

- HEAD：`a527ec030215e5bfcf9c4fad2f4a6fda243f5d65`。
- accepted plan：`docs/host/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan.md`，SHA-256 `55d35256f0f89f39f722438dc19d9ae65269b16810f96f1cd0129c6eba06d427`。
- live authorization：`docs/reviews/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-i1-controller-authorization.md`，SHA-256 `9af48935ae42472a212d3b6727347625d2be5018204490653c07a6eefbfbd26d`。
- AgentCodex evidence：`docs/reviews/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-i1-implementation-codex.md`，SHA-256 `2f8847dd5198c882045db01564c08cca1910cd8a5037f2f161f06dc749731c39`。
- read-only FMP sentinel：`tests/fins/test_fmp_company_info_resolver.py`，SHA-256 仍为 `3530bcf11d604f651c7770cafaa4cd61fa493158894ad1aef239e8e0a2baa455`。

Controller 独立检查 `git status --porcelain=v1`：恰有八个 authorized code/test paths、一个新增 renderer、Controller control/authorization 与 Agent implementation artifact，共 11 个路径；unexpected/missing 均为空。staged set 为空，`git diff --check HEAD` 通过。I2 packaging/CI/deletion/test/README 路径尚无 diff；Service/Host/Engine/runtime/config/tool/UI/design/deferred-owner 路径无 R11-I1 diff。

## 3. 独立功能、覆盖率与静态验证

Controller 在当前 dirty tree 重新执行：

```bash
source .venv/bin/activate
pytest tests/fins/test_upload_batch.py \
  tests/cli/test_upload_filings_from_command.py \
  tests/cli/test_fins_commands.py \
  tests/cli/test_arg_parsing.py \
  tests/cli/test_public_package_entrypoints.py \
  tests/fins/test_fmp_company_info_resolver.py -q
```

结果：`163 passed, 2 skipped, 3 warnings in 13.84s`。两项 skip 是 macOS 缺少真实 `cmd.exe` 的计划内 Windows-only nodes；真实 Windows release gate 必须由 R11-I2 workflow 承接，不能在本 checkpoint 标 closed。

Controller 重新生成 `workspace/tmp/r11-controller-i1-coverage.json`，coverage suite 为 `155 passed, 2 skipped`，四个 changed production owners 的 line coverage 为：

| path | coverage |
|---|---:|
| `dayu/fins/upload_batch.py` | 95.25% |
| `dayu/cli/commands/fins.py` | 90.04% |
| `dayu/cli/arg_parsing.py` | 99.66% |
| `dayu/cli/upload_script.py` | 91.37% |

静态验证：

- `python -m pyright dayu/ tests/ utils/`：`0 errors, 0 warnings, 0 informations`；
- authorized Python paths scoped Ruff：`All checks passed!`；
- full Ruff：baseline/current 均为 144，current-only `0`、resolved `0`；baseline SHA-256 仍为 `051bd6cc84fcd32adbd792c81c9e524438dd0532a92c7504ea2edf8234ec1cea`；
- legacy JSON argv/schema owner、renderer reclassification、`list2cmdline`、`shell=True`、delayed-expansion enable、type-ignore/noqa/`hasattr`/`getattr` 等禁止项均无命中；`setlocal DisableDelayedExpansion` 在 production/test 各有预期正向命中；
- POSIX/Windows generated artifact secret scans无 `FMP_API_KEY`、sentinel secret、provider URL 或 `--infer` 泄漏；
- `git diff --check HEAD`、staged-empty、deferred-owner no-diff、README no-diff gates均通过。

## 4. 全量测试中两项 Service 失败的归因

AgentCodex 报告的 related/full test 两项失败由 Controller 独立复现：

1. `tests/service/test_host_admin.py::test_prepare_host_admin_loads_only_host_runtime_without_models_or_secrets` 因 fixture 缺 required `wait_poller_policy` 失败；
2. `tests/service/test_import_boundary.py::test_service_does_not_import_forbidden_layers` 命中三个既有 Service -> Fins import。

Controller 对六个直接相关文件同时比较 working-tree blob 与 `HEAD:<path>` blob：

- `dayu/service/fins_direct.py`
- `dayu/service/fins_wait_adapter.py`
- `dayu/service/host_assembly.py`
- `dayu/runtime/config_loader.py`
- `tests/service/test_host_admin.py`
- `tests/service/test_import_boundary.py`

六组 blob id 逐一相等，且 `git diff --exit-code HEAD -- dayu/service dayu/runtime/config_loader.py tests/service` 为零。因此这两项是 HEAD 已存在、与 R11-I1 八路径没有数据/逻辑同源关系的 Service baseline failure。裁决为：

- 不把它们归因于 R11-I1；
- 不扩张 R11-I1/R11-I2 allowlist；
- 不通过 fixture shim、import allowlist 放宽或下游兼容代码掩盖；
- 保留为既有 owner 风险，不阻止本计划内 R11-I2，但 R11 final evidence 必须继续如实报告 full-suite 状态。

## 5. finding ledger 与安全边界

- current accepted I1 validation finding：`0`；
- blocker：`0`；
- plan-deferred R11-I2 closure：placeholder package/public scripts/README/wheel/Windows real `cmd.exe` evidence；
- pre-existing non-R11 baseline：上述两项 Service tests；未修复、未豁免、未冒充 green。

本 slice 保留 output containment、symlink 防护、atomic publish/rollback、POSIX strict mode、Windows delayed-expansion disable、参数 quoting、secret non-persistence 与 FMP explicit opt-in。没有设计或实现统一 tool authorization framework，没有实施 Issue 142/151/175/177/178，也没有实现 Web/WeChat/render tracker 能力。

## 6. 下一 gate

仅授权 `R11-I2 packaging/README/Windows gate implementation`，精确路径和 stop conditions 由独立 Controller authorization 固定。I2 完成并通过 Controller checkpoint 后，必须对 I1+I2 完整 cumulative diff 并发执行 AgentMiMo / AgentDS code review；在此之前不得 stage、commit、进入 R12、push 或创建 PR。

READY_FOR_R11_I2_PACKAGING_IMPLEMENTATION
