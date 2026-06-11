# WU-PROJ-01 Slice 4 Code Review — DeepReview

## 元数据

- Work unit：`WU-PROJ-01`
- Slice：Slice 4 accepted compact -> Conversation Memory -> ordinary RunInput regression
- Gate：review (DeepReview)
- 日期：2026-06-11
- 审查者：Claude (deepseek-v4-pro)
- 分支：`wu-proj-01`
- 审查范围：未提交改动（3 modified files + 1 untracked implementation artifact）
- Artifact path：`docs/reviews/wu-proj-01-slice4-code-review-ds.md`

## Preflight

```
branch: wu-proj-01
modified:
  M tests/host/test_dispatch_scheduler.py
  M tests/host/test_memory_projection.py
  M tests/host/test_run_input_builder.py
untracked:
  ?? docs/reviews/wu-proj-01-slice4-implementation-codex.md
```

生产代码未修改；改动全部在测试文件与 implementation artifact。

## 结论：PASS

## 审查结果总览

| # | 审查项 | 结果 |
|---|--------|------|
| 1 | accepted compact 经 durable ProjectionRunner 物化五类 memory section 并推进 checkpoint | PASS |
| 2 | ordinary RunInput 证明读到 projection snapshot 中的五类业务 section | PASS |
| 3 | failed compact negative regression：不物化 memory snapshot/items，不生成 compact artifact | PASS |
| 4 | 过窄/脆弱断言、测试污染、AGENTS.md 违规 | PASS-WITH-NOTES |
| 5 | S3-R1 未覆盖是否可接受 | ACCEPTABLE |

## 1. accepted compact → ProjectionRunner → 五类 memory section + checkpoint（PASS）

### 测试入口

**`test_projection_consumer_applies_event_and_writes_durable_vnext_snapshot`** (`tests/host/test_memory_projection.py:627`)

### 链路覆盖

```text
EventLog.append(CONTEXT_COMPACTED)
  -> ProjectionRunner.run_once(consumer_id, limit=10)
    -> ConversationMemoryProjectionConsumer.apply(event, previous_snapshot=None)
    -> write_memory_snapshot_with_checkpoint (同一 durable write transaction)
  -> read_latest_memory_snapshot (read transaction)
  -> 断言五类 section 均已物化
  -> 断言 checkpoint 已推进到 compact-1
```

### 断言覆盖

测试新增了以下关键断言（原测试仅验证 evidence_fact 与 item_kinds）：

| 断言 | 覆盖的 section | 行号 |
|------|---------------|------|
| `latest.snapshot.latest_compaction_event_ref == "compact-1"` | compact event 引用 | 695 |
| `latest.snapshot.session_summary_memory.summary_text == "用户关注收入增速和毛利率变化。"` | Session Summary | 696-698 |
| `latest.snapshot.evidence_fact_memory.evidence_backed_facts[0].claim_text == "收入增长。"` | Verified Evidence and Facts | 699-701 |
| `latest.snapshot.answer_anchor_memory.anchors[0].anchor_title == "收入口径"` | Prior Answer Anchors | 703-705 |
| `latest.snapshot.forward_intent_memory.intents[0].text == "下一轮继续核对费用率。"` | Open Follow-up Context | 706-708 |
| `latest.snapshot.trace_memory.reference_continuity_items[0].text == "该公司继续指向当前分析主体。"` | Reference Continuity | 709-711 |
| `checkpoint.checkpoint_event_sequence == 1` | checkpoint sequence | 713 |
| `checkpoint.checkpoint_event_id == "compact-1"` | checkpoint event id | 714 |
| `latest.snapshot.cursor.checkpoint_event_sequence == checkpoint.checkpoint_event_sequence` | cursor↔checkpoint 一致性 | 715-718 |
| `latest.snapshot.cursor.checkpoint_event_id == checkpoint.checkpoint_event_id` | cursor↔checkpoint id 一致性 | 719 |
| `set(item_kinds) == {answer_anchor, evidence_backed_fact, forward_intent, reference_continuity, session_summary}` | 五类 memory item 均已写入 durable table | 720-726 |

### 评价

- **不是只测 builder helper**：测试走完整的 `ProjectionRunner.run_once()` durable path，包括 durable write transaction 内的 consumer apply + snapshot write + checkpoint commit，再用 read transaction 读回并断言。
- **cursor↔checkpoint 一致性断言**（715-719）是关键增强：证明 snapshot.cursor 与 projection_checkpoint 来自同一 durable write transaction，这是 Slice 4 plan 明确要求的 "projection checkpoint advanced in same transaction"。
- **item_kinds 集合断言**（720-726）证明五类 memory item 均被写入 `host_memory_items` durable table，不是只有 snapshot JSON blobs。

## 2. ordinary RunInput 读取 projection snapshot 中的五类 section（PASS）

### 测试入口

**`test_run_input_memory_messages_include_context_compacted_projection`** (`tests/host/test_run_input_builder.py:1427`)

### 链路覆盖

```text
_append_rich_memory_source_events (写入 CONTEXT_COMPACTED 到 EventLog)
  -> _seed_current_run (创建 running Run + ATTEMPT_STARTED)
  -> _required_memory_cursor (读取 required cursor = ATTEMPT_STARTED 前 event sequence)
  -> catch_up_conversation_memory_projection (bounded catch-up 到 required cursor)
  -> _build_request_with_memory (DurableMemorySnapshotProvider -> RunInputBuilder.build)
  -> 断言 system_content 包含五个 ## Section Header
  -> 断言 per-message content 包含业务内容
```

### 断言覆盖

| 断言 | 覆盖的 section | 行号 |
|------|---------------|------|
| `"## Conversation Summary" in system_content` | Session Summary section header | 1453 |
| `any("summary=episode navigation only" in content ...)` | Session Summary 业务内容 | 1454 |
| `"## Verified Evidence and Facts" in system_content` | Evidence Facts section header | 1455 |
| `"claim_text=Revenue increased year over year" in system_content` | Evidence Facts 业务内容（system envelope 内） | 1456 |
| `"## Prior Answer Anchors" in system_content` | Answer Anchors section header | 1457 |
| `any("compact pinned goal" in content ...)` | Answer Anchors 业务内容 | 1458 |
| `"## Open Follow-up Context" in system_content` | Forward Intents section header | 1459 |
| `any("compact open question" in content ...)` | Forward Intents 业务内容 | 1460 |
| `"## Reference Continuity" in system_content` | Reference Continuity section header | 1461 |
| `any("second factor: margin mix" in content ...)` | Reference Continuity 业务内容 | 1462 |
| `contents[-1] == "current prompt"` | current input 在最后位置 | 1463 |

### 评价

- **双重断言设计合理**：system_content 断言验证 one-system-message envelope 中有五个 `## Section Header`（由 `run_input.py:2544-2600` 的 `_build_conversation_memory_envelope` 渲染）；per-message content 断言验证具体业务内容（如 `summary=episode navigation only`、`claim_text=Revenue increased year over year`）确实出现在渲染后的 messages 中。
- **链路完整**：从 EventLog CONTEXT_COMPACTED → projection catch-up → DurableMemorySnapshotProvider → RunInputBuilder.build → AgentRunRequest.messages，覆盖了 Slice 4 plan 定义的完整回归链。
- **`_single_system_content` 辅助校验**：该 helper（line 3857）同时校验 one-system-message contract（唯一 system message 在 messages[0] 位置）和不暴露内部治理标识，这是对 AGENTS.md Agent 语义约束的遵守。

## 3. failed compact negative regression（PASS）

### 3a. ProjectionRunner 层：failed compact 不物化 memory（PASS）

**`test_projection_consumer_skips_failed_compact_without_memory_snapshot`** (`tests/host/test_memory_projection.py:729`)

断言矩阵：

| 断言 | 含义 | 行号 |
|------|------|------|
| `result.events_scanned == 1` | ProjectionRunner 扫描了 1 个事件 | 782 |
| `result.events_matched == 0` | consumer 的 event filter 不匹配 CONTEXT_COMPACTION_FAILED | 783 |
| `result.events_applied == 0` | consumer 未 apply 该事件 | 784 |
| `latest is None` | 未写入任何 memory snapshot | 785 |
| `item_count == 0` | 未写入任何 memory item | 786 |
| `checkpoint is not None` | checkpoint 存在（被 ProjectionRunner 推进） | 787 |
| `checkpoint.checkpoint_event_sequence == 1` | checkpoint 推进到 event_sequence=1 | 788 |
| `checkpoint.checkpoint_event_id == "compact-failed-1"` | checkpoint 指向 failed compact 事件 | 789 |

**关键设计验证**：
- `events_matched == 0` 证明 `ConversationMemoryProjectionConsumer` 的 event filter 确实不消费 `CONTEXT_COMPACTION_FAILED`，与 Slice 4 plan 中 "不修改生产代码" 的前提一致。
- checkpoint 仍然推进到 `compact-failed-1`：这是 `ProjectionRunner` 的正确行为 — 即使 consumer 不消费，runner 也要标记该事件已被扫描，避免后续无限循环同一条事件。

### 3b. Dispatch 层：failed compact 不生成 compact artifact（PASS）

**`test_pre_start_governance_compact_failure_is_attempt_free`** (`tests/host/test_dispatch_scheduler.py:4409`)

新增断言：
```python
compact_artifact_root = tmp_path / "compact-artifacts"    # line 4415
...
compact_artifact_root=compact_artifact_root,               # line 4427
...
assert _compact_artifact_files(compact_artifact_root) == ()  # line 4459
```

**链路验证**：
- Scheduler 使用 `_soft_compact_policy()`（触发 soft threshold compact）但不传 `context_compactor` → compactor 为 None → compaction 失败 → fallback dispatch。
- `_compact_artifact_files(compact_artifact_root) == ()` 断言 compact artifact 根目录下无任何文件。
- 配合既有的 `CONTEXT_COMPACTED == 0` 断言（line 4438），双重确认 failed compact 不提交 compact artifact 也不写 CONTEXT_COMPACTED event。

**`_compact_artifact_files` helper**（line 5974-5983）实现正确：
- `root.exists()` 为 False 时返回空 tuple（目录不存在也视为无文件）。
- `root.rglob("*")` 递归查找所有文件，防止子目录中的 artifact 被遗漏。

## 4. 过窄/脆弱断言、测试污染、AGENTS.md 违规检查（PASS-WITH-NOTES）

### 4a. 断言过窄/脆弱性

**无严重问题。** 逐一检查：

1. **`test_projection_consumer_applies_event_and_writes_durable_vnext_snapshot`**：断言了 exact text values（如 `"用户关注收入增速和毛利率变化。"`），这是对 `_accepted_compact_payload` fixture 的直接验证，属于确定性回归断言，不脆弱。

2. **`test_run_input_memory_messages_include_context_compacted_projection`**：
   - `any("summary=episode navigation only" in content for content in contents)` 使用了 `any()` + substring 模式，如果渲染格式从 `summary=` 变为 `summary_text=` 会失败。但这正是回归测试的目的 — 验证渲染格式的稳定性。**不视为脆弱。**
   - `"## Conversation Summary" in system_content` 等 section header 断言基于 `run_input.py` 中 `_SYSTEM_ENVELOPE_HEADER_PREFIX = "## "` + section name 的固定格式，合理。

3. **`test_projection_consumer_skips_failed_compact_without_memory_snapshot`**：断言 `result.events_scanned == 1` 的具体数值依赖于 EventLog 中恰好只有一条事件。若后续有人在 fixture 中增加 setup 事件，此断言会失败。但这是 **正确的失败** — 它迫使修改者理解 ProjectionRunner 行为变化。**不视为脆弱。**

4. **`test_pre_start_governance_compact_failure_is_attempt_free`**：`_compact_artifact_files(compact_artifact_root) == ()` 只有在 scheduler 确实使用传入的 `compact_artifact_root` 时才有效。验证通过 `_open_scheduler` line 5126 确认该参数被传入 `HostLocalExecutionOptions.compact_artifact_root`，链路正确。

### 4b. 测试污染

**无问题。** 所有测试：
- 使用 `tmp_path` pytest fixture（进程隔离临时目录）。
- Durable store 通过 `open_host_durable_store(_options(tmp_path))` 上下文管理器创建/销毁。
- 异步测试使用 `try/finally: await scheduler.close()` 确保资源释放。
- 无全局可变状态、无 module-level shared fixture、无 monkeypatch 副作用。

### 4c. AGENTS.md 遵守情况

**通过。** 改动文件遵守：
- 完整中文 docstring（所有新增函数和修改的 docstring 均为中文）。
- 类型标注完整（`_memory_item_count` 标注为 `int`，`_compact_artifact_files` 标注为 `tuple[Path, ...]`）。
- 无 `Any`、无 `object`、无魔法字符串（测试中使用的 section header 字符串是从生产代码中引用的业务可读常量）。
- 无嵌套函数/类（`_memory_item_count` 和 `_compact_artifact_files` 均为模块级私有函数）。

### 4d. NOTES（低优先级观察）

1. **`test_run_input_memory_messages_include_context_compacted_projection` 的 per-message 与 system_content 断言存在部分语义重叠**：
   - `"claim_text=Revenue increased year over year" in system_content`（line 1456）与 `any("summary=episode navigation only" in content ...)`（line 1454）检查了不同粒度的内容，但 `system_content` 已包含所有 section 的完整渲染，per-message 断言提供了额外但非必需的覆盖。这增加了测试维护成本但**不是缺陷**。

2. **`_memory_item_count` helper 使用了 f-string SQL**：
   ```python
   f"SELECT COUNT(*) AS count FROM {TABLE_HOST_MEMORY_ITEMS}"
   ```
   `TABLE_HOST_MEMORY_ITEMS` 是编译期常量，不是用户输入，因此不存在 SQL 注入风险。但与该文件其他 SQL 查询风格（多行字符串 + 参数绑定）不一致。**低风险，建议后续统一风格但非阻塞。**

3. **`_compact_artifact_files` helper 仅被 1 个测试使用**：当前仅有 `test_pre_start_governance_compact_failure_is_attempt_free` 使用该 helper。其他 compact 测试（如 line 3735, 3820 等也传了 `compact_artifact_root`）未做相同断言。这些测试是正向 compact 测试（应生成 artifact），与负向测试的断言目标不同，因此不需要统一。但若后续有人新增 compact failure 测试，应复用此 helper。**不阻塞。**

## 5. S3-R1 未覆盖评估（ACCEPTABLE）

### S3-R1 定义

Slice 3 plan 中 S3-R1 为：**dispatch 前 required cursor 已覆盖时继续构造 RunInput**（即 projection checkpoint 已 ≥ required cursor，无需 catch-up 即可 build RunInput 的 happy path）。

### 当前覆盖状态

- `test_run_input_memory_messages_include_context_compacted_projection` 调用 `catch_up_conversation_memory_projection` 显式追平 projection 到 required cursor，然后 build RunInput。这覆盖了 "catch-up + build" 路径。
- **未覆盖** "cursor already covered, skip catch-up, directly build" 路径。
- 覆盖该路径需要 dispatch-level fixture：构造一个 projection checkpoint 已超前于 required cursor 的场景，然后验证 scheduler 跳过 catch-up 直接调用 RunInputBuilder。这超出了 Slice 4 的测试边界（Slip 4 只允许修改 test_memory_projection.py、test_run_input_builder.py 和 test_dispatch_scheduler.py 的已有测试入口）。

### 可接受理由

1. **S3-R1 是 dispatch integration gap**，不是 memory projection 或 RunInputBuilder 的单元回归缺口。需要 dispatch scheduler 级 fixture，不能在不修改 scheduler test 基础设施的情况下自然新增。
2. **catch-up + build 路径（已覆盖）与 skip-catch-up + build 路径共享同一个 `RunInputBuilder.build`**，build 行为本身不因是否执行 catch-up 而改变。
3. **Implementation artifact 明确记录了该 residual risk**：`"仍保留给后续 Host dispatch test hardening"`，有 owner 有后续路径。
4. **如果 catch-up 逻辑本身有 bug**（例如 cursor 比较错误导致已经追平还重复 catch-up），这属于 Slice 3 的覆盖缺口，不在 Slice 4 的 regression scope。

**建议**：在后续 Host dispatch test hardening 中补充一个聚焦的 test case，不要求在本 Slice 解决。

## 验证结果

### 测试运行

| 命令 | 结果 |
|------|------|
| `pytest tests/host/test_memory_projection.py tests/host/test_run_input_builder.py::test_run_input_memory_messages_include_context_compacted_projection tests/host/test_dispatch_scheduler.py::test_pre_start_governance_compact_failure_is_attempt_free -v` | 18 passed |
| `pytest tests/host/test_run_input_builder.py -v` | 45 passed |
| `pytest tests/host/test_memory_projection.py -v` | 16 passed |
| `pytest tests/host/test_dispatch_scheduler.py -k "compact_failure_is_attempt_free or compact or governance" -v` | 16 passed, 51 deselected |

### Pyright

```
0 errors, 0 warnings, 0 informations
```

### 预存失败排除

`test_reactive_compact_failure_fallback_dispatch_uses_failed_view` 在首次运行中因 lane timeout (0.01s) 出现 flaky 失败，经 `git stash` 对比验证在 base commit 上也会偶发。该测试不在 Slice 4 修改范围，属于既有 flaky test。

## README 决策

已阅读 `tests/README.md`。本 Slice 只在既有测试文件中扩展回归断言，无新增测试层级、运行方式或维护约定，不触发 README 更新。

未修改 `dayu/host/` 生产代码，不触发 `dayu/host/README.md` 更新。

## 残余风险

1. **S3-R1**：dispatch before-worker catch-up happy path（cursor already covered）未覆盖，仍为 deferred-with-owner。
2. **Flaky test**：`test_reactive_compact_failure_fallback_dispatch_uses_failed_view` 存在 lane timeout 相关 flaky，与 Slice 4 无关，需单独 tracking。
3. **`_compact_artifact_files` 仅被 1 个测试使用**：其他 compact failure 测试未做 artifact 目录断言，但它们的语义目标不同（正向 compact），不视为缺口。

## 审查校验清单

- [x] 测试覆盖 accepted compact → ProjectionRunner → 五类 memory section + checkpoint
- [x] 测试覆盖 ordinary RunInput 读取五类 business section
- [x] 测试覆盖 failed compact 不物化 memory snapshot/items
- [x] 测试覆盖 failed compact 不生成 compact artifact
- [x] 无过窄/脆弱断言
- [x] 无测试污染
- [x] 遵守 AGENTS.md（中文 docstring、类型标注、无魔法字符串/数字）
- [x] Pyright 0 errors
- [x] 受影响的测试全部通过
- [x] 生产代码未修改（符合 Slice 4 scope）
- [x] S3-R1 未覆盖已评估并记录
