# WU-CLI-SMOKE-01-R1 Transient Delivery Ownership Design Fix

## Gate metadata

- Work unit：`WU-CLI-SMOKE-01-R1` final-closeout design correction。
- Gate：design fix gate。
- Date：2026-07-21。
- Agent：AgentCodex。
- Design truth：`docs/host/design.md`；`docs/engine/design.md` 只读核对。
- Original design record：`docs/reviews/wu-transient-delivery-ownership-design-codex.md`。
- Review inputs：`docs/reviews/plan-review-20260721-141110.md`、`docs/reviews/plan-review-20260721-141359.md`、`docs/reviews/plan-review-20260721-142109.md`。
- Controller decision：接受 `CODEX-DESIGN-F01` 至 `F05`；DS / MiMo 同类 finding 合并到对应修复，不单独保留 residual。
- Scope：只修设计真源、原设计记录与本 fix artifact；不修改生产代码、测试、README 或总控，不 commit。

## First-principles correction

动机成立。直接代码证据显示，问题不是单纯的“256 是否太小”：Host public Protocol 没有公开具体实现已经提供的 `aclose()`；Service 因此自建 closable Protocol / cast，并用第二个 256-item queue + drain task 复制同一事件；Host overflow 复用 availability error；Hub 支持多 watcher、同步 O(N) fanout，并用长期 terminal id set 重做 late-state 语义。若只调容量或删一个 queue，而不冻结公共关闭 contract、sole consumer 状态机、错误 owner 和资源承诺，实施者只能在 Service fallback / cast / relay 或 Host 私有常量中重新补洞。

修复边界因此落在三个 owner：Host public API 拥有 closable iterator / delivery error contract；Session Event Delivery 拥有单 mailbox、byte accounting、overflow、fanout 与 bounded current-terminal fence；Service watch runtime 拥有 sole `anext`、快速 callback、容量一 terminal/failure signal 和 durable degraded recovery。Engine 继续只拥有单次 generator event 顺序，Host ingest 继续拥有 durable identity / late-state validation；无需修改 Engine contract。

## Finding -> fix mapping

| Finding | 合并的同类 finding | 修复位置 | 修复结果 |
| --- | --- | --- | --- |
| `CODEX-DESIGN-F01` Service relay 删除后的状态机 / cleanup contract 缺失 | `DS-DESIGN-F01`、`MIMO-DESIGN-F01` | `docs/host/design.md` §4.2、§4.5、watch attach cleanup；原设计记录 Public interface / State 与 lifecycle | public return 冻结为可关闭 `HostSessionEventIterator`，Service 删除私有 cast；恰好一个 consumer 是 sole `anext` owner，只直接调用快速 callback，并只写容量一 target-terminal / typed-failure slot。submit、target-unbound、cancel、startup、watcher failure、terminal race、caller cancel、never-started 与 normal close 全部给出 transition；固定 stop -> await no-active-`anext` -> `aclose()`，renderer 仍由 caller `finally` 关闭。`accepted-fixed`。 |
| `CODEX-DESIGN-F02` “永不反压”超出同 event-loop 可证明范围 | 无独立编号；DS / MiMo 在 F01 callback 风险中有交叉 | `docs/host/design.md` §4.1、§4.3、§4.5、§16 read boundary；原设计记录 Handoff | 承诺收窄为 Host publish 不 await 被动 consumer 或 mailbox capacity，overflow 只隔离当前订阅。同-loop blocking callback、CPU starvation 与 O(N) fanout 不属于物理隔离；callback 快速非阻塞及隔离适配归 Service / UI。`accepted-fixed`。 |
| `CODEX-DESIGN-F03` overflow 复用 `HostUnavailableDetail` 造成错误 owner 漂移 | `DS-DESIGN-F04`；`MIMO-DESIGN-F03` 的旧错误术语迁移部分 | `docs/host/design.md` §4.4、public error contract、§4.6；原设计记录 Overflow / scope | 新增 `HostApiErrorCode.DELIVERY_INTERRUPTED`、`HostSessionEventDeliveryDetail`、`HostSessionEventDeliveryReason.TRANSIENT_MAILBOX_OVERFLOW`、`HostSessionEventDeliveryLimitDimension.ITEM_COUNT/PAYLOAD_BYTES`，固定 `retryable=false`。Service 只进入 local degraded + `get_run` / Outbox recovery，不标 Host outage；旧 `slow_consumer` / `session_live_stream` / availability error 全量迁移列为同 WU acceptance。`accepted-fixed`。 |
| `CODEX-DESIGN-F04` 新 public contract 与旧 “不得改 fields / exports” 及 future scope 冲突 | `DS-DESIGN-F05`；`MIMO-DESIGN-F03` 的迁移 scope 部分 | `docs/host/design.md` §3 runtime assembly、§4.6；原设计记录 Future WU scope | 旧限制修正为“未经对应 design gate 不得漂移”；本 gate 明确授权 `OpenHostOptions.session_event_delivery_policy`、public iterator / error contract / exports。未来文件、tests、README trigger 与旧常量 / 术语迁移完整列出；control 仍只读，由 Controller owner 维护。`accepted-fixed`。 |
| `CODEX-DESIGN-F05` opener policy owner、aggregate resource 与 terminal fence 不完整 | `DS-DESIGN-F02`、`DS-DESIGN-F03`、`MIMO-DESIGN-F02` | `docs/host/design.md` §4.1-§4.4、§4.6；原设计记录 Ownership / Byte / Ordering / Aggregate | runtime composer / operator 是 opener-wide policy owner，所有 subscription 统一，per-sub override 为 non-goal；精确列出 string traversal，一 event 一次 size 后 fanout 并定义 owner-loop 顺序；fence 只保留 current terminal，在 generator 恢复 / close 时释放，post-terminal truth 仍由 ingest late-state validation 拥有；明确 per-sub bound 不等于 Host total / O(N)，topology audit 与 session admission / aggregate bound 是同一实施 WU acceptance prerequisite。`accepted-fixed`。 |

## DS / MiMo standalone reconciliation

- `DS-DESIGN-F01`、`MIMO-DESIGN-F01`：并入 Codex F01，不再把 replacement primitive 留作 open question。
- `DS-DESIGN-F02`、`MIMO-DESIGN-F02`：并入 Codex F05。byte traversal 已精确到字段，enum / datetime / int / serialization overhead 排除；publication / accounting 依赖 opener owner loop 的同步无 `await` 调用栈，一 event 一次 size。
- `DS-DESIGN-F03`：并入 Codex F05。opener-wide policy 的 tradeoff 已冻结，UI / CLI / subscription 不得覆盖。
- `DS-DESIGN-F04`：并入 Codex F03。`retryable=True` 与 availability 复用被删除，不再保留立即重试歧义。
- `DS-DESIGN-F05`：并入 Codex F04。ConfigLoader -> packaged JSON -> Service assembly -> Host API / export 的文件面和验证面已列全。
- `MIMO-DESIGN-F03`：错误 owner 部分并入 Codex F03，旧常量 / 术语 migration scope 并入 Codex F04。

## Frozen decisions checklist

1. `watch_session_events(session_id)` 保持统一 async iterator 外观；public return 精确为含 `aclose()` 的 `HostSessionEventIterator`，禁止 Service 私有 cast / fallback。
2. Service 不再保存 event copy：attach-before-submit；sole consumer 是唯一 `anext` owner；activity / thinking callback 直接、快速、非阻塞；只有目标 terminal / typed watcher failure 进入容量一语义 slot。command / durable probe 不抢 iterator。submit failure、target 未绑定、cancel、startup reconnect、watcher failure、terminal race、never-started 与关闭顺序均已冻结。
3. no-backpressure 只表示 Host publish 不等待被动 consumer 或 mailbox capacity，overflow 只隔离当前 subscription；同-loop blocking callback / CPU starvation / O(N) fanout 不在物理隔离承诺内。
4. overflow 使用 delivery-specific public typed error，`retryable=false`；Service 映射为 local degraded / durable recovery，不映射 Host outage。
5. 旧 public assembly 限制修正为“无 design gate 不得漂移”；本 gate 已授权新 `OpenHostOptions` field、iterator / error contract 与 exports。
6. runtime composer / operator 是 opener-wide policy owner；所有 subscription 统一，per-subscription override 为 non-goal。
7. `delivery_size_bytes` 的 string traversal、primary dimension 判定、owner-loop concurrency 与“一 event 一次计算后 fanout”已冻结。
8. subscription fence 是 O(1) current-terminal handoff fence；generator 恢复或 cleanup 时释放。Host ingest late-state validation 仍是 post-terminal 唯一事实 owner。
9. per-subscription bound 不等于 Host total memory / O(N) fanout bound。当前代码已显示 multi-watcher；实施前仍须审计 topology，多订阅成立则同一 WU 落 session admission / aggregate bound，否则用代码 / contract / tests 证明单订阅后关闭，不能 defer 为 residual；不无证据增加 Host-global quota。
10. future implementation files、owner-level / E2E tests、README trigger 与旧 overflow 常量 / error terminology migration 已列全。
11. packaged items / bytes 默认值、低基数 metrics 与 Python heap margin 留给 implementation WU 测量裁决，不阻塞设计；它们不得成为 Host 隐藏 fallback。

## Direct code evidence checked

- `dayu/host/api.py:3902-3911` 只公开 `AsyncIterator[HostSessionEvent]`；`dayu/host/open_host.py:905-929,1194-1276` 的具体 iterator 已实现 `aclose()`。
- `dayu/service/entrypoint_runtime.py:459-511,998-1076` 定义私有 closable Protocol / cast、256-item relay queue、drain task 与先停 drain 再 close 的必要顺序。
- `dayu/service/entrypoint_runtime.py:646-959,1079-1212,1470-1530,1600-1771` 显示 submit / cancel / startup / live / Outbox race 的现有语义，证明 sole-consumer 状态机必须在设计中闭合。
- `dayu/host/transient_delta.py:26-29,187-336,388-465` 显示 Host 256-item queue、availability error 术语、历史 terminal set、Session subscription set 与同步 fanout。
- `dayu/host/api.py:1317-1394` 显示 `UNAVAILABLE` / `HostUnavailableDetail` 当前拥有 Host execution availability，不应承载局部 delivery continuity failure。
- `dayu/host/open_host.py:1460-1493`、`dayu/host/dispatch.py:3387-3397,3887-4090` 与 Service callback 直接调用路径显示共用 event loop，支持收窄物理隔离承诺。
- `dayu/runtime/config_loader.py:521-561,799-843,1906-1969`、`dayu/service/host_assembly.py:560-675,763-885` 与 `dayu/config/host_runtime.json` 显示 policy 的完整 typed assembly 触发面。
- `docs/engine/design.md` §1.1、§14 明确 Engine event 无 Host cursor、fanout 或 replay，且只拥有 generator 顺序；本修订无需改变 Engine design。

## Validation

- `git diff --check`：pass。
- 原设计记录与本 untracked fix artifact 分别执行 `git diff --no-index --check /dev/null <file>`：无 whitespace diagnostic；按 `git diff --no-index` 的“文件内容不同”语义返回 `1`。
- stale wording scan：旧宽泛 watch signature、旧 availability overflow 实例、私有可关闭 fallback 与字面“永不反压”均无 normative 命中；`slow_consumer` / `session_live_stream` 只存在于历史证据和明确 migration scope。
- frozen-decision scan：11 项决策在 `docs/host/design.md`、原设计记录与本 mapping 中均有对应项。
- scope boundary：`docs/engine/design.md`、`docs/host/issues-implementation-control.md`、`dayu/`、`tests/` 与根 `README.md` 无 tracked diff；三份首轮评审保持输入原文。
- 本 gate 不运行测试或 pyright：没有生产代码 / 测试修改，且用户明确限定只修设计与修订记录。

## Open issues

没有阻塞 re-review / implementation plan 的开放设计问题。未来 WU 仅需测量 packaged items / bytes、heap margin 与 low-cardinality metrics；watcher topology / session aggregate 是 acceptance prerequisite，不是 residual risk。
