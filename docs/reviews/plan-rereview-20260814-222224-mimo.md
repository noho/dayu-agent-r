# upload-filing-ticker-alias-contract plan re-review

## Review metadata

| 字段 | 值 |
| --- | --- |
| Reviewer | AgentMiMo |
| Artifact | `docs/reviews/plan-rereview-20260814-222224-mimo.md` |
| Review type | plan re-review（plan fix 后复核） |
| Reviewed plan | `docs/reviews/wu-upload-filing-ticker-alias-contract-plan-codex.md` |
| Plan fix artifact | `docs/reviews/wu-upload-filing-ticker-alias-contract-plan-fix-codex.md` |
| Goal confirmation | `docs/reviews/wu-upload-filing-ticker-alias-contract-goal-confirmation-controller.md` |
| Controller adjudication | `docs/reviews/wu-upload-filing-ticker-alias-contract-plan-review-controller-adjudication.md` |
| Previous reviewer artifacts | `docs/reviews/plan-review-20260814-215912.md`（MiMo, pass-with-risks）; `docs/reviews/plan-review-20260814-220204.md`（DS, fail） |
| Review scope | A1–A8 closure verification, R1/R2 rejection validity, Company Identity/CompanyMeta/storage owner uniqueness, commit intent authoritative merge, writer→recovery→identity→publication lock graph, swap-before-COMMITTED recovery, read route corruption/lock typed projection, over-design challenge |
| Conclusion | **pass** |

## Method

完整读取 plan（fix 后）、goal confirmation、controller adjudication、plan fix artifact、两份前序 plan review artifact、`docs/host/design.md` §1–§3/§18、`docs/engine/design.md` §1/§10/§16。以直接代码/数据流证据复核每个 accepted finding 是否真正关闭、每个 rejected reason 是否仍合理。挑战反例与过度设计。

### 直接代码证据来源

| 文件 | 验证内容 |
| --- | --- |
| `ingestion_runtime.py:855-944, 1051-1070` | prevalidation 在 writer lock 前调用 `resolve_upload_company_meta_decision`；`ValueError -> COMPANY_NAME_REQUIRED` 是 catch-all |
| `sec_upload_workflow.py:233-253` | `begin_batch` 后 stage `company_meta_decision`，writer lock 已持有时才 stage |
| `_fs_storage_infra.py:481-536, 583-691, 1334-1350, 1633-1775` | `begin_batch` 取 writer lock；`commit_batch` 顺序：validate → publication guard → backup/swap/COMMITTED；recovery sweep 取 recovery lock 后对 orphan 做物理恢复 |
| `_fs_company_meta_core.py:209-238, 240-268, 272-305, 351-378` | `_upsert_company_meta_impl` 写 staging；`resolve_existing_ticker` 先 direct canonical probe 再 alias fallback；`_build_company_alias_index_from_meta` 产生 `dict[str, list[str]]` |
| `read_runtime.py:2301-2362` | `_resolve_canonical_ticker` 有 `strip().upper()` fallback |
| `ticker_normalization.py:67, 128-147, 344-366` | `_US_SYMBOL_PATTERN` 只允许单字符 dot section；`try_normalize_ticker` 是非抛错版本 |
| `_fs_storage_utils.py:56-101` | `_canonicalize_ticker_alias` 和 `_normalize_company_ticker_aliases` 各自实现归一化/去重 |
| `upload_failure.py:23-42, 148-201` | exception chain：`DoclingConversionError → OSError → RUNTIME/UNEXPECTED_RUNTIME` |
| `fins_tools.py:1056-1119, 1756-1775` | generic `except Exception → execution_error`；`_ticker_parameter_schema` 无验证约束 |
| `error_contract.py:8-27` | `ErrorCode` 枚举无 `WORKSPACE_IDENTITY_CORRUPTED`/`STORAGE_UNAVAILABLE`（plan 新增） |
| `document_models.py:422-476` | `CompanyMeta` 有 `ticker`/`market`/`ticker_aliases` 字段；`from_dict` 不做 ticker 归一化 |
| `fmp_company_info.py:33-45, 335-371` | `_normalize_ticker_token` 有 `strip().upper()` fallback；`FmpCompanyInfo` 有 `canonical_ticker`/`ticker_aliases` |
| `fins.py:1107-1158` | `_parse_ticker_csv` 用 `normalize_ticker`；`_merge_ticker_aliases` 自行去重 |
| `docs/host/design.md` §2–§3 | Host 不承载财报业务语义；`dayu.runtime` 不得 import `dayu.fins` |
| `docs/engine/design.md` §1 | Engine 不负责财报业务语义、ticker 归一或财报文档仓储 |

## A1–A8 closure verification

### A1 — 同 canonical 并发 lost-update：**已关闭**

**fix 方案复核**：

plan 新增 `dayu/fins/domain/company_meta_contract.py` 作为唯一 commit intent/merge owner。`CompanyMetaCommitIntent` 只携带 `proposed_identity`（本次声明的 aliases）、`merge_mode`、`expected_non_identity`（optimistic precondition）和 `resolver_version`。`merge_company_meta_for_commit` 是 pure function，在 commit-time identity guard 内由 storage 机械调用。

**代码证据确认**：

- 当前代码 `ingestion_runtime.py:1051-1070` 在 writer lock 前调用 `resolve_upload_company_meta_decision`，产生 `company_meta_decision`。
- `sec_upload_workflow.py:233-253` 在 `begin_batch`（取得 writer lock）后 stage 该 decision。
- plan 将 stage 改为记录 `CompanyMetaCommitIntent` 到 `_ActiveBatchState.company_meta_intent`，不提前写 `meta.json`。
- commit-time 在 identity guard 内重读 incoming canonical 的 published meta（`current_published`），与 intent merge。
- merge 规则：current aliases 在前、intent aliases 在后稳定 union；`preserve_published` 保留 current 非 identity 字段；`refresh_if_stale` 按 optimistic precondition 判定。

**反例验证**：

P1 prevalidate v1 → P2 commit alias Y（published 变 v2）→ P1 commit：identity guard 内读到 v2 current，merge 结果 = v2 aliases ∪ P1 declared aliases。Y 不丢失。P1 的旧 non-identity snapshot 不覆盖 P2 更晚 durable facts。

**测试覆盖**：plan §11.3 列出 barrier-controlled `multiprocessing.get_context("spawn")` cross-process test，覆盖两个提交均保留 aliases 和 changed-but-still-stale typed fail-closed。

**结论**：fix 正确关闭了 prevalidation snapshot 到 commit-time merge 的窗口。authoritative current 在 writer + recovery + identity 三重保护下读取，prevalidation snapshot 不再有覆盖通道。

### A2 — 6-K primary repair 漏项：**已关闭**

plan §9.1 将 `sec_6k_primary_document_repair.py` 纳入 affected files，§10 S1 allowed files 包含该文件。迁移限定为 `entry.company_meta.ticker → entry.company_meta.ticker_identity.canonical_ticker` 机械替换。由 `test_sec_pipeline_download.py` 既有 repair regression、residue scan 和 pyright 共同验证。fix artifact 确认无新 repair 业务行为。

### A3 — S1 storage 中间契约：**已关闭**

plan §10 S1 change #5 精确规定：
- `_resolve_existing_ticker_by_company_alias` 和 `_build_company_alias_index_from_meta` 只消费 `CompanyMeta.ticker_identity.lookup_tickers()`。
- S1 保留 `alias → list[canonical]` index 形状和 duplicate-owner late `ValueError`。
- S1 residue scan 临时允许 `resolve_existing_ticker`、`_resolve_existing_ticker_by_company_alias`、`_build_company_alias_index`/`_build_company_alias_index_from_meta` 和 read runtime 旧 fallback。
- S2 一次删除旧 public/internal route，用 `_build_unique_company_identity_index`（`dict[str, str]`）替换两个 list-index helpers。

代码证据确认：`_build_company_alias_index_from_meta`（`_fs_company_meta_core.py:351-378`）当前消费 `_normalize_company_ticker_aliases`；S1 改为消费 `ticker_identity.lookup_tickers()` 后，该 helper 可安全删除。

### A4 — incoming conflict / published corruption 分型：**已关闭**

plan 区分：
- `CompanyTickerAliasConflictError`：valid published owner 与 incoming commit intent 冲突。字段含 `alias`/`existing_canonical_ticker`/`incoming_canonical_ticker`。仅用于 commit-time。
- `CompanyTickerIdentityCorruptionError`：missing/invalid/mismatch/duplicate durable identity。字段含 `kind`（closed `Literal`）和 `lookup_ticker`。用于 read route 和 commit scan。

read projection：
- 新增 `ErrorCode.WORKSPACE_IDENTITY_CORRUPTED` 和 `STORAGE_UNAVAILABLE`。
- `_resolve_canonical_ticker` 捕获 `CompanyTickerIdentityCorruptionError` → `FinsReadBusinessError(workspace_identity_corrupted, ...)`。
- identity/publication guard `RuntimeFileLockError` → `FinsReadBusinessError(storage_unavailable, ...)`。

代码证据确认：当前 `fins_tools.py:1111` 的 `except Exception → execution_error` 会吞掉任何非预期异常。plan 在该 catch 之前增加 `FinsReadBusinessError` catch（line 1084 已存在），typed corruption 被正确投影为 `exc.code.value`。

upload projection：
- `CompanyTickerAliasConflictError` → `storage/ticker_alias_conflict`（新 code）。
- `CompanyTickerIdentityCorruptionError` → `storage/storage_io`（既有 code），不归责 incoming alias。

代码证据确认：当前 `upload_failure.py:161-201` catch chain 是 `DoclingConversionError → OSError → RUNTIME`。`CompanyTickerAliasConflictError(ValueError)` 不会被 `OSError` 误捕，需在 `OSError` 前插入 catch。plan §5.6 明确描述此位置。

**结论**：read/upload 两侧 failure contract 一致且有界。字段语义适合各自场景（read 无 incoming canonical，commit 有）。

### A5 — company-name-required reason 收窄：**已关闭**

plan 新增 `UploadCompanyNameRequiredError`（typed exception），只在 missing/stale meta 需要 explicit refresh 且缺 company name 时产生。`ingestion_runtime.py` 只捕获该 typed exception，不捕获 `ValueError`。

代码证据确认：当前 `ingestion_runtime.py:1055-1058` 的 `except ValueError: _raise_upload_usage(COMPANY_NAME_REQUIRED)` 是 catch-all，会误捕 builder 的 alias grammar `ValueError`。plan 收窄为只捕获 typed exception。`_validate_fins_upload_filing_static` 的 alias 校验（line 886-892）在 decision 之前拒绝非法 alias，但 plan 不依赖该偶然顺序——typed exception 确保即使校验顺序变化也不会误报。

### A6 — invalid published meta commit fail closed：**已关闭**

plan §7.4 step 8 规定：commit identity scan 只枚举 `portfolio/` 实际 published ticker directories；任何 missing/invalid CompanyMeta、descriptor mismatch 或 durable duplicate 均在 backup/swap 前抛 typed corruption。backup/lock-only locator 不视为 published corpus。

代码证据确认：当前 `_fs_company_meta_core.py:160-171` inventory 已能产生 `invalid_meta` 状态。plan 将该行为提升为 commit-time fail-closed，不允许跳过。

测试覆盖：plan §11.3 列出 missing meta、invalid JSON/schema、identity mismatch 分别注入，断言 incoming 与 corrupt corpus tree SHA 不变、首次 replace 调用为零。

### A7 — recovery-read 与 guard failure tests：**已关闭**

plan §7.5 规定 recovery 对每个 recovered ticker tree 在 recovery guard + nonblocking writer 后、publication mutation 前统一取得 identity guard。不依赖不可恢复的 transaction-local fact。

测试覆盖：
- barrier 固定 recovery 已持 identity guard 但尚未 physical restore，alias read 必须等待并只观察恢复后完整 route。
- identity guard acquire failure：第一次 restore/delete/swap 为零且 evidence 保留。
- identity guard release failure：验证恢复结果、最早 primary 与 secondary note 规则。

代码证据确认：当前 `_recover_single_batch_dir`（`_fs_storage_infra.py:1633-1775`）在 recovery lock 下执行物理恢复。plan 在 publication guard 前插入 identity guard acquisition。

### A8 — S1/S2 完成语义：**已关闭**

plan §10 S1 completion signal 明确："S1 只是 reviewed local checkpoint，仍保留 late duplicate detection 与 A1 的 prevalidation-to-commit 并发窗口，不满足 workspace atomicity success signal，不得部署、close 或进入 final closeout；accepted S1 local commit 后必须立即继续 S2。"

plan 顶部删除"用户要求 plan complete 后停止"的错误表述，恢复 Gateflow 自动推进语义。

**结论**：S1/S2 边界清晰。S1 不被误读为 goal confirmation 完成。

## R1/R2 rejection 复核

### R1 — recovery 只对含 meta.json orphan 取得 identity guard：**rejection 仍合理**

controller rejected reason："当前 batch staging 会复制既有 ticker tree，`meta.json` 存在不能证明本 batch 修改过 CompanyMeta；crash 后 transaction-local `company_meta_staged` 不可恢复。用文件存在推断 mutation 违反 semantic-owner 约束并重新打开 crash 窗口。"

代码证据确认：`begin_batch`（`_fs_storage_infra.py:514-536`）在 `if target_ticker_dir.exists()` 时执行 `shutil.copytree(target_ticker_dir, staging_ticker_dir)`，把整个 published tree（含 `meta.json`）复制到 staging。因此 staging 中 `meta.json` 的存在不表示本 batch 修改过 CompanyMeta。

plan 的统一 guard 方案（对所有 recovered ticker tree 取 identity guard）正确。性能风险分类为 `assigned to later work unit`，只有实测 contention 后才进入独立性能 WU。

### R2 — `_STORAGE_FAILURE_CODES` 当前不存在：**rejection 仍合理**

controller rejected reason："plan §5.6 明确写的是'新增 `_STORAGE_FAILURE_CODES`'，并明确在 generic/OSError 前识别 typed conflict；这不是 implementation 遗漏。"

代码证据确认：当前 `upload_failure.py` 无 `_STORAGE_FAILURE_CODES`。plan 明确将其列为 S2 新增 contract。mapper unit test 已列在 plan 测试矩阵中。

## Lock graph 复核

plan §7.3 锁序：

```text
normal meta commit:
  ticker writer → recovery guard → recovery sweep → identity guard
  → incoming/current publication guard（读取后释放）
  → actual-published publication guards（校验扫描，排序逐个释放）
  → target publication guard

alias read route:
  identity guard → ticker publication guards（排序逐个释放）

recovery:
  recovery guard → ticker writer → identity guard → publication guard

ordinary no-meta commit:
  ticker writer → target publication guard
```

**无环验证**：

1. normal meta commit 持有 writer 时等 recovery guard。recovery 持有 recovery guard 时对 ticker writer 做 nonblocking try-lock（跳过活动 batch）。不形成等待环。
2. identity guard 在所有路径中位于 recovery guard 之后、publication guard 之前。
3. read route 只取 identity guard → publication guards，不取 recovery guard。不与 commit 形成环。
4. 任何持有 identity/publication guard 的路径不得再获取 recovery guard（plan §7.3 明确约束）。

**代码证据确认**：当前 recovery 顺序 `recovery → nonblocking writer → publication` 由 `_fs_storage_infra.py:1334-1350`（`recover_orphan_batches` 取 recovery lock）和 `:1633-1775`（`_recover_single_batch_dir` 内 nonblocking ticker writer）证实。

## swap-before-COMMITTED recovery 复核

plan §7.4 step 11：swap/journal 失败在 target publication + identity + recovery guards 保护下走 precommit restore。published reader 只看到完整 old/new。

plan §7.5：crash interleaving 场景——A 在 target swap 后、COMMITTED 前留下 orphan，B 已持不同 ticker writer 准备声明 A 的旧 alias。B 必须先在 recovery guard 内恢复 A，再做 identity validation 并以 typed conflict 失败。

**代码证据确认**：当前 `_recover_single_batch_dir` 对 `_PHASE_SWAPPED_TARGET` 阶段执行 backup → target 恢复。plan 在该恢复前插入 identity guard，确保恢复完成后 alias index 一致。

## read route corruption/lock typed projection 复核

plan §5.6 定义：
- `CompanyTickerIdentityCorruptionError` → read runtime 投影 `workspace_identity_corrupted`。
- `RuntimeFileLockError`（identity/publication guard）→ `storage_unavailable`。
- `None`（正常未命中）→ `NOT_FOUND`。

**代码证据确认**：当前 `_resolve_canonical_ticker`（`read_runtime.py:2301-2362`）只有 `None → NOT_FOUND` 路径。plan 在该路径前增加 typed corruption 和 lock error 投影。`fins_tools.py:1084` 已有 `FinsReadBusinessError` catch，新增的 `ErrorCode` 枚举值会正确进入 `exc.code.value`。

## Company Identity / CompanyMeta / storage owner 唯一性

### Owner 分解验证

| 语义 | Owner | 证据 |
| --- | --- | --- |
| ticker grammar / canonicalization / stable dedupe | `ticker_normalization.py` | 当前 `_US_SYMBOL_PATTERN`（line 67）只允许单字符 dot section；plan 扩展为 multi-section。`normalize_ticker` 是唯一 grammar entry。 |
| Company Identity value / builder | `ticker_normalization.py`（新增 `CompanyTickerIdentity` + `build_company_ticker_identity`） | plan §5.1 定义。所有 producer/consumer 必须调用该 builder。 |
| CompanyMeta durable state | `document_models.py::CompanyMeta`（identity value 由上节 owner 产生） | plan §5.2。`to_dict()`/`from_dict()` 只从 `ticker_identity` 投影。 |
| commit intent / authoritative merge | `company_meta_contract.py`（新增） | plan §5.3。pure function，storage 机械调用。 |
| workspace uniqueness / commit validation / alias-to-corpus route | `dayu.fins.storage` | plan §5.5–§5.6。identity guard 内 scan + validation。 |
| read projection | `read_runtime.py` + `error_contract.py` | plan §5.6。typed corruption → `workspace_identity_corrupted`。 |
| upload failure projection | `upload_failure.py` | plan §5.7。conflict → `ticker_alias_conflict`；corruption → `storage_io`。 |

**无交叉 ownership**：每个语义有唯一 owner。CLI、resolver、pipeline、tool schema 和 read runtime 只能构造或消费这些 owner 的 contract。

### 删除重复 owner 验证

plan §5.1 列出删除清单：

| 重复 helper | 当前位置 | S1/S2 删除时机 |
| --- | --- | --- |
| `_merge_ticker_aliases` | `cli/commands/fins.py` | S1 |
| `_normalize_ticker_aliases` | `pipelines/upload_company_meta.py` | S1 |
| `_canonicalize_alias_token` / `normalize_sec_ticker_aliases` | `pipelines/sec_company_meta.py` | S1 |
| `_merge_aliases` | `pipelines/cn_download_company_meta.py` | S1 |
| `_normalize_ticker_token` / `_dedupe_ticker_aliases` | `resolver/fmp_company_info.py` | S1 |
| `_canonicalize_ticker_alias` / `_normalize_company_ticker_aliases` | `storage/_fs_storage_utils.py` | S1 |

代码证据确认：这些 helper 各自实现归一化/去重逻辑（见上方代码证据表），与唯一 builder 重复。S1 删除后，所有 producer/consumer 统一调用 `build_company_ticker_identity`。

## Over-design challenge

### 挑战 1：CompanyMetaCommitIntent 是否过度设计？

**判定**：否。`CompanyMetaCommitIntent` 是解决 A1 lost-update 的最小必要 contract。prevalidation 不能产生最终 CompanyMeta（因为 commit-time current 可能已变），intent 只携带本次声明的 aliases 和 optimistic precondition。pure merge helper 让 storage 不自创 merge 语义。没有额外 abstraction layer、factory 或 registry。

### 挑战 2：workspace identity guard 是否过度设计？

**判定**：否。当前 `_build_company_alias_index_from_meta` 在 read 时扫描全部 published meta，`resolve_existing_ticker` 只在查询遇到多个 owner 时抛错——durable state 已可进入歧义状态。identity guard 是实现"冲突在 published side effect 前原子拒绝"的最小机制。复用现有 `dayu.runtime.filelock` wrapper，不新增 runtime helper。

### 挑战 3：两个 typed error（conflict vs corruption）是否过度设计？

**判定**：否。read 场景没有 incoming canonical（无法构造 `CompanyTickerAliasConflictError` 的 `incoming_canonical_ticker` 字段），commit 场景需要区分"别人占了 alias"和"published state 损坏"。两个 error 服务不同 failure mode，字段语义不同，投影路径不同。合并成一个 error 会导致 read 场景非法构造或字段语义模糊。

### 挑战 4：两 slice 是否过度拆分？

**判定**：否。S1 是 identity migration checkpoint（grammar/contract/producers/consumers 统一），S2 是 atomicity enforcement（commit validation/typed failure/read route）。合并会把 grammar/API 迁移与并发故障矩阵放进一次过大的 review pass。S1 明确不满足 goal confirmation success signal 4，不是可部署增量——plan 已修正 S1 完成语义。

### 挑战 5：不持久化 alias index 是否过度保守？

**判定**：合理。CompanyMeta 是 durable identity source；alias index 是 storage owner 在 identity guard 内的确定性 projection。当前 workspace 规模（单用户本地文件系统）和已有 inventory scan 没有性能证据要求缓存。新增第二个持久化 index 会引入双文件提交、recovery 一致性和 schema 迁移问题。

## Goal drift check

| plan element | goal confirmation mapping | drift? |
| --- | --- | --- |
| `CompanyTickerIdentity` + builder | success signal 1（grammar/去重覆盖） | 无 |
| CompanyMeta `ticker_identity` | success signal 3（durable meta 不丢失 aliases） | 无 |
| FMP/SEC/CN/CLI 删除重复 helper | success signal 2（`DELTA,MSFT` 无条件接受） | 无 |
| commit intent + authoritative merge | success signal 4（并发冲突原子拒绝） | 无 |
| storage single-token route | success signal 5（canonical/alias 命中同 corpus） | 无 |
| conflict/corruption 分型 | success signal 4（typed failure 有界可行动） | 无 |
| schema/help updates | success signal 6（LLM/用户自足理解） | 无 |
| tests/coverage/pyright/README | success signal 7/8 | 无 |

plan §14 goal alignment matrix 与以上复核一致。没有发现 goal confirmation 之外的新增目标、验收标准或架构强化。

## Residual risks

| Risk / uncovered area | Classification | Owner / destination |
| --- | --- | --- |
| 旧 workspace 歧义 alias / 旧 CompanyMeta schema | `assigned to later work unit` | fresh schema 边界；如需升级另立 migration WU |
| UF-PF05 真实 CLI evidence | `assigned to later work unit` | 用户明确排除 |
| oracle/scenario registry、冻结 evidence、其它 finding | `assigned to later work unit` | 用户明确排除 |
| CompanyMeta workspace scan 成本随公司数增长 | `assigned to later work unit` | 仅在真实 profile 超标后另立性能 WU |
| recovery 对所有 orphan tree 取 identity guard 的等待 | `assigned to later work unit` | R1 correctness 优先；只有实测 contention 后优化 |
| identity guard 文件锁成为 alias read 单点故障 | `covered by later approved slice` | S2 fail-closed 投影 `storage_unavailable`；plan §5.6 已定义 |
| NFS/网络文件系统下 filelock 行为 | `assigned to later work unit` | 当前单机本地文件系统；网络部署时需独立评估 |

没有 unclassified residual risk。

## Open questions

无。owner、public types、锁序、commit validation、failure transport、files、slices 与 tests 均已在 goal confirmation、controller adjudication 和 plan fix 中冻结。

## Final plan review conclusion

**pass**

plan fix 正确关闭了 A1–A8 全部 accepted findings。R1/R2 的 rejected reasons 在代码证据复核后仍然有效。Company Identity / CompanyMeta / storage owner 唯一性已建立，无交叉 ownership。commit intent authoritative merge 在 writer → recovery → identity → publication 锁图保护下闭合，swap-before-COMMITTED recovery 在 identity guard 前完成 orphan 恢复。read route corruption/lock typed projection 与 upload failure projection 分型一致且有界。无 goal drift，无过度设计。

plan 可以交给 implementation agent 进入 S1。next entry point：Gateflow 在当前分支创建 accepted plan local commit，自动进入 S1 implementation。
