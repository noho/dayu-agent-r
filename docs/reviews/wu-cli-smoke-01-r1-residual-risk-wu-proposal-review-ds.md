# WU-CLI-SMOKE-01-R1 Residual-Risk WU Proposal 对抗复核

## 1. Scope 与复核方法

- 复核对象：`docs/reviews/wu-cli-smoke-01-r1-residual-risk-wu-proposal-codex.md`（下称"提案"）。
- 复核性质：严格对抗复核，重点挑战五项用户指定维度；不修改提案、生产代码、测试、设计文档、README、control document、PR/Issue metadata。
- 独立真源：
  - `docs/host/design.md`（Host 架构真源）
  - `docs/engine/design.md`（Engine 架构真源）
  - `docs/host/issues-implementation-control.md`（主总控）
  - `docs/phaseflow-umbrella-optimization-control.md`（附加总控）
  - `docs/reviews/wu-cli-smoke-01-r1-final-closeout.md`（R1 final closeout）
  - 当前分支生产代码：`dayu/host/transient_delta.py`、`dayu/host/engine_ingest.py`、`dayu/host/open_host.py`、`dayu/service/entrypoint_runtime.py`、`dayu/cli/thinking.py`
  - 当前分支测试：`tests/host/test_transient_delta.py`、`tests/host/test_watch_session_events.py`、`tests/host/test_transient_delta_stress.py`、`tests/service/test_entrypoint_runtime.py`、`tests/cli/test_thinking_renderer.py`、`tests/cli/test_transient_slow_consumer_path.py`
- 复核不重新执行 pytest/pyright；提案 Section 7 已验证 75 passed + 1 stress passed + pyright 0 errors + git diff --check pass。复核聚焦代码路径与语义 owner 的对抗验证。

## 2. 逐挑战裁决

### 2.1 Challenge 1：删除 live-only、无跨域总序、可控 worker 是否有充分直接证据，是否遗漏当前可修 gap

#### 2.1.1 live-only 不补放（提案 Item 1）

**独立代码验证：**

- `dayu/host/transient_delta.py:26`：`_TRANSIENT_WATCH_BUFFER_CAPACITY = 256`，私有模块常量，bounded queue。
- `dayu/host/transient_delta.py:321-336`：`_offer()` 使用 `put_nowait`，满队列 → `_overflowed=True` + detach，不等待、不丢弃单个 delta、不反压 EventLog。
- `dayu/host/transient_delta.py:477-494`：`Hub.close()` 清空所有订阅 buffer 并唤醒 watcher，不保留未消费 delta。
- `dayu/host/open_host.py:1460`：每次 `open_host()` 创建新的 `HostTransientDeltaHub()`，`runtime_id` 为新 UUID，不存在跨 Host 实例 replay source。
- `docs/host/design.md:359`：明确 "断线、detach、Host close、进程退出或新 `open_host` runtime 均不补放 transient delta"。

**对抗测试：** 提案引用的测试行已通过独立代码路径核对，断言一致。fan-out、late attach 不补放、detach/terminal/hub close、overflow isolation 均有直接 owner-level 测试覆盖。

**裁决：`accepted`（认可提案的 accepted-boundary 判定）。** 不存在可修复 gap。任何"补放"实现都需要新的 durable transient log、ack/cursor、恢复与淘汰策略——这是新的产品能力，不是 bug fix。当前 WU 不应实施。

**current-WU-fix：否。**

---

#### 2.1.2 无跨域可重放总序（提案 Item 3）

**独立代码验证：**

- `dayu/host/api.py:2988-3054`：`HostTransientDelta` 只携带 `runtime_id`/`runtime_sequence`（transient domain）。
- `dayu/host/api.py:3411-3476`：`HostEvent` 携带 durable `event_sequence`。
- 类型层：`runtime_sequence` 是 `int`，`event_sequence` 是 `int`，但没有公共可比类型或统一 cursor——两套 sequence 分属不同 dataclass。
- `dayu/host/engine_ingest.py:871-875`：transient publish 发生在 durable transaction commit 之后，两者不在同一提交序列。
- `dayu/host/engine_ingest.py:5276-5302`：`_publish_transient_delta()` 隔离 publish 异常，transient 发布失败不回滚 durable transaction。
- `docs/host/design.md:359`："durable 与 transient 是两个 sequence domain，不定义可比较的全局 sequence"。

**对抗测试：** `tests/host/test_transient_delta.py:138-154` 断言 durable/transient identity 字段分离；`tests/host/test_watch_session_events.py:493-617` 断言 live delta + durable terminal 各自正确且 transient EventLog row 为 0。测试验证的是 terminal fence（同 Run 内 transient 在 durable terminal 前交付），不是虚构全序。

**裁决：`accepted`（认可提案的 accepted-boundary 判定）。** 全序需要新的 Host public persistence/query contract，变更 EventLog schema、事务边界与恢复策略。当前无产品需求时实施是过度设计。

**current-WU-fix：否。**

---

#### 2.1.3 可控 worker 替代真实 provider（提案 Item 4）

**独立代码验证：**

- `tests/cli/test_transient_slow_consumer_path.py:230-400`：通过真实 `open_host()`、Service entrypoint 与 CLI 路径执行；`TransientStreamWorkerFactory` 只替换 worker factory，其余 Host→Service→CLI 路径均为生产实现。
- `tests/cli/test_transient_slow_consumer_path.py:257-265`：factory 按确定性的 `TransientStreamCounts`（每类 400 个 delta）产生三类 delta，覆盖真实 overflow（400 > 256）。
- `git diff main...HEAD -- dayu/cli/thinking.py` 确认 R1 对 renderer 的生产变更集中在 runtime identity/sequence，不涉及 provider transport。
- `docs/reviews/wu-cli-smoke-01-manual-validation-evidence.md:10-30` 已记录原始 `WU-CLI-SMOKE-01` 的真实 provider 调用与 HTTP 200 最终答案。
- `docs/reviews/wu-cli-smoke-01-final-closeout.md:87` 起记录真实交互用户验证。

**对抗分析：** 真实 provider 具有凭证、网络、成本和输出非确定性，无法稳定覆盖三类 delta × overflow/terminal 的确定性组合。可控 worker 是测试该 failure matrix 的正确选择，不是妥协。R1 受影响生产路径（Host fan-out → Service relay → CLI renderer → slow-consumer/terminal）已全部被确定性覆盖。

**裁决：`accepted`（认可提案的 rejected-as-R1-remaining-risk 判定）。** 真实 provider smoke 按既有 Engine/provider 流程继续运行即可，不应伪装为 R1 未关闭代码风险。

**current-WU-fix：否。**

---

### 2.2 Challenge 2：固定容量是否真应按 Host watcher 与 Service relay 拆成两个 WU，或可在当前 WU 直接闭环/应合并

**独立代码验证：**

- Host watcher 容量：`dayu/host/transient_delta.py:26`：`_TRANSIENT_WATCH_BUFFER_CAPACITY: Final[int] = 256`，私有于 `HostTransientDeltaSubscription`。
- Service relay 容量：`dayu/service/entrypoint_runtime.py:76`：`_ENTRYPOINT_LIVE_EVENT_BUFFER_CAPACITY: Final[int] = 256`，私有于 `_WatchAndWaitRuntime.queue`。
- 两个常量分属不同模块、不同层（Host vs Service），不存在共享常量或跨层引用。

**失败域对比：**

| 维度 | Host watcher 256 | Service relay 256 |
|---|---|---|
| Owner | `HostTransientDeltaSubscription` / hub | `_WatchAndWaitRuntime` / drain task |
| 生产者 | Hub.publish() → sub._offer() non-blocking | `_drain_host_events()` → `await queue.put()` blocking |
| 消费者 | watcher iterator → drain_nowait() | `_drain_available_watcher_items()` → `queue.get_nowait()` |
| 满队列行为 | 仅 detach 该 watcher，抛 typed `slow_consumer` error | backpressure 阻塞 drain task，进而反压 Host watcher iterator |
| 对其他订阅者影响 | 隔离，快 watcher 不受影响 | N/A（Service 只有一条 drain task） |
| 可观测信号 | `HostApiError(code=UNAVAILABLE, component="session_live_stream", reason_code="slow_consumer")` | `_WatcherFailure` → activity diagnostic → Outbox fallback |

**对抗分析：合并 vs 拆分 vs 当前闭环：**

1. **合并为单一 WU 的错误：** 两个队列的生产者、消费者、阻塞语义、失败传播与观测信号不同。合并且共享常量会引入跨层耦合、掩盖 owner 差异，并在未来单独调参时无法独立验证。这违反 semantic ownership 原则。

2. **当前 WU 直接闭环的错误：** 没有代表性生产 workload、delta burst 分布、消费 SLO、内存预算或 slow-consumer 可接受频率。把 256 改成任意其他值不会关闭任何已知风险；增加 public knob、共享常量或 unbounded queue 反而扩张 contract 并掩盖 owner 差异。当前可验证的是机制正确（bounded、隔离、typed failure），不是参数最优。

3. **拆分为二的正确性：** 两个 WU 对应两个不同的 semantic owner、失败域和验证矩阵。`WU-HOST-TRANSIENT-CAPACITY-01` 验证 Host watcher 的 slow-consumer 频率/backlog/交付延迟；`WU-SVC-ENTRYPOINT-RELAY-CAPACITY-01` 验证 Service relay 的 backlog/watcher failure/Outbox fallback 频率/终态延迟。两者可独立 profile、独立裁决、独立调参。

**裁决：`accepted`（认可拆分，拒绝合并，拒绝当前闭环）。**

**current-WU-fix：否（对两个 capacity WU 均否）。**

---

### 2.3 Challenge 3：CLI R2 是否应当前修、复用是否正确、描述是否精确

**独立代码验证：**

- `dayu/cli/thinking.py:21-23`：`_TEXT_MAX_CHARS = 160`，`_TRUNCATED_SUFFIX = "..."`。
- `dayu/cli/thinking.py:167-181`：`_single_line_delta_text()` 对**每个 delta** 做空白折叠与截断到 160 字符。
- `dayu/cli/thinking.py:106-116`：`record()` 把每个已截断 delta **追加**到 `self._line_text`，没有累计 160 字符 cap。
- 实际行为：每个 delta 单行化截断到 160 → 追加到同一行 → 累计行可远超 160 字符。不是"整行总上限 160"。
- `docs/host/issues-implementation-control.md:253`：现有 R2 描述为"160 字符单行运行态展示"——容易被理解为累计总上限 160，属于不精确描述。

**对抗分析：**

1. **是否应当前修：否。** R2 需要先选定至少三项产品语义：累计缓冲上限、滚动或可展开交互、TTY/非 TTY 与历史保留边界。直接删除 160、把累计行硬截断或引入 panel 都会未经需求选择不同用户体验，并扩张 R1 的 runtime identity 修复 scope。`git diff main...HEAD -- dayu/cli/thinking.py` 确认 160 字符逻辑来自 R1 之前，不是本 PR 引入的 regression。

2. **复用是否正确：是。** `docs/host/issues-implementation-control.md:253` 已存在 `WU-CLI-SMOKE-01-R2`，与第 5 项完全同源。Section 4.1 的 duplicate audit 确认无其他 CLI thinking WU。复用避免重复 ID。

3. **描述是否精确：提案的修正精确。** 提案将"160 字符单行运行态展示"修正为"每个 delta 单行化并按 160 字符截断后持续追加到同一运行态行，累计行并非 160 字符总上限，也没有可展开 panel/history"。该修正准确反映 `_single_line_delta_text()` 的 per-delta 截断 + `record()` 的累计追加行为。

**裁决：`accepted`（认可 defer、复用 R2、描述修正）。**

**current-WU-fix：否。**

---

### 2.4 Challenge 4：稳定 WU ID、状态、owner、trigger、next action、non-goals 与 proposed control rows 是否满足主总控约束

**独立格式核对：**

- 提案 Section 5.1（Residual Risk Reconciliation 表）格式：`| ID | 状态 | Owner / Destination | 下一步 |`——与主总控 line 249 的现有表头一致。
- 提案 Section 5.2（Current Work Units 表）格式：`| Work Unit | 状态 | 主题 | Owner / Destination | 当前定位 |`——与主总控 line 257 的现有表头一致。

**逐 WU 约束核对：**

| 约束项 | WU-HOST-TRANSIENT-CAPACITY-01 | WU-SVC-ENTRYPOINT-RELAY-CAPACITY-01 | WU-CLI-SMOKE-01-R2 |
|---|---|---|---|
| 稳定 ID | ✓ 遵循 `WU-{LAYER}-{DOMAIN}-{SEQ}` 命名 | ✓ 遵循命名约定 | ✓ 复用已有 ID |
| 状态 | `deferred-with-owner`—合法状态值 | `deferred-with-owner`—合法 | `deferred-with-owner`—合法 |
| Owner | Host transient hub performance-validation lane—明确 | Service entrypoint runtime performance-validation lane—明确 | CLI UI adapter lane—明确 |
| Trigger | 代表性 workload/SLO 或生产 slow-consumer 观测—证据门控 | 代表性消费 workload/SLO 或 relay backlog 观测—证据门控 | 用户明确 UX 要求—需求门控 |
| Next action | owner-level profile/benchmark → 决定保留或调参 | 单独 profile relay/drain → 决定保留或调参 | goal confirmation → 冻结展示 contract → 实现 |
| Non-goals | 不修改 Service relay；不共享跨层常量；不增加 public knob/unbounded queue/replay | 不修改 Host watcher；不跨层共享常量；不 silent drop/unbounded relay | 不改 Host transient/durable contract；不持久化 thinking；不增加 replay |
| 来源标注 | ✓ 标注来源 `WU-CLI-SMOKE-01-R1` | ✓ 标注来源 | ✓ 已存在于主总控 |
| 无 GitHub Issue 标注 | ✓ 标注"无 GitHub Issue" | ✓ 标注 | ✓ 标注 |

**主总控约束合规（`docs/host/issues-implementation-control.md:233-238`）：**
- 每条有稳定 id ✓
- 每条有来源 work unit ✓
- 每条有状态（均为 `deferred-with-owner`，非 `open`）✓
- 每条有 owner/destination ✓
- 每条有下一步动作 ✓
- 不保留无 owner 的 open item ✓

**裁决：`accepted`。** 三项 proposed control rows 均满足主总控格式与约束。

---

### 2.5 Challenge 5：是否存在未枚举的 remaining risk、existing WU/Issue duplicate、semantic ownership drift 或过度设计

#### 2.5.1 未枚举 remaining risk

**独立扫描：**

- 对 `dayu/host/transient_delta.py` 全部 public API 做 boundary audit：`subscribe`/`publish`/`drain_nowait`/`wait_ready`/`overflow_error`/`mark_run_terminal`/`close`——均已由设计文档和测试覆盖。
- 对 `dayu/service/entrypoint_runtime.py` 的 relay 路径做 boundary audit：`_create_watch_and_wait_runtime` → `_drain_host_events` → `_drain_available_watcher_items` → `_emit_entrypoint_thinking_from_transient_delta`——所有分支均有测试覆盖或类型守卫（`assert_never`）。
- 对 `dayu/cli/thinking.py` 做 boundary audit：`record`/`finish_runtime_display`/`close`——runtime identity 序列校验、去重、关闭后拒绝均有覆盖。
- 对其他固定常量的检查：`_OUTBOX_TERMINAL_READ_LIMIT = 50`（`entrypoint_runtime.py:71`）是 Outbox 读取分页上限，不属于 transient capacity 域；`ENTRYPOINT_STARTUP_PROMOTION_MAX_ATTEMPTS = 20`（`entrypoint_runtime.py:70`）是启动 promotion 重试上限，也不同域。均不构成遗漏的 transient capacity 风险。

**裁决：未发现未枚举 remaining risk。**

#### 2.5.2 Existing WU/Issue duplicate

**独立核对（补充提案 Section 4 的 audit）：**

- `WU-STRESS-SQLITE-01` / Issue #38：SQLite 慢盘 durable persistence。live in-memory watcher/relay 容量不属于其 scope。确认不重复。
- `WU-CLI-DEBUG-STREAM-01` / Issue #148：逐 delta diagnostic logging。不拥有 bounded queue 容量或 slow-consumer SLO。确认不重复。
- `WU-ENG-01` / `WU-ENG-02`：Engine provider 层。不能替代 Host→Service→CLI 确定性 E2E。确认不重复。
- `WU-WAIT-04`：awaiting E2E smoke。不覆盖 transient 容量或 provider conformance。确认不重复。
- 提案 Section 4.2 的 GitHub Issue 搜索结论（`thinking`/`transient`/`slow consumer`/`relay` 无直接重复项）经独立 re-grep 确认。

**裁决：未发现未枚举 duplicate。**

#### 2.5.3 Semantic ownership drift

**独立检查：**

1. **Test capacity constant duplication（minor note）：**
   - `tests/service/test_entrypoint_runtime.py:1787`：`assert runtime.queue.maxsize == 256`——magic number，未引用生产常量 `_ENTRYPOINT_LIVE_EVENT_BUFFER_CAPACITY`。
   - `tests/cli/test_transient_slow_consumer_path.py:53`：`_SERVICE_RELAY_CAPACITY = 256`——独立定义，与生产常量 `_ENTRYPOINT_LIVE_EVENT_BUFFER_CAPACITY = 256` 恰好相等但无引用关系。
   - 影响：若生产常量变更，测试需手动同步。这是 minor test hygiene concern，不构成生产 semantic ownership drift。两个测试的断言目标均是行为正确性（bounded、overflow），不是常量值本身。**不阻塞提案，不要求 current-WU-fix。**

2. **Service relay 常量未暴露：** `_ENTRYPOINT_LIVE_EVENT_BUFFER_CAPACITY` 是模块私有常量（`_` 前缀），与 Host 的 `_TRANSIENT_WATCH_BUFFER_CAPACITY` 同为私有。两者都未通过 public API 暴露，符合设计文档"第一版不增加 public tuning option"的决策。确认无 drift。

**裁决：`accepted`（无 material semantic ownership drift）。测试常量 duplication 为 accepted-as-note，不构成 current-WU-fix。**

#### 2.5.4 过度设计

**独立检查：**

- 两个 capacity WU 的 trigger 均为证据门控（有 workload/SLO 或生产观测后才进入 profile/benchmark），不是直接进入 implementation。避免了无证据时盲目实施。
- 两个 WU 的 non-goals 均明确阻止：public knob、unbounded queue、跨层共享常量、silent drop、replay。避免了 contract 扩张。
- R2 的 trigger 为需求门控（用户明确 UX 要求后才进入 goal confirmation）。避免了无需求时实施。
- 提案建议的 allowed files 是最小必要集（各自 owner 模块 + 对应测试 + 必要时 `utils/` 分析脚本）。

**裁决：未发现过度设计。**

---

## 3. 提案五项逐项独立裁决汇总

| 提案项 | 提案裁决 | 复核裁决 | current-WU-fix | 备注 |
|---|---|---|---|---|
| 1. live-only 不补放 | accepted boundary | `accepted` | 否 | 设计、类型、测试一致；无 gap 可修 |
| 2a. Host watcher 256 | needs-more-evidence → deferred | `accepted` | 否 | owner/失败域独立，拆分正确 |
| 2b. Service relay 256 | needs-more-evidence → deferred | `accepted` | 否 | 同上；合并为单一 WU 是错误的 |
| 3. 无跨域总序 | accepted boundary | `accepted` | 否 | 双序列域是设计意图 |
| 4. 可控 worker | rejected as R1 residual | `accepted` | 否 | R1 生产路径已被确定性覆盖 |
| 5. CLI R2 | deferred，复用 R2 | `accepted` | 否 | 描述修正精确，复用正确 |

## 4. 补充发现

### F01：Test relay capacity magic number（accepted-as-note）

- **路径：** `tests/service/test_entrypoint_runtime.py:1787`
- **现状：** `assert runtime.queue.maxsize == 256` 使用 magic number，未引用生产常量 `_ENTRYPOINT_LIVE_EVENT_BUFFER_CAPACITY`。
- **严重度：** low。测试目标是验证 bounded 行为，不是常量值审计。生产常量变更时测试会因断言失败而捕获变更。
- **裁决：`accepted-as-note`。** 不阻塞提案，不要求 current-WU-fix。未来若执行 `WU-SVC-ENTRYPOINT-RELAY-CAPACITY-01` 的 validation 阶段，可顺带改为引用生产常量。

### F02：E2E test capacity constant duplication（accepted-as-note）

- **路径：** `tests/cli/test_transient_slow_consumer_path.py:53`
- **现状：** `_SERVICE_RELAY_CAPACITY = 256` 独立定义，与 `_ENTRYPOINT_LIVE_EVENT_BUFFER_CAPACITY` 无引用关系。
- **严重度：** low。测试的 `blocked_yield_count` 计算依赖该值，变更生产常量时需同步更新。这是测试 fixture 的常规耦合，不构成 semantic ownership drift。
- **裁决：`accepted-as-note`。** 同 F01，未来 validation 阶段可顺带改为引用。

## 5. 提案修正建议

以下修正**仅写入本 artifact**，不修改提案原文件。由总控 owner 在后续 reconciliation 中裁决是否采纳。

### 5.1 R2 描述修正的精确行

提案 Section 5.1 中 R2 的 Residual Risk Reconciliation 行已精确。其对应的 Current Work Units 行（Section 5.2）主题为"Expandable CLI thinking runtime display"——该主题精确反映了需要产品决策后才能确定的 feature 范围。

### 5.2 建议澄清：两个 capacity WU 的互斥性

提案 Section 3 的 WU mapping table 中，2a 和 2b 的 non-goals 已明确互斥（2a 不修改 Service relay，2b 不修改 Host watcher）。建议在写入主总控的 control rows 中显式增加一行互斥声明，防止未来实施时联动调参。但这是建议，不构成提案 defect。

## 6. 结论

**Overall verdict：`accepted`。**

五项提案裁决均经独立代码路径验证通过。三项的删除（live-only、无跨域总序、可控 worker）均有充分设计、类型和测试证据支撑，无遗漏可修 gap。固定容量拆分为两个 owner-independent WU 是正确的——合并会制造跨层"god WU"并掩盖不同失败域。CLI R2 的 defer、复用与描述修正均精确。三项 proposed control rows 满足主总控格式与约束。未发现未枚举 remaining risk、existing WU/Issue duplicate、material semantic ownership drift 或过度设计。

**所有五项均不应 current-WU-fix。** 无因 defer 而遗漏的 current-WU implementation slice。

**两项补充发现（F01、F02）为 accepted-as-note**，不阻塞提案，不要求当前修改。

---

- **复核日期：** 2026-07-21
- **复核人：** AgentDS（对抗复核）
- **复核范围：** 提案全部五项 + 主总控约束合规 + 补充 duplicate/drift/over-design 扫描
- **独立验证的真源：** 设计文档、控制文档、生产代码（6 个关键文件）、测试（6 个关键文件）
- **未执行的操作：** 未修改提案、生产代码、测试、设计文档、README、control document、PR/Issue metadata；未 commit、push、mark ready、merge、request reviewers
- **Stop status：** `review-complete / verdict-accepted / no-blocking-findings`
