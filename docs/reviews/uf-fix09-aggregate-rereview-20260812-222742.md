# UF-FIX09 Aggregate Re-Review

## Gate

- Gate：aggregate re-review（controller 裁决后、no-op fix confirmation 后）
- Work unit：UF-FIX09 shared-interruptible-docling-converter
- Base：`3f24d75adba49868fbc8646ac9c81f5a0a4a3c2e`
- Target：`d40ac173fd308b3329ed7216e0c26b9951663cdc`
- 冻结 base..target diff SHA-256：`2b82f47832f8042b4f498765d08fd34043225fb86c97507ee83a39e6cf126aca`（已验证一致）
- Branch：`codex/upload-filing-oracle`
- Output file：`docs/reviews/uf-fix09-aggregate-rereview-20260812-222742.md`

## Scope

- Included scope：base..target 全部实现、controller 裁决、no-op fix confirmation、accepted plan §11.1 与 S2 adjudication
- Excluded scope：另一 reviewer 本轮/原 aggregate artifact、UF-PF09 执行
- Parallel review coverage：三个 subagent 并行验证 AGG-01 直接证据（6 点）、AGG-02 直接证据（7 点）、cross-slice defect（8 点）

## Findings

未发现实质性问题。

### 验证摘要

#### AGG-01 — partial batch cancellation no-op 裁决核查

controller 裁决：rejected as observation；不是 residual risk。

**直接证据逐项验证**：

| # | 验证点 | 文件(行号) | 结论 |
|---|--------|-----------|------|
| 1 | `commit_prepared_upload_batch` 是唯一 publication lifecycle owner | `docling_upload_service.py:799-852` | ✅ 函数 docstring 明确声明唯一 owner；内部控制流：publish → cancel check → commit/rollback → finally rollback |
| 2 | `publish_prepared_upload` 只写入 caller-owned batch，不 commit、不 rollback | `docling_upload_service.py:311-380` | ✅ 函数体内无 `commit_batch`/`rollback_batch` 调用 |
| 3 | `_store_upload_assets` 所有写入绑定同一 batch | `docling_upload_service.py:382-514` | ✅ `reset_source_document`、`store_file`、`_upsert_source_document` 均传入同一 `batch` |
| 4 | `_rollback_precommit_upload_batch` 恰好一次 rollback | `docling_upload_service.py:855-882` | ✅ 函数体内恰好调用一次 `rollback_batch`，仅被 `commit_prepared_upload_batch` 的 `finally` 块调用 |
| 5 | `publish_prepared_upload` 唯一 production 调用点 | `docling_upload_service.py:830` | ✅ 位于 `commit_prepared_upload_batch` 内 |
| 6 | `commit_prepared_upload_batch` 恰好四个业务调用点 | `sec_upload_workflow.py:243,446`；`cn_pipeline.py:898,1167` | ✅ SEC filing、SEC material、CN/HK filing、CN/HK material |

**结论**：controller 裁决正确。当前唯一 publication owner 已完整 rollback 同一 batch；不存在绕过唯一 owner 的 production caller。未来假设新增错误 caller 不构成当前缺陷。

#### AGG-02 — callable transport 到 canonical token no-op 裁决核查

controller 裁决：rejected as duplicate of S2 R1；是冻结 plan 已裁决的显式 trade-off。

**直接证据逐项验证**：

| # | 验证点 | 文件(行号) | 结论 |
|---|--------|-----------|------|
| 1 | `CancellationToken` 是 `@runtime_checkable` Protocol | `dayu/contracts/cancellation.py:20-48` | ✅ 定义 `is_cancelled`、`cancel_reason`、`requested_at` 三个观察方法 |
| 2 | `FinsJobCancellationChecker` 继承 `CancellationToken` 并声明 `__call__` | `ingestion_runtime.py:904-920` | ✅ 同时满足 callable 与 canonical token contract |
| 3 | `_RuntimeJobCancellationChecker` 实现全部 4 方法 | `ingestion_runtime.py:1290-1378` | ✅ `__call__`、`is_cancelled`、`cancel_reason`、`requested_at` |
| 4 | `_DirectCancellationChecker` 实现全部 4 方法 | `ingestion_runtime.py:1571-1642` | ✅ 同上 |
| 5 | `FinsSourceDownloadAdapterRequest` 唯一 production 构造点 | `ingestion_runtime.py:4168-4177` | ✅ `cancellation_checker=context.cancellation_checker` |
| 6 | `_canonical_cancellation` fail-closed 收窄 | `cn_download_filing_workflow.py:889-908` | ✅ None→None，CancellationToken→原对象，纯 callable→TypeError |
| 7 | CN/HK adapter 透传到 converter | `cn_pipeline.py:1355` → `cn_pipeline.py:711` | ✅ `request.cancellation_checker` 直接传递 |

**结论**：controller 裁决正确。production 路径始终运输 composite concrete object，不会触发纯 callable 拒绝；`_canonical_cancellation` 在 converter 边界 fail-closed。把共享 request 标成 `CancellationToken` 会丢失 callable 静态契约，标成 ingestion-owned `FinsJobCancellationChecker` 会造成反向依赖。当前实现与冻结 plan §11.1 一致。

#### Cross-slice Defect 扫描

| # | 风险面 | 验证结果 |
|---|--------|---------|
| 1 | `_produce_direct_upload` 事件构造与 claim 顺序 | ✅ 事件在 claim 前构造（无副作用），claim 成功后才入队；失败则静默丢弃 |
| 2 | `_run_upload_job` durable path terminal disposition | ✅ 使用 atomic save + `_upload_terminal_disposition_from_job_record` 交叉验证 |
| 3 | `_upload_terminal_disposition_from_status` 唯一真源 | ✅ 被 pipeline JSON 解析、dataclass init、durable record read、pre-persistence validation 共 5 处调用 |
| 4 | `claim_upload_summary` 原子性 | ✅ 在 `self._lock` 内检查 `consumer_aborted` 和 `terminal_status` 双重守卫 |
| 5 | `ProcessDoclingConverter` frozen/slots | ✅ 有意设计为 plain class（无状态服务），数据类型均为 `frozen=True, slots=True` |
| 6 | `DoclingConversionConfig/Result` frozen/slots | ✅ 含 `__post_init__` SHA-256 验证 |
| 7 | `hasattr`/`getattr`/loose parsing | ✅ 零调用；所有 `isinstance` 使用 exhaustive dispatch + `assert_never` |
| 8 | `@property`/隐式 `__call__` | ✅ 零 `@property`；所有 `__call__` 均为显式委托 |

**结论**：未发现 material cross-slice defect。

## Accepted Findings 闭环确认

| Finding | 来源 | 修复 slice | 闭环状态 |
|---------|------|-----------|---------|
| S2 A1：重复计算 converter 已承诺的 SHA-256 | AgentDS S2 | S2 | ✅ 已修复，`docling_sha256 = conversion.sha256` |
| S3：direct upload claim 后事件构造异常可能丢失 RESULT | AgentDS S3 | S3 | ✅ 已修复，先构造事件再 claim |
| S3：cancelled summary 仍可能先投影 upload.completed | AgentDS S2 D1 | S3 | ✅ 已修复，typed terminal disposition + single claim |
| S3：CN/SEC status mapping 重复 | AgentDS S2 D2 | S3 | ✅ 已修复，`_upload_terminal_disposition_from_status` 唯一真源 |

所有 accepted findings 均已在对应 slice 修复并通过双路 re-review。

## Validation

- 冻结 target：`d40ac173fd308b3329ed7216e0c26b9951663cdc`（`git rev-parse HEAD` 验证一致）
- 冻结 diff SHA-256：`2b82f47832f8042b4f498765d08fd34043225fb86c97507ee83a39e6cf126aca`（已验证一致）
- 本 artifact 未修改生产代码、测试、accepted plan 或已有 artifact

## Docs Decision

无新增文档变更。既有 README decision 保持不变。

## Residual Risk

| 分类 | 风险 | 处理方式 |
|------|------|---------|
| `fixed in current slice` | S2 重复 digest 计算 | 已修复 |
| `fixed in current slice` | S3 projection 异常安全网 | 已补测 |
| `fixed in current slice` | S3 direct upload claim 后构造异常 | 已修复 |
| `covered by later approved gate` | UF-PF09 fresh evidence | 后续 gate |
| `assigned to later work unit` | company meta 独立事务 | later work unit |
| `assigned to later work unit` | web fetch cancellation | later work unit |
| `assigned to later work unit` | 非 POSIX descendant governance | later work unit |
| `assigned to later work unit` | 格式范围扩展 | later work unit |

- `requiring user decision`：无
- 未分类 residual risk：无

## Completion Status

**AGGREGATE RE-REVIEW COMPLETE — NO BLOCKING FINDINGS**

controller 对 AGG-01 与 AGG-02 的 no-op 裁决均有 accepted plan §11.1、S2 adjudication、owner contract、冻结 target 调用路径与 focused validation 的直接支持。三路 subagent 并行验证确认：

1. AGG-01：`commit_prepared_upload_batch` 是唯一 publication lifecycle owner，`publish_prepared_upload` 唯一调用点在 owner 内，四个业务调用点覆盖 SEC/CN/HK filing/material，`_rollback_precommit_upload_batch` 恰好一次 rollback。
2. AGG-02：`FinsJobCancellationChecker` 同时满足 callable 与 canonical token contract，`_canonical_cancellation` 在 converter 边界 fail-closed，production 路径始终运输 composite concrete object。
3. Cross-slice：`_upload_terminal_disposition_from_status` 唯一真源，`claim_upload_summary` 原子双守卫，事件构造与 claim 顺序正确，无 loose parsing 或 fallback。

所有 accepted findings 已闭环。无 blocking question、未分类风险或 requiring-user-decision 项。冻结 target 保持不变。
