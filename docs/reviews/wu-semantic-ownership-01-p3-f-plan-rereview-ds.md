# WU-SEMANTIC-OWNERSHIP-01 P3-F Plan Re-Review — AgentDS

## Review Target

- Plan: `docs/host/wu-semantic-ownership-01-p3-f-fins-source-provenance-plan.md`
- Gate: plan-rereview (post plan-fix)
- Plan completion state: `ready-for-plan-rereview`

## Review Context

- Original MiMo review: `docs/reviews/wu-semantic-ownership-01-p3-f-plan-review-mimo.md`
- Original DS review: `docs/reviews/wu-semantic-ownership-01-p3-f-plan-review-ds.md`
- Controller adjudication: `docs/reviews/wu-semantic-ownership-01-p3-f-plan-review-controller-adjudication.md`
- Plan fix report: `docs/reviews/wu-semantic-ownership-01-p3-f-plan-fix-codex.md`
- Controller validation: `docs/reviews/wu-semantic-ownership-01-p3-f-plan-fix-controller-validation.md`

## Re-Review Scope

本 re-review 仅验证八项 accepted plan-fix 要求是否在更新后的 plan 中闭合，以及是否引入新的 material plan finding。不做 implementation gate、不修改文件、不 commit/push/PR/merge。

## Accepted Fix Verification

### P3-F-PF-01 — Staging source idempotency/retry, SEC insertion point, placeholders, tests

**Controller requirement:** 定义 `stage_source_document` 的首次调用、重复调用（ingest_complete=False）、已完成 source meta、字段不匹配行为；指定 SEC staging 的具体插入点；定义 SEC staging placeholder 要求；添加对应测试。

**Plan evidence:**

| 要求 | Plan 位置 | 状态 |
| --- | --- | --- |
| 首次调用创建 ingest_complete=False meta | 第 87 行 | ✅ |
| 重复调用稳定字段匹配时幂等返回 | 第 88 行 | ✅ |
| 稳定字段不匹配时 fail closed | 第 89 行 | ✅ |
| 已完成 source meta 存在时 fail closed | 第 90 行 | ✅ |
| Staging-to-complete 更新同一 source id | 第 91 行 | ✅ |
| 失败/重试 SEC download 复用 staging meta | 第 92 行 | ✅ |
| SEC 插入点：`sec_download_filing_workflow.py`，SourceHandle 已知后、store_file 前 | 第 222-223 行 | ✅ |
| SEC staging placeholder：ingest_complete=False, source_kind=filing, source_provider=sec_edgar, primary_document=None, files/file_entries 为空 | 第 223-225 行 | ✅ |
| 测试：首次 staging、幂等、字段不匹配、completed-source 冲突、commit、blob 拒绝、读/列表排除、upload/SEC 管线路径 | 第 230-248 行 | ✅ |

**Verdict: CLOSED.** 所有 controller 要求已落实到 plan 具体行。

---

### P3-F-PF-02 — Provenance lookup signature vs citation routing context

**Controller requirement:** 说明 `_build_citation` 如何获取路由 `source_kind` 而不将其作为 provenance 真源；决定 `get_source_document_provenance` 是否接收 `source_kind` 并说明理由；meta 读取仅用于 citation 业务字段；验证所有 citation 调用点仍路由到单一 helper。

**Plan evidence:**

| 要求 | Plan 位置 | 状态 |
| --- | --- | --- |
| `_build_citation` 以 source_kind 为路由键读取 meta，但不作为分类真源 | 第 46-47 行 | ✅ |
| `get_source_document_provenance` 保留 `source_kind` 参数，匹配现有仓储寻址模式 | 第 81-82 行 | ✅ |
| 调用方需先从 meta/SourceHandle 获取 source_kind 作为路由键 | 第 82 行 | ✅ |
| Meta 读取仅用于 form_type/filing_date/accession_no 等 citation 业务字段 | 第 46-47, 165-166 行 | ✅ |
| 所有 citation 调用点路由通过 `_build_citation` | 第 167-168, 197, 413-416 行 | ✅ |
| 移除所有 `document_id.startswith("fil_")` 分类逻辑 | 第 166 行 | ✅ |

**Verdict: CLOSED.** 签名选择有明确理由，routing-vs-provenance 区分清楚。

---

### P3-F-PF-03 — Exact LLM-facing SourceType and Citation.source_provider values

**Controller requirement:** 显式命名新增 `SourceType` 枚举值及输出字符串；定义 `Citation.source_provider` 的输出格式、`to_dict()` 行为、`None` 语义；确保 LLM-facing 值自解释；添加 exact citation 值的测试断言。

**Plan evidence:**

| 要求 | Plan 位置 | 状态 |
| --- | --- | --- |
| `SourceType` 枚举值显式命名：SEC_EDGAR, CNINFO, HKEXNEWS, UPLOADED, SUPPLEMENTARY | 第 105-110 行 | ✅ |
| `Citation.source_provider` 输出字符串：SEC_EDGAR, CNINFO, HKEXNEWS, USER_UPLOAD | 第 111-115 行 | ✅ |
| `to_dict()` 行为：non-None 时可见，None 时省略 | 第 103-104 行 | ✅ |
| `None` 语义：仅非 source-backed 过渡 citation 或显式 providerless 路径 | 第 104-105 行 | ✅ |
| 禁止用 `None` 掩盖已完成 source meta 的缺失 provider | 第 105 行 | ✅ |
| Required citation mapping 完整覆盖五种来源 | 第 116-121 行 | ✅ |
| 测试断言 exact source_type 和 source_provider 值 | 第 174-180 行 | ✅ |
| LLM-facing 自解释约束 | 第 431 行 | ✅ |

**Verdict: CLOSED.** LLM-facing 值的命名空间清晰，storage values 与 display values 映射明确。

---

### P3-F-PF-04 — Company metadata freshness mechanism

**Controller requirement:** 定义 `RESOLVER_VERSION` 的 owner、变更时机、变更原因；若保留 resolver-version mismatch，添加 older-version 元数据刷新测试；time-based TTL 不引入。

**Plan evidence:**

| 要求 | Plan 位置 | 状态 |
| --- | --- | --- |
| `RESOLVER_VERSION` owner：upload company-meta resolver helper | 第 126 行 | ✅ |
| 变更规则：仅当 upload-provided company identity normalization 或 required-field semantics 变化时 | 第 126-127 行 | ✅ |
| 不是 release version / schema version / market-data recency marker / cache TTL | 第 127 行 | ✅ |
| Current-scope 规则：version 匹配时保留，不匹配时要求 refresh | 第 128 行 | ✅ |
| 无 time-based TTL | 第 128 行 | ✅ |
| 测试构造 older-version metadata 显式触发 refresh 路径 | 第 129 行 | ✅ |
| 测试：同版本保留、旧版本刷新、stale+缺失 company_name 报错、read runtime 不刷新 | 第 320-324 行 | ✅ |
| SEC/CN download 路径不经过 upload freshness logic | 第 315-316 行 | ✅ |

**Verdict: CLOSED.** `RESOLVER_VERSION` 的 owner 和变更规则已明确，不再有"永不触发"的问题——测试通过显式构造 older-version metadata 覆盖 freshness 路径。

---

### P3-F-PF-05 — Blob/source validation boundary, ProcessedHandle scope, TOCTOU classification

**Controller requirement:** 说明 source acknowledgement 在哪一层执行；若在 blob repository 执行，指定依赖注入/共享 core 机制；声明仅对 SourceHandle 验证；TOCTOU 风险分类为 accepted residual 或要求 file-lock/atomic 策略。

**Plan evidence:**

| 要求 | Plan 位置 | 状态 |
| --- | --- | --- |
| 执行层：blob repository，因为它是可能创建 ownerless blob state 的边界 | 第 98 行 | ✅ |
| 依赖注入：constructor injection 接收 source-meta existence/provenance reader，或共享 storage assembly 提供的 lower-level storage core | 第 98-99 行 | ✅ |
| 禁止导入具体高层 repository/pipeline/service/Host/UI | 第 99 行 | ✅ |
| `ProcessedHandle` 不纳入 P3-F scope，除非有独立证据 | 第 97, 376-377 行 | ✅ |
| TOCTOU 分类：accepted residual（当前 Host 单 storage assembly 运行） | 第 99-100 行 | ✅ |
| 若实现发现 multi-worker writes，需纳入 file-lock 或记录 follow-up owner | 第 100 行 | ✅ |

**Verdict: CLOSED.** 执行边界、注入方式、ProcessedHandle scope、TOCTOU 分类全部明确。

---

### P3-F-PF-06 — Slice dependency and shared staging/protocol ownership

**Controller requirement:** 声明哪个 slice 引入共享协议方法、哪个 slice 消费它们；澄清 CN staging 是迁移到新方法还是作为同一不变量的 legacy-shaped caller；避免两套独立 staging 语义。

**Plan evidence:**

| 要求 | Plan 位置 | 状态 |
| --- | --- | --- |
| Slice 1 引入共享 domain/protocol：FinsSourceProvider, SourceDocumentProvenance, get_source_document_provenance, stage_source_document | 第 63-64, 143-144 行 | ✅ |
| Slice 2 消费 Slice 1 staging protocol，不得发明第二套 staging 语义 | 第 64, 203-204 行 | ✅ |
| CN staging 必须委托或语义上由同一 `stage_source_document` 幂等/冲突规则支撑 | 第 204 行 | ✅ |
| CN 和 SEC 不得有两套独立的 staging 定义 | 第 204 行 | ✅ |

**Verdict: CLOSED.** Slice 依赖方向和共享协议 ownership 明确，两套 staging 语义已被禁止。

---

### P3-F-PF-07 — Fixture/source-meta migration impact

**Controller requirement:** 添加 Slice 1 实施前必需的 fixture/source-meta 扫描；列出可能需要 `source_provider` 的 fixture 类别或目录；声明 completed source meta 缺失 provider 时 fail closed，tests 必须迁移而非生产代码添加 fallback。

**Plan evidence:**

| 要求 | Plan 位置 | 状态 |
| --- | --- | --- |
| 实施前 fixture/source-meta 扫描命令 | 第 183-184 行 | ✅ |
| 受影响的 fixture 类别/目录列表 | 第 185 行 | ✅ |
| Completed source meta 缺失 provider fail closed | 第 186 行 | ✅ |
| 迁移 fixtures 而非添加兼容 shim | 第 186, 427 行 | ✅ |

**Verdict: CLOSED.** Fixture 影响面已显式列出，fail-closed 行为和迁移方向明确。

---

### P3-F-PF-08 — Wait boundary availability and no-boundary behavior

**Controller requirement:** 要求检查 Host wait record creation 中 Fins awaiting tools 的 `deadline_at`/`expires_at`；若无边界 wait 合法，显式论证 `WaitPollNotReady` 并指出 Host poller policy 阻止无限等待；添加 deadline/expires/invalid/no-boundary 测试。

**Plan evidence:**

| 要求 | Plan 位置 | 状态 |
| --- | --- | --- |
| 实施时检查 `dayu/host/waiting.py:_wait_record_row` | 第 134, 267 行 | ✅ |
| 当前证据：`deadline_at` 来自 `candidate.await_spec.deadline`，`expires_at=None` | 第 134 行 | ✅ |
| No-boundary 论证：Fins adapter 不是生命周期 owner，不得从 `created_at` 发明 terminal lost boundary | 第 136 行 | ✅ |
| Host poller policy 限制实际等待：`not_ready_observe_interval_seconds`、claim TTL、backoff、close/cancel | 第 136 行 | ✅ |
| 行为变更：未来 deadline→NotReady、过去 deadline→Lost、过去 expires→Lost、invalid boundary→Lost、no boundary→NotReady | 第 268-274 行 | ✅ |
| 与 Host callback 相同边界优先级：deadline_at 优先于 expires_at | 第 273 行 | ✅ |
| 测试覆盖五种边界场景 + created_at 年龄不再触发 lost | 第 279-289 行 | ✅ |
| 移除 `_TRANSIENT_PENDING_MAX_SECONDS` 和 `_transient_pending_expired` | 第 266, 298-299 行 | ✅ |

**Verdict: CLOSED.** No-boundary 论证充分，Host poller policy 作为实际等待上限的理由成立。

---

## New Material Findings

本轮 re-review 未发现新的 material plan finding。所有八项 accepted fix 均已闭合，plan 修复未引入新的架构问题、契约缺失、切片冲突或不可实施缺口。

以下为审查中注意到的非阻塞性细节，不构成 material finding：

1. **Stable fields 列表中的"expected market/company identity fields when present"**（第 88 行）未穷举。实施 agent 需要根据 `SourceDocumentUpsertRequest` 的实际字段自行判断哪些属于 stable fields。这属于正常的实施判断，不属于契约缺失——核心 stable fields（ticker, document_id, internal_document_id, source_kind, source_provider, ingest_method, fingerprint）已经显式列出。

2. **`FinsSourceProvider.USER_UPLOAD` → LLM-facing `"USER_UPLOAD"` 与 `SourceType.UPLOADED` 的不对称命名**：provider 是 `USER_UPLOAD`，source_type 是 `UPLOADED`。这是有意为之——provider 描述来源方，source_type 描述文档类别——在 plan 第 120 行的映射表中已明确。实施和 review gate 可验证。

3. **"Invalid boundary text"**（第 133 行）的精确判断标准留给实施判断（如非 datetime 可解析字符串）。这不影响整体契约完整性，因为正常路径（deadline_at 存在/不存在、expires_at 存在/不存在）和测试覆盖已足够。

## Deferred Items Status

Plan 中 deferred items 保持不变，与 controller adjudication 一致：

- Physical cleanup of stale staging directories → deferred（plan 第 428 行）
- Company metadata time-based TTL → deferred（plan 第 430 行）
- ProcessedHandle blob validation widening → deferred（plan 第 97, 377 行）
- Rejected filing artifact storage → 已分类为 separate maintenance owner（plan 第 432 行）

## Residual Risks

1. **Staging meta 残留**：失败下载/转换后残留的 `ingest_complete=False` meta 不会自动清理。Plan 声明 read/list 排除 `ingest_complete=False` 文档（第 225 行），在功能上安全。若大量残留影响 `list_documents` 性能，需独立 cleanup WU。

2. **TOCTOU**：blob repository 的 source-meta check-then-write 在多进程并发下存在理论竞态。Plan 已分类为 accepted residual 并给出条件处置策略（第 99-100 行）。

3. **FinsSourceProvider 与 SourceType 的命名空间分离**：storage values（小写）与 LLM-facing values（大写）在两个枚举中分别定义。如果未来新增 provider，需要同步更新两处映射。这是当前设计的显式 tradeoff——storage 和 LLM-facing 不应耦合——已在 plan 中明确。

## Conclusion

**pass**

全部八项 accepted plan-fix 要求已在当前 plan 中闭合，无新增 material plan finding。Plan 已达到 code-generation-ready 状态，可安全交给 implementation agent。

- 闭合 fixes: P3-F-PF-01, P3-F-PF-02, P3-F-PF-03, P3-F-PF-04, P3-F-PF-05, P3-F-PF-06, P3-F-PF-07, P3-F-PF-08
- 新材料 findings: 无
- Open questions: 无（原始 MiMo/DS open questions 已在 plan fix 中处理或转为实施时的验证步骤）

---

Re-review date: 2026-07-11
