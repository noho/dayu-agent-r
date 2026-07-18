# WU-SEMANTIC-OWNERSHIP-01 / R12 S2 stop-condition fixed-plan final re-review Controller 裁决

## 1. Gate 身份与结论

- 本 gate 是既有 umbrella `WU-SEMANTIC-OWNERSHIP-01` / R12 S2 stop-condition fixed plan 的双路完整 final re-review 裁决，不是新 WU，也不重新打开独立历史 sub-WU。
- review target：`docs/host/wu-semantic-ownership-01-r12-init-workflow-plan.md`，708 行 / 105,368 字节 / SHA-256 `aa7b50a90c9623ea8dcafe8c4c651665b16b9ee3be76ec8357c4d47977fb2a4c`。
- AgentMiMo final artifact：`docs/reviews/wu-semantic-ownership-01-r12-s2-stop-condition-plan-final-rereview-mimo.md`，369 行 / 32,071 字节 / SHA-256 `67814b7b48fce0987de2efc843e2444369c2d2eee2d5ac45eea6ad305f09f49b`。
- AgentDS final artifact：`docs/reviews/wu-semantic-ownership-01-r12-s2-stop-condition-plan-final-rereview-ds.md`，457 行 / 38,671 字节 / SHA-256 `f2155645fdb218b520d9ef3ef4315c5854af90f2d169b6412d9fb5d79d2de61f`。
- Controller verdict：`PASS / R12-S2-PR-F01..F06 CLOSED 6/6 / READY_FOR_AMENDED_S2_IMPLEMENTATION_AUTHORIZATION`。
- 最终 ledger：`accepted/open = 0`，`rejected/no-fix = 2`，`deferred accepted = 0`，`blocking design contradiction = 0`，`blocking question = 0`。

两路 reviewer 均完整复核了同一 fixed plan，并独立确认 Service-owned Fins validation override、ordinary runtime preservation、fault injection、retained cleanup truth、跨平台 no-follow 删除、platform durability 与 exact owner scans 已形成可实施闭环。Reviewer PASS 本身不授权 implementation；本裁决只关闭计划 review gate。

## 2. 原六个 accepted findings 最终状态

| Finding | 最终状态 | Controller 结论 |
|---|---|---|
| `R12-S2-PR-F01` HIGH | `CLOSED` | raw Fins root 仍先通过现行 type/non-empty grammar；对合法未配置、绝对、相对值，Service owner 的 validation-only override 在 raw path selection/return 前支配 effective Fins root。raw/staging/public bytes 不变，ordinary runtime 显式 `None`，非 Fins/Web 不消费 override。 |
| `R12-S2-PR-F02` MEDIUM | `CLOSED` | plan 精确允许 test 侧 syscall monkeypatch/fault injection，同时禁止 production callback/factory seam、synthetic provider 和 catalog shim。 |
| `R12-S2-PR-F03` MEDIUM | `CLOSED` | 删除完成但 POSIX parent sync 失败、删除中途失败、全部成功三种 retained truth 与 diagnostic 已唯一化。 |
| `R12-S2-PR-F04` MEDIUM | `CLOSED` | POSIX 只在 `shutil.rmtree.avoids_symlink_attacks=True` 时走 fd-safe path；Windows 走 identity/quarantine/reparse contract，pre-seeded junction fail closed，与 scan-delete race evidence 分离。 |
| `R12-S2-PR-F05` MEDIUM | `CLOSED` | file content、directory entry 与 deletion 三类 durability truth 分离；Windows 不冒充 POSIX directory crash-durability，同时保留 isolation、atomic replace/rollback 与 truthful diagnostic。 |
| `R12-S2-PR-F06` LOW | `CLOSED` | Service allowlist 精确限定 owner/caller/direct test/README 四路径；Fins/package/Host/Engine/Tool/runtime/design/deferred 路径继续零 diff，override consumers 与 CLI classification/raw-strip scans 已同步。 |

## 3. AgentDS 两个 LOW candidates 裁决

### `FR-DS-F01` — REJECT / NO PLAN FIX

Fixed plan §3 已明确两段式 contract：先校验 raw Fins root 的现行 type/non-empty grammar，再让 override 对合法 raw 值支配 path selection；§6.4、§8 与 §10.2 同步要求三类合法 raw owner tests、ordinary `None` 路径和 invalid/relative override rejection。要求再逐行规定 private helper 的插入位置会把 implementation detail 固化进 plan，不能增加 owner contract 的可验证性。

Implementation 必须遵守现有 contract：invalid raw 不得被 override 掩盖；override 只能在 raw grammar validation 通过后、raw path return 前生效。可增加 invalid raw + override 的 direct owner反例测试，但这不是 plan fix 或新 finding。

### `FR-DS-F02` — REJECT / NO PLAN FIX

Plan §7 已要求隔离 subprocess 证明 CURRENT import graph 零网络、零 secret/runtime 需求、零 workspace/environment external mutation，并在 root/graph 漂移或导入开始需要这些状态时停止；§10.1 已把未来 transitive import-time side-effect 漂移登记为 S3 residual。把未来任意 FD、signal、logger 或不可枚举副作用提升为当前通用 stop schema 会扩张为 import lifecycle framework，也没有当前代码反例支撑。

S3 仍必须执行既定隔离 smoke；若 CURRENT 直接证据显示该 smoke 出现外部 mutation，则按已有 stop condition 交 Controller，不得补 fallback/lifecycle。当前无需修改 plan。

## 4. Rejected/no-fix 与边界保持

- 前轮 rejected/no-fix 两项保持：partial deletion 不承诺完整 forensic tree；两个 managed roots 不升级为 single-syscall snapshot、Host process lock 或 watcher。
- 本轮不新增第四 slice 或新 sub-WU；R12 继续只有 cumulative S1/S2/S3。
- 本轮不实施 Issue 142、151、175、177、178、Web/WeChat/render tracker、Topic 8 或 Topic 9；不设计统一 tool authorization framework。
- 现有 containment、symlink/reparse protection、atomic swap/rollback、Fins private isolation 与 Service/Fins ordinary runtime semantics 均保留。

## 5. 下一 gate

下一 gate 是 Controller 依据 fixed plan 签发 amended R12 S2 cumulative implementation authorization，然后由 AgentCodex 从已恢复的 S2 entry tree 继续实施。

S3、aggregate、accepted implementation commit、push、PR 与 umbrella final closeout 仍未授权。R11/R12 真实 Windows runner 仍是 umbrella final acceptance 前的 `PENDING_RELEASE_BLOCKER`，不阻塞本地 S2/S3 推进。
