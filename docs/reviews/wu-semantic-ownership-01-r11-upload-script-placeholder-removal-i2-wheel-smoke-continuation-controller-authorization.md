# WU-SEMANTIC-OWNERSHIP-01 / R11-I2 wheel smoke continuation Controller authorization

## 1. 唯一 live authorization

本文件 supersede 先前两份 R11-I2 authorization，恢复同一 umbrella WU / 同一 R11-I2 implementation task。它不是新 WU、新 slice、独立 acceptance 或 review fix。

不得 stage、commit、push、创建 PR、进入 cumulative code review、R12 或 umbrella aggregate。完成 corrected plan 的剩余 wheel/final cumulative validation与唯一 I2 implementation artifact后停在 Controller checkpoint。

## 2. Accepted plan 与当前 tree locks

- branch：`phaseflow/host-issues-control`；
- accepted wheel-smoke plan-correction commit：`7972c3c0ba8628173fc91c362b9394655f60678e`，parent `de476c452411e9d325d43b608de22b7236edfedb`；
- corrected plan：942 lines / 81,592 bytes / SHA-256 `f1c95c3b5ecb1d6f01a2f15d1af6c96396ebb370c10997108a3c44dbd14b2ffd`；
- plan-review ledger：accepted/open `0`、rejected `0`、blocker `0`、unclassified residual `0`；
- stopped product/test/README/packaging/workflow binary diff：`6c8284c6fdcfc4661a0bcd00f1c155d34985fa4af81fa400158ce3a034acd0e6`；
- staged set：empty；
- Ruff baseline：144 findings / SHA-256 `051bd6cc84fcd32adbd792c81c9e524438dd0532a92c7504ea2edf8234ec1cea`。

七个 non-shared I1 paths必须保持 read-only，hash 仍为：

| path | SHA-256 |
|---|---|
| `dayu/fins/upload_batch.py` | `7cbc1f6aa167088ebe3c89a46cb712981e2e93227bf001ec8ed12fb251512ad9` |
| `tests/fins/test_upload_batch.py` | `51ae67a8f811feb64394dbcae0a86c337c216ae0c0a665a6542ca54a8679d23c` |
| `dayu/cli/upload_script.py` | `dfe0508deb905ef9bc21204a75a8ec55abf87ec254517831556dc7a8ba7aea65` |
| `dayu/cli/arg_parsing.py` | `d8442bc64dd823cf92b09eec408a1b4437fae07a0f6b89b06afe9b25e7521b0e` |
| `dayu/cli/commands/fins.py` | `13bab3f4a1ac3eeece61c4cfb1169f68d2ac20da08afa6a4d5aeb7e63f75c0a3` |
| `tests/cli/test_upload_filings_from_command.py` | `14e1bff29c9a1f7efce61bf4891d3f6c099bb43931d54d4ef586d1df9b7ca3cd` |
| `tests/cli/test_fins_commands.py` | `297ecc542dd347b8ecf615814d001b6d71e639750cfca30b306815db9327afaa` |

Current I2 locks：workflow `4026da55...0953`；shared test `d3a4abcc...2658`；`tests/README.md` `478efffc...4c1`；six placeholder files absent。其余 I2 path lock以当前 stopped diff `6c8284c6...d0e6` 为整体真源。

## 3. Exact scope

产品实现已完成，默认不得再 mutation。若 mandatory validation发现真实 R11 root cause，只能在 accepted plan §4 的 exact 15-path I2 allowlist内修复，并立即重新执行受影响及最终 cumulative validation；任何 owner、contract、allowlist、lock、workflow scope或 deferred boundary变化必须 stop 回 Controller。

允许新建/更新唯一 evidence：

`docs/reviews/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-i2-implementation-codex.md`

Controller control、plan、既有 review/authorization/I1 artifacts均 read-only。`workspace/tmp/**` 只承载机械验证产物，不得 stage。

## 4. Immediate continuation

不得重做已经通过且 tree 未变化的设计修改。先重新确认 stopped diff、I1 locks、I2 current locks和 staged-empty，然后从 corrected plan §7.3 的 fresh wheel gate完整重跑：

1. 清理并重建 `workspace/tmp/r11-dist`、`r11-wheel-extract`、`r11-wheel-venv`；
2. wheel build仍用 `python -m pip wheel --no-deps --no-build-isolation`；
3. archive/METADATA/entrypoints/extracted paths/RECORD negative oracles全部执行；
4. fresh venv仅一次 normal install exact built wheel，使用 `--constraint constraints/lock-macos-arm64-py311.txt`；
5. 顺序执行 `pip check`、`python -m dayu.cli --help`、`python -m dayu.cli upload_filings_from --help`、placeholder importability oracle；
6. dependency resolution/download/install、lock、`pip check` 或任一 runtime oracle失败均按真实 packaging gate failure停止并保留证据。

禁止 runtime `--no-deps`、重复 install、lazy import、fallback、fixture/sys.path shim、修改 constraints/lock、修改 Windows workflow或扩大产品/测试范围。

## 5. Mandatory final cumulative validation

wheel gate通过后完成 corrected plan §7.3 与 §8 全部 final cumulative gates，至少包括：

- focused I1+I2 tests、public packaging tests、POSIX recorder smoke、POSIX real CLI-to-temp-storage smoke；
- related/full suites；两项已裁决的 HEAD-existing Service failures必须精确披露，任何新增 failure stop；
- changed production whole-file coverage全部 `>=80%`；
- full pyright零错误；scoped Ruff零错误；full Ruff locked 144 baseline的 current-only/resolved均零；
- exact cumulative `22`-path allowlist、I1 `8` / I2 `15` allocation、shared-function-only diff、七个 I1 hashes、staged-empty、`git diff --check`；
- placeholder/JSON/public script/README/source/security/secret/deferred/no-unified-auth scans；
- README trigger matrix与四份 README owner人工复核；
- Windows-only nodes在 macOS明确 skip，workflow local contract完整；真实 GitHub `cmd.exe` run保持 `PENDING_RELEASE_BLOCKER`。

不得把 `git ls-files` 仍列出 unstaged deletions伪装成 working-tree残留；working-tree absence、diff deletion status、wheel/archive/RECORD/importability才是当前 local oracle。

## 6. Stop conditions

出现 allowlist外 diff、shared function外 delta、I1 hash变化、Controller/plan/既有 artifact变化、staged content、新 test/static/coverage/security failure、真实 non-placeholder consumer、需要 tracker/deferred能力或 unified authorization时立即停止。不得实施 Issue 142/151/175/177/178、Topic 8/9 code、Web/WeChat/render真实能力或兼容 shim。

## 7. Handoff

唯一 I2 implementation artifact必须记录 final path/hash manifest、shared-function diff proof、tests/coverage/pyright/Ruff、wheel constrained install与 runtime oracle、README/security/deferred scans、两项既有 Service failure、Windows pending blocker与 staged-empty。末行写：

`READY_FOR_CONTROLLER_R11_I2_CHECKPOINT`

然后停止。

AUTHORIZED_R11_I2_WHEEL_SMOKE_CONTINUATION_ONLY
