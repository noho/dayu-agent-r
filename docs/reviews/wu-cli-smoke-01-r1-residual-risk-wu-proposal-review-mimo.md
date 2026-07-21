# WU-CLI-SMOKE-01-R1 Residual Risk WU 提案严格对抗复核

## 复核对象

`docs/reviews/wu-cli-smoke-01-r1-residual-risk-wu-proposal-codex.md`

## 复核范围

按用户硬约束，对提案五项裁决逐一挑战：直接证据充分性、当前 WU 可闭环性、WU 拆分合理性、R2 复用正确性、主总控格式合规性、未枚举风险、重复项与语义所有权漂移。

## 复核依据

- `docs/host/design.md`（Host 架构真源）
- `docs/engine/design.md`（Engine 架构真源）
- `docs/host/issues-implementation-control.md`（主总控）
- `docs/phaseflow-umbrella-optimization-control.md`（附加总控）
- `docs/reviews/wu-cli-smoke-01-r1-final-closeout.md`（R1 最终关闭）
- 提案引用的全部生产代码与测试文件

## 逐项裁决

### 1. live-only 不补放（提案项 1）

**提案裁决：** `accepted boundary`，从 remaining risks 删除。

**对抗挑战：** 是否遗漏当前可修 gap？

**代码复核：**

- `docs/host/design.md:359` 明确："断线、detach、Host close、进程退出或新 `open_host` runtime 均不补放 transient delta"。
- `dayu/host/transient_delta.py:216` 使用 `asyncio.Queue(maxsize=_TRANSIENT_WATCH_BUFFER_CAPACITY)`，overflow 时 `_overflowed = True` 并 detach（`:334-335`），没有 replay 路径。
- `dayu/host/open_host.py` 每次 `open_host(...)` 创建新 hub（`:1460-1549`），启动失败也关闭，不存在跨实例 replay source。
- `tests/host/test_transient_delta.py:157-190` 断言 fan-out 与 late attach 不补放。
- `tests/host/test_watch_session_events.py:659-805` 覆盖 never-started、detach、Host close 与 late attach 不 replay。

**证据充分性判断：** 直接设计文档、生产代码与测试三方一致，证明 live-only 是有意的 contract 选择，不是遗漏。没有"断线后恢复 transient delta"的独立产品需求时，该边界不应被误报为缺陷。

**current-WU-fix 判断：** 否。"修复"它意味着新增 durable transient log、ack/cursor、恢复与淘汰策略，或者破坏 live-only contract；这不是 R1 的最小修复，而是新的产品能力。

**裁决：`accepted`。** 同意从 remaining risks 删除。最终关闭已将其归类为 `accepted live-only boundary`，提案只是提供了更详细的证据链。

### 2. 固定容量 256（提案项 2）

**提案裁决：** `needs-more-evidence`，拆为 `WU-HOST-TRANSIENT-CAPACITY-01` 与 `WU-SVC-ENTRYPOINT-RELAY-CAPACITY-01` 两个 deferred WU。

**对抗挑战 A：** 是否真应拆成两个 WU？

**代码复核：**

- Host watcher 容量：`dayu/host/transient_delta.py:26` 定义 `_TRANSIENT_WATCH_BUFFER_CAPACITY: Final[int] = 256`，用于 subscription queue（`:216`）。生产者是 hub `publish()`（`:463-464`），消费者是 watcher `drain_nowait()`（`:242-258`）。满队列时 `_overflowed = True` 并 detach（`:333-335`），只影响该 watcher。
- Service relay 容量：`dayu/service/entrypoint_runtime.py:76` 定义 `_ENTRYPOINT_LIVE_EVENT_BUFFER_CAPACITY: Final[int] = 256`，用于 `_WatchAndWaitRuntime.queue`（`:1027`）。生产者是 `_drain_host_events()`（`:1049-1050` 使用 `await queue.put(event)`），消费者是 `wait_for_terminal()` 的 drain 循环。满队列时 backpressure 到 drain task，可能延迟 terminal observation。
- 两者的生产者、消费者、阻塞方式（`put_nowait` vs `await put`）、失败传播（detach vs backpressure）与观测指标不同。
- 设计真源 `docs/host/design.md:361` 明确 Host watcher 容量是 Host 私有 contract："第一版不增加 public tuning option"。

**拆分合理性判断：** 同意拆分。两者虽恰好取值相同，但语义 owner、失败域与调优维度不同。把两个 256 合并为一个"统一容量调参"WU 会混淆不同层的 contract。`phaseflow-umbrella-optimization-control.md` 的切分约束也要求"有不同 semantic owner"时才拆分。

**对抗挑战 B：** 是否可在当前 WU 直接闭环？

**代码复核：**

- `tests/host/test_transient_delta.py:311-346` 与 `tests/host/test_watch_session_events.py:545-617` 验证精确容量边界、slow watcher detach 与 durable terminal 可达。
- `tests/service/test_entrypoint_runtime.py:1781-1815` 验证 Service relay `maxsize == 256`。
- `tests/cli/test_transient_slow_consumer_path.py:52-55,129-155,230-400` 使用每类 400 个 delta 压过 256 容量，通过真实 Host → Service → CLI 路径验证 slow-consumer error、Outbox fallback 与 durable terminal。
- 上述测试只验证有界行为与失败隔离，不提供代表性生产 workload、消费时延、内存预算或 SLO。

**当前闭环判断：** 同意不能在当前 WU 闭环。没有 workload 与 SLO 时，把 256 改成任意其他值不会关闭风险；提前增加 public knob 或 unbounded queue 则会扩张 contract。当前可验证的是机制正确，不是参数最优。

**裁决：`accepted`。** 同意拆为两个 deferred-with-owner WU，不同意在当前 WU 闭环。

### 3. 无跨域可重放总序（提案项 3）

**提案裁决：** `accepted boundary`，从 remaining risks 删除。

**对抗挑战：** 是否遗漏当前可修 gap？

**代码复核：**

- `docs/host/design.md:345-359` 明确："durable 与 transient 是两个 sequence domain，不定义可比较的全局 sequence"。
- `dayu/host/api.py:2988-3054` 的 `HostTransientDelta` 只有 `runtime_id/runtime_sequence`，没有 durable `event_sequence`。
- `dayu/host/api.py:3411-3476` 的 `HostEvent` 携带 `event_sequence`，是完全不同的类型。
- `dayu/host/engine_ingest.py:864-875,5276-5294` 先完成 durable transaction，再 best-effort 发布 transient；transient 发布错误不回滚 durable state。
- `tests/host/test_transient_delta.py:138-154` 断言 durable/transient identity 字段分离。

**证据充分性判断：** 设计文档、类型定义、事务隔离与测试四方一致，证明双序列域是有意设计。"统一可重放序列"需要全新持久化/query contract，不是当前可修 gap。

**current-WU-fix 判断：** 否。任何"统一 sequence"若不持久化便不可重放，若持久化则改变 EventLog schema 与 public query contract。

**裁决：`accepted`。** 同意从 remaining risks 删除。

### 4. E2E 可控 worker（提案项 4）

**提案裁决：** `rejected`（作为 R1 remaining risk），从 remaining risks 删除。

**对抗挑战：** 是否有充分直接证据证明可控 worker 覆盖了 R1 failure matrix？

**代码复核：**

- `tests/cli/test_transient_slow_consumer_path.py:230-400` 通过真实 `open_host(...)`、Service entrypoint 与 CLI 路径执行，只注入 `TransientStreamWorkerFactory`。
- 测试断言 typed slow-consumer error、Outbox fallback、terminal 与清理，不是 mock 下游消费者。
- `docs/reviews/wu-cli-smoke-01-manual-validation-evidence.md:10-30` 已记录原始 `WU-CLI-SMOKE-01` 的真实 provider 调用与 HTTP 200 最终答案。
- `git diff main...HEAD -- dayu/cli/thinking.py` 显示 R1 变更集中在 runtime identity/sequence，不涉及 provider transport。
- 真实 provider 具有凭证、网络、成本和输出非确定性，也不能保证单次响应覆盖三类 delta。

**证据充分性判断：** R1 受影响的生产路径是 Engine delta 映射后的 Host fan-out、Service relay、CLI 展示及 slow-consumer/terminal failure。可控 worker 只替换 worker factory，其余路径均为生产实现。真实 provider 无法稳定构造相同的 failure matrix。

**裁决：`accepted`。** 同意从 remaining risks 删除。R1 的变更路径不包含 provider，可控 worker 已足够覆盖 R1 scope。

### 5. CLI thinking 160 字符（提案项 5）

**提案裁决：** `deferred`，复用已有 `WU-CLI-SMOKE-01-R2`，修正总控描述。

**对抗挑战 A：** 原描述是否确实失真？

**代码复核：**

- `dayu/cli/thinking.py:22` 定义 `_TEXT_MAX_CHARS: Final[int] = 160`。
- `:167-181` 的 `_single_line_delta_text(...)` 对单个 delta 做空白折叠与截断，超过 160 字符时追加 `"..."`。
- `:106-116` 的 `record(...)` 把每个已截断 delta 追加到 `_line_text`，没有累计 160 字符 cap。
- `tests/cli/test_thinking_renderer.py:11-83` 断言 thinking 输出、追加和单行行为。

**描述精确性判断：** 同意原描述失真。当前是"每个 delta 截断到 160 字符后持续追加"，累计行可以超过 160 字符。提案的精确描述"单 delta 160 截断 + 累计单行追加"更准确。

**对抗挑战 B：** R2 描述修正是否合理？

**代码复核：**

- `docs/host/issues-implementation-control.md:253` 当前文字："`CliThinkingRenderer` 当前保留 160 字符单行运行态展示"。
- 提案建议修正为："把每个 delta 单行化并按 160 字符截断后持续追加到同一运行态行，累计行并非 160 字符总上限，也没有可展开 panel/history"。

**修正合理性判断：** 同意修正。原文字"160 字符单行"容易被理解为累计总长，修正后语义更精确。

**裁决：`accepted`。** 同意复用 `WU-CLI-SMOKE-01-R2`，同意修正描述。

## WU 映射表与主总控格式审查

### 稳定 WU ID 审查

- `WU-HOST-TRANSIENT-CAPACITY-01`：新 ID，不与现有总控任何条目重复。✅
- `WU-SVC-ENTRYPOINT-RELAY-CAPACITY-01`：新 ID，不与现有总控任何条目重复。✅
- `WU-CLI-SMOKE-01-R2`：已有 ID（`issues-implementation-control.md:253`），复用正确。✅

### 主总控 Residual Risk 表格式审查

提案 5.1 的三行是否满足 `issues-implementation-control.md` 的 residual risk 表格式：

| 要求 | WU-HOST-TRANSIENT-CAPACITY-01 | WU-SVC-ENTRYPOINT-RELAY-CAPACITY-01 | WU-CLI-SMOKE-01-R2 |
|---|---|---|---|
| 稳定 ID | ✅ | ✅ | ✅ |
| 状态（open / deferred-with-owner / transferred-to-issue / closed） | ✅ `deferred-with-owner` | ✅ `deferred-with-owner` | ✅ `deferred-with-owner` |
| Owner / Destination | ✅ Host transient hub performance-validation lane | ✅ Service entrypoint runtime performance-validation lane | ✅ CLI UI adapter lane |
| 下一步 | ✅ 明确 trigger 与 next action | ✅ 明确 trigger 与 next action | ✅ 明确 trigger 与 next action |

**格式合规性：** ✅ 通过。

### 主总控 Current Work Units 表格式审查

提案 5.2 的三行是否满足 `issues-implementation-control.md` 的 current work units 表格式：

| 要求 | WU-HOST-TRANSIENT-CAPACITY-01 | WU-SVC-ENTRYPOINT-RELAY-CAPACITY-01 | WU-CLI-SMOKE-01-R2 |
|---|---|---|---|
| Work Unit ID | ✅ | ✅ | ✅ |
| 状态 | ✅ `deferred` | ✅ `deferred` | ✅ `deferred` |
| 主题 | ✅ | ✅ | ✅ |
| Owner / Destination | ✅ | ✅ | ✅ |
| 当前定位 | ✅ | ✅ | ✅ |

**格式合规性：** ✅ 通过。

### WU 条目字段完整性审查

提案 WU mapping table（第 3 节）每行是否包含用户要求的全部字段：

| 字段 | 全部五行 |
|---|---|
| 稳定 WU ID | ✅ |
| 状态 | ✅ |
| owner | ✅ |
| trigger | ✅ |
| next action | ✅ |
| non-goals | ✅ |
| proposed control rows | ✅（第 5 节） |

**字段完整性：** ✅ 通过。

## 未枚举风险检查

### 是否存在提案未枚举的 remaining risk？

**检查维度：**

1. **EventLog 写入放大：** R1 已通过删除 `REASONING_DELTA` 的 `PREVIEW` EventLog row 解决。三类 delta 均不写 EventLog（`docs/host/design.md:345`）。✅ 已关闭。
2. **Service relay backpressure 对 terminal observation 的延迟：** 提案项 2b 已覆盖。✅
3. **Host watcher overflow 后 CLI 的用户体感：** 提案项 1 的 accepted boundary 已覆盖（live-only contract）。✅
4. **transient delta dedupe key 冲突：** `transient_delta.py:81-93` 使用 `runtime_id + execution_id + worker_event_index` 的 SHA-256，在同一 runtime 内唯一。✅ 无风险。
5. **Hub close 后新 watch 的行为：** `docs/host/design.md:361` 明确"Host close 后新 watch 仍由 public lifecycle gate 抛 `HostClosedError`"。✅ 已在设计中覆盖。

**结论：** 未发现提案遗漏的 remaining risk。

## 语义所有权漂移检查

### 是否存在 semantic ownership drift？

1. **Host transient capacity vs Service relay capacity：** 提案正确识别两者 owner 不同（`HostTransientDeltaHub` vs `_WatchAndWaitRuntime.queue`），不应共享常量或 public knob。✅ 无 drift。
2. **CLI thinking display vs Host transient contract：** 提案正确识别 `CliThinkingRenderer` 是终端投影的唯一 owner，Host transient contract 不拥有 CLI 展示策略。✅ 无 drift。
3. **durable EventLog vs transient hub：** 提案正确维持两域分离，不引入跨域 cursor 或统一 sequence。✅ 无 drift。

**结论：** 未发现 semantic ownership drift。

## Existing WU / Issue 重复检查

### 是否存在 duplicate？

- `WU-STRESS-SQLITE-01` / Issue #38：面向 SQLite 慢盘与 durable persistence，不拥有 live watcher 或 Service relay 容量。✅ 不重复。
- `WU-WAIT-04`：面向 awaiting E2E，未覆盖 transient 容量或 provider conformance。✅ 不重复。
- `WU-CLI-DEBUG-STREAM-01` / Issue #148：面向逐 delta diagnostic logging，不拥有 bounded queue 容量或 thinking UX。✅ 不重复。
- `WU-ENG-01` / `WU-ENG-02`：属于 Engine provider 层，不拥有 Host watcher / Service relay / CLI thinking 语义。✅ 不重复。
- `WU-CLI-SMOKE-01-R2`：已有，提案正确复用。✅ 不重复。

**结论：** 未发现 duplicate。

## 过度设计检查

### 是否存在过度设计？

1. **两个 capacity WU 拆分：** 不是过度设计。两者 owner 不同、失败域不同、调优维度不同。合并会混淆 contract。✅ 合理。
2. **R2 描述修正：** 不是过度设计。只是语义精确化，不引入新 contract。✅ 合理。
3. **三项 accepted boundary 删除：** 不是过度设计。已有设计文档、类型定义与测试覆盖，不应为了形式制造 implementation WU。✅ 合理。

**结论：** 未发现过度设计。

## 用户硬约束合规检查

### 约束 1：所有真实 remaining risk 必须经过代码裁决后，以稳定 WU 形式进入主总控 residual 表和 current work units 表

- 项 2（容量）：经过代码裁决后，以 `WU-HOST-TRANSIENT-CAPACITY-01` 和 `WU-SVC-ENTRYPOINT-RELAY-CAPACITY-01` 进入。✅
- 项 5（CLI thinking）：经过代码裁决后，以 `WU-CLI-SMOKE-01-R2` 进入。✅
- 项 1、3、4：经代码裁决确认为 accepted boundary / rejected，不进入。✅

### 约束 2：凡能在当前 R1 WU 以正确 owner、最小正确实现和确定验证闭环关闭的，必须 current-WU-fix

- 项 1：关闭需要新 durable replay 协议，非最小修复。✅ 不 current-WU-fix。
- 项 2：缺少 workload/SLO，任意改常量无法证明更正确。✅ 不 current-WU-fix。
- 项 3：统一序列需要新持久化/query contract。✅ 不 current-WU-fix。
- 项 4：不存在 R1 代码缺口。✅ 不 current-WU-fix。
- 项 5：需要产品 UX 决策，非 R1 regression。✅ 不 current-WU-fix。

### 约束 3：不能为了形式把 accepted design boundary 伪装成 implementation risk

- 项 1、3：已确认为 accepted design boundary，不伪装为 risk。✅
- 项 4：已确认为 accepted test boundary，不伪装为 risk。✅

### 约束 4：不能把不同 owner 风险硬合并

- 项 2：Host watcher 与 Service relay 拆为两个独立 WU，不硬合并。✅

**结论：** 全部用户硬约束合规。

## 最终裁决汇总

| 提案项 | 提案裁决 | 复核裁决 | current-WU-fix | 理由 |
|---|---|---|---|---|
| 1. live-only 不补放 | `accepted boundary` | **accepted** | 否 | 设计文档、类型、测试三方一致；live-only 是有意 contract 选择 |
| 2. 固定容量 256 | `needs-more-evidence` / 拆两个 WU | **accepted** | 否 | 语义 owner/失败域不同；缺少 workload/SLO；拆分合理 |
| 3. 无跨域总序 | `accepted boundary` | **accepted** | 否 | 双序列域是有意设计；统一序列需新 contract |
| 4. 可控 worker | `rejected` | **accepted** | 否 | R1 变更路径不包含 provider；可控 worker 已覆盖 R1 failure matrix |
| 5. CLI thinking UX | `deferred` / 复用 R2 | **accepted** | 否 | 描述修正准确；需要产品 UX 决策 |
| WU 拆分 | 两个 capacity WU | **accepted** | — | 不同 semantic owner，不同失败域 |
| R2 复用 | 复用已有 ID | **accepted** | — | 正确识别已有条目，避免重复 |
| 格式合规 | — | **✅ 通过** | — | 稳定 ID、状态、owner、trigger、next action、non-goals 均完整 |
| 未枚举风险 | — | **✅ 无** | — | 五项覆盖完整 |
| 语义所有权漂移 | — | **✅ 无** | — | 三域分离正确维持 |
| WU/Issue 重复 | — | **✅ 无** | — | 已核对全部相关 WU 与 Issue |
| 过度设计 | — | **✅ 无** | — | 拆分与裁决均合理 |

## 复核结论

**全部五项裁决 accepted。** 提案的代码证据充分、语义 owner 判定正确、WU 拆分合理、R2 复用正确、主总控格式合规、未发现遗漏风险或语义所有权漂移。无 finding 需要修正或补充。

## Verification

```bash
# 提案引用的代码路径已全部直接读取并验证
# 未修改任何生产代码、测试、README、design、control、Issue 或 PR metadata
# 未 commit、push、mark ready、merge、request reviewers 或进入下一 gate
```

## Completion Status

`review-complete / all-findings-accepted / no-modifications-required`
