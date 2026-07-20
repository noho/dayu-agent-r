# WU-SEMANTIC-OWNERSHIP-01 / AR-F07 WIN4-RW-RF01 One-test Code-review Zero-change Fix — AgentCodex

## Gate identity and result

- Timestamp：`2026-07-20T10:01:35+0800`。
- Umbrella：`WU-SEMANTIC-OWNERSHIP-01`；当前 gate 是既有 `AR-F07 WIN4-RW-RF01` one-test code-review fix，
  不是新 WU。
- Agent：`AgentCodex`。
- Mechanical base：`39926eb85aa25441f5209a128a3c971f451b5b25`。
- Frozen binary/full-index code diff SHA-256：
  `fcecb15cc3f09707077a6cf016ac28b960fb13013f1dcda92d4db092734f2169`。
- Frozen implementation artifact SHA-256：
  `f9b36d4b58d4a81c845058790f6d99d8b7994b8a35410a79242aed606163f42e`。
- Frozen Controller code-review adjudication SHA-256：
  `1dceeeb2b9d58c3e0bf1a700c19ca7f7dbfb26f1fcc2c5a6e6ab9844fdd4f569`。
- Controller verdict：`PASS / ACCEPTED_CODE_FINDING=0 / BLOCKER=0 / ZERO_CHANGE_FIX_REQUIRED`。
- 本 gate 结果：
  `ZERO_CHANGE_FIX_PASS / ACCEPTED_FINDING=0 / CODE_TEST_PRODUCT_README_PLAN_CONTROL_EXISTING_REVIEWS_UNCHANGED /
  REAL_WINDOWS_PENDING / STOPPED_BEFORE_CONTROLLER_VALIDATION`。
- 本 gate 唯一新增文件是本文。没有修改任何既有代码、test、product、README、plan、control、implementation artifact、
  Controller validation或既有 review artifact。

## Read inputs and immutable locks

| Input | Lines | SHA-256 | Disposition |
| --- | ---: | --- | --- |
| `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-fresh-windows-test-oracle-code-review-mimo.md` | `160` | `0fbf17bb730ec1b3cb4cb1093135acd3516de342b5e4a38caf312cefdb84d7b2` | `PASS / finding 0 / blocker 0 / open 0 / backflow 0` |
| `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-fresh-windows-test-oracle-code-review-ds.md` | `239` | `c60a8db64800f37a26fdb1a384b5f980ad8d434b1a7ca765cc414a4ddbb78b4d` | `PASS / material finding 0 / blocker 0 / open 0 / backflow 0` |
| `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-fresh-windows-test-oracle-code-review-controller-adjudication.md` | `47` | `1dceeeb2b9d58c3e0bf1a700c19ca7f7dbfb26f1fcc2c5a6e6ab9844fdd4f569` | Controller接受code finding `0` |
| `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-fresh-windows-test-oracle-implementation-codex.md` | `150` | `f9b36d4b58d4a81c845058790f6d99d8b7994b8a35410a79242aed606163f42e` | one-test implementation evidence |
| `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-fresh-windows-test-oracle-implementation-controller-validation.md` | `61` | `382fbf2f4a16ee1a3492b5d712212372820e2599b0595ab72b6ab6a38378e672` | `PASS / EXACT_ONE_TEST_BLOCK / PRODUCT_DIFF_ZERO` |
| `docs/host/wu-semantic-ownership-01-ar-f07-win4-remediation-plan.md` | `1124` | `571ca834a515620283447a6c2166fc7bbd5dcf9393b685457a0ee7e959dc7ff2` | accepted corrected plan truth |
| `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-fresh-windows-corrected-plan-accepted-commit-controller-validation.md` | `54` | `abc848714f23a4528711bef419609ab83bb8e3642dabc6fc00bacd3102d27d8b` | accepted corrected-plan commit `e2c9a31b25fb6d87e6fb4d618bb4043f556a55b0` |
| `docs/host/issues-implementation-control.md` | `2411` | `b4524533d9ea69829b9be042e9f897c5281fc9363d35b494c06b1eb9d7700323` | 当前 gate与next entry point真源；本 gate零修改 |

上述 implementation、Controller validation、两路 review、Controller adjudication、accepted plan与control均已读取。

## First-principles and semantic-owner judgment

两路完整 code review均未证明新的 correctness、stability、maintainability、安全或语义所有权缺陷，Controller accepted code
finding精确为 `0`。当前实现已经在唯一正确 owner——
`tests/cli/test_upload_filings_from_command.py::test_windows_generated_script_runs_real_cli_into_temp_storage` 的既有 snapshot
assertion block——分别消费两个 public facts：Fins-owned primary exact-one membership，以及 raw-source exact-name/public
SHA-256 publication。没有新的 owner defect可供修复。

因此修改 product、test、Fins contract、README、plan、control或review内容不会关闭任何 accepted finding，反而会越过冻结
scope并制造新的语义所有权漂移。最佳实践且最小充分的 fix disposition只能是保持全部既有字节不变并产出本 zero-change记录。

AgentMiMo记录的 POSIX sibling test assertion asymmetry明确按 Controller裁决消费为
`PRE_EXISTING / OUT_OF_SCOPE / NON_FINDING / NO_ACTION`：它不是本次 one-test diff引入的行为，不影响 Windows owner contract，
不进入 fix、residual ledger或后续隐含范围。

## Frozen diff identity and plain-diff explanation

冻结 identity使用：

```bash
LC_ALL=C git diff --binary --full-index --no-ext-diff --no-renames \
  39926eb85aa25441f5209a128a3c971f451b5b25 -- \
  tests/cli/test_upload_filings_from_command.py | shasum -a 256
```

Fresh结果仍为：
`fcecb15cc3f09707077a6cf016ac28b960fb13013f1dcda92d4db092734f2169`。

作为对照，plain命令：

```bash
LC_ALL=C git diff 39926eb85aa25441f5209a128a3c971f451b5b25 -- \
  tests/cli/test_upload_filings_from_command.py | shasum -a 256
```

Fresh结果为：
`f4dd51eb87776d7ee63758f9e19dd8e627cf30aa7f323fe4694da809f463a2f7`。

`f4dd...` 的输入没有 `--binary --full-index --no-ext-diff --no-renames`；尤其 index行使用缩写object id，因而与冻结命令产生
不同的diff byte stream。两个摘要对应不同命令输入，不是同一identity的mismatch，不是代码漂移，也不是finding。

目标test文件内容 SHA-256在本 gate入口与终态均为
`3827b569fea759e6feaaba657b27a41a3303bde787d784e52677dd49a69ad110`；冻结diff仍只有目标函数现有 assertion block的单一hunk。

## Zero-change disposition by scope

| Scope | Disposition | Evidence |
| --- | --- | --- |
| code / target test | 零改动 | binary/full-index diff SHA保持 `fcecb15c...f2169`；test文件内容SHA保持 `3827b569...ad110` |
| product `dayu/` | 零改动 | 相对mechanical base的 `git diff --name-only ... -- dayu` 无输出 |
| README | 零改动 / `NO UPDATE REQUIRED` | 相对base的根README与全部README path scan无输出；本 gate不改变用户或测试工作流 |
| accepted plan | 零改动 | `1124` lines / SHA-256 `571ca834...c7ff2` 保持不变 |
| control | 零改动 | 入口与终态SHA-256均为 `b4524533...0323` |
| implementation / Controller validation | 零改动 | SHA-256分别保持 `f9b36d4b...3f42e` / `382fbf2f...672` |
| 两路 review / adjudication | 零改动 | SHA-256分别保持 `0fbf17bb...d7b2` / `c60a8db...8b4d` / `1dceeeb2...f569` |
| workflow / design / schema / oracle | 零改动 | 不属于accepted finding或本gate allowlist |

## Fresh validation and forbidden scans

所有Python命令均在 `source .venv/bin/activate` 后fresh执行。

| Validation | Fresh result |
| --- | --- |
| `pytest tests/cli/test_upload_filings_from_command.py -q` | `20 passed, 2 skipped, 3 warnings in 13.12s` |
| Windows exact node | `1 skipped, 3 warnings in 1.17s`；本机macOS缺少真实 `cmd.exe`，只记录platform skip，不声称closure |
| `python -m pyright dayu/ tests/ utils/` | `0 errors, 0 warnings, 0 informations` |
| `python -m ruff check tests/cli/test_upload_filings_from_command.py` | `All checks passed!` |
| `git diff --check` | PASS / 无输出 |
| `git diff --cached --name-only` | 空；staged tree empty |
| product path scan | `dayu/` 相对base零diff |
| README path scan | 根README与全部README相对base零diff |
| display/stream/physical-oracle additions | `Fins result/summary/progress/succeeded/failure/cancelled`、`execution.stdout/stderr`、新增 `rglob(` 命中 `0` |
| primary/Docling additions | `_docling.json`、`DOCLING_FILE_SUFFIX`、`docling`、`primary_filename == source_path.name` 命中 `0` |
| private storage additions | `source_meta`、`meta.json`、`private`、`_core`、`materialize_files=True`、`get_source(` 命中 `0` |
| structure/fallback additions | 新 `def/class`、oracle string-key、`hasattr/getattr`、fallback 命中 `0` |
| import additions | 新 `import/from ... import` 命中 `0` |

pytest的三个warning均来自未修改的installed `edgar` deprecated imports。pyright的新版本提示只是工具更新提示，不是类型诊断。

## Findings, residual risk and completion boundary

- Accepted/open code finding：`0`；new/backflow finding：`0`；blocker/open/design contradiction：`0`。
- POSIX assertion asymmetry：`PRE_EXISTING / OUT_OF_SCOPE / NON_FINDING / NO_ACTION`。
- 唯一 residual：真实 Windows仍为 `PENDING`。它不是code finding或waiver；owner/destination唯一是Controller在accepted
  implementation与aggregate gates后执行fresh R11与R12（含embedded R11），并按accepted plan验证两个独立descriptor facts与
  same-run evidence。
- 若fresh R11/R12失败，必须回到Controller diagnostic-first owner裁决；不得恢复primary==raw、硬编码Docling expected primary、
  读取private meta/path或修改Fins contract迁就测试。
- 本 gate未stage、commit、push、workflow dispatch、Agent/reviewer dispatch或进入re-review，也未修改control或计划。
- 当前停止。唯一后续入口是Controller validation本zero-change record；本 AgentCodex不自行进入双路re-review。

Artifact path：
`docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-fresh-windows-test-oracle-code-review-fix-codex.md`。
