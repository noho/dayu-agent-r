# UF-FIX11 company-metadata-ignored-change-warning 实施计划

## 0. Gate 元数据

- Work unit：`UF-FIX11 company-metadata-ignored-change-warning`
- 当前 gate：S3 projection boundary plan review-fix
- 日期：2026-08-17
- 分支：`codex/upload-filing-oracle`
- Goal 状态：用户已确认；本计划不重新打开 goal confirmation
- plan review artifacts：
  - `docs/reviews/plan-review-20260817-090453.md`
  - `docs/reviews/plan-review-20260817-091441.md`
- controller 裁决：`docs/gateflow/uf-fix11-plan-review-adjudication-20260817.md`
- fix artifact：`docs/gateflow/uf-fix11-plan-review-fix-20260817.md`
- re-review artifacts：
  - `docs/reviews/plan-rereview-ds-20260817.md`
  - `docs/reviews/plan-rereview-mimo-20260817.md`
  - `docs/reviews/plan-rereview-final-ds-20260817.md`
  - `docs/reviews/plan-rereview-final-mimo-20260817.md`
- re-review fix2 artifact：`docs/gateflow/uf-fix11-plan-rereview-fix2-20260817.md`
- controller acceptance：`docs/gateflow/uf-fix11-plan-acceptance-20260817.md`
- slice-boundary blocker：`docs/gateflow/uf-fix11-s1-slice-boundary-blocker-20260817.md`
- plan amendment：`docs/gateflow/uf-fix11-slice-boundary-amendment-20260817.md`
- S3 前置 accepted slice：`5bb122d3`
- S3 projection blocker：`docs/gateflow/uf-fix11-s3-projection-boundary-blocker-20260817.md`
- S3 projection amendment：`docs/gateflow/uf-fix11-s3-projection-boundary-amendment-20260817.md`
- S3 projection 双路 review：`docs/reviews/uf-fix11-s3-projection-boundary-review-mimo-20260817.md`、`docs/reviews/uf-fix11-s3-projection-boundary-review-ds-20260817.md`
- 本 gate 产物：按 Controller 裁决修复 S3 direct projection symbol-boundary amendment，只收紧 plan contract，不实现
- 实现状态：S3 implementation 暂停；当前 gate 禁止 production/test/README diff
- 下一入口：S3 projection boundary 双路 re-review；不预判 re-review、acceptance 或 plan-gate commit
- Implementation 禁止事项：不运行真实 CLI evidence，不创建 PR，不修改 Host/Engine/material/oracle/scenario/frozen evidence

## 1. Goal、motivation 与 success

### 1.1 Goal

修复 `upload_filing` 在已有新鲜 company metadata 场景下静默忽略用户提交公司名称、以及 filing 内容被判定为 `skipped` 时合法新 ticker alias 随 batch rollback 丢失的问题。

修复后的系统必须由 company-meta 提交契约在 publication lock 内依据最终已发布事实生成唯一提交结果；共享 filing publication 只机械传播该结果。只有最终 `uploaded` 或 `skipped` 的成功终态可以携带“公司名称未被采用”警告，并且 direct、CLI 与 tool/wait 投影必须来自同一 typed source of truth。

### 1.2 Motivation

问题真实存在，且严重性与 UF-FIX11 goal confirmation 一致：

1. 当前 fresh company-meta 决策只在 identity 变化时生成 commit intent。若用户只提交不同 `company_name`，该输入会在进入提交 owner 之前被丢弃，后续层没有直接证据判断“名称被保留”还是“名称被忽略”。
2. 当前 shared filing publication 的 `SKIP` 分支总是 rollback。即使 fresh 决策已经形成合法 alias merge intent，alias 也不会进入 storage commit，因此“accepted alias”与持久化真相可能不一致。
3. warning 若由 CLI、wait adapter、workflow 或测试根据请求参数、旧 snapshot、字符串或 status 反推，会违反单一语义 owner，并在并发发布时产生错误结论。

这不是展示层缺一行文案的问题；root cause 是提交契约没有暴露 publication-final company-meta outcome，且 `SKIP` 生命周期没有提交合法的 metadata intent。因此不能用 CLI fallback、日志匹配、`details` 拼接或 workflow 特例止血。

### 1.3 Success criteria

完成实现后必须同时满足：

1. 已发布 company metadata 新鲜时，单次 filing 上传不得改写 canonical `company_name`。
2. 用户提交非空名称，且该名称经唯一规范化规则与 publication-lock 下最终 canonical name 不等价时，成功终态生成一个 typed、定长、无路径、可操作的 company-metadata warning。
3. 名称等价时不生成 warning；等价只影响比较，不改写已持久化名称。
4. stale/missing company metadata 的显式 refresh 若最终采用提交名称，不生成 ignored-change warning；若并发最终真相没有采用该名称，则以 publication-lock 下最终结果为准。
5. fresh 决策携带合法新 alias 时，即使 filing 内容最终 `skipped`，alias 也通过同一 batch、同一 publication lock、同一 alias uniqueness guard 原子持久化。
6. alias 已存在或输入名称等价、且没有其他 metadata 变更时，`SKIP` 仍 rollback，不制造无意义 metadata commit。
7. alias collision、非法 identity、存储失败、取消、rollback、进程 kill 或其他失败终态不产生 warning。
8. warning 只允许出现在 `uploaded` / `skipped` 对应的成功结果中；CLI 保持 exit code `0`，成功摘要走 stdout，warning 走 stderr。
9. direct result、CLI 与 tool/wait 的 warning 都由同一个 typed warning 值投影，不各自重算。
10. 不改变已提交 UF-FIX01 的 company/source atomic boundary、ticker-alias grammar/uniqueness contract、UF-FIX10 的 publication arbitration 与 cancellation linearization。

## 2. Non-goals 与 scope

### 2.1 In scope

- `dayu.fins` company-meta intent、合并结果及名称比较契约。
- Fins storage batch commit 对 publication-final company-meta outcome 的返回。
- upload company-meta fresh/stale 决策对 submitted company name 的保留。
- shared filing publication 的 skip metadata commit 与 warning 传播。
- SEC/CN `upload_filing` completed payload 的 typed warning 字段。
- Fins ingestion/service/direct result、CLI 输出及 service wait result 的同源投影。
- 与上述 owner contract、状态机和 public projection 直接相关的单元/集成测试。
- 命中职责范围的根 README、Fins README、tests README。

### 2.2 Explicit non-goals

以下内容本 work unit 明确不改：

- `dayu/host/**` 及 Host README、Host 生命周期、ToolRuntime、wait/cancel 治理。
- `dayu/engine/**` 及 Engine README、tool protocol、LLM loop、compaction 或取消协议。
- material upload/publish 流程及 material 结果 schema。
- `docs/cli_ci_oracles.json`，包括 `upload_filing.company-meta-refresh` predicate 本身。
- scenario 定义、scenario runner、evidence runner、oracle evaluator。
- 任何 frozen evidence、真实 CLI evidence、golden transcript 或已冻结验证产物。
- company-name fuzzy matching、公司后缀剥离、翻译/音译、标点模糊、市场推断或外部主数据查询。
- ticker alias grammar、canonical ticker 选择、alias collision 规则的重新设计。
- 旧 schema/旧数据库兼容读取或兼容 shim。
- 通用 warning framework、跨业务 warning registry 或 Host/Engine warning protocol。
- PR 创建、提交、推送或合并。

## 3. Design alignment

### 3.1 分层与 owner 对齐

本计划保持 `UI -> Service -> Host -> Engine` 业务分层，并把财报业务语义留在 Fins：

- company name 是否被最终采用，是 Fins company metadata 的业务事实，不属于 Host/Engine。
- Host 继续只拥有 runner/tool 生命周期、等待、治理与取消；wait adapter 只投影已完成的 Fins typed result。
- Engine 继续只拥有单次运行、tool protocol 与消息转换；不得理解 company name、ticker alias 或 storage commit。
- storage publication lock 是最终持久化事实的线性化边界；请求快照、resolver snapshot 和 workflow status 都不能替代它。
- CLI 是展示层，只按 typed summary 输出，不根据用户输入或文本 details 推断 warning。

因此本 work unit 不需要也不允许修改 Host 或 Engine。该结论与 `docs/host/design.md` 中 Host 治理/等待/取消边界、`docs/engine/design.md` 中 Engine 不理解财报存储业务语义的边界一致。

### 3.2 与既有 work unit 对齐

- UF-FIX01：公司 metadata 与 filing/source 继续在同一 batch 中受 authoritative revalidation 和 publication guard 保护；不得先独立写 alias 再发布 filing。
- ticker-alias：`CompanyTickerIdentity` 继续独占 ticker grammar/dedupe；company-meta commit contract 继续独占 merge；storage 继续独占跨公司 alias uniqueness。UF-FIX11 不复制这些规则。
- UF-FIX10：共享 filing publication 继续独占 begin → cancel checkpoint → fresh read/validate → arbitration → cancel checkpoint → rollback/commit 的生命周期。UF-FIX11 仅细化 `SKIP` 后 metadata intent 的合法终结方式，不另建第二套 publication flow。

### 3.3 Oracle 对齐

`docs/cli_ci_oracles.json` 的 `upload_filing.company-meta-refresh` 要求：

- stale resolver company meta 缺名称时 fail-closed，显式名称与 source 一起原子 refresh；
- fresh canonical identity 不被单个 filing 静默改名；被忽略的新名称或 alias update 不能静默；
- 禁止 silent rename 和 silent ignored metadata。

UF-FIX11 对其作如下实现解释，不修改 oracle：合法 alias update 不应被“忽略后警告”，而应由 commit owner 实际持久化；不同 company name 因 fresh canonical name 必须保留，才生成 ignored-change warning。非法/冲突 alias 仍失败。

## 4. First-principles direct evidence

以下判断全部来自直接代码/契约证据，不以日志、测试偶然行为或下游表现代替 root cause：

1. `dayu/fins/pipelines/upload_company_meta.py::resolve_upload_company_meta_decision` 在 fresh existing meta 下仅比较 ticker identity；名称输入不进入 `CompanyMetaCommitIntent`。这是名称语义丢失的第一处 owner-boundary 证据。
2. `dayu/fins/domain/company_meta_contract.py::merge_company_meta_for_commit` 是 commit-time merge owner，但当前只返回 `CompanyMeta`，没有表达“提交名称未成为最终名称”的结果。
3. `dayu/fins/storage/_fs_storage_infra.py::_prepare_company_identity_commit` 在 publication guard 内重新读取当前 metadata、合并并做 alias uniqueness 检查；这是能观察 final truth 的最窄正确边界。
4. `dayu/fins/storage/repository_protocols.py::BatchingRepositoryProtocol.commit_batch` 当前返回 `None`，使 publication-final company-meta 结果无法传回 workflow。
5. `dayu/fins/pipelines/filing_upload_publication.py::execute_prepared_filing_publication` 的 `SKIP` 分支无条件 rollback；因此合法 alias intent 即使已被 fresh resolver 识别，也不会持久化。
6. SEC/CN filing workflow、`FinsUploadPipelineResult`、`FinsResultSummary`、CLI output 与 wait adapter 当前均无 typed company metadata warning，只能新增同源投影，不能从 raw fields 猜测。
7. 现有 SEC 测试证明 normal publish 会保留 fresh canonical name 并合并新 alias；现有 UF-FIX10 并发测试把带不同 alias intent 的 skip candidate 判为 conflict，正是本 work unit 需要按最终 metadata intent 语义细化的行为。
8. UF-FIX01/ticker-alias closeout 与 reviews 已确认：batch token、commit-time revalidation、alias uniqueness 和物理 swap 是正确原子边界；绕过它们做独立 alias 写入会回归已关闭风险。
9. SEC `_build_sec_filing_failure_event` 与 CN `_build_cn_filing_failure_event` 分别独占各自 filing typed failure terminal result 的构造；当前两个 builder 均未输出 `warnings`。A4 把 `SourceKind.FILING` 缺失 warnings 收紧为 fail-closed 后，这两个真实 producer 若漏改会让 typed failure 在 parser 边界退化为 generic exception failure。
10. `execute_prepared_filing_publication` 的 `finally` 在 `batch_terminal_started is False` 时调用 `rollback_prepared_upload_batch`；既有 PUBLISH 分支在进入 commit owner 前先把 flag 设为 `True`。`BatchingRepositoryProtocol.commit_batch` 明确消费 batch capability，commit 成功或抛错后 caller 都不得再次 rollback，因此新 SKIP metadata commit 必须沿用同一 capability 转交顺序。

## 5. 唯一 semantic owner

### 5.1 业务事实 owner

`dayu/fins/domain/company_meta_contract.py` 是以下语义的唯一 owner：

- submitted company name 的比较规范化；
- commit intent 中“本次上传请求过哪个 company name”；
- publication-lock 下最终 company metadata；
- 最终名称是否采用了 submitted name；
- `CompanyNameIgnoredChange` 这一 commit-time 业务事实。

`upload_company_meta.py` 只能调用同一规范化 helper 决定是否需要把 intent 带到 commit；它的结果不是 warning 真相。真正 warning predicate 必须在 commit owner 依据 final metadata 再计算。

### 5.2 持久化与原子性 owner

`dayu/fins/storage/_fs_storage_infra.py` 继续独占：

- publication lock；
- authoritative current metadata read；
- batch 内 company/source/material tree 的 swap；
- alias uniqueness guard；
- commit 成功后返回 `CompanyMetaCommitOutcome`。

任何 workflow、adapter 或测试 helper 都不得自行写 alias 或重做 uniqueness 检查。

### 5.3 LLM/user-facing projection owner

新增窄模块 `dayu/fins/company_metadata_warning.py`，只拥有 company-metadata warning 的稳定 public projection：

- typed kind；
- 固定、业务可读、可操作、无内部术语的 message；
- closed JSON object 编解码；
- 从 `CompanyNameIgnoredChange` 到 public warning 的唯一投影 helper。

它不是通用 warning framework，不接受自由文本，不承载其他业务 warning。domain owner 产生事实，projection owner 产生 LLM/user-facing 表达；二者职责不重叠。

### 5.4 消费者约束

- shared filing publication 只接收 commit outcome 并调用唯一 projection helper。
- `UploadOperationResult.company_meta_commit_outcome` 仅是 commit helper 到 shared publication 的内部载体；shared publication 是唯一读取者。
- SEC/CN workflow 只序列化 `FilingUploadPublicationOutcome.warnings`；不得读取内部 company outcome。未进入 shared publication 的 early cancelled/delete 分支显式使用空 warning tuple。
- ingestion/direct/service 只做 typed parse/forward。
- CLI 只决定 stdout/stderr 通道。
- wait adapter 只把同一 JSON warning 放入 completed tool result。
- 禁止任何消费者比较 raw company names、检查 alias 差异、解析 details/message 或基于 status 伪造 warning。

## 6. Typed contracts

以下名称、字段和约束在 implementation 中固定；若实现发现无法满足，必须停止并返回 plan gate，而不是临场改成 loose contract。

### 6.1 Domain intent 与 commit fact

在 `dayu/fins/domain/company_meta_contract.py`：

```python
@dataclass(frozen=True, slots=True)
class CompanyNameIgnoredChange:
    requested_company_name: str
    published_company_name: str


@dataclass(frozen=True, slots=True)
class CompanyMetaCommitOutcome:
    company_meta: CompanyMeta
    ignored_company_name: CompanyNameIgnoredChange | None
```

`CompanyMetaCommitIntent` 新增：

```python
requested_company_name: str | None = None
```

约束：

- 该字段表达用户本次 upload 明确提交的名称，不等同于 resolver proposal。
- `None` 表示本次调用没有提交名称；不得从 `proposed_company_name`、当前 meta 或 alias 反推。
- 非 `None` 必须在 intent 构造边界 trim 后非空，并受既有 upload validation 长度上限约束。
- download workflow 继续不传该字段，因此不会获得 upload warning 语义。
- `merge_company_meta_for_commit(...)` 返回值从 `CompanyMeta` 改为 `CompanyMetaCommitOutcome`；`company_meta` 是唯一要写入的 final meta。
- `ignored_company_name` 仅当 `requested_company_name` 非空且与 final `company_meta.company_name` 不等价时存在。

### 6.2 Company-name normalization 决策

新增单一公开 domain helper：

```python
def company_names_are_equivalent(left: str, right: str) -> bool:
    ...
```

比较规范化严格限定为：

1. Unicode NFKC；
2. `split()` 后以单个 ASCII space 连接，从而 trim 并折叠 Unicode whitespace；
3. `casefold()`。

明确不做：

- 标点删除；
- `Inc./Ltd./股份有限公司` 等后缀删除；
- 简繁转换、翻译、音译；
- ticker/市场推断；
- fuzzy/编辑距离。

原因：上述三步只消除表现形式差异，结果确定、可测试、无外部依赖；进一步“理解公司名”会把业务主数据推断引入上传事务，可能把真实不同名称误判为相同。

规范化只用于比较，不用于持久化。canonical name 继续保持现有已发布值；stale refresh 继续使用既有校验后的 submitted value，不把 NFKC/casefold 结果写入库。

### 6.3 Public warning contract

在 `dayu/fins/company_metadata_warning.py`：

```python
class CompanyMetadataWarningKind(str, Enum):
    COMPANY_NAME_IGNORED = "company_name_ignored"


@dataclass(frozen=True, slots=True)
class CompanyMetadataWarning:
    kind: CompanyMetadataWarningKind
    message: str
```

唯一允许的 JSON：

```json
{
  "kind": "company_name_ignored",
  "message": "本次提交的公司名称未生效；已保留现有公司名称。请核对上传目标公司是否正确。"
}
```

约束：

- message 是模块常量，不接受调用方自由文本。
- JSON parser 使用 closed shape；缺字段、多字段、未知 kind、非字符串或 message 不等于规范常量均 fail-closed。
- public warning 不暴露 requested/published raw name、路径、ticker、batch/token、内部类型名或 publication 状态。
- 当前业务最多 0/1 个 warning；typed result 中即使使用 tuple，也必须验证长度不超过 1 且 kind 唯一。

### 6.4 Batch commit contract

修改：

```python
BatchingRepositoryProtocol.commit_batch(
    batch: BatchToken,
) -> CompanyMetaCommitOutcome | None
```

语义：

- batch 没有 company-meta intent 时返回 `None`。
- 有 intent 且 physical publication 与 post-commit completion 都成功时，返回 publication-lock 内生成的 outcome。
- merge、alias uniqueness、swap、guard release 或其他 commit 错误均抛出既有 typed/storage error，不返回 outcome。
- 返回 outcome 不代表新增第二次读取；它必须就是 `_prepare_company_identity_commit` 用于写入 batch 的 final value。
- 所有 repository implementation 与 test fake 的签名同步更新；不得用 `object`、`Any` 或 `getattr` 逃避类型。
- pyright 不能单独证明 fake 已收敛：`-> None` 是 `CompanyMetaCommitOutcome | None` 的合法协变返回。必须用 §9.2 的完整 fake 清单与 `rg -n "def commit_batch" dayu tests` 输出逐项验收；需要模拟成功 metadata commit 的 fake 必须返回 exact outcome，并由测试断言该值真正进入 shared publication。

### 6.5 Internal upload/publication contracts

`UploadOperationResult` 新增内部字段：

```python
company_meta_commit_outcome: CompanyMetaCommitOutcome | None = None
```

该字段不直接进入 JSON；它只作为 `commit_prepared_upload_batch` 到 shared filing publication 之间的最小内部载体。`commit_prepared_upload_batch` 仅在 `commit_batch` 成功返回后，以不可变 replacement 返回携带 outcome 的 result。另建 wrapper 会把返回签名扩散到 material caller，因此不采用。

`FilingUploadPublicationOutcome` 新增：

```python
warnings: tuple[CompanyMetadataWarning, ...] = ()
```

并验证：

- `uploaded` / `skipped` 可为 0/1；
- cancelled、failed 或非完成态必须为空；
- warning 只能来自成功 commit outcome 的 projection。
- shared filing publication 是 `UploadOperationResult.company_meta_commit_outcome` 的唯一业务消费者，也是 `FilingUploadPublicationOutcome.warnings` 的唯一生产者。
- SEC/CN workflow 禁止直接读取或投影 `UploadOperationResult.company_meta_commit_outcome`；主 publication 分支只读取 `FilingUploadPublicationOutcome.warnings`，early cancelled/delete 分支显式使用 `warnings=()`。
- owner test 必须断言 `outcome.warnings == projection(outcome.result.company_meta_commit_outcome)`；除 shared publication 测试外，消费者测试不得访问内部 outcome 字段。

### 6.6 Pipeline/direct/service public contracts

#### 6.6.1 原子 S1+S2：terminal producer 与 strict parser contract

- SEC/CN `upload_filing` 的所有 terminal JSON（`ok`/`skipped`/failed/cancelled/delete）必须显式包含 `warnings` 数组，元素为上述 closed warning object；无 warning时为 `[]`。failed/cancelled/delete 分支只能是 `[]`，不得从内部 outcome 补算。
- `dayu/fins/company_metadata_warning.py` 独占 `CompanyMetadataWarning` 的 closed JSON codec；缺字段、多字段、未知 kind、非字符串或非规范 message 均 fail closed。
- S1+S2 在 `dayu/fins/ingestion_runtime.py` 只允许修改 `FinsUploadPipelineResult.warnings`、该类型的 warnings/status invariant、`FinsUploadPipelineResult.from_pipeline_json(result, *, source_kind: SourceKind)` 的无默认值签名，以及该 parser 对 `CompanyMetadataWarning` 闭集的调用/校验。不得在本 slice 修改 `FinsUploadResultSummary`、`FinsUploadResultSummary.to_json_summary()` 或 durable/direct projection。
- `FinsUploadPipelineResult.from_pipeline_json` 的 filing caller 必须传 `SourceKind.FILING`，material caller 必须传 `SourceKind.MATERIAL`，不得从 payload 字段猜类型。同一个 fresh parser 也服务 out-of-scope material payload，material payload 结构性地不含 `warnings`，所以“字段缺失 -> 空 tuple”只允许 `source_kind is SourceKind.MATERIAL`；这不是旧 schema compatibility。`SourceKind.FILING` 的 terminal payload 缺失 `warnings` 是 schema violation，必须 fail closed。
- `warnings: null`、非数组、未知 kind、message 不匹配、重复 kind、超过 1 个对象都必须 fail closed；只有显式 `[]` 表示 filing terminal result 无 warning。
- S1+S2 在 `dayu/fins/service_runtime.py` 只允许修改调用 `FinsUploadPipelineResult.from_pipeline_json` 的四个生产 callsite：SEC/CN filing 两处显式传 `SourceKind.FILING`，US/CN material 两处显式传 `SourceKind.MATERIAL`。不得在本 slice 修改 `_upload_summary_from_result` 或任何 durable/direct projection。

#### 6.6.2 后续 S3：summary、durable、direct、CLI/tool projection

- `FinsUploadResultSummary` 在 S3 增加 `warnings: tuple[CompanyMetadataWarning, ...] = ()`；该默认值是 failed/cancelled/deleted 及无 warning 成功结果的自然空状态。构造器必须 exact 校验每个元素类型、最多一个 warning，且仅 exact status `ok`/`skipped` 允许非空；`failed`/`cancelled`/`deleted` 必须为空。`FinsUploadResultSummary.to_json_summary()` 在 S3 写入 `warnings`，空值也序列化为 `[]`。
- `dayu/fins/service_runtime.py::_upload_summary_from_result` 在 S3 仍必须显式从已冻结的 `FinsUploadPipelineResult.warnings` 机械复制到 `FinsUploadResultSummary.warnings`；不得依赖默认值，也不得重新 parse JSON、比较名称或生成 warning。
- durable job record 的 `result_summary`、direct/CLI/tool 必须保存/传播同一个 typed tuple。既有 durable re-read 路径只消费 `status`/`document_id`，允许保留新增字段，但不得在 re-read 时重新推断 warning。
- `FinsResultSummary` 在 S3 增加 `warnings: tuple[CompanyMetadataWarning, ...] = ()`；仅 `FinsResultStatus.SUCCESS` 允许非空。该跨 operation public summary 使用语义自然的空 tuple 默认值，构造器必须 exact 校验元素类型、最多一个 warning 与 success-only invariant；非 SUCCESS + 非空是非法 typed 组合，必须 fail closed。此默认值表达合法的“无 warning”业务状态，不是从旧字段或下游数据补偿的 compatibility fallback。
- direct terminal event 从 typed upload summary 复制 warnings。真实 copy owner 是 `dayu/fins/ingestion_runtime.py::_direct_upload_terminal_events`；它把 `summary.warnings` 传入无默认值的 `_direct_result_event(..., warnings=...)`。唯一 generic/non-upload helper callsite `_emit_claimed_direct_result` 必须显式传 `warnings=()`，禁止给 `_direct_result_event` 增加默认值而掩盖漏传。
- `_direct_result_event` 不得在 CANCELLED 归一化分支静默把非空 warnings 置为 `()`；CANCELLED + 非空必须由 `FinsResultSummary` constructor invariant 拒绝，以保留非法 producer 组合的可见失败。
- CLI 在 S3 按现有逻辑先向 stdout 输出成功摘要，再逐条向 stderr 输出规范 warning message；exit code 保持 `0`。
- wait adapter 在 S3 仅为 completed result 增加 `warnings` 数组；failed/cancelled mapping 不增加、不从 exception/message 推断。

## 7. Data flow 与 public projections

### 7.1 请求到 publication-final fact

```text
validated upload request
  -> resolve_upload_company_meta_decision
     -> exact/equivalent name + no new alias: keep / no intent
     -> different name or new alias on fresh meta:
        preserve_published intent(requested_company_name, proposed identity)
     -> stale/missing meta:
        refresh_if_stale intent(requested_company_name, proposed name/source)
  -> shared filing publication
  -> storage publication lock
  -> authoritative current CompanyMeta read
  -> merge_company_meta_for_commit
  -> CompanyMetaCommitOutcome(final meta, optional ignored-name fact)
  -> alias uniqueness guard + atomic batch publication
  -> only after commit success: public warning projection
```

### 7.2 Public propagation

```text
CompanyMetaCommitOutcome
  -> FilingUploadPublicationOutcome.warnings
     -> SEC/CN upload_filing completed JSON
        -> FinsUploadPipelineResult
           -> FinsUploadResultSummary
              -> to_json_summary -> durable job record.result_summary
              -> FinsResultSummary
                 -> direct event -> CLI stderr
              -> service runtime -> wait adapter completed result
```

每条箭头只允许 typed parse/copy/serialize，不允许重新比较 company names 或读取 storage。`UploadOperationResult.company_meta_commit_outcome` 不越过 shared filing publication；durable `result_summary["warnings"]`、direct/CLI 与 tool/wait 均从同一个 `FinsUploadResultSummary.warnings` 派生。

## 8. State machine 与 invariants

### 8.1 Shared publication state machine

保持 UF-FIX10 的主状态机，仅细化 `SKIP`：

```text
BEGIN_BATCH
  -> CANCEL_CHECK_1
  -> FRESH_READ_AND_VALIDATE
  -> ARBITRATE
     -> CONFLICT: rollback -> failed(no warning)
     -> CANCEL: rollback -> cancelled(no warning)
     -> PUBLISH
     -> SKIP
  -> CANCEL_CHECK_2
     -> cancelled: rollback -> cancelled(no warning)
     -> PUBLISH: stage filing + company intent -> capability transfer -> commit
     -> SKIP + no metadata intent: rollback -> skipped(no warning)
     -> SKIP + preserve metadata intent:
        stage intent -> set batch_terminal_started=True -> commit metadata batch
  -> COMMIT_SUCCESS
     -> project optional ignored-name warning
     -> uploaded/skipped success
  -> COMMIT_FAILURE
     -> failed(no warning; storage 已消费 capability，caller rollback=0)
```

### 8.2 Skip arbitration contract

`_canonical_skip_requirements_are_met` 只接受：

1. authoritative source state 为既有 UF-FIX10 定义的 fresh `COMPLETE`；
2. filing candidate 与 authoritative identity 完全相同；
3. company decision 为以下二者之一：
   - `keep` 且没有 intent；
   - `stage` 且 intent 的 mode 恰为 `preserve_published`。

明确拒绝：

- `refresh_if_stale` intent 进入 skip；
- `skip` disposition 携带 intent；
- malformed/缺失 intent；
- identity mismatch、invalid alias 或 collision；
- 任何通过 loose predicate 接受的未知状态。

### 8.3 Skip 时 alias 原子持久化

当 `SKIP + preserve_published intent`：

1. 调用 `stage_upload_company_meta_decision(...)`，只在同一个已持有 writer scope 的 batch 中 stage company-meta intent；
2. 在调用 storage commit 前先设置 `batch_terminal_started = True`，把 batch capability 转交给 storage owner；从这一行起，无论 commit 成功还是抛错，outer `finally` 都禁止再次 rollback；
3. 直接调用 `batching_repository.commit_batch(batch)`；
4. 用 `build_prepared_filing_skip_result(...)` 构造 skipped result，再以 `dataclasses.replace(...)` 附上 commit outcome；
5. shared filing publication 从这个内部 outcome 唯一投影 warning，并构造 `FilingUploadPublicationOutcome`；
6. storage 在 publication lock 内重新读取 final meta、merge alias、做全局 uniqueness guard；
7. 只在整个 batch commit 成功后返回 `skipped` 与可选 warning。

SKIP 分支明确禁止调用 `publish_prepared_upload(...)` 或 `commit_prepared_upload_batch(...)`，也禁止 stage 任何 filing/source asset、source meta、version 或 manifest。上述 helper 属于 PUBLISH 路径，复用它会把本应 skipped 的 filing bytes 写入 batch。`batch_terminal_started` 不得晚于 `commit_batch` 设置；commit 返回或抛错后不得复位 flag，也不得由 outer `finally`/exception handler 调用 `rollback_prepared_upload_batch`。

因此合法新 alias 与 final company meta 原子发布；collision 或存储错误使整个操作失败，不会返回“alias accepted”或 warning。禁止在 skip 前后调用独立 alias repository 写入。source publication 必须保持零 mutation：source stage token 为空，source tree/content hash、source version、assets/meta/manifest 均 exact unchanged；accepted company identity metadata update 是 UF-FIX11 对 UF-FIX10 source-skip no-mutation contract 的有意且唯一例外。

若 intent 只承载不同 submitted name 而没有 identity 变化，仍需进入 commit owner，以 publication-final truth 判断 warning。这个 commit 是为生成受锁保护的业务结果所必需；等价名称/no-op alias 会在 fresh decision 阶段保持 `keep + rollback`。`_company_meta_from_published` 在 identity 不变时必须保留原 `updated_at`，测试必须断言 final company meta 逐字段/序列化 bytes 不变以及 source tree hash 不变。禁止采用 plan review MiMo 001 所建议的 commit 前 snapshot 比较，因为这会重新制造非最终真源。

metadata-only commit 仍完整服从 storage owner 的 `_validate_complete_source_tree`。若同 ticker whole tree 中存在无关 `REPAIR_REQUIRED` 或任何非 `COMPLETE` source，SKIP+preserve 必须 typed failure、无 warning、无 alias/company partial mutation；不得增加绕过完整性校验的 metadata-only commit API。这是 fail-closed 的明确权衡。

### 8.4 Success/skip-only warning invariant

| 终态/情形 | metadata action | warning |
| --- | --- | --- |
| `uploaded`，fresh canonical name 与 submitted name 不等价 | preserve + commit success | 1 个 |
| `skipped`，名称不同，无新 alias | metadata-only commit success | 1 个 |
| `skipped`，名称不同且有合法新 alias | alias commit success | 1 个 |
| `uploaded`/`skipped`，名称等价 | keep 或 commit success | 0 个 |
| `uploaded`/`skipped`，只有合法新 alias且名称等价/未提交 | alias commit success | 0 个；alias 已应用 |
| stale/missing refresh 最终采用 submitted name | refresh commit success | 0 个 |
| refresh intent 被并发 final truth 覆盖且名称不同 | commit success | 1 个，以 final truth 为准 |
| `skipped` candidate + unrelated non-`COMPLETE` source | whole-tree validation typed failure | 0 个，tree/identity 均不变 |
| alias collision/非法 identity/commit error | failed | 0 个 |
| cancel checkpoint 命中 | rollback + cancelled | 0 个 |
| arbitration conflict | rollback + failed | 0 个 |
| 进程 kill/无 completed result | recovery/未知 | 不发布 warning |

### 8.5 Failure/cancel/rollback/kill invariant

- warning 不是预提交日志，也不是 request validation side effect。
- 在 commit 成功返回以前，不构造 public warning。
- 任何 exception path 丢弃未返回 outcome，沿用既有 rollback/failure contract。
- cancel 在第二 checkpoint 前命中时 rollback；commit 开始后的晚到取消沿用 UF-FIX10 的 first-committer/linearization 语义，不把已提交 success 改写为 cancelled。
- 进程 kill 不产生 terminal projection；后续 recovery 只恢复 durable state，不补发推测 warning。

### 8.6 Publication-lock final truth

warning predicate 必须使用 `_prepare_company_identity_commit` 在 publication guard 内读取并合并出的 final `CompanyMeta`。以下来源均不具备最终权威：

- request payload；
- resolver 初始 snapshot；
- arbitration 前 fresh read；
- staged tree；
- upload result status；
- CLI details、日志或 event ordering。

提交所写 `CompanyMeta` 与 outcome 中 `company_meta` 必须是同一个值；durable state、direct result、CLI 和 tool result 才能保持一致。

## 9. 精确 affected files/modules

### 9.1 生产代码：允许修改

1. `dayu/fins/domain/company_meta_contract.py`
   - 名称比较 owner、intent 字段、ignored fact、commit outcome、merge 返回契约。
2. `dayu/fins/company_metadata_warning.py`（新增）
   - 窄 typed warning、固定文案、closed JSON 与唯一 projection helper。
3. `dayu/fins/pipelines/upload_company_meta.py`
   - 保留 submitted name；fresh name-only/new-alias intent 决策。
4. `dayu/fins/storage/repository_protocols.py`
   - `commit_batch` typed return。
5. `dayu/fins/storage/_fs_storage_infra.py`
   - publication-lock outcome 产生与成功返回。
6. `dayu/fins/storage/fs_batching_repository.py`
   - 透传 typed return。
7. `dayu/fins/pipelines/docling_upload_service.py`
   - `UploadOperationResult` 携带内部 outcome；commit 后不可变返回。
8. `dayu/fins/pipelines/filing_upload_publication.py`
   - skip metadata commit、状态 invariant、warning projection。
9. `dayu/fins/pipelines/sec_upload_workflow.py`
   - filing completed payload 序列化同源 warnings。
10. `dayu/fins/pipelines/cn_pipeline.py`
    - filing completed payload 序列化同源 warnings。
11. `dayu/fins/ingestion_runtime.py`
    - typed warning parse 与 upload summary。
12. `dayu/fins/service_runtime.py`
    - service upload summary 透传。
13. `dayu/fins/direct_events.py`
    - direct typed summary 的 success-only warnings invariant。
14. `dayu/cli/output.py`
    - success warning 输出到 stderr。
15. `dayu/service/fins_wait_adapter.py`
    - completed tool result 的同源 warnings 投影。

除上述文件外不允许扩大生产代码范围。若实现发现必须新增 exports 或修改其他生产模块，停止 slice 并回到 plan review，不做临场 facade/re-export。

### 9.2 测试代码：允许修改

Owner/核心行为：

- `tests/fins/test_company_meta_contract.py`
- `tests/fins/test_company_identity_storage_contract.py`
- `tests/fins/test_filing_upload_publication.py`
- `tests/fins/test_docling_upload_service.py`
- `tests/fins/test_sec_pipeline_upload_filing_stream.py`
- `tests/fins/test_cn_pipeline.py`

Typed projection：

- `tests/fins/test_fins_ingestion_runtime.py`
- `tests/fins/test_fins_service_runtime.py`
- `tests/fins/test_fins_direct_stream.py`
- `tests/cli/test_output.py`
- `tests/cli/test_fins_commands.py`
- `tests/service/test_fins_wait_adapter.py`

Protocol/fake 的机械类型同步：

- `tests/fins/upload_filing_test_support.py`
- `tests/fins/test_cn_download_workflow.py`
- `tests/fins/test_sec_pipeline_download_stream.py`

测试不得通过 fake 直接注入 public warning 绕过 commit owner；需要 warning 的 workflow 测试必须让 typed fake/real storage 返回合法 `CompanyMetaCommitOutcome`。

#### `commit_batch` 全量收敛清单

实施开始与结束时都执行 `rg -n "def commit_batch" dayu tests`，输出必须逐项对应以下当前全集；若出现新增定义，必须先补入本清单并说明 ownership：

| 类型 | 文件 | 定义/成功路径要求 |
| --- | --- | --- |
| public protocol | `dayu/fins/storage/repository_protocols.py` | exact `CompanyMetaCommitOutcome | None` contract |
| production core | `dayu/fins/storage/_fs_storage_infra.py` | exact `CompanyMetaCommitOutcome | None`；有 intent 的成功路径返回 publication-final outcome |
| production repository | `dayu/fins/storage/fs_batching_repository.py` | exact union return；机械透传 core 返回值 |
| test fake | `tests/fins/upload_filing_test_support.py` | exact union return；需要 metadata success 的路径返回 exact outcome |
| test fake | `tests/fins/test_sec_pipeline_download_stream.py` | exact union return；download no-intent/既有场景按契约返回 `None` |
| test fake | `tests/fins/test_cn_download_workflow.py` | exact union return；download no-intent/既有场景按契约返回 `None` |
| structural fake | `tests/fins/test_filing_upload_publication.py` | exact union return；warning/alias success 测试返回 exact outcome并断言被消费 |
| test fake | `tests/fins/test_fins_ingestion_runtime.py` | exact union return；需要 completed warning 的路径返回 exact outcome |
| test fakes（3 处） | `tests/fins/test_docling_upload_service.py` | 每个 override 都使用 exact union；success/failure/cancel 分别返回 outcome/抛错/不返回 |
| test fake | `tests/fins/test_sec_pipeline_upload_filing_stream.py` | exact union return；success warning 路径返回 exact outcome |

pyright 对 `-> None` 协变 override 不会报错，因此“pyright 通过”不能代替该表的人工/`rg` 验收。需要 outcome 的 fake 成功路径必须有行为断言，确保 outcome 进入 shared publication 而非静默丢弃。

### 9.3 文档：允许修改

文档 allowed files 只在后续 S3 projection slice 的 `Allowed files -> 文档` 中列一次；该清单同时构成本节的精确全局文档范围，避免重复条目漂移。

### 9.4 明确禁止修改

- `dayu/host/**`
- `dayu/engine/**`
- material workflow/module/tests
- `docs/cli_ci_oracles.json`
- scenario、oracle runner、evidence runner
- frozen evidence 与真实 CLI evidence 文件
- 已提交 UF-FIX01、ticker-alias、UF-FIX10 artifacts
- 与本 work unit 无关的 README

## 10. Small implementation slices

修订后只有两个 implementation slices：原 Slice 1/2 合并为一个不可拆分的原子 S1+S2，原 Slice 3 保留为后续 S3 projection slice。S1+S2 在完整绿色 validation 与同一 review loop 通过前不得形成 implementation artifact acceptance 或 commit；S3 只能在 S1+S2 accepted slice commit 后开始。每个 slice 只允许修改列出的文件。

### 原子 Slice S1+S2：company-meta owner 到 filing terminal parser 的完整闭环

#### Objective / expected outcome

在一个可独立变绿的 implementation/review/commit 单元内同时完成 domain intent/outcome、storage exact return、shared publication arbitration 与 metadata-only skip、warning codec、SEC/CN terminal producers，以及 strict parser/显式 `SourceKind`。成功信号是原 blocker 红测与本 slice 全部 focused tests 同时通过，且 warning 只能从 publication-final commit outcome 投影。

#### Prerequisites

- 本 amendment 经 `plan amendment review -> fix -> re-review` 接受，并形成 amendment acceptance checkpoint 后才能恢复 implementation。
- `docs/gateflow/uf-fix11-s1-slice-boundary-blocker-20260817.md` 的 `639 passed, 1 failed` 是 slice-boundary 直接证据，不是允许递延的测试债务。
- 当前原 Slice 1 dirty diff 原样保留为本原子 slice 的 partial implementation；它没有独立 acceptance，不得单独 stage/commit，也不得用旧 Slice 1 review 边界关闭。
- 原 accepted plan 的 §1-§9 typed contract、owner、state machine、non-goals 与 A1-A10/DS-RR1/DS-RR2 裁决保持不变；本 amendment 只修复 implementation slicing。

#### Plan-amendment gate commit boundary

amendment review/fix/re-review 接受后，必须先创建一个独立 plan-gate commit；该 commit 与后续 S1+S2 code commit 严格分离。plan-gate commit 只允许 stage 以下 amendment 文档，不得 stage 当前任何 production/test partial diff：

- `docs/gateflow/uf-fix11-company-meta-warning-plan-20260817.md`
- `docs/gateflow/uf-fix11-s1-slice-boundary-blocker-20260817.md`
- `docs/gateflow/uf-fix11-slice-boundary-amendment-20260817.md`
- `docs/gateflow/uf-fix11-slice-amendment-review-fix-20260817.md`
- `docs/gateflow/uf-fix11-slice-amendment-acceptance-20260817.md`（re-review 通过后创建）
- `docs/reviews/uf-fix11-slice-amendment-review-ds-20260817.md`
- `docs/reviews/uf-fix11-slice-amendment-review-mimo-20260817.md`
- `docs/reviews/uf-fix11-slice-amendment-rereview-ds-20260817.md`（如该 reviewer re-review 产生）
- `docs/reviews/uf-fix11-slice-amendment-rereview-mimo-20260817.md`（如该 reviewer re-review 产生）

建议 commit message 为 `gateflow: accept UF-FIX11 slice-boundary amendment`。commit 前必须逐个显式 stage 已存在的上述文件并用 cached diff 证明零 production/test path；禁止使用目录级 glob。plan-gate commit 完成后，现有 production/test partial diff 仍留在工作区，继续作为未接受的 S1+S2 implementation，不得被误判为已提交红色中间态。

#### Allowed files

生产：

- `dayu/fins/domain/company_meta_contract.py`
- `dayu/fins/pipelines/upload_company_meta.py`
- `dayu/fins/storage/repository_protocols.py`
- `dayu/fins/storage/_fs_storage_infra.py`
- `dayu/fins/storage/fs_batching_repository.py`
- `dayu/fins/company_metadata_warning.py`（新增）
- `dayu/fins/pipelines/docling_upload_service.py`
- `dayu/fins/pipelines/filing_upload_publication.py`
- `dayu/fins/pipelines/sec_upload_workflow.py`
- `dayu/fins/pipelines/cn_pipeline.py`
- `dayu/fins/ingestion_runtime.py`（仅 `FinsUploadPipelineResult.warnings`、其 invariant、`from_pipeline_json(..., source_kind)` 与 `CompanyMetadataWarning` 闭集解析；禁止触碰 `FinsUploadResultSummary`/`to_json_summary`）
- `dayu/fins/service_runtime.py`（仅四个 `FinsUploadPipelineResult.from_pipeline_json` callsite 的显式 `SourceKind`；禁止触碰 `_upload_summary_from_result`）

测试：

- `tests/fins/test_company_meta_contract.py`
- `tests/fins/test_company_identity_storage_contract.py`
- `tests/fins/upload_filing_test_support.py`
- `tests/fins/test_cn_download_workflow.py`
- `tests/fins/test_sec_pipeline_download_stream.py`
- `tests/fins/test_filing_upload_publication.py`
- `tests/fins/test_fins_ingestion_runtime.py`（fake、`FinsUploadPipelineResult` parser/invariant contract 与真实 failure roundtrip；禁止增加 summary/durable projection 断言）
- `tests/fins/test_docling_upload_service.py`
- `tests/fins/test_sec_pipeline_upload_filing_stream.py`
- `tests/fins/test_cn_pipeline.py`
- `tests/fins/test_fins_service_runtime.py`（仅四个 parser callsite 的显式 `SourceKind` regression；禁止修改 `_upload_summary_from_result` projection 断言）

#### Exact changes：domain/storage contract

1. 实现 §6.2 已冻结的唯一 company-name equivalence helper，并覆盖 Unicode/whitespace/case 与标点/后缀不等价反例；本 Slice 不重复列举规范化步骤。
2. 为 `CompanyMetaCommitIntent`/builder 增加显式 optional `requested_company_name`，校验非空，download callers 默认 `None`。
3. 新增 `CompanyNameIgnoredChange` 和 `CompanyMetaCommitOutcome`；让 merge 始终返回 outcome。
4. 让 upload fresh decision 在“新 alias”或“submitted name 与 snapshot 不等价”时生成 `preserve_published` intent；完全 no-op 时仍 keep。
5. 让 stale/missing upload refresh intent 显式携带 requested name；不改变 fail-closed source/name 要求。
6. `_prepare_company_identity_commit` 返回它实际写入的 outcome；`commit_batch` 仅在完整成功后返回 outcome/None。
7. 按 §9.2 `commit_batch` 全量收敛清单同步 protocol、repository 与全部 7 个 fake 文件（其中 `test_docling_upload_service.py` 有 3 个定义）；不能依赖 pyright 捕获 `-> None` 协变漏改。
8. 为需要模拟 metadata commit success 的 fake 返回 exact `CompanyMetaCommitOutcome`；no-intent download fake 可按真实契约返回 `None`，但注解仍必须是 exact union。

#### Tests：domain/storage/fake contract

- domain：fresh name preserved、different/equivalent name predicate、refresh adopted/no warning、final newer truth ignored warning。
- storage：returned outcome 与 durable final meta 完全相同；alias union/collision/rollback 保持原 contract。
- upload decision：name-only fresh intent、新 alias intent、no-op keep、stale refresh、缺名称 fail-closed。
- download regression：默认 `requested_company_name=None`，无 upload warning 语义，既有 commit 行为不变。
- fake contract：逐项断言需要 outcome 的成功路径返回 exact outcome；`rg -n "def commit_batch" dayu tests` 与 §9.2 全集一一对应。

#### Exact changes：publication/warning/producer/parser

1. 新增窄 public warning type、固定文案、closed codec 与 commit-fact projection helper。
2. `commit_prepared_upload_batch` 成功后把 storage outcome 放回不可变 `UploadOperationResult`；异常路径不构造 warning。
3. 扩展 canonical skip predicate，仅允许 `keep/no intent` 或 `stage/preserve_published intent`。
4. `SKIP + keep` 保持 rollback；`SKIP + preserve intent` 必须严格执行 `stage_upload_company_meta_decision(...) -> batch_terminal_started = True -> batching_repository.commit_batch(batch) -> build_prepared_filing_skip_result(...) -> dataclasses.replace(...)`。flag 必须在 commit 调用前设置，表示 capability 已转交 storage；commit 成功或抛错后 outer `finally` 均不得二次 rollback。该分支禁止调用 `publish_prepared_upload(...)`、`commit_prepared_upload_batch(...)` 或 stage 任何 filing/source asset。
5. alias-only skip 成功持久化 alias、不生成 ignored-name warning；name-only/different-name skip 在 commit success 后生成 warning。
6. shared filing publication 是 `UploadOperationResult.company_meta_commit_outcome` 的唯一读取/投影点；publish 与 metadata-only skip 都在这里生成 `FilingUploadPublicationOutcome.warnings`，并断言 projection 与内部 outcome 一致。
7. `FilingUploadPublicationOutcome` 强制 success/skip-only warning invariant；SEC/CN 禁止直接访问内部 outcome。
8. SEC/CN 只从 shared outcome 序列化成功/skip warnings；枚举并收敛所有 filing terminal producer：normal `ok`/`skipped` 使用 shared warnings，early cancelled/delete 显式 `warnings=[]`，`_build_sec_filing_failure_event(...)` 与 `_build_cn_filing_failure_event(...)` 构造的每个 failed result 都必须把 `warnings=[]` 传入各自 result builder。禁止 failure builder 省略字段，也禁止从 exception/message 推断 warning；不触碰 material/download semantics。
9. 更新 UF-FIX10 中“不同 alias intent 必为 conflict”的测试：当 source identity exact、intent 是合法 preserve 时走 metadata commit；真正 identity mismatch/refresh intent 仍 conflict。
10. metadata-only commit 继续服从 `_validate_complete_source_tree`；whole tree 有无关非 `COMPLETE` source 时 typed failure、无 warning、无 partial mutation，不新增 bypass。
11. 为让 producer/schema 在同一 slice 可验收，把 A4 的 parser boundary 提前在本 Slice 完成；修改范围严格等于 §6.6.1 的符号清单：`FinsUploadPipelineResult.warnings`/invariant、`from_pipeline_json(result, *, source_kind: SourceKind)` 与 `CompanyMetadataWarning` 闭集解析，以及 `service_runtime` 四个 parser callsite 的显式 filing/material `SourceKind`。`FinsUploadResultSummary.warnings`、`to_json_summary()`、`_upload_summary_from_result` 与 direct/durable projection 全部归 S3，S1+S2 禁止提前实现。
12. 改写 blocker 测试 `test_upload_filing_fresh_recheck_discards_stale_action_and_company_decision` 的旧 lifecycle 断言，但保留其原始回归语义：publication-lock 内 fresh re-read 必须丢弃 stale preflight 的 `create` action 与 stale company decision，以 fresh published truth 重新得到 `update + preserve_published`，不得复用旧 decision 或改写 canonical company name。

#### Tests：publication/warning/producer/parser

- shared owner 状态矩阵：uploaded/skipped × same/different name × no/new alias。
- skip alias 原子性：成功后 alias 存在；collision/commit failure 后不产生成功 result/warning。成功与失败都断言 source stage token 为空，source version/assets/meta/manifest 与 `published_tree_sha256` exact unchanged。
- name-only metadata commit：final `CompanyMeta` 逐字段和序列化 bytes 与 published meta 相同（包括 `updated_at`），source tree/content hash exact unchanged；只产生 publication-final warning。
- blocker 测试 `test_upload_filing_fresh_recheck_discards_stale_action_and_company_decision` 的新 exact contract：terminal result 保持 `filing_action == "update"` 且最终 `status == "skipped"`；metadata-only batch `begin` 恰一次、`commit` 恰一次且 `commit_tokens == begin_tokens`，caller `rollback_tokens == []`；`company.stage_tokens == begin_tokens` 且 source stage token 为空；raw terminal `warnings` 必须精确等于 `[{"kind": "company_name_ignored", "message": "本次提交的公司名称未生效；已保留现有公司名称。请核对上传目标公司是否正确。"}]`。提交前后 final `CompanyMeta` 的 canonical JSON 序列化 bytes 必须完全相同（显式覆盖 `company_name` 与 `updated_at`），`published_tree_sha256`、既有 source revision/version/meta/manifest/assets 必须完全不变。测试仍必须证明 publication-lock fresh re-read 丢弃 stale preflight 的 `create` action/旧 company decision，依据已发布事实重新得到 `update + preserve_published`；不得把测试弱化为只断言 warning 或 skip。
- whole-tree COMPLETE fail-closed：构造同 ticker 无关 `REPAIR_REQUIRED` source，SKIP+preserve 必须 typed failure、无 warning，company identity 与完整 published tree 都不变。
- cancellation：两个 checkpoint 均 rollback、无 warning；commit 开始后的既有 linearization 不变。
- SEC/CN 对称测试：同一请求一 publish 一 skip；name-only skip warning；alias-on-skip durable；early cancelled/delete 显式空 warnings，且 workflow 不读取内部 commit outcome。
- 真实 failure producer/roundtrip：分别新增 `test_sec_filing_failure_event_roundtrips_typed_reason_with_empty_warnings` 与 `test_cn_filing_failure_event_roundtrips_typed_reason_with_empty_warnings`（名称可按文件惯例微调但语义不得变）。测试必须执行真实 filing workflow 触发 `_build_sec_filing_failure_event`/`_build_cn_filing_failure_event`，不得手工拼 result dict或 mock parser；从 terminal event 取 `payload["result"]`，先断言 raw `warnings == []`，再调用 `FinsUploadPipelineResult.from_pipeline_json(..., source_kind=SourceKind.FILING)`，断言原 `FinsUploadFailureReason` 的 code/kind/message 保留且 parsed `warnings == ()`。
- terminal producer coverage：SEC/CN 各自对 fresh-validation typed failure 与 try-block 内 failure 至少覆盖一个真实 producer path，确保 builder 的全部调用点共享同一显式空 warnings 结果契约；不得只测 success/skip 或 handcrafted fixture。
- outcome 唯一投影：断言 `FilingUploadPublicationOutcome.warnings == projection(FilingUploadPublicationOutcome.result.company_meta_commit_outcome)`，consumer 只读前者。
- SKIP capability 成功：terminal-aware batching spy 断言执行顺序为 stage -> capability transfer -> commit，`commit_count == 1`、caller `rollback_count == 0`，返回 `skipped` 且 alias/company outcome durable；若 outer finally 尝试 rollback 已消费 token，测试必须直接失败。
- SKIP capability 失败：让 `commit_batch` 在消费 capability 后抛既有 storage/typed error，断言原异常/typed failure 保留、`commit_count == 1`、caller `rollback_count == 0`、无 warning；禁止 finally 二次 rollback 覆盖主异常。另保留 commit 前 stage error 仍恰好 rollback 一次的对照断言，证明 flag 只在 capability 真正转交前后分界。
- barrier/event 并发一：请求 A 完成同 ticker publish 后释放 barrier，请求 B 以 stale-prepared/fresh-recheck 进入 skip+alias/name metadata commit；断言 B warning/outcome 与 publication-lock final `CompanyMeta` 一致，source tree hash 不变。
- barrier/event 并发二：请求 A 的 skip metadata intent 使用 alias，同时请求 B 在另一 ticker 抢占该 alias；用 `threading.Barrier`/`threading.Event` 控制交错，断言唯一 winner、loser typed collision failure 且无 warning/partial mutation，最终 alias owner 与 returned outcome 一致。禁止 `sleep` 或 polling。
- warning JSON exact shape、固定文案、无路径/内部术语/raw company names。

#### Stop condition

若出现以下任一情况立即停止：

- final warning 判断需要离开 company-meta merge owner；
- 必须在 publication lock 外二次读取 storage；
- alias uniqueness/grammar 需要复制到 domain/workflow；
- commit 返回值无法严格类型化而需要 `Any`/`object`/`getattr`；
- 任一现有 atomicity/collision test 回归；
- 原 blocker 测试或任一本 slice focused test 仍为红色；不得把确定性红测递延到 S3、review 或 commit 后；
- 需要修改 Host/Engine 或建立第二套 publication lifecycle；
- alias 需要独立于 batch 写入；
- SKIP 分支调用 `publish_prepared_upload`、`commit_prepared_upload_batch` 或 stage 任一 filing/source asset；
- SKIP metadata commit 未在 `commit_batch` 前设置 `batch_terminal_started = True`，或 commit 返回/抛错后 outer finally/exception handler 再次 rollback；
- warning 在 commit 返回前产生；
- material flow 或其 schema 被改变；
- failure/cancel/rollback 能观察到非空 warning；
- 任一 SEC/CN filing terminal producer（尤其 `_build_sec_filing_failure_event`/`_build_cn_filing_failure_event`）省略 `warnings`，或 failure roundtrip 退化为 generic exception failure；
- S1+S2 修改 `FinsUploadResultSummary.warnings`、`FinsUploadResultSummary.to_json_summary()`、`service_runtime._upload_summary_from_result` 或任何 direct/durable/CLI/tool projection；
- 为 metadata-only commit 绕过 `_validate_complete_source_tree`；
- 并发测试依赖 `sleep`/polling 而非 barrier/event；
- 为保旧测试需要兼容分支。

#### Completion / review / commit boundary

- 只有本原子 slice 全部 exact changes 完成、完整 focused suite 绿色、§12.2 combined regression 全绿、相关逐文件 coverage 达标、全仓 pyright 通过、static boundary checks 通过后，才能写 S1+S2 implementation artifact 并进入一次完整 implementation review。combined regression 是 review/commit acceptance 的硬前置，不得只在 completion report 中补记。
- code review target 必须包含保留的原 Slice 1 partial diff 与新增 publication/warning/producer/parser diff；不得只 review 后半段，也不得沿用 blocker 前的局部验证作为 acceptance。
- review/fix/re-review 必须作为同一个原子 loop 裁决全部 findings；review fix 修改代码/测试后必须重新运行受影响 focused tests，并在 accepted commit 前重跑 §12.2 combined regression，最终一次必须全绿。只有 loop 通过、全部硬前置仍有效且 residual risks 全部分类后，才允许创建一个 `gateflow: accept UF-FIX11 company metadata warning S1+S2` protected local commit。
- 禁止为原 Slice 1 domain/storage partial diff、原 Slice 2 publication diff或任一红色/未验证中间态分别 stage/commit。当前 dirty diff 在 amendment review 与后续实现完成前始终是未接受工作区状态。
- accepted S1+S2 code commit 只允许包含本 slice 的 production/test implementation、按 accepted scope 确属本 slice 必要的 README（当前计划把 README 放在 S3，因此正常应为零）及本 slice implementation/review/fix/re-review/acceptance closeout artifacts；不得混入 blocker、amendment、plan review/fix/re-review/acceptance 或完整 plan 等 plan-gate docs。若实现期确认 S1+S2 必须修改 README，必须先修订本 slice allowed files，不能临时越界 stage。
- S1+S2 accepted slice commit 是后续 S3 的唯一 implementation prerequisite；缺少绿色 evidence、review artifacts 或 accepted commit 时不得进入 S3。

### Slice S3：typed public/durable/CLI/tool projections、README 与全量回归

#### Prerequisite

原子 S1+S2 的 SEC/CN/shared publication/parser tests、coverage、全仓 pyright 与 implementation review 全部通过，public warning codec 已冻结，且 accepted S1+S2 slice commit 已创建。

#### Allowed files

生产：

- `dayu/fins/ingestion_runtime.py`（仅 `FinsUploadResultSummary.warnings`、其 invariant 与 `to_json_summary()`，以及 direct typed copy 必需的 `_direct_upload_terminal_events`、`_direct_result_event` 与唯一 generic/non-upload callsite `_emit_claimed_direct_result`；不得改写 S1+S2 已冻结的 pipeline parser）
- `dayu/fins/service_runtime.py`（仅 `_upload_summary_from_result` 的 warnings 机械透传；不得改写四个 parser callsite 的 `SourceKind`）
- `dayu/fins/direct_events.py`
- `dayu/cli/output.py`
- `dayu/service/fins_wait_adapter.py`

测试：

- `tests/fins/test_fins_ingestion_runtime.py`（仅 summary/durable projection 与 parser non-regression）
- `tests/fins/test_fins_service_runtime.py`（仅 `_upload_summary_from_result` projection 与 parser callsite non-regression）
- `tests/fins/test_fins_direct_stream.py`
- `tests/cli/test_output.py`
- `tests/cli/test_fins_commands.py`
- `tests/service/test_fins_wait_adapter.py`

文档：

- `README.md`
- `dayu/fins/README.md`
- `tests/README.md`

#### Exact changes

1. 复用原子 S1+S2 已冻结的 `FinsUploadPipelineResult.from_pipeline_json(result, *, source_kind: SourceKind)` 与 typed warnings；本 Slice 不重新决定 missing/null/closed-shape schema，也不修改四个 service parser callsite，只做 summary/durable/direct/service 投影并保留 parser regression。
2. 严格按 §6.6.2 修改共享文件：`FinsUploadResultSummary.warnings: tuple[CompanyMetadataWarning, ...] = ()`/exact-element/at-most-one/`ok|skipped`-only invariant 与 `to_json_summary()` 归 `ingestion_runtime.py`；`failed`/`cancelled`/`deleted` 必须为空。`_upload_summary_from_result` 只在 `service_runtime.py` 显式机械复制 `result.warnings`，不得依赖 summary 默认值。随后 upload/service/direct summary 继续复制同一 typed tuple，durable job `result_summary` 的 warnings 空值也必须为 `[]`，save/re-read 不丢失、不重算。
3. direct event 保持现有 status/exit code/title/details；`_direct_upload_terminal_events` 只把同一个 `summary.warnings` 传给 `_direct_result_event`。`_direct_result_event` 的 typed warnings 参数无默认值，upload 与 `_emit_claimed_direct_result` 两个 production callsites都必须显式传值；后者只能传 `()`。`FinsResultSummary.warnings: tuple[CompanyMetadataWarning, ...] = ()` 的空 tuple 默认值只表达跨 operation 的合法空状态，不授权 producer 漏传或下游推断。CANCELLED + 非空 warnings 必须在 `FinsResultSummary` constructor fail closed，`_direct_result_event` 禁止静默归零。
4. CLI success summary 继续 stdout；每个 typed warning 的规范 message 输出 stderr；exit code `0`。
5. wait adapter completed result 增加同一 warnings JSON；failed/cancelled result 不增加、不推断。
6. README 只更新职责内稳定事实，不记录 gate/迁移历史。

#### Tests

- ingestion parser：所有 direct test/callsite 显式传 `SourceKind`；filing valid/empty；filing missing/null/malformed/unknown-message/unknown-kind/duplicate/超限全部 fail closed；仅 `SourceKind.MATERIAL` + missing 映射 empty，material `null` 仍 fail closed。
- durable summary：`to_json_summary()["warnings"]` 与 typed tuple exact 相同（空为 `[]`），saved job record 的 `result_summary["warnings"]` 与 direct/CLI/tool 同源；既有 re-read 的 status/document_id 读取不受新增字段影响。
- `tests/fins/test_fins_ingestion_runtime.py`：覆盖 `FinsUploadResultSummary` exact-element、at-most-one 与 success-status 闭集 contract；非精确元素、超过一个 warning、`failed`/`cancelled`/`deleted` + 非空均拒绝，且成功集合精确为 `ok`/`skipped`。该文件同时独占 direct helper/AST 测试：上传 `uploaded` + 无 warning 必须 exact copy 为 `()`，`deleted` direct result 必须为空，CANCELLED + 非空直接构造必须由 `FinsResultSummary` 拒绝，不得被 helper 静默归零。AST 必须穷举 `ingestion_runtime.py` 内 `_direct_result_event` 的全部 `Call` 节点，断言数量恰为两个，`warnings` 实参分别 exact 为 `summary.warnings` 与 `()`；新增任何 callsite 必须立即红。
- `tests/fins/test_fins_direct_stream.py`：只测试 `FinsResultSummary` public contract/invariant 与 `ValidatedFinsEventStream` stream contract；对 warnings 覆盖非精确元素、超过一个、FAILURE/CANCELLED + 非空拒绝及 SUCCESS 合法正例。该文件禁止 import `ingestion_runtime` private helper。
- service/direct 跨路径：`tests/fins/test_fins_service_runtime.py` 断言 `_upload_summary_from_result` 显式 exact copy；`tests/fins/test_fins_ingestion_runtime.py` 断言 uploaded/skipped 携带同一 warning object/value，failed/cancelled、deleted 与 generic non-upload result 为空。
- CLI：stdout 成功摘要不变、stderr 逐字输出 `本次提交的公司名称未生效；已保留现有公司名称。请核对上传目标公司是否正确。`、exit `0`、无 warning 时 stderr 不新增内容。
- wait adapter：completed warnings exact JSON；failed/cancelled 无 warning；LLM-facing 文本自足、无内部术语。
- end-to-end mocked CLI command：uploaded 与 skipped 都覆盖，且不运行真实外部 CLI evidence。

#### Stop condition

若出现以下任一情况立即停止：

- CLI/wait/direct 需要从 raw request、details 或 message 反推 warning；
- 需要修改 Host/Engine message contract；
- public warning 泄漏路径、raw names、batch/token/digest/cursor 或内部治理术语；
- warning 改变 success exit code/status；
- S3 改写 `FinsUploadPipelineResult.from_pipeline_json` 的 `source_kind`/warnings schema、pipeline warnings invariant、`CompanyMetadataWarning` closed codec 或四个 service parser callsite；
- direct projection 需要修改上述三个 `ingestion_runtime.py` symbols 之外的 producer，或需要从 details、raw request、durable JSON、日志或 storage 反推 warning；
- `_observation_failure_result`、`_observation_cancelled_result` 或 `_mark_observation_failed` 出现任何 diff；它们是非 direct projection 构造点，必须保持自然默认空状态且不纳入 S3 修改白名单；
- `_direct_result_event` 在 CANCELLED 分支静默丢弃非空 warnings，而不是让非法 typed 组合由 `FinsResultSummary` fail closed；
- README 需要描述未实现或非稳定行为。

## 11. README 决策

### 11.1 `README.md`：需要更新

触发原因是用户可见 CLI 输出与最终工作流发生变化。只更新 upload filing 相关段落：

- fresh canonical company name 不被单个 filing 改写；
- submitted name 不同且未采用时成功命令会在 stderr 给出 warning，exit code 仍为 `0`；
- 合法 ticker alias 即使 filing 内容 skipped 也会原子持久化；
- 不把“不要填写公司名称”作为规避 warning/业务校验的建议。

修改前再次阅读 README 内 `Agent更新约束`，保持最终用户手册边界。

### 11.2 `dayu/fins/README.md`：需要更新

触发原因是 Fins 稳定 contract 与 shared publication 状态机变化。记录：

- company-meta commit outcome 的 owner；
- publication-lock final truth；
- skip/no-intent rollback 与 skip/preserve-intent metadata commit 的区别；
- warning 只在 commit success 后投影。

不写实现历史、gate 编号或临时测试命令。

### 11.3 `tests/README.md`：需要更新

触发原因是测试矩阵新增稳定事实。记录 owner tests、skip alias atomicity、success-only warning 与 CLI/wait projection 覆盖。

### 11.4 其他 README：不更新

- `dayu/README.md`：分层关系和装配方式未变。
- Host/Engine README：对应代码与契约未变。
- config README：无 config/prompt 变化。

## 12. Validation plan

Implementation 完成后，所有命令均从仓库根目录执行，并先激活 Python 3.11 venv：

```bash
source .venv/bin/activate
```

### 12.1 Slice-focused tests

原子 S1+S2（一个命令、一个绿色门槛，不允许先跑 domain/storage 子集并形成 acceptance）：

```bash
pytest -q \
  tests/fins/test_company_meta_contract.py \
  tests/fins/test_company_identity_storage_contract.py \
  tests/fins/test_cn_download_workflow.py \
  tests/fins/test_sec_pipeline_download_stream.py \
  tests/fins/test_filing_upload_publication.py \
  tests/fins/test_fins_ingestion_runtime.py \
  tests/fins/test_docling_upload_service.py \
  tests/fins/test_sec_pipeline_upload_filing_stream.py \
  tests/fins/test_cn_pipeline.py \
  tests/fins/test_fins_service_runtime.py
```

该命令必须包含并关闭 blocker 中的
`test_upload_filing_fresh_recheck_discards_stale_action_and_company_decision`；不得 `--deselect`、`-k` 排除或把失败分类到 S3。

后续 S3：

```bash
pytest -q \
  tests/fins/test_fins_ingestion_runtime.py \
  tests/fins/test_fins_service_runtime.py \
  tests/fins/test_fins_direct_stream.py \
  tests/cli/test_output.py \
  tests/cli/test_fins_commands.py \
  tests/service/test_fins_wait_adapter.py
```

### 12.2 Combined regression

本命令是原子 S1+S2 implementation review 与 accepted code commit 的强制 acceptance 前置：focused suite 通过后、进入 review 前必须全绿；review fix 改动代码/测试后，accepted commit 前必须再次全绿。任何失败都使 S1+S2 保持未接受状态，禁止写 acceptance、stage 或 commit，也不得递延给 S3。

```bash
pytest -q \
  tests/fins \
  tests/cli/test_output.py \
  tests/cli/test_fins_commands.py \
  tests/service/test_fins_wait_adapter.py
```

S3 closeout 仍需按其 own gate 重跑该 combined regression；后一次运行不能补认 S1+S2 的红色或缺失 evidence。不得以真实 CLI、真实 SEC/CN 网络下载或 frozen evidence 代替上述确定性测试；本 work unit 也不运行这些 evidence。

### 12.3 Coverage

#### 12.3.1 原子 S1+S2 coverage gate

focused tests 全绿后运行完整 Fins deterministic suite，以覆盖 shared storage core 的既有分支；不得用 blocker 前 partial coverage 作为 acceptance：

```bash
coverage erase
coverage run --branch -m pytest tests/fins
coverage report -m --include='dayu/fins/domain/company_meta_contract.py,dayu/fins/company_metadata_warning.py,dayu/fins/pipelines/upload_company_meta.py,dayu/fins/pipelines/docling_upload_service.py,dayu/fins/pipelines/filing_upload_publication.py,dayu/fins/pipelines/sec_upload_workflow.py,dayu/fins/pipelines/cn_pipeline.py,dayu/fins/ingestion_runtime.py,dayu/fins/service_runtime.py,dayu/fins/storage/repository_protocols.py,dayu/fins/storage/_fs_storage_infra.py,dayu/fins/storage/fs_batching_repository.py'
```

#### 12.3.2 S3 coverage gate

```bash
coverage erase
coverage run --branch -m pytest \
  tests/fins \
  tests/cli/test_output.py \
  tests/cli/test_fins_commands.py \
  tests/service/test_fins_wait_adapter.py
coverage report -m --include='dayu/fins/ingestion_runtime.py,dayu/fins/service_runtime.py,dayu/fins/direct_events.py,dayu/cli/output.py,dayu/service/fins_wait_adapter.py'
```

每个 slice 的 gate 条件：该 slice 每个新增/修改生产文件的 statement coverage 均 `>= 80%`，并检查 branch misses；不能只用 aggregate coverage 掩盖单文件不足。若某个低层协议文件因纯 Protocol/转发导致覆盖不足，仍应增加直接 contract test，不加 pragma/ignore 绕过。S1+S2 coverage 未达标时不得进入 implementation review 或提交；S3 不得用自己的 coverage 补认前一 slice。

### 12.4 Pyright

```bash
python -m pyright dayu tests utils
```

原子 S1+S2 与后续 S3 各自在进入其 implementation review 前都必须运行一次全仓命令。Gate 条件：不得新增、扩散或掩盖类型错误。注意 pyright 允许 `-> None` 协变 override，不能单独证明 `commit_batch` fake 已收敛；S1+S2 必须同时执行下一节的全量 `rg` 与行为断言。任何 pyright 失败都禁止 review acceptance/commit，不得递延到后一 slice。

### 12.5 Static boundary checks

```bash
git diff --check
git status --short
git diff --name-only
rg -n "def commit_batch" dayu tests
rg -n "_build_(sec|cn)_filing_failure_event|warnings" \
  dayu/fins/pipelines/sec_upload_workflow.py \
  dayu/fins/pipelines/cn_pipeline.py
rg -n "batch_terminal_started|commit_batch|rollback_prepared_upload_batch" \
  dayu/fins/pipelines/filing_upload_publication.py \
  tests/fins/test_filing_upload_publication.py
rg -n "_direct_result_event|_observation_failure_result|_observation_cancelled_result|_mark_observation_failed" \
  dayu/fins/ingestion_runtime.py \
  tests/fins/test_fins_ingestion_runtime.py
rg -n "hasattr|getattr|Any|object" \
  dayu/fins/domain/company_meta_contract.py \
  dayu/fins/company_metadata_warning.py \
  dayu/fins/pipelines/upload_company_meta.py \
  dayu/fins/pipelines/filing_upload_publication.py
```

人工检查：

- diff 文件严格属于 allowed files；
- `rg -n "def commit_batch" dayu tests` 的 dayu 3 个定义（1 个 Protocol + 2 个 implementation）、test 7 个文件/9 个定义（其中 docling 文件 3 个定义）与 §9.2 清单 exact 对应；所有注解为 `CompanyMetaCommitOutcome | None`，需要 outcome 的 fake 成功路径有 exact return/assertion；
- Host/Engine/material/oracle/scenario/frozen evidence 无 diff；
- warning 规范常量逐字等于 `本次提交的公司名称未生效；已保留现有公司名称。请核对上传目标公司是否正确。`，且不含路径、raw company names 或内部治理标识；
- SKIP+preserve call path 不含 `publish_prepared_upload`/`commit_prepared_upload_batch`，source stage token 与 tree hash 断言存在；
- `from_pipeline_json` 所有 callsite 显式传无默认值 `SourceKind`；filing terminal `warnings` 必存在且空为 `[]`；只有 `SourceKind.MATERIAL` 的 missing 被解析为空，任一 source kind 的 `null` 都 fail closed；
- `_build_sec_filing_failure_event` 与 `_build_cn_filing_failure_event` 的 result builder 参数都显式包含 `warnings=[]`；真实 workflow producer roundtrip tests 断言 raw empty list、parsed empty tuple 与 exact typed failure reason；
- SKIP metadata branch 的 `batch_terminal_started=True` 文本顺序严格早于 `commit_batch`；success/commit-failure tests 都断言 caller rollback 0，commit 前 stage failure 对照断言 rollback 1；
- durable job `result_summary["warnings"]` 与 typed/direct/CLI/tool 投影一致；
- `_direct_result_event` 的 warnings 参数无默认值；AST test 穷举 `ingestion_runtime.py` 中全部 `_direct_result_event` `Call` 节点，数量 exact 为两个，`_direct_upload_terminal_events` 传 `summary.warnings`、`_emit_claimed_direct_result` 传 `()`；任何第三个 production callsite 使测试变红。
- `_observation_failure_result`、`_observation_cancelled_result`、`_mark_observation_failed` 函数体无 diff，仍由 `FinsResultSummary.warnings=()` 表达自然空状态；`_direct_result_event` 的 CANCELLED 分支不得静默归零 warnings。
- 每个新增/修改模块、类、函数具有符合项目约束的中文 docstring，包含参数、返回、异常；
- 没有 compatibility re-export、wrapper/facade、默认值补偿或 loose parsing。

## 13. Risks 与 residual classification

### 13.1 Plan review A1-A10 裁决保留

| ID | Controller decision | Plan fix 状态 | 结论 |
| --- | --- | --- | --- |
| A1 | `rejected-with-reason` | 证据保留 | 等价名称本就 keep+rollback；不等价 name-only 必须进入 commit owner。identity 不变时 final meta/`updated_at` 不变；禁止提交前 snapshot 推断 warning。锁/physical swap 成本另行分类。 |
| A2 | `rejected-with-reason` | 证据保留 | UF-FIX10 零 mutation 约束继续覆盖 filing/source；合法 company identity metadata commit 是用户明确授权的唯一例外。必须验证 source stage 为零、source tree hash exact unchanged。 |
| A3 | `accepted` | 已修复 | §9.2 列全 dayu 3 个定义（Protocol + 2 implementations）及 test 7 文件/9 定义，原子 S1+S2 覆盖全部 fake 文件，§12.5 加 `rg` 与行为验收。 |
| A4 | `accepted` | 已修复 | parser 新增无默认值显式 `SourceKind`；missing 仅允许 material；filing 必须显式数组；`null` 等 fail closed。 |
| A5 | `accepted` | 已修复 | 固定 message 改为 controller 指定精确文案。 |
| A6 | `accepted` | 已修复 | `UploadOperationResult` 仅作内部载体；shared outcome 是唯一消费/投影点；early/delete 显式空 warnings。 |
| A7 | `accepted` | 已修复 | metadata-only commit 保留 whole-tree COMPLETE fail-closed，并加入无 warning/无 partial mutation 测试。 |
| A8 | `accepted` | 已修复 | SKIP 写死 direct metadata stage+commit，禁止 publish helper 与 filing stage。 |
| A9 | `accepted` | 已修复 | durable `to_json_summary()`/job record 明确持久化 warnings。 |
| A10 | `accepted` | 已修复 | 两个 barrier/event-controlled final-truth/collision 并发测试已落名，禁止 sleep/polling。 |

### 13.2 DS re-review 新 findings 裁决

| ID | Controller decision | Plan fix 状态 | 结论 |
| --- | --- | --- | --- |
| DS-RR1 | `accepted` | 已修复 | 原子 S1+S2 点名 `_build_sec_filing_failure_event`/`_build_cn_filing_failure_event` 的显式 `warnings=[]` producer contract，把 parser/source-kind boundary 与 domain/storage/publication 放在同一绿色 slice，并增加真实 workflow failure event -> typed parser roundtrip tests，防止 typed reason 退化。 |
| DS-RR2 | `accepted` | 已修复 | SKIP metadata commit 在 `commit_batch` 前必须设置 `batch_terminal_started=True` 转交 capability；成功/失败后 caller rollback 都为 0，commit 前 stage error 才 rollback 1 次，并以 terminal-aware spy 验收。 |

### 13.3 本 work unit 内必须关闭

1. **commit return 类型扩散**：protocol、Fs implementation、所有 override/fake 必须同步；以 pyright 和 download regression 关闭。
2. **并发 snapshot 误报/漏报**：warning 必须由 publication-lock final outcome 产生；以 commit-time concurrent tests 关闭。
3. **skip alias 丢失或部分写入**：必须走同一 batch/uniqueness/swap；以 collision、failure、durable-state tests 关闭。
4. **failure/cancel 泄漏 warning**：所有 public result 类型建立 invariant；以 shared owner/direct/wait/CLI negative tests 关闭。
5. **SEC/CN 漂移**：两条 filing workflow 使用同一 shared outcome，并做对称测试。
6. **LLM-facing 非自足/泄漏**：固定业务文案与 closed JSON；以 exact projection tests 关闭。
7. **whole-tree degraded 状态的错误绕过/部分提交**：保留 storage completeness owner 的 fail-closed 行为，以 owner/workflow degraded-tree test 关闭；不新增 bypass。
8. **durable/UI/tool 漂移**：`to_json_summary()`、saved job record、direct/CLI/tool 使用同一 typed tuple，以 exact durable record test 关闭。
9. **filing failure producer/schema 漂移**：SEC/CN 两个真实 failure builder 必须显式输出 `warnings=[]`，并经 `SourceKind.FILING` parser roundtrip 保留 exact typed failure reason；以 producer/roundtrip tests 关闭。
10. **commit capability 二次 rollback**：SKIP metadata commit 必须在调用 storage 前转交 capability；以成功/失败 rollback-count 和 terminal-token spy tests 关闭。
11. **slice-boundary 红色中间态**：domain producer 产生 `stage/preserve` intent 后，必须在同一原子 S1+S2 完成 canonical skip predicate 与 metadata-only commit；blocker 红测必须在同一 focused gate 关闭，禁止拆分 acceptance/commit。

### 13.4 接受的设计权衡，不是 blocker

1. **name-only skip 可能执行内容不变的 metadata batch publication**：这是为了让 warning 以 lock-final truth 为准；仅不同名称才触发，等价/no-op 请求仍 rollback。final company meta bytes/字段与 source tree 必须不变。当前不增加预提交 no-op optimizer，避免产生第二真源。
2. **public warning 不回显两个公司名**：降低路径/敏感信息/长度风险，用户可回看请求和 canonical metadata；固定文案已给出可操作动作。
3. **warning collection 当前最多一个**：使用 typed tuple 便于结果层稳定序列化，但 module 仍只支持 company-name-ignored 单一业务语义，不演化通用 warning registry。
4. **degraded unrelated source 使 metadata-only commit fail closed**：行为已在本 slice 明确并以测试覆盖；正确性风险分类为 `fixed in current slice`，因为不再存在未声明分支或 bypass 空间。
5. **failure producer 与 parser 同 Slice 收敛**：为避免 producer 先变而 strict parser 后变（或反向）造成中间断裂，原子 S1+S2 同时修改两个 failure builders、pipeline parser 与 `service_runtime` 显式 callsite；这是一个原子 schema slice，不是 material scope 扩张。

### 13.5 Residual：分配给后续 work unit

1. **name-only metadata batch 的 writer lock/physical swap 成本**：`assigned to later work unit`；除非本轮测试发现 correctness/stability 回归，否则 final-truth 正确性优先。
2. **material upload 的类似 company-name 行为**：`assigned to later work unit`；明确不在 UF-FIX11 scope，若 oracle/产品要求再建独立 work unit。
3. **真实 CLI evidence、scenario/oracle/frozen evidence 更新**：`assigned to later work unit`；UF-FIX11 不运行、不改动。
4. **commit 已 durable 但 post-commit guard-release/cleanup 报错的运维可见性**：`assigned to later work unit`；沿用既有 storage failure contract，本 work unit 不引入 warning 补发或 success 推断。

没有 `covered by later approved slice`、`tracked by existing issue` 或 `requiring new issue or explicit user decision` 的 residual；没有未分类 residual risk。

DS-RR1 与 DS-RR2 均分类为 `fixed in current slice`：前者由真实 SEC/CN producer roundtrip 关闭，后者由 capability transfer 顺序与 rollback-count/terminal-token tests 关闭，不递延到后续 work unit。

### 13.6 Blocker classification

已识别的 slice-boundary blocker 由本 amendment 合并 S1+S2 解决；在 amendment review 接受前 implementation 保持 blocked，现有 partial diff 不可提交。若恢复 implementation 后发现 warning 无法在现有 publication-lock commit boundary 内返回、必须修改 Host/Engine/material/oracle、或原 blocker 红测无法在原子 allowed files 内关闭，则视为新的 plan invalidation blocker，停止并回到 plan amendment，不擅自扩大 scope。

## 14. 为什么不过度设计

本方案只增加两类必要能力：company-meta commit owner 的 typed final outcome，以及一个单一业务用途的 warning projection。它复用现有 batch、publication lock、shared filing publication、direct/service result 链和 CLI renderer：

- 不建新数据库表、event bus、outbox 或 warning service；
- 不建通用 warning registry/插件体系；
- 不给 Host/Engine 增加财报业务协议；
- 不做 fuzzy company-name matching 或外部主数据查询；
- 不为 skip alias 另建独立事务；
- 不通过 adapter fallback 或兼容 schema 保留错误语义。

新增的 `company_metadata_warning.py` 只隔离 LLM/user-facing 固定投影，避免 domain commit 模块承担展示格式，也避免 CLI、wait、workflow 各自复制文案。这个模块是单一 projection owner，而非抽象层扩张。

## 15. Completion format

Implementation gate 完成时，交付说明必须按以下格式：

1. **改了什么**：列出 owner contract、skip alias atomic persistence、public warning projections 与 README 更新。
2. **验证了什么**：列出实际执行的 focused tests、combined regression、逐文件 coverage、pyright 与 boundary checks，报告结果。
3. **风险/未覆盖项**：按“本 work unit 已关闭 / 接受权衡 / 后续 work unit”分类，不得写模糊的“可能有风险”。
4. **边界确认**：明确 Host/Engine/material/oracle/scenario/frozen evidence 未改，真实 CLI evidence 未运行，PR 未创建。
5. **下一 gate**：implementation review；未通过前不得进入 deepreview/PR。

## 16. Plan amendment gate closeout

- Goal/motivation/success：已冻结。
- Non-goals/scope：已冻结。
- 语义 owner 与 publication-lock final truth：已冻结。
- typed contracts/data flow/state machine/public projections：已冻结。
- company-name normalization 与 skip alias atomicity：已冻结。
- 原 accepted plan 的业务契约、owner、state machine、non-goals、README decision 与 completion format：保持冻结。
- slices、allowed files、prerequisites、focused/combined tests、coverage/pyright、stop conditions、review/commit boundary：已按 blocker 与 DS Finding-001/002/003、OQ-1 修订，待 plan amendment re-review。
- A1/A2：保留 `rejected-with-reason`，未采用 commit 前 warning 或取消 skip metadata commit 的建议。
- A3-A10：上一轮 controller accepted findings 已落实并由两路 re-review 确认关闭。
- DS-RR1/DS-RR2：controller accepted 的新 findings 已落实，并由最终双路定向 re-review 以 `pass` 确认关闭。
- 原 Slice 1/2：合并为不可拆分的原子 S1+S2；domain/storage partial diff 保留但无独立 acceptance，必须与 publication/warning/producer/parser 一起变绿、review、commit。
- 原 Slice 3：保留为后续 S3 public/durable/CLI/tool projection slice，只能在 S1+S2 accepted slice commit 后进入。
- DS Finding-001：已修复；blocker 测试的新 skipped/metadata-only lifecycle、warning、byte/tree 不变量与 stale fresh-recheck 原回归语义均已冻结。
- DS Finding-002：已修复；§12.2 combined regression 已成为 S1+S2 review/commit acceptance 强制前置。
- DS Finding-003：已修复；`ingestion_runtime.py`/`service_runtime.py` 已按 S1+S2 parser symbols 与 S3 summary/durable symbols 精确拆分。
- DS OQ-1：已关闭；amendment docs 先形成独立 plan-gate commit，production/test partial diff 零 stage；后续 S1+S2 code commit 排除 plan docs。
- 本 amendment 对生产代码或测试的新增修改：无；已有 UF-FIX11 S1 dirty diff 内容保持不变。
- 真实 CLI evidence：未运行，且本 work unit 禁止运行。
- PR：未创建，且本 gate 禁止创建。
- 当前 blocker：无；slice-boundary amendment 已由两路 final re-review `pass` 并被 controller 接受。
- 当前 gate：原子 S1+S2 implementation。
- 下一入口：完成原子 S1+S2 implementation、验证并进入 implementation review。

## 17. S3 direct projection symbol-boundary amendment

- blocker：`docs/gateflow/uf-fix11-s3-projection-boundary-blocker-20260817.md` 证明 `FinsUploadResultSummary -> FinsResultSummary` 的唯一 typed copy 必经 `ingestion_runtime.py::_direct_upload_terminal_events/_direct_result_event`，而原 S3 symbol 白名单漏列这两个 helper。
- 修订范围：production/test/document allowed 文件全集、业务目标、warning owner、S1+S2 parser/codec 与 Host/Engine non-goals全部不变；只扩大 `ingestion_runtime.py` 的 S3 symbol 白名单并精确规定两个 production callsites。
- 参数策略：`_direct_result_event` 的 warnings 参数必填且无默认值；upload callsite 传 `summary.warnings`，唯一 generic/non-upload callsite `_emit_claimed_direct_result` 显式传 `()`。`FinsResultSummary.warnings=()` 是跨 operation public contract 的合法空状态，不是 producer fallback。
- gate：本修订必须独立经过 MiMo/DS plan review、controller fix/re-review 与 acceptance，并形成独立 plan-gate commit；在此之前 S3 implementation 保持暂停。
- plan-gate commit 只允许包含本 plan、blocker、amendment、双路 review/fix/re-review 与 acceptance artifacts，禁止 production/test/README diff。建议 commit message：`gateflow: accept UF-FIX11 S3 projection boundary amendment`。
- acceptance：MiMo 与 DS 定向 re-review 均为 PASS；initial findings 已全部 fixed 或 rejected-with-reason，未分类 residual risk 为零。独立 plan-gate commit 创建后恢复 S3 implementation。
