# Plan Review — Slice 4 Amendment v2（AgentDS 独立路 Re-review）

## 元信息

- **Review 目标**：`docs/gateflow/wu-cli-download-01-slice4-plan-amendment-v2-20260810-072924.md`
- **Base plan**：`docs/gateflow/wu-cli-download-01-plan-20260809.md` §5.6 / Slice 4 / §9
- **V1 amendment**：`docs/gateflow/wu-cli-download-01-slice4-plan-amendment-20260810-060259.md`
- **新 stop evidence**：`docs/gateflow/wu-cli-download-01-slice4-stop-evidence-20260810-071524.md`
- **Review 类型**：adversarial plan re-review（AgentDS 独立路）
- **Reviewer**：AgentDS
- **Timestamp**：2026-08-10 07:38 UTC
- **Artifact path**：`docs/reviews/plan-review-20260810-slice4-amendment-v2-ds.md`
- **Baseline HEAD**：`93eb073e597899b3c25234eaf50923ba1d6c0219`

## Review Posture

本 review 对 v2 amendment 做 adversarial 审查。v2 的动机由 stop evidence 建立——真实 pipeline repair 用例证明 `company-only batch` 在 `filing Phase A` 之前发生，`strict complete-tree validator` 拒绝 company batch 复制的已损坏 source。motivation 成立。

v1 的 transport/materialization 设计与 v2 的 mutation order 修复是正交的：v1 解决"锁内 HTTP"，v2 解决"company batch 先于 repair"。两版不冲突，v2 叠加于 v1 之上。

## 1. 完整 mutation inventory 漏项检查

v2 §3 的 inventory 表声称覆盖 SEC/CN 全部 ticker batch mutation。逐项验证：

| v2 §3 声称的 mutation | 直接代码证据 | 验证结果 |
|---|---|---|
| SEC company meta batch（L457-469） | `sec_download_workflow.py:457-469`：`begin_batch → upsert_company_meta → commit_batch`，发生在 form/window 解析后、`_filter_filings` 前 | **确认** |
| SEC SC13 rejected artifact batch | `sec_sc13_filtering.py:454-494`：`should_keep_sc13_direction` 内调 `list_filing_files` + `_persist_rejected_filing_artifact`，早于顶层 filing loop | **确认** |
| SEC SC13 in-memory registry 写入 | `sec_sc13_filtering.py:503-511`：`_record_rejection_impl` 在同一函数内，artifact 成功或失败后均写入 | **确认** |
| SEC 6-K rejected artifact batch | `sec_download_filing_workflow.py:382-393`：Phase A 后调 `_persist_rejected_filing_artifact` | **确认** |
| SEC 6-K in-memory registry | `sec_download_filing_workflow.py:415-423`：artifact 成功后调 `record_rejection` | **确认** |
| SEC accepted filing Phase B | `sec_download_filing_workflow.py:445-617`：source blob+meta+processed commit | **确认** |
| SEC 尾部 unconditional registry batch | `sec_download_workflow.py:601-612`：在全部 filing 后无条件 `begin_batch → save_rejection_registry → commit_batch` | **确认** |
| CN/HK company meta batch | `cn_download_workflow.py:193-205`：profile resolve 后 `begin_batch → upsert → commit_batch` | **确认** |
| CN/HK accepted filing Phase B | `cn_download_filing_workflow.py:386-408,487-586`：PDF/Docling 后 source batch | **确认** |
| CN/HK PDF digest reuse Phase B | `cn_download_filing_workflow.py:240-271,646-680`：PDF 下载后 source metadata batch | **确认** |

**补充验证**：

- `sec_sc13_filtering.py:515` `extend_with_browse_edgar_sc13`：同样调用 `should_keep_sc13_direction` 产生 durable side effect。v2 §5.3 明确覆盖 "browse-edgar extension"。
- `sec_download_workflow.py:502` `_retry_sc13_if_empty`：同样经过 SC13 direction 路径。v2 §5.3 明确覆盖 "retry"。
- `_filter_filings_to_windows`（L496, L516）：纯过滤，不产生 batch mutation。无需覆盖。

**结论**：mutation inventory 完整，无漏项。所有进入 ticker published tree 的 batch mutation 均已清点。SEC HTTP cache 写入（transport cache，不经 ticker batch）正确排除。

## 2. V2 allowlist 增量最小充分性

v2 §4.1 新增三个 production 文件：

| 文件 | 必要性证据 | 不修改的后果 |
|---|---|---|
| `sec_download_workflow.py` | L457-469 company batch 在 filing Phase A 前；L601-612 无条件尾部 registry batch | 不改则 company batch 必然先于 repair，严格 validator 拒绝 |
| `cn_download_workflow.py` | L193-205 同构 company batch | 不改则 CN/HK 对称风险不解决 |
| `sec_sc13_filtering.py` | L454-511 SC13 direction 在 selection 内产生 durable artifact + registry | 不改则完整 preflight 前已提交 rejection batch |

**不修改的文件（有充分理由）**：

- `sec_download_state.py`：`_record_rejection`（L153-187）就地修改内存 dict；`_save_rejection_registry`（L97-119）接受 registry + batch。v2 的 "copy → record → batch save → replace" 模式可直接使用现有签名，无需修改函数体。直接证据：`_record_rejection` 接受 mutable dict 参数，v2 只需传入 registry copy。
- `sec_pipeline.py` / `cn_pipeline.py`：facade 层只机械适配 host/typed 签名，不拥有顺序。v2 禁止在其中复制或绕过 workflow 顺序——这本身就是防止 glue seam。
- `_fs_maintenance_core.py` / `sec_download_company_meta.py` / `cn_download_company_meta.py`：现有 owner 接口足够（upsert/save/rejection registry），只需改变调用时序。

**结论**：三个 allowlist 增量是最小且充分的。不修改的 exclusion 均有直接证据支撑。

## 3. SC13 typed decisions：god bag 检查

v2 §5.3 定义至少四个 variants：

| Variant | 携带字段 | 互斥性 |
|---|---|---|
| `Sc13DirectionAccepted` | accepted filing identity | 不与其他 variant 共享 optional 字段 |
| `Sc13DirectionRejectedWithArtifact` | filing、archive CIK、remote descriptors、source fingerprint、selected primary、rejection reason/category | 均为构造 artifact+registry 所需，字段集封闭 |
| `Sc13DirectionRejectedRegistryOnly` | registry entry facts + safe diagnostic | 不携带 remote files（listing 失败） |
| `Sc13DirectionRejectedAlreadyRegistered` | 纯 skip 标记 | 不产生 mutation |

**"把 persistence facts 上移" 检查**：

当前 `should_keep_sc13_direction`（`sec_sc13_filtering.py:454-511`）已经调用了 `list_filing_files`（L457-467，远端 HTTP）和 `_persist_rejected_filing_artifact`（L482-493，durable write）。`list_filing_files` 是远端 transport read，不在 writer lock 内，由 SEC downloader owner 产生。v2 不改变这一事实——它只把 listing 结果从 "立即持久化" 改为 "作为 typed intent 传递给后续 persistence owner"。

typed decision 携带的 facts（remote descriptors、archive CIK、source fingerprint 等）是 **construction prerequisites**，不是 durability decisions。它们回答"如果要持久化这个 rejection artifact，需要什么材料"，而非"现在就要持久化"。持久化决策仍由 `persist_rejected_filing_artifact`（persistence owner）在 repair gate 后执行。

**god bag 防护**：v2 §5.3 规定"若一个 variant 需要互斥 optional 字段，必须继续拆 variant"。当前四个 variant 之间没有共享 optional 字段，各自携带互不矛盾的事实集。

**结论**：SC13 typed decisions 不是 god bag。不构成 persistence facts 上移——listing 是已有 transport read，v2 只延迟了 persistence 时机。

## 4. Artifact + registry durable unit：owner 正确性

v2 §5.4 定义每条 rejection 的 atomic 边界：

```text
caller 在 registry 副本构造 registry_after
  → persistence 完整 prefetch（无 batch）
  → cancellation checkpoint
  → begin_batch
  → materialize + upsert rejected meta + save registry_after（同一真实 batch）
  → commit
  → caller 替换 in-memory registry
```

**Owner 验证**：

| 事实 | Owner | v2 是否改变 owner |
|---|---|---|
| Registry entry 构造 | `sec_download_state.py::_record_rejection` | 否，只改变调用时机（copy→record） |
| Artifact prefetch | `sec_downloader.py::prefetch_files_stream`（v1） | 否，保持 |
| Artifact materialization | `sec_download_persistence.py`（v1） | 否，保持 |
| Registry persistence | `sec_download_state.py::_save_rejection_registry` → `FilingMaintenanceRepositoryProtocol` | 否，现与 artifact 同 batch |
| commit/rollback | `BatchingRepositoryProtocol` | 否，保持 |

**非 operation-wide transaction 证明**：

- 每个 filing source 仍是独立 atomic batch（v1 不变）
- 每条 rejection 是独立 atomic batch（artifact + registry entry）
- Batch 之间不跨 provider I/O 持 writer lock
- Company batch 仅在 repair gate + post-repair preflight 之后发生

v2 §7 表明确记录"cancel或普通filing失败发生在company已成功之后"：company 是已提交独立 fact，不伪造 operation-wide rollback。

**结论**：durable unit owner 正确，非 operation-wide transaction。

## 5. Whole-tree inventory 单 guard 可实现性

v2 §5.1 的 `list_source_integrity` 设计：

```python
def list_source_integrity(self, ticker: str) -> tuple[SourceIntegrityClassification, ...]:
```

现有基础设施：
- `_FsSourceDocumentCore.list_document_ids`（L756-778）：已在一个 publication guard 内枚举 filing + material 全部 source ID
- `_FsSourceDocumentCore._list_document_ids_unguarded`（L780-795）：guard 内核心逻辑
- v1 的 `classify_source_integrity`（单个 source 分类）：已存在于 v1 allowlist

实现路径：
1. 获取一个短 publication guard
2. 调用 `_list_document_ids_unguarded` 枚举 filing + material 全部 ID
3. 对每个 ID 调用 `classify_source_integrity`（同一 unguarded core）
4. 按 `(source_kind.value, document_id)` 排序返回
5. 释放 guard

同一 guard 确保 "list" 和 "classify" 看到同一 published revision——消除跨 publication 混合视图。这不是新 capability，只是现有 source facts 的整树查询。

**单 guard 可实现性**：现有 `list_document_ids` 已证明 "获取 guard → 枚举 → 释放" 模式。`list_source_integrity` 遵循同一模式，只是增加了 per-ID classification 调用。classification 是纯本地计算（读 meta → stat file → compute digest），不在 guard 内做 I/O。

**结论**：可实现。

## 6. Exactly-one selected repair-first 时序验证

v2 §6.1 的不变量序列：

```text
READ_ONLY_DISCOVERY_AND_FINAL_SELECTION
  → WHOLE_TICKER_INTEGRITY_PREFLIGHT
  → STABLE_PARTITION(REPAIR_TARGET_FIRST)
  → OPTIONAL_REPAIR_FIRST_THREE_ROUND_PHASE_A/B
  → WHOLE_TICKER_POST_REPAIR_PREFLIGHT
  → COMPANY_PUBLICATION
  → DEFERRED_REJECTIONS / REMAINING_FILINGS
  → TERMINAL
```

**验证 repair-first 在所有 company/rejected/maintenance 之前**：

| 阶段 | 是否产生 batch | 证据 |
|---|---|---|
| Discovery + Selection | 否。SC13 只产生 typed decisions（§5.3） | `sec_sc13_filtering.py` 修改后不再调 `_persist_rejected_filing_artifact` |
| Whole-ticker preflight | 否。只读 published tree（§5.1） | `list_source_integrity` 在短 publication guard 内只读 |
| Repair-first Phase A/B | 是，但仅 target source batch。发生在 company 前（§6.2 step 5） | ordering spy 断言 `repair_commit < company_begin`（§8.2） |
| Post-repair preflight | 否 | 同 whole-ticker，只读 |
| Company publication | 是（首个 company batch） | §6.2 step 7 |
| Deferred rejections | 是（每条独立 durable unit） | §6.2 step 8 |

**边界情况**：
- Repair 失败/cancel：company 前中止，company batch 调用数 0（§7 表）
- Repair 成功但 post-repair preflight 非 clean：company 前 typed fail closed（§6.2 step 6）
- Concurrent writer 已修好：post-repair preflight 看到 clean，按原 `overwrite=False` skip repair Phase B（§6.1）

**结论**：repair-first 在任何 company/rejected/maintenance batch 之前。时序可证明。

## 7. Multiple/unselected/material/no-filing/selected-rejected 首 mutation 前 typed fail closed

v2 §5.2 的 `SourceIntegrityPreflightDisposition` 逻辑（固定优先级）：

| 场景 | Disposition | 首个 ticker batch | 直接证据 |
|---|---|---|---|
| Storage 结构错误 | 构造 inventory 时直接抛 strict error | 0 | identity/meta/manifest 损坏包括 malformed sha256，不进入 classification |
| >1 REPAIR_REQUIRED | `MULTIPLE_REPAIR_REQUIRED` | 0 | §5.2 rule 2 |
| 1 个，不在 accepted/rejected | `UNSELECTED_REPAIR_REQUIRED` | 0 | §5.2 rule 3；含 material corruption |
| 1 个，在 rejected 集合 | `SELECTED_REJECTED_REPAIR_REQUIRED` | 0 | §5.2 rule 4；含 SC13 rejected target corruption |
| 1 个，accepted filing | `SelectedSourceRepairRequired` | repair batch 先于 company | §5.2 rule 5 |
| 0 个 | `NoSourceRepairRequired` | company batch 正常 | §5.2 rule 6 |

**No-filing 边界**（§6.3 step 5）：
- No-filing + inventory clean → company batch 提交
- No-filing + 存在 corruption → `UNSELECTED_REPAIR_REQUIRED`，company batch 为 0

**Selected-rejected 6-K 边界**（§6.2 step 5）：
- Designated repair target 在 Phase A 后被 6-K policy 拒绝 → 在调用 rejected persistence 前抛 `SELECTED_REJECTED_REPAIR_REQUIRED`
- 损坏 source、company、artifact、registry 全部 old
- 不把损坏 source 重写为新 source，不发布语义冲突的 rejection

**§7 矩阵逐行验证**：

| 场景 | 首个 ticker mutation 前裁决 | Durable facts | 验证状态 |
|---|---|---|---|
| Multiple corruption | company/rejection/source batch 均 0 | 全部 old | **可证明**：preflight 在 selection 后、company 前执行 |
| Unselected corruption | 同上 | 同上 | **可证明** |
| Selected-rejected 6-K | rejected persistence 前失败 | 全部 old | **可证明**：repair gate 在 deferred rejection 前 |
| SC13 rejected target corrupt | intent 已形成但未发布 | 全部 old | **可证明**：SC13 intent 是 typed decision，非 durable fact |

**结论**：所有 multiple/unselected/material/no-filing/selected-rejected 场景均在首个 ticker batch mutation 前 typed fail closed。全部 old facts 精确保留。

## 8. 6-K remote policy 判定后 old facts 保持

v2 §6.2 明确 6-K 处理流程：

1. Selection 阶段（step 2）：全部 SEC 候选统一应用 rejection-registry policy。`overwrite=False` 命中同 version entry → 进入最终 rejected 集合。此时已不进入 single-filing。
2. Preflight 阶段（step 3-4）：若 rejected target 本身 corrupt → `SELECTED_REJECTED_REPAIR_REQUIRED`，首 batch 为 0。
3. Repair-first 阶段（step 5）：若 repair target 为 6-K，先执行 v1 完整 Phase A → 锁外 prefetch → Phase B。Phase A 的 6-K remote policy（`_precheck_6k_filter`）判定 reject → 在调用 rejected persistence 前抛 `SELECTED_REJECTED_REPAIR_REQUIRED`。
4. 此时 company、artifact、registry、source batch 均为 0。损坏 source 不变成新 source，rejection 不发布。

**Old facts 保持机制**：rejected persistence 从未被调用 → artifact 不变；company batch 从未开始 → company 不变；source batch 从未开始 → 损坏 source 不变。所有 old facts 由"任何 batch 都未 commit"保证。

**结论**：6-K remote policy 判定后 old facts 完全保持。

## 9. Cancel/failure 与已提交独立 batch 边界

v2 §7 表精确区分两类失败：

**首 mutation 前失败**（cancel/failure 在 company/rejection 之前）：
- Cancel 在 discovery/selection/preflight/repair/begin 前 → company/rejection 均 old
- Open target batch rollback，后续不执行

**独立 batch 已成功后失败**（cancel/failure 在 company 提交之后）：
- "cancel 或普通 filing 失败发生在 company 已成功之后" → 不伪造 operation-wide rollback
- Company 是完整已提交新 fact
- 此前成功的独立 source/rejection batch 保留
- 当前 open batch 回滚
- 后续不执行

**Storage 层保护**：`_fs_storage_infra.py:586-680` 的 `commit_batch` 严格区分 pre-commit error（rollback）与 post-commit error（primary exception 保留 committed tree）。v2 不改变这一 storage 层语义。

**结论**：cancel/failure 与独立 batch 边界清晰。不通过 operation-wide transaction 假装回滚已提交事实。

## 10. 测试/barrier/static/coverage code-generation-readiness

### 10.1 测试矩阵

v2 §8 的测试规格：

| 类别 | 覆盖范围 | 是否 code-generation-ready |
|---|---|---|
| Storage owner（§8.1） | `list_source_integrity` 单 guard + malformed sha256 strict error + per-ticker reservation/blocking/recovery | **是**。spy 接口已在 v1 定义（`SpyBatchRepository`、`SpyStoreFile`），v2 增量仅需验证 `list_source_integrity` |
| SEC 顶层（§8.2） | 真实 pipeline repair（size/digest/physical missing）、SC13 hidden mutation Event、registry skip、selected-then-rejected 6-K、multiple/unselected/material/no-filing、repair failure/cancel、artifact/registry atomicity | **是**。全部指定 spy 记录内容与断言顺序 |
| CN/HK 顶层（§8.3） | CN size/digest/physical missing、HK 顺序回归、no-filing clean/corrupt、repair failure/cancel | **是**。指定 Event/barrier 名称 |
| Race 矩阵（§8.4） | 同 target 双 overwrite、different-target union、revision churn 三轮、10 次 repeat + process writer 另 10 次 | **是**。继承 v1 barrier 序列 |

**Spy 接口**：v1 已定义 `SpyBatchRepository`（`begin/staged_classify/commit/rollback/release`）和 `SpyStoreFile`（`sequence, batch_token, name, payload_sha256`）。v2 增加 `SpyCompanyMetaRepository`、`SpyFilingMaintenanceRepository` 记录首次 mutation。接口定义充分。

**取消测试**：v2 继承 v1 的 cancel-after-prefetch Event 策略（fake prefetch stream 等待 test-owned Event），并扩展到 repair failure/cancel 场景。

### 10.2 Static gate

v2 §9 的 static gate 在 v1 四类证据基础上，增加 v2-specific 检查（L371-379）：
- `sec_sc13_filtering.py` 不调 persistence/batch/registry mutation
- SEC/CN company `begin_batch` 的语法位置在 preflight/repair/post-check 之后
- SEC 无无条件尾部 maintenance batch
- `persist_rejected_filing_artifact` prefetch 在 `begin_batch` 前
- 多条 single-filing 不变量

所有检查均为 syntax-level，可用 Python `ast` 模块实现。v1 已证明 AST 脚本可行（stop evidence 提及 "临时AST gate：PASS，仅声称syntax-level evidence"）。

### 10.3 Coverage

v2 §9 要求 affected union（10 个测试文件）全部通过，10 次 deterministic repeat，逐 production 文件 `coverage >= 80%`。v1 已通过 affected union（`585 passed, 3 warnings`），v2 增加了顶层 pipeline 用例后覆盖率应更高。

**结论**：测试/barrier/static/coverage 规格是 code-generation-ready 的。

## Findings

本轮未发现 blocking finding。以下为 non-blocking observations：

### OBS-1-低-SC13-typed-decision-variant-数量可能随实现增加

- **位置**: §5.3 SC13 typed decision variant 定义
- **问题类型**: 实现细节
- **当前写法**: "精确 variant 至少为" 四种。若实现发现需要更多 variant（如不同的 rejection reason 需要不同的 artifact construction facts），§5.3 的 "若一个 variant 需要互斥 optional 字段，必须继续拆 variant" 规则已覆盖。
- **影响**: 不影响 plan 正确性。implementation 阶段按需拆分 variant。
- **严重程度**: 低。

### OBS-2-低-rejected-artifact-的-overwrite-语义在-typed-decision-中传递

- **位置**: §5.3 `Sc13DirectionRejectedWithArtifact` variant
- **问题类型**: 实现细节
- **当前写法**: variant 携带"构造既有 artifact/registry 所需且互不矛盾的 facts"。v1 的 `persist_rejected_filing_artifact` 仍需要 `overwrite` 参数以传给 `prefetch_files_stream(allow_not_modified=...)`。typed decision 当前未显式携带 `overwrite`。
- **分析**: `overwrite` 是顶层 request-level 事实，在 deferred rejection 执行时 workflow 已持有。workflow 可将其作为独立参数传给 `persist_rejected_filing_artifact`，无需通过 SC13 typed decision 传递。这不是 design gap。
- **严重程度**: 低。implementation 阶段自然解决。

### OBS-3-低-`DownloadFilesStream`-Protocol-删除影响范围

- **位置**: v1 §5.2 已要求删除 `DownloadFilesStream` Protocol；v2 不改变此要求
- **问题类型**: 实现验证
- **当前写法**: v2 §9 的 static gate 包含 `rg` 枚举所有 `DownloadFilesStream` references。若除 `persist_rejected_filing_artifact` 外有其他 consumer，需逐个处理。
- **影响**: implementation 阶段 `rg` 枚举即可验证。
- **严重程度**: 低。

## Open Questions

无。v2 规格自足，无需要澄清的新 open question。

## Residual Risks

| # | 风险 | 分类 | 建议跟踪 |
|---|---|---|---|
| RR-1 | Out-of-band physical corruption 在 post-repair preflight 和 company commit 之间发生 | 平台风险 | v2 §11 列为 "assigned to later storage reliability WU"。strict commit validator 仍为最后防线。非本 slice blocker |
| RR-2 | `list_source_integrity` 对于大量 source 的 ticker（如 >100 filings）可能耗时 | 性能 | publication guard 只覆盖本地文件 stat + digest 计算，无网络 I/O。实现阶段 profiling 验证；若 >100ms 需记录为 known limitation |
| RR-3 | SC13 extension/retry 的 typed decision 去重逻辑 | 实现 | v2 §5.3 规定 "重复筛选同一 accession 只复用 decision"；implementation 阶段需设计 decision cache 的 key 与生命周期 |
| RR-4 | CN no-filing + clean → company 提交的语义可能造成空 ticker tree | 业务语义 | 这是现有行为（company-resolved durable），v2 不改变 |

## Final Conclusion

**PASS**

v2 amendment 在所有用户指定的审查维度均通过了 adversarial 审查：

- **完整 mutation inventory**：无漏项。10 个 mutation 点逐一有直接 `file:line` 证据
- **Allowlist 增量**：3 个文件为最小且充分；排除的 4 个文件均有不修改的直接理由
- **SC13 typed decisions**：不是 god bag，不把 persistence facts 上移。variant 按 construction prerequisites 切分
- **Artifact + registry durable unit**：owner 正确，非 operation-wide transaction。每 rejection 独立 atomic batch
- **Whole-tree inventory 单 guard**：可实现，复用现有 `list_document_ids` 的 guard→enumerate→release 模式
- **Exactly-one selected repair-first**：在时序上先于所有 company/rejected/maintenance batch
- **Multiple/unselected/material/no-filing/selected-rejected**：全部在首个 ticker batch mutation 前 typed fail closed
- **6-K remote policy**：old facts 由"任何 batch 都未 commit"保证
- **Cancel/failure 与已提交 batch 边界**：明确区分首 mutation 前失败和独立 batch 已成功后失败
- **测试/barrier/static/coverage**：code-generation-ready

v2 与 v1 正交叠加，无冲突。v1 的 transport/materialization 设计（prefetch、private variants、single core、唯一 materializer、repair unconditional）全部继续有效。
