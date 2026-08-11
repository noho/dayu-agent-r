# AgentMiMo Plan Review — WU-CLI-DOWNLOAD-01 Slice 4 Amendment v2

## 1. Review metadata

- Reviewer: AgentMiMo
- Review type: adversarial plan review (v2 amendment)
- Target: `docs/gateflow/wu-cli-download-01-slice4-plan-amendment-v2-20260810-072924.md`
- Base plan: `docs/gateflow/wu-cli-download-01-plan-20260809.md` §5.6 / Slice 4 / §9
- Amendment v1: `docs/gateflow/wu-cli-download-01-slice4-plan-amendment-20260810-060259.md`（已 PASS）
- Stop evidence: `docs/gateflow/wu-cli-download-01-slice4-stop-evidence-20260810-071524.md`
- v1 re-review: `docs/reviews/plan-review-20260810-slice4-amendment-mimo-rereview.md`
- Code evidence HEAD: `93eb073e597899b3c25234eaf50923ba1d6c0219`
- Date: 2026-08-10

## 2. Review scope

按用户指令 adversarial 检查以下 11 项：

1. 完整 mutation inventory 是否漏项
2. v2 三个 allowlist 增量是否最小充分
3. SC13 typed decisions 是否 god bag / 把 persistence facts 上移
4. artifact+registry durable unit 是否 owner 正确且非 operation-wide transaction
5. whole-tree inventory 单 guard 是否可实现
6. exactly-one selected repair-first 是否在任何 company/rejected/maintenance batch 前
7. multiple/unselected/material/no-filing/selected-rejected 是否真能首 mutation 前 typed fail closed
8. 6-K 在 remote policy 判定后如何保持 old facts
9. cancel/failure 与已提交独立 batch 边界
10. 测试/barrier/static/coverage 是否 code-generation-ready
11. v1 PASS 的结论是否仍有效

## 3. Stop evidence 直接代码验证

### 3.1 SEC company batch 位置

stop evidence 声明 `sec_download_workflow.py:457-469` 在 filing selection 前提交 company batch。

**代码验证**：
- `sec_download_workflow.py:457` — `company_batch = host._batching_repository.begin_batch(normalized_ticker)`
- `sec_download_workflow.py:459-465` — `_upsert_company_meta(..., batch=company_batch)`
- `sec_download_workflow.py:469` — `host._batching_repository.commit_batch(company_batch)`
- `sec_download_workflow.py:473` — `filings, filenums = await host._filter_filings(...)` 在 company commit 之后

**结论**：直接证据准确。Company batch 在 filing selection/filing Phase A 前完成。

### 3.2 SC13 hidden mutation

stop evidence 声明 `sec_sc13_filtering.py:454-494` 在 selection 内提交 rejected artifact。

**代码验证**：
- `sec_sc13_filtering.py:454` — `if not keep and rejection_registry is not None:`
- `sec_sc13_filtering.py:457-468` — `remote_files = await _maybe_await(host._downloader.list_filing_files(...))`（HTTP 调用）
- `sec_sc13_filtering.py:481-494` — `artifact_saved, artifact_error = await _maybe_await(host._persist_rejected_filing_artifact(...))`
- `sec_sc13_filtering.py:503-511` — `_record_rejection_impl(registry=rejection_registry, ...)`（内存 registry 写入）

`_persist_rejected_filing_artifact` 内部（`sec_download_persistence.py:255-321`）执行 `begin_batch` → `store_file` → `upsert_rejected_filing_artifact` → `commit_batch`。

**结论**：直接证据准确。SC13 selection 在完整 preflight 前产生 ticker batch mutation。

### 3.3 CN company batch 位置

stop evidence 声明 `cn_download_workflow.py:193-205` 存在同构顺序。

**代码验证**：
- `cn_download_workflow.py:193` — `company_batch = host.batching_repository.begin_batch(normalized_ticker)`
- `cn_download_workflow.py:195-201` — `upsert_company_meta_for_cn_download(..., batch=company_batch)`
- `cn_download_workflow.py:205` — `host.batching_repository.commit_batch(company_batch)`

**结论**：直接证据准确。CN 在 single-filing Phase A 前提交 company batch。

### 3.4 Validator 行为

stop evidence 声明 `_validate_complete_source_tree` 在每次 commit 前校验完整 source tree。

**代码验证**：
- `_fs_storage_infra.py:594` — `self._validate_complete_source_tree(state)` 在 publication guard 获取前
- `_fs_storage_infra.py:709-710` — `for source_kind in (SourceKind.FILING, SourceKind.MATERIAL): self._validate_complete_source_kind_tree(state, source_kind)`

**结论**：直接证据准确。Validator 遍历 filing + material 两棵完整 source tree。

### 3.5 SEC 无条件尾部 maintenance batch

stop evidence 声明 `sec_download_workflow.py:601-612` 存在无条件尾部 registry batch。

**代码验证**：
- `sec_download_workflow.py:601` — `maintenance_batch = host._batching_repository.begin_batch(normalized_ticker)`
- `sec_download_workflow.py:603-608` — `save_rejection_registry(..., batch=maintenance_batch)`
- `sec_download_workflow.py:612` — `host._batching_repository.commit_batch(maintenance_batch)`

此代码在 filing loop 结束后、`break` 后仍到达。即使 registry 未变也提交 batch。

**结论**：直接证据准确。无条件尾部 batch 在 registry 未变时仍触发完整 validator。

## 4. 逐项 adversarial 检查

### 4.1 完整 mutation inventory 是否漏项

**检查方法**：`rg` 搜索 `sec_download_workflow.py`、`cn_download_workflow.py`、`sec_sc13_filtering.py`、`sec_download_filing_workflow.py`、`cn_download_filing_workflow.py` 中所有 `begin_batch`、`_persist_rejected_filing_artifact`、`_record_rejection`、`save_rejection_registry` 调用。

**v2 §3 inventory 覆盖**：

| 实际 mutation | v2 inventory 行 | 验证 |
|---|---|---|
| `sec_download_workflow.py:457` company begin | SEC company resolve 后 | ✓ |
| `sec_sc13_filtering.py:481` rejected artifact | SC13 direction selection | ✓ |
| `sec_sc13_filtering.py:503` registry write | SC13 direction selection | ✓ |
| `sec_download_filing_workflow.py:382` 6-K rejected artifact | selected 6-K Phase A | ✓ |
| `sec_download_filing_workflow.py:415` 6-K registry write | selected 6-K Phase A | ✓ |
| `sec_download_filing_workflow.py:445` source batch | accepted filing Phase B | ✓ |
| `sec_download_workflow.py:601` maintenance batch | pipeline 尾部 | ✓ |
| `cn_download_workflow.py:193` company begin | CN company resolve 后 | ✓ |
| `cn_download_filing_workflow.py:487` source batch | CN accepted filing Phase B | ✓ |
| `cn_download_filing_workflow.py:646` PDF digest reuse batch | CN PDF digest reuse | ✓ |

**未覆盖项检查**：
- `sec_download_workflow.py` 中 `_filter_filings` 的 `_extend_with_browse_edgar_sc13` 内部调用 `_persist_rejected_filing_artifact`（`sec_sc13_filtering.py:481`）。该路径已由 SC13 direction selection 行覆盖。✓
- `sec_download_workflow.py` 中 `_filter_filings` 的 `retry_sc13_if_empty` 内部调用 `_persist_rejected_filing_artifact`（同上）。同路径。✓
- `sec_download_filing_workflow.py:513` rollback batch — 这是 failure rollback，不是新 mutation。✓
- `cn_download_filing_workflow.py:713` rollback batch — 同上。✓

**裁决**：**无漏项**。Inventory 完整覆盖所有 ticker batch mutation 点。

### 4.2 v2 三个 allowlist 增量是否最小充分

**v2 增量**：
- `sec_download_workflow.py` — 需要移动 company batch 顺序、删除无条件尾部 maintenance batch
- `cn_download_workflow.py` — 需要移动 company batch 顺序
- `sec_sc13_filtering.py` — 需要把 batch mutation 延后到 repair gate 之后

**必要性论证**：
- `sec_download_workflow.py`：是 SEC company publication 与 filing dispatch 顺序的 owner。不修改它，company batch 仍在 repair 前。✓
- `cn_download_workflow.py`：是 CN company publication 与 filing dispatch 顺序的 owner。同理。✓
- `sec_sc13_filtering.py`：是 SC13 direction decision 与 rejected artifact/registry mutation 的 owner。不修改它，selection 内仍产生 hidden mutation。v2 §3.1 已证明这是最小充分新增项。✓

**不修改的文件检查**：
- `sec_download_state.py`：v2 §3 明确不修改，现有 `_record_rejection` / `_save_rejection_registry` 接口足够。✓
- `sec_pipeline.py` / `cn_pipeline.py`：只是 facade/composition owner，不拥有顺序。✓
- `sec_download_company_meta.py` / `cn_download_company_meta.py`：company meta 构造逻辑不变。✓

**裁决**：**最小充分**。三个增量各自对应一个必须修改的 mutation owner；无多余文件。

### 4.3 SC13 typed decisions 是否 god bag / 把 persistence facts 上移

**v2 §5.3 定义的 variants**：
- `Sc13DirectionAccepted`：只携带 accepted filing identity
- `Sc13DirectionRejectedWithArtifact`：携带 filing、archive CIK、remote descriptors、source fingerprint、selected primary、rejection reason/category
- `Sc13DirectionRejectedRegistryOnly`：只携带 registry entry 所需 facts 与 safe diagnostic
- `Sc13DirectionRejectedAlreadyRegistered`：纯 skip，属于最终 rejected ID 集合

**God bag 检查**：
- 每个 variant 的字段集合互斥，没有 optional 字段模拟不同状态。✓
- `Sc13DirectionRejectedWithArtifact` 的字段是构造 artifact + registry 所需的不可变 facts，不是 persistence 内部状态。✓
- v2 §5.3 明确："若一个 variant 需要互斥 optional 字段，必须继续拆 variant。" ✓

**Persistence facts 上移检查**：
- variant 不包含 `BatchToken`、`FileObjectMeta`、storage path 或 commit/rollback 语义。✓
- variant 只表达 "SC13 direction decision 的结果是什么"，不表达 "如何持久化"。✓
- persistence owner（`sec_download_persistence.py`）继续拥有 `build_rejected_store_file`、`upsert_rejected_filing_artifact`、commit/rollback。✓
- v2 §5.4 明确："artifact 成功时 artifact+对应 registry entry 不可分离；任一 store/meta/registry/validator/cancel 失败都 rollback。" 这是 persistence owner 的职责，不是 typed decision 的职责。✓

**裁决**：**不是 god bag，persistence facts 未上移**。Typed decisions 只表达 direction decision 的业务结果；persistence 语义留在 persistence owner。

### 4.4 artifact+registry durable unit 是否 owner 正确且非 operation-wide transaction

**v2 §5.4 定义的 durable unit**：

```text
caller 以既有 _record_rejection 在 registry 副本构造 registry_after
  -> persistence 完整 prefetch（无 batch）
  -> cancellation checkpoint
  -> begin_batch
  -> materialize rejected files + upsert rejected meta
  -> save registry_after（同一真实 batch）
  -> commit
  -> caller 才把 in-memory registry 替换为 registry_after
```

**Owner 检查**：
- `sec_download_persistence.py` 拥有 `begin_batch` → `store_file` → `upsert_rejected_filing_artifact` → `save registry` → `commit`。✓
- `sec_sc13_filtering.py` 只返回 typed decision，不执行 batch。✓
- 顶层 workflow 负责调用时序（repair gate 后才执行 rejection durable unit）。✓

**非 operation-wide transaction 检查**：
- v2 §5.4："这不是 operation-wide transaction：每个 filing source 与每条 rejection 仍是独立 atomic batch；batch 之间不跨 provider I/O 持锁。" ✓
- §7 矩阵："cancel 或普通 filing 失败发生在 company 已成功之后 → 不伪造 operation-wide rollback → company 是完整已提交新 fact；此前成功的独立 source/rejection batch 保留。" ✓

**SC13 registry-only 语义保留**：
- v2 §5.4："SC13 artifact listing/prefetch 失败沿用现有语义：以独立 registry-only batch 提交 typed rejection entry；不伪造 artifact。registry-only batch 也只能发生在 repair gate 之后。" ✓
- 当前代码 `sec_sc13_filtering.py:495-501` 在 artifact 失败时只 log warning，然后仍调用 `_record_rejection_impl`。v2 保持该语义但延后到 repair gate 后。✓

**裁决**：**Owner 正确，非 operation-wide transaction**。每条 rejection 是独立 atomic batch；artifact+registry 在同一 batch 内不可分离。

### 4.5 whole-tree inventory 单 guard 是否可实现

**v2 §5.1 定义的 `list_source_integrity`**：
- "wrapper/core 在一个短 publication guard 内枚举 filing + material 的全部 published source ID 并逐项调用同一 unguarded classification core；按 `(source_kind.value, document_id)` 排序返回。"
- "同一 guard 消除'先 list、后逐项 classify'跨 publication 混合视图。"

**代码证据**：
- `repository_protocols.py:682-697`：repository 已拥有 public source ID enumeration。✓
- `fs_source_document_repository.py:642-658`：wrapper 已实现 source ID 列表。✓
- `_fs_source_document_core.py:756-817`：core 已实现 source ID 枚举。✓
- v1 `classify_source_integrity` 已在同一个 `SourceDocumentRepositoryProtocol` 上定义。`list_source_integrity` 是同一 owner 的整树扩展。✓

**单 guard 可行性**：
- 现有 `_acquire_publication_guard` 是短持有、只读操作。✓
- 枚举 source ID + 逐项 classification 是纯 storage 读取，不涉及 provider I/O。✓
- 不需要新增 capability/Protocol/compat。✓

**裁决**：**可实现**。现有 repository 已有 source ID enumeration；单 guard 内枚举 + classification 是纯读取操作。

### 4.6 exactly-one selected repair-first 是否在任何 company/rejected/maintenance batch 前

**v2 §6.2 SEC 精确顺序**：

```text
1. resolve company、fetch submissions、加载 published registry；全部只读。
2. 完成 form/window selection。SC13 direction 只产生 typed decisions；不得产生 ticker batch。
3. 构造 accepted filing IDs 与 SC13 rejected IDs，调用 list_source_integrity 并执行 preflight。
4. 若 multiple/unselected/SC13-rejected corruption，立即抛 typed preflight error；company/artifact/registry/source batch 调用数均为 0。
5. 若有唯一 accepted repair target，stable-partition 到首位并只执行该 filing。
6. 再次 whole-ticker preflight；非 clean 即 typed fail closed。然后执行 cancel checkpoint。
7. 提交 company meta batch。
8. 按稳定顺序处理 deferred SC13 rejection intents；每条使用 durable unit。
```

**验证**：
- 步骤 1-3：全部只读，无 batch mutation。✓
- 步骤 4：fail closed，batch 调用数为 0。✓
- 步骤 5：repair target 在 company batch（步骤 7）和 rejection（步骤 8）之前。✓
- 步骤 6：post-repair preflight 在 company batch 前。✓
- 步骤 7：company batch 在 repair 成功 + post-repair clean 后。✓
- 步骤 8：rejection durable unit 在 company batch 后。✓

**裁决**：**正确**。Exactly-one selected repair-first 在任何 company/rejected/maintenance batch 前完成。

### 4.7 multiple/unselected/material/no-filing/selected-rejected 是否真能首 mutation 前 typed fail closed

**v2 §5.2 preflight disposition 优先级**：

1. storage 结构错误：inventory 构造时直接失败。
2. `REPAIR_REQUIRED` 数量 > 1：`MULTIPLE_REPAIR_REQUIRED`。
3. 恰好 1 个且为 material 或不在 accepted/rejected 集合：`UNSELECTED_REPAIR_REQUIRED`。
4. 恰好 1 个且在 rejected 集合：`SELECTED_REJECTED_REPAIR_REQUIRED`。
5. 恰好 1 个且是 accepted filing：返回 `SelectedSourceRepairRequired`。
6. 零个：返回 `NoSourceRepairRequired`。

**v2 §6.2 步骤 4**：
> 若 multiple/unselected/SC13-rejected corruption，立即抛 typed preflight error；company/artifact/registry/source batch 调用数均为 0。

**v2 §7 矩阵**：
| 场景 | 首个 ticker mutation 前裁决 | 结束后的 durable facts |
|---|---|---|
| multiple corruption | company/rejection/source batch 均 0 | 全部 old 精确保留 |
| unselected filing 或 material corruption | company/rejection/source batch 均 0 | 全部 old 精确保留 |
| designated 6-K Phase A 后 rejected | rejected persistence 前失败 | 损坏 source、company、artifact、registry 全部 old |
| no-filing、有 corruption | company 前 fail closed | 全部 old |

**代码验证**：§5.2 的 preflight 是纯函数，接收 inventory + accepted/rejected IDs，返回 disposition。不执行任何 batch。✓

**裁决**：**正确**。Preflight 在首 mutation 前执行；fail closed 场景 batch 调用数为 0。

### 4.8 6-K 在 remote policy 判定后如何保持 old facts

**v2 §6.2 步骤 5**：
> 该 target 为 6-K 且 Phase A 最终判为 rejected：在调用 rejected persistence 前抛 `SELECTED_REJECTED_REPAIR_REQUIRED`，不把损坏 source 重写成被 policy 拒绝的新 source，也不发布 rejection。

**v2 §7 矩阵**：
> designated 6-K Phase A 后 rejected → rejected persistence 前失败 → 损坏 source、company、artifact、registry 全部 old

**逻辑分析**：
- 6-K 在 Phase A 后被 policy 判定为 rejected（非 publication-eligible）。
- 如果该 6-K 是 designated repair target，v2 要求在 persistence 前抛 `SELECTED_REJECTED_REPAIR_REQUIRED`。
- 这意味着损坏 source 不会被重写为 "被 policy 拒绝的新 source"，也不会发布 rejection artifact/registry。
- 所有 old facts 精确保留。

**裁决**：**正确**。Selected-then-rejected 6-K 在 persistence 前 fail closed，old facts 保持。

### 4.9 cancel/failure 与已提交独立 batch 边界

**v2 §7 矩阵**：
> cancel 或普通 filing 失败发生在 company 已成功之后 → 不伪造 operation-wide rollback → company 是完整已提交新 fact；此前成功的独立 source/rejection batch 保留，当前 open batch 回滚，后续不执行。

**v2 §6.2 步骤 5-6**：
> repair-first 目标：provider/prefetch/Phase B/validator 失败或三轮耗尽 → 中止，不提交 company/rejection。
> 再次 whole-ticker preflight；非 clean 即 typed fail closed。然后执行 cancel checkpoint。

**逻辑分析**：
- Repair 失败发生在 company batch 前 → company 不提交，old 保留。✓
- Repair 成功、company 提交后、后续 filing 失败 → company 已提交，后续 open batch 回滚。✓
- Cancel 在 repair 前 → canonical cancelled 收口，company 不提交。✓
- Cancel 在 company 后 → company 已提交，后续不执行。✓

**裁决**：**正确**。Cancel/failure 边界清晰；不伪造 operation-wide rollback。

### 4.10 测试/barrier/static/coverage 是否 code-generation-ready

**v2 §8 测试矩阵**：
- §8.1 Storage owner tests：`list_source_integrity` 排序、malformed sha256、concurrent swap。✓
- §8.2 SEC 真实顶层矩阵：corruption repair、ordering spies、SC13 hidden mutation、既有 registry skip、selected-then-rejected、multiple/unselected/material/no-filing、repair failure/cancel、SC13 artifact/registry atomicity。✓
- §8.3 CN/HK 真实顶层矩阵：CN/HK 各一条真实 path、Event 控制、no-filing clean/corrupt、repair failure/cancel。✓
- §8.4 既有 race 矩阵：同 target 双 overwrite、different-target、revision churn、10 次 repeat。✓

**v2 §9 Static gate**：
- 6 条 rg 命令 + 1 条 AST 脚本 + pyright。✓
- AST 脚本检查项 10+ 条，覆盖 SC13 无 batch、company 顺序、无条件尾部 batch、prefetch 时序、staged classification、CN PDF/Docling、list_source_integrity 签名、v1 shared transport 等。✓
- 人工 review 逐条展开 SEC clean/repair-first/SC13 rejection/6-K rejection/CN assets/CN metadata reuse/company/registry-only/artifact+registry/rollback/cancel。✓

**v2 §10 Validation commands**：
- owner tests、affected union、10 次 deterministic repeat、base plan §9 aggregate、static gate、pyright、Ruff、compileall、JSON、diff check。✓
- 逐 production 文件 coverage `>= 80%`。✓

**裁决**：**Code-generation-ready**。测试矩阵、static gate、validation commands 均已完整指定。

### 4.11 v1 PASS 的结论是否仍有效

**v1 re-review 结论**：PASS。v1 的 storage-neutral SEC prefetch、discriminated variants、shared transport core、唯一 materializer、repair unconditional、Phase B identity-first、rejected prefetch-before-batch、200/304/empty/failure/cancel 测试与 static gate 全部通过。

**v2 §1.1 声明**：
> v1 的 storage-neutral SEC prefetch、private discriminated variants、single shared transport core、唯一 materializer、repair unconditional、Phase B identity-first、rejected prefetch-before-batch、200/304/empty/failure/cancel 测试与 static gate 全部继续有效。

**验证**：v2 不修改 v1 的任何核心设计，只增加顶层 workflow 顺序和 preflight。v1 PASS 结论仍然有效。✓

**裁决**：**v1 PASS 结论仍有效**。v2 是 v1 的增量叠加，不覆盖 v1 核心设计。

## 5. 综合裁决

### 结论: **PASS**

v2 amendment 的 root cause 分析正确（stop evidence 直接代码验证准确），mutation inventory 完整无漏项，三个 allowlist 增量最小充分，SC13 typed decisions 不是 god bag 且 persistence facts 未上移，artifact+registry durable unit owner 正确且非 operation-wide transaction，whole-tree inventory 单 guard 可实现，exactly-one selected repair-first 在所有 batch 前，所有 fail-closed 场景首 mutation 前 typed 裁决，cancel/failure 边界清晰，测试/barrier/static/coverage code-generation-ready，v1 PASS 结论仍有效。

### Non-blocking observations

| ID | Severity | Observation | 建议 |
|---|---|---|---|
| O-1 | Low | §5.2 preflight disposition 的纯函数签名未在 amendment 中完整列出（只列了输入输出类型） | implementation 阶段按 §5.2 优先级规则实现；plan 层面不 blocking |
| O-2 | Low | §6.2 步骤 5 "该 target 为 6-K 且 Phase A 最终判为 rejected" 的判定逻辑需要与现有 6-K precheck 代码对齐 | implementation 阶段确认 6-K policy 判定时序；plan 层面不 blocking |
| O-3 | Low | §8.4 要求 "同一矩阵 10 次 repeat；process writer/recovery subset 另跑 10 次"，implementation 需确保总测试时间可控 | implementation 阶段优化 barrier 超时；plan 层面不 blocking |

### 下一动作

本 review 结论为 PASS。等待 AgentDS 独立 review。两路均 PASS 且总控接受后，可恢复 Slice 4 implementation。
