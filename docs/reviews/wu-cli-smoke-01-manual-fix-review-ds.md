# WU-CLI-SMOKE-01 / MANUAL-F01 Fix Adversarial Review (AgentDS)

## 审查定位

本 artifact 是 AgentDS 对 MANUAL-F01 的 root cause 分析与候选修复方案进行的 adversarial review，目标是：验证 root cause 与用户观察现象同源、审核候选修复是否符合设计真源和分层、评估是否存在更优方案、确定必测项和真实验证项。

**不涉及代码修改**。本 review 只基于直接代码证据和设计真源进行裁决。

## 直接证据链

### 现象

- `dayu-cli interactive` 中 LLM 调用 `start_fins_download` 后返回 failed tool result，错误类型为 `HostDurableError`
- `dayu-cli download --ticker V` 直接下载路径正常启动 Fins progress
- DB `host_wait_records` 表为空，无 `TOOL_AWAITING` / `RUN_WAITING` / `ATTEMPT_SUSPENDED` EventLog 事件
- 探针复现：`accept transaction` 抛 `HostDurableError`，cause 为 SQLite CHECK constraint failed：`snapshot_ref`、`snapshot_captured_at`、`snapshot_digest` 必须同存同缺
- Fins 工具构造的 `ToolAwaitSnapshot` 有 `snapshot_ref` 和 `captured_at` 但 `snapshot_digest=None`

### Root Cause 定位

**root cause 确认为 `dayu/host/tool_runtime.py:6952-6965` 的 `_wait_snapshot_ref` 函数。**

证据链逐层追溯：

#### Layer 1: Engine contract — `ToolAwaitSnapshot` 无 digest

`dayu/contracts/tool_await.py:71-83`:
```python
class ToolAwaitSnapshot:
    snapshot_id: str
    captured_at: datetime
    # 注意：无 snapshot_digest 字段
```

这是 Engine 契约类型。Engine 不拥有 durable snapshot 语义，只透传 opaque `snapshot_id` 与采集时间。设计正确，无缺陷。

#### Layer 2: Fins 工具构造 — 传入 snapshot 但无 digest

`dayu/fins/tools/_ingestion_tool_helpers.py:39-53`:
```python
return ToolAwaitingOutcome(
    await_spec=ToolAwaitSpec(...),
    snapshot=ToolAwaitSnapshot(
        snapshot_id="fins-observation-start-{kind}-{timestamp}",
        captured_at=captured_at,
    ),
)
```

Fins 工具按 Engine 契约构造 snapshot，snapshot 非空，有 `snapshot_id` 和 `captured_at`。无缺陷。

#### Layer 3: Host 翻译层 — `_wait_snapshot_ref` 硬编码 `snapshot_digest=None`

`dayu/host/tool_runtime.py:6952-6965`:
```python
def _wait_snapshot_ref(outcome: ToolAwaitingOutcome) -> WaitSnapshotRef | None:
    if outcome.snapshot is None:
        return None
    return WaitSnapshotRef(
        snapshot_id=outcome.snapshot.snapshot_id,
        captured_at=outcome.snapshot.captured_at,
        snapshot_digest=None,  # <--- BUG: 硬编码 None
    )
```

**这是缺陷位置。** `WaitSnapshotRef` 的 Python 类型允许 `snapshot_digest=None`（`state.py:380` 声明为 `str | None`，`__post_init__` 使用 `_require_optional_non_empty_text`），`None` 在 Python 层合法。

#### Layer 4: Durable schema — CHECK constraint 拒绝不完整 snapshot

`dayu/host/durable/schema.py:752-760`:
```sql
CHECK (
    (snapshot_ref IS NULL
      AND snapshot_captured_at IS NULL
      AND snapshot_digest IS NULL)
    OR
    (snapshot_ref IS NOT NULL
      AND snapshot_captured_at IS NOT NULL
      AND snapshot_digest IS NOT NULL)
)
```

此 CHECK 要求三个字段要么全 NULL，要么全 NOT NULL。

#### Layer 5: INSERT 失败链

`serialize_wait_snapshot_ref(ref)` → `ref.snapshot_id` → `"fins-observation-start-..."` → NOT NULL
`serialize_wait_snapshot_captured_at(ref)` → `format_utc_timestamp(ref.captured_at)` → `"2026-07-06T..."` → NOT NULL
`serialize_wait_snapshot_digest(ref)` → `ref.snapshot_digest` → `None` → NULL

INSERT 的三列值为 `(NOT NULL, NOT NULL, NULL)` → CHECK 要求 `(NOT NULL, NOT NULL, NOT NULL)` → **FAIL** → `HostDurableError`

#### Layer 6: 错误传播到用户可见层

`_accept_awaiting` (line 3456) → `_accept_awaiting_with_retry` (line 3662) → `accept_tool_awaiting` 事务失败（line 420-429 of `waiting.py`）→ INSERT 失败触发 `HostTransactionRetryExhaustedError` → 重试耗尽后返回 `ToolAwaitingAcceptTimedOut` → Engine 收到 failed outcome → LLM 看到 "failed tool result"

#### Layer 7: 为什么 direct `dayu-cli download --ticker V` 不受影响

Direct download 走 `dayu/cli/commands/fins.py:_run_fins_direct_command_async` 路径，使用 Service → Fins direct pipeline，全程不经过 Engine tool-calling/awaiting/accept/wait-record-INSERT 路径。因此完全 bypass 了 CHECK constraint bug。

### Root Cause 与用户现象的因果同源性

**确认完全同源。** 所有观察到的现象都由 `_wait_snapshot_ref` 的 `snapshot_digest=None` 硬编码单一缺陷解释：

| 观察现象 | 因果解释 |
|---|---|
| `start_fins_download` 返回 failed tool result | INSERT 失败 → accept 超时 → failed outcome |
| 错误类型为 `HostDurableError` | SQLite CHECK constraint 在 durable 写入时违反 |
| cause 为 CHECK constraint failed | `snapshot_digest=NULL` 但另两列 NOT NULL |
| DB 无 `host_wait_records` | 事务在 INSERT 处失败，整批回滚 |
| 无 `TOOL_AWAITING` / `RUN_WAITING` / `ATTEMPT_SUSPENDED` | 同事务在 INSERT 之后才 append EventLog，回滚后无事件 |
| `dayu-cli download --ticker V` 正常 | bypass Engine tool-calling/awaiting 路径 |
| `ToolAwaitSnapshot` 有 `snapshot_ref` 和 `captured_at` 无 digest | Engine 契约类型确实不含 digest 字段 |

没有间接迹象、没有推测、没有"可能是"——全部可沿着调用链逐层验证。

## 候选修复方案审查

### 候选方案

> 在 Host ToolRuntime 的 `_wait_snapshot_ref` 为 Engine awaiting snapshot 派生稳定 digest，避免写入不完整 durable snapshot。

具体：在 `_wait_snapshot_ref` 中，当 `outcome.snapshot is not None` 时，从 `snapshot_id` 和 `captured_at` 派生稳定 digest（例如 `sha256(snapshot_id + "|" + captured_at.isoformat())`），替代硬编码的 `None`。

### 分层正确性审查

#### 是否在正确的层修复？

**是。** `_wait_snapshot_ref` 是 Engine `ToolAwaitSnapshot` → Host `WaitSnapshotRef` 的唯一翻译边界。修复应该在此：

- **Engine** 不能承担此修复——`ToolAwaitSnapshot` 不含 `snapshot_digest` 字段，且 Engine 不拥有 durable snapshot 语义（Engine 设计真源 §1："Engine 不保存跨 run 状态，不拥有工具注册表"）。
- **Fins 工具层** 不能承担此修复——Fins 工具返回 `ToolAwaitingOutcome`，这是 Engine 契约。如果 Fins 添加 digest，那属于 Engine 契约扩展，违反"下层组件接口设计不得向上泄漏实现细节"的架构硬约束。
- **Durable schema** 不应放松——CHECK 约束确保 snapshot 数据的结构完整性，是 Host durable truth 的正确防御。
- **Host `_wait_snapshot_ref`**——这是 Engine 契约到 Host durable schema 的规范翻译点。Host 拥有 durable snapshot truth，应该在这个边界完成从 Engine opaque ref 到 Host durable digest 的补充。

#### 是否违反设计真源？

**没有。** Host 设计真源 `docs/host/design.md:2313-2315` 规定：

> `adapter_key`、`await_kind`、`resume_token`、`external_job_id` 与 `snapshot_ref` 必须是强类型字段或受限 typed refs，不能把 adapter 对象、callable、无结构 metadata bag 或外部系统私有 payload 放进 durable row。

候选方案从已有强类型字段（`snapshot_id` + `captured_at`）计算稳定摘要，不引入无结构 bag、不依赖外部系统私有 payload，符合"强类型字段或受限 typed refs"约束。

#### 是否影响 Engine ingest 验证？

**不会。** 存在两条独立验证路径：

1. `engine_ingest.py:3733-3749` `_await_snapshot_matches_wait(snapshot: ToolAwaitSnapshot, wait_record)`——比较 Engine 的 `ToolAwaitSnapshot`（无 digest）与 wait record。**只检查 `snapshot_id` + `captured_at`，不检查 `snapshot_digest`**。修复后仍然匹配。

2. `engine_ingest.py:3615-3634` `_payload_snapshot_matches_wait(payload, wait_record)`——比较 Host `TOOL_AWAITING` EventLog payload（由 `_event_payload.py:433-446` 的 `_snapshot_ref_json` 从 `WaitSnapshotRef` 构造）与 wait record。**检查全部三字段包括 digest**。修复后 payload 的 digest 与 wait record 的 digest 来自同一个 `WaitSnapshotRef`，`None == None` → `True`。原本也匹配（两个都是 None）。

#### 是否存在新风险？

**两个需要注意的风险点：**

1. **直接 Engine 路径**：如果存在不经过 Host `_wait_snapshot_ref` 而直接调用 `WaitSnapshotRef(snapshot_digest=None)` 或 `deserialize_wait_snapshot_ref(..., snapshot_digest=None)` 的代码路径，需要一并检查。经搜索，当前代码中 `WaitSnapshotRef` 的直接构造仅在 `_wait_snapshot_ref` 和 `deserialize_wait_snapshot_ref` 中出现。

2. **digest 计算函数选择**：`snapshot_id` 是 Fins 工具生成的可读 id（如 `"fins-observation-start-download-20260706T..."`），`captured_at` 是 UTC timestamp。直接拼接后 sha256 是确定性操作，但建议利用已有 `sha256_digest_json` 基础设施，统一 digest 计算方式。

### 是否存在更优最佳实践方案？

**逐一排除替代方案：**

#### 方案 B：在 `ToolAwaitSnapshot` 增加 `snapshot_digest` 字段

**拒绝。** 理由：
- Engine 不拥有 durable snapshot 语义（Engine 设计真源 §1）
- 让 Engine 契约带上 durable digest 是向上泄漏 Host durable 概念
- Fins 工具和其他 future providers 都需要理解并正确填充 digest → 扩散责任
- 违反"设计下层组件接口时，必须假设上层组件不存在"的架构硬约束

#### 方案 C：松动 durable CHECK constraint

**拒绝。** 理由：
- CHECK constraint 的 all-or-none 不变量是数据完整性承诺
- 允许 `snapshot_ref` NOT NULL 但 `snapshot_digest=NULL` 意味着 durable 层接受不完整数据
- 后续任何消费 snapshot_digest 的代码都需要处理 NULL 分支 → 扩散防御代码
- 当前缺陷的本质是上游没填值，不应让 durable schema 降低完整性要求来迁就

#### 方案 D：在 `_accept_awaiting` 中 snapshot 不为空时去掉 snapshot_ref

**拒绝。** 理由：
- `snapshot_id` 和 `captured_at` 是有价值的诊断信息（例如 EventLog `TOOL_AWAITING` payload 可展示等待快照）
- 丢弃信息是降级，不是修复
- WaitSnapshotRef 设计为可选项——snapshot_ref 字段在 Fins 场景下提供了有意义的初始观测语义

#### 候选方案 A vs 方案 B/C/D 裁决

**候选方案 A 胜出。** 它是唯一同时满足以下约束的方案：
- ✅ 在正确的分层位置修复（Host 翻译边界）
- ✅ 不修改 Engine 契约
- ✅ 不降低 durable schema 完整性
- ✅ 不丢失有价值信息
- ✅ 尊重 Host 对 durable truth 的所有权
- ✅ 不扩散责任到 Fins 工具或其他 providers

### 方案 A 的具体实现建议

在 `_wait_snapshot_ref` 中派生稳定 digest：

```python
def _wait_snapshot_ref(outcome: ToolAwaitingOutcome) -> WaitSnapshotRef | None:
    if outcome.snapshot is None:
        return None
    digest = sha256_digest_json({
        "snapshot_id": outcome.snapshot.snapshot_id,
        "captured_at": outcome.snapshot.captured_at.isoformat(),
    })
    return WaitSnapshotRef(
        snapshot_id=outcome.snapshot.snapshot_id,
        captured_at=outcome.snapshot.captured_at,
        snapshot_digest=digest,
    )
```

要点：
- 使用项目已有的 `sha256_digest_json` 基础设施
- digest 输入为 `snapshot_id` + `captured_at`，两者都来自 Engine 的不可变 snapshot 引用
- digest 是确定性的：相同输入始终产生相同 digest
- 不影响 `_await_snapshot_matches_wait` 的 Engine 路径验证（该函数不检查 digest）
- 不影响 `_payload_snapshot_matches_wait` 的 Host payload 验证（`_snapshot_ref_json` 会从 `WaitSnapshotRef` 读取 digest 投影到 payload）

## 必测项 / 真实验证项

### 单元级必测项（pytest）

| 编号 | 测试项 | 目的 |
|---|---|---|
| UT-01 | `_wait_snapshot_ref` 传入 `outcome.snapshot=None` 返回 `None` | 无快照路径不受影响 |
| UT-02 | `_wait_snapshot_ref` 传入 Fins snapshot 返回 digest 非 None 的 `WaitSnapshotRef` | 核心修复验证 |
| UT-03 | 同一 snapshot_id + captured_at 两次调用返回相同 digest | 确定性 |
| UT-04 | 不同 snapshot_id 或不同 captured_at 返回不同 digest | 区分性 |
| UT-05 | `WaitSnapshotRef` 带 digest 的 serialize/deserialize roundtrip 保持 digest 不变 | durable 读写正确性 |
| UT-06 | `_tool_awaiting_accept_candidate` 构建的 candidate 中 snapshot_ref 的 digest 非 None | 端到端传递 |

### 集成级必测项（pytest）

| 编号 | 测试项 | 目的 |
|---|---|---|
| IT-01 | Host awaiting accept 完整路径：Fins snapshot → `_wait_snapshot_ref` → `accept_tool_awaiting` → INSERT 成功 → wait record 可读 | 端到端修复验证 |
| IT-02 | `serialize_wait_snapshot_digest` 返回非 None 值 | 序列化层修复验证 |
| IT-03 | Engine ingest `_await_snapshot_matches_wait` 对带 digest 的 wait record 正确匹配 | Engine 路径验证不受影响 |
| IT-04 | Engine ingest `_payload_snapshot_matches_wait` 对带 digest 的 payload 正确匹配 | Host payload 路径验证不受影响 |
| IT-05 | 无 snapshot（`outcome.snapshot=None`）的 awaiting tool 仍然 INSERT 成功 | 空 snapshot 路径回归 |

### 真实环境验证（manual）

| 编号 | 测试项 | 命令 | 预期 |
|---|---|---|---|
| MV-01 | interactive 中 `start_fins_download` 正常进入 awaiting | `dayu-cli interactive` → 输入"用 start_fins_download 下载 V 的年报" | 工具调用后显示 waiting/进度，不报 HostDurableError |
| MV-02 | `host_wait_records` 表有记录 | 同上，观察 durable DB | 表中有至少一条 status=waiting 记录，snapshot_digest 非空 |
| MV-03 | EventLog 有 TOOL_AWAITING / RUN_WAITING / ATTEMPT_SUSPENDED | 同上，观察 EventLog | 三个事件均有记录 |
| MV-04 | direct `dayu-cli download --ticker V` 继续正常工作 | `dayu-cli download --ticker V` | 回归验证 |
| MV-05 | `dayu-cli prompt` 中 `start_fins_download` 也正常 | `dayu-cli prompt "用 start_fins_download 下载 V 的年报"` | interactive 和 prompt 两条路径均修复 |

### pyright / 测试覆盖率

- pyright: `0 errors, 0 warnings`（现有标准）
- 受影响测试通过：Host durable/waiting、ToolRuntime、Fins tools、CLI interactive
- 单文件覆盖率 ≥ 80%（按 AGENTS 编码硬约束）

## Residual Risk

| ID | Risk | Severity | Owner |
|---|---|---|---|
| R1 | `WaitSnapshotRef.__post_init__` 允许 `snapshot_digest=None`，与 durable CHECK constraint 不一致——Python 校验比 SQL 约束宽松 | Low | 当前修复本身不改变此 gap，但未来若其他路径直接构造 `WaitSnapshotRef(snapshot_digest=None)` 仍会触发相同错误。建议后续在 `WaitSnapshotRef` 的 Python 校验层也强制 all-or-none，实现 defense in depth | deferred：不阻塞当前 fix，但应在 `_wait_snapshot_ref` 修复中同步考虑是否加固 `__post_init__` |
| R2 | `snapshot_digest` 的语义未被设计真源精确定义——当前只说了"快照摘要"，没有说明应该在哪个边界产生、由谁拥有、用途是什么 | Low | 不影响本次修复，但建议在 `docs/host/design.md` 的 Wait Record 章节补充 `snapshot_digest` 的生成边界和所有权的简要说明 |

## 审查结论

| 维度 | 裁决 |
|---|---|
| Root cause 与用户现象同源 | **确认同源**。`_wait_snapshot_ref` 硬编码 `snapshot_digest=None` → INSERT CHECK violation → HostDurableError → failed tool result。全部现象由单一缺陷解释，无间接推测。 |
| 候选修复符合设计真源和分层 | **确认符合**。修复在正确的 Host 翻译边界，不修改 Engine 契约，不降低 durable schema 完整性，不扩散责任。 |
| 存在更优最佳实践方案 | **不存在**。三个替代方案（改 Engine 契约、松 CHECK、丢弃 snapshot）均有设计缺陷。候选方案 A 是唯一满足全部架构约束的方案。 |
| 可实施性 | **可实施**。修复范围明确：仅 `dayu/host/tool_runtime.py` 的 `_wait_snapshot_ref` 函数。连带影响可控：仅需确保 `sha256_digest_json` 已在作用域内可导入。 |
| 建议 | **可以进入 implementation gate**。建议在 implementation 时同步加固 `WaitSnapshotRef.__post_init__` 的 Python 层校验（添加 all-or-none invariant），实现 defense in depth。 |

**Review verdict: `pass` — candidate fix is approved for implementation gate entry.**
