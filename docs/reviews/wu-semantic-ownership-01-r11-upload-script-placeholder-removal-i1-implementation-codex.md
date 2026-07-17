# WU-SEMANTIC-OWNERSHIP-01 / R11-I1 atomic implementation evidence

## 1. 输入锁与执行边界

- 实现基线：`a527ec030215e5bfcf9c4fad2f4a6fda243f5d65`。
- accepted plan：`docs/host/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan.md`，889 lines，SHA-256 `55d35256f0f89f39f722438dc19d9ae65269b16810f96f1cd0129c6eba06d427`。
- 唯一 live authorization：`docs/reviews/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-i1-controller-authorization.md`，139 lines / 10,524 bytes，SHA-256 `9af48935ae42472a212d3b6727347625d2be5018204490653c07a6eefbfbd26d`。
- Controller-owned live truth `docs/host/issues-implementation-control.md` 与 authorization 的 modified/untracked 状态均保留；未修改、覆盖、删除或 stage。
- 未 stage、commit、push、创建 PR；未进入 R11-I2；未修改 README、packaging、CI、placeholder/deferred/design 路径。

R11-I1 实现路径精确为：

1. `dayu/fins/upload_batch.py`
2. `tests/fins/test_upload_batch.py`
3. `dayu/cli/upload_script.py`
4. `dayu/cli/arg_parsing.py`
5. `dayu/cli/commands/fins.py`
6. `tests/cli/test_upload_filings_from_command.py`
7. `tests/cli/test_fins_commands.py`
8. `tests/cli/test_arg_parsing.py`

本文件是唯一 AgentCodex 自有 artifact。

## 2. 实现结果

### 2.1 WP-A：Fins typed semantic owner

`dayu.fins.upload_batch` 现在直接拥有 immutable typed request、filing/material/skipped entry 与 plan；发现、suffix、递归、containment、symlink、OLD filename/parent semantics、material routing/name、优先级、去重、caps、skip reason 与 empty-plan evidence 全部在 Fins boundary 完成。CLI 不再读取 generic JSON schema 或从 filename 重算业务事实。

五个 Q4/FY owner oracle 已精确冻结：

| 输入 | owner 结果 |
|---|---|
| `2024Q4季报.pdf` | `Q4` |
| `2024Q4季度报告.pdf` | `FY` |
| `2024Q4年报.pdf` | `FY` |
| `2021Q4/季报.pdf` | `Q4` |
| `2021Q4/季度报告.pdf` | `FY` |

其余 owner contract 包括 annual `5`、periodic latest-year/max `6`、presentation `6`、earnings-call cap 等于 filtered filing count、zero recognized filing 时 call candidates typed skipped、financial statements 不设 cap、同周期优先级与稳定排序。

### 2.2 WP-B：typed consumer、argv builder、renderer 与 publisher

- parser contract：filing action `auto/create/update/delete`，batch action `auto/create/update`，三个 upload parser default 均为 `auto`；batch `--infer`/`--overwrite` default false。
- typed argv builder：entry type 唯一决定 `upload_filing`/`upload_material`；canonical ticker 与 aliases 合为单一 CSV；`auto` 不产生 `--action`；optional typed fact 无值即不产生 flag；每 entry 精确一个 `--files`；overwrite 只传播至 direct upload。
- FMP：未传 `--infer` 时零 env read/零 resolver；传入时读取非空 `FMP_API_KEY`，调用 public `resolve_company_info` 每 invocation 精确一次，验证 canonical ticker，一次性合并显式值与 resolver facts；secret/provider URL/推断结果不进入 executable body。
- output：默认写入 `--base/upload_filings_<TICKER>.sh|.cmd`；显式既有目录采用默认文件名，显式文件原样采用。
- POSIX renderer：`#!/usr/bin/env sh`、`set -eu`、`shlex.join`、`"$@"`。
- Windows renderer：UTF-8 CRLF、`setlocal DisableDelayedExpansion`、自有 batch-percent + CRT quoting、`%*`，无 `list2cmdline`、`shell=True` 或 delayed expansion。
- publisher：lexical/resolved containment、external-ancestor symlink allowed、workspace root-self/internal component/target symlink rejected、same-directory temp、flush+fsync、atomic replace、POSIX executable mode、失败/中断 old-target preservation 与 temp cleanup。
- human summary 只消费 Fins typed counts/skips；无 JSON/schema dual surface、compatibility alias/wrapper、loose parsing、`hasattr/getattr` 或测试 shim。

## 3. correction loop

全部八路径 coordinated edits 完成后才开始 validation。累计验证中收敛了四项 owner-scope finding：

1. 独立 Windows CRT test recorder 的尾反斜杠解析错误，改为完整 quote-state 记录器；production quoting 未放宽。
2. POSIX real `--action create` smoke 显式提供既有 Fins owner 所需 `--company-name "Apple Inc."`，并把断言强化为两个 `Fins succeeded` 与 filing/material 两类 storage meta。
3. scoped Ruff 指出的 `FISCAL_PERIODS` 未使用 import 已删除。
4. tests 中一处 `# type: ignore[arg-type]` 改为显式 `BatchUploadAction` cast。

每次 accepted-scope correction 后均重跑 producer+consumer cumulative validation；以下记录为最终树结果。

## 4. 最终 cumulative validation

### 4.1 focused owner/CLI tests 与 real smokes

```bash
source .venv/bin/activate
pytest tests/fins/test_upload_batch.py tests/cli/test_upload_filings_from_command.py tests/cli/test_fins_commands.py tests/cli/test_arg_parsing.py tests/cli/test_public_package_entrypoints.py tests/fins/test_fmp_company_info_resolver.py -q
```

结果：`163 passed, 2 skipped, 3 warnings in 12.58s`。两项 skip 是当前 macOS 无真实 `cmd.exe` 的 Windows-only real nodes；非 Windows 的 Windows grammar/quote recorder tests 已通过，真实 Windows release gate 仍属于 R11-I2。

```bash
python -m pytest tests/fins/test_upload_batch.py::test_real_filesystem_builds_typed_old_aligned_plan -q
python -m pytest tests/cli/test_upload_filings_from_command.py::test_posix_script_round_trips_adversarial_argv_with_real_sh -q
python -m pytest tests/cli/test_upload_filings_from_command.py::test_posix_generated_script_runs_real_cli_into_temp_storage -q
```

结果依次为：`1 passed in 0.05s`、`1 passed in 0.94s`、`1 passed in 11.04s`。最后一项真实经过 `python -m dayu.cli -> generated /bin/sh -> parser -> Service -> Fins direct runtime -> temp portfolio storage`，并产生 filing/material 两类 source document terminal success。

### 4.2 full-related 与全量 tests

```bash
pytest tests/cli tests/fins tests/service -q
```

结果：`2 failed, 1478 passed, 3 skipped, 3 warnings in 54.65s`。

```bash
pytest tests -q
```

结果：`2 failed, 5064 passed, 5 skipped, 5 deselected, 3 warnings in 146.79s`。

两项失败稳定相同：

- `tests/service/test_host_admin.py::test_prepare_host_admin_loads_only_host_runtime_without_models_or_secrets`：既有 fixture 缺当前 required `wait_poller_policy`。
- `tests/service/test_import_boundary.py::test_service_does_not_import_forbidden_layers`：既有 `dayu/service` 三个 import sentinel 命中 `dayu.fins.direct_stream` / `dayu.fins.tools._ingestion_tool_helpers`。

隔离复核命令：

```bash
pytest tests/service/test_host_admin.py::test_prepare_host_admin_loads_only_host_runtime_without_models_or_secrets tests/service/test_import_boundary.py::test_service_does_not_import_forbidden_layers -q
git diff --exit-code HEAD -- dayu/service tests/service
```

结果：两个测试仍独立失败；随后 `git diff --exit-code` 为 `0` 且无输出。失败静态依赖的 `dayu/service`、`dayu/runtime`、`tests/service` 均无 R11-I1 diff，因此是 HEAD 已存在且超出 authorization 八路径的非 accepted-scope baseline；未越权修复或掩盖。Controller checkpoint 必须显式裁决这一全局基线风险。

### 4.3 per-file coverage

```bash
coverage erase
coverage run -m pytest tests/fins/test_upload_batch.py tests/cli/test_upload_filings_from_command.py tests/cli/test_fins_commands.py tests/cli/test_arg_parsing.py tests/cli/test_public_package_entrypoints.py
coverage json -o workspace/tmp/r11-coverage.json
```

结果：coverage test `155 passed, 2 skipped, 3 warnings in 13.28s`；JSON 写入成功。普通 line coverage：

| production file | percent_covered |
|---|---:|
| `dayu/fins/upload_batch.py` | 95.25% |
| `dayu/cli/commands/fins.py` | 90.04% |
| `dayu/cli/arg_parsing.py` | 99.66% |
| `dayu/cli/upload_script.py` | 91.37% |

### 4.4 pyright 与 Ruff

```bash
python -m pyright dayu/ tests/ utils/
```

结果：`0 errors, 0 warnings, 0 informations`。

```bash
python -m ruff --version
python -m ruff check dayu/fins/upload_batch.py dayu/cli/commands/fins.py dayu/cli/arg_parsing.py dayu/cli/upload_script.py tests/fins/test_upload_batch.py tests/cli/test_upload_filings_from_command.py tests/cli/test_fins_commands.py tests/cli/test_arg_parsing.py tests/cli/test_public_package_entrypoints.py
```

结果：`ruff 0.15.11`；`All checks passed!`。

```bash
python -m ruff check dayu tests utils --output-format json > workspace/tmp/r11-ruff-current.json
```

结果：预期 Ruff findings exit `1`；锁定 baseline SHA-256 `051bd6cc84fcd32adbd792c81c9e524438dd0532a92c7504ea2edf8234ec1cea`，`baseline_count=144 current_count=144 current_only=0 resolved=0`。

## 5. source、propagation、security 与 deferred evidence

### 5.1 source / owner / propagation

- accepted-plan schema scan 在 I1 production owner/consumer 路径无旧 `_UPLOAD_BATCH_SCHEMA*`、`_render_upload_batch_plan`、`schema_version` 或 JSON plan surface；完整计划 scan只命中 `README.md:264` 与 `tests/README.md:104` 的 I2 待同步旧说明。
- `rg -n '_UPLOAD_BATCH_SCHEMA(_VERSION)?|_render_upload_batch_plan|json\.dumps|schema_version'` 对四个 changed production files 为 exit `1` / 零输出。
- `rg` 对 Fins forbidden reverse imports 为 exit `1` / 零输出。
- renderer/CLI 的 `re.compile|re.search|re.match|fnmatch|glob(` classifier scan为 exit `1` / 零输出；renderer 只消费 typed argv。
- `type: ignore|noqa|pragma: no cover|hasattr|getattr|Any|object` 对八路径为 exit `1` / 零输出。
- typed mapping 由 focused tests逐字段验证：entry type→command、ticker/aliases、action auto omission/explicit、file、fiscal、amended、dates、company、overwrite、material form/name；skipped facts只进入 summary。

### 5.2 security

```bash
rg -n 'list2cmdline|shell[[:space:]]*=[[:space:]]*True|setlocal EnableDelayedExpansion' dayu/cli
```

结果：exit `1`，零输出。

```bash
rg -n 'setlocal DisableDelayedExpansion' dayu/cli/upload_script.py tests/cli/test_upload_filings_from_command.py
```

结果：production/test 各一项正向命中。

POSIX 与本地 production renderer 生成的 Windows artifact secret scans：

```bash
rg -n 'FMP_API_KEY|R11_SENTINEL_FMP_SECRET_7f31c0|financialmodelingprep\.com' workspace/tmp/r11-posix-real/storage/*.sh
rg -n 'FMP_API_KEY|R11_SENTINEL_FMP_SECRET_7f31c0|financialmodelingprep\.com' workspace/tmp/r11-windows/*.cmd
sed '/^# Regenerate:/d' workspace/tmp/r11-posix-real/storage/upload_filings_AAPL.sh | rg -n -- '--infer|FMP_API_KEY|financialmodelingprep\.com|https?://'
```

三项均 exit `1` / 零输出。containment、root-self/internal symlink rejection、external-ancestor allow、atomic replace、old-target preservation、temp cleanup、mode/newline、fixed/appended adversarial argv、injection marker 不存在均由 focused tests通过。本轮只声明脚本生成/发布边界，不扩大为统一 authorization、workspace trust 或 shell sandbox。

### 5.3 deferred / README / placeholder

```bash
git diff --name-only HEAD -- dayu/service dayu/host dayu/engine dayu/runtime dayu/config dayu/tool dayu/ui constraints docs/host/design.md docs/engine/design.md docs/tool/design.md docs/fins/design.md docs/ui/design.md
git diff --name-only HEAD -- README.md dayu/README.md dayu/fins/README.md tests/README.md
```

两项均零输出。Issue 142/151/175/177/178、R12、Web/WeChat/render、Topic 8/9、统一 auth 与 design 路径没有 production diff。

plan placeholder scan仍命中当前 tracked `dayu/web`、`dayu/wechat`、`dayu/render`、pyproject entrypoints及旧 README/test说明；这是 authorization 明确禁止 I1 修改且由 R11-I2 closure 的 live deferred truth，不冒充 I1 零命中。README trigger 已触发但 I1 不写：R11-I2 必须同步根 `README.md`、`dayu/README.md`、`dayu/fins/README.md`、`tests/README.md` 的 executable script、default/explicit output、infer/auto 与 Windows release contract。

### 5.4 diffcheck、staging、sentinel

```bash
git diff --check HEAD
git diff --cached --name-only
git diff --exit-code HEAD -- dayu/service tests/service
```

三项均 exit `0` / 零输出。`dayu/cli/upload_script.py` 作为 untracked authorized new file另经 Ruff、pyright 与测试覆盖；无 whitespace finding。

- read-only sentinel `tests/fins/test_fmp_company_info_resolver.py` SHA-256 保持 `3530bcf11d604f651c7770cafaa4cd61fa493158894ad1aef239e8e0a2baa455`。
- HEAD 保持 `a527ec030215e5bfcf9c4fad2f4a6fda243f5d65`。
- staged set 为空；无 commit/push/PR。

## 6. final implementation hashes

| path | SHA-256 |
|---|---|
| `dayu/fins/upload_batch.py` | `7cbc1f6aa167088ebe3c89a46cb712981e2e93227bf001ec8ed12fb251512ad9` |
| `tests/fins/test_upload_batch.py` | `51ae67a8f811feb64394dbcae0a86c337c216ae0c0a665a6542ca54a8679d23c` |
| `dayu/cli/upload_script.py` | `dfe0508deb905ef9bc21204a75a8ec55abf87ec254517831556dc7a8ba7aea65` |
| `dayu/cli/arg_parsing.py` | `d8442bc64dd823cf92b09eec408a1b4437fae07a0f6b89b06afe9b25e7521b0e` |
| `dayu/cli/commands/fins.py` | `13bab3f4a1ac3eeece61c4cfb1169f68d2ac20da08afa6a4d5aeb7e63f75c0a3` |
| `tests/cli/test_upload_filings_from_command.py` | `14e1bff29c9a1f7efce61bf4891d3f6c099bb43931d54d4ef586d1df9b7ca3cd` |
| `tests/cli/test_fins_commands.py` | `297ecc542dd347b8ecf615814d001b6d71e639750cfca30b306815db9327afaa` |
| `tests/cli/test_arg_parsing.py` | `7cdc4c1d014bc7012aca28f05927b8afbbd04b86cc6d0aa2dfbf5f87af91ece6` |

Artifact 自身不在正文中记录自引用 hash；写入完成后的 hash由最终 handoff 单独报告。

## 7. remaining risk / Controller decision

- R11-I1 accepted producer/consumer、real POSIX workflow、coverage、pyright、Ruff、source/security/deferred/allowlist gates均已收敛。
- repository full-related/full tests仍有上文两项 HEAD-existing Service baseline failure；八路径 authorization 无权修复。Controller 必须在 atomic checkpoint 中显式接受既有 baseline 或另行授权其 owner，不能把它误归因于 R11-I1，也不能由本 slice 越权消除。
- 真实 Windows `cmd.exe` recorder/CLI workflow、packaging/placeholder/README closure严格保留给 R11-I2；本 artifact 不主张这些 release gates已完成。

READY_FOR_CONTROLLER_R11_I1_ATOMIC_CHECKPOINT
