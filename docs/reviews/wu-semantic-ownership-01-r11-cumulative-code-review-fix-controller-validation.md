# WU-SEMANTIC-OWNERSHIP-01 / R11 cumulative code-review fix Controller validation

## 1. Gate 与输入

- umbrella：既有 `WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation；不是新 WU、
  新 feature/issue 或 R12。
- gate：R11 cumulative code-review bounded fix Controller checkpoint。
- HEAD：`7972c3c0ba8628173fc91c362b9394655f60678e`，staged set为空。
- accepted plan：
  `docs/host/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan.md`，
  SHA-256 `f1c95c3b5ecb1d6f01a2f15d1af6c96396ebb370c10997108a3c44dbd14b2ffd`。
- finding adjudication：
  `docs/reviews/wu-semantic-ownership-01-r11-cumulative-code-review-controller-adjudication.md`。
- AgentCodex fix evidence：
  `docs/reviews/wu-semantic-ownership-01-r11-cumulative-code-review-fix-codex.md`，
  250 lines / SHA-256
  `c6e24041994a61afca3208e6f869807da29b8c7a91cb57c3bcfb9d5d34f7b753`；Controller已完整读取。

## 2. Exact scope 与 owner 复核

Fix只修改五个授权路径：

1. `dayu/fins/upload_batch.py`
2. `dayu/cli/commands/fins.py`
3. `tests/fins/test_upload_batch.py`
4. `tests/cli/test_upload_filings_from_command.py`
5. `.github/workflows/r11-upload-script-windows.yml`

另新增唯一 AgentCodex fix evidence。未修改 `dayu.runtime`、其它产品/测试/README、plan、
Controller artifacts、constraints、Service/Host/Engine、deferred ISSUE 或 R12。

五个 fix-owned path 的 Controller独立 SHA-256依次为：

- `95c543801a75c4428b8d2022000d23be644c3a706ca12c06568a8f3e1eda74f0`
- `2b022641e2d19daaf73b8787e3240a6c4e041b7b36fd66965f466275d9a1797f`
- `1e3967ecadd77c8688640f02783b9283390a32e1a01b316ac88f83323bc2a1cf`
- `758e4e3db093e456c62d872c74046c17357214e9dbeacd133d0d8d914f728fd7`
- `8eae09d59e69413adbb2c49dc60c3c431834bab7f230c410b9e981100d3f84c5`

Cumulative tracked product/test/README/packaging/workflow binary diff为
`6065289ee2a2da8d475de29fcd8b5d719ca1f0448e357e885a5ac0156fb6f424`。

## 3. Finding closure 复核

### `R11-DS-F02` — FIXED / pending dual re-review

- `UploadBatchPlanRequest.material_form`诚实表达为尚未验证的 `str | None`；
- CLI只做单值、trim、uppercase输入规范化，不再拥有三个合法业务值；
- normalized candidate进入 Fins request，只有 Fins私有 routing table派生的值域与
  `_validated_material_form`负责合法性判断和 typed result；
- Controller source scan确认 CLI中三项业务值字面量为零；没有 public constant、compatibility
  alias、fallback或下游第二套值域校验。

### `R11-DS-F03` — FIXED / pending dual re-review

- 两个 Windows-only tests在显式 artifact root下分别使用固定 `cmd-recorder/` 与
  `cli-storage/`，发布 exact script/oracle/storage evidence；
- workflow只读取和校验 exact paths、hash与source count；不再递归扫描系统 `%TEMP%`，不再使用
  generic `-Filter`或 `Copy-Item`；
- Controller corrected YAML parse确认 `pull_request.paths`为 exact `22`，且无重复；相关负向 scan为
  zero output。

`R11-DS-F01`保持 `REJECTED / NO FIX`：Fins source containment与CLI output publication
containment仍是两个独立 policy owner；`dayu.runtime`没有范围扩张。

## 4. Controller 独立验证

- focused owner/CLI/public packaging matrix：`147 passed, 2 skipped, 3 warnings`；两个 skip只因本机
  macOS没有真实 `cmd.exe`。
- full pyright：`0 errors, 0 warnings, 0 informations`。
- scoped Ruff（四个本轮 Python paths）：`All checks passed!`。
- workflow使用 `yaml.BaseLoader`解析 PASS；`pull_request.paths = 22 / unique = 22`。
- `git diff --check` PASS；staged set为空。
- workflow `%TEMP%|Get-ChildItem.*-Filter|Copy-Item` scan：zero output。
- CLI material-form三值 scan：zero output。

同时接受 AgentCodex记录的完整复验：focused累计 `155 passed, 2 skipped`；related
`2 failed, 1470 passed, 3 skipped`；full `2 failed, 5056 passed, 5 skipped, 5 deselected`；
失败仍精确为两项 HEAD-existing Service baseline且相关owner blobs无diff。三项POSIX real smoke、fresh
exact-wheel constrained normal install、pip check/help/importability/archive gates均PASS；四个changed
production files line coverage为 `90.87%`—`99.66%`；full Ruff相对锁定baseline为
`current-only=0`。

## 5. Verdict 与 next gate

Verdict：`PASS / READY_FOR_DUAL_COMPLETE_CUMULATIVE_REREVIEW`。

- `R11-DS-F02`、`R11-DS-F03`已实现并由Controller验证，仍须AgentMiMo / AgentDS对完整累计树
  并发re-review后才可关闭；
- 当前accepted/open implementation finding在re-review前为 `0`，blocker为 `0`；
- 真实GitHub `windows-latest` / `cmd.exe` execution仍为 `PENDING_RELEASE_BLOCKER`，本地skip、YAML或
  renderer evidence不能关闭或waive它；
- re-review findings如被接受，必须由AgentCodex全部修复并再次双路re-review；
- R11 accepted implementation commit、R12、push、PR仍未授权。
