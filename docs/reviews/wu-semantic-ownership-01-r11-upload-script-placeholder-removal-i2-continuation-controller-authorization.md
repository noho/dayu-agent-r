# WU-SEMANTIC-OWNERSHIP-01 / R11-I2 continuation Controller authorization

## 1. 唯一 live authorization

本文件 supersede 先前 I2 authorization，恢复同一 umbrella WU / 同一 R11-I2 implementation task。它不是新 WU、第三 slice、独立 acceptance或 review fix。当前 partial I2 tree在 validation plan-drift gate期间被保护，现以 accepted corrected plan继续。

不得 stage、commit、push、创建 PR、进入 cumulative code review、R12 或 umbrella aggregate。完成 I2 exact implementation、全部 cumulative validation与唯一 implementation artifact后停在 Controller checkpoint。

## 2. Accepted plan 与 stopped-tree locks

- branch：`phaseflow/host-issues-control`；
- HEAD / accepted plan amendment commit：`de476c452411e9d325d43b608de22b7236edfedb`，parent `a527ec030215e5bfcf9c4fad2f4a6fda243f5d65`；
- corrected plan：925 lines / 79,384 bytes / SHA-256 `20f35e55573321ddfa474f772742097bb55963165936195de73785c39bc031dd`；
- plan review ledger：accepted/open `0`、rejected `2`、observation `3`、blocker `0`；
- stopped product/test/README/packaging tracked diff：`718846cdd5ce3ad8d9d789b3b7b47e18df8943ac541f63a925dd696b06fe8332`；
- staged set：空；
- Ruff baseline：144 findings / SHA-256 `051bd6cc84fcd32adbd792c81c9e524438dd0532a92c7504ea2edf8234ec1cea`。

七个 non-shared I1 paths全程 read-only：

| path | SHA-256 |
|---|---|
| `dayu/fins/upload_batch.py` | `7cbc1f6aa167088ebe3c89a46cb712981e2e93227bf001ec8ed12fb251512ad9` |
| `tests/fins/test_upload_batch.py` | `51ae67a8f811feb64394dbcae0a86c337c216ae0c0a665a6542ca54a8679d23c` |
| `dayu/cli/upload_script.py` | `dfe0508deb905ef9bc21204a75a8ec55abf87ec254517831556dc7a8ba7aea65` |
| `dayu/cli/arg_parsing.py` | `d8442bc64dd823cf92b09eec408a1b4437fae07a0f6b89b06afe9b25e7521b0e` |
| `dayu/cli/commands/fins.py` | `13bab3f4a1ac3eeece61c4cfb1169f68d2ac20da08afa6a4d5aeb7e63f75c0a3` |
| `tests/cli/test_upload_filings_from_command.py` | `14e1bff29c9a1f7efce61bf4891d3f6c099bb43931d54d4ef586d1df9b7ca3cd` |
| `tests/cli/test_fins_commands.py` | `297ecc542dd347b8ecf615814d001b6d71e639750cfca30b306815db9327afaa` |

唯一 shared path before-lock：`tests/cli/test_arg_parsing.py` SHA-256 `7cdc4c1d014bc7012aca28f05927b8afbbd04b86cc6d0aa2dfbf5f87af91ece6`。本 continuation 只能修改 `test_root_readme_matches_current_cli_public_contract`；同文件其它内容不得变化。

## 3. Exact 15-path I2 allowlist

只允许继续修改/新增/删除：

1. `pyproject.toml`
2. `requirements.txt`
3. `.github/workflows/r11-upload-script-windows.yml`
4. 删除 `dayu/web/__init__.py`
5. 删除 `dayu/web/__main__.py`
6. 删除 `dayu/wechat/__init__.py`
7. 删除 `dayu/wechat/main.py`
8. 删除 `dayu/render/__init__.py`
9. 删除 `dayu/render/render.py`
10. `tests/cli/test_public_package_entrypoints.py`
11. `tests/cli/test_arg_parsing.py`，仅限上述单一函数
12. `README.md`
13. `dayu/README.md`
14. `dayu/fins/README.md`
15. `tests/README.md`

另可新增唯一 evidence：`docs/reviews/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-i2-implementation-codex.md`。

partial I2 entry locks：

| path | entry SHA-256 / state |
|---|---|
| `pyproject.toml` | `b71fd9ff6435294752ec8de8cb0cc9f11bb4783f1a9e8944d9ce457a745c081e` |
| `requirements.txt` | `de025c19420211c2145f8533bbf0d2cf297229057b37c6caa48cc7930a9a4f63` |
| workflow | `4026da55c789c0f3f961887f3f19536c7817abad4665ffd78b493219f2560953` |
| six placeholder files | all absent in working tree |
| `tests/cli/test_public_package_entrypoints.py` | `e08d195e436e594e0bb7d2ca3b55a43b0b93080569dc0298a0c397ad9d8c0e0a` |
| shared test file | `7cdc4c1d014bc7012aca28f05927b8afbbd04b86cc6d0aa2dfbf5f87af91ece6` |
| `README.md` | `b6e1bcfc580e794fba2eb7528aacc6a6b0f8e8dd4763eb7b27ce5636460d8733` |
| `dayu/README.md` | `8b89eec6132f3cbd19d7e06660a7b380b79a85b5ef207aa17ffbbe1fe3ab994e` |
| `dayu/fins/README.md` | `f93daf5bc3c29e4f19a76c2820a94e7973b713af543244e36a6dd0481fdbf218` |
| `tests/README.md` | `64787842c7f6b930948acd8f0761da44729e0a035eb7bfc31078e4a70b567f97` |

Controller control、plan、所有 existing review/authorization/I1 artifacts均 read-only。`workspace/tmp/**` 只放机械验证产物，不得 stage。

## 4. Immediate accepted fix

先只修改 shared function：

- 从旧全局 forbidden set 删除 `--infer`；
- 删除旧 JSON argv / no-shell 正向 assertions；
- 正向断言 batch `upload_filings_from`、`--infer`、`FMP_API_KEY`、POSIX `.sh` / Windows `.cmd` 与 `/bin/sh` / `cmd.exe /d /c`；
- 负向断言 direct upload没有 `--infer`，旧 `schema_version=1` / `commands` JSON协议和“不生成 shell”文案不存在；
- 保留其它 removed/unimplemented contract assertions。

不得把 parser help fixture或另一套 schema塞进 README owner test；可用 README section/context assertion与既有 parser owner tests共同证明 batch-only boundary。修改后先运行 exact failed node；未通过则只能在本 15-path allowlist内按 root cause修复。

## 5. Mandatory final cumulative validation

随后完成原 I2 task并重新执行 corrected plan §7.3/§8 全部 gates：

- focused I1+I2 tests、public packaging tests、POSIX real recorder与 real CLI/temp-storage smoke；
- related/full suites；只允许精确复现 Controller 已裁决的两项 HEAD-existing Service failures，任何新增 failure stop；
- changed production whole-file coverage均 `>=80%`；
- full pyright零错误；scoped Ruff零错误；full Ruff对 locked 144 baseline current-only/resolved均零；
- exact cumulative allowlist、shared-function-only diff、七个 I1 hashes、staged-empty、`git diff --check`；
- wheel build/extract/RECORD/METADATA/entrypoints、isolated venv install/help/importability；
- placeholder/JSON/public script/README/source/security/secret/deferred/no-unified-auth scans；
- README trigger matrix与四份 README人工 owner复核；
- Windows-only nodes在 macOS保持明确 skip，workflow local contract完整；真实 GitHub `cmd.exe` run继续标 `PENDING_RELEASE_BLOCKER`。

`git ls-files dayu/web dayu/wechat dayu/render` 在未 stage deletions 时仍会列 index paths，不能把这一 Git 事实伪装成 working-tree残留；正确 local deletion oracles是 working-tree absence、diff deletion status、wheel/archive/RECORD/importability。staged set必须保持空。

## 6. Stop conditions

出现 allowlist外 diff、shared function外 test delta、I1 hash变化、Controller/plan/artifact变化、staged content、新 test/static/coverage/security failure、真实 non-placeholder consumer、需要 tracker/deferred能力或 unified authorization时立即停止。不得实施 Issue 142/151/175/177/178、Topic 8/9 code、Web/WeChat/render真实能力或兼容 shim。

## 7. Handoff

唯一 implementation artifact必须完整记录 final path/hash manifest、shared-function diff proof、tests/coverage/pyright/Ruff、wheel/isolated-install、README/security/deferred scans、两项既有 Service failure、Windows pending blocker与 staged-empty。末行 `READY_FOR_CONTROLLER_R11_I2_CHECKPOINT` 后停下。

AUTHORIZED_R11_I2_CONTINUATION_ONLY
