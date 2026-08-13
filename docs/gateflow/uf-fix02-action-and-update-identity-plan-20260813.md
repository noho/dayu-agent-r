# UF-FIX02 action-and-update-identity — Code-generation-ready Plan

## 1. Gate metadata

- Work unit：`UF-FIX02 action-and-update-identity`
- Gate：`plan`
- Decision：**PLAN PASS**
- Binding scope contract：
  `docs/gateflow/uf-fix02-action-and-update-identity-goal-confirmation-20260813.md`
- Design documents：`docs/host/design.md`、`docs/engine/design.md`
- Frozen read-only registries：`docs/cli_ci_scenarios.json`、`docs/cli_ci_oracles.json`
- Branch：`codex/upload-filing-oracle`
- Baseline HEAD：`114430ce312ca6d8eb9c9f4cb7bb0a1f0bdba5a0`
- Execution policy：local-only；不 commit、不 push、不建 PR；本次 plan-review fix 不进入 re-review 或任何后续 gate。
- 本 fix gate 唯一写入：本 artifact。

## 2. Goal / motivation / success signals

### 2.1 Goal

1. filing update 只按 canonical ticker、fiscal year、normalized fiscal period 与 amended
   共同生成的稳定 filing identity 定位，不按本地 basename/stem 定位。
2. explicit `update` 在目标缺失时始终拒绝，`overwrite=True` 不得把它变为 upsert。
3. `auto` 遇到 logical deleted source 且用户提供完整输入时不得 skip；必须恢复为 active、完整且可读的 source。
4. 同一 filing 的同名或改名 update 都以 old-or-new 原子方式替换目标完整业务文件集合；新集合发布后不残留旧业务文件。
5. create-existing / update-missing 只要 fresh published state 可判定，就必须在 Docling conversion 前 fail closed；workflow
   必须丢弃 preflight 的 stale action/company decision，只使用 fresh recheck 结果。
6. 保持 UF-FIX01 已关闭的 zero-mutation、company/source single atomic batch、typed bounded stderr，以及 UF-FIX09 已关闭的
   cancellation/commit linearization contract。

### 2.2 Motivation judgment

问题真实且严重性正确。当前实现同时存在四个直接反例：

- `evaluate_upload_overwrite_precondition(...)` 只在 `overwrite=False` 时拒绝 update-missing；
- `_resolve_upsert_mode(...)` 把 `update + missing + overwrite=True` 转成 `create`；
- `_can_skip_upload(...)` 不检查 `is_deleted`，相同完整输入会对 deleted source 返回 skipped；
- `_store_upload_assets(...)` 仅在 overwrite 路径 reset，普通 changed update 会把新 blob 写入旧目录，改名时旧文件留存。

这些不是 CLI 文案问题，也不是 basename 解析问题，而是 action/precondition 与 publication owner 的语义错误。应在 Fins owner
边界修复，不应在 CLI、Service、Host、Engine、测试 fixture 或 evidence harness 增加补偿分支。

### 2.3 Success signals

- owner contract tests 先红后绿，覆盖：
  - 同名 changed update；
  - 改名 changed update；
  - update missing 在 overwrite false/true 两种模式；
  - delete 后相同完整输入执行 auto；
  - create-existing fresh conflict；
  - fresh recheck 丢弃 stale action。
- 冻结 predicate `upload_filing.action-core`、`upload_filing.renamed-update`、
  `upload_filing.auto-after-delete` 的当前 WU 范围行为通过。
- UF-PF02 使用真实 `.venv/bin/dayu-cli`、真实 production runtime/storage/Docling converter；无 mock、fake、monkeypatch、
  fault injection 或测试专用 hook。
- 受影响测试全部通过；每个修改生产文件 coverage `>=80%`；完整 pyright 无新增或扩散错误。
- README trigger、diff/static audit、registry/frozen evidence no-touch audit 全部通过。

## 3. Non-goals / scope boundary

### 3.1 明确不做

- 不处理 UF-FIX03–UF-FIX08、UF-FIX10、UF-FIX11、UF-PF03–UF-PF12。
- 不修改 summary/count、date/calendar/year、ticker alias、format/XBRL、multi-file primary/collision、existing-source
  integrity auto repair、same-request concurrency、fresh company name/alias warning。
- 除下述 shared Docling owner 的有意一致性效果外，不改变 delete-with-files、delete-never-existed、重复 action/ticker、amended
  identity 之外的既有行为：filing/material 共用的 action、skip 与 publication owner 同步拒绝 update-missing upsert、禁止
  deleted auto skip，并对 existing full-input update 做完整替换。
- 不新增 action enum、跨层 identity registry、storage compatibility schema、补偿删除、自动重试、字符串异常分类、
  compat shim、lazy import、下游 fallback 或 basename/stem identity 分支。
- 不修改 CLI 参数、Service public signature、Host/Engine contract、tool schema、LLM-facing prompt 或 schema。
- 不刷新 `docs/cli_ci_scenarios.json`、`docs/cli_ci_oracles.json`，不重写第一轮 observed evidence，不在本 WU 登记或执行
  post-fix conformance refresh。`UF-A08-update-missing-overwrite-creates` 是 intentionally stale observed evidence：它记录修复前事实，
  不是 correctness contract；本 WU 实施后也不修改其 status。该状态更新唯一归属后续统一 conformance refresh，由该 owner 一次性
  重跑场景、更新 observed status/evidence，并保持现有 oracle predicate 不变。
- material 只接受 shared owner 的一致性效果与最小 owner parity tests；不新增 material typed usage/public error projection，不修改
  CLI/Service/SEC/CN/HK material workflow 生产代码，也不把 material 扩入 UF-PF02 focused-real。

### 3.2 最小性与 goal drift 判断

本方案只修两个现有 shared Docling owner：filing/material 共用的 action/precondition/skip owner，以及既有 source reset + atomic
batch publication owner。logical
deleted 与 active source 对 `auto` 都解析为 `update`，差异只在“deleted 不允许 skip”；因此不新增 `restore` action 或第二套
published-state enum。完整输入 update 的正确写入语义可直接复用现有 `reset_source_document(...)` 与同一 batch 中的完整 create，
无需新增仓储协议。material parity 只在该共同 owner 边界固定同形输入的同形结果，不引入 material 专用分支、typed usage 面或
workflow 改造。CLI/Service/Host/Engine 当前边界已正确，不因下游可见问题扩大修改范围。

## 4. Owner adjudication and direct evidence

| 语义 | 唯一 owner / 真源 | 直接代码证据 | 本 WU 决策 |
| --- | --- | --- | --- |
| filing identity | `dayu.fins.ingestion_runtime._validate_fins_upload_filing_static` + `build_sec_filing_ids` / `build_cn_filing_ids` | `ValidatedFinsUploadFilingRequest.document_id/internal_document_id` 在文件读取和 Service handoff 前产生；ID builder 不接收 basename/stem | 保持 owner；用同名/改名 request tests 固定 identity 不变 |
| published existence/deleted canonical data | `FilingUploadStateRepositoryProtocol.read_filing_upload_state(ticker, document_id)` 与 source meta 的 `is_deleted` | `_FsFilingUploadStateMixin` 在同一 publication guard 下按 exact document id 读取 source meta；delete owner 写入 `is_deleted=True` | 不新增第二真源；action/skip 只消费 fresh source meta |
| action resolution | `docling_upload_service.resolve_upload_action` + `evaluate_upload_overwrite_precondition`，由 filing/material 共用的 `DoclingUploadService` 调用 | auto 当前按 source presence 解析；validator、shared service 与 filing workflow fresh recheck 复用同一 helper | update-missing 与 overwrite 解耦；deleted 仍解析 update但不得 skip；同形 material owner 输入有意得到同形结果，不新增 material 专用规则 |
| 完整文件集合替换 | filing/material 共用的 `DoclingUploadService._store_upload_assets` + `SourceDocumentRepositoryProtocol.reset_source_document` + caller-owned batch | 当前 reset 只在 overwrite；blob-first 与 final source mutation 已在一个 batch 内 | 任何 existing create-overwrite/update 都 reset target 后完整 create；filing/material 共享效果，不逐文件补偿删除 |
| fresh authoritative decision | SEC `run_upload_filing_stream`、CN/HK `CnPipeline.upload_filing_stream` | 两条 workflow 都重新 read state、重新 validate、核对 stable identity，并使用 authoritative request | 保持生产路径；补测试固定 stale decision 被丢弃和 conflict pre-conversion |
| CLI / Service | `dayu.cli.commands.fins`、`dayu.service.fins_direct` | CLI 构造一次 validated typed request；Service 原样传给 runtime | 不修改，只由既有 boundary tests 与 UF-PF02 回归 |
| Host / Engine | `docs/host/design.md`、`docs/engine/design.md` | Host 不承载财报业务语义，Engine 不访问财报仓储 | 明确 no-touch |

冻结 registry 直接证据：

- `UF-FIX02` accepted requirement 明确为 filing identity update、update-missing 即使 overwrite 也失败、deleted 后 auto 恢复、
  existing conflict 转换前判断。
- `UF-PF02` required observation 精确为“同名/改名 update、update missing±overwrite、deleted 后 auto、existing
  pre-conversion conflict”。
- `UF-A08-update-missing-overwrite-creates` 只是在 frozen scenario 中保存的修复前 observed evidence；它将在本 WU 后 intentionally
  stale。本 WU 只以 `upload_filing.action-core` oracle predicate 判定正确性，绝不修改 registry/evidence；其 status/evidence 更新由
  后续统一 conformance refresh owner 负责。
- 只读基线 SHA-256：
  - `docs/cli_ci_scenarios.json`：`a357e5a1e0ee11cb42f8ab6e25083b23761a4c8181d14ddc1876f0bf9a788efb`
  - `docs/cli_ci_oracles.json`：`88b04ca47472f320b614ad1374a9f0a243443efaca1e0565eaf29b5f0cb770b8`

## 5. Contract and state-machine decisions

### 5.1 Action/admission matrix

`source` 的 `missing/active/deleted` 全部来自同一次 published-state read；`overwrite` 只控制 create-existing 是否允许和
active identical input 是否强制重建，不拥有 upsert 权限。

| requested action | missing | active | deleted |
| --- | --- | --- | --- |
| `auto` | resolve `create` | resolve `update` | resolve `update`，且禁止 skip |
| `create`, overwrite false | allowed | `CREATE_TARGET_EXISTS` | `CREATE_TARGET_EXISTS` |
| `create`, overwrite true | allowed | allowed，完整替换 | allowed，完整替换并恢复 active |
| `update`, overwrite false | `UPDATE_TARGET_MISSING` | allowed | allowed并恢复 active |
| `update`, overwrite true | `UPDATE_TARGET_MISSING` | allowed且强制完整替换 | allowed且完整替换并恢复 active |
| `delete` | 保持既有行为 | 保持既有 logical delete | 保持既有幂等 delete |

关键不变量：

- explicit update 的存在性前置条件不读取 overwrite；overwrite 不能改变 action identity。
- `source_meta is not None` 表示 identity 已发布；`is_deleted is True` 表示 logical deleted，不等于 missing。
- skip 只允许 `active + !overwrite + non-empty equal source_fingerprint`。
- source meta 缺失/损坏不在下游猜默认；既有 storage read/validation failure 继续 fail closed。

### 5.2 Publication transition

完整输入需要写入时：

```text
authoritative active/deleted target
  -> Docling conversion completes outside writer batch
  -> final cancellation check
  -> begin one ticker batch
  -> stage company decision in same batch
  -> reset exact (ticker, filing document_id) source tree in staging
  -> store every new original + Docling blob
  -> create one complete source meta/manifest with is_deleted=False
     -> on any store/create failure: discard/rollback whole batch
        -> published old state remains byte-for-byte unchanged
  -> final cancellation checkpoint
     -> on precommit cancellation: discard/rollback whole batch
        -> published old state remains byte-for-byte unchanged
  -> commit batch (old-or-new publication)
```

目标 missing 且 action=create 时跳过 reset，直接在同一 batch create。`reset` 后必须走 create；不得保留
`_resolve_upsert_mode` 的 missing-update→create 分支，也不得 reset 后调用 update。reset 仅作用于 exact filing identity，不清空 ticker、
其它 filing 或 processed tree。任何 reset 后的 store/create failure 与 precommit cancellation 都必须让 caller-owned batch 走既有
discard/rollback，禁止提交半成品或另起补偿 batch；已发布 old source/meta/manifest/company state 保持不变。

`previous_meta` 在 reset 前由 caller 持有，是 version 与 `first_ingested_at` 派生的唯一真源；reset 只清 staging identity tree，
不得清空、重读或以 reset 后 missing 状态替代该引用。final create 继续用同一个 `previous_meta` 解析 version，并在同一 filing/material
identity 的改名 update 与 deleted restore 中保持原始 `first_ingested_at`；changed fingerprint 按既有规则递增 version，不得回退到
`v1`。

### 5.3 Observable state transitions

| Before | Request | Result | After |
| --- | --- | --- | --- |
| missing | auto/create + full input | uploaded/create | active complete source, `v1` |
| active, equal fingerprint | auto/update, overwrite false | skipped | bytes/meta/revision 不变 |
| active, changed same basename | auto/update | uploaded/update | exact new complete set；旧 bytes 不可见；version 按 `previous_meta` 递增 |
| active, changed renamed basename | auto/update | uploaded/update | exact new names；旧 original/Docling names 不存在；`first_ingested_at` 保持 |
| deleted, equal or changed full input | auto/update | uploaded/update | active；`is_deleted=False`、`deleted_at=None`、integrity complete；version 不回退且 `first_ingested_at` 保持 |
| missing | explicit update ± overwrite | typed usage failure | zero conversion、zero workspace mutation |
| active/deleted | explicit create, overwrite false | typed usage failure | zero conversion、published tree 不变 |
| stale preflight | raw request + fresh state changed | fresh validator outcome | stale action/company decision 不进入 prepare/stage |

### 5.4 Error/public text contract

- `FinsUploadUsageCode.UPDATE_TARGET_MISSING` 保持 code 不变。
- 唯一用户文案改为 `update 目标不存在；请改用 create`；删除“或允许覆盖”，因为 overwrite 不再允许 upsert。
- CLI 继续机械投影 owner failure：exit `2`、stdout empty、单行 bounded stderr、无 traceback/path。
- create-existing 文案保持 `create 目标已存在；请改用 update 或允许覆盖`。

## 6. Exact affected files and symbols

### 6.1 Production files

1. `dayu/fins/pipelines/docling_upload_service.py`
   - `evaluate_upload_overwrite_precondition(...)`
     - update missing 无条件返回 `UPDATE_TARGET_MISSING`；overwrite 只影响 create-existing。
   - `DoclingUploadService.prepare_upload(...)`
     - 保持文件 validation/precondition/cancellation 次序；使用 corrected precondition；deleted equal input 不走 skip。
   - `DoclingUploadService._store_upload_assets(...)`
     - existing create-overwrite/update 一律在当前 batch reset exact source；随后写完整 blob set 并 final create。
   - `DoclingUploadService._upsert_source_document(...)`
     - 收敛为与新语义一致的 create-only final mutation helper并改名；删除无可达 update 分支，避免 dead semantic branch。
   - `_can_skip_upload(...)`
     - 只接受 active source；logical deleted 必须返回 false。
   - `_resolve_upsert_mode(...)`
     - 删除；不得保留 update-missing→create 或 reset 后 update 的第二套决策。
   - `resolve_upload_action(...)`
     - 保持 presence-based auto：deleted source 仍是 published target并解析 update；测试固定这一语义。

2. `dayu/fins/ingestion_runtime.py`
   - `_USAGE_MESSAGES[FinsUploadUsageCode.UPDATE_TARGET_MISSING]`
     - 删除错误的 overwrite 建议；code、异常类型、投影边界不变。
   - `validate_fins_upload_filing_request(...)`
     - 不复制 action 规则；继续消费 corrected owner disposition。

### 6.2 Test files

1. `tests/fins/test_fins_ingestion_runtime.py`
   - 扩充 pure validator action/admission matrix与 stable identity assertions。
2. `tests/fins/test_docling_upload_service.py`
   - owner-level conversion-before-publication、deleted skip、same/renamed full replacement、rollback/cancellation assertions；S1/S2 各一个
     filing/material shared-owner 最小 parity test；删除 `_resolve_upsert_mode` import 与错误 upsert pin，以 public owner matrix 取代。
3. `tests/fins/test_sec_pipeline_upload_filing_stream.py`
   - SEC authoritative fresh recheck、renamed update、delete→auto integration。
4. `tests/fins/test_cn_pipeline.py`
   - CN/HK 路径的同形 fresh recheck 与 update/restore parity。
5. `tests/cli/test_fins_commands.py`
   - typed state-conflict 到 exit/stderr/Service-not-called/zero-mutation 的 CLI boundary regression。

不新增 fake helper 文件；优先复用现有 `_FakeDoclingConverter`、tracking repository 与
`tests/fins/upload_filing_test_support.py`，但不修改该 support 文件。测试 double 只用于 deterministic owner tests，不进入
UF-PF02。

### 6.3 README files

1. `dayu/fins/README.md`
   - 更新 upload current contract：update missing 与 overwrite 解耦；logical deleted 不可 skip；完整输入 update 以 exact target
     reset→complete create 原子替换；fresh recheck 仍是 authoritative owner；说明 filing/material 共用 Docling owner 的一致性效果，
     不宣称新增 material typed usage 或 focused-real coverage。
2. `tests/README.md`
   - 记录现有测试能力：action matrix、renamed complete replacement、deleted restore、fresh pre-conversion conflict。
3. `README.md`
   - 在最终用户 upload action 说明中明确 update 必须已有目标，overwrite 不提供 upsert；auto 可恢复 logical deleted source；
     update 发布完整替换同一 filing 文件集合。

### 6.4 Explicit no-touch files/modules

- `dayu/cli/**`、`dayu/service/**`：typed handoff 已正确，不改生产代码。
- `dayu/fins/storage/**`：既有 exact-document reset、batch与 public read/integrity contract 足够，不新增协议。
- SEC/CN/HK workflow 生产文件（包括 material path）：fresh recheck/共享调用已正确，不为测试重写、复制规则或新增 material typed
  usage/public error projection。
- `dayu/host/**`、`dayu/engine/**`、`dayu/runtime/**`、`dayu/config/**`。
- `docs/host/design.md`、`docs/engine/design.md`、两个 frozen registry及全部既有 evidence。

## 7. Implementation slices

共 **2 个** slice，按可独立验证的行为增量切分，不按文件机械拆分。两者不能合并为一个 review unit：S1 改 action admission
和 no-op 决策，S2 改 mutation/publication 语义；分开可在 S2 前先证明所有可预判冲突仍为 zero conversion/zero mutation。

### S1 — Action admission and logical-deleted no-skip

- Objective：让 explicit action、overwrite、published existence/deletion 形成唯一 closed decision。
- Prerequisite：UF-FIX01 closeout 与当前 baseline。
- Tests first：
  1. 在 `test_fins_ingestion_runtime.py` 新增 parameterized matrix：update missing × overwrite false/true 均得到
     `UPDATE_TARGET_MISSING`；create existing false 冲突、true 允许；auto deleted 解析 update且 identity 不随文件名变化。
  2. 在 `test_docling_upload_service.py` 新增 converter call recorder：update missing ± overwrite 与 create-existing false 均在
     converter call 前失败；deleted + equal fingerprint 不得 skipped，必须进入 conversion；另加一个最小 material parity owner test，
     证明 material update-missing 在 overwrite false/true 下同样于 converter 前失败且 converter call count 为 `0`，不测试或新增
     material workflow/public typed projection。
  3. 在 `test_fins_commands.py` 以真实 published state + forbidden Service factory 断言 update-missing 两种 overwrite 与
     create-existing conflict 均 exit `2`、stdout empty、exact bounded stderr、workspace/business tree不变。
- Production change：只修改 §6.1 两个文件中 admission/skip/message 符号；不开始 full-set reset 改造。
- Expected outcome：所有 pre-conversion conflict 与 deleted no-skip tests 通过；existing active changed update 仍由 S2 完成。
- Focused validation：
  `pytest tests/fins/test_fins_ingestion_runtime.py tests/fins/test_docling_upload_service.py tests/cli/test_fins_commands.py -q`
- Stop condition：若 logical deletion 无法从 fresh `source_meta` 得到确定 bool、或 CLI prevalidation 与 workflow fresh state 不同源，
  立即停止并重新澄清 owner；不得用默认值或 downstream fallback。
- Non-goals：不改变 publication mutation、文件集合、并发、integrity repair或 summary；不新增 material typed usage、workflow
  生产改动或 focused-real case。

### S2 — Complete-set replacement, restore, and cross-market propagation

- Objective：让所有 existing full-input update 使用 exact target 的 atomic complete replacement，并证明 fresh decision 跨 SEC/CN/HK
  正确传播。
- Prerequisite：S1 accepted；其 action matrix不可在 S2 重定义。
- Tests first：
  1. `test_docling_upload_service.py`
     - same basename changed update：新 bytes/meta/manifest 同源、版本递增、文件集合精确；
     - renamed update without overwrite：仅存在新 original + 新 Docling 文件，旧两项消失；version 按 reset 前 `previous_meta` 派生，
       `first_ingested_at` 等于初次 create 的值且不被本次 `updated_at` 替代；
     - delete→auto/update equal input：不得 skip，最终 `is_deleted=False`、`deleted_at=None`、integrity complete；version 不回退，
       `first_ingested_at` 等于 logical delete 前的初次 create 值；
     - 一个最小 material publication parity owner test：deleted + equal full input 的 auto 不得 skip，成功后 active、完整且
       `first_ingested_at` 保持；不进入 material workflow 或 focused-real；
     - reset 后任一 blob store/final create failure，或 final checkpoint/precommit cancellation：whole batch 被 discard/rollback，
       published old source/meta/manifest/company tree SHA 仍等于 old。
  2. `test_sec_pipeline_upload_filing_stream.py`
     - 把 renamed update 的成功条件固定为不依赖 overwrite；document id 与 create 相同；
     - fresh preflight auto=create 被已发布状态改写为 update（保留现有 stale-action test）；
     - fresh explicit create-existing 在 converter 前抛 typed usage，zero new batch/mutation；
     - delete 后 auto 产生 uploaded/update，不是 skipped，public repository active。
  3. `test_cn_pipeline.py`
     - 保留/强化 CN fresh stale-action test；
     - 构造 preflight 时存在、fresh 时 missing 的 explicit update，parameterize overwrite false/true，均在 converter 前失败；
     - 至少一个 changed update 或 delete→auto case证明 CN/HK facade 与 SEC 共享相同 owner，而非各自复制规则。
- Production change：
  - `_store_upload_assets` 对任一 existing create-overwrite/update 执行 reset；
  - reset 后完整 blob-first + final create；
  - 删除 `_resolve_upsert_mode`，收敛 final helper 为 create-only。
- Test migration：从 `test_docling_upload_service.py` 删除 `_resolve_upsert_mode` import 与
  `assert _resolve_upsert_mode("update", None, True) == "create"` 错误 upsert pin；不得保留 compat shim。由 S1 action/admission owner
  matrix 与 S2 complete-replacement owner matrix取代该 internal helper 断言。完成后运行
  `rg -n '_resolve_upsert_mode' --glob '*.py' .`，要求全仓生产/测试 Python 源码零命中；plan/review 历史 artifact 仍需原样引用被删除
  符号，不属于实现源码审计域。
- Expected outcome：同名/改名 update 与 deleted restore全部 old-or-new；失败/取消保留 old；非目标 filing不变。
- Focused validation：
  `pytest tests/fins/test_docling_upload_service.py tests/fins/test_sec_pipeline_upload_filing_stream.py tests/fins/test_cn_pipeline.py -q`
- Stop condition：若现有 reset 无法在同一个 caller-owned batch 中保持 exact-target old-or-new，立即停止；不得改成 commit 后补偿删除或
  跨 batch copy/delete。
- Non-goals：不实现同请求 lock 内 second recheck（UF-FIX10）、integrity repair（UF-FIX08）或多文件 collision/primary（UF-FIX07）。

## 8. Tests and validation matrix

| Contract | Owner test | Integration / boundary | Expected assertion |
| --- | --- | --- | --- |
| stable filing identity | `test_fins_ingestion_runtime.py` | SEC/CN upload tests | 同 fiscal identity 的同名/改名 request 得到 exact same document IDs |
| update missing ± overwrite | validator + filing/material shared service parameterized tests | CLI + SEC/CN filing fresh conflict tests | typed `UPDATE_TARGET_MISSING`；converter 0 calls；batch 0；exit 2；material 只做 owner parity |
| create existing pre-conversion | validator/service test | CLI/SEC workflow | typed `CREATE_TARGET_EXISTS`；converter 0 calls；published SHA不变 |
| deleted no-skip | service owner test | SEC/CN delete→auto | status uploaded/update；`is_deleted=False`；非 skipped |
| same-name update | service real FS test | UF-PF02 | 新 bytes/digest/meta；完整集合精确 |
| renamed update | service real FS test | SEC workflow + UF-PF02 | document id不变；旧 original/Docling文件不存在；version 由 reset 前 meta 派生且 `first_ingested_at` 保持 |
| material shared-owner parity | S1 update-missing + S2 deleted restore 两个最小 service tests | 不进入 workflow/focused-real | action/skip/publication 与 filing 同形；active complete；`first_ingested_at` 保持 |
| stale action discard | 现有 SEC/CN fresh tests + explicit conflict增量 | workflow | authoritative action/state/company decision驱动 prepare；stale值零消费 |
| atomic batch | existing failure/cancel tests + reset 后 store/create/precommit cancel assertions | UF-PF02 before/after | whole batch discard/rollback；published old state不变；成功只见完整new |
| bounded stderr / zero mutation | CLI tests | UF-PF02 | exit 2、stdout empty、single bounded stderr、无新 workspace business state |
| cancellation | existing Docling/batch cancellation suites | affected regression | terminal/rollback/commit linearization不变 |

### 8.1 Slice-local commands

```bash
source .venv/bin/activate
pytest tests/fins/test_fins_ingestion_runtime.py \
  tests/fins/test_docling_upload_service.py \
  tests/fins/test_sec_pipeline_upload_filing_stream.py \
  tests/fins/test_cn_pipeline.py \
  tests/cli/test_fins_commands.py -q
```

### 8.2 UF-FIX01 / atomicity / cancellation regressions

```bash
source .venv/bin/activate
pytest tests/fins/test_fins_storage_atomicity.py \
  tests/fins/test_fins_storage_provider.py \
  tests/fins/test_docling_process_converter.py \
  tests/fins/test_fins_service_runtime.py \
  tests/service/test_fins_direct.py \
  tests/cli/test_import_boundary.py -q
```

### 8.3 Per-production-file coverage

使用独立临时 coverage data file，避免把验证产物写入 repo：

```bash
source .venv/bin/activate
UF_FIX02_COVERAGE_DIR="$(mktemp -d)"
export COVERAGE_FILE="$UF_FIX02_COVERAGE_DIR/coverage"
coverage run -m pytest \
  tests/fins/test_fins_ingestion_runtime.py \
  tests/fins/test_docling_upload_service.py \
  tests/fins/test_sec_pipeline_upload_filing_stream.py \
  tests/fins/test_cn_pipeline.py \
  tests/cli/test_fins_commands.py -q
coverage report \
  --include='dayu/fins/pipelines/docling_upload_service.py,dayu/fins/ingestion_runtime.py' \
  --fail-under=80
```

实现时须逐文件读取 report；aggregate `>=80%` 不能替代以下两项各自 `>=80%`：

- `dayu/fins/pipelines/docling_upload_service.py`
- `dayu/fins/ingestion_runtime.py`

### 8.4 Full type check

```bash
source .venv/bin/activate
python -m pyright dayu/ tests/ utils/
```

预期：完整 pyright exit `0`；不得用 ignore、cast bag、`Any/object`、`hasattr/getattr` 或弱类型 payload 掩盖新错误。

## 9. UF-PF02 focused-real evidence

### 9.1 Execution boundary

- 在 implementation + slice reviews 通过后创建独立 root：
  `/Users/leo/workspace/.dayu-cli-ci/uf-pf02-focused-real-20260813-<unique>/`。
- 不复用 UF-PF01 root、第一轮 calibration workspace、frozen reports 或 registry observed evidence。
- 所有业务动作通过当前 worktree 的真实 `.venv/bin/dayu-cli` subprocess执行；真实 `DefaultFinsRuntime`、filesystem storage 与
  Docling converter；不设置 pytest/fake/fault-injection环境，不 import 测试包。
- observation 可以用 `.venv/bin/python -c` 只读调用 `dayu.fins.storage` public repository；不得私读 storage path来替代 public
  repository结论。

### 9.2 Real command sequences

每步 argv 都保存为逐 token JSON；以下 `$ROOT`、`$BASE_*`、`$INPUT_*` 在 manifest 中绑定 canonical path 和 SHA-256。

#### A. Same-name and renamed update (`$BASE_UPDATE`, ticker `ACTN`)

1. auto fresh create：`report.txt` v1，FY 2024，company `Action Corp.`；预期 create/uploaded。
2. auto same-name changed update：另一目录下同 basename `report.txt` v2；预期 same document id、update/uploaded，内容 digest变更，
   文件集合仍精确为 `report.txt` + `report_docling.json`。
3. explicit renamed update without overwrite：`renamed-report.txt` v3；预期 same document id、update/uploaded，文件集合精确为
   `renamed-report.txt` + `renamed-report_docling.json`，旧两个名字不存在。
4. identical auto replay：再次提交 v3；预期 update/skipped、repository revision/tree digest不变。
5. explicit create-existing without overwrite：提交完整 v4；预期 exit `2`、`CREATE_TARGET_EXISTS` 对应单行文案、无 conversion-start
   log、filesystem/public repository/integrity 与 step 4 完全相同。

#### B. Update missing (`$BASE_MISSING`, ticker `MISS`)

1. explicit update without overwrite，完整 `missing.txt`；预期 exit `2`。
2. exact same request 加 `--overwrite`；预期仍 exit `2`，stderr 精确为
   `dayu-cli upload_filing: update 目标不存在；请改用 create\n`。
3. 两步均要求 workspace business/durable state zero mutation、无 conversion-start log、public repository target missing。

#### C. Auto after logical delete (`$BASE_DELETE`, ticker `DELR`)

1. auto fresh create `restore.txt`；预期 active完整 source。
2. explicit delete 同一 fiscal identity；预期 logical deleted，public state `is_deleted=True`。
3. 用与 step 1 相同完整输入执行 auto；预期 update/uploaded而非 skipped。
4. public repository 重读：same document id、`is_deleted=False`、`deleted_at=None`、完整文件集合、integrity `complete`。

### 9.3 Required observations per step

每个 step 独立保存：

- `argv.json`：exact tokens、cwd、HEAD、Python、resolved CLI executable/package version、相关输入 SHA-256；
- `stdout.txt`、`stderr.txt`、`screen.txt`、`result.json`：分离 exact bytes、合并 screen transcript、exit、duration、timeout；
- `log.txt` 与 bounded `log-observation.json`：conversion 是否开始、typed terminal、无 traceback/secret/path leak；
- `files-before.json`、`files-after.json`、`files-diff.json`：相对 path/type/mode/size/SHA-256，列 created/modified/deleted；
- `public-repository-before.json`、`public-repository-after.json`：通过 public repository读取 exact document id、source meta 的必要
  action/deletion/version/fingerprint字段、文件名/size/SHA-256、非目标 filing inventory；不发布 local URI；
- `integrity-before.json`、`integrity-after.json`：`classify_source_integrity(...)` 的 status/reasons/revision presence；
- `db-observation.json`：扫描 CI-owned base/run root 中 `.sqlite/.sqlite3/.db` 及 `-wal/-shm`，记录 queried-absent；direct
  upload不得创建 Host/runtime SQLite；
- `trace-observation.json`：扫描 CI-owned workspace/run root 的 Tool Trace入口，记录 queried-absent / not-applicable proof；direct
  upload不创建 Host Run/Attempt/EventLog/Memory/Tool Trace；
- `sha256sums.txt`：上述 raw evidence exact-byte digests。

`screen.txt` 对非交互 direct command 是 stdout/stderr 按时间顺序的真实终端投影，不得用人工总结代替。DB/Trace absent 是设计上的
not-applicable proof，不得伪造空 DB/Trace 文件来满足清单。

### 9.4 Bundle publication and integrity

最终 root 至少包含：

- `manifest.json`：run id、target HEAD、scope=`UF-PF02`、case/step graph、exact artifact refs、mock/fake absence proof、
  frozen registry digest refs；
- `report.md`：逐行为内嵌 bounded screen/streams/file diff/public repository/integrity/DB/Trace事实，primary verdict只能是
  `focused-real-pass` 或证据支持的更高优先级 failure；不得宣称 full-real；
- `digests.json`：manifest/report/step evidence exact-byte SHA-256 与确定性 bundle digest basis；
- `secret-scan.json`：最后独占创建，复用 tracked
  `utils.cli_ci_run_observation.write_final_publication_scan_report(...)`，扫描完整 public evidence tree与 path hygiene；
- `completion.json`：planned/executed/pass/fail/not-run counts、artifact完整率、integrity failures、最终 verdict。

secret scan 前 report/manifest/digests/completion 必须已终态；scan report 不覆盖、不二次生成。API key、credential、authorization、
cookie、用户目录绝对路径不得进入 distributable evidence。若发现真实 secret，只记录类型、owner位置、hit count与受限 raw identity，
不复制值，并将 verdict 升级为 fail/blocked，不得删除证据掩盖事实。

### 9.5 UF-PF02 pass conditions

- A/B/C 全部 executed，无 blocked/not-run/limited-signal。
- 同名/改名 update、missing ± overwrite、deleted auto、create-existing conflict均满足 §5。
- 所有成功 active source integrity=`complete`；rejected steps old state/zero state不变。
- screen/stdout/stderr/files/logs/DB/Trace/public repository/integrity 八类 observation全部 present或有合法 not-applicable proof。
- manifest/report/digests/completion/secret scan完整，digest验证 0 failure，secret/path hygiene 0 hit。
- 只报告 UF-PF02 focused范围，不更新 registry，不覆盖 frozen evidence。

## 10. README trigger decision

| Trigger | Decision | Reason |
| --- | --- | --- |
| `dayu/fins/` production change | 更新 `dayu/fins/README.md` | action/deleted/full replacement current contract改变且属于 Fins开发者边界 |
| `tests/` change | 更新 `tests/README.md` | owner/state-machine coverage发生实质扩展 |
| 用户可见 action/error/workflow | 更新根 `README.md` | update+overwrite行为、auto deleted恢复与文件集合替换是最终用户语义 |
| Service change | 不触发 | Service生产代码不改；typed handoff已记录 |
| 分层/装配变化 | `dayu/README.md` 不更新 | Fins位置与 UI→Service→Host→Engine不变 |
| Host/Engine | README/design均不更新 | no-touch |
| config/prompt/schema | 不更新 | 无变化 |

README 只能在对应生产行为实现并验证后更新；不得在 README 中写 plan、测试清单、future work 或内部文件流水账。

## 11. Diff and static audit

实现完成后执行：

```bash
git diff --check
git diff --exit-code -- docs/cli_ci_scenarios.json docs/cli_ci_oracles.json \
  docs/host/design.md docs/engine/design.md
git status --short
git diff --name-only
```

允许的 repo changed paths 仅限 §6.1–§6.3 与本 Gateflow WU 后续获授权 artifacts；出现其它 path 立即停止，不自动丢弃。

人工 + `rg` static audit：

- 无新增 `hasattr/getattr`、`Any/object`、裸 dict公共签名、lazy import、compat re-export/wrapper；
- 无 basename/stem filing identity、字符串异常分类、`str(exc)` public projection、默认 deleted state、下游 fallback；
- 无 commit 后补偿删除、跨 batch replacement、ticker级清空；
- 无 CLI/Service duplicated action rule、Host/Engine/Fins反向依赖；
- 无 registry/evidence refresh、UF-FIX03–08/10/11 或 UF-PF03–12内容；
- `UF-A08` 只被标注为 intentionally stale observed evidence；本 WU 无 registry/evidence/status 写入，后续统一 conformance refresh
  是唯一状态更新 owner；
- `rg -n '_resolve_upsert_mode' --glob '*.py' .` 在全仓生产/测试 Python 源码零命中；不得用 compat shim 保留旧 import/assertion；
- material 变化仅来自 filing/material shared Docling owner，并只有 S1/S2 两个最小 owner parity tests；无 material typed usage、workflow
  生产代码或 UF-PF02 focused-real 扩面；
- 所有新增/修改函数保留完整中文 docstring（参数、返回、异常），复杂 reset→create 意图有中文注释。

## 12. Risks / residuals / open questions

| Risk / uncovered area | Classification / destination | Current handling |
| --- | --- | --- |
| prevalidation/fresh recheck 后到 batch publication 前的同请求竞争 | assigned to later work unit `UF-FIX10 same-request-concurrency` | 本 WU 不在 lock 内新增 second recheck，不改变既有 atomic batch fail-closed |
| existing source corruption + auto repair | assigned to `UF-FIX08 existing-source-auto-repair` | 本 WU 只处理合法 logical deleted state，不把 corruption当 deleted/missing |
| multi-file basename/stem collision和 primary | assigned to `UF-FIX07` | 本 WU 仅证明无 collision 的完整集合替换 |
| format/XBRL companion capability | assigned to `UF-FIX06` | UF-PF02 使用当前已支持 TXT，不扩格式声明 |
| summary/stored counts和 broader bounded errors | assigned to `UF-FIX03` | 只修 UPDATE_TARGET_MISSING 的错误行动建议 |
| fresh company name/alias ignored warning | assigned to `UF-FIX11` | 保持现有 company decision，不扩 warning |
| full upload_filing conformance | assigned to existing `UF-PF12` | UF-PF02 只给 focused verdict |
| `UF-A08` frozen observed evidence 与修复后行为不一致 | assigned to later unified conformance refresh | intentionally stale；本 WU 不改 registry/evidence/status，后续 owner 统一重跑并更新状态 |
| material broader public typed error projection / full-real coverage | assigned to `UF-PF12` 或后续明确 work unit | 本 WU 只固定 shared owner parity，不改 material workflow/typed usage，不扩 UF-PF02 |
| real converter runtime cost/机器差异 | covered by UF-PF02 bounded timeout与完整 raw evidence | 外部运行失败必须如实 classified，不能用 fake替代 |

Blocking open questions：**无**。若实现时发现 source meta 无法确定 logical deletion、reset 不具备 same-batch old-or-new、或 fresh
workflow 实际绕过 authoritative request，则 owner/contract发生变化，必须停止并回到 goal confirmation；不得局部补偿。

## 13. Completion report format

后续 implementation/final validation完成时报告必须包含：

1. `PASS` 或 `BLOCKED`，对应 Gateflow gate与 slice id；
2. changed files / exact symbols；
3. 每个 owner contract的 before/after行为与 state transition；
4. tests-first红灯证据、修复后 focused/regression test结果；
5. 每个修改生产文件 coverage百分比；
6. 完整 pyright结果；
7. README trigger与实际更新；
8. UF-PF02 evidence root、manifest/report/digest/secret scan identity与八类 observation状态；
9. diff/static audit与 frozen registry no-touch结果；
10. residual risks按 §12分类；
11. `git status --short` 与 local-only/no commit/no push/no PR确认。

## 14. Plan gate closeout

- Plan status：**PLAN PASS**
- Suggested implementation slices：`2`（S1 action/deleted admission；S2 complete replacement/cross-market propagation）
- Direct evidence：§4
- Validation matrix：§8 + §9
- Risks / uncovered areas：§12，全部已有 destination，无未分类 residual risk
- Plan-review fix status：**FIX PASS**（仅表示本 artifact 已按 Controller accepted findings 修订，不代替 re-review 裁决）。
- Next possible Gateflow entry：`re-review`，但本任务明确禁止进入；本 fix gate 在此停止。
