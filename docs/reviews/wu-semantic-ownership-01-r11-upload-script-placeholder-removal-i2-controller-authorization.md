# WU-SEMANTIC-OWNERSHIP-01 / R11-I2 Controller authorization

## 1. 唯一授权

本文件是当前唯一 live write authorization。它授权 AgentCodex 在已通过 checkpoint 的 R11-I1 dirty tree 上继续实施 accepted plan 的 `R11-I2 packaging/README/Windows gate`。这是 R11 内部第二个 implementation slice，不是新 WU、独立 sub-WU、旧 sub-WU reopen 或独立 acceptance。

不得 stage、commit、push、创建 PR、进入 code review、R12 或 umbrella aggregate。完成本授权的 cumulative validation 与 implementation artifact 后停在 Controller checkpoint。

## 2. 不可变输入

- branch：`phaseflow/host-issues-control`；
- HEAD：`a527ec030215e5bfcf9c4fad2f4a6fda243f5d65`；
- accepted plan：`docs/host/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan.md`，889 lines，SHA-256 `55d35256f0f89f39f722438dc19d9ae65269b16810f96f1cd0129c6eba06d427`；
- R11-I1 implementation：`docs/reviews/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-i1-implementation-codex.md`，SHA-256 `2f8847dd5198c882045db01564c08cca1910cd8a5037f2f161f06dc749731c39`；
- R11-I1 Controller validation：`docs/reviews/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-i1-controller-validation.md`，89 lines / 6,131 bytes，SHA-256 `6418ade14976240c055c9a29e76c654b011ddc237c416a3a8a2c71c3e4d023a4`；
- Ruff：`.venv` 0.15.11；locked baseline `workspace/tmp/r11-ruff-baseline.json` 为 144 findings，SHA-256 `051bd6cc84fcd32adbd792c81c9e524438dd0532a92c7504ea2edf8234ec1cea`；
- staged set：空。

R11-I1 八个 code/test paths 与新 renderer 是本 slice 的 protected cumulative input，不得回改：

| path | entry SHA-256 |
|---|---|
| `dayu/fins/upload_batch.py` | `7cbc1f6aa167088ebe3c89a46cb712981e2e93227bf001ec8ed12fb251512ad9` |
| `tests/fins/test_upload_batch.py` | `51ae67a8f811feb64394dbcae0a86c337c216ae0c0a665a6542ca54a8679d23c` |
| `dayu/cli/upload_script.py` | `dfe0508deb905ef9bc21204a75a8ec55abf87ec254517831556dc7a8ba7aea65` |
| `dayu/cli/arg_parsing.py` | `d8442bc64dd823cf92b09eec408a1b4437fae07a0f6b89b06afe9b25e7521b0e` |
| `dayu/cli/commands/fins.py` | `13bab3f4a1ac3eeece61c4cfb1169f68d2ac20da08afa6a4d5aeb7e63f75c0a3` |
| `tests/cli/test_upload_filings_from_command.py` | `14e1bff29c9a1f7efce61bf4891d3f6c099bb43931d54d4ef586d1df9b7ca3cd` |
| `tests/cli/test_fins_commands.py` | `297ecc542dd347b8ecf615814d001b6d71e639750cfca30b306815db9327afaa` |
| `tests/cli/test_arg_parsing.py` | `7cdc4c1d014bc7012aca28f05927b8afbbd04b86cc6d0aa2dfbf5f87af91ece6` |

如果任一 protected hash、accepted plan、Controller control/authorization/artifact 或 staged set在任务中发生非本授权变化，立即停止并报告。

## 3. 精确 write allowlist

本 slice 只允许修改/新增/删除下列 product/test/README/CI paths：

1. `pyproject.toml`
2. `requirements.txt`
3. 新增 `.github/workflows/r11-upload-script-windows.yml`
4. 删除 `dayu/web/__init__.py`
5. 删除 `dayu/web/__main__.py`
6. 删除 `dayu/wechat/__init__.py`
7. 删除 `dayu/wechat/main.py`
8. 删除 `dayu/render/__init__.py`
9. 删除 `dayu/render/render.py`
10. `tests/cli/test_public_package_entrypoints.py`
11. `README.md`
12. `dayu/README.md`
13. `dayu/fins/README.md`
14. `tests/README.md`

AgentCodex 另可新增唯一 evidence：

15. `docs/reviews/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-i2-implementation-codex.md`

Controller-owned `docs/host/issues-implementation-control.md`、两份 Controller authorizations、I1 Controller validation 与既有 dirty design/review/control artifacts均为 read-only。`workspace/tmp/**` 仅可放机械 validation/build/smoke outputs，不得 stage。

entry locks：

| path | lines / bytes | SHA-256 |
|---|---:|---|
| `pyproject.toml` | 152 / 4,136 | `e076606fd68ab911291be92cdba1bda9df05835baf8db7f81b1d33d517ce6a25` |
| `requirements.txt` | 12 / 606 | `d15176134f7e1cf651b77175450dba526a5e82ff7c7f60cf15356c1532215d3a` |
| `dayu/web/__init__.py` | 9 / 271 | `838db1b2411c5689fb6da4484107488dade8134927ccef8a258b5473707b2936` |
| `dayu/web/__main__.py` | 59 / 1,827 | `3f0f0696e6464c9b0492d3a362c7dd66fec2a1739b417ec570ab934a1121dfc5` |
| `dayu/wechat/__init__.py` | 9 / 271 | `d20467c914bf06a33d01ac84d0df5bc5276ef34aafad6fc1c9f884c25bd32049` |
| `dayu/wechat/main.py` | 118 / 4,268 | `6a9ff7ca666c3515a784d920acff93020a31a873dfa0dfdbadd4f5d25277062c` |
| `dayu/render/__init__.py` | 9 / 265 | `00d5e0bf5359a12fe5d02b563ef6666dc623395f731c0dccdbd32469bc9033c4` |
| `dayu/render/render.py` | 69 / 2,215 | `405fdc2b11ed8cec1d9ca43d5890e9e2ee4911bf74c435ba47436124055acd58` |
| `tests/cli/test_public_package_entrypoints.py` | 217 / 7,931 | `675470c43b62c2fe9b80cc6a4a87f8291170de226fb94eccaf9b619e0725959b` |
| `README.md` | 348 / 11,099 | `2f5cebfd3bf82b7099ff11f94e7a1e0df3840ca13fc41324a9d4ae99a02a6e6a` |
| `dayu/README.md` | 265 / 31,685 | `16bbdc87da05f68ad7787086cf5e4646e011a8e8304991cb360916487fa85367` |
| `dayu/fins/README.md` | 793 / 69,005 | `a4805995879a5284f2205ef12e1113c1cec89dae55aefa96995b8d2749519767` |
| `tests/README.md` | 293 / 82,643 | `15bb09f8c38c9b659c64d8f6d3cc120abf0d2c7c3ce20b91e9629733fa91fba9` |

entry 时 `.github` 不存在；新增 workflow 必须是该 tree 唯一文件。修改四个 README 前必须先完整读取各自 `Agent更新约束` 或等价章节，并按读者职责最小更新。

## 4. 必须实现的 exact contract

严格实施 accepted plan §7：

1. packaging 只保留真实能力：删除三个 placeholder console scripts、只为 placeholder 存在的 `web` extra/comment、`dayu.render` package-data；保留真实 `dayu-cli` 与其它已实现入口。
2. `requirements.txt` 删除 `[web]` extra 消费和 stale Streamlit/dayu-web 承诺；不修改 constraints/lock inert pins。
3. 删除六个 placeholder package files，不留空 package、re-export、wrapper、unavailable README/grammar/test contract，不实现未来 tracker 能力。
4. public packaging test 删除 placeholder 成功/失败/help 冻结，保留 Docling/constraints 等真实 contract，并增加 wheel entrypoint/metadata/archive negative assertions。
5. 四个 README 只按各自 owner/读者更新 upload script 当前工作流、typed Fins owner、测试/Windows gate 与 placeholder 删除；根 README 必须覆盖 default/explicit output、`.sh`/`.cmd`、ticker CSV、`--infer` 环境要求、`auto`、human summary、追加参数、检查/执行与排障；删除 JSON argv schema 和 placeholder claims。
6. 新 workflow 必须精确是 `.github/workflows/r11-upload-script-windows.yml`，name、permissions、runner、Python 3.11、30-minute timeout、exact path triggers、install command、三个 exact pytest nodes、真实 `cmd.exe /d /c` evidence、artifact env/name/path/retention/always/no-files-error均遵守 accepted plan §7.2；不加 secrets/provider、schedule/release/deployment、unrelated matrix 或宽 glob。

真实 Windows runner 在本地不可执行时，workflow 与两个 Windows-only nodes可标 `PENDING_RELEASE_BLOCKER`，不得标 closed、waive 或降级成 unit test。最迟 umbrella aggregate/draft PR check 必须有真实 GitHub-hosted run 和完整 artifact；本授权不允许 push/PR。

## 5. Mandatory cumulative validation

完成 I2 后必须从当前 I1+I2 cumulative tree 重新执行 accepted plan §8 的全部 final gates，不得复用 I1 结果冒充 final：

- focused/public CLI/Fins tests，包括 POSIX real recorder 与 real temp-storage smoke；Windows-only nodes在非 Windows上只能保持明确 skip；
- `pytest tests/cli tests/fins tests/service -q` 与 `pytest tests -q`；只允许精确复现 I1 Controller 已裁决的两项 HEAD-existing Service failures，任何新增失败立即 stop；
- changed production per-file coverage均 `>=80%`；
- `python -m pyright dayu/ tests/ utils/` 零错误；
- authorized changed paths scoped Ruff零错误；full Ruff与 locked 144 baseline current-only/resolved均为零；
- `git diff --check HEAD`、staged-empty、exact cumulative allowlist、protected I1 hashes；
- build wheel、exact-one extract、isolated venv install、两个真实 CLI help、三个 placeholder package不可 import；
- wheel METADATA 无 `Provides-Extra: web`/Streamlit requirement，entry_points/archive/RECORD 无 placeholder scripts/packages；
- placeholder/public scripts/JSON schema/README source scans、README trigger matrix、security/secret/deferred/no-unified-auth scans；
- generated POSIX/Windows artifact secret scan，atomic publisher与 containment/symlink gates仍通过。

所有 wheel/build/install outputs 只放 `workspace/tmp`。不得用 compatibility branch、旧 schema fallback、test shim、loose import oracles 或放宽 scan/test 来使 gate 变绿。

## 6. Stop conditions

出现以下任一情况立即停止并报告 Controller：

- 删除项仍有真实 production owner/consumer，或 `web` extra 兼有非-placeholder 产品 owner；
- wheel 仍发布 placeholder entrypoint/package/extra/Streamlit requirement；
- 需要实现 Web/WeChat/render tracker 能力、修改 constraints/lock、Service/storage/runtime、I1 protected paths或其它 README；
- workflow 需要 secret/provider 或不能按 accepted plan 构造真实 `cmd.exe` gate；
- 新增测试/pyright/Ruff/coverage/source/security failure；
- Controller/control/plan/protected hash变化，出现未授权 tracked path或 staged content。

不得实施 Issue 142/151/175/177/178、Topic 8/9 code、统一 tool authorization framework 或任何 deferred capability。

## 7. Handoff

implementation artifact 必须记录：exact path/diff/hash manifest、删除清单、workflow contract、full validation raw summaries、coverage、wheel/archive/install oracles、README trigger decisions、Windows pending/actual evidence、安全/deferred scans、两项既有 Service failure状态与 staged-empty proof。完成后以 `READY_FOR_CONTROLLER_R11_I2_CHECKPOINT` 结束并停下。

AUTHORIZED_R11_I2_PACKAGING_IMPLEMENTATION_ONLY
