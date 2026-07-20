# WU-SEMANTIC-OWNERSHIP-01 / R11-I2 implementation checkpoint evidence（AgentCodex）

## 1. Gate identity 与授权边界

- umbrella / slice：既有 `WU-SEMANTIC-OWNERSHIP-01 / R11-I2`；本轮是同一 implementation task 的
  wheel-smoke continuation，不是新 WU、新 slice、review 或 acceptance。
- live authorization：
  `docs/reviews/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-i2-wheel-smoke-continuation-controller-authorization.md`，
  SHA-256 `2258eda0ff7bde58f71c8e4b600477c10a343a822cddf2336ff9818e93201420`。
- accepted correction HEAD：`7972c3c0ba8628173fc91c362b9394655f60678e`，parent
  `de476c452411e9d325d43b608de22b7236edfedb`，subject
  `docs: accept R11 I2 wheel smoke plan correction`。
- accepted plan：942 lines / 81,592 bytes / SHA-256
  `f1c95c3b5ecb1d6f01a2f15d1af6c96396ebb370c10997108a3c44dbd14b2ffd`。
- continuation 开始和结束时 staged set 均为空。未 stage、commit、push、创建 PR、进入 cumulative review 或 R12。
- 产品、测试、README、packaging、workflow 在本 continuation 中没有 mutation；唯一写入是本 evidence。
  `workspace/tmp/**` 只承载机械验证产物。
- Controller control、plan、authorization、adjudication 与既有 artifacts 均保持只读。结束前 control 为
  2,271 lines / 541,114 bytes / SHA-256
  `686b603b02926cfe6bf01ceb56a267662e8813736f47455f9690b38eb1cee83e`。

第一性原理判断：前次 isolated help failure 的直接根因是 runtime venv 刻意用 `--no-deps` 安装 wheel，导致 wheel
已声明的 `aiohttp` 未安装；它不是 CLI import owner 缺陷。正确 validation owner 是把 build/archive 边界与 fresh runtime
边界分开：build 保持 `--no-deps --no-build-isolation`，runtime 对 exact wheel 只做一次受当前平台 lock 约束的正常安装。
本轮按 corrected plan 复验后该真实 packaging gate通过，无理由修改产品代码。

## 2. Continuation preflight 与 protected locks

开始和所有 validation 完成后均重新核对：

| Lock | 最终值 | 结果 |
|---|---|---|
| stopped tracked binary diff：`git diff --binary HEAD -- README.md dayu tests pyproject.toml requirements.txt .github` | `6c8284c6fdcfc4661a0bcd00f1c155d34985fa4af81fa400158ce3a034acd0e6` | MATCH |
| `dayu/fins/upload_batch.py` | `7cbc1f6aa167088ebe3c89a46cb712981e2e93227bf001ec8ed12fb251512ad9` | MATCH |
| `tests/fins/test_upload_batch.py` | `51ae67a8f811feb64394dbcae0a86c337c216ae0c0a665a6542ca54a8679d23c` | MATCH |
| `dayu/cli/upload_script.py` | `dfe0508deb905ef9bc21204a75a8ec55abf87ec254517831556dc7a8ba7aea65` | MATCH |
| `dayu/cli/arg_parsing.py` | `d8442bc64dd823cf92b09eec408a1b4437fae07a0f6b89b06afe9b25e7521b0e` | MATCH |
| `dayu/cli/commands/fins.py` | `13bab3f4a1ac3eeece61c4cfb1169f68d2ac20da08afa6a4d5aeb7e63f75c0a3` | MATCH |
| `tests/cli/test_upload_filings_from_command.py` | `14e1bff29c9a1f7efce61bf4891d3f6c099bb43931d54d4ef586d1df9b7ca3cd` | MATCH |
| `tests/cli/test_fins_commands.py` | `297ecc542dd347b8ecf615814d001b6d71e639750cfca30b306815db9327afaa` | MATCH |
| shared `tests/cli/test_arg_parsing.py` | `d3a4abcc22093ff6c4e06edebf249282f1fbac9d9eb3a575c618f28210742658` | MATCH |
| `tests/README.md` | `478efffcbf5d3e4f172ec5a7373e49996cf62f3b85a485fdcd60af7623f1c4c1` | MATCH |
| Windows workflow | `4026da55c789c0f3f961887f3f19536c7817abad4665ffd78b493219f2560953` | MATCH |
| read-only FMP test sentinel | `3530bcf11d604f651c7770cafaa4cd61fa493158894ad1aef239e8e0a2baa455` | MATCH |
| six placeholder source files | working tree 全部 absent | MATCH |
| staged set | empty | MATCH |

这里的七个 non-shared I1 paths是表中从 `upload_batch.py` 到 `test_fins_commands.py` 的七项；它们在 I2
continuation 前后均保持只读。

## 3. Fresh exact-wheel packaging gate

### 3.1 清理、build 与 archive boundary

先删除并重建 `workspace/tmp/r11-dist`、`r11-wheel-extract`、`r11-wheel-venv`。build 精确使用：

```bash
python -m pip wheel --no-deps --no-build-isolation --wheel-dir workspace/tmp/r11-dist .
```

结果只有一个 wheel：

| Artifact | 值 |
|---|---|
| path | `workspace/tmp/r11-dist/dayu_agent-0.1.4-py3-none-any.whl` |
| size | 2,068,159 bytes |
| SHA-256 | `68ae7aa1bb53748ba76e949cce5f4e30138d59ebeace8baf014842de51af0850` |
| archive member count | 424 |
| placeholder archive path | 0 |

exact-one extraction与全部 negative oracles均 exit 0：

- archive raw member scan：`placeholder paths: 0`；
- `wheel METADATA placeholder contracts: 0`，无 `Provides-Extra: web` 或 Streamlit requirement；
- `wheel placeholder entry points: 0`；实际 `entry_points.txt` 只有
  `dayu-cli = dayu.cli.main:main`；
- `wheel extracted placeholder paths: 0`；
- `wheel RECORD placeholder paths: 0`。

### 3.2 Fresh constrained normal install 与 runtime oracles

- fresh venv 只对上述 exact wheel 安装一次；未先用 runtime `--no-deps`，未重复 install。
- install 使用 `--constraint constraints/lock-macos-arm64-py311.txt`；constraint SHA-256
  `3bbfe5c0d9f73ec621993c0eabb5f7e94ea2713f31a9632cc02ddaade42b6c33`。
- pip 正常解析、下载/读取缓存并安装 wheel 声明的 runtime dependencies，包括前次缺失的 `aiohttp`；install 成功。
- 随后的顺序 oracle：
  1. `python -m pip check`：exit 0，`No broken requirements found.`；
  2. `python -m dayu.cli --help`：exit 0，公开 `upload_filings_from`；
  3. `python -m dayu.cli upload_filings_from --help`：exit 0，显示
     `--action {auto,create,update}`、batch-only `--infer`、`--overwrite`；
  4. `importlib.util.find_spec`：`dayu.web`、`dayu.wechat`、`dayu.render` 全为 `None`。

dependency resolution/install、lock、`pip check`、help、importability 均无失败；未采用 lazy import、fallback、fixture/
`sys.path` shim、lock/workflow 修改或范围扩大。

## 4. Final cumulative tests 与真实 smoke

| Validation | 结果 | 裁决 |
|---|---|---|
| Ruff version oracle | `ruff 0.15.11` | MATCH |
| focused I1+I2/public packaging/FMP | `153 passed, 2 skipped, 3 warnings in 14.20s` | PASS；两项仅 Windows-only |
| related：`pytest tests/cli tests/fins tests/service -q` | `2 failed, 1468 passed, 3 skipped, 3 warnings in 55.76s` | 仅两项已裁决 Service baseline；不冒充 green |
| full：`pytest tests -q` | `2 failed, 5054 passed, 5 skipped, 5 deselected, 3 warnings in 145.66s` | 仅同两项 Service baseline；无新增 failure |
| Fins real filesystem | `1 passed in 0.05s` | PASS |
| real `/bin/sh` adversarial argv recorder | `1 passed, 3 warnings in 0.94s` | PASS |
| real POSIX CLI → Service → Fins → temp storage | `1 passed, 3 warnings in 11.03s` | PASS |
| workflow 对应本地 Windows command | `1 passed, 2 skipped, 3 warnings in 0.91s` | grammar node PASS；两个真实 `cmd.exe` nodes在 macOS明确 SKIP |

两项 repository baseline failure精确为：

1. `tests/service/test_host_admin.py::test_prepare_host_admin_loads_only_host_runtime_without_models_or_secrets`：
   fixture 缺 current required `wait_poller_policy`；
2. `tests/service/test_import_boundary.py::test_service_does_not_import_forbidden_layers`：三个既有
   Service → Fins imports 命中 `dayu.fins.direct_stream` / `dayu.fins.tools._ingestion_tool_helpers`。

直接同源复核：`dayu/service/fins_direct.py`、`fins_wait_adapter.py`、`host_assembly.py`、
`dayu/runtime/config_loader.py` 与上述两个 Service test 的 working blob 均逐一等于 `HEAD:<path>` blob；
`git diff --exit-code HEAD -- dayu/service dayu/runtime/config_loader.py tests/service` 为零。因此它们是 HEAD-existing、
非 R11 baseline failure；本 slice 未扩域修复、未豁免、也未把 related/full suite写成 green。

## 5. Coverage、pyright 与 Ruff

coverage 命令按 plan 对五个 focused test files from-zero 重建，结果 `145 passed, 2 skipped, 3 warnings`。实际 changed
production Python whole-file line coverage：

| File | percent_covered | Gate |
|---|---:|---|
| `dayu/fins/upload_batch.py` | 95.2532% | PASS |
| `dayu/cli/commands/fins.py` | 90.0442% | PASS |
| `dayu/cli/arg_parsing.py` | 99.6599% | PASS |
| `dayu/cli/upload_script.py` | 91.3669% | PASS |

- full pyright：`python -m pyright dayu/ tests/ utils/` → `0 errors, 0 warnings, 0 informations`。
- scoped Ruff 对九个 changed production/test paths：`All checks passed!`。
- full Ruff JSON：locked baseline/current 都是 144 findings，二者 SHA-256 均为
  `051bd6cc84fcd32adbd792c81c9e524438dd0532a92c7504ea2edf8234ec1cea`；按
  relative filename/code/row/column/message 比较为
  `baseline_count=144 current_count=144 current_only=0 resolved=0`。
- 没有使用 `noqa`、type-ignore、coverage pragma、配置 exclusion 或 baseline refresh 掩盖 finding。

## 6. Final cumulative 22-path manifest

Allocation 断言：I1 `8` paths，I2 `15` paths，唯一 shared path
`tests/cli/test_arg_parsing.py`，union `22` unique paths。tracked diff 加两个 authorized untracked additions 后与该 union
精确相等，无 unexpected/missing path。

| Status | Path | SHA-256 / deletion truth |
|---|---|---|
| A | `.github/workflows/r11-upload-script-windows.yml` | `4026da55c789c0f3f961887f3f19536c7817abad4665ffd78b493219f2560953` |
| M | `README.md` | `b6e1bcfc580e794fba2eb7528aacc6a6b0f8e8dd4763eb7b27ce5636460d8733` |
| M | `dayu/README.md` | `8b89eec6132f3cbd19d7e06660a7b380b79a85b5ef207aa17ffbbe1fe3ab994e` |
| M | `dayu/cli/arg_parsing.py` | `d8442bc64dd823cf92b09eec408a1b4437fae07a0f6b89b06afe9b25e7521b0e` |
| M | `dayu/cli/commands/fins.py` | `13bab3f4a1ac3eeece61c4cfb1169f68d2ac20da08afa6a4d5aeb7e63f75c0a3` |
| A | `dayu/cli/upload_script.py` | `dfe0508deb905ef9bc21204a75a8ec55abf87ec254517831556dc7a8ba7aea65` |
| M | `dayu/fins/README.md` | `f93daf5bc3c29e4f19a76c2820a94e7973b713af543244e36a6dd0481fdbf218` |
| M | `dayu/fins/upload_batch.py` | `7cbc1f6aa167088ebe3c89a46cb712981e2e93227bf001ec8ed12fb251512ad9` |
| D | `dayu/render/__init__.py` | working tree absent / deletion diff |
| D | `dayu/render/render.py` | working tree absent / deletion diff |
| D | `dayu/web/__init__.py` | working tree absent / deletion diff |
| D | `dayu/web/__main__.py` | working tree absent / deletion diff |
| D | `dayu/wechat/__init__.py` | working tree absent / deletion diff |
| D | `dayu/wechat/main.py` | working tree absent / deletion diff |
| M | `pyproject.toml` | `b71fd9ff6435294752ec8de8cb0cc9f11bb4783f1a9e8944d9ce457a745c081e` |
| M | `requirements.txt` | `de025c19420211c2145f8533bbf0d2cf297229057b37c6caa48cc7930a9a4f63` |
| M | `tests/README.md` | `478efffcbf5d3e4f172ec5a7373e49996cf62f3b85a485fdcd60af7623f1c4c1` |
| M | `tests/cli/test_arg_parsing.py` | `d3a4abcc22093ff6c4e06edebf249282f1fbac9d9eb3a575c618f28210742658` |
| M | `tests/cli/test_fins_commands.py` | `297ecc542dd347b8ecf615814d001b6d71e639750cfca30b306815db9327afaa` |
| M | `tests/cli/test_public_package_entrypoints.py` | `e08d195e436e594e0bb7d2ca3b55a43b0b93080569dc0298a0c397ad9d8c0e0a` |
| M | `tests/cli/test_upload_filings_from_command.py` | `14e1bff29c9a1f7efce61bf4891d3f6c099bb43931d54d4ef586d1df9b7ca3cd` |
| M | `tests/fins/test_upload_batch.py` | `51ae67a8f811feb64394dbcae0a86c337c216ae0c0a665a6542ca54a8679d23c` |

### Shared-function-only proof

对 current shared file 与 `HEAD:tests/cli/test_arg_parsing.py` 做 AST node 定位，只把 current
`test_root_readme_matches_current_cli_public_contract`（current lines 358—397）在内存中替换为 HEAD 中同名旧函数
（HEAD lines 304—327）。重建文件 SHA-256 为
`7cdc4c1d014bc7012aca28f05927b8afbbd04b86cc6d0aa2dfbf5f87af91ece6`，精确等于 I1 before-lock。
因此 I2 在 shared path 的 delta 只属于该函数；同文件其它 I1 parser/help nodes 的 bytes未变化。

## 7. README trigger 与 owner review

| README | Trigger / owner decision | 人工复核 |
|---|---|---|
| root `README.md` | public CLI、install extra、entrypoint、script output/workflow/排障变化 | 已按最终用户手册边界说明 batch-only infer、auto、ticker CSV、default/explicit output、`.sh`/`.cmd` 执行、追加参数与排障；无 Host/Engine/review 状态 |
| `dayu/README.md` | package/public stable boundary变化 | 只删除 placeholder packages 的稳定边界承诺；未改分层、装配或 future capability |
| `dayu/fins/README.md` | Fins typed owner变化 | 只记录扫描/classification/caps/skip 的 Fins owner与 CLI mechanical consumer boundary；无用户命令或 gate 流程 |
| `tests/README.md` | tests 与真实 smoke/workflow变化 | 文件自身没有独立 `Agent更新约束`；按 AGENTS trigger只同步 focused tests、真实 POSIX/Windows nodes、packaging negative contract和 workflow evidence，不扩写产品架构 |

根 README contract test同时确认：batch section 有 `upload_filings_from --infer`、`FMP_API_KEY`、`.sh` / `.cmd`、
`/bin/sh` / `cmd.exe /d /c`；direct upload section无 `--infer`；旧 JSON argv `schema_version=1` / `commands` 与
“不生成 shell”均不存在。

## 8. Source、security、deferred 与 no-unified-auth scans

### 8.1 自动 scan 结果

| Scan | Exit / output | 结果 |
|---|---|---|
| old JSON/schema renderer contract | exit 1 / zero output | PASS |
| placeholder public scripts/packages/README claims/Web extra | exit 1 / zero output | PASS |
| Fins reverse imports | exit 1 / zero output | PASS |
| renderer filename/fiscal/material classifier regex/glob | exit 1 / zero output | PASS |
| `type: ignore` / `noqa` / coverage pragma / `hasattr/getattr` / `Any/object` seam | exit 1 / zero output | PASS |
| `list2cmdline` / `shell=True` / delayed expansion re-enable | exit 1 / zero output | PASS |
| `setlocal DisableDelayedExpansion` positive oracle | production/test各一项 | PASS |
| POSIX generated artifact secret/provider URL | exit 1 / zero output | PASS |
| Windows locally generated artifact secret/provider URL | exit 1 / zero output | PASS |
| POSIX executable body `--infer`/secret/network | exit 1 / zero output | PASS |
| deferred production/design/constraints diff | exit 0 / zero output | PASS |
| added-line Issue 142/151/175/177/178、R12、Topic 8/9、unified auth/workspace trust/shell sandbox | exit 1 / zero output | PASS |
| `git diff --check HEAD` | exit 0 / zero output | PASS |
| staged manifest | empty | PASS |

`rg '"dayu.web"'` 精确在两个 read-only Web tool negative import-boundary sentinel中各命中一次，且两文件相对 R10
baseline diff为空。`git ls-files dayu/web dayu/wechat dayu/render` 如实列出六个 index 中仍 tracked 的 unstaged deletions；
这不是 working-tree残留。local deletion closure由六文件 working-tree absence、`D` status、wheel archive/extracted/
RECORD zero paths与 fresh-wheel importability共同证明。

### 8.2 人工 owner / propagation / security review

- Fins 只产生 typed classification/fiscal/material/cap/skip facts，零 CLI/Service/Host/Engine/UI reverse import；CLI builder只把
  entry type、ticker/aliases、action、file、fiscal、amended、dates、company、overwrite、material form/name映射到当前
  direct grammar，无 optional fact时不传，不猜 document ID。
- renderer/publisher仍由 focused与真实 smoke覆盖 lexical/resolved containment、external-ancestor symlink allowed、root-self/
  internal component/target symlink rejected、same-directory atomic replace、旧 target preservation、temp cleanup、POSIX mode/
  newline、fixed/appended adversarial argv与 injection marker absence。
- generated script comment/body分离：regeneration comment可保留无 secret 的 `--infer` 生成命令；executable body不含
  `--infer`、API-key env/provider URL或网络调用。安全结论只覆盖 path、symlink、atomic write、argv injection 与 secret
  non-persistence，不冒充统一 authorization、workspace trust 或 shell sandbox。
- Issue 142/151/175/177/178、R12、真实 Web/WeChat/render、Topic 8/9 与统一 authorization 均无 production diff；
  Service/Host/Engine/runtime/config/tool/UI/constraints/design diff为空。

## 9. Windows workflow contract 与 release blocker

本地人工复核 112-line workflow：

- name、`contents: read`、`windows-latest`、Python 3.11、30-minute timeout正确；
- `workflow_dispatch` 与 `pull_request.paths` 精确列出 22 个 cumulative unique product paths；
- install仍精确为
  `python -m pip install -e ".[test,dev]" -c constraints/lock-windows-x64-py311.txt`；
- pytest精确包含 real `cmd.exe` recorder、real CLI/temp-storage 与 action grammar三个 nodes；production tests实际调用
  `cmd.exe /d /c`；
- artifact env/path、JUnit、generated scripts、recorder/CLI oracle、stdout/stderr、environment、`cmd.exe /?`、
  `if: always()`、artifact name、14-day retention与 no-files error完整；无 secret/provider、schedule/release/deployment或宽 glob。

当前 macOS 无真实 `cmd.exe`，两个 Windows-only nodes明确 skipped。branch 未 push，故没有可对应当前 implementation tree 的
GitHub-hosted Windows run/artifact；状态必须保持：

`PENDING_RELEASE_BLOCKER`

它不是 accepted residual，不能标 closed/waived，也不能由本地 renderer unit或 macOS skip替代。真实 GitHub
`windows-latest` run 必须在后续获授权发布后成功，并由 Controller核对 event/commit SHA、无 skip、exact argv、no injection、
CLI terminal success/temp-storage artifacts与 secret scan，才可关闭 release gate。

## 10. Completion status、风险与 handoff

- R11-scoped final local validation：无新增 product/test/static/coverage/security failure，产品无需 correction。
- accepted/open R11-I2 implementation finding：`0`；unclassified residual：`0`。
- repository related/full suite：不全绿，精确只有两项 Controller 已裁决的 HEAD-existing Service baseline failure；owner不在
  R11-I2，本轮不扩域修复。
- Windows cross-platform release：`PENDING_RELEASE_BLOCKER`，真实 GitHub `cmd.exe` 尚未运行。
- final stopped binary diff与所有 protected hashes在全部验证后仍 MATCH；staged set empty。
- next entry point只能是 Controller R11-I2 checkpoint；cumulative review、accepted implementation commit、R12、push/PR均未授权。

Artifact path：
`docs/reviews/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-i2-implementation-codex.md`

READY_FOR_CONTROLLER_R11_I2_CHECKPOINT
