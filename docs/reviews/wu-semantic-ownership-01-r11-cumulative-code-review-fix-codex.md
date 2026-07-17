# WU-SEMANTIC-OWNERSHIP-01 / R11 cumulative code-review fix（AgentCodex）

## 1. Gate、输入与授权边界

- umbrella / gate：既有 `WU-SEMANTIC-OWNERSHIP-01 / R11 cumulative code-review fix`；不是新 WU、
  新 slice、R12 或 release closure。
- Agent：AgentCodex。
- 入口 HEAD：`7972c3c0ba8628173fc91c362b9394655f60678e`；实现、验证与 evidence 完成后 HEAD 未变化。
- before-fix tracked product/test/README/packaging binary diff：
  `6c8284c6fdcfc4661a0bcd00f1c155d34985fa4af81fa400158ce3a034acd0e6`。
- accepted plan：`docs/host/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan.md`，
  942 lines；完整读取。
- AgentMiMo review：
  `docs/reviews/wu-semantic-ownership-01-r11-cumulative-code-review-mimo.md`，完整读取。
- AgentDS review：
  `docs/reviews/wu-semantic-ownership-01-r11-cumulative-code-review-ds.md`，完整读取。
- Controller adjudication：
  `docs/reviews/wu-semantic-ownership-01-r11-cumulative-code-review-controller-adjudication.md`，
  100 lines / SHA-256
  `87d27acd7d8af2db6079957914bebaa8a6c844a59aad2ab09e08bc77ec3e042e`，匹配授权锁并完整读取。
- I2 implementation evidence 与 cumulative Controller validation均完整读取；control 当前 gate精确为
  `R11 cumulative code-review bounded fix`，current R11 rows要求只修 F02/F03后完整复验并停止。
- 开始与结束时 staged set均为空；未 stage、commit、push、创建 PR、进入 R12或修改 Controller control、plan、既有
  artifacts、constraints/lock、Service/Host/Engine/runtime/deferred scope。

第一性原理结论：两个 accepted findings均成立。F02 的根因不是 CLI 错误文案，而是 CLI 在 Fins owner前复制 material-form
值域；F03 的根因不是 pytest 临时目录位置，而是 Windows real tests没有兑现显式 artifact directory contract，迫使
workflow在下游搜索通用文件名。正确修复分别位于 Fins request boundary与 Windows test/workflow evidence boundary。

## 2. Exact mutation scope 与 README decision

本轮仅修改五个授权文件，并新增本 evidence：

1. `dayu/fins/upload_batch.py`
2. `dayu/cli/commands/fins.py`
3. `tests/fins/test_upload_batch.py`
4. `tests/cli/test_upload_filings_from_command.py`
5. `.github/workflows/r11-upload-script-windows.yml`
6. `docs/reviews/wu-semantic-ownership-01-r11-cumulative-code-review-fix-codex.md`（本文件）

`tests/README.md` 未修改：现有文字只承诺两个真实 Windows nodes、workflow command与 release evidence，不拥有
`%TEMP%` locator、artifact内部文件名或子目录 contract；本轮用户可见 CLI、测试入口与执行方式均未改变，故没有实际文字
触发。其它四份 README同样没有 contract变化，不机械同步。

## 3. Finding closure

### 3.1 `R11-DS-F01` — REJECTED / NO FIX / boundary preserved

- 未修改 `dayu.runtime`，未抽取 containment helper，未新增共享 path abstraction。
- Fins source containment与 CLI output containment继续由两个独立 policy owner拥有。
- `git diff` 对 `dayu/runtime/**` 为零；Fins reverse import scan为零。
- `_optional_text` / `_optional_stripped_text` 未修改；没有 optional-text normalization fix、alias或fallback。

### 3.2 `R11-DS-F02` — FIXED

Root-cause fix：

- `UploadBatchPlanRequest.material_form` 从“已经合法的 `MaterialFormType`”改为严格、诚实的输入类型
  `str | None`；它表示尚待 Fins owner验证的候选，不用 `cast`伪造已验证事实。
- CLI `_single_batch_material_form` 只拥有 CLI输入边界需要的单值检查、trim与 uppercase normalization，返回
  `str | None`；删除三个合法值的硬编码副本与下游合法性判断。
- raw normalized candidate直接进入 `UploadBatchPlanRequest`；Fins私有 `_MATERIAL_FORM_TYPES`及
  `_validated_material_form`继续唯一验证值域并返回 typed `MaterialFormType`。
- 未公开 `_MATERIAL_FORM_TYPES`，未新增 public constant、compatibility alias/wrapper、fallback、loose parsing或
  downstream revalidation。
- `UploadBatchPlanUsageError`仍由 `run_fins_direct_command`稳定映射为 `EXIT_USAGE_ERROR`，无效候选不发布脚本。

Owner tests：

- `test_invalid_material_form_is_rejected_by_fins_owner` 直接向 Fins request传入 `ESG_REPORT`，断言唯一 owner抛出
  `UploadBatchPlanUsageError("unsupported material form: ESG_REPORT")`。
- `test_material_form_candidate_reaches_fins_owner_and_maps_usage_exit` 断言 CLI将 ` esg_report `传播为 request候选
  `ESG_REPORT`，真实 Fins owner拒绝后 CLI返回 usage exit且 workspace/script均未产生。
- `rg` 对 `dayu/cli/commands/fins.py` 中
  `FINANCIAL_STATEMENTS|EARNINGS_CALL|EARNINGS_PRESENTATION` 为 exit 1 / zero output。

### 3.3 `R11-DS-F03` — FIXED / release execution still pending

Root-cause fix：

- 两个 Windows-only real tests继续保留 `@pytest.mark.skipif(os.name != "nt")` 与真实
  `cmd.exe /d /c`；没有 unit替代、fake runner或 production seam。
- 未配置 `DAYU_R11_WINDOWS_ARTIFACT_DIR` 时，普通本地 test仍原样使用自己的 `tmp_path`。
- env显式配置时，test先要求该 root已经存在；不存在即 assertion failure，不做 repo/tmp fallback。两个 test分别只拥有
  固定 `cmd-recorder/` 与 `cli-storage/` 子目录，并在其内发布 exact files：
  `generated-upload.cmd`、`recorder-oracle.jsonl`、`cli-generated-upload.cmd`、
  `cli-grammar-oracle.json`与真实 `portfolio/` storage evidence。
- CLI real test自身写出 oracle，包含 test node、pass result、generated script SHA-256、source artifact count与
  `cmd.exe /d /c` invocation；workflow不再从偶然文件位置重建事实。
- workflow删除三次 `%TEMP%` recursive search、通用名 `-Filter`与 `Copy-Item`；只从上述固定路径读取，校验四个 exact
  files、recorder单行 oracle、CLI oracle字段、generated script hash及 exact portfolio artifact count。
- JUnit、stdout/stderr、environment、cmd help与 `actions/upload-artifact`仍落在 plan锁定的
  `workspace/tmp/r11-windows`；workflow triggers仍精确为 cumulative 22 paths。
- 没有 broad locator glob、repo-local fallback、production test seam、secret/provider或跳过真实 cmd。

本地验证只能证明 YAML、路径 contract、grammar node与非 Windows skip；真实 GitHub `windows-latest` run仍未发生，
状态必须保持 `PENDING_RELEASE_BLOCKER`。

## 4. Before / after manifest

### 4.1 Fix-owned five-file locks

| Path | Before SHA-256 | After SHA-256 |
|---|---|---|
| `dayu/fins/upload_batch.py` | `7cbc1f6aa167088ebe3c89a46cb712981e2e93227bf001ec8ed12fb251512ad9` | `95c543801a75c4428b8d2022000d23be644c3a706ca12c06568a8f3e1eda74f0` |
| `dayu/cli/commands/fins.py` | `13bab3f4a1ac3eeece61c4cfb1169f68d2ac20da08afa6a4d5aeb7e63f75c0a3` | `2b022641e2d19daaf73b8787e3240a6c4e041b7b36fd66965f466275d9a1797f` |
| `tests/fins/test_upload_batch.py` | `51ae67a8f811feb64394dbcae0a86c337c216ae0c0a665a6542ca54a8679d23c` | `1e3967ecadd77c8688640f02783b9283390a32e1a01b316ac88f83323bc2a1cf` |
| `tests/cli/test_upload_filings_from_command.py` | `14e1bff29c9a1f7efce61bf4891d3f6c099bb43931d54d4ef586d1df9b7ca3cd` | `758e4e3db093e456c62d872c74046c17357214e9dbeacd133d0d8d914f728fd7` |
| `.github/workflows/r11-upload-script-windows.yml` | `4026da55c789c0f3f961887f3f19536c7817abad4665ffd78b493219f2560953` | `8eae09d59e69413adbb2c49dc60c3c431834bab7f230c410b9e981100d3f84c5` |

本 evidence在 fix前 absent，fix后 present；自身 SHA不能在自身内容中无循环地承诺，由 Controller checkpoint锁定。

### 4.2 Cumulative exact 22-path product manifest

| Status | Path | Before-fix truth | After-fix truth |
|---|---|---|---|
| A | `.github/workflows/r11-upload-script-windows.yml` | `4026da55...0953` | `8eae09d5...84c5` |
| M | `README.md` | `b6e1bcfc...8733` | unchanged / same |
| M | `dayu/README.md` | `8b89eec6...994e` | unchanged / same |
| M | `dayu/cli/arg_parsing.py` | `d8442bc6...1b0e` | unchanged / same |
| M | `dayu/cli/commands/fins.py` | `13bab3f4...c0a3` | `2b022641...797f` |
| A | `dayu/cli/upload_script.py` | `dfe0508d...ea65` | unchanged / same |
| M | `dayu/fins/README.md` | `f93daf5b...218` | unchanged / same |
| M | `dayu/fins/upload_batch.py` | `7cbc1f6a...ad9` | `95c54380...74f0` |
| D | `dayu/render/__init__.py` | absent / deletion | absent / deletion |
| D | `dayu/render/render.py` | absent / deletion | absent / deletion |
| D | `dayu/web/__init__.py` | absent / deletion | absent / deletion |
| D | `dayu/web/__main__.py` | absent / deletion | absent / deletion |
| D | `dayu/wechat/__init__.py` | absent / deletion | absent / deletion |
| D | `dayu/wechat/main.py` | absent / deletion | absent / deletion |
| M | `pyproject.toml` | `b71fd9ff...081e` | unchanged / same |
| M | `requirements.txt` | `de025c19...f63` | unchanged / same |
| M | `tests/README.md` | `478efffc...4c1` | unchanged / same |
| M | `tests/cli/test_arg_parsing.py` | `d3a4abcc...2658` | unchanged / same |
| M | `tests/cli/test_fins_commands.py` | `297ecc54...faaa` | unchanged / same |
| M | `tests/cli/test_public_package_entrypoints.py` | `e08d195e...0e0a` | unchanged / same |
| M | `tests/cli/test_upload_filings_from_command.py` | `14e1bff2...a3cd` | `758e4e3d...fd7` |
| M | `tests/fins/test_upload_batch.py` | `51ae67a8...23c` | `1e3967ec...a1cf` |

After-fix unchanged full hashes依次匹配 I2 evidence锁：`b6e1bcfc...8733`、`8b89eec6...994e`、
`d8442bc6...1b0e`、`dfe0508d...ea65`、`f93daf5b...218`、`b71fd9ff...081e`、
`de025c19...f63`、`478efffc...4c1`、`d3a4abcc...2658`、`297ecc54...faaa`、
`e08d195e...0e0a`。22-path union无新增/缺失；tracked cumulative binary diff由 before
`6c8284c6...d0e6`变为 after
`6065289ee2a2da8d475de29fcd8b5d719ca1f0448e357e885a5ac0156fb6f424`；untracked workflow继续由独立 full hash锁定。

## 5. Mandatory cumulative revalidation

所有命令均在 `source .venv/bin/activate` 后运行。

### 5.1 Tests 与 real smokes

| Gate | Result | Decision |
|---|---|---|
| 新 Fins owner + CLI propagation | `2 passed, 3 warnings` | PASS |
| Windows local exact workflow nodes | `1 passed, 2 skipped, 3 warnings` | grammar PASS；两个 skip仅因 macOS无真实 cmd.exe |
| affected/focused cumulative | `155 passed, 2 skipped, 3 warnings` | PASS |
| Fins real filesystem smoke | `1 passed` | PASS |
| POSIX real `/bin/sh` adversarial recorder | `1 passed, 3 warnings` | PASS |
| POSIX real CLI → Service → Fins → temp storage | `1 passed, 3 warnings` | PASS |
| related `tests/cli tests/fins tests/service` | `2 failed, 1470 passed, 3 skipped, 3 warnings` | 精确两项 existing Service baseline |
| full `tests` | `2 failed, 5056 passed, 5 skipped, 5 deselected, 3 warnings` | 精确同两项；无第三项/new R11 failure |

两项允许的既有 failure仍精确为：

1. `tests/service/test_host_admin.py::test_prepare_host_admin_loads_only_host_runtime_without_models_or_secrets`：
   fixture缺 current required `wait_poller_policy`；
2. `tests/service/test_import_boundary.py::test_service_does_not_import_forbidden_layers`：三个既有
   Service → Fins imports。

`dayu/service/fins_direct.py`、`fins_wait_adapter.py`、`host_assembly.py`、
`dayu/runtime/config_loader.py`及上述两个 test files相对 HEAD的 exact diff为零；本轮不扩域修复，也不把 suite冒充 green。

### 5.2 Fresh exact-wheel constrained gate

- `pip wheel --no-deps --no-build-isolation`生成 exact-one
  `workspace/tmp/r11-dist/dayu_agent-0.1.4-py3-none-any.whl`。
- wheel：2,068,047 bytes / 424 members / SHA-256
  `f379d394cc1164b7bb79c9e93def3f941565cb0c29bf2c9da5dc066858145487`。
- fresh venv只对该 exact wheel执行一次
  `constraints/lock-macos-arm64-py311.txt` constrained normal install；未先 runtime `--no-deps`、未重复 install。
- `pip check`：`No broken requirements found.`；top-level help与 `upload_filings_from --help`均 exit 0。
- `dayu.web` / `dayu.wechat` / `dayu.render` importability：0。
- `wheel METADATA placeholder contracts: 0`；`wheel placeholder entry points: 0`；
  `wheel extracted placeholder paths: 0`；`wheel RECORD placeholder paths: 0`。
- 未使用 lazy import、fallback、fixture/`sys.path` shim、lock/workflow范围扩大。

### 5.3 Coverage、pyright 与 Ruff

from-zero coverage run：`147 passed, 2 skipped, 3 warnings`。

| Changed production file | Whole-file line coverage |
|---|---:|
| `dayu/fins/upload_batch.py` | `95.5696%` |
| `dayu/cli/commands/fins.py` | `90.8686%` |
| `dayu/cli/arg_parsing.py` | `99.6599%` |
| `dayu/cli/upload_script.py` | `91.3669%` |

- 四文件均 `>=80.00%`。
- full pyright：`0 errors, 0 warnings, 0 informations`。
- Ruff version：`ruff 0.15.11`，精确匹配锁。
- scoped Ruff九个 changed production/test paths：`All checks passed!`。
- full Ruff：baseline/current均 144 findings；`current_only=0`、`resolved=0`；两份 JSON SHA-256均为
  `051bd6cc84fcd32adbd792c81c9e524438dd0532a92c7504ea2edf8234ec1cea`。

### 5.4 Workflow、README、source、security 与 deferred scans

- workflow YAML parse PASS；`pull_request.paths`为 exact 22，无 missing/extra/duplicate。
- `%TEMP%|Get-ChildItem.*-Filter|Copy-Item` 对 workflow：exit 1 / zero output。
- exact artifact env/subdirectories/files在 test/workflow均有正向命中；workflow只在 exact `portfolio/`内递归计数，
  不扫描系统 temp或 repo通用名。
- old JSON/schema renderer与 placeholder public surface scans：exit 1 / zero output。
- Fins reverse imports、renderer filename/fiscal/material classifier、`type: ignore` / `noqa` / coverage pragma /
  `hasattr/getattr` / `Any/object` seam scans：exit 1 / zero output。
- `list2cmdline|shell=True|setlocal EnableDelayedExpansion`：exit 1 / zero output；
  `setlocal DisableDelayedExpansion`在 production/test各正向命中一处。
- POSIX与本地已生成 Windows `.cmd`的 `FMP_API_KEY` / sentinel secret / provider URL scans：exit 1 / zero output；
  POSIX executable body的 `--infer` / secret / URL scan同样为零。
- `git ls-files dayu/web dayu/wechat dayu/render`仍精确列出 index中的六个删除项；working tree六文件均 absent，wheel
  archive/importability为零。
- 两个只读 Web tool negative import-boundary sentinel各精确命中一次且文件无 diff。
- README diff仍精确为 root / `dayu/` / Fins / tests四份既有变更；current positive scan继续覆盖
  `upload_filings_from`、default auto、batch-only infer与 `.sh`/`.cmd`。
- Service/Host/Engine/runtime/config/tool/UI/constraints/design diff为零；added-line Issue 142/151/175/177/178、R12、
  Topic 8/9、unified auth、workspace trust、shell sandbox scan为 exit 1 / zero output。
- `git diff --check` PASS；staged manifest empty。

安全结论只覆盖既有 source/output containment、symlink、same-directory atomic replace、argv injection与 secret
non-persistence；不冒充统一 authorization、workspace trust或 shell sandbox。

## 6. Final ledger、风险与 handoff

| Finding / risk | Final status |
|---|---|
| `R11-DS-F01` | `REJECTED / NO FIX`；owner separation保持 |
| `R11-DS-F02` | `FIXED`；Fins owner test + CLI propagation/usage-exit通过 |
| `R11-DS-F03` | `FIXED`；deterministic locator/test-published evidence/workflow exact validation通过本地审计 |
| accepted/open local finding | `0 pending Controller checkpoint` |
| unclassified residual | `0` |
| existing Service failures | 精确两项 repository baseline；非 R11 owner |
| Windows real run | `PENDING_RELEASE_BLOCKER` |

真实 GitHub `windows-latest` / `cmd.exe` recorder与 CLI storage run尚未发生。本轮只消除 locator不确定性，不能用 macOS
skip、renderer unit、YAML parse或本地 artifact代替真实 run，不能把 Windows gate标为 closed/waived/residual。下一入口只能是
Controller R11 code-review fix checkpoint；dual complete re-review、stage/commit、R12、push与 PR仍未授权。

Artifact path：
`docs/reviews/wu-semantic-ownership-01-r11-cumulative-code-review-fix-codex.md`

READY_FOR_CONTROLLER_R11_CODE_REVIEW_FIX_CHECKPOINT
