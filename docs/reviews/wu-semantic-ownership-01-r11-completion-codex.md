# WU-SEMANTIC-OWNERSHIP-01 / R11 artifact-only completion ledger（AgentCodex）

## 1. Handoff identity、结论与边界

- umbrella：既有 `WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation。
- gate：R11 accepted implementation commit 后的 artifact-only completion handoff；不是新 WU、R12、aggregate
  deepreview、push 或 PR gate。
- Controller authorization review-time input：
  [R11 completion Controller authorization](./wu-semantic-ownership-01-r11-completion-controller-authorization.md)，
  60 lines / 3,034 bytes / SHA-256
  `09d6aec8c08efc6b418650113cd71bcc9c16a78bf3a2b8972f70bc691c330748`；这是AgentCodex实际完整读取并据以执行
  review/completion handoff的输入。
- Controller stage-hygiene后拟进入completion accepted commit的final staged blob只删除上述输入末尾一个空行，
  为59 lines / 3,033 bytes / SHA-256
  `1f58f3d8bbda7bf5e40e98ff91e3d49be22629b4251bfe8085e363a022496789`；authorization正文、语义与授权边界不变。
- 原始 handoff 中AgentCodex唯一 mutation 是新增本 ledger；本follow-up也只更新本ledger。两次均未修改production、
  tests、README、packaging、workflow、plan、control、既有review artifact、constraints或design，未stage、commit、
  push、创建PR或进入R12。
- R11 local implementation 已由 Controller 接受；local completion evidence 可验证。它不等于 Windows cross-platform
  closure、release closure、R11/umbrella closure或 draft-PR readiness。
- final local implementation ledger：accepted/open `0`、rejected/no-fix `1`、actual accepted residual `0`、
  local blocker `0`；真实 Windows run 单独保持 `PENDING_RELEASE_BLOCKER`。

## 2. Accepted plan provenance

最终 plan 真源为
[R11 accepted plan](../host/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan.md)。独立读取与 commit-blob
复核得到以下连续 accepted plan 链：

| Stage | Commit / parent | Subject | Plan lines / bytes / SHA-256 |
|---|---|---|---|
| initial accepted plan | `f7b452f992b4797b32fea7c6f7212b5ec4345ec1` / `2b14b2fbc89654267e3d33daa2ae410ceff45e68` | `docs: accept R11 upload workflow remediation plan` | 773 / 61,810 / `48bcfbaa648500d16a5148d4d0e4dba34db572a64c90e29ab8083242bd97d025` |
| atomic-cutover amendment | `a527ec030215e5bfcf9c4fad2f4a6fda243f5d65` / `f7b452f9…` | `docs: accept R11 atomic cutover plan amendment` | 889 / 75,526 / `55d35256f0f89f39f722438dc19d9ae65269b16810f96f1cd0129c6eba06d427` |
| I2 validation correction | `de476c452411e9d325d43b608de22b7236edfedb` / `a527ec03…` | `docs: accept R11 I2 validation plan correction` | 925 / 79,384 / `20f35e55573321ddfa474f772742097bb55963165936195de73785c39bc031dd` |
| I2 wheel-smoke correction / final | `7972c3c0ba8628173fc91c362b9394655f60678e` / `de476c45…` | `docs: accept R11 I2 wheel smoke plan correction` | 942 / 81,592 / `f1c95c3b5ecb1d6f01a2f15d1af6c96396ebb370c10997108a3c44dbd14b2ffd` |

最终 plan blob 在 `7972c3…`、accepted implementation commit和当前工作树三处 SHA-256 均为
`f1c95c3b5ecb1d6f01a2f15d1af6c96396ebb370c10997108a3c44dbd14b2ffd`。Plan acceptance、原子边界修订、
I2 validation 与 wheel-smoke correction 的 Controller evidence分别由
[initial plan re-review adjudication](./wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan-rereview-controller-adjudication.md)、
[final boundary re-review adjudication](./wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan-self-description-rereview4-controller-adjudication.md)、
[I2 validation plan-drift adjudication](./wu-semantic-ownership-01-r11-i2-validation-plan-drift-review-controller-adjudication.md)和
[I2 wheel-smoke plan-drift adjudication](./wu-semantic-ownership-01-r11-i2-wheel-smoke-plan-drift-review-controller-adjudication.md)
拥有。

## 3. Accepted implementation commit truth

独立使用 `git cat-file`、`git show`、`git diff-tree` 与 parent-to-commit diffcheck复核：

| Field | Verified truth |
|---|---|
| commit | `de4cf116c20c687f38cd3474b53949b0aedee5ab` |
| parent | `7972c3c0ba8628173fc91c362b9394655f60678e` |
| tree | `cf1d1aa6e205361c514a1c2522836459cb46a36a` |
| subject | `cli: accept R11 upload script remediation` |
| author / committer | `Leo Liu <leoliu2000@hotmail.com>` |
| authored / committed | `2026-07-18T05:54:45+08:00` |
| exact path count | `39` |
| product/test/README/packaging/workflow subset | exact `22` |
| control/evidence subset | exact `17` |
| parent-to-commit diffcheck | `git diff --check 7972c3… de4cf116…` exit `0` / zero output |
| full 22-path product binary diff | SHA-256 `eb01708a686716465eef366d9b7682108289349535ee8aad8db8feb7e01b7eb8` |

`6065289ee2a2da8d475de29fcd8b5d719ca1f0448e357e885a5ac0156fb6f424` 是 commit 前对 tracked
product tree 的 stopped binary-diff lock；当时两个 authorized additions仍未跟踪。上表的 `eb01708a…` 是 accepted
commit 中包含这两个 additions 后，对完整 22-path parent-to-commit diff重新计算的 hash；二者验证对象不同，不矛盾。

### 3.1 Exact 22-path product manifest

下表内容和删除状态均从 accepted commit tree独立读取；非删除项 SHA-256 是 commit blob bytes 的内容 hash：

| Status | Path | Commit truth |
|---|---|---|
| A | `.github/workflows/r11-upload-script-windows.yml` | `8eae09d59e69413adbb2c49dc60c3c431834bab7f230c410b9e981100d3f84c5` |
| M | `README.md` | `b6e1bcfc580e794fba2eb7528aacc6a6b0f8e8dd4763eb7b27ce5636460d8733` |
| M | `dayu/README.md` | `8b89eec6132f3cbd19d7e06660a7b380b79a85b5ef207aa17ffbbe1fe3ab994e` |
| M | `dayu/cli/arg_parsing.py` | `d8442bc64dd823cf92b09eec408a1b4437fae07a0f6b89b06afe9b25e7521b0e` |
| M | `dayu/cli/commands/fins.py` | `2b022641e2d19daaf73b8787e3240a6c4e041b7b36fd66965f466275d9a1797f` |
| A | `dayu/cli/upload_script.py` | `dfe0508deb905ef9bc21204a75a8ec55abf87ec254517831556dc7a8ba7aea65` |
| M | `dayu/fins/README.md` | `f93daf5bc3c29e4f19a76c2820a94e7973b713af543244e36a6dd0481fdbf218` |
| M | `dayu/fins/upload_batch.py` | `95c543801a75c4428b8d2022000d23be644c3a706ca12c06568a8f3e1eda74f0` |
| D | `dayu/render/__init__.py` | absent in commit tree |
| D | `dayu/render/render.py` | absent in commit tree |
| D | `dayu/web/__init__.py` | absent in commit tree |
| D | `dayu/web/__main__.py` | absent in commit tree |
| D | `dayu/wechat/__init__.py` | absent in commit tree |
| D | `dayu/wechat/main.py` | absent in commit tree |
| M | `pyproject.toml` | `b71fd9ff6435294752ec8de8cb0cc9f11bb4783f1a9e8944d9ce457a745c081e` |
| M | `requirements.txt` | `de025c19420211c2145f8533bbf0d2cf297229057b37c6caa48cc7930a9a4f63` |
| M | `tests/README.md` | `478efffcbf5d3e4f172ec5a7373e49996cf62f3b85a485fdcd60af7623f1c4c1` |
| M | `tests/cli/test_arg_parsing.py` | `d3a4abcc22093ff6c4e06edebf249282f1fbac9d9eb3a575c618f28210742658` |
| M | `tests/cli/test_fins_commands.py` | `297ecc542dd347b8ecf615814d001b6d71e639750cfca30b306815db9327afaa` |
| M | `tests/cli/test_public_package_entrypoints.py` | `e08d195e436e594e0bb7d2ca3b55a43b0b93080569dc0298a0c397ad9d8c0e0a` |
| M | `tests/cli/test_upload_filings_from_command.py` | `758e4e3db093e456c62d872c74046c17357214e9dbeacd133d0d8d914f728fd7` |
| M | `tests/fins/test_upload_batch.py` | `1e3967ecadd77c8688640f02783b9283390a32e1a01b316ac88f83323bc2a1cf` |

计数为 `14 M + 6 D + 2 A = 22`，与 final plan closed allowlist逐项相等。

### 3.2 Exact 17-path control/evidence subset

accepted commit 的其余 17 paths精确为：

1. `docs/host/issues-implementation-control.md`
2. `docs/reviews/wu-semantic-ownership-01-r11-cumulative-code-rereview-controller-adjudication.md`
3. `docs/reviews/wu-semantic-ownership-01-r11-cumulative-code-rereview-ds.md`
4. `docs/reviews/wu-semantic-ownership-01-r11-cumulative-code-rereview-mimo.md`
5. `docs/reviews/wu-semantic-ownership-01-r11-cumulative-code-review-controller-adjudication.md`
6. `docs/reviews/wu-semantic-ownership-01-r11-cumulative-code-review-ds.md`
7. `docs/reviews/wu-semantic-ownership-01-r11-cumulative-code-review-fix-codex.md`
8. `docs/reviews/wu-semantic-ownership-01-r11-cumulative-code-review-fix-controller-validation.md`
9. `docs/reviews/wu-semantic-ownership-01-r11-cumulative-code-review-mimo.md`
10. `docs/reviews/wu-semantic-ownership-01-r11-cumulative-controller-validation.md`
11. `docs/reviews/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-i1-controller-authorization.md`
12. `docs/reviews/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-i1-controller-validation.md`
13. `docs/reviews/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-i1-implementation-codex.md`
14. `docs/reviews/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-i2-continuation-controller-authorization.md`
15. `docs/reviews/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-i2-controller-authorization.md`
16. `docs/reviews/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-i2-implementation-codex.md`
17. `docs/reviews/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-i2-wheel-smoke-continuation-controller-authorization.md`

因此 `22 + 17 = 39`；无 `workspace/tmp`、wheel/dist、coverage、generated script、recorder或 secret artifact进入提交。

## 4. Final evidence index 与 artifact hashes

| Evidence | Lines / bytes | Independently verified SHA-256 |
|---|---:|---|
| [I1 Controller authorization](./wu-semantic-ownership-01-r11-upload-script-placeholder-removal-i1-controller-authorization.md) | 139 / 10,524 | `9af48935ae42472a212d3b6727347625d2be5018204490653c07a6eefbfbd26d` |
| [I1 implementation](./wu-semantic-ownership-01-r11-upload-script-placeholder-removal-i1-implementation-codex.md) | 230 / 14,386 | `2f8847dd5198c882045db01564c08cca1910cd8a5037f2f161f06dc749731c39` |
| [I1 Controller validation](./wu-semantic-ownership-01-r11-upload-script-placeholder-removal-i1-controller-validation.md) | 89 / 6,131 | `6418ade14976240c055c9a29e76c654b011ddc237c416a3a8a2c71c3e4d023a4` |
| [I2 initial authorization](./wu-semantic-ownership-01-r11-upload-script-placeholder-removal-i2-controller-authorization.md) | 126 / 10,042 | `8698fdf55a3f4a6adfb8ecbdb780019c67c1f38c9c10bc93563e62ec62b560ea` |
| [I2 continuation authorization](./wu-semantic-ownership-01-r11-upload-script-placeholder-removal-i2-continuation-controller-authorization.md) | 108 / 7,165 | `8e624c6e9684ed182f32097ece55c47db518fd9ff133dffb917f2a1ad0732b28` |
| [I2 wheel continuation authorization](./wu-semantic-ownership-01-r11-upload-script-placeholder-removal-i2-wheel-smoke-continuation-controller-authorization.md) | 83 / 6,120 | `2258eda0ff7bde58f71c8e4b600477c10a343a822cddf2336ff9818e93201420` |
| [I2 implementation](./wu-semantic-ownership-01-r11-upload-script-placeholder-removal-i2-implementation-codex.md) | 268 / 18,421 | `57fb654d2f484da7e72340eadfba6f8edab37b8aefb90cb784a7dae7667aa3ba` |
| [cumulative Controller validation](./wu-semantic-ownership-01-r11-cumulative-controller-validation.md) | 94 / 5,676 | `7023a71801a86f0f712ca320d25ea2cec06ef82d005458c352f280a6888902d1` |
| [initial DS review](./wu-semantic-ownership-01-r11-cumulative-code-review-ds.md) | 126 / 16,852 | `df6e61c3e947fca3450163eed4b6b2315f3e3cdf09a4736d6d3321fb56b8ccbf` |
| [initial MiMo review](./wu-semantic-ownership-01-r11-cumulative-code-review-mimo.md) | 46 / 6,814 | `e28a5473b34e2bacb26800aef22eb6efc1b6f8de8bec8070a36a621a29cdf18d` |
| [initial review Controller adjudication](./wu-semantic-ownership-01-r11-cumulative-code-review-controller-adjudication.md) | 100 / 7,091 | `87d27acd7d8af2db6079957914bebaa8a6c844a59aad2ab09e08bc77ec3e042e` |
| [bounded fix](./wu-semantic-ownership-01-r11-cumulative-code-review-fix-codex.md) | 250 / 16,204 | `c6e24041994a61afca3208e6f869807da29b8c7a91cb57c3bcfb9d5d34f7b753` |
| [fix Controller validation](./wu-semantic-ownership-01-r11-cumulative-code-review-fix-controller-validation.md) | 94 / 4,938 | `79afe277f3b6116c08455f211b4c91c07db1d4704cd9827782e8317c4d4f3d6d` |
| [DS complete re-review](./wu-semantic-ownership-01-r11-cumulative-code-rereview-ds.md) | 429 / 25,923 | `585e0fba2e04c72cad9eaa041a867e74eebcf2c6aaa07325859adfe497c8a15d` |
| [MiMo complete re-review](./wu-semantic-ownership-01-r11-cumulative-code-rereview-mimo.md) | 166 / 11,902 | `f428348dee73eed355144972d26086d93132b9bc15575a07c989d5dfc64d90cc` |
| [final re-review Controller adjudication](./wu-semantic-ownership-01-r11-cumulative-code-rereview-controller-adjudication.md) | 73 / 4,865 | `5d931006bb82131047fdde075f0db4323fc7211fa686a03af926b0504a32cf3c` |

Hash integrity note：accepted commit blob中的 fix Controller validation实际为 `94` lines / `4,938` bytes /
`79afe277…`。DS complete re-review 的输入表仍记载此前中间锁 `d514e74…` / 95 / 4,939；final Controller
adjudication与finding disposition没有依赖该旧值，accepted commit tree/path count与final finding ledger均一致。本 handoff
以 accepted commit blob truth 为准，按授权不修改历史 artifact；该 evidence cross-reference observation交给 Controller
completion validation复核，不把它重分类为产品 finding或accepted residual。

## 5. Complete finding ledger

### 5.1 Plan findings

| Finding group | Final disposition | Owner evidence |
|---|---|---|
| `R11-PR-F01`—`R11-PR-F06` | all `CLOSED` | [initial fixed-plan re-review adjudication](./wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan-rereview-controller-adjudication.md) |
| `R11-IMP-BF01` | `CLOSED`；S1/S2 broken intermediate boundary被改为一个原子 I1 producer-consumer cutover | [S1 stop adjudication](./wu-semantic-ownership-01-r11-s1-checkpoint-stop-controller-adjudication.md) / [final boundary adjudication](./wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan-self-description-rereview4-controller-adjudication.md) |
| `R11-PR-BF-RR-F01` | `CLOSED`；sequential edit、transient inconsistency与safety stop明确 | final boundary adjudication |
| `R11-PR-BF-FR-DS-F01/F02` | both `CLOSED`；requirements与FMP resolver exact source locks修正 | final boundary adjudication |
| `R11-PR-BF-FR-CV-F01` | `CLOSED`；`dayu/README.md` exact source lock修正 | final boundary adjudication |
| `R11-PR-BF-RR2-DS-F01/F02/F03` | all `CLOSED`；external OLD paths、umbrella plan与Q4 five-oracle semantics锁定 | final boundary adjudication |
| `R11-PR-BF-RR3-DS-F01` | `CLOSED`；plan不再拥有live gate/write authorization/ready marker | final boundary adjudication |
| `R11-I2-VAL-PD-F01` | `CLOSED`；root README contract test的I2 single-node ownership与22/8/15 allocation修正 | [I2 validation corrected-plan adjudication](./wu-semantic-ownership-01-r11-i2-validation-plan-drift-review-controller-adjudication.md) |
| MiMo validation-plan F01/F02 | both `REJECTED / NO PLAN FIX`；mandatory numbered requirement已明确direct no-`--infer`及no-JSON负向断言 | same adjudication |
| DS validation-plan LOW-O1—O3 | `OBSERVATION / NO FIX` | same adjudication |
| `R11-I2-VAL-PD-F02` | `CLOSED`；wheel archive与fresh constrained runtime oracle在validation owner处分离 | [I2 wheel-smoke corrected-plan adjudication](./wu-semantic-ownership-01-r11-i2-wheel-smoke-plan-drift-review-controller-adjudication.md) |
| initial Windows algorithm/`list2cmdline`、compatibility与其它 reviewer candidates | `REJECTED / NO ACTION`；未预猜算法、未保留旧default或compatibility surface | [initial plan review adjudication](./wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan-review-controller-adjudication.md) |

Plan final accepted/open `0`、actual accepted residual `0`、blocker `0`。Windows real-run是独立 release gate，
不是 plan residual。

### 5.2 Implementation/review findings

| Finding | Final disposition | Direct owner result |
|---|---|---|
| `R11-DS-F01` | `REJECTED / NO FIX` | Fins source containment与CLI output publication containment是两个独立security policy owner；没有直接drift/bypass证据，`dayu.runtime`未扩张。 |
| `R11-DS-F02` | `CLOSED / FIXED` | CLI删除material-form三值副本，只做trim/uppercase；normalized candidate进入Fins request，由Fins routing-table派生集合与validator唯一校验；owner/propagation tests通过。 |
| `R11-DS-F03` | `CLOSED / FIXED`（local evidence） | Windows tests在显式artifact root发布deterministic evidence，workflow只消费exact paths并校验hash/count；系统`%TEMP%`搜索、generic filter/copy归零。 |
| AgentMiMo initial material finding | `NONE` | initial review PASS。 |
| complete re-review new material finding | `0`（DS `0`，MiMo `0`） | 两路均完整重审22-path累计树并PASS。 |

Final local implementation accepted/open `0`、rejected/no-fix `1`、unclassified residual `0`、local blocker `0`。

## 6. Final tests、smokes与static evidence

以下值来自 bounded fix 后的最终累计树，并由
[fix evidence](./wu-semantic-ownership-01-r11-cumulative-code-review-fix-codex.md)、
[Controller fix validation](./wu-semantic-ownership-01-r11-cumulative-code-review-fix-controller-validation.md)和双路完整
re-review共同接受；本 artifact-only gate未冒充重新执行产品验证。

### 6.1 Tests and real smokes

| Gate | Final result | Decision |
|---|---|---|
| F02 Fins owner + CLI propagation | `2 passed, 3 warnings` | PASS |
| Windows local exact workflow nodes | `1 passed, 2 skipped, 3 warnings` | grammar PASS；两个skip只因macOS没有真实`cmd.exe`，不能关闭Windows gate |
| affected/focused cumulative | `155 passed, 2 skipped, 3 warnings` | PASS |
| Fins real filesystem typed-plan smoke | `1 passed` | PASS |
| real `/bin/sh` adversarial fixed/appended argv recorder | `1 passed, 3 warnings` | PASS；逐元素恢复且injection marker不存在 |
| real POSIX generated script → CLI → Service → Fins → temp storage | `1 passed, 3 warnings` | PASS；filing/material两类source terminal success |
| related `tests/cli tests/fins tests/service` | `2 failed, 1470 passed, 3 skipped, 3 warnings` | 只有两项HEAD-existing Service baseline；不是green |
| full `tests` | `2 failed, 5056 passed, 5 skipped, 5 deselected, 3 warnings` | 精确同两项baseline；无第三项/new R11 failure，不冒充green |

### 6.2 Fresh exact-wheel gate

- build：`python -m pip wheel --no-deps --no-build-isolation`；exact-one
  `dayu_agent-0.1.4-py3-none-any.whl`。
- final wheel：2,068,047 bytes / 424 archive members / SHA-256
  `f379d394cc1164b7bb79c9e93def3f941565cb0c29bf2c9da5dc066858145487`。
- fresh venv只对exact wheel执行一次
  `constraints/lock-macos-arm64-py311.txt` constrained normal install；未先用runtime `--no-deps`，未重复install。
- `pip check`：`No broken requirements found.`；top-level help与`upload_filings_from --help`均exit `0`。
- `dayu.web`、`dayu.wechat`、`dayu.render` importability均为`None`。
- METADATA placeholder contracts、placeholder entry points、extracted placeholder paths、RECORD placeholder paths均为`0`。

### 6.3 Coverage、pyright、Ruff、diff/scans

from-zero coverage suite为`147 passed, 2 skipped, 3 warnings`：

| Changed production file | Whole-file line coverage |
|---|---:|
| `dayu/fins/upload_batch.py` | `95.5696%` |
| `dayu/cli/commands/fins.py` | `90.8686%` |
| `dayu/cli/arg_parsing.py` | `99.6599%` |
| `dayu/cli/upload_script.py` | `91.3669%` |

- full pyright：`python -m pyright dayu/ tests/ utils/` → `0 errors, 0 warnings, 0 informations`。
- Ruff version：`ruff 0.15.11`；scoped changed production/test paths：`All checks passed!`。
- full Ruff locked baseline/current均`144` findings；`current_only=0`、`resolved=0`；两份JSON SHA-256均为
  `051bd6cc84fcd32adbd792c81c9e524438dd0532a92c7504ea2edf8234ec1cea`。
- final source/owner/propagation/placeholder/JSON/security/deferred scans按各自正负oracle通过；未用`noqa`、
  `type: ignore`、coverage pragma或baseline refresh隐藏finding。
- accepted commit parent-to-commit `git diff --check`通过；commit前 staged diffcheck也由Controller记录通过。

## 7. Exact Service baseline classification

Repository related/full suites不全绿，只有以下两项HEAD-existing baseline failure：

1. `tests/service/test_host_admin.py::test_prepare_host_admin_loads_only_host_runtime_without_models_or_secrets`：
   test fixture未提供当前required `wait_poller_policy`。
2. `tests/service/test_import_boundary.py::test_service_does_not_import_forbidden_layers`：三个既有Service→Fins
   sentinel命中：
   - `dayu/service/fins_direct.py` → `dayu.fins.direct_stream`；
   - `dayu/service/fins_wait_adapter.py` → `dayu.fins.tools._ingestion_tool_helpers`；
   - `dayu/service/host_assembly.py` → `dayu.fins.tools._ingestion_tool_helpers`。

`dayu/service/fins_direct.py`、`fins_wait_adapter.py`、`host_assembly.py`、`dayu/runtime/config_loader.py`与上述两个
Service test的working blob均由Controller逐项证明等于`HEAD:<path>` blob，且R11对这些owner paths为零diff。因此两项
失败不是R11引入，R11没有越权修复、waive、xfail、hide或将full suite写成green；其owner/destination仍是独立Service
baseline治理，不属于R11 residual或Windows gate。

## 8. README、packaging与placeholder closure

- root [README](../../README.md)：按最终用户owner说明batch-only `--infer` / `FMP_API_KEY`、`auto`、ticker CSV、
  default/explicit output、POSIX `.sh` / Windows `.cmd`、追加参数、检查/执行与排障；direct upload不暴露`--infer`，
  旧JSON argv `schema_version=1` / `commands`和“不生成shell”文案不存在。
- [dayu README](../../dayu/README.md)：只列真实package，删除把Web/WeChat/render placeholder写成稳定边界的承诺；未改分层或
  future capability。
- [Fins README](../../dayu/fins/README.md)：说明typed scan/classification/fiscal/material/caps/skip的Fins owner与CLI
  mechanical consumer边界。
- [tests README](../../tests/README.md)：同步owner tests、三项POSIX real smoke、真实Windows nodes、packaging negative
  contract与workflow evidence；明确非Windows skip不能替代真实runner。
- packaging只保留真实`dayu-cli` entrypoint；删除placeholder scripts、`web` extra/requirements消费与
  `dayu.render` package-data。
- 六个placeholder source files在accepted tree全部absent；wheel METADATA、entry points、archive、RECORD与fresh-wheel
  importability五层oracle均为零残留。
- `tests/tools/web`中两个禁止旧`dayu.web` import的read-only negative sentinels保持，未误删真实`dayu.tools.web`能力。

## 9. Security behavior and explicit non-implementation

### 9.1 Retained or strengthened behavior

- source containment仍由Fins owner执行lexical/resolved containment、root-self/internal component/candidate symlink拒绝，
  external ancestor symlink允许。
- output containment与publication仍由CLI publisher独立执行相同边界类别，并使用same-directory private temp、
  flush+fsync、`os.replace`、POSIX mode、failure/interrupt cleanup与old-target rollback/preservation。
- POSIX renderer继续使用`shlex.join` + `"$@"`；Windows renderer继续使用single batch-percent + CRT quoting、
  `setlocal DisableDelayedExpansion`与`%*`，无`list2cmdline`、`shell=True`、delayed-expansion re-enable、fallback或shim。
- fixed/adversarial/appended argv逐元素oracle与injection-marker absence保持；F03只把Windows test/workflow evidence locator
  改为deterministic exact paths，没有改变production quoting。
- `FMP_API_KEY`、sentinel secret、provider URL与网络调用不持久化到generated script executable body；`--infer`只可出现在
  无secret的regeneration comment，不进入每条direct command；stdout与artifacts同样接受secret scan。

### 9.2 Explicitly not implemented

R11只交付上述局部path/symlink/atomic-write/argv-injection/secret防御；没有实现或声称统一tool authorization framework，
没有workspace trust模型，没有shell sandbox，也没有把这些Host/Engine治理语义伪装成脚本生成安全。Topic 9维持
`NO CODE`，`R11-DS-F01`的runtime抽取建议也明确rejected/no-fix。

## 10. Deferred/no-touch ledger

| Deferred scope | R11 truth | Owner / destination |
|---|---|---|
| Issue 142 / 151 / 175 / 177 / 178 | no production/design diff；未偷带 | 各自既有issue owner |
| Topic 8 | Engine 240-char redacted/truncated exception projection无diff | umbrella既有`NO CODE`裁决 |
| Topic 9 / unified authorization | 未实现 | umbrella既有`NO CODE`裁决 |
| real Web/WeChat/render capability | placeholder surface被删除，但未实现真实未来能力 | 既有tracker，不由R11创建重复issue |
| Service/Host/Engine/runtime/config/tool/UI/constraints/design | final deferred scan为零product diff | 各自owner；R11 no-touch |
| R12 / init/provider/model/API-key/prewarm | 未进入 | 后续只有新Controller authorization才可开始 |

## 11. Residual and blocker ledger

| Category | Count / status | Owner / destination |
|---|---|---|
| accepted/open R11 finding | `0` | none |
| actual accepted residual | `0` | none |
| rejected/no-fix finding | `1`：`R11-DS-F01` | final Controller adjudication；保持两个独立policy owner |
| HEAD-existing Service baseline | `2` exact failures | 独立Service baseline治理；不归R11 |
| local R11 blocker | `0` | none |
| Windows cross-platform release blocker | `PENDING_RELEASE_BLOCKER` | R11 Windows workflow + Controller release validation |

Windows pending不能被重分类为accepted residual，也不能由local renderer unit、YAML parse或macOS skip关闭。

## 12. Windows `PENDING_RELEASE_BLOCKER` closure contract

### 12.1 Required trigger and run identity

- workflow：`.github/workflows/r11-upload-script-windows.yml`，name `R11 upload script Windows gate`。
- 后续必须先获得push/PR相关Controller authorization；本 handoff不发布branch。
- trigger只能是`workflow_dispatch`或`pull_request`命中workflow中精确22个product paths之一；不能用schedule、release、
  deployment、secret/provider或宽glob替代。
- run必须是GitHub-hosted `windows-latest`、Python 3.11、30-minute timeout、`contents: read`，checkout的event/head commit
  必须对应包含本R11 workflow与accepted implementation product tree的目标tree；Controller必须对照Actions run metadata与
  commit/tree，不能拿其它branch、旧workflow或旧renderer run冒充。
- install必须精确使用
  `python -m pip install -e ".[test,dev]" -c constraints/lock-windows-x64-py311.txt`。

### 12.2 Required test nodes

一次run必须执行且不得skip以下三个exact nodes：

1. `tests/cli/test_upload_filings_from_command.py::test_windows_cmd_script_round_trips_adversarial_argv_with_real_cmd`
2. `tests/cli/test_upload_filings_from_command.py::test_windows_generated_script_runs_real_cli_into_temp_storage`
3. `tests/cli/test_arg_parsing.py::test_upload_actions_default_to_auto_and_batch_rejects_delete`

前两个必须真实调用`cmd.exe /d /c`；不得以renderer unit、fake recorder或非Windows skip替代。

### 12.3 Required uploaded artifact

- Actions artifact name：`r11-windows-upload-script-${{ github.run_id }}`。
- upload path：`workspace/tmp/r11-windows/**`；`if: always()`；retention `14` days；
  `if-no-files-found: error`。
- 下载并解压后至少必须存在且可读：
  - `environment.txt`
  - `cmd-help.txt`
  - `pytest-stdout.txt`
  - `pytest-stderr.txt`
  - `pytest-junit.xml`
  - `cmd-recorder/generated-upload.cmd`
  - `cmd-recorder/recorder-oracle.jsonl`
  - `cli-storage/cli-generated-upload.cmd`
  - `cli-storage/cli-grammar-oracle.json`
  - `cli-storage/portfolio/**`中的真实source/storage artifacts。

### 12.4 Required oracles

- Actions job与三个pytest nodes全部success，JUnit无skip/cancel/failure；runner evidence明确是Windows/Python 3.11，
  `cmd.exe /?`成功。
- recorder oracle精确只有一行；JSON argv逐元素等于fixed
  `("", "space value", "中文", "quote\"value", "trail\\", "%PATH%", "!", "&")`
  加appended `("appended value", "& type nul > <marker>")`；injection marker不存在。
- CLI evidence必须满足：
  `test_node == "test_windows_generated_script_runs_real_cli_into_temp_storage"`、`result == "passed"`、
  `cmd_invocation == "cmd.exe /d /c"`；`generated_script_sha256`等于实际
  `cli-generated-upload.cmd` SHA-256；`source_artifact_count > 0`且精确等于`cli-storage/portfolio`中的实际文件数。
- 真实CLI smoke必须exit `0`、有terminal success且产生temp-storage source artifacts；grammar node必须继续证明direct
  action与batch no-delete/default-auto contract。
- generated `.cmd`、stdout/stderr、oracle与其它上传evidence不得包含API key、sentinel secret或provider URL；不得出现
  `list2cmdline`、fallback、compatibility shim或delayed-expansion bypass。
- Controller必须同时核对Actions event/head SHA与目标commit/tree、artifact name/path/retention、exact 22-path workflow
  contract和implementation evidence中的quoting invariant；缺任一项都不能关闭gate。

### 12.5 Failure loop

以下任一情况都保持/恢复`PENDING_RELEASE_BLOCKER`并阻止umbrella aggregate acceptance、draft PR ready与final closeout：

- run未执行、对应错误commit/tree、skipped、cancelled、timed out或job/test失败；
- artifact缺失、过期前未读取、name/path/retention不符、required file缺失或secret scan失败；
- recorder行数/argv不等、injection marker存在、CLI oracle字段/hash/count不等、terminal success或storage artifact缺失；
- 为通过gate引入`list2cmdline`、fallback、shim、宽locator或降级成unit test。

失败必须回到同一R11正确owner做narrow fix，重跑受影响与完整累计validation，重新code review/fix/re-review并由Controller
裁决；不新建WU、不进入R12、不转accepted residual、不waive。只有真实run全部oracles通过后，Controller才能把Windows
状态改为`CLOSED`。

## 13. Working/staged state and next checkpoint

- accepted implementation commit后，Controller在
  [completion authorization](./wu-semantic-ownership-01-r11-completion-controller-authorization.md)与
  control transition中记录的历史快照是working tree empty、staged tree empty。
- 本 handoff最初写入前独立当前态复核：HEAD仍为`de4cf116…`；当时staged set为空；working set只有Controller-owned
  `M docs/host/issues-implementation-control.md`与untracked completion authorization。control diff精确把gate从
  `R11 exact-scope accepted implementation local commit`推进到`R11 artifact-only completion handoff`并记录commit truth；
  这两项是post-commit handoff state，不推翻历史post-commit empty snapshot。
- 最初新增本 ledger后，working set只增加
  `?? docs/reviews/wu-semantic-ownership-01-r11-completion-codex.md`，且当时staged set继续为空；这是原始handoff快照。
- 随后的同任务Controller stage-hygiene只把authorization的commit候选从review-time 60-line blob收敛为上述59-line
  final staged blob；本follow-up只更新本 ledger以区分两个时点，不修改authorization或其它文件，也不改变Controller已建立
  的index/staging状态。最终stage与accepted commit仍只由Controller执行和验证。
- 本 ledger写入后只做artifact hash、diffcheck、exact status/manifest复核；不重跑已接受的产品验证冒充新evidence。
- 下一且唯一gate是Controller completion validation；只有它通过后才可能授权一次artifact-only completion accepted local
  commit。R12、push、PR、aggregate/release closure仍未授权。

CONTROLLER_COMPLETION_CHECKPOINT
