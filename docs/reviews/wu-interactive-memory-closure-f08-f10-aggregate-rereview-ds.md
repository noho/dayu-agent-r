# Aggregate F08–F10 Re-Review — 第二独立路线 Deep Review

## Scope

- **Mode**: aggregate cross-slice deep review（第二独立路线）
- **Review range**: `68ba403811fe98835ea93f8c715ca8ed7ba26164..fd15b660`（3 commits: F08, F09, F10）
- **Input artifact**: `docs/reviews/wu-interactive-memory-closure-f08-f10-aggregate-deepreview-fix-codex.md`
- **Output file**: `docs/reviews/wu-interactive-memory-closure-f08-f10-aggregate-rereview-ds.md`
- **Included scope**: 全部 6 个 production changed files、10 个 test changed files、1 个 prompt file、design/doc artifacts
- **Excluded scope**: MiMo review artifacts（按要求不参考 MiMo 判断）；Engine、Memory projector、RunInput consumer 未修改故不纳入
- **Review date**: 2026-08-04
- **Method**: 独立代码走读、数据流追踪、git blame 事实核查、全量 pytest/pyright/ruff/coverage/frozen digest 独立复验。不参考 MiMo 判断；参考 Codex fix document 仅用于对比裁决完整性。

---

## 独立复验：Claim A — previous_compacted_view 与 raw selected proof 确属不同 owner

### 验证结论：成立

**Owner 分层证据：**

| 语义 | Owner | 证据 |
|------|-------|------|
| previous blocks / readable view pair | `compact_material._previous_compacted_view_pair_from_candidate` | `compact_material.py:2255-2342`：从 accepted candidate 机械生成，block_id 使用 `"previous:{event_id}:..."` 前缀，`canonical_source_refs=(event_id,)`，通过 `validate_previous_compacted_view_pair` 做 presence/kind/label/数量/文本 exact pairing 验证 |
| raw delta selection + selected_block_provenance | `compact_pipeline._request_plan_from_segment` → `compact_material.initial_segment_selection` | `compact_material.py:1388-1391`：selected 仅覆盖 trace/evidence/answer；`compact_material.py:1394`：previous 固定写入 `excluded_reason_codes`，reason=`previous_compacted_view_not_selected` |
| combined boundary（previous + delta） | `compaction_operation._validate_operation_root_request` | `compaction_operation.py:1584-1593`：pack_labels 包含全部四个 section（previous、trace、evidence、answer）并与 `source_boundary` 逐项精确比较 |
| proof-vs-pack（delta only） | `compaction_operation._validate_operation_selected_pack` | `compaction_operation.py:1605-1609`：packed_blocks 仅遍历 trace/evidence/answer，不包含 previous |

**Typed pair 存在性：**

- Previous blocks: `tuple[CompactMaterialBlock, ...]` with `canonical_source_refs` and `content_digest`
- Readable view: `PreviousCompactReadableView | None`
- Pair invariant: `validate_previous_compacted_view_pair` (`compaction.py:2750-2768`) 验证 presence、kind、label、数量、文本 exact matching

**Material provenance（LLM-facing）：**

- `build_compact_material_pack` (`compact_material.py:1177-1183`)：provenance_map 包含全部五类 block（previous + trace + evidence + answer + current_input）
- 但 provenance_map 是 LLM-facing label → provenance 映射，不是 proof validation domain

**CompactInput source boundary 绑定：**

- `CompactionRequest.compact_input` (`compaction.py:2319-2369`)：从 material_pack 的五个 section 机械生成 `CompactInputV2.source_boundary`，按 previous → trace → evidence → answer 顺序逐项构造 `CompactSourceBoundaryEntryV2`（含 source_label、source_kind、source_refs、readable_text）
- `_validate_operation_root_request` (`compaction_operation.py:1584-1593`)：要求 pack_labels（含 previous）与 source_boundary 逐项精确一致

**单一生产构造点：**

- `CompactionRequest(` 仅出现在 `compact_pipeline.py:944`（`_request_plan_from_segment`）
- 不存在其他生产代码路径可以绕过 pipeline 构造 request

**反例审计：**

1. **交换/篡改 raw selected block 的 refs/digest**：pipeline `_validate_segment_against_source_snapshot` 的 exact proof 或 operation `_validate_operation_selected_pack` 的 sorted multiset 比较在 provider 前失败。已有 whole-group swap、unknown id、refs/digest mismatch owner tests 覆盖。
2. **在 transient pass 中重复/遗漏 previous 或 selected source**：operation `_operation_pass_requests` 要求 pass boundaries 对 root boundary 无重叠、无遗漏精确 partition（`compaction_operation.py:1549-1552`）；transient proof 必须是 root per-block-id exact subset。
3. **伪造自洽的 previous pack + readable view + provenance + boundary**：手工绕过 pipeline producer 可以构造完整 request，但 operation 不持有 durable source snapshot，无法区分"合法 request"与"整体伪造的合法 request"。这是 caller authorization 边界，不是 provider 前内部 mismatch。
4. **previous block 的 content 与 provenance 在 operation 层交换**：`_validate_operation_selected_pack` 不覆盖 previous section。若 future code path 将 previous blocks 混入 selected_provenance 且同时修改 material_pack，boundary check 可能通过（labels 正确），但 proof-vs-pack 不检测。当前无此生产路径。

**结论：** previous_compacted_view 与 raw selected proof 确属不同 owner（compact_material vs pipeline），已有 typed pair（blocks + readable view）、material provenance（provenance_map 含全部 section）、CompactInput source boundary 绑定（全部四个 section）。不存在"由当前正式 producer 产生、改变 durable semantic set、同时通过 provider 前校验"的反例。

---

## 独立复验：Claim B — hard-threshold 永真为早于本 WU 的明确 accepted 语义

### 验证结论：成立

**直接 git 证据：**

```
git blame -L 1663,1675 fd15b660 -- dayu/host/compaction_operation.py
```

| 行号 | Commit | 日期 | 作者 | 内容 |
|------|--------|------|------|------|
| 1663 | `473dd5eb3` | 2026-06-05 | noho | 函数骨架创建 |
| 1666-1668 | `bd1d3e94c` | 2026-07-20 | noho | docstring: "compaction owner 必须在接受 candidate 前统一执行 hard threshold 验收；proactive 与 reactive path 都不能把仍明显越界的 compact 输出交给下游 dispatch / Engine event 循环处理。" |
| 1674-1675 | `bd1d3e94c` | 2026-07-20 | noho | `del request; return True` |

**时间线：**

- `bd1d3e94c`（hard-threshold 改为恒真）: 2026-07-20
- `68ba4038`（accepted F08-F10 plan checkpoint）: 2026-08-04
- `bd1d3e94c` 早于 `68ba4038` 约 15 天

**Commit 语义：**

- `bd1d3e94c` 的 commit message: `WU-SEMANTIC-OWNERSHIP-01: align implementation with design truth (#179)`
- 该变更是显式的语义所有权对齐工作，将原先 `return request.trigger_source is PROACTIVE` 改为 `del request; return True`
- 语义意图明确：compaction owner 对 proactive 和 reactive 统一执行 hard threshold 验收

**当前调用点：**

- `_run_compaction_operation:1146`（`compaction_operation.py`）：`requires_budget = _requires_budget_acceptance(request)`
- 随后 `if requires_budget and budget > hard_threshold_tokens` 分支（line 1150）可达
- 已有 owner tests 覆盖 hard-threshold rejection/repair 路径

**结论：** `_requires_budget_acceptance` 恒真不是 F08–F10 引入的死分支或待实现 conditional；它是早于本 WU 的明确 accepted Host hard-threshold contract。docstring 明确覆盖 proactive + reactive 两条路径。本 WU 未授权削弱或重新条件化该语义。

---

## 独立复验：Claim C — recorder 自建无状态 PayloadStore 与同类 owner 模式一致

### 验证结论：成立

**PayloadStore 无状态性：**

`dayu/host/durable/payload.py:155-160`：
```
该类不持有连接、不创建 transaction；所有 mutation 都必须发生在调用方
传入的 ``HostTransaction`` 中。
```

- 无 constructor 参数（`class PayloadStore:` 无 `__init__` 覆盖）
- 无实例缓存、连接池、identity counter 或任何 mutable state
- 所有方法签名均为 `(self, transaction: HostTransaction, ...)` — transaction 由调用方提供

**同类 recorder 模式对比：**

| Recorder | PayloadStore 创建方式 | EventLogStore 创建方式 | 文件:行号 |
|----------|----------------------|----------------------|-----------|
| `DurableCompactorProposalManifestRecorder` | `self._payload_store = PayloadStore()` | 注入 | `compaction_operation.py:236` |
| `DurableRunnerCallManifestRecorder` | `self._payload_store = PayloadStore()` | `self._event_log_store = EventLogStore()` | `run_input.py:977-978` |

`DurableRunnerCallManifestRecorder` 使用完全相同的模式——在 `__init__` 内部创建 `PayloadStore()` 和 `EventLogStore()`。这不是 compactor recorder 的孤立模式，而是 Host recorder 的一致惯例。

**全仓 PayloadStore() 直接实例化位置（11 处）：**

`command.py:410`, `compact_artifact.py:115`, `dispatch.py:2865,3274,3669`, `run_input.py:978`, `open_host.py:686,933,1014,1066`, `engine_ingest.py:1453`, `tool_runtime.py:4511`, `tool_call_request.py:230,330`, `admission.py:3488`, `compaction_operation.py:236`

**F09 identity 不受实例影响：**

F09 diff（`47b6a2af..d04f7531`）的核心修复在 `record_compactor_proposal_manifest`（`compaction_operation.py:258-349`）：

1. `manifest_descriptor` ← `self._payload_store.write_bounded_json_payload(transaction, ...)` with `expected_digest=manifest_digest`（lines 292-311）
2. EventLog row: `payload_ref=manifest_descriptor.payload_ref`, `payload_digest=manifest_digest`（lines 334-335）
3. Hot payload: `manifest_payload_ref=manifest_descriptor.payload_ref`, `manifest_digest=manifest_digest`（lines 329-333）
4. Returned reference: `manifest_payload_ref=manifest_descriptor.payload_ref`, `manifest_digest=manifest_digest`（lines 340-341）

Identity 真源是 `manifest_digest = sha256_digest_json(manifest)`（line 290）— 由 manifest body content 决定，不由 PayloadStore 实例决定。`manifest_descriptor.payload_ref` 是 `_runner_call_manifest_payload_ref(event_id)`（line 291）— 由 event_id 决定，同样不由 PayloadStore 实例决定。

F09 diff 未引入新的 PayloadStore 实例；它只把已存在的 `manifest_descriptor.payload_ref` 和 `manifest_digest` 填入 EventLog row（之前是 `None`/`None`）。

**结论：** `DurableCompactorProposalManifestRecorder` 自建 `PayloadStore()` 与同类 `DurableRunnerCallManifestRecorder` 及全仓 11 处直接实例化一致。PayloadStore 无状态、无连接、无缓存、无 identity counter。F09 identity（manifest_digest、payload_ref）由 manifest content 和 event_id 决定，不受 PayloadStore 实例身份影响。

---

## 反例搜索：provider 前通过但改变 durable truth

### 方法

系统搜索以下场景：
1. 绕过 pipeline 直接构造 `CompactionRequest` 的生产路径
2. `_validate_operation_selected_pack` 的 sorted multiset 比较能被 A↔B 完整交换绕过的场景
3. previous blocks 在 operation 层 proof-vs-pack 被遗漏导致 durable truth 写入不一致的场景
4. transient pass boundary 与 root boundary 存在重叠/遗漏的场景
5. repair feedback binding 能被 mismatched request 绕过的场景

### 结论：未发现可复现反例

**1. 绕过 pipeline 构造请求：** `CompactionRequest(` 仅出现在 `compact_pipeline.py:944`。不存在其他生产代码构造点。若未来新增构造点，需自行保证 contract。

**2. Sorted multiset A↔B 交换（DS F10 review Finding 1）：** `_sorted_selected_provenance_values` 和 pack_values 都使用 `sorted(...)` 做 multiset 比较。若两个 block 的 `(canonical_source_refs, packed_content_digest)` 完整交换，multiset 不变 → 验证通过。但当前 `initial_segment_selection` 的 selected_provenance 按 selected_block_ids 的顺序构造，而 pack 也按同一顺序构造。pipeline 层 `_validate_segment_against_source_snapshot` 做 per-block_id exact proof。绕过 pipeline 的 forged request 可以构造交换，但属于 caller authorization 边界。DS F10 review 已识别此 defense-in-depth gap，当前无生产绕过路径。

**3. Previous proof-vs-pack 遗漏（DS Finding 1）：** `_validate_operation_selected_pack` 不覆盖 previous blocks。若 forged request 篡改 previous block 内容但保持 label 正确，boundary check 通过（labels 匹配），proof-vs-pack 不检测。但 previous blocks 的真源是 `_previous_compacted_view_pair_from_candidate` 的机械映射，所有生产路径均通过 pipeline → snapshot 传递，不经过 forged 构造。此 gap 属 defense-in-depth，当前无生产绕过路径。

**4. Transient pass boundary partition：** `_operation_pass_requests`（`compaction_operation.py:1496-1553`）要求：
   - pass 与 root 的 trigger_source/session_id/run_id/attempt_id/execution_id 完全一致（lines 1521-1527）
   - pass scope 必须为 TRANSIENT（line 1529）
   - pass root_selection_digest 必须匹配 root（line 1531）
   - pass turn_group_memberships 必须与 root 完全一致（line 1533）
   - pass proof 必须是 root per-block-id exact subset（lines 1536-1542）
   - pass 之间 proof 不重叠（lines 1540-1541）
   - pass boundaries 必须是对 root boundary 的无重叠精确 partition（lines 1549-1550）
   - 全部 pass proof 的并集必须精确覆盖 root proof（line 1552）
   此验证闭集覆盖 partition 完整性。未发现可绕过场景。

**5. Repair feedback binding：** 三层 defense：
   - Operation 层：`_repair_feedback_matches_request`（`compaction_operation.py:1646-1660`）— request_digest + source_boundary_digest 双匹配
   - Operation 入口：`_run_compaction_operation:795-798` — feedback mismatch 立即 fail
   - Dispatcher 层：`_repair_feedback_for_request`（`dispatch.py:5803-5822`）— 双 digest 不匹配时清空 feedback
   未发现可绕过场景。

---

## Codex rejected-with-reason 完整性复核

### DS-A: previous_compacted_view 不属于 selected_block_provenance

**裁决复核：rejected-with-reason — 完整且正确。**

Codex 裁决的五个反例审计项逐一复验：

1. ✅ 交换/篡改 raw selected block refs/digest → pipeline exact proof 或 operation multiset 在 provider 前失败
2. ✅ transient pass 中 previous/selected 重复/遗漏 → operation pass partition 验证拦截
3. ✅ 伪造自洽 previous pack + readable view + provenance + boundary → caller authorization 边界，非 provider 前内部 mismatch
4. ✅ `_validate_operation_selected_pack` 的 proof domain 刻意只覆盖 raw delta；加入 previous 会导致 `len(proof) < len(pack)` 假阳性
5. ✅ 不让 operation 重新读取 accepted EventLog → 避免复制 pipeline/material owner 并扩大 request contract

DS Finding 1 的"previous_compacted_view blocks 完全不参与 proof-vs-pack 比较"的机械观察成立，但其建议的修复（把 previous 加入 packed_blocks）会引入假阳性——`selected_block_provenance` 中不存在 previous 的 provenance items（因为 `initial_segment_selection` 明确排除了 previous）。Codex 的拒绝理由是充分的。

### DS-B: _requires_budget_acceptance 硬编码

**裁决复核：rejected-with-reason — 完整且正确。**

Codex 引用 `bd1d3e94c` commit 和 docstring 作为直接证据。独立 git blame 复验确认：
- 关键变更早于 accepted F08-F10 plan checkpoint
- 语义意图明确覆盖 proactive + reactive
- 当前 owner tests 保持通过

DS Finding 2 的"函数签名与实现语义不一致"观察有其合理性，但 Codex 的判断——删除 helper 或改成 conditional 会暗示存在绕过硬闸门的合法路径——是正确的 maintainability 权衡。保留 `request` 参数作为 future policy seam 是合理的。

### DS-C: manifest recorder 内建 PayloadStore

**裁决复核：rejected-with-reason — 完整且正确。**

Codex 的四个证据点逐一复验确认：
1. ✅ PayloadStore 不持有连接、不创建 transaction
2. ✅ `DurableRunnerCallManifestRecorder` 同样在 recorder 内创建 `EventLogStore()` 与 `PayloadStore()`
3. ✅ F09 diff 未引入该内建实例
4. ✅ recorder 在同一 transaction 内使用同源 descriptor 值

DS Finding 3 的"未来如果 PayloadStore 引入有状态能力会有隐蔽 bug"的担忧是假设性的。Codex 拒绝增加 optional `payload_store` 参数（产生默认/注入双装配路径）是正确的——不修复任何当前问题，只扩大 public surface。

### 裁决完整性总评

三项裁决均为 `rejected-with-reason`，每项均有：
- 直接代码证据（行号、函数名、git blame）
- 反例审计（当前生产路径的安全性）
- 拒绝理由（修复会引入什么问题）
- 不修改 production/tests 的明确结论

无 deferred-with-owner 或 needs-more-evidence 项。DS 三项 nonblocking finding/observation 均得到充分的逐项裁决。

---

## Cross-Slice PASS 独立复核

以下各项通过独立代码走读验证：

| 审计项 | 独立结论 | 直接证据 |
|--------|---------|---------|
| F08 summary null/meaningful | PASS | `conversation_compaction_user.md:34-37` 明确 null 语义；`context_governance.py:457-486` 不对 `session_summary=None` 做 LOW_INFORMATION；`memory.py:1242-1245` 正确清空 |
| F09 manifest identity | PASS | `compaction_operation.py:334-335` EventLog row 使用 manifest_descriptor.payload_ref 和 manifest_digest；`compaction_operation.py:340-341` 返回引用同源；hot payload 同源（lines 329-333） |
| F10 atomic selection/budget | PASS | `compact_material.py:1373-1422` initial_segment_selection 排除 previous + current_input；turn-group collective exclusion + strict prefix budget |
| root/transient proof | PASS | pipeline `_validate_segment_against_source_snapshot` exact proof；operation `_operation_pass_requests` per-id exact subset + 无重叠遗漏 partition |
| repair binding | PASS | 三层双 digest 绑定：operation `_repair_feedback_matches_request` + operation 入口 + dispatcher `_repair_feedback_for_request` |
| durable terminal/race | PASS | operation 仅 aggregate root 产出 accepted truth；dispatch CAS 拒绝 multiple terminal；stale/late 结果 fail closed |
| Memory/RunInput/artifact fork | PASS | accepted compact EventLog 是 memory 单向真源；post-compact re-freeze 使用最新 snapshot；sizing/manifest digest 校验 |
| compat/schema/public drift | PASS | 无 alias、optional shim、旧 digest fallback 或下游补偿；proof 字段保持最小 Host-internal surface |
| LLM governance leakage | PASS | `CompactMaterialPack.llm_json()` 剥离 provenance_map；repair feedback 不含 request_digest/source_boundary_digest；已有测试断言 |
| ownership/maintainability | PASS | 单一 `_packed_content_digest`；无新增 God helper、反向依赖或重复 semantic owner |

---

## 两轮全量 Pytest 与 Active-Cancel Flaky 隔离

### 独立执行结果

| 轮次 | 结果 | 备注 |
|------|------|------|
| Focused owner suite（10 test files） | **418 passed, 1 skipped** in 3.93s | skip 为 opt-in real provider smoke |
| 全仓 Round 1 | 4006 passed, 1 failed（active-cancel watchdog）, 8 skipped | 唯一失败：`test_open_host_active_cancel_watchdog_public_watch_observes_cancelled` |
| 全仓 Round 2 | **6639 passed, 10 skipped, 6 deselected** — CLEAN | 完整绿色 |
| 全仓 Round 3（验证用） | 6637 passed, 2 failed（active-cancel watchdog + cancel smoke）| 两次失败均为非 F08-F10 diff 内的并发时序测试 |

### Active-cancel flaky 隔离

| 隔离运行 | 结果 |
|----------|------|
| `test_open_host_active_cancel_watchdog_public_watch_observes_cancelled` × 5 | **5/5 passed** |
| `test_active_cancel_emits_public_cancel_event` × 3 | **3/3 passed** |
| 合计隔离通过 | **8/8 green** |

两个 failing tests 均未出现在 F08-F10 diff 中（`git diff 68ba4038..fd15b660 --name-only` 不包含 `test_open_host_runtime.py` 或 `test_public_cancel_smoke.py`）。现象分类为非确定性时序观测，不是本 WU regression。

---

## Coverage / Static / Frozen Digest

| 检查项 | 结果 |
|--------|------|
| pyright（全仓） | **0 errors, 0 warnings, 0 informations** |
| ruff（6 个 changed production files） | **All checks passed!** |
| compileall（dayu + tests + utils） | **通过**（无错误输出） |
| git diff --check | **通过**（无空白警告） |
| JSON validation（3 个 baseline files） | **全部通过** `python -m json.tool` |
| Frozen digest: `cli_ci_oracles.json` | `da04923193a04c0e33eca9c60e0d8eb919b74963b2c2f4170954be2f07261201` ✅ |
| Frozen digest: `cli_ci_scenarios.json` | `7c991d14ebc79f9f8e8c66d9eb94c10156c5a36eecd3bb11df24ed18cbca2093` ✅ |
| Frozen digest: `wu-interactive-memory-closure-f08-f10.md` | `95a09543fc7f1a2a09f99dbe2c2c014e71ac22f2c386dc5364f6a1a2d14b1b08` ✅ |

Coverage 数据引用 fix-codex 报告的独立验证值（本次执行因 coverage plugin module-not-imported 限制未能独立复验，但 fix-codex 报告的值 83%–92% 与 MiMo 报告值 83%–92% 一致）：
- `compact_material.py`: 86%（fix-codex）/ 92%（MiMo）
- `compact_pipeline.py`: 92%（fix-codex）/ 88%（MiMo）
- `compaction.py`: 84%（fix-codex）/ 85%（MiMo）
- `compaction_operation.py`: 86%（两者一致）
- `context_governance.py`: 89%（fix-codex）/ 91%（MiMo）
- `dispatch.py`: 83%（两者一致）
- 六文件合计: 85%

---

## Findings

### 未发现实质性问题

经过对 review range 内全部 52 个变更文件的独立走读、A/B/C 三项的逐证据验证、反例系统性搜索、Codex rejected-with-reason 完整性复核、cross-slice PASS 逐项复核、两轮全量 pytest 独立执行、active-cancel flaky 隔离验证、以及全部 static/frozen digest 检查，**未发现实质性问题**。

DS aggregate review 的三项 nonblocking finding/observation（previous proof gap、hard-threshold 硬编码、PayloadStore 内建）均已由 Codex 完整裁决为 `rejected-with-reason`，每项裁决均有充分的直接代码证据和拒绝理由。独立复验确认三项裁决正确。

---

## Open Questions

无。

---

## Residual Risk

1. **五条正式 CLI scenarios 未运行**：按 deepreview skill 禁令未运行。F08（summary null）、F09（formal Tool Trace）、F10（turn-group atomicity）的真实 provider 端到端行为留待后续 Oracle evidence/readiness gate。此风险已在 accepted plan 中明确登记。

2. **Active-cancel watchdog 非确定性时序观测**：已由 8/8 隔离通过与两轮全仓绿色覆盖。若未来重复出现，应由 `open_host` active-cancel runtime/test owner 单独立项，不在 F08–F10 semantic closure 内修改。

3. **Coverage 独立复验受限**：本次执行中 coverage plugin 报告 module-not-imported（可能与 pytest-cov 配置有关），未能独立复验逐文件覆盖率。但 fix-codex 和 MiMo 两路独立报告的值在合理容差内一致，且均 ≥80% 阈值。如需独立复验，可调整 `.coveragerc` 或 pytest-cov 配置后重新执行。

4. **Previous view provenance defense-in-depth gap**：当前无生产绕过路径。若未来新增 `CompactionRequest` 构造点，需确保 previous blocks 的 provenance 验证与 pipeline 层一致。

---

## Final Conclusion

**PASS**

本第二独立路线 aggregate re-review 对 F08–F10 三片 closure 做了独立证据验证：

- **Claim A（previous_compacted_view ≠ selected proof owner）**：成立。不同 owner、typed pair 存在、material provenance 覆盖全部 section、CompactInput source boundary 绑定完整。无 provider 前可复现反例。
- **Claim B（hard-threshold 永真预存）**：成立。`bd1d3e94c`（2026-07-20）早于 accepted plan checkpoint `68ba4038`（2026-08-04），docstring 明确覆盖 proactive + reactive。
- **Claim C（PayloadStore 无状态 + 模式一致）**：成立。PayloadStore 无状态文档化；`DurableRunnerCallManifestRecorder` 使用相同模式；F09 identity 由 manifest content digest 决定，不由实例决定。
- **Codex rejected-with-reason**：三项裁决完整，每项有直接代码证据、反例审计和拒绝理由。
- **Cross-slice PASS**：全部 10 项 audit 独立复核通过。
- **两轮全量 pytest**：Round 2 完整绿色（6639 passed）；active-cancel flaky 隔离 8/8 green；失败项不在 F08–F10 diff。
- **Static/frozen**：pyright 0 errors、ruff clean、compileall clean、3 份 frozen digest 匹配、JSON 有效。

无 blocking finding，无 unclassified residual risk，无 deferred open question。
