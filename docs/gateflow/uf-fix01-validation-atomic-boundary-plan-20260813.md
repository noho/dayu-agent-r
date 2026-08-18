# UF-FIX01 validation atomic boundary — Plan Gate

## 1. Gate 元数据

- **work unit**：`UF-FIX01 validation-atomic-boundary`
- **gate**：plan
- **plan 状态**：`accepted / implementation-authorized / implementation-not-started`
- **目标分支**：`codex/upload-filing-oracle`
- **target baseline / plan 取证 HEAD**：`b3cb1f1b16f4d552eb762de3be59dc75c7586ab6`
- **goal confirmation**：已由用户确认；本 gate 不重新打开目标确认。
- **artifact path**：`docs/gateflow/uf-fix01-validation-atomic-boundary-plan-20260813.md`
- **本 gate 产物范围**：plan、plan-fix、双路 review/re-review 与 Controller adjudication artifacts。
- **本 gate 禁止变更**：生产代码、测试、README、oracle/scenario registry、frozen evidence、push、PR、main。
- **plan review 输入**：`docs/reviews/plan-review-20260813-093247.md`、
  `docs/reviews/plan-review-20260813-094750-agentds.md`。
- **plan fix 裁决**：`docs/gateflow/uf-fix01-validation-atomic-boundary-plan-fix-20260813.md`。
- **plan gate 裁决**：`docs/gateflow/uf-fix01-validation-atomic-boundary-plan-gate-adjudication-20260813.md`。
- **后继入口**：implementation；仅在 accepted-plan checkpoint commit 后授权按本 plan 实现。

## 2. Goal / Motivation / Success

### 2.1 Goal

在不改变 filing date/year domain、现有两套 format allow-list 内容和 UF-FIX09 shared
interruptible Docling converter 的前提下，建立以下 owner 级边界：

1. Fins typed filing upload request/validation contract 在任何 workspace mutation 之前完成全部可预判 usage 校验。
2. CLI 只解析 syntax、调用 Fins contract、在 Service factory/bootstrap 前失败，并机械映射 exit/stdout/stderr。
3. SEC 与 CN/HK filing 的 company meta 和 source 使用同一个 `BatchToken`、同一次 commit 原子发布。
4. pipeline/result summary 携带 closed、bounded、actionable 的 typed failure reason；CLI 不读异常字符串作分类。
5. 正常 handled validation/content failure 不留下 job、company meta、half source 或 eager workspace skeleton。

### 2.2 动机成立且严重性未被高估

直接证据显示这是 owner 与事务边界缺陷，不是展示瑕疵：

- `_run_fins_direct_command_async` 当前先执行 `FINS_DIRECT_SERVICE_FACTORY(workspace_root)`，再在
  `_upload_filing_stream` 中解析 ticker/files；`DefaultFinsRuntime.create` 又以
  `create_directories=True` 构造 storage，并由 `FsFinsIngestionJobStore.__post_init__` 创建 jobs 目录。
- UF-003–006、015–019、021–024、026–038 的 frozen raw evidence 证明可预判失败会创建
  `.dayu`、batch/recovery/ingestion 目录、`portfolio`；UF-017、033–038 还会先发布 company meta。
- `run_upload_filing_stream` 与 `CnPipeline.upload_filing_stream` 当前先独立 commit `company_batch`，随后
  `prepare_upload`，最后为 source 开另一个 batch；转换或 source publication 失败不能回滚已发布 company meta。
- UF-I11–I13 的 raw stderr 含第三方 traceback，after tree 留下 company meta/skeleton；
  `FinsUploadPipelineResult.from_pipeline_json` 当前丢弃 pipeline `message`，runtime 只能渲染通用失败文本。

### 2.3 Success criteria

- frozen 无效/缺参矩阵均在 factory 调用前返回 exit `2`、stdout 为空、stderr 为一个具体可行动 reason；fresh workspace before/after tree 完全相同。
- state-aware `auto/create/update` 使用同一 Fins validator 与同一 storage snapshot，不在 CLI/pipeline 复制规则。
- fresh company 与 existing company 下，SEC、CN、HK filing 成功路径都只提交一个 publication batch；任何 precommit failure/cancel 保持 company/source 的旧 published state 同时不变。
- skip 不开启 publication batch；delete 不创建/刷新 company meta；cancel/rollback/commit ownership 保持现有线性化语义。
- content、storage、runtime failure 返回 exit `1`；cancel 返回 `130`；failure reason 是 typed、closed、最大 240 字符且不含绝对路径、traceback、exception repr、job id 或 raw payload。
- 所有受影响测试通过，完整 pyright 无新增/扩散错误，每个新增/修改生产文件单文件覆盖率 `>=80%`。

## 3. Non-goals

本 WU 明确不处理：

- UF-FIX02–08、UF-FIX10、UF-FIX11、UF-PF12；尤其不修 renamed update identity、delete 后 auto、
  existing-source repair、multi-file primary/collision、计数和其它 action 业务语义。
- 不增加、删除或对齐 `FINS_UPLOAD_FILE_SUFFIXES` 与 `SUPPORTED_UPLOAD_SUFFIXES` 的成员；格式漂移留给其所属 WU。
- 不扩张 fiscal year 合法域；保持当前 `int` 且非负规则，不把 `0` 改为非法。
- 不扩张/收窄 US fiscal period；CN/HK 继续只复用当前 `normalize_cn_fiscal_period` 的闭集。
- 不新增 filing/report date calendar/domain 校验，不改变现有 stripped/bounded 行为。
- 不修改 shared converter、Docling config、process/IPC/cleanup/cancellation state machine；不恢复同步 converter 或 caller-local converter。
- 不修改 Host、Engine、EventLog、Memory、Trace、ToolAwaiting 或 LLM-facing schema/prompt。
- 不修改 frozen evidence、`docs/cli_ci_oracles.json`、`docs/cli_ci_scenarios.json` finding/rerun 状态。
- 按 Gateflow 生成本地 checkpoint/implementation/fix/closeout commits；不创建 PR、不 push、不更新 main。

## 4. Design alignment 与 owner

`docs/host/design.md` 与 `docs/engine/design.md` 明确 Host 不拥有财报业务/仓储语义，Engine 不理解 Fins；
direct Fins 命令不进入 Host/Engine run。实现依赖保持：

```text
CLI syntax/exit UI
  -> Service direct typed handoff
    -> Fins typed upload validation/result owner
      -> dayu.fins.storage pure published-state read
      -> SEC or CN/HK filing workflow
        -> shared ProcessDoclingConverter (UF-FIX09, unchanged)
        -> caller-owned BatchingRepository publication unit
```

| 语义 | 唯一 owner | 本 WU 责任 |
| --- | --- | --- |
| ticker CSV syntax、argparse 值、stdout/stderr、exit mapping | `dayu.cli.commands.fins` | 在 factory 前构造 typed request、调用 Fins validator；不拥有业务规则 |
| filing request、usage code/message、identity、resolved action、failure reason、result summary | `dayu.fins.ingestion_runtime` | 单一 typed contract；CLI/runtime/pipeline 复用 |
| company/source 当前 published state | 新增 storage 窄协议与 FS 实现 | 同一 publication guard 下纯读；fresh absent fast path 零目录/锁创建 |
| company meta freshness/name/alias 决策 | `dayu.fins.pipelines.upload_company_meta` | 拆成纯 decision 与 batch stage，validator/workflow 复用同一 decision |
| suffix 集合 | `upload_batch.FINS_UPLOAD_FILE_SUFFIXES` 与 `docling_upload_service.SUPPORTED_UPLOAD_SUFFIXES` 各自现有 owner | validator 按顺序调用两者的共享 predicate；本 WU 不改集合值 |
| date/year/period 与 filing ID | 现有 ticker/CN period/SEC-CN ID pure helpers | 移到或暴露为同一 Fins validation call chain；不复制、不改 domain |
| converter/取消/cleanup | `docling_process_converter.ProcessDoclingConverter` | 原样保留，只消费其 typed error/cancel outcome |
| staged source、cancel checkpoint、rollback、commit capability transfer | `DoclingUploadService` + `commit_prepared_upload_batch` + `BatchingRepositoryProtocol` | 生命周期不下沉到 CLI；company stage 纳入 caller 的同一 batch |

## 5. Evidence baseline

### 5.1 规范与裁决

- 根 `AGENTS.md`：owner boundary、禁止 fallback/shim/string matching、storage-only access、测试/pyright/README 约束。
- `docs/cli_ci_scenarios.json`：UF-FIX01 accepted requirement 与 UF-PF01
  `real-cli-frozen-report-no-mock-no-fake` rerun policy。
- `docs/cli_ci_oracles.json`：`upload_filing.validation-side-effects`、
  `upload_filing.error-classification`。
- `oracle-adjudication.md`：UF-O03/UF-O04；O03 拒绝 precondition mutation/孤立 company，O04 接受
  usage=`2`、content/storage/runtime=`1`、cancel=`130`。

### 5.2 Frozen observed/raw evidence

已读取 `observed-behavior.md` 对应 UF-003–006、015–019、021–024、026–038、UF-I11–I13，
并核对各 raw `static-index.json` / `integrity-index.json`、`before.json`、`after.json`、
`stdout.txt`、`stderr.txt` 与 SHA-256：

- UF-003–006、026–028、030–032 虽 exit `2`，仍创建 8 项 eager skeleton。
- UF-015–016、021–024 把 usage 错误投影为 runtime exit `1` 并创建 skeleton。
- UF-017、033–038 在失败前发布 AAPL company tree；stderr 只有通用“上传运行时返回失败状态”。
- UF-018–019 不能依据 current company state 正确判定 `--company-name` 是否必需。
- UF-I11–I13 exit `1` 合理，但 raw stderr 分别为 5908/5908/9092 bytes，并含 traceback；
  fresh workspace 留下 company meta 与 16 项 skeleton，source 本身未发布。

### 5.3 生产/测试代码证据

直接核对了 CLI、Service、`DefaultFinsRuntime`、`FinsIngestionRuntime`、job store、storage core/protocol、
SEC/CN pipeline、`DoclingUploadService`、`upload_company_meta`、shared converter，以及对应 CLI/Service/Fins tests。
已有 `commit_prepared_upload_batch` 已正确拥有 precommit cancel/rollback 与 commit capability transfer，
storage batch 已允许 company/source 共享同一 token；不需要补偿删除。

## 6. Contracts / state / public interface

### 6.1 Fins typed usage contract

在 `dayu/fins/ingestion_runtime.py` 新增以下 closed contract（名称在实现中固定，不另设 alias）：

```python
class FinsUploadUsageCode(str, Enum): ...

@dataclass(frozen=True, slots=True)
class FinsUploadUsageFailure:
    code: FinsUploadUsageCode
    message: str

class FinsUploadUsageError(ValueError):
    failure: FinsUploadUsageFailure

@dataclass(frozen=True, slots=True)
class ValidatedFinsUploadFilingRequest:
    request: FinsUploadFilingRequest
    normalized_ticker: NormalizedTicker
    normalized_fiscal_period: str
    document_id: str
    internal_document_id: str
    resolved_action: Literal["create", "update", "delete"]
    published_state: FilingUploadPublishedState
    company_meta_decision: UploadCompanyMetaDecision
```

`dayu/fins/ingestion_runtime.py` 是 pure types/validator 的唯一归属，只定义：

```python
def validate_fins_upload_filing_request(
    request: FinsUploadFilingRequest,
    *,
    published_state: FilingUploadPublishedState,
) -> ValidatedFinsUploadFilingRequest: ...

def fins_upload_usage_failure(
    code: FinsUploadUsageCode,
    *,
    file_name: str | None = None,
) -> FinsUploadUsageFailure: ...
```

`dayu/fins/service_runtime.py` 只拥有 concrete workspace assembly wrapper，名称与签名固定为：

```python
def prevalidate_fins_upload_filing_request_for_workspace(
    request: FinsUploadFilingRequest,
    *,
    workspace_root: Path,
) -> ValidatedFinsUploadFilingRequest: ...
```

wrapper 只装配 `FsFilingUploadStateRepository(create_directories=False)`、按 deterministic request identity
读取 snapshot，再调用 ingestion owner 的 pure validator；不构造 `DefaultFinsRuntime`，不定义 code/message，
不把 concrete storage type 泄漏到 validator 或 CLI。不得再定义第二个 workspace validator 名字或兼容 alias。

`FinsUploadUsageCode` 的成员是以下**穷尽闭集**，不得在实现时添加 ad-hoc 成员：

```text
EMPTY_TICKER
INVALID_TICKER
INVALID_TICKER_ALIAS
INVALID_SOURCE_KIND
INVALID_ACTION
TOO_MANY_FILES
MISSING_FISCAL_YEAR
INVALID_FISCAL_YEAR
MISSING_FISCAL_PERIOD
FISCAL_PERIOD_TOO_LONG
UNSUPPORTED_CN_FISCAL_PERIOD
FILING_DATE_TOO_LONG
REPORT_DATE_TOO_LONG
COMPANY_NAME_TOO_LONG
TOO_MANY_TICKER_ALIASES
MISSING_FILES
FILE_NOT_FOUND
FILE_NOT_REGULAR
FILE_SUFFIX_NOT_ALLOWED
CONVERTER_SUFFIX_UNSUPPORTED
COMPANY_NAME_REQUIRED
CREATE_TARGET_EXISTS
UPDATE_TARGET_MISSING
```

`fins_upload_usage_failure` 是 code→actionable message 唯一 source mapping；除四个文件相关 code
（`FILE_NOT_FOUND`、`FILE_NOT_REGULAR`、`FILE_SUFFIX_NOT_ALLOWED`、
`CONVERTER_SUFFIX_UNSUPPORTED`）可接收已经去路径化的 basename 外，其余文案完全由 code 决定。
message 最大 240 字符；不得含绝对路径。CLI、Service、runtime、runner、workflow 都不得自行拼 usage 文案或按
message 分支。

| Frozen scenario | Exact code | `fins_upload_usage_failure` 的 exact message |
| --- | --- | --- |
| UF-003、UF-006 | `EMPTY_TICKER` | `--ticker 不能为空，请提供公司代码` |
| UF-004、UF-005 | `INVALID_TICKER` | `--ticker 无法识别，请提供有效公司代码` |
| UF-015 | `MISSING_FISCAL_YEAR` | `--fiscal-year 不能为空` |
| UF-016、UF-022 | `MISSING_FISCAL_PERIOD` | `--fiscal-period 不能为空` |
| UF-017、UF-019 | `MISSING_FILES` | `create/update 上传必须提供 --files` |
| UF-018 | `COMPANY_NAME_REQUIRED` | `当前公司缺少有效元数据；create/update 必须提供 --company-name` |
| UF-021 | `INVALID_FISCAL_YEAR` | `--fiscal-year 必须是非负整数` |
| UF-023 | `FISCAL_PERIOD_TOO_LONG` | `--fiscal-period 长度不能超过 240 个字符` |
| UF-024 | `UNSUPPORTED_CN_FISCAL_PERIOD` | `CN/HK --fiscal-period 仅支持 Q1、Q2、Q3、Q4、H1、FY` |
| UF-026 | `FILE_NOT_FOUND` | `上传文件不存在：{basename}` |
| UF-027 | `FILE_NOT_REGULAR` | `上传路径不是普通文件：{basename}` |
| UF-028、UF-030、UF-031、UF-032 | `FILE_SUFFIX_NOT_ALLOWED` | `上传文件后缀不在命令允许范围：{basename}` |
| UF-033、UF-034、UF-035、UF-036、UF-037、UF-038 | `CONVERTER_SUFFIX_UNSUPPORTED` | `当前上传转换器不支持该文件后缀：{basename}` |

表中顺序也是冲突输入的判定优先级：ticker → year → period → files presence → path/type → 两个 suffix
owner → state/company。其余闭集成员由同一 mapping 提供字段名明确的固定中文文案；owner tests 必须逐成员
exhaustive 覆盖，并断言不存在 default/unknown 分支。该表只前移现有判定，不改变 year/period domain 或
任一 allow-list 成员。

CLI usage stderr 只允许一条现有 renderer 路径：

```python
except FinsUploadUsageError as exc:
    usage_failure = exc.failure
    render_cli_error(f"dayu-cli upload_filing: {usage_failure.message}")
    return EXIT_USAGE_ERROR
```

`render_cli_error` 负责追加唯一换行，因此 exact stderr 是
`f"dayu-cli upload_filing: {usage_failure.message}\n"`，stdout 为空。这里消费的是
`FinsUploadUsageFailure`，绝不能与 runtime 的 `FinsUploadFailureReason` 混用。该 catch 必须紧随既有 usage
catch，位于 `FinsDirectStreamProtocolError`、`KeyboardInterrupt` 和最终 generic `except Exception` 之前；
generic branch 只映射 runtime/content/storage failure 为 exit `1`。

### 6.2 State-aware validation order

严格顺序如下，任一步失败都不得读取/创建 workspace state：

1. 校验 request 类型/source kind/action、ticker/aliases、字段 bounds、file count。
2. filing create/update/auto 要求 fiscal year/period/files；delete 不要求 files。
3. year 保持当前非负规则；US period 只 trim/uppercase/bounded；CN/HK 调当前
   `normalize_cn_fiscal_period`；filing/report date 不新增 domain。
4. path 解析、exists、regular file；调用 `FINS_UPLOAD_FILE_SUFFIXES` owner predicate，再调用
   `SUPPORTED_UPLOAD_SUFFIXES` owner predicate。两个常量内容不变：UF-030–032 仍被第一层拒绝，
   UF-033–038 改为第二层在 mutation 前拒绝。
5. 用现有 SEC/CN ID helper 生成 target identity；不得在 CLI 重建 digest。
6. 通过单次 `FilingUploadStateRepositoryProtocol.read_filing_upload_state(...)` 读取 company/source。
7. `auto` 依 source absent/present 解析为 create/update；显式 create/update/delete 保持原动作。
8. 把当前 `DoclingUploadService` 已有 precondition 原样前移：create-existing 且不允许当前 overwrite
   规则、update-missing 且 `overwrite=False` 均为 typed usage；不引入 UF-FIX02 的新 identity/action 规则。
9. 调用 `resolve_upload_company_meta_decision(...)`：resolved create/update 且 company meta 缺失/陈旧时
   要求非空 company name；fresh resolver meta 时忽略本次 name/alias；delete 不需要 company。

### 6.2.1 Exact validated handoff 与 authoritative recheck

签名和传导链固定如下，不保留旧 kwargs wrapper：

```python
# CLI
def _prevalidate_upload_filing_request(
    args: ParsedCliArgs, *, workspace_root: Path
) -> ValidatedFinsUploadFilingRequest | None: ...

def _open_direct_stream(
    *,
    args: ParsedCliArgs,
    service: FinsDirectCommandService,
    cancellation_token: _CliFinsCancellationToken,
    download_request: FinsDownloadRequest | None,
    upload_filing_request: ValidatedFinsUploadFilingRequest | None,
) -> ValidatedFinsEventStream: ...

# Service
def FinsDirectCommandService.upload_filing(
    self,
    request: ValidatedFinsUploadFilingRequest,
    *,
    cancellation_token: CancellationToken | None = None,
) -> ValidatedFinsEventStream: ...

# Runtime/runner
def FinsIngestionRuntime.upload(
    self,
    request: FinsUploadRequest | ValidatedFinsUploadFilingRequest,
    *,
    cancellation_token: CancellationToken | None = None,
) -> ValidatedFinsEventStream: ...

def FinsUploadRunner.run_upload(
    self,
    request: ValidatedFinsUploadFilingRequest | FinsUploadMaterialRequest,
    *,
    cancellation_checker: FinsJobCancellationChecker,
) -> FinsUploadResultSummary: ...

# SEC/CN facade；两侧签名对称
def upload_filing(
    self,
    request: ValidatedFinsUploadFilingRequest,
    *,
    cancellation_checker: CancellationToken | None = None,
) -> JsonObject: ...

async def upload_filing_stream(
    self,
    request: ValidatedFinsUploadFilingRequest,
    *,
    cancellation_checker: CancellationToken | None = None,
) -> AsyncIterator[UploadFilingEvent]: ...
```

SEC 模块级 `run_upload_filing_stream` 同样改为 `request: ValidatedFinsUploadFilingRequest` 加 cancellation
keyword；CN/HK facade 机械透传同一 typed object。CLI preflight 的对象必须原样经过 Service 和 Runtime 到 runner，
不得还原成散参或重建 request。

workflow 收到的 CLI/runtime preflight **不是 commit authorization**。SEC 与 CN/HK 在任何 prepare/mutation 前：

1. 仅复用 preflight 中由 immutable raw request 确定的 canonical ticker/document ID 定位 fresh state；
2. 调用同一个 `FilingUploadStateRepositoryProtocol.read_filing_upload_state` 取得 fresh snapshot；
3. 对 `preflight.request` 再调用同一 `validate_fins_upload_filing_request`，得到 `authoritative_request`；
4. 只允许 `authoritative_request.resolved_action/published_state/company_meta_decision` 驱动 prepare/stage/commit。

旧 snapshot、旧 resolved action、旧 company decision 必须丢弃；它们不得成为 commit authorization、fallback 或
concurrency repair。canonical ticker/document ID 只是 raw request 的 deterministic identity；authoritative recheck
必须断言 fresh result 的 identity 与其一致，否则 fail closed。recheck 后仍发生的并发由 batch/storage owner 拒绝，
不得补偿重试或删除。

所有非 CLI filing upload consumer 也走同一边界：`FinsIngestionRuntime.upload(raw filing)`、
`prepare_observed_upload`、`start_observed_upload`、legacy `start_upload` 在 stream producer、observation registration、
job create 或业务 runner 启动前调用同一 storage protocol + pure validator，失败同步抛
`FinsUploadUsageError`。只有 CLI 把它映射为 exit `2`；Service/tool/wait consumer 原样得到 typed error，并由其
既有调用边界处理。Host/Engine 不新增 error type、schema、event 或映射。

### 6.3 最小 non-mutating storage contract（已裁决，非 open question）

必须新增纯读协议；不允许 CLI 路径拼接或两个 repository 的非一致 loose composition：

```python
@dataclass(frozen=True, slots=True)
class FilingUploadPublishedState:
    company_meta: CompanyMeta | None
    source_meta: Mapping[str, JsonValue] | None

class FilingUploadStateRepositoryProtocol(Protocol):
    def read_filing_upload_state(
        self, ticker: str, document_id: str
    ) -> FilingUploadPublishedState: ...
```

- FS 实现必须按唯一顺序执行：先规范 external ticker，再调用 storage owner 新增的 private tri-state helper
  `_ticker_dir_if_present_for_read(external_ticker) -> Path | None`。它复用 `_fs_identity.py` 新增的
  `_identity_directory_if_present_for_read(...) -> Path | None` 及既有 descriptor 校验规则：namespace/identity
  directory absent 返回 `None`，existing valid 返回 canonical locator，symlink/descriptor mismatch/corruption
  fail closed。只有 `None` 可短路为 `(None, None)`；此分支不得调用 `_acquire_publication_guard`，不得创建
  `.dayu`、`portfolio`、lock。既有 `_ticker_dir_for_read` 的真实契约是 absent 时仍返回确定性 locator，
  不得把它误当 absent predicate，也不得修改其既有 contract。
- canonical root existing 时才 `_acquire_publication_guard(external_ticker)` **一次**，在同一个 guard 内依次调用
  `_get_company_meta_unguarded(external_ticker)` 与
  `_get_source_meta_unguarded(external_ticker, document_id, SourceKind.FILING)`，分别只把 exact
  `FileNotFoundError` 投影为该成员 `None`，最后 release 同一个 guard。
- canonical root 是 symlink/broken symlink、identity descriptor 缺失/不匹配、非目录或 meta corruption 时必须由
  既有 canonical read helper/unguarded reader fail closed；不得把这些情况当 absent，不得 fallback 到
  `Path.exists()`、raw path 或新建空 root。
- 只吞掉 exact `FileNotFoundError` 为 absent；corruption、identity mismatch、permission/I/O/lock error 原样失败，
  不伪装成新公司。
- 这是 validation/read model，不是 commit concurrency guarantee；workflow 在 prepare 前用同一协议重读，
  最终 mutation 仍由 batch capability/commit fail-closed。禁止从 timestamp、目录偶然顺序或日志反推 state。
- SEC、CN、HK 使用完全相同的 `FilingUploadPublishedState`：`source_meta` 都是 filing source 的
  `Mapping[str, JsonValue] | None`，由同一 FS implementation/guard 读取；CN/HK 不保留 `_safe_get_upload_document_meta`
  作为第二状态 owner，market 只影响 period/ID pure derivation，不影响 snapshot 语义。

### 6.4 Lazy bootstrap contract

- `DefaultFinsRuntime.create` 使用 `build_fs_repository_set(..., create_directories=False)`；真正的首次 mutation
  仍由 `begin_batch` 的 `_ensure_batch_storage_dirs` 创建 infrastructure。
- `dayu/fins/storage/_fs_repository_factory.py::build_fs_repository_set` 已有并已透传
  `create_directories: bool = True`；本 WU 只在 `DefaultFinsRuntime.create` 传 `False`，**不修改** factory 文件、
  不新增 wrapper/overload。
- `FsFinsIngestionJobStore.__post_init__` 不创建目录；`create_job` 在获取 job lock 前调用私有
  `_ensure_root_for_write()`。read/save missing 不为不存在的 job store 创目录。
- `SecPipeline`、`CnPipeline` 及 SEC/CN/HK download adapter builder 的内部 fallback repository set 必须使用
  `build_fs_repository_set(..., create_directories=False)`，并让默认具体 repositories 共享该 lazy set。
  即使 caller 已注入全部具体 repositories，也不得先构造一个未使用的 eager set。首次真实写仍只由
  `begin_batch`/repository write owner 创建目录；不新增 repository-set public 参数或兼容 wrapper。
- direct upload 不创建 legacy job；合法内容失败若 publication batch 尚未开始，fresh workspace 保持空。
- 该变化只消除 eager side effect，不改变 batch recovery、download/preprocess 写路径或 durable legacy job schema。

### 6.5 Company/source single publication state machine

`dayu/fins/pipelines/docling_upload_service.py` 继续是 action/overwrite/prepare 分支的唯一 owner：

```python
def resolve_upload_action(
    requested_action: str | None,
    previous_meta: Mapping[str, JsonValue] | None,
) -> str: ...

class UploadOverwritePrecondition(str, Enum):
    ALLOWED = "allowed"
    CREATE_TARGET_EXISTS = "create_target_exists"
    UPDATE_TARGET_MISSING = "update_target_missing"

def evaluate_upload_overwrite_precondition(
    *,
    action: str,
    previous_meta: Mapping[str, JsonValue] | None,
    overwrite: bool,
) -> UploadOverwritePrecondition: ...
```

`validate_fins_upload_filing_request` 与 SEC/CN/HK authoritative recheck 都必须调用这两个同一 module
symbols；不得复制 auto/create/update 或 overwrite 分支。validator 只把两个非 allowed typed disposition
映射为 `CREATE_TARGET_EXISTS` / `UPDATE_TARGET_MISSING` usage code。`prepare_upload` 也调用同一 helper 保持
direct service invariant，但不拥有第二套条件。本 WU 只把现有判断前移并类型化，不改变 UF-FIX02/08/10 的
action、identity、repair 或 overwrite 业务语义。

现有 `prepare_upload` 的真实分支在本 plan 固定，不留实现时再判断：

- cancellation 已生效时先返回 `UploadOperationResult(status="cancelled")`，不开 batch；
- resolved `delete` 直接返回 `_PreparedDeleteMutation`，不要求 files、不计算 fingerprint、不转换；只有随后
  `publish_prepared_upload` 在 caller-owned batch 内执行 source delete；
- 非 delete 先验证 files、消费 authoritative `previous_meta`、执行同一 overwrite precondition，再读取原文件并
  计算 fingerprint；fingerprint 相同且 `overwrite=False` 时返回
  `UploadOperationResult(status="skipped")`，不产生 prepared mutation、不开 batch、不 stage company；
- 其余 create/update 完成 async shared converter 后返回 `_PreparedAssetMutation`；转换失败/取消发生在
  `begin_batch` 前。

SEC 与 CN/HK filing 使用同一状态机：

```text
validate/re-read published state (no mutation)
  -> resolve action + company decision
  -> prepare_upload(previous_meta=state.source_meta)
       -> cancelled | skipped: return, no batch
       -> prepared delete: begin one batch, source delete only
       -> prepared create/update: begin one batch
  -> stage company decision on same BatchToken (create/update only)
  -> publish_prepared_upload on same BatchToken
       -> cancelled/precommit error: rollback exactly once
       -> final cancel checkpoint passes: transfer capability to commit_batch
       -> commit begins: caller never rollback and never lets late cancel rewrite result
```

- fresh company success：company meta、identity descriptor、source/blob/meta 同一 commit 可见。
- existing fresh company：decision=`keep`，source 在同一 publication unit 更新，company 不重写。
- existing stale company：refresh stage 与 source 使用同一 token；失败保持旧 company/source 同时不变。
- skip：fingerprint owner 在 `DoclingUploadService.prepare_upload`；不 stage company，不 begin batch。
- delete：只由 source publication owner处理，不创建/刷新 company；missing/delete semantics 不在本 WU 重定义。
- cancel：converter cancel 继续返回 canonical cancelled；publication 前零 batch，publication 内交给
  `commit_prepared_upload_batch` rollback。
- commit：保留现有 first-committer/capability transfer；不增加补偿删除、二次 rollback 或 commit 后 cancel。

### 6.6 Typed bounded failure reason

在 `dayu/fins/ingestion_runtime.py` 新增：

```python
class FinsUploadFailureKind(str, Enum):
    CONTENT = "content"
    STORAGE = "storage"
    RUNTIME = "runtime"

class FinsUploadFailureCode(str, Enum): ...

@dataclass(frozen=True, slots=True)
class FinsUploadFailureReason:
    kind: FinsUploadFailureKind
    code: FinsUploadFailureCode
    message: str
    retry_hint: str | None
```

- `message` 与 `retry_hint` 各最大 240 字符，拒绝控制字符、路径分隔信息、traceback/raw exception。
- `DoclingConversionError.kind` 通过 exhaustive enum mapping 变为 content code；只用其 fixed
  `safe_message` 选择 owner 文案，不复制 cause/exit path。
- storage typed/OSError 映射 storage code；未知异常映射固定 runtime code/message，并只在 operator log 保留 cause。
- workflow catch 顺序固定为：先处理 `DoclingConversionCancelledError`/canonical cancelled outcome，再
  `DoclingConversionError`，再 storage typed error/`OSError`，最后才是 generic `Exception`；具体 typed catch
  不得置于 generic 之后，也不得用 `str(exc)`/substring 重新分类。
- SEC/CN pipeline failed result 精确包含 `failure` object，不再写 `message=str(exc)` / `error=str(exc)`。
- `FinsUploadPipelineResult.from_pipeline_json` exact-key/type 校验 failure；`status="failed"` 必须有 failure，
  其它 status 禁止带 failure。
- `FinsUploadResultSummary.failure_reason`、direct RESULT、legacy durable result/failure summary 从同一对象派生；
  CLI 只渲染 `error_message`/typed details，exit 仍由 terminal status owner 机械决定。

## 7. Exact production files and symbols

### 新增

- `dayu/fins/storage/fs_filing_upload_state_repository.py`
  - `FsFilingUploadStateRepository.__init__(..., create_directories: bool = False)`
  - `FsFilingUploadStateRepository.read_filing_upload_state`
- `dayu/fins/storage/_fs_filing_upload_state_core.py`
  - `_FsFilingUploadStateMixin.read_filing_upload_state`

### 修改

- `dayu/fins/ingestion_runtime.py`
  - `FinsUploadFilingRequest` 邻近新增 usage/validated/failure types 与 validator
  - `FinsUploadPipelineResult.from_pipeline_json`
  - `FinsUploadResultSummary`
  - `FinsUploadRunner.run_upload`
  - `FinsIngestionRuntime.create` / `upload` / `prepare_observed_upload` / `start_observed_upload` / `start_upload`
  - 私有 `_validate_runtime_upload_request` 作为上述入口的唯一 filing pre-business helper
  - `_direct_upload_terminal_events`、upload summary JSON bounds
  - `FsFinsIngestionJobStore.__post_init__` / `create_job` / `_ensure_root_for_write`
- `dayu/fins/storage/repository_protocols.py`
  - `FilingUploadPublishedState`、`FilingUploadStateRepositoryProtocol`
- `dayu/fins/storage/_fs_identity.py`
  - 新增 private `_identity_directory_if_present_for_read`，复用既有 identity/descriptor validation，
    以 `Path | None` 精确表达 valid/absent，corruption fail closed；不修改 `_identity_directory_for_read` 契约
- `dayu/fins/storage/_fs_storage_infra.py`
  - 新增 private `_ticker_dir_if_present_for_read`，只委托 identity owner 的 tri-state helper，不 mkdir/lock
- `dayu/fins/storage/_fs_storage_core.py`
  - 组合 `_FsFilingUploadStateMixin`
- `dayu/fins/storage/__init__.py`
  - 导出新增窄协议/实现；不是兼容 re-export
- `dayu/fins/service_runtime.py`
  - `prevalidate_fins_upload_filing_request_for_workspace` concrete assembly wrapper
  - `DefaultFinsRuntime` 新增 `filing_upload_state_repository` 字段并在 `create` 用同一个
    `repository_set(create_directories=False)` 构造；`get_ingestion_runtime` 把同一实例注入 runtime、SEC、CN
  - `ProductionFinsUploadRunner.run_upload` / `_run_filing_upload` 接收并透传
    `ValidatedFinsUploadFilingRequest`，不还原散参
- `dayu/fins/pipelines/upload_company_meta.py`
  - 以 `UploadCompanyMetaDecision`、`resolve_upload_company_meta_decision`、
    `stage_upload_company_meta_decision` 取代读写耦合的 `upsert_company_meta_for_upload`
- `dayu/fins/pipelines/docling_upload_service.py`
  - 将 `_validate_source_files` 提升为 Fins validator 可复用的 public pure predicate
  - 保留并共享 `resolve_upload_action`；新增 `UploadOverwritePrecondition` 与
    `evaluate_upload_overwrite_precondition`
  - `prepare_upload(..., previous_meta=...)` 不再自行读取 state
  - `commit_prepared_upload_batch` 生命周期不改，只扩展 docstring/断言同 batch 使用
- `dayu/fins/pipelines/sec_pipeline.py`
  - constructor 与 `build_sec_download_adapter` 的 fallback repository set 使用 `create_directories=False`
  - `SecPipeline.__init__(..., filing_upload_state_repository: FilingUploadStateRepositoryProtocol, ...)`
  - `SecPipeline.upload_filing` / `upload_filing_stream` 改收 typed validated request，并把同一 repository identity
    与 request 透传给 workflow
- `dayu/fins/pipelines/sec_upload_workflow.py`
  - `SecUploadWorkflowHost` 新增只读 `_filing_upload_state_repository` typed property
  - `run_upload_filing_stream(host, *, request, cancellation_checker)` fresh snapshot authoritative recheck、
    单 publication unit + typed failure
  - `run_upload_material_stream` 仅做 failure projection 回归所需的共用 helper 迁移；material 原子业务不扩 scope
- `dayu/fins/pipelines/cn_pipeline.py`
  - constructor、`build_cn_download_adapter`、`build_hk_download_adapter` 的 fallback repository set 使用
    `create_directories=False`
  - `CnPipeline.__init__(..., filing_upload_state_repository: FilingUploadStateRepositoryProtocol, ...)` 注入与 SEC
    相同 repository instance
  - `upload_filing` / `upload_filing_stream` 改收 typed validated request；CN/HK 共用同一 snapshot/recheck，
    单 publication unit + typed failure
  - material 仅跟随共用 failure helper，不改变 material transaction 语义
- `dayu/cli/commands/fins.py`
  - `_run_fins_direct_command_async` 在 factory 前调用 `_prevalidate_upload_filing_request`
  - `_open_direct_stream` / `_upload_filing_stream` 只接受并透传 `ValidatedFinsUploadFilingRequest`
  - 删除 CLI-owned `_validated_upload_files` 的业务判定；保留纯 argparse/syntax mapping
  - `run_fins_direct_command` 按 6.1 exact renderer/catch 顺序映射 `FinsUploadUsageError` 为 exit `2`
- `dayu/service/fins_direct.py`
  - `FinsDirectCommandService.upload_filing` 改为接收 `ValidatedFinsUploadFilingRequest`，不重建字段
  - runtime stream identity/cancellation handoff 不改

### 明确不修改

- `dayu/fins/storage/_fs_repository_factory.py`：`build_fs_repository_set` 已有 `create_directories` 参数并完成透传；
  Q2 resolved，禁止为本 WU 修改或加 wrapper。
- `dayu/host/**`、`dayu/engine/**`：非 CLI consumer 只收到现有 Fins typed exception，不新增跨层 contract。

## 8. Implementation slices（每 slice 同时含 owner test 与实现）

### S1 — Pure published-state read + lazy bootstrap

**实现文件**：storage 新文件、`repository_protocols.py`、`_fs_identity.py`、`_fs_storage_infra.py`、
`_fs_storage_core.py`、`storage/__init__.py`、`ingestion_runtime.py` job store、`service_runtime.py` runtime create、
`sec_pipeline.py` / `cn_pipeline.py` lazy fallback composition。

**owner tests**：`tests/fins/test_fins_storage_atomicity.py`、`tests/fins/test_fins_storage_provider.py`、
`tests/fins/test_fins_ingestion_runtime.py`。

Exact assertions：

- fresh absent read 返回 both `None`，workspace 不存在时调用后仍不存在，且 lock acquire helper 未调用。
- fresh absent 后路径级断言 `.dayu`、`portfolio`、batch lock root/publication lock 全部不存在。
- canonical ticker root symlink、broken symlink、identity descriptor 缺失/错配、company/source corrupt meta 均
  fail closed，guard/reader error 不降级为 absent。
- existing ticker 在一个 publication guard 内返回 company/source 同版 snapshot；guard acquire/release 各一次，
  两个 unguarded reader 在该 guard 内各调用一次。
- company missing/source present、company present/source missing 都分别精确返回；source fixture 必须发布至少一个
  真实业务文件并通过 complete-source commit validation，不得用空 `files` 假造 durable source；corrupt meta 不降级为 absent。
- `DefaultFinsRuntime.create` + `get_ingestion_runtime` 在 fresh root 不创建任何 entry。
- owner test 分别覆盖 `SecPipeline`、`CnPipeline` 与 SEC/CN/HK adapter builder 的默认 fallback composition：
  constructor 本身零目录，首次 begin/write 后才创建 infrastructure；全部具体 repositories 已注入时不构造
  未使用的 eager repository set。
- `begin_batch` 后 batch/recovery/lock 目录仍按现行协议创建；legacy `create_job` 首写才创建 jobs root。
- **direct download**：`FinsIngestionRuntime.download` 在 fresh root 通过真实 repository/batch 首写 source，成功后有
  source durable tree、无 `.dayu/fins_ingestion/jobs`。
- **runtime/durable download**：`start_download` 在 fresh root 先由 `create_job` 创建 jobs root，再由 executor/adapter
  完成 source publication；queued/terminal schema 与 recovery assertions 不变。
- **direct preprocess**：先 seed complete source，再由 `FinsIngestionRuntime.preprocess` 首写 processed tree；不依赖
  job root 预存在。
- **legacy preprocess/upload job**：`start_preprocess`、`start_upload` 在 fresh jobs root 上均能 create/save terminal
  record；`FsFinsIngestionJobStore.create_job` 单独断言 lock 前 mkdir，而 missing read/save 不创建 root。

### S2 — Unified filing validation before Service factory

**实现文件**：`ingestion_runtime.py`、`service_runtime.py`、`upload_company_meta.py`、
`docling_upload_service.py`、`dayu/cli/commands/fins.py`、`dayu/service/fins_direct.py`。

**owner tests**：`tests/fins/test_fins_ingestion_runtime.py`、`tests/fins/test_docling_upload_service.py`、
`tests/fins/test_sec_pipeline_upload_filing_stream.py`（company decision pure tests）、
`tests/service/test_fins_direct.py`、`tests/cli/test_fins_commands.py`、`tests/cli/test_import_boundary.py`。

Exact assertions：

- UF-003–006、015–019、021–024、026–038 参数逐项返回 exact `FinsUploadUsageCode` 和 bounded message。
- 四个文件相关 code 的 exact message owner assertions 分别覆盖：`FILE_NOT_FOUND` →
  `上传文件不存在：report.pdf`、`FILE_NOT_REGULAR` → `上传路径不是普通文件：report.pdf`、
  `FILE_SUFFIX_NOT_ALLOWED` → `上传文件后缀不在命令允许范围：report.exe`、
  `CONVERTER_SUFFIX_UNSUPPORTED` → `当前上传转换器不支持该文件后缀：report.doc`；传入值均为已经去路径化的
  basename，四者之外的 code 不接收文件名派生文案。
- 每个 CLI case：exit `2`、stdout `""`、stderr 恰一行 `dayu-cli upload_filing: <reason>\n`、
  factory calls `[]`、service calls `[]`、workspace tree unchanged。
- 每个 CLI case 的 stderr 必须来自
  `render_cli_error(f"dayu-cli upload_filing: {usage_failure.message}")`；断言 usage failure 与 runtime
  `failure_reason` 是不同类型，且新 catch 位于 generic `Exception` 之前。
- file validation 顺序稳定：missing > not regular > batch suffix > converter suffix；030–032 和 033–038
  的两套 allow-list 值完全不变。
- US period 不调用 CN normalizer；CN/HK 只接受当前闭集；year `0` 仍按当前非负域处理；date 不新校验。
- auto absent/create、auto present/update；create-present/update-absent 复用当前 overwrite precondition；
  fresh/stale company 缺 name 失败，fresh resolver company 缺 name 成功。
- CLI 不 import `dayu.fins.storage`，不访问 `portfolio` 路径，不从 message/string 决定 code。
- CLI preflight → Service → Runtime → Runner 的 `ValidatedFinsUploadFilingRequest` object identity 保持；不重建、
  默认或兼容旧 kwargs。
- raw non-CLI filing 分别调用 `upload`、`prepare_observed_upload`、`start_observed_upload`、legacy `start_upload`
  时，在 producer/observation/job/runner 前抛 exact `FinsUploadUsageError`，零业务 mutation；这些入口不映射 exit code。

### S3 — SEC/CN/HK company + source atomic publication

**实现文件**：`upload_company_meta.py`、`docling_upload_service.py`、
`sec_pipeline.py`、`sec_upload_workflow.py`、`cn_pipeline.py`、`service_runtime.py`。

**owner tests**：`tests/fins/test_sec_pipeline_upload_filing_stream.py`、`tests/fins/test_cn_pipeline.py`、
`tests/fins/test_docling_upload_service.py`、`tests/fins/test_fins_storage_atomicity.py`、
`tests/fins/test_fins_ingestion_runtime.py`（DefaultFinsRuntime composition owner）。

Exact assertions（SEC 与 CN 至少各一组；HK 复用 CN facade 并单独断言 market route）：

- fresh success：company/source writer 收到同一 `BatchToken` identity，只 `begin=1/commit=1/rollback=0`；
  commit 前 published reads 均 absent，commit 后两者均 visible。
- SEC 与 CN/HK facade 都收到 `service_runtime` 注入的同一个
  `FilingUploadStateRepositoryProtocol` instance；HK 以真实 HK normalized ticker 断言与 CN 相同 snapshot shape、
  fresh authoritative recheck 和 publication state machine，不用 CN-only fake 代替。
- workflow 必须发生 fresh state read + 同一 pure validator recheck；并发夹具在 CLI preflight 后改变 source state时，
  断言旧 resolved action/company decision 被丢弃，只有 fresh validated result 进入 prepare/stage。
- existing fresh company update：company bytes/SHA 不变，source 更新成功；仍只有一个 publication batch。
- existing stale company update：company refresh 与 source 同 commit；在 company stage、source stage、final checkpoint、commit
  注入失败时 before/after company/source tree 和每个 file SHA 全相同。
- converter failure（fresh/existing）发生在 `begin_batch` 前；无 company/source mutation。
- skip：`begin=0`，company 不写，source SHA 不变；delete：company SHA 不变，source 在单 batch 删除。
- company stage 写 staging 中途失败：`rollback=1/commit=0`，published company/source before/after tree 与逐文件
  SHA-256 完全相同，batch staging/journal 只按既有 rollback/recovery contract 收口。
- delete source stage 失败：`rollback=1/commit=0`，company tree/SHA 不变、source 完整恢复且所有文件 SHA 不变。
- precommit cancel/stage error：`rollback=1/commit=0`；commit 开始后的 late cancel 不 rollback、不改 completed。
- rollback failure 保留 primary cause/recovery evidence；禁止补偿 delete 或第二 batch。
- `DefaultFinsRuntime.get_ingestion_runtime` owner test 构造一次 production composition，断言 SEC upload、CN upload、
  CN download、HK download 持有的 `ProcessDoclingConverter` 均 `is` 同一实例，重复调用返回同一 ingestion runtime；
  operation cancellation token 从 runtime→runner→SEC/CN facade→`DoclingUploadService.prepare_upload`→converter 保持
  object identity，且 `prepare_upload` 仍为 async/await 路径。禁止以 caller-local fake converter 证明共享装配事实。

### S4 — Typed bounded actionable failure end-to-end

**实现文件**：`ingestion_runtime.py`、`service_runtime.py`、`sec_upload_workflow.py`、
`cn_pipeline.py`、`dayu/cli/commands/fins.py`。

**owner tests**：`tests/fins/test_fins_ingestion_runtime.py`、
`tests/fins/test_sec_pipeline_upload_filing_stream.py`、`tests/fins/test_cn_pipeline.py`、
`tests/service/test_fins_direct.py`、`tests/cli/test_fins_commands.py`。

Exact assertions：

- failed pipeline JSON 缺 failure、未知 key/code/kind、过长/control/pathful message 均 fail closed；非 failed 带 failure 也拒绝。
- 每个 `DoclingConversionFailureKind` exhaustive 映射到 content code；storage/runtime 分别映射自己的 code。
- 通过可观察 marker 断言 catch 顺序为 cancelled → typed Docling → typed storage/OSError → generic Exception；
  typed failure 不落入 generic mapping。
- pipeline result、runtime summary、direct RESULT、durable failure summary 的 kind/code/message 完全相同。
- CLI content/storage/runtime 均 exit `1`，cancel exit `130`；CLI 只消费 typed RESULT，不捕获内容错误为 usage。
- UF-I11–I13 形状：stderr 不含 `Traceback`、绝对 workspace/repo path、异常 repr；reason `<=240`，
  明确提示文件不可解析/损坏或重试动作；fresh tree 无 company/source/job/skeleton。
- operator log 可以保留 internal cause，但 public event/stdout/stderr/durable summary 不得包含 cause。

### S5 — Documentation + closeout verification

只在 S1–S4 代码和 tests 通过后更新 README 并执行第 10 节验证；不得在实现前写未来态 README。

## 9. Tests and verification commands

实现每个 slice 后先跑对应 owner tests；最终必须执行：

```bash
source .venv/bin/activate
pytest tests/cli/test_fins_commands.py tests/cli/test_import_boundary.py \
  tests/service/test_fins_direct.py \
  tests/fins/test_fins_ingestion_runtime.py \
  tests/fins/test_fins_storage_atomicity.py \
  tests/fins/test_fins_storage_provider.py \
  tests/fins/test_docling_upload_service.py \
  tests/fins/test_sec_pipeline_upload_filing_stream.py \
  tests/fins/test_cn_pipeline.py -q
python -m pyright dayu/ tests/ utils/
```

覆盖率不能只看 aggregate；对每个新增/修改生产文件执行 `coverage report --include=<file>`，逐文件
`>=80%`。至少显式报告 storage 新文件、`ingestion_runtime.py`、`service_runtime.py`、
`upload_company_meta.py`、`docling_upload_service.py`、SEC/CN workflow、CLI/Service 文件。最后执行
`git diff --check`，并检查无 production `hasattr/getattr`、string classification、补偿删除、compat shim。

## 10. UF-PF01 focused-real evidence（实现完成后，no mock/no fake）

### 10.1 Exact argv matrix

使用真实 `.venv/bin/dayu-cli`、真实 `DefaultFinsRuntime`、真实 storage；每 case 使用独立 fresh
`$CASE_BASE`。除 executable 与 frozen bundle root 重定位外，argv 精确为：

| IDs | `upload_filing --base $CASE_BASE` 后的 exact argv |
| --- | --- |
| UF-003 | `--ticker ""` |
| UF-004 | `--ticker ../../etc/passwd` |
| UF-005 | `--ticker ABCDEFGHI` |
| UF-006 | `--ticker AAPL,` |
| UF-015 | `--ticker AAPL --fiscal-period FY` |
| UF-016 | `--ticker AAPL --fiscal-year 2024` |
| UF-017 | `--ticker AAPL --fiscal-year 2024 --fiscal-period FY --company-name "Apple Inc."` |
| UF-018 | `--ticker AAPL --files $INPUT/probe.txt --fiscal-year 2024 --fiscal-period FY` |
| UF-019 | `--ticker AAPL --fiscal-year 2024 --fiscal-period FY --company-name ""` |
| UF-021 | `--ticker AAPL --fiscal-year -1 --fiscal-period FY` |
| UF-022 | `--ticker AAPL --fiscal-year 2024 --fiscal-period ""` |
| UF-023 | `--ticker AAPL --fiscal-year 2024 --fiscal-period <exact 300-char X value from frozen argv>` |
| UF-024 | `--ticker 600519 --fiscal-year 2024 --fiscal-period 9M` |
| UF-026 | `--ticker AAPL --fiscal-year 2024 --fiscal-period FY --company-name "Apple Inc." --files $INPUT/missing.pdf` |
| UF-027 | `--ticker AAPL --fiscal-year 2024 --fiscal-period FY --company-name "Apple Inc." --files $INPUT` |
| UF-028 | `--ticker AAPL --fiscal-year 2024 --fiscal-period FY --company-name "Apple Inc." --files $INPUT/probe.bin` |
| UF-030–038 | 分别以 `$INPUT/probe.doc/.ppt/.pptx/.csv/.json/.xbrl/.xhtml/.xml/.zip` 替换 files，其他参数固定 `--ticker AAPL --fiscal-year 2024 --fiscal-period FY --company-name "Apple Inc."` |

UF-I11/12/13 作为 content-boundary supplement 原样运行 frozen argv：ICPD corrupt.pdf、ICMX
`probe.txt + corrupt.pdf`、ICDX corrupt.docx；它们预期 exit `1`，不是 PF01 usage pass。

### 10.2 每 case 必留证据

每 case 输出不可变 evidence directory，至少包含：

- `argv.json`：逐 token exact argv、cwd、Python/CLI version、HEAD。
- `stdout.txt`、`stderr.txt`、`result.json`：exact bytes、exit code、duration、timeout=false。
- `before.json`、`after.json`：相对路径、type、mode、size；regular file 记录 SHA-256，symlink 记录 target。
- `durable-artifacts.json`：company meta、identity、source meta/files、job records、batch journal/backup 的存在性与 SHA-256；
  PF01 invalid cases必须为空。
- `sha256sums.txt`：输入文件以及上述每个 evidence file 的 SHA-256；另写 bundle manifest digest。

PF01 exact assertions：exit `2`；stdout exact empty bytes；stderr exact one actionable line且不含 traceback；
before/after tree byte-for-byte equivalent；`created/deleted/modified=[]`；无 `.dayu`、`portfolio`、lock、job、
company/source durable artifact。I11–I13 assertions：exit `1`、typed bounded reason、无 traceback/path；fresh
before/after business/durable tree等价。报告只根据 raw files 生成，不用 mock/fake、人工转述或旧 digest 代替。

## 11. README trigger audit

实现完成后按各 README 自身约束判断：

- `dayu/fins/README.md`：**更新**；记录 current typed validation owner、pure published-state read、lazy bootstrap、
  filing company/source single batch、typed failure reason，并明确 upload validation snapshot 与完整
  `read_source_snapshot` 的不同适用边界。
- `dayu/service/README.md`：**更新**；`upload_filing` 改为 typed request handoff，且 Service 不拥有/读取 storage。
- `tests/README.md`：**更新**；补充 pre-factory zero-mutation、single-batch atomicity、typed failure owner coverage。
- 根 `README.md`：**更新**；用户可见 usage exit `2`/actionable error、content exit `1`、失败不发布 filing。
- `dayu/README.md`：**不更新**；`UI -> Service -> Host -> Engine` 与 Fins package 位置未变。
- `dayu/host/README.md`、`dayu/engine/README.md`、`docs/host/design.md`、`docs/engine/design.md`：**不更新**；无 Host/Engine contract 变化。
- `dayu/config/README.md`：**不更新**；无 config/schema/prompt 变化。

## 12. Risks / questions

### 12.1 已裁决风险

- **TOCTOU — covered by approved S2/S3**：pre-factory validation 不是 commit authorization；workflow 用同一 pure
  state protocol 重读并丢弃旧派生值，storage batch/commit 最终 fail closed。不得靠重试/补偿删除掩盖并发。
- **eager bootstrap 回归 — covered by approved S1**：所有 mutation owner 必须在写前确保目录；direct/durable
  download、direct/legacy preprocess、legacy upload job 与 begin_batch 首写 tests 全覆盖，不允许 caller 手工 mkdir。
- **format drift — assigned to existing later UF-FIX work unit**：两套集合本轮维持原值并按顺序验证；不能把集合交集
  发布为第三个真源。
- **existing lock artifacts — covered by approved S1**：existing workspace 的一次 publication guard 是一致读协议；
  fresh canonical-root absent 必须在 guard 前短路且零 lock。crash recovery artifacts 仍由 storage owner 管理。
- **failure redaction — covered by approved S4**：不能 truncate `str(exc)`；先 typed 分类、固定安全文案，再 bounds。
- **UF-FIX09 regression — covered by approved S3**：DefaultFinsRuntime composition owner test 固定 shared converter、
  cancellation token identity 与 async prepare path。
- **validation snapshot 与 full source snapshot 误用 — covered by approved S5 docs**：Fins README 必须说明前者只服务
  upload admissibility/action snapshot，后者继续服务完整 source read；消费者不得互换。

### 12.2 Review questions resolved / blockers

- **Q1 resolved**：现有 `prepare_upload` 在 cancellation 后先分 delete；delete 返回
  `_PreparedDeleteMutation`，skip 在非 delete 的 original-bytes/fingerprint 判定后返回 terminal
  `UploadOperationResult`。6.5 已固定真实分支，非 open。
- **Q2 rejected/resolved**：Controller 已验证 `_fs_repository_factory.py::build_fs_repository_set` 已有
  `create_directories` 参数；不修改该文件。
- **Q3 resolved**：SEC、CN、HK 注入同一 `FilingUploadStateRepositoryProtocol` instance，返回等价
  `FilingUploadPublishedState`；CN/HK 有独立 market-route owner tests。
- **Q4 resolved**：所有 non-CLI filing consumers 在业务启动前调用同一 validator并得到 typed
  `FinsUploadUsageError`；只有 CLI 映射 exit `2`，Host/Engine 不改。

**Blocking question：无。** company_name/state lookup、fast path、assembly、validated handoff、prepare 分支与
non-CLI projection 均已固定，不留到实现再决定。

## 13. Closeout

实现 gate 完成的必要条件：S1–S4 全部 owner assertions 通过；完整 pyright 通过；逐生产文件覆盖率
`>=80%`；README trigger audit 完成；UF-PF01 与 I11–I13 focused-real bundle 满足 exact argv/stream/exit/tree/
durable/SHA-256 要求；确认无 Host/Engine、oracle/registry/frozen evidence、UF-FIX09 converter、其它 FIX/PF
越界修改。随后才可进入 code review/deepreview/final closeout；后续 gate 按 Gateflow 本地提交，PR/push/main
更新在本 WU 明确禁止，不等待或请求授权。

本 plan gate 不运行 implementation 阶段测试；双路 review 与 delta re-review 收口后，按 Gateflow 创建
accepted-plan checkpoint commit，再进入 implementation。
