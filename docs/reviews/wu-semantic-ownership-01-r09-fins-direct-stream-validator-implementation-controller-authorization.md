# WU-SEMANTIC-OWNERSHIP-01 / R09 Fins direct-stream validator implementation Controller authorization

## 1. Authorization

`AUTHORIZED / SAME_UMBRELLA_REMEDIATION_SUB_WU / CUMULATIVE_S1_THEN_S2_IMPLEMENTATION`。

这是现有 umbrella `WU-SEMANTIC-OWNERSHIP-01` 的 overdesign remediation continuation 内部 sub-WU R09，不是新 WU、不是新 feature/issue，也不是重开旧 sub-WU。

Authoritative entry：

- accepted plan commit：`9d36a115400fb59fd95475189810b43a09fda31b`（`docs: accept R09 direct stream validator plan`）；
- parent：`a31ded764da0621b6e7a6c7c6a083b4bb6593d21`；
- tree：`4112761a35ed2a6b806caaaedd5654e93acfee9e`；
- fixed plan：`docs/host/wu-semantic-ownership-01-r09-fins-direct-stream-validator-plan.md`；
- fixed plan SHA-256：`a46cd4457121bf976368076ee729436a10a89ed0c50852f3eb73de90fbb1dd8d`；
- plan re-review Controller adjudication：`docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-plan-rereview-controller-adjudication.md`。

本 authorization 只允许 AgentCodex 按 accepted plan 完成累计 S1 owner checkpoint 后继续 S2 mechanical cutover，并完成全部 implementation validation 与 implementation artifact。S1 不是独立 accepted slice，不得单独 review 或 commit。

## 2. Accepted-plan commit audit

Controller 已验证 accepted-plan commit 恰含以下 11 路径，且没有 product、test、README、design 或其他 sub-WU 路径：

1. `docs/host/issues-implementation-control.md`
2. `docs/host/wu-semantic-ownership-01-r09-fins-direct-stream-validator-plan.md`
3. `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-plan-entry-controller-validation.md`
4. `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-plan-review-mimo.md`
5. `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-plan-review-ds.md`
6. `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-plan-review-controller-adjudication.md`
7. `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-plan-fix-codex.md`
8. `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-plan-fix-controller-validation.md`
9. `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-plan-rereview-mimo.md`
10. `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-plan-rereview-ds.md`
11. `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-plan-rereview-controller-adjudication.md`

Commit-time `git diff --cached --check` passed；commit 后 staged/working tree 为空。`a31ded...` 到 accepted-plan commit 的 product/test/README/design diff 为空。

## 3. Entry source locks

AgentCodex 必须先独立复核这些 current-tree locks；任一不匹配即停止回 Controller，不得用兼容分支、fallback 或扩域修复吞掉漂移：

| Lock | Required SHA-256 / state |
|---|---|
| `dayu/fins/direct_events.py` | `b34cb82d70205a23d1e1853c260ea0c9353567082710699bfc4000e485578cf3` |
| `dayu/fins/ingestion_runtime.py` | `176d8ab974c263f6aedc99b1d8b9a8fbd60ebed441a3aa950d5d9a718c64908a` |
| `dayu/service/fins_direct.py` | `875d5396b1d98bdc28f13480241e081529db5e9fa33416914fa6d47e9663b696` |
| `dayu/cli/commands/fins.py` | `666d9dc2793a706a5f00301f215ca324857e4593fcc4c98b18cc90fdc9e245bf` |
| `tests/fins/test_fins_ingestion_runtime.py` | `6480be571d2118648b7829714b885cd0c8a030b6499ec48625af7d207e57ebf4` |
| `tests/service/test_fins_direct.py` | `9c533d7e632762e3fe02a5ae1c58939d71bc7d8c6cb853bd21ad8b4e3a6f2e9b` |
| `tests/cli/test_fins_commands.py` | `525414da8675fdada4ad458271861cf2801c21f57544d62f436594218dafa26c` |
| `dayu/fins/README.md` | `50c07ae625188c470c2818405d445772d073bc67496dcb58f57362720479dd4f` |
| `dayu/service/README.md` | `8d7d7680e82642a769da9a3acc28ea429f8ff32550dff732e6a0478c7aabb2d5` |
| `tests/README.md` | `6c0614afd2b4a6c1a78988cc4512e2b4d0e21528f8e5cc5af69959de8dfe0454` |
| `dayu/fins/direct_stream.py` | absent |
| `tests/fins/test_fins_direct_stream.py` | absent |
| staged tree | empty |

## 4. Exact authorized work and order

1. 按 plan S1 实施唯一 Fins validator owner：typed `EVENT_AFTER_RESULT`、`ValidatedFinsEventStream` 完整状态机、terminal availability、primary error/cleanup chaining、底层 close 至多一次，以及 runtime plain-`def` 返回与 raw async-generator bridge 去重。
2. 先运行 S1 focused owner tests、runtime tests、modified-owner pyright/Ruff/source scans 与 `git diff --check`，记录 checkpoint；不得 stage/commit/review。
3. 在同一累计 tree 上按 plan S2 完成 Service protocol/public methods 与 CLI helper/consumer 的机械 typed-stream cutover，删除 Service/CLI duplicate/missing fallback 和 CLI `operation_kind` terminal-validation参数；不增加 `await`、wrapper、fallback 或第二 validator。
4. 更新 `dayu/fins/README.md`、`dayu/service/README.md`、`tests/README.md`，仅同步其读者职责内的已实施 contract；root `README.md` 与 `dayu/README.md` 不触发。
5. 完成 accepted plan §6 全部验证：受影响/R06/R08/full Fins tests、每个 changed production Python file `>=80.00%`、full pyright zero、scoped Ruff zero、source/propagation/security/no-deferred scans、README check、`git diff --check`，以及真实 download/process/upload smoke。真实 SEC/Docling smoke 失败是 stop condition，不得 waiver。
6. 产出 implementation artifact，锁定 base、sorted path manifest、binary diff、逐文件 content SHA、测试/coverage/type/lint/scans/smoke、README、安全、deferred/no-touch 和 residual evidence；完成后停止等待 Controller validation 与双路 code review。

## 5. Exact implementation allowlist

Production：

- `dayu/fins/direct_events.py`
- `dayu/fins/direct_stream.py`（新增）
- `dayu/fins/ingestion_runtime.py`
- `dayu/service/fins_direct.py`
- `dayu/cli/commands/fins.py`

Tests：

- `tests/fins/test_fins_direct_stream.py`（新增）
- `tests/fins/test_fins_ingestion_runtime.py`
- `tests/service/test_fins_direct.py`
- `tests/cli/test_fins_commands.py`

README：

- `dayu/fins/README.md`
- `dayu/service/README.md`
- `tests/README.md`

AgentCodex 唯一允许新增的 durable implementation artifact：

- `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-implementation-codex.md`

Controller-owned 本 authorization 与 control doc 可作为既有未提交 gate evidence 存在，但 AgentCodex 不得修改。`workspace/tmp/` 只允许 plan 所需的临时 coverage/smoke 证据。

## 6. No-touch and stop conditions

- 不修改 design truth、prompt/config/tool schema、R01-R08 artifact、R10-R12、Topic 8、Topic 9 或任何 deferred Issue 实现。
- 不创建统一 tool authorization framework；保留所有既有权限配置、防御性安全、containment、symlink、DNS/peer、resource budget、atomic write 与 process fencing 行为。
- 不新增 compatibility、旧 schema 分支、downstream fallback、loose parsing、test shim、第二 error schema/validator 或 speculative producer protocol-error channel。
- Issue 175 继续拥有 Docling process isolation；Issues 142/151/177/178 与 Web/WeChat/render trackers 不得夹带。
- production/test/README 任一 allowlist 扩域、source lock 漂移、owner contract 矛盾、真实 smoke无法完成、changed-file coverage不足、测试/type/lint/scan失败，都必须停止并向 Controller提供直接证据。
- 不得 stage、commit、push、PR，也不得自行进入 code review、aggregate deepreview 或 R10。

## 7. Completion report

Implementation artifact 必须报告 entry/exit locks、S1 checkpoint、S2 cumulative changed path/content/binary-diff locks、完整命令和 exact results、逐文件 coverage、真实/injected smoke、README 决策、全部删除/传播扫描、安全与 deferred/no-touch 结论、残余风险与最终 `COMPLETE` 或 `STOPPED` 状态。
