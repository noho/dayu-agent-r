# WU-SEMANTIC-OWNERSHIP-01 / R09 code re-review finding fix（AgentCodex）

## 1. Gate 与 authority

- 本轮是同一 umbrella `WU-SEMANTIC-OWNERSHIP-01` / R09 的 code re-review finding fix gate，
  不是新 WU、issue 或 feature。
- 唯一 authority：
  `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-code-rereview-controller-adjudication.md`，
  107 lines，SHA-256
  `1b64b0b0c527ae5e88f167a6e488f45f0b2591a42231eb928797c13ac986d27c`。
- 唯一 accepted finding：`R09-RR-F01`。
- 本 gate 只授权修改 `dayu/fins/README.md`，并新增本 fix artifact。
- 未授权 product Python、tests、其它 README、design/control/plan/prior artifact、deferred scope、
  stage、commit、push、PR、aggregate deepreview 或 R10。

## 2. Entry locks

- branch：`phaseflow/host-issues-control`；
- HEAD：`9d36a115400fb59fd95475189810b43a09fda31b`；
- staged tree：empty；
- entry README：789 lines，SHA-256
  `fe2d12627c2f8da780a7305f2e5f3611c09a3660f233c7014d272e900fded9d7`；
- sorted newline-delimited 12-path manifest SHA-256：
  `ce024b6df7e319fe38c3a708ec4a2cec9f66b9286c5d41763c73c17cc2fc5cb4`；
- canonical cumulative binary diff SHA-256：
  `e5f35bd8ccfe945cd74436fad25ae2cb0ca537a4d3d706f97e6721ba6a86e48d`。

Entry 12-path content locks 全部匹配：

| Path | Lines | Entry SHA-256 |
|---|---:|---|
| `dayu/cli/commands/fins.py` | 1057 | `0db8ff2dedf541c2b58bc11342a02cd0bf4098bc9fcc19d948efa5cf4afc95a6` |
| `dayu/fins/README.md` | 789 | `fe2d12627c2f8da780a7305f2e5f3611c09a3660f233c7014d272e900fded9d7` |
| `dayu/fins/direct_events.py` | 496 | `192f31fc42a1be7415ccca2f658a8a84044b086f41c7c65d3dba02fc579a993a` |
| `dayu/fins/direct_stream.py` | 261 | `f724e51ca6ff5dd687dfe4709751b8f0e9bd440b4e02f0bfd343f598a1e50c53` |
| `dayu/fins/ingestion_runtime.py` | 6920 | `aba78b1e4cacf7566ffd275db51392441575d90c2d9341a2e377bf801d43b580` |
| `dayu/service/README.md` | 42 | `4f4f30b8e1caae100c9329fe42515ca504f7057e29e92381e15cd35851f6be9d` |
| `dayu/service/fins_direct.py` | 467 | `c5bd361ba1603fd76656af9f7b065d8aa07906ed5568749ef6d5e470e20391ac` |
| `tests/README.md` | 293 | `993ae9ce210625214a3ec4d621111e26e21c327c20cc1987636bcdc818b580c3` |
| `tests/cli/test_fins_commands.py` | 1803 | `d139e10c7636da59e62296d935ed305e7ea0762a94fc59168b7b2a4d199c9668` |
| `tests/fins/test_fins_direct_stream.py` | 742 | `781c3bd941bed675441d9a3e09ac33e525705f02b4c7049d0eb6274f761ba67a` |
| `tests/fins/test_fins_ingestion_runtime.py` | 4925 | `56d9db211e04bdbb246de77432931be1f4262d20eba6bb7b486c95db19f475bf` |
| `tests/service/test_fins_direct.py` | 720 | `e90c7a9238ef00afcee9d49d5093cad387afdb77fadb7505a0d5a4825f706162` |

canonical diff 使用原锁算法：tracked 10 paths 的 `git diff --binary HEAD`，再依次拼接
`direct_stream.py` 与 `test_fins_direct_stream.py` 的 `git diff --no-index --binary /dev/null`。

## 3. 第一性原理与 owner 判定

- `dayu/fins/direct_events.py` 的代码真源直接定义 direct event、typed protocol error 与 result contract。
- `dayu/fins/direct_stream.py` 的代码真源直接定义 `ValidatedFinsEventStream`，并独占“恰好一个且最后一个
  RESULT”的校验和 raw source 关闭生命周期。
- Fins README 已把 direct event contract 与 validator 写成稳定边界，但现有主要组件 tree 遗漏这两个稳定 owner，
  因此 finding 动机成立，且不是产品语义缺陷。
- 该遗漏的唯一 owner boundary 是 `dayu/fins/README.md` 的 package architecture / main-component projection；
  不应在产品代码、消费者、测试或其它 README 补偿。
- README 的更新约束允许记录当前代码已实现的稳定边界和主要组件，同时禁止文件级流水账。最小正确修复是只补
  两个稳定 owner，不扩列 `_log.py`、converter、upload batch 或其它顶层 helper。

## 4. 实际修复

仅在 `dayu.fins` 现有主要组件 tree 中新增两行：

```text
├── direct_events.py          # direct 事件、类型化协议错误与结果契约所有者
├── direct_stream.py          # ValidatedFinsEventStream 恰好一个且最后一个 RESULT 校验所有者
```

本 gate 未修改任何 product Python、tests、其它 README 或 prior artifact，也未实现 deferred scope。

## 5. Final cumulative locks

- final README：791 lines，SHA-256
  `2f94d7b7efb880063cb75ed6c8e5a7740d117761ec66a969c73bd754a3d14d76`；
- sorted 12-path manifest 未增删路径，SHA-256 仍为：
  `ce024b6df7e319fe38c3a708ec4a2cec9f66b9286c5d41763c73c17cc2fc5cb4`；
- 新 canonical cumulative binary diff SHA-256：
  `60f52a7ebbd1608b11d28dd0206bf4176eac59e5dfc4a03fa87393c9457caf3e`。

README 之外的 11 个 target content locks 全部 no-drift：

| Path | Lines | Final SHA-256 | Drift |
|---|---:|---|---|
| `dayu/cli/commands/fins.py` | 1057 | `0db8ff2dedf541c2b58bc11342a02cd0bf4098bc9fcc19d948efa5cf4afc95a6` | none |
| `dayu/fins/direct_events.py` | 496 | `192f31fc42a1be7415ccca2f658a8a84044b086f41c7c65d3dba02fc579a993a` | none |
| `dayu/fins/direct_stream.py` | 261 | `f724e51ca6ff5dd687dfe4709751b8f0e9bd440b4e02f0bfd343f598a1e50c53` | none |
| `dayu/fins/ingestion_runtime.py` | 6920 | `aba78b1e4cacf7566ffd275db51392441575d90c2d9341a2e377bf801d43b580` | none |
| `dayu/service/README.md` | 42 | `4f4f30b8e1caae100c9329fe42515ca504f7057e29e92381e15cd35851f6be9d` | none |
| `dayu/service/fins_direct.py` | 467 | `c5bd361ba1603fd76656af9f7b065d8aa07906ed5568749ef6d5e470e20391ac` | none |
| `tests/README.md` | 293 | `993ae9ce210625214a3ec4d621111e26e21c327c20cc1987636bcdc818b580c3` | none |
| `tests/cli/test_fins_commands.py` | 1803 | `d139e10c7636da59e62296d935ed305e7ea0762a94fc59168b7b2a4d199c9668` | none |
| `tests/fins/test_fins_direct_stream.py` | 742 | `781c3bd941bed675441d9a3e09ac33e525705f02b4c7049d0eb6274f761ba67a` | none |
| `tests/fins/test_fins_ingestion_runtime.py` | 4925 | `56d9db211e04bdbb246de77432931be1f4262d20eba6bb7b486c95db19f475bf` | none |
| `tests/service/test_fins_direct.py` | 720 | `e90c7a9238ef00afcee9d49d5093cad387afdb77fadb7505a0d5a4825f706162` | none |

## 6. 本 gate 验证

所有 Python 验证均先执行 `source .venv/bin/activate`。

| Validation | Result |
|---|---|
| README `Agent更新约束` 复核 | pass；当前实现、稳定边界与主要组件职责允许本次两行更新，未扩成文件流水账 |
| 精确两模块 owner 扫描 | exact 2 matches；仅 `direct_events.py` 与 `direct_stream.py` 两行 |
| README tree added-entry 扫描 | exact 2 additions；没有第三个顶层组件条目 |
| R09 affected aggregate：4 个 affected test files | `161 passed, 3 existing warnings in 4.11s` |
| full pyright：`python -m pyright dayu/ tests/ utils/` | `0 errors, 0 warnings, 0 informations` |
| scoped Ruff：完整 9 个 changed Python files | `All checks passed!` |
| 11-path content SHA check | 全部 `OK`；无 product/test/其它 target drift |
| `git diff --check` | pass，零输出 |
| staged tree | empty |

## 7. 沿用的 final locked evidence

authority 明确允许在 product/test content hashes 不变时沿用 R06、R08、full Fins、coverage、security 与
real smokes 的 final locked evidence。本轮 11-path no-drift 检查证明该前置条件成立，因此不重复执行这些高成本验证：

- R06：`242 passed, 3 existing warnings`；
- R08：`180 passed, 3 existing warnings`；
- full Fins：`873 passed, 1 existing skip, 3 existing warnings`；
- 五个 changed production Python file coverage：
  `direct_events.py 92.207792%`、`direct_stream.py 97.777778%`、
  `ingestion_runtime.py 90.439430%`、`fins_direct.py 90.163934%`、`fins.py 88.563830%`；
- retained security exact cases：`16 passed, 3 existing warnings`；
- fresh real SEC download、Docling process、upload_filing smokes：三条均 exit 0。

沿用证据由 authority 锁定的 Controller final validation 承接；本 gate 没有用 README-only 结果重解释
任何产品或测试语义。

## 8. Finding、docs 与 residual risk

- `R09-RR-F01`：`已修复`；README 主要组件投影现在与两个稳定 owner 的代码真源一致。
- docs decision：只更新触发且获授权的 `dayu/fins/README.md`；其它 README 不属于本 finding owner，保持不变。
- current gate residual risk：0；没有未分类 residual risk。
- Issue 175 physical process isolation、Issues 142/151/177/178、R10-R12、Topic 8/9、统一 authorization、
  Web/WeChat/render 等既有 deferred owner/destination 均未进入本 gate，也未发生状态变化。

## 9. Exit state

- completion status：AgentCodex README-only fix complete，等待 Controller relock 与双路完整 re-review；
- HEAD 保持 `9d36a115400fb59fd95475189810b43a09fda31b`；
- staged tree empty；未 stage、commit、push、建 PR；
- 未执行 aggregate deepreview 或 R10；
- artifact path：
  `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-code-rereview-fix-codex.md`；
- 本 artifact 不内嵌自引用 final lines/SHA；写入完成后由外部命令计算并报告。
