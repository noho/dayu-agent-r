# Re-Review：WU-CLI-SMOKE-01-R1 Transient Delivery Ownership Design Fix

## 评审元数据

- **评审类型**：phaseflow 设计修订 re-review gate（adversarial architecture review）
- **阶段**：`WU-CLI-SMOKE-01-R1` final-closeout design correction re-review
- **评审目标**：
  - `git diff` 中 `docs/host/design.md` 的全部修订（normative design text）
  - `docs/reviews/wu-transient-delivery-ownership-design-codex.md`（原始设计记录）
  - `docs/reviews/wu-transient-delivery-ownership-design-fix-codex.md`（修正记录）
- **设计真源**：`docs/engine/design.md`、`docs/host/design.md`
- **只读控制**：`docs/host/issues-implementation-control.md`
- **首轮评审输入**：
  - `docs/reviews/plan-review-20260721-141110.md`（Claude，pass-with-risks，5 findings）
  - `docs/reviews/plan-review-20260721-141359.md`（MiMo，pass-with-risks，3 findings）
  - `docs/reviews/plan-review-20260721-142109.md`（Codex，fail，5 findings）
- **直接代码证据**：`dayu/host/transient_delta.py`、`dayu/host/engine_ingest.py`、`dayu/host/open_host.py`、`dayu/host/api.py`、`dayu/service/entrypoint_runtime.py`、`dayu/runtime/config_loader.py`、`dayu/service/host_assembly.py`
- **评审日期**：2026-07-21
- **评审 Agent**：AgentMiMo

## 评审范围

本次 re-review 只审查 design fix 修订是否真实关闭首轮 findings，以及修订后的 normative design 是否自洽、可实现且无竞态。不修改设计、代码、控制文档或既有 artifact。

## 首轮 Finding 逐项关闭验证

### CODEX-DESIGN-F01（高）→ 关闭 ✅

**原始问题**：删除 Service relay 后的消费、取消与关闭状态机没有闭合。

**修订证据**：

设计新增 §4.5 "Service 无 event-copy relay 的可执行状态机"，完整冻结以下内容：

1. **Sole anext owner**："每个 active watch runtime 恰好有一个 consumer task，且它是该 `HostSessionEventIterator` 唯一的 `__anext__` owner"（design.md diff line 110）。consumer 直接在调用栈执行快速 callback，只写容量一 terminal/failure slot。command、`get_run` probe、Outbox recovery 都不得调用 `anext()`。

2. **完整状态机**：`DETACHED -> ATTACHED_UNBOUND -> CONSUMING -> DEGRADED -> STOPPING -> CLOSED`，每个 transition 都有明确语义：
   - submit：attach-before-submit，consumer 在首次 `anext` 前等待 target binding
   - submit failure：不猜 target，原样传播 command error
   - cancel：先 attach consumer 再发 cancel，terminal race 通过 identity 去重
   - watcher failure：`DELIVERY_INTERRUPTED` 进入 `DEGRADED` + durable recovery
   - startup reconnect：先 attach consumer 再做 Outbox backfill / snapshot
   - caller cancellation：stop → await task → 确认无 active `anext()` → `aclose()`
   - never-started：收口 task → `aclose()` → 观察 cursor future

3. **Public closable iterator**：`HostSessionEventIterator` 是 `AsyncIterator[HostSessionEvent]` 的可关闭子协议，显式提供幂等 `aclose()`。Service 删除私有 `ClosableHostSessionEventIterator`（当前存在于 `entrypoint_runtime.py:459`）和 `cast`。

4. **关闭顺序固定**：stop → await consumer → 确认无 active `anext()` → `aclose()` → 释放 slot。renderer 仍由 caller `finally` 关闭。

**Adversarial 验证**：设计覆盖了首轮评审识别的所有 race 路径（submit/target-unbound、cancel terminal race、startup reconnect、watcher failure、caller cancel、never-started）。容量一 slot 明确不是 event-copy queue。关闭顺序防止了 `anext()`/`aclose()` 并发。

### CODEX-DESIGN-F02（高）→ 关闭 ✅

**原始问题**："慢 UI/Service 永不反压 Agent/Engine"超出了当前执行模型能够证明的边界。

**修订证据**：

设计将承诺精确收窄为（design.md diff line 61, 105）：

> "这个 no-backpressure contract 只排除'被动消费者未读取或异步读取慢'造成的容量等待，不承诺同一 event loop 上的阻塞 callback、CPU 饥饿或同步 O(N) fanout 具有线程 / 进程级物理隔离；Service / UI callback 必须快速、同步、非阻塞返回，慢 I/O、重 CPU 与 renderer 隔离适配由 Service / UI owner 完成。"

修正记录（fix-codex.md line 26）同样确认："承诺收窄为 Host publish 不 await 被动 consumer 或 mailbox capacity，overflow 只隔离当前订阅。同-loop blocking callback、CPU starvation 与 O(N) fanout 不属于物理隔离。"

**Adversarial 验证**：设计不再承诺字面"永不反压"。同-loop callback 阻塞风险被正确转移为 Service/UI adapter 责任。publisher 的同步 `put_nowait` + fanout 已在现有代码中证明可实现（`transient_delta.py:321-336,434-465`）。收窄后的承诺在 asyncio 单线程协作调度模型下可证明成立。

### CODEX-DESIGN-F03（高）→ 关闭 ✅

**原始问题**：overflow 使用 `HostUnavailableDetail` 造成公共错误语义所有权漂移。

**修订证据**：

设计新增 §4.4 完整定义 delivery-specific error（design.md diff line 88-101）：

```text
HostApiError(
  code=HostApiErrorCode.DELIVERY_INTERRUPTED,
  retryable=false,
  detail=HostSessionEventDeliveryDetail(
    reason=HostSessionEventDeliveryReason.TRANSIENT_MAILBOX_OVERFLOW,
    limit_dimension=HostSessionEventDeliveryLimitDimension.ITEM_COUNT | PAYLOAD_BYTES,
  ),
)
```

- 新增 public `HostApiErrorCode.DELIVERY_INTERRUPTED = "delivery_interrupted"`
- 新增 `HostSessionEventDeliveryDetail` 含 typed `reason` 与 `limit_dimension` enum
- `retryable=false`：overflow 不可通过立即 reattach 自动恢复
- Service 映射为 local degraded + durable recovery，不标 Host outage
- 明确禁止复用 `HostUnavailableDetail`、`UNAVAILABLE`、`session_live_stream`、`slow_consumer`

**Adversarial 验证**：错误语义 owner 从 Host availability 迁移到 delivery/subscription。`retryable=false` 消除了首轮 DS-DESIGN-F04 指出的 retry loop 风险。`limit_dimension` 暴露命中维度，帮助调用方判断是否需要调整 policy——这直接回应了首轮 MiMo 和 DS 的建议。

### CODEX-DESIGN-F04（高）→ 关闭 ✅

**原始问题**：目标设计、既有装配约束与只读控制文档互相冲突。

**修订证据**：

设计修改了 `:124` 的旧限制（design.md diff line 32）：

> "未经对应 public interface design gate，runtime assembly 不得自行漂移 Host public command...本次 Session Event Delivery 设计 gate 已明确授权未来实施 WU 新增 `OpenHostOptions.session_event_delivery_policy`，并公开 `HostSessionEventIterator`、delivery-specific error code / detail / enum 与相应 `dayu.host` exports；这些变更不是绕过 gate 的 assembly 漂移。"

修正记录（fix-codex.md line 28）确认："旧限制修正为'未经对应 design gate 不得漂移'；本 gate 明确授权新字段/类型/exports。"

Future WU scope（§4.6）完整列出所有需要修改的文件、测试和 README，以及旧术语/常量迁移清单。

**Adversarial 验证**：新旧约束不再冲突——"不得漂移"被精确限定为"未经 design gate"，而本 gate 已明确授权所需变更。control 文档的只读约束未被修改（设计修正只声明 gate 授权），implementation WU 开始前仍需 control owner 裁决冲突 WU——但这是 control 流程问题，不是设计自洽性问题。

### CODEX-DESIGN-F05（中）→ 关闭 ✅

**原始问题**：opener-wide policy 是最小方案，但 caller 表述与总资源边界尚未归一。

**修订证据**：

1. **Policy owner 明确**："runtime composer / operator 是 opener-wide effective policy 的唯一 owner"（fix-codex.md line 27）。UI/CLI/subscription 不得覆盖。
2. **Byte traversal 精确**：设计 §4.3 完整列出 envelope（6 fields）和 payload（content/reasoning 的 iteration_id + text_delta，tool-call 的 iteration_id + tool_call_id? + name_delta? + arguments_delta?），明确排除 runtime_sequence、worker_event_index、tool_call_index 等整数、observed_at、enum、字段名、序列化标点与 Python 对象头。
3. **一次计算后 fanout**："publisher 对每个 public event 只构造并计算一次 `(event, delivery_size_bytes)`，随后把同一不可变 event 与同一 size fanout 给订阅快照；禁止每个 subscription 重算"。
4. **Fence 收窄为 O(1) current-terminal**："subscription fence 只线性化'当前 mailbox 已接收前缀'与'当前正在交付的 durable terminal'...yield 后 generator 在下一次恢复时立即释放该 fence...禁止用随历史 Run 数量无限增长的 `terminal_run_ids` 集合保存已交付历史"。
5. **Aggregate acceptance 作为 prerequisite**："若审计确认可多订阅，同一实施 WU 必须由 Session Event Delivery owner 落地 session-scoped subscription admission / aggregate bound...不能 defer"。

**Adversarial 验证**：per-subscription bound ≠ Host total 的声明是诚实的。topology audit 和 session admission 被正确定位为同一 WU 的 acceptance prerequisite 而非 residual。fence 生命周期从 O(N) 降为 O(1) 消除了长生命周期 session 的内存增长风险。

## DS / MiMo 同类 Finding 验证

| 首轮 Finding | 关闭状态 | 对应修正 |
|---|---|---|
| DS-DESIGN-F01 / MIMO-DESIGN-F01（Service 协调原语） | ✅ 关闭 | §4.5 完整状态机 + sole consumer + 容量一 slot + 关闭顺序 |
| DS-DESIGN-F02 / MIMO-DESIGN-F02（byte accounting scope） | ✅ 关闭 | §4.3 精确列出遍历字段、排除项、一次计算后 fanout、owner-loop 顺序 |
| DS-DESIGN-F03（opener-wide tradeoff） | ✅ 关闭 | §4.2 明确 "per-subscription override 是明确 non-goal"，记录了未来演进路径 |
| DS-DESIGN-F04（overflow retryable 语义） | ✅ 关闭 | §4.4 改为 `retryable=false` + typed `limit_dimension` + 不可自动恢复语义 |
| DS-DESIGN-F05（config schema 文件清单） | ✅ 关闭 | §4.6 完整列出 config_loader / host_runtime.json / host_assembly 的具体文件 |
| MIMO-DESIGN-F03（error constant migration） | ✅ 关闭 | §4.6 旧术语迁移作为同一 WU acceptance：`_LIVE_STREAM_COMPONENT`、`_SLOW_CONSUMER_REASON_CODE`、`_slow_consumer_error()`、`slow_consumer`、`session_live_stream`、`UNAVAILABLE + HostUnavailableDetail` overflow 路由 |

## Adversarial 检查：核心设计命题

### 1. 公开可关闭 iterator 是否可实现且无竞态

**结论**：可实现。

`HostSessionEventIterator` Protocol 要求 `__aiter__`、`__anext__`、幂等 `aclose()`。现有 `open_host.py:1266-1281` 的具体 iterator 已实现 `aclose()`。设计要求 Host Protocol、implementation 与 exports 使用同一类型——这消除了 Service 私有 cast（当前 `entrypoint_runtime.py:459`）。

竞态防护：设计明确 "调用方不得在 active `__anext__` 上并发调用 `aclose()`；Service 必须先停止并 await sole consumer task"。Host iterator 负责 started / never-started 两种幂等 cleanup。cursor future 在 never-started 路径也有收口要求。

### 2. attach-before-submit 与唯一 anext owner 状态机是否可实现且无竞态

**结论**：可实现，竞态已覆盖。

- **submit race**：`ATTACHED_UNBOUND` 窗口期间 Host mailbox 是唯一 buffer，consumer 等待 target binding 后才首次 `anext`
- **cancel terminal race**：live slot + `get_run` + Outbox 通过 terminal identity 去重
- **startup reconnect**：先 attach consumer 再做 backfill，容量一 terminal slot 顺序绑定
- **watcher failure**：typed error 写入 slot，consumer 进入 `DEGRADED` + durable recovery
- **caller cancellation**：stop → await task → 确认无 active `anext()` → `aclose()` → 释放 slot

设计要求 "command task、`get_run` probe、Outbox durable recovery 与 startup snapshot probe 都不得调用 `anext()`"——这保证了 sole consumer 的排他性。

### 3. 无二级 event buffer 是否成立

**结论**：成立，但有精确定义。

设计 §4.5："readiness、停止信号、target binding 与 terminal / failure 语义 slot 可以存在，但这些 primitive 不得保存任意事件副本或形成第二条事件序列。" 容量一 slot 不是 event buffer——它只保存一个 semantic result（terminal 或 typed failure），不是事件序列。

Service 删除 relay queue 后，唯一事件路径是 Host iterator → sole consumer → inline callback。consumer 不把 `HostSessionEvent` 复制给其它 task。

### 4. no-backpressure 承诺是否精确

**结论**：精确。

收窄后的承诺（design.md diff line 61, 105）明确区分：
- **已承诺**：Host publish 不 await 被动 consumer 或 mailbox capacity
- **未承诺**：同 event loop 阻塞 callback、CPU starvation、O(N) fanout 物理隔离

callback 快速非阻塞约束被正确转移为 Service/UI adapter 责任。

### 5. delivery error owner 是否正确

**结论**：正确。

- Error 语义 owner：Session Event Delivery subscription（不是 Host availability）
- Error code：`DELIVERY_INTERRUPTED`（不是 `UNAVAILABLE`）
- `retryable=false`（overflow 不可自动恢复）
- `limit_dimension` 暴露命中维度
- Service 映射：local degraded + durable recovery（不是 Host outage）
- 明确禁止复用旧 `HostUnavailableDetail` / `slow_consumer` / `session_live_stream`

### 6. byte 双界是否自洽

**结论**：自洽。

- **遍历边界完整**：envelope 6 fields + payload all string fields
- **排除项明确**：整数、datetime、enum、字段名、序列化标点、Python 对象头
- **primary dimension 固定**：先判 item count，再判 bytes；单事件超 bytes 报告 `PAYLOAD_BYTES`
- **一次计算后 fanout**：publisher 计算一次，同一 size 给所有 subscription
- **owner-loop 顺序**：sequence 分配 → 构造 → size → snapshot → `_offer` 在同一无 await 调用栈
- **精确扣减**：drain 时按 entry 保存的 size 扣减

设计正确声明 "该 budget 不宣称等于 Python heap resident bytes"。

### 7. O(1) terminal fence 是否自洽

**结论**：自洽。

- Fence 只覆盖 "当前 mailbox 已接收前缀" 与 "当前 durable terminal"
- `yield` 后 generator 恢复时立即释放
- iterator close/error 在 cleanup 释放
- 禁止 `terminal_run_ids` 集合无限增长
- Post-terminal truth 由 ingest late-state validation 拥有，subscription 不重做

### 8. 多 watcher admission / aggregate acceptance 是否自洽

**结论**：自洽，且正确处理了不确定性。

- 当前代码证明多订阅存在（`transient_delta.py:388-465` Hub 的 Session -> subscription set）
- 设计要求实施前必须做 topology audit
- 多订阅成立 → 同一 WU 交付 session admission / aggregate bound
- 单订阅收敛 → 以代码/测试证明后关闭
- 不授权无证据增加 Host-global quota
- 不把 per-sub bound 夸大为 Host total memory

## 阻塞 / Material Finding

### 0 Material Finding

首轮 CODEX-DESIGN-F01..F05 与 DS/MiMo 同类 findings 全部真实关闭。修订后的 normative design 在以下维度自洽：

- 公开可关闭 iterator + sole anext owner 状态机：可实现，无竞态
- 无二级 event buffer：成立（容量一 semantic slot 不是 event buffer）
- no-backpressure 承诺：已精确收窄到可证明范围
- delivery error owner：正确，typed，不复用 availability 语义
- byte 双界：遍历边界完整，一次计算后 fanout，owner-loop 顺序
- O(1) terminal fence：收窄为 current-terminal，释放语义明确
- 多 watcher admission/aggregate：正确处理为同一 WU prerequisite

## Residual Ownership

以下项不属于 design fix 阻塞项，已在未来 implementation WU scope 中正确归属：

| Residual | Owner | 触发条件 |
|---|---|---|
| packaged items/bytes 默认值 | 实施 WU（workload/SLO 测量） | 编码前 |
| low-cardinality metrics 设计 | 实施 WU | 编码前 |
| Python heap margin 校准 | 实施 WU（benchmark） | 编码前 |
| watcher topology audit | 实施 WU（Session Event Delivery owner） | 编码前 |
| 旧常量/术语迁移 | 实施 WU | 编码时 |
| control 文档冲突 WU 裁决 | control owner | 实施 WU 启动前 |
| callback 快速非阻塞验证 | Service/UI adapter owner | 实施 WU 测试时 |

## 结论

**Verdict：PASS。**

修订后的设计修正真实关闭了首轮全部 5 个 CODEX findings 和 6 个 DS/MiMo findings。normative design 在 iterator 可关闭性、sole consumer 状态机、无二级 buffer、no-backpressure 精确承诺、delivery error owner、byte 双界、O(1) terminal fence 和多 watcher admission 等维度自洽且可实现。Future WU scope 完整，未将当前可实施项留为 residual。

---

*Review artifact path: `docs/reviews/wu-transient-delivery-ownership-design-rereview-mimo.md`*
