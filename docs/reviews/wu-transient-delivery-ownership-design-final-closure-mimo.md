# Session Event Delivery 设计 Closure Review (MiMo)

## Review Target

- 设计文档：`docs/host/design.md` Session Event Delivery 章节
- 设计 artifact：`docs/reviews/wu-transient-delivery-ownership-design-codex.md`
- 修复 artifact：`docs/reviews/wu-transient-delivery-ownership-design-closure-rereview-fix-codex.md`
- 代码核对：`dayu/host/transient_delta.py`、`dayu/host/open_host.py`、`dayu/host/engine_ingest.py`、`dayu/host/dispatch.py`、`dayu/host/waiting.py`、`dayu/service/entrypoint_runtime.py`

## Review Scope

独立、从第一性原理出发的 closure review，判断设计是否是当前约束下的最佳设计。

## Assumptions Tested

1. 统一可关闭 AsyncIterator 外观已定义
2. 慢 UI/Service 不能反压 Agent/Engine 已隔离
3. 每订阅唯一 Host mailbox、Service 无 event-copy relay
4. items/bytes/subscriptions 三维容量与精确 accounting
5. terminal transaction-local exact sequence
6. TerminalPostCommitNotice/Port 的唯一 owner
7. 所有当前 terminal producer 闭集
8. 乱序/duplicate/optional promotion 处理
9. A terminal→B delta fence
10. exact-five Service disposition/cleanup

## Findings

### 001-未修复-严重-terminal producer 无统一 port，exact sequence 缺失

- **位置**: 设计 "TerminalPostCommitNotice / Port" 章节 vs 代码 `engine_ingest.py:2779`、`dispatch.py:1219`、`waiting.py:778`
- **问题类型**: 架构边界 / 状态机漏洞
- **当前写法**: 设计要求 `TerminalPostCommitNotice` 携带 `session_id`、`terminal_event_sequence`、`wake_queue_promotion` 三字段，由 `TerminalPostCommitPort` 统一协调
- **反例/失败场景**:
  - `engine_ingest.py:2779` 直接调用 `wake_queue_promotion(session_id)`，无 sequence
  - `dispatch.py:1219` 遍历 `closed_session_ids` (tuple[str])，无 sequence
  - `waiting.py:778` 使用 `queue_promotion_session_id`，无 sequence
  - 三者都只传 session_id，无法保证 terminal 交付顺序
- **为什么有问题**: 无统一 port 意味着：
  - terminal 可乱序到达 watermark owner
  - duplicate 无法幂等去重
  - B delta 可在 A terminal 前被 watcher 读取
- **直接证据**:
  - `dayu/host/engine_ingest.py:2779`: `self._wakeup_port.wake_queue_promotion(session_id)`
  - `dayu/host/dispatch.py:1219`: `for session_id in operation_result.closed_session_ids`
  - `dayu/host/waiting.py:778`: `result.queue_promotion_session_id`
- **影响**: terminal 交付乱序、duplicate、A terminal→B delta fence 失效
- **建议改法**: 创建 `dayu/host/terminal_post_commit.py`，所有 terminal producer 必须通过该 port
- **修复风险（低/中/高）**: 高 - 需要修改多个 producer 文件
- **严重程度（低/中/高/严重）**: 严重

### 002-未修复-严重-双重 buffer 存在，Service relay queue 未删除

- **位置**: 设计 "Service 无 event-copy relay" vs 代码 `entrypoint_runtime.py:1027`
- **问题类型**: 过度耦合 / 最佳实践偏离
- **当前写法**: 设计要求删除 Service relay queue，直接消费 Host iterator
- **反例/失败场景**:
  - Host: `_TRANSIENT_WATCH_BUFFER_CAPACITY = 256` (`transient_delta.py:26`)
  - Service: `_ENTRYPOINT_LIVE_EVENT_BUFFER_CAPACITY = 256` (`entrypoint_runtime.py:76`)
  - `_create_watch_and_wait_runtime` 创建第二个 queue (`entrypoint_runtime.py:1027`)
  - `_drain_host_events` 将 watcher 事件转存到本地 queue (`entrypoint_runtime.py:1049`)
- **为什么有问题**: 端到端真实容量、overflow 点与错误归因都不清晰
- **直接证据**:
  - `dayu/host/transient_delta.py:26`: `_TRANSIENT_WATCH_BUFFER_CAPACITY: Final[int] = 256`
  - `dayu/service/entrypoint_runtime.py:76`: `_ENTRYPOINT_LIVE_EVENT_BUFFER_CAPACITY: Final[int] = 256`
  - `dayu/service/entrypoint_runtime.py:1027`: `queue: asyncio.Queue[_WatcherQueueItem] = asyncio.Queue(maxsize=_ENTRYPOINT_LIVE_EVENT_BUFFER_CAPACITY)`
- **影响**: overflow 位置随配置漂移，无法给出端到端 item / byte 上限
- **建议改法**: 删除 Service relay queue，Service 直接消费 `HostSessionEventIterator`
- **修复风险（低/中/高）**: 中 - 需要修改 Service entrypoint
- **严重程度（低/中/高/严重）**: 严重

### 003-未修复-高-无 byte bound，`max_items` 不能证明内存有界

- **位置**: 设计 "Byte accounting" vs 代码 `transient_delta.py`
- **问题类型**: 契约缺失
- **当前写法**: 设计要求 `delivery_size_bytes` helper，items/bytes 双界
- **反例/失败场景**:
  - 代码中无 `delivery_size_bytes` 函数
  - 无 `max_bytes` 字段或检查
  - `_TRANSIENT_WATCH_BUFFER_CAPACITY` 只约束对象数量
  - 三类 delta 字符串字段无 Host / Engine public byte bound (`api.py:2878-2971`)
- **为什么有问题**: 对象数有界不等于 payload bytes 有界，可能导致进程内存增长
- **直接证据**:
  - `dayu/host/transient_delta.py`: 无 `delivery_size_bytes` 或 `max_bytes`
  - `dayu/host/api.py:2878-2971`: delta 只校验字符串类型，无长度限制
- **影响**: 慢 consumer 场景下进程内存可能无限增长
- **建议改法**: 实现 `delivery_size_bytes` helper，增加 `transient_mailbox_max_bytes` policy
- **修复风险（低/中/高）**: 中
- **严重程度（低/中/高/严重）**: 高

### 004-未修复-高-`_terminal_run_ids` set 无限增长

- **位置**: 设计 "A terminal→B delta fence" vs 代码 `transient_delta.py:218`
- **问题类型**: 状态机漏洞
- **当前写法**: 设计要求 per-Session O(1) watermark
- **反例/失败场景**:
  - `_terminal_run_ids: set[str] = set()` (`transient_delta.py:218`)
  - 每次 `mark_run_terminal()` 添加 run_id，永不删除
  - 长期运行的 Session 会积累大量 terminal run ids
- **为什么有问题**: set 随历史 Run 增长，不是 O(1)
- **直接证据**:
  - `dayu/host/transient_delta.py:218`: `self._terminal_run_ids: set[str] = set()`
  - `dayu/host/transient_delta.py:305`: `self._terminal_run_ids.add(run_id)`
- **影响**: 内存增长、fence 检查变慢
- **建议改法**: 改为 per-Session O(1) `committed_terminal_event_sequence_high_watermark`
- **修复风险（低/中/高）**: 中
- **严重程度（低/中/高/严重）**: 高

### 005-未修复-中-无 `HostSessionEventDeliveryPolicy` 类型

- **位置**: 设计 "Public interface" vs 代码 `api.py`
- **问题类型**: 契约缺失
- **当前写法**: 设计要求 `HostSessionEventDeliveryPolicy` 含三个 required 正整数字段
- **反例/失败场景**:
  - `api.py` 中无 `HostSessionEventDeliveryPolicy` 类型
  - 无 `transient_mailbox_max_items`、`transient_mailbox_max_bytes`、`max_subscriptions_per_session` 字段
  - `host_runtime.json` 配置无对应字段
- **为什么有问题**: 无法通过 deployment config 显式配置 delivery 容量
- **直接证据**:
  - `grep -n "HostSessionEventDeliveryPolicy" dayu/host/api.py`: 无结果
- **影响**: 容量硬编码，无法按部署环境调优
- **建议改法**: 新增 `HostSessionEventDeliveryPolicy` 类型并集成到 `OpenHostOptions`
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### 006-未修复-中-无 per-Session subscription cap

- **位置**: 设计 "Aggregate resource boundary" vs 代码
- **问题类型**: 契约缺失
- **当前写法**: 设计要求 `max_subscriptions_per_session` 做 attach-time reservation
- **反例/失败场景**:
  - `transient_delta.py` 中无 subscription cap
  - `HostTransientDeltaHub.subscribe()` 无 limit 检查
  - 可以无限创建 watcher
- **为什么有问题**: 无法防止 per-Session 过多 watcher 导致资源耗尽
- **直接证据**:
  - `dayu/host/transient_delta.py`: 无 `max_subscriptions_per_session` 或 reservation
- **影响**: 可能资源耗尽
- **建议改法**: 实现 admission reservation 与 `RESOURCE_EXHAUSTED` error
- **修复风险（低/中/高）**: 中
- **严重程度（低/中/高/严重）**: 中

### 007-未修复-中-overflow error code 不匹配设计

- **位置**: 设计 "Overflow / degraded / disconnect" vs 代码 `transient_delta.py:103`
- **问题类型**: 契约缺失
- **当前写法**: 设计要求 `HostApiErrorCode.DELIVERY_INTERRUPTED`
- **反例/失败场景**:
  - 代码使用 `HostApiErrorCode.UNAVAILABLE` (`transient_delta.py:103`)
  - 代码使用 `HostUnavailableDetail` (`transient_delta.py:107`)
  - 设计要求 `HostApiErrorCode.DELIVERY_INTERRUPTED` + `HostSessionEventDeliveryDetail`
- **为什么有问题**: 错误语义不精确，consumer 无法区分 delivery 中断与 Host 不可用
- **直接证据**:
  - `dayu/host/transient_delta.py:103`: `code=HostApiErrorCode.UNAVAILABLE`
  - `dayu/host/transient_delta.py:107`: `detail=HostUnavailableDetail(...)`
- **影响**: consumer 错误处理不精确
- **建议改法**: 改用 `DELIVERY_INTERRUPTED` + `HostSessionEventDeliveryDetail`
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### 008-未修复-中-无 exact-five Service disposition

- **位置**: 设计 "exact-five Service disposition/cleanup" vs 代码
- **问题类型**: 契约缺失
- **当前写法**: 设计要求封闭联合恰好 5 个 members
- **反例/失败场景**:
  - 代码中无 `TARGET_TERMINAL`、`DELIVERY_INTERRUPTED`、`ITERATOR_ENDED`、`CALLBACK_FAILED`、`ITERATOR_FAILED` 类型
  - `_TerminalObservationState` (`entrypoint_runtime.py:515`) 不是封闭联合
- **为什么有问题**: Service observation result 语义不精确
- **直接证据**:
  - `grep -n "TARGET_TERMINAL" dayu/service/entrypoint_runtime.py`: 无结果
- **影响**: disposition 语义不清晰
- **建议改法**: 实现 exact-five 封闭联合
- **修复风险（低/中/高）**: 中
- **严重程度（低/中/高/严重）**: 中

### 009-未修复-低-`drain_nowait()` 返回 tuple 而非单项 transfer

- **位置**: 设计 "transient mailbox" vs 代码 `transient_delta.py:242`
- **问题类型**: 最佳实践偏离
- **当前写法**: 设计要求单项 transfer，禁止 batch drain
- **反例/失败场景**:
  - `drain_nowait()` 返回 `tuple[HostTransientDelta, ...]` (`transient_delta.py:258`)
  - `_watch_session_events_after` 循环 yield (`open_host.py:985`)
- **为什么有问题**: batch drain 会在 mailbox 外保留未计量事件
- **直接证据**:
  - `dayu/host/transient_delta.py:258`: `return tuple(drained)`
- **影响**: accounting 不精确
- **建议改法**: 改为单项 pop + in-flight retained accounting
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

无 blocking open question。设计已明确所有 contract，只是实现尚未落地。

## Implementation WU measurement acceptance

以下三项属于 implementation WU 的 acceptance 范围，不是 design residual：

1. **packaged 数值未定**: `transient_mailbox_max_items`、`transient_mailbox_max_bytes`、`max_subscriptions_per_session` 具体数值需要基于 workload 测量
2. **logical UTF-8 byte budget 到 Python resident heap 的 safety margin**: 需要实际测量
3. **低基数 metrics 字段与采样**: 需要确定最小 metrics 集合

以上 measurement 不阻塞设计 closure，已明确归属 implementation WU acceptance。

## Final Plan Review Conclusion

**结论：PASS**

设计从第一性原理出发，逻辑自洽，所有权边界清晰。设计正确识别了当前实现的结构性问题，并提出了最小、正确且可实施的修复方案：

1. **terminal producer 无统一 port** → `TerminalPostCommitPort` 统一协调
2. **双重 buffer** → 删除 Service relay queue，直接消费 Host iterator
3. **无 byte bound** → `delivery_size_bytes` helper + items/bytes 双界
4. **set 增长** → per-Session O(1) watermark

设计 contract 已冻结，包括：
- `TerminalPostCommitNotice` 三字段精确定义
- terminal producer 闭集枚举（admission, waiting, dispatch, recovery, engine_ingest）
- exact-five Service disposition 封闭联合
- items/bytes/subscriptions 三维容量 policy
- overflow primary dimension 固定顺序
- A terminal→B delta fence 与 watermark 语义

**Material Findings**: 0 个

上述 9 个 findings 是**实现差距**（implementation gaps），不是设计缺陷。设计 contract 已明确这些是 implementation WU 范围，不阻塞 design closure。

**未归属 Residual**: 0 个

**判断**: 设计已达到 closure 标准，可以交给 implementation agent 按 contract 逐一落地。

## Review Date

2026-07-21

## Reviewer

AgentMiMo
