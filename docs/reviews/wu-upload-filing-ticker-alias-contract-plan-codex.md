# upload-filing-ticker-alias-contract code-generation-ready plan

## 1. Gate metadata

| 字段 | 值 |
| --- | --- |
| Gate | `plan fix (round 2)` |
| Work unit | `upload-filing-ticker-alias-contract` |
| Goal confirmation | `docs/reviews/wu-upload-filing-ticker-alias-contract-goal-confirmation-controller.md` |
| Completion status | `second plan fix complete` |
| Current gate / next entry point | `plan re-review` |
| Artifact path | `docs/reviews/wu-upload-filing-ticker-alias-contract-plan-codex.md` |

本artifact已按plan review、plan re-review两轮controller adjudication及第二轮fix补充校验修订为code-generation-ready plan。当前第二轮fix gate不进入implementation；`plan re-review`通过后，Gateflow在当前分支创建accepted plan local commit，并继续S1/S2的implementation/review/fix/re-review/local commit gates。用户只排除PR与push，不把普通gate完成视为停止条件。

## 2. Goal、motivation 与 success signal

### 2.1 Goal

建立唯一、严格且可持久化的 Company Ticker Identity contract，使一次用户声明从 CLI / tool / resolver 到 CompanyMeta、workspace alias index 和 read route 保持同一语义：

- filing/material CSV 第一项是 canonical corpus ticker；后续项是用户明确声明的同公司 accepted aliases。
- `ticker_aliases`适用于filing与material；两条producer路径必须复用同一`CompanyTickerIdentity`、CompanyMeta commit intent与authoritative merge，成功返回前可靠持久化，禁止接受后忽略。
- 系统信任声明，不联网核验、不按现实公司归属纠正 `DELTA,MSFT`。
- US / CN / HK 与 `V.BA` 使用同一个 ticker grammar、canonicalization 和长度边界。
- canonical-equivalent 变体稳定去重；不同 accepted alias 按首次出现顺序保留。
- fresh / stale / new CompanyMeta 都不能静默丢失既有或本次 accepted aliases。
- workspace 内一个 normalized lookup ticker 只能属于一个 canonical corpus；冲突在任何 published tree mutation 前原子拒绝。
- `list_documents` 传 canonical 或任一 accepted alias 都只由 storage identity route 命中同一 corpus。
- 合法descriptor拥有corpus canonical；storage公开状态或文档先于meta的恢复边界可形成meta-less corpus并保持canonical-only可读，只有valid CompanyMeta额外声明aliases。正常SEC/CN material create/update会写CompanyMeta，不是meta-less来源假设。
- 冲突沿现有 typed upload terminal failure 链输出有界、可行动且 path-free 的失败。

### 2.2 Motivation 与 first-principles judgment

动机成立，且严重性没有被高估。直接代码表明问题不是单入口 parsing bug，而是同一业务事实缺少唯一 owner：

1. `dayu/fins/ticker_normalization.py::_US_SYMBOL_PATTERN` 只允许单字符点号分节；`try_normalize_ticker("V.BA")` 因此失败。
2. `dayu/fins/resolver/fmp_company_info.py::_normalize_ticker_token` 在 normalizer 失败后回退为 compact upper text，能公开返回 `V.BA`；`dayu/fins/ingestion_runtime.py::_validate_fins_upload_filing_static` 又逐 alias 严格调用 normalizer，形成 producer/consumer 断裂。
3. CLI `_parse_ticker_csv` / `_merge_ticker_aliases`、SEC `_canonicalize_alias_token` / `normalize_sec_ticker_aliases` / `merge_ticker_aliases`、CN `_merge_aliases`、upload `_normalize_ticker_aliases` 与 storage `_canonicalize_ticker_alias` / `_normalize_company_ticker_aliases` 各自产生 grammar、fallback 或去重语义。
4. `resolve_upload_company_meta_decision` 在 resolver version fresh 时直接返回 `keep`，没有比较本次 aliases；现有测试还把 `NEW` 被丢弃固定成预期。
5. `_upsert_company_meta_impl` 只写当前 ticker staging；`commit_batch` 只持 ticker publication guard 并直接 backup/swap/`COMMITTED`，没有 workspace uniqueness validation。
6. `_build_company_alias_index_from_meta` 当前产生 `alias -> [ticker]`，`resolve_existing_ticker` 只在 read 时发现多个 owner；published state 已经进入歧义状态。
7. `FinsReadRuntime._resolve_canonical_ticker` 与 storage `resolve_existing_ticker` 两级执行 normalize/fallback/猜目录，不是单一 route。
8. `FilingUploadPublishedState.company_meta=None`是公开合法状态；公开storage batch API及文档先于meta的恢复/发布边界可以留下只有ticker descriptor/文档而没有`meta.json`的corpus，descriptor canonical今天仍可direct route命中。正常SEC/CN material create/update则会调用`upsert_company_meta_for_upload`写CompanyMeta。
9. `FinsUploadMaterialRequest`、combined upload tool与CLI `upload_material`当前都携带`ticker_aliases`；`service_runtime`把它们下传，SEC `run_upload_material_stream`与CN `upload_material_stream`在create/update中调用`upsert_company_meta_for_upload`。因此material不是“接受后忽略”路径，而是必须与filing一起迁移到唯一identity builder及S2 commit-intent/authoritative merge的直接CompanyMeta producer。

根因与修复边界逻辑/数据同源：Fins Company Ticker Identity 拥有 grammar、canonicalization、稳定去重与 CompanyMeta identity projection；`dayu.fins.storage` 拥有 workspace durable uniqueness、commit validation 和 alias-to-corpus route。CLI、resolver、pipeline、tool schema 与 read runtime只能构造或消费这两个 owner 的 contract。

### 2.3 Success signals

1. owner tests 覆盖 US/CN/HK、8/9 字符长度边界、`BRK.B`、`V.BA`、`AAPL.SW`、`DELTA,MSFT`、重复与 canonical-equivalent 去重。
2. `build_company_ticker_identity("AAPL", ("AAPL", "US.AAPL"))` 产生零 accepted aliases；`build_company_ticker_identity("DELTA", ("MSFT",))` 无条件保留 `MSFT`。
3. FMP `V` resolver 返回 canonical `V` 与 accepted alias `V-BA`；upload validator接受原始 `V.BA`，storage/read query 对 `V.BA` 与 `V-BA` 路由相同。
4. new、fresh 与 stale CompanyMeta 都由同一 identity builder 产生；fresh meta 新 alias 会 stage，已有不同 alias 不丢失，非 identity 字段不被 alias merge 擅自改写。
5. 同canonical并发commit以writer-lock后的authoritative current稳定union aliases，且prevalidation旧snapshot不覆盖更晚published非identity facts。
6. sequential（两种顺序）与 concurrent alias conflict 都恰有一个 canonical corpus成功；失败 batch 的 published tree 保持原状，冲突判定发生在 target backup/swap 前。
7. canonical、显式 alias、跨市场 alias、resolver alias 的 `list_documents` 返回同一 canonical ticker 和同一文档集合。
8. meta-less corpus canonical `list_documents`保持可用且不凭空产生alias；与健康alias corpus共存互不阻断，后续可原子补齐CompanyMeta。
9. material new/fresh/stale CompanyMeta与filing使用同一builder/merge规则；`upload_material --ticker DELTA,MSFT`保留`MSFT`并在成功commit后由两者路由同一corpus，跨进程same-canonical更新不丢alias或覆盖更晚durable facts。
10. descriptor缺失或结构/namespace/locator/external canonical非法均投影closed `invalid_descriptor` corruption kind；合法missing `meta.json`仍不是corruption。
11. CLI help 与 upload/read tool schema 自足说明 canonical/alias 声明及同 corpus 查询语义。
12. focused owner/e2e tests、每个受影响生产文件 coverage `>= 80%` 与全量 pyright 通过；README 只按读者职责更新。

## 3. Binding non-goals 与 scope boundary

- 不执行 UF-PF05 真实 CLI evidence。
- 不读取、刷新或修改 oracle/scenario registry、冻结 evidence 或其它 finding。
- 不联网核验 alias 现实归属，不引入证券主数据或公司 identity 服务。
- 不为旧歧义 workspace 做兼容读取、双读、迁移、自动修复或 compatibility shim；按 fresh schema 起库。
- 不改变 filing calendar、download selection、Docling、source revision、document identity 或其它上传行为。
- 不把 Company Identity 放入 Host、Engine、Service state machine 或 `dayu.runtime`。
- 不新增持久化 alias registry/index 文件；alias index 保持为 CompanyMeta 的 storage-owned派生视图。
- 不为material新增第二套alias registry、merge helper或CompanyMeta owner；保留其既有CompanyMeta producer职责，但机械消费与filing相同的identity/intent contract。
- 不引入 callback/factory/profile/query facade、通用 alias framework、数据库或网络 registry。
- 不修改 `docs/host/design.md`、`docs/engine/design.md`；它们只作为 owner 排除证据。
- 不创建 PR、不 push；accepted plan/slice/deepreview 仍按 Gateflow 在当前分支创建受保护的本地 commits。

## 4. Design document alignment

### 4.1 Host boundary

`docs/host/design.md` §1–§3 与 §18.1–§18.2 已完整核对相关边界：Host 是 run/tool governance 真源，但不承载财报业务语义、不管理财报原文仓储规则；ToolRuntime 只消费业务 `ToolDefinition` 并执行 accept barrier。故 ticker identity、storage conflict 与 read routing 不进入 Host。上传工具只在 Fins 工具声明现场更新 LLM-facing schema。

### 4.2 Engine boundary

`docs/engine/design.md` §1、§10、§16 已完整核对相关边界：Engine 不负责财报语义、ticker 归一、工具参数校验或 storage；它只看到 `ToolSchema`、`ToolExecutor` 和 outcome。故不修改 Engine contracts、events 或 error code。

### 4.3 Goal-confirmation alignment

本计划不扩大 goal confirmation 的identity目标；补充校验只是把已存在的material CompanyMeta producer纳入同一contract。failure transport按阶段冻结：静态非法 ticker/alias继续由`FinsUploadUsageFailure`拥有；workspace race 的权威冲突只能在 `commit_batch` 判定，此时 direct stream / awaiting job 已启动，必须进入现有 `FinsUploadFailureReason` terminal chain。两阶段不复制错误原因，也不把commit race伪装成pre-start usage failure。

## 5. Semantic owners 与 public contract changes

### 5.1 Ticker grammar 与 Company Ticker Identity owner

Owner：`dayu/fins/ticker_normalization.py`。

新增 public immutable type：

```python
@dataclass(frozen=True, slots=True)
class CompanyTickerIdentity:
    canonical_ticker: str
    market: Market
    exchange: Exchange | None
    accepted_aliases: tuple[str, ...]

    def lookup_tickers(self) -> tuple[str, ...]: ...
```

字段 contract：

- `canonical_ticker` 是 canonical corpus ticker。
- `market` / `exchange` 只从 canonical ticker 的 `normalize_ticker` 结果产生。
- `accepted_aliases` 不包含 canonical-equivalent 项，按首次出现顺序稳定去重；tuple 保证 public fact 不被调用方修改。
- `lookup_tickers()` 是唯一 canonical + accepted aliases 投影，返回 `(canonical_ticker, *accepted_aliases)`；alias index、resolver output 与测试不得各自重建。

新增 public function：

```python
def build_company_ticker_identity(
    canonical_ticker: str,
    declared_aliases: Sequence[str],
) -> CompanyTickerIdentity: ...
```

函数严格调用 `normalize_ticker` 处理 canonical 与每个非空 alias；空 alias 或非法 grammar 抛 `ValueError`。stable dedupe key 是各 token 的 `NormalizedTicker.canonical`，不按 raw 大小写/分隔符、市场现实或来源分类。

Grammar 精确调整：

- `_US_SYMBOL_PATTERN` 从“点号后只允许单字符”收敛为一个可选 `.` 或 `-` 分节，分节为一个或多个 `[A-Z0-9]`；仍禁止多个分节、空分节和其它字符。
- `_MAX_US_SYMBOL_LENGTH = 8` 保持不变并作用于 canonical token 的完整字面长度。
- dot 分节继续 canonicalize 为 `-`：`BRK.B -> BRK-B`、`V.BA -> V-BA`、`AAPL.SW -> AAPL-SW`。
- market prefix/suffix owner 仍先处理 `AAPL.US` / `US.AAPL`；未知但符合单分节 grammar 的 `V.BA` / `AAPL.SW` 作为 accepted ticker token，不联网解释其交易所含义。

删除/迁移重复 owner：

- CLI `_merge_ticker_aliases`。
- upload `_normalize_ticker_aliases`。
- SEC `_canonicalize_alias_token` 与 `normalize_sec_ticker_aliases`。
- CN `_merge_aliases`。
- FMP `_normalize_ticker_token` 与 `_dedupe_ticker_aliases`。
- storage `_canonicalize_ticker_alias` 与 `_normalize_company_ticker_aliases`。

SEC/FMP 外部响应中的非法 symbol 在各自 producer 的直接输入校验处用 `try_normalize_ticker` 丢弃；canonical 请求非法则 fail closed。用户明确声明的 aliases 不做宽松过滤，任一非法项整体拒绝。

### 5.2 CompanyMeta owner

Owner：`dayu/fins/domain/document_models.py::CompanyMeta`，identity value 由上节 owner 产生。

Python public type 改为：

```python
@dataclass(frozen=True)
class CompanyMeta:
    company_id: str
    company_name: str
    ticker_identity: CompanyTickerIdentity
    resolver_version: str
    updated_at: str
```

不保留 `ticker` / `market` / `ticker_aliases` compatibility property。调用方必须使用 `ticker_identity.canonical_ticker`、`ticker_identity.market` 与 `ticker_identity.accepted_aliases`。

Durable JSON 仍使用 flat current keys，避免无需求的物理 schema 嵌套：

```json
{
  "company_id": "...",
  "company_name": "...",
  "ticker": "AAPL",
  "market": "US",
  "resolver_version": "...",
  "updated_at": "...",
  "ticker_aliases": ["MSFT", "V-BA"]
}
```

语义变化是 `ticker_aliases` 只保存 accepted aliases，不重复 canonical。`to_dict()` 只能从 `ticker_identity` 投影这些字段；`from_dict()` 必须要求 `ticker_aliases` 为 `list[str]`，调用 `build_company_ticker_identity`，并校验 persisted `market` 与 builder 结果一致。缺字段、wrong type、空/非法 alias 或 market mismatch 都 fail closed；不再把缺失/非法 alias 字段默认为 `[]`。

Canonical ownership不依赖CompanyMeta存在：storage ticker identity descriptor拥有该published corpus的exact canonical；CompanyMeta只在存在且strict valid时拥有accepted aliases，并必须与descriptor canonical/market一致。由storage公开状态或文档先于meta恢复边界形成的meta-less corpus因此是合法canonical-only identity，不是CompanyMeta schema兼容分支，也不允许从文档、目录名或请求参数反推alias；正常material create/update仍按下文producer contract写CompanyMeta。

### 5.3 CompanyMeta commit intent 与 authoritative merge owner

Owner：新增 `dayu/fins/domain/company_meta_contract.py`。该 domain 模块是 CompanyMeta mutation policy 的唯一 owner；storage 可以依赖 domain contract，但不得 import pipeline，也不得自行比较 resolver version、选择字段或重写 merge 算法。

新增 public immutable types：

```python
CompanyMetaMergeMode = Literal["preserve_published", "refresh_if_stale"]

@dataclass(frozen=True, slots=True)
class CompanyMetaNonIdentitySnapshot:
    company_id: str
    company_name: str
    resolver_version: str
    updated_at: str

@dataclass(frozen=True, slots=True)
class CompanyMetaCommitIntent:
    proposed_identity: CompanyTickerIdentity
    merge_mode: CompanyMetaMergeMode
    expected_non_identity: CompanyMetaNonIdentitySnapshot | None
    proposed_company_id: str | None
    proposed_company_name: str | None
    resolver_version: str
```

`proposed_identity.accepted_aliases`只表示本次明确声明/producer接受的alias intent，不含prevalidation snapshot中的既有aliases。`CompanyMetaNonIdentitySnapshot`是domain owner产生的exact optimistic precondition，不含identity/aliases，不能作为merge base或从时间戳单独反推。`proposed_company_*`在`preserve_published`中必须为`None`，在`refresh_if_stale`中必须为非空显式refresh值，绝不把旧`CompanyMeta`整体复制成最终staged value。`preserve_published`用于prevalidation看到fresh meta的alias-only mutation；`refresh_if_stale`用于missing/stale meta的显式refresh。

新增唯一 pure function：

```python
def build_company_meta_commit_intent(
    *,
    proposed_identity: CompanyTickerIdentity,
    merge_mode: CompanyMetaMergeMode,
    observed_meta: CompanyMeta | None,
    proposed_company_id: str | None,
    proposed_company_name: str | None,
    resolver_version: str,
) -> CompanyMetaCommitIntent: ...

def merge_company_meta_for_commit(
    *,
    current_published: CompanyMeta | None,
    intent: CompanyMetaCommitIntent,
    committed_at: str,
) -> CompanyMeta: ...
```

intent builder是`CompanyMetaNonIdentitySnapshot`的唯一构造入口并校验mode/optional fields不变量；pipeline/resolver/storage不得各自投影snapshot。filing prevalidation传其published snapshot；SEC/CN material direct producer及download等在caller-owned batch中写meta的producer，先用repository public read取得`observed_meta | None`（此时same-canonical writer已由batch持有），再调用同一builder形成intent。该observed value仍只作为optimistic precondition，commit authoritative current必须重读。

精确规则：

1. `current_published` 只能由 storage 在 commit 持有 same-canonical writer、recovery guard 与 workspace identity guard 后，从 incoming canonical 当前 published target 的 publication-guarded view读取；prevalidation snapshot不得传作该参数。
2. current存在时，其`ticker_identity.canonical_ticker/market/exchange`必须与`intent.proposed_identity`一致，否则抛published identity corruption；最终identity为`build_company_ticker_identity(intent.proposed_identity.canonical_ticker, (*current.ticker_identity.accepted_aliases, *intent.proposed_identity.accepted_aliases))`，因此current durable aliases在前、本次新增aliases在后，均稳定去重。
3. `preserve_published`：current必须存在；无论其resolver version在prevalidation后如何变化，最终`company_id/company_name/resolver_version`全部取commit-time current，intent只贡献aliases。若prevalidation观察到meta但commit-time合法descriptor已无meta，抛`CompanyMetaConcurrentUpdateError`；不用prevalidation copy重建，也不误报durable corruption。
4. `refresh_if_stale`：若current不存在且`expected_non_identity is None`，或current的exact nonidentity snapshot等于`expected_non_identity`，应用intent的`proposed_company_id/proposed_company_name/resolver_version`；若concurrent writer已把current更新为intent resolver version的fresh meta，则current全部非identity字段优先，intent不得覆盖这些更晚durable facts；若current已改变但仍stale，抛`CompanyMetaConcurrentUpdateError`，整批在published mutation前失败，不能用旧refresh intent覆盖更晚且无法安全判序的durable facts。
5. `updated_at`：若最终 identity与current identity相同且选择的非 identity字段也完全沿用 current，则保留 current值；只要新增 alias或真正应用 refresh intent，使用 storage传入的 `committed_at`。storage只提供时点并机械调用函数，不拥有字段选择语义。
6. current不存在且mode为`refresh_if_stale`、`expected_non_identity is None`时创建新meta；这同时覆盖全新target与合法既有meta-less target首次补meta。current不存在但`expected_non_identity`非`None`、或`preserve_published`要求current时均抛`CompanyMetaConcurrentUpdateError`；只有descriptor无效、meta存在但strict parse失败或meta/descriptor identity不一致才抛typed corruption。不猜测、不从staging旧文件恢复业务事实。

`CompanyMetaConcurrentUpdateError`由同一domain模块定义，固定path-free message，不携带raw fields/path；upload failure mapper将其映射为既有`storage/storage_io`与“公司元数据已被并发更新，请基于最新状态重试”的retry hint，不误报alias conflict或company-name-required。

`UploadCompanyMetaDecision` 改为携带 `CompanyMetaCommitIntent | None`，不再携带最终 `CompanyMeta`。`CompanyMetaRepositoryProtocol.upsert_company_meta` 改为语义准确的 `stage_company_meta_intent(intent, *, batch)`；该调用只校验 capability/ticker并把唯一 intent记入 `_ActiveBatchState`，不提前把 prevalidation-derived final meta写进staging。SEC/CN download producers与upload workflow都构造同一 intent；最终 `CompanyMeta` 只在 commit authoritative merge后写入staging。

### 5.4 Resolver public contract

Owner：`dayu/fins/resolver/fmp_company_info.py`。

`FmpCompanyInfo` 改为：

```python
@dataclass(frozen=True, slots=True)
class FmpCompanyInfo:
    ticker_identity: CompanyTickerIdentity
    company_name: str
```

不保留 `canonical_ticker` / `ticker_aliases` compatibility properties。两跳 FMP 算法和“不联网校验用户显式 alias”的边界不变；FMP 只产生自身 resolver aliases。`_select_symbol_result` 与 alias collection 复用 ticker owner，`V.BA` 进入 identity 后为 `V-BA`。

### 5.5 Storage routing public contract

Owner：`dayu/fins/storage`。

删除：

```python
resolve_existing_ticker(ticker_candidates: list[str]) -> str | None
```

新增：

```python
resolve_company_ticker(ticker: str) -> str | None
```

涉及 `CompanyMetaRepositoryProtocol` 与 `FsCompanyMetaRepository`。该接口是 canonical/alias 到 canonical corpus 的唯一 route：

1. storage 用 `try_normalize_ticker` 对单个查询 token应用唯一 grammar；无法接受时返回 `None`，不回退 `strip().upper()`。
2. 在workspace Company Identity guard内扫描每个实际published ticker directory并strict读取identity descriptor。每个合法descriptor的exact canonical无条件进入`dict[str, str]` unique index；若`meta.json`不存在，该corpus到此为止，合法但只拥有canonical。
3. 只有`meta.json`存在且strict `CompanyMeta.from_dict()`成功、其canonical/market与descriptor一致时，才把`company_meta.ticker_identity.accepted_aliases`加入同一index；canonical不从CompanyMeta重复贡献，alias不从request/document/path推断。
4. 命中返回唯一descriptor canonical；未命中返回`None`。因此meta-less corpus的canonical query路由自身真实文档，任何alias query均不命中；健康corpus的canonical/alias read不因无关meta-less corpus而失败。
5. descriptor缺失/非法、存在但invalid的CompanyMeta、meta/descriptor identity mismatch或任一lookup key有多个owner时抛下节typed corruption；`meta.json`缺失本身不是corruption。不得把read-side durable corruption伪装成incoming conflict，也不在read runtime猜测。

route与commit共同复用private `_scan_actual_published_company_identities()` + `_build_unique_company_identity_index()`：前者只枚举`portfolio/`实际directories并在排序publication guards下返回“descriptor canonical + optional valid CompanyMeta”，后者先登记每个descriptor canonical、再登记valid meta的accepted aliases。现有public`scan_company_meta_inventory()`继续服务operator inventory，`missing_meta`仍是合法诊断status且可包含backup/lock locator状态；该operator inventory禁止用于authoritative route/uniqueness decision。

正常SEC/CN material create/update是既有CompanyMeta producer：其成功CompanyMeta commit后的aliases与filing aliases一样进入本route。meta-less只描述descriptor存在而valid CompanyMeta暂缺的storage状态，不由“upload_kind=material”推导；不得从material source document/event payload反推aliases。

`FinsReadRuntime._resolve_canonical_ticker` 仅负责非空参数错误、调用 `resolve_company_ticker(raw_ticker)` 以及 `None -> NOT_FOUND` 业务投影；删除 `try_normalize_ticker` 与 upper fallback。所有 read methods 继续复用这个单一 runtime入口。

### 5.6 Workspace uniqueness 与 durable corruption typed exceptions

Owner：`dayu/fins/storage/repository_protocols.py`，并由 `dayu.fins.storage` 包显式导出：

```python
class CompanyTickerAliasConflictError(ValueError):
    alias: str
    existing_canonical_ticker: str
    incoming_canonical_ticker: str
```

`CompanyTickerAliasConflictError`只表示本次incoming descriptor canonical/commit intent lookup key与另一个有效published canonical冲突；构造器只接受已normalized、非空business values。它不得用于read route、invalid published meta或duplicate durable owner。

另新增：

```python
CompanyTickerIdentityCorruptionKind = Literal[
    "invalid_descriptor",
    "invalid_meta",
    "identity_mismatch",
    "duplicate_owner",
]

class CompanyTickerIdentityCorruptionError(ValueError):
    kind: CompanyTickerIdentityCorruptionKind
    lookup_ticker: str | None
```

该异常是published identity scan/read route的owner-produced typed fact，不含`incoming_canonical_ticker`。closed kinds精确定义为：

- `invalid_descriptor`：实际published ticker directory缺少identity descriptor，或descriptor不是non-symlink regular file、JSON/schema/namespace/external identity/private locator双向关系非法，或descriptor external ticker不能被唯一ticker owner接受为该目录的exact canonical。`_scan_actual_published_company_identities()`必须把对应`FileNotFoundError`/descriptor validation `ValueError`收敛为此kind；普通permission/I/O失败仍沿storage unavailable/storage_io投影，不伪装为durable corruption。
- `invalid_meta`：descriptor合法且`meta.json`存在，但JSON/schema/grammar非法。
- `identity_mismatch`：descriptor与strict-valid CompanyMeta的canonical/market/exchange不一致。
- `duplicate_owner`：两个strict-valid published corpus对同一normalized lookup key声明owner。

`missing_meta`明确不在closed kind中；descriptor合法且meta absent是canonical-only identity。两类异常的public message都固定且不含filesystem path、private storage key、transaction id或raw exception；字段只供owner tests/operator structured handling，用户/LLM文案不直接拼business values。

read projection由 `dayu/fins/tools/error_contract.py` 与 `read_runtime.py` 共同拥有：

- `ErrorCode` 新增 `WORKSPACE_IDENTITY_CORRUPTED = "workspace_identity_corrupted"` 与 `STORAGE_UNAVAILABLE = "storage_unavailable"`。
- `_resolve_canonical_ticker` 捕获 `CompanyTickerIdentityCorruptionError`，产生 path-free `FinsReadBusinessError`：message固定为“工作区中的公司代码身份数据不一致，当前无法安全解析该公司”，hint固定为“请修复该工作区的公司元数据后重试”。
- identity/publication guard 的 `RuntimeFileLockError` 产生 `STORAGE_UNAVAILABLE`：message固定为“财报存储当前无法建立一致读取视图”，hint固定为“请稍后重试；若持续失败，请检查工作区存储权限与锁服务”。
- `None` 仍唯一投影 `NOT_FOUND`；read tool callable继续复用既有 `FinsReadBusinessError -> failed_outcome` owner，不新增 tool-local catch。

### 5.7 Upload failure projection

Owner：`dayu/fins/upload_failure.py`。

- `FinsUploadFailureCode` 新增 `TICKER_ALIAS_CONFLICT = "ticker_alias_conflict"`。
- 保持现有 `FinsUploadFailureKind.STORAGE`，新增 `_STORAGE_FAILURE_CODES` closed set，包含 `STORAGE_IO` 与 `TICKER_ALIAS_CONFLICT`；JSON parser 的 kind/code一致性从该 set 派生。
- `fins_upload_failure_from_exception` 在 generic/OSError 前识别 `CompanyTickerAliasConflictError`，产生：
  - kind: `storage`
  - code: `ticker_alias_conflict`
  - message: `股票代码别名已属于当前工作区中的其他公司，请移除冲突别名后重试`
  - retry_hint: `确认 canonical ticker 与别名声明后重新上传`
  - file_label: `None`
- SEC/CN pipeline 已在 terminal catch 中统一调用该 mapper；不新增单入口 catch/fallback。runtime summary、durable failure summary、direct RESULT 和 awaiting tool observation 继续消费同一个 `FinsUploadFailureReason`。
- `FinsUploadUsageFailure` 继续只负责 static/published-snapshot admission；不新增一个无法覆盖并发 race 的同名 usage code。
- `CompanyTickerIdentityCorruptionError`不映射为`ticker_alias_conflict`；mapper将它投影为既有`storage/storage_io`，使用固定“工作区公司代码身份数据损坏，无法安全提交”文案与修复workspace identity data的hint，避免把published corruption归责给incoming alias。合法meta-less状态不会产生该异常。

### 5.8 Material CompanyMeta producer contract

Owner仍是`dayu/fins/pipelines/upload_company_meta.py`的唯一upload decision/intent contract，不在material workflow另建规则。直接数据流冻结如下：

1. `FinsUploadMaterialRequest.ticker_aliases`是accepted input；`dayu/fins/service_runtime.py`继续把canonical ticker与aliases原样交给对应SEC/CN material producer。combined tool的material request construction与Service direct API不得清空、过滤或忽略aliases。
2. S1删除`upsert_company_meta_for_upload`内部重复的fresh/stale/normalization分支，改为语义准确的`stage_company_meta_for_upload(...)`：在caller已`begin_batch(canonical)`并持same-canonical writer后public-read `existing_meta | None`，调用同一个`resolve_upload_company_meta_decision`，再调用`stage_upload_company_meta_decision`。该helper有真实的read/decision/stage语义，不是兼容wrapper。
3. `resolve_upload_company_meta_decision`对filing与material都先调用`build_company_ticker_identity(canonical, declared_aliases)`；fresh meta只有identity完全未新增alias才`keep`，否则stage stable union结果。S1暂时stage final CompanyMeta；SEC `run_upload_material_stream`和CN `upload_material_stream`必须继续在source-document publication前提交其CompanyMeta batch，确保alias conflict/validation失败时材料文档尚无published副作用。
4. S2把同一个decision切换为`CompanyMetaCommitIntent`，`stage_company_meta_for_upload`只stage intent；storage commit在writer/recovery/identity guards下authoritative重读并机械调用`merge_company_meta_for_commit`。因此material与filing共享same-canonical lost-update、nonidentity optimistic precondition、workspace conflict validation与typed terminal projection，不存在material专属merge或alias source。
5. material event payload可以展示owner已经接受的canonical/aliases，但不能成为durable/read真源；read route仍只消费descriptor + committed valid CompanyMeta。正常material create/update成功后必须能用canonical或任一accepted alias读取同一corpus。

## 6. Prevalidation intent 与 commit-time CompanyMeta state transition

### 6.1 Prevalidation owner

`dayu/fins/pipelines/upload_company_meta.py::resolve_upload_company_meta_decision` 只拥有 upload admission与commit intent construction，不拥有最终 merge base：

1. 非 create/update返回`skip`。
2. 对 canonical与本次 declared aliases构造`proposed_identity`；invalid alias仍在static validation唯一投影`INVALID_TICKER_ALIAS`。
3. existing fresh且没有新增alias返回`keep`；existing fresh但有新增alias返回`stage(preserve_published intent)`，不把existing fields复制为最终CompanyMeta。
4. existing stale或不存在时，只有这两个状态需要company name；缺失时抛专用`UploadCompanyNameRequiredError`。满足要求后返回`stage(refresh_if_stale intent)`，proposed company id/name/version是显式refresh值；`expected_non_identity`由existing的四个nonidentity fields精确投影，不存在时为`None`。
5. prevalidation读到的existing只用于决定`keep/stage`、company-name-required、merge mode与typed optimistic precondition；它不进入最终alias union，也不是commit-time current或字段merge base。

`dayu/fins/ingestion_runtime.py` 只捕获 `UploadCompanyNameRequiredError` 并映射 `COMPANY_NAME_REQUIRED`。builder的`ValueError`不会被该分支捕获；invalid alias由先行static owner稳定映射，任一其它domain/storage异常不能借偶然调用顺序伪装成company-name-required。

### 6.2 Commit authoritative state machine

`stage_upload_company_meta_decision` 与material direct producer的 `stage_company_meta_for_upload` 都只调用 `stage_company_meta_intent`；后者只为构造intent读取observed meta，不生成最终CompanyMeta。storage在commit时按§7锁保护重读authoritative current，然后只机械调用§5.3 `merge_company_meta_for_commit`。因此同 canonical current published aliases永远是authoritative union base，current非identity durable facts与staged explicit refresh intent按§5.3规则组合，prevalidation/producer observed whole-object snapshot没有覆盖通道。

## 7. Atomic transaction design

### 7.1 Existing evidence

- `begin_batch` 在返回 `BatchToken` 前取得并持续持有 ticker writer lock。
- `commit_batch` 先 `_validate_complete_source_tree(state)`，再取得 ticker publication guard，随后 target -> backup、staging -> target、写 `COMMITTED`。
- 失败时 `_rollback_precommit_batch` 能在 `COMMITTED` 前恢复 target 并移除 staging；commit 一开始 capability 即被 terminal consume。
- recovery 当前 lock order 是 recovery guard -> nonblocking ticker writer -> ticker publication guard。

### 7.2 New private state and lock

在 `_ActiveBatchState` 增加：

```python
company_meta_intent: CompanyMetaCommitIntent | None
publishes_new_corpus: bool
```

`begin_batch`在持有same-ticker writer并确认target是否存在后，初始化`company_meta_intent=None`并把`publishes_new_corpus`冻结为“本batch将首次发布ticker descriptor”的exact transaction-local fact；不得在commit时通过目录/`meta.json`猜测。`stage_company_meta_intent`校验intent canonical与batch ticker一致后记录一次，重复stage fail closed。`company_meta_intent is not None or publishes_new_corpus`是commit必须进入workspace identity serialisation的充分必要条件：前者可能改变aliases，后者即使meta-less也会新增descriptor canonical lookup。最终`meta.json`直到commit-time authoritative merge后才写入staging。

在 `_FsStorageInfra` 增加 private lock path：

```text
.dayu/company_identity.lock
```

使用现有 `dayu.runtime.filelock` wrapper 与 `_acquire_storage_lock_token`，新增 `_acquire_company_identity_guard()`；不新增 runtime helper。锁放在 `.dayu` 根而非 `batch_locks/`，避免 `_published_ticker_candidate_keys()` 把它误判为 ticker candidate。

### 7.3 Exact lock ordering

所有路径固定遵守：

```text
identity-changing commit（meta intent或首次发布corpus descriptor）:
  ticker writer (begin_batch 持有)
  -> workspace recovery guard
  -> recovery sweep（其它 ticker writer 只做 nonblocking try-lock；当前活动 batch 被跳过）
  -> workspace company identity guard
  -> incoming/current ticker publication guard（读取后释放）
  -> zero or more actual-published ticker publication guards（校验扫描，按 private key 排序并逐个释放）
  -> target ticker publication guard

alias read route:
  workspace company identity guard
  -> ticker publication guards（按 private candidate key 排序并逐个释放）

recovery:
  recovery guard
  -> ticker writer
  -> workspace company identity guard
  -> ticker publication guard

ordinary existing-corpus no-meta commit:
  ticker writer
  -> target ticker publication guard
```

释放顺序反向。任何持有identity/publication guard的路径不得再获取recovery guard，任何持有ticker publication guard的路径不得再获取identity guard。recovery在持有recovery guard时对ticker writer只做既有nonblocking try-lock；因此identity-changing commit即使已持自身ticker writer并等待recovery guard，recovery也会立即跳过该活动ticker，不形成等待环。authoritative route/commit只调用caller已持identity guard的private actual-published scan；public operator inventory不拥有identity语义，也不得被该路径反向调用。

### 7.4 Commit-time validation and publication

`commit_batch` 精确顺序：

1. resolve capability，标记 commit-started。
2. `_validate_complete_source_tree(state)`，只读 staging。
3. `company_meta_intent is None and publishes_new_corpus is False`：这是既有corpus的document-only/no-meta commit，保持当前ticker-scoped路径，不取得workspace recovery/identity guard，因为descriptor canonical与aliases都不变。
4. 其它batch都是identity-changing commit：取得workspace recovery guard，并通过不重复获取该guard的private helper执行orphan batch + backup sweep。当前batch因自身ticker writer仍被持有而由既有nonblocking recovery try-lock跳过；其它活动batch同样跳过，orphan先恢复/清理。
5. recovery guard保持到本次identity-changing commit完成，再取得workspace identity guard。这样任何后续descriptor/meta commit都必须先恢复此前在swap/`COMMITTED`窗口崩溃的事务，不能抢先占用其old/new canonical或alias。
6. 在identity guard内取得incoming canonical publication guard。若`publishes_new_corpus=True`，published target应不存在，`current_published=None`；若既有target存在，必须strict验证descriptor canonical。descriptor合法但`meta.json`不存在时同样令`current_published=None`，这是storage层canonical-only状态，不由upload kind推断；meta存在但strict parse失败或meta/descriptor identity不一致才抛`CompanyTickerIdentityCorruptionError`。prevalidation/producer read曾观察meta而此时为None，由§5.3 helper抛`CompanyMetaConcurrentUpdateError`。释放publication guard后，writer + recovery + identity仍保证authoritative view不被commit/recovery改变。
7. `company_meta_intent is not None`时，storage传入`current_published`、intent与单次`committed_at`，机械调用`merge_company_meta_for_commit`，得到final CompanyMeta并strict写入staging `meta.json`；storage不得自行union alias或选择非identity fields。首次发布meta-less corpus没有intent，不写`meta.json`，其incoming lookup keys只有staged descriptor canonical。
8. 在identity guard内调用private actual-published scan：只枚举`portfolio/`实际directories，按private key排序取得publication guard；每个descriptor必须strict valid，meta缺失则记录canonical-only，meta存在则必须strict valid且与descriptor一致。backup、writer/publication lock-only locator与当前batch staging均不参与published scan。只有invalid meta、descriptor invalid/mismatch才在swap前typed corruption；missing meta不失败。
9. 用唯一index helper先登记所有valid descriptor canonicals，再登记valid CompanyMeta accepted aliases。若当前published state已有duplicate owner，抛typed corruption。然后逐一检查incoming final lookup keys（有final meta时为其`lookup_tickers()`，首次meta-less descriptor publication时仅descriptor canonical）：index未命中或owner等于incoming canonical可继续，owner为其它canonical则抛`CompanyTickerAliasConflictError`。这覆盖“新descriptor canonical撞健康alias”和“新alias撞既有meta-less canonical”两个方向，不排除incoming现有descriptor也不把self-owner误报冲突。
10. 只有final merge与validation全通过后才取得target publication guard并执行backup、swap、`COMMITTED`。
11. swap/journal失败继续在target publication + identity + recovery guards保护下走现有precommit restore；published reader只能看到完整old/new。
12. 先释放target publication guard，再释放identity guard，最后释放recovery guard。若已有corruption/conflict/commit primary error，release failure仅附加note；若`COMMITTED`后release失败，沿现有post-commit terminal error规则处理，不回滚durable tree。
13. corruption/conflict/concurrent-update发生在任何target backup/swap前；outer terminal path调用现有`_rollback_precommit_batch`清理staging并消费token，published tree byte-for-byte不变。

### 7.5 Recovery

orphan batch与orphan backup的每个physical target restore/delete/swap分支，在recovery guard与nonblocking ticker writer之后、publication guard前统一取得identity guard。recovery无法恢复transaction-local intent/`publishes_new_corpus`，因此无条件对所有recovered ticker tree使用guard；绝不以staging/published`meta.json`存在猜测mutation。这是R1 rejected reason的correctness约束。identity guard获取失败时，在该orphan的第一次physical restore/delete/swap前fail closed并保留全部recovery evidence；release失败按既有最早primary/error-note规则处理。identity-changing commit复用同一个recovery sweep并把recovery guard持有到`COMMITTED`/rollback完成；只有既有corpus且没有meta intent的普通document commit不取该guard，因为它既不新增descriptor canonical也不改变aliases。该组合关闭“swap后崩溃 -> 另一identity-changing commit抢占canonical/alias -> restore old backup”的跨ticker窗口，不新增journal字段。

### 7.6 Why no durable alias index file

Ticker identity descriptor是durable canonical owner，valid CompanyMeta是durable accepted-alias owner；unique index是storage在identity guard内对这两个既有真源的确定性projection。新增第二个持久化index文件会引入双文件提交、recovery一致性和schema迁移问题，而当前workspace规模与已存在inventory scan没有证据要求缓存。故本WU不持久化registry/index，也不新增cache invalidation state。

## 8. CLI、tool 与 LLM-facing projection

### 8.1 CLI

- `dayu/cli/commands/fins.py::_parse_ticker_csv` 返回 `CompanyTickerIdentity`，直接调用唯一 builder；删除 `CliTickerInput` 和 `_merge_ticker_aliases`。
- `upload_filings_from --infer` 先断言 FMP identity canonical 与用户 canonical一致，再以 `(explicit accepted aliases + resolver accepted aliases)` 重新调用 builder；显式 aliases 顺序优先。
- direct `upload_filing`保持raw CSV进入Fins typed validator，让usage code owner不被CLI替代；`upload_material`与`upload_filings_from`继续调用同一`_parse_ticker_csv`/builder并把`canonical_ticker`与`accepted_aliases`原样送入各自CompanyMeta producer。生成的material命令行也保留完整CSV identity，不得只投影canonical。
- `dayu/cli/arg_parsing.py`新增语义明确的upload ticker argument helper，只用于`upload_filing`、`upload_material`、`upload_filings_from`。三个命令help都说明“第一项canonical，后续项为用户明确alias声明；成功CompanyMeta commit后同corpus查询”，其中`upload_material`明确其aliases由material CompanyMeta producer可靠持久化。process/download ticker help不宣称接受CSV。

### 8.2 Upload tool schema

`dayu/fins/tools/upload_tools.py` 只改 schema 和既有 request construction：

- `ticker`：明确是 corpus canonical ticker，单个字符串，不放 CSV。
- `ticker_aliases`：明确适用于`upload_kind=filing`和`upload_kind=material`；每项是用户明确声明的同公司alias，系统信任且不联网核验；对应CompanyMeta成功commit后canonical与aliases查询同一corpus；不要重复canonical-equivalent变体。
- 两个request construction分支都原样携带该数组，并由§5.8同一个upload decision/intent owner消费；schema不新增material特例或第二套条件错误。
- schema 不暴露 CompanyTickerIdentity、lock、index、transaction 或 internal code。

### 8.3 Read tool schema

`dayu/fins/tools/fins_tools.py::_ticker_parameter_schema` 明确可传 workspace 已接收的 canonical ticker 或 alias，任一 accepted alias 路由同一公司 corpus；仍禁止公司名和手工穷举变体。

## 9. Affected files/modules

### 9.1 Production contract and producers/consumers

- `dayu/fins/ticker_normalization.py`
- `dayu/fins/domain/document_models.py`
- `dayu/fins/domain/company_meta_contract.py`（新增唯一commit intent/merge owner）
- `dayu/fins/pipelines/upload_company_meta.py`
- `dayu/fins/pipelines/sec_company_meta.py`
- `dayu/fins/pipelines/cn_download_company_meta.py`
- `dayu/fins/resolver/fmp_company_info.py`
- `dayu/fins/ingestion_runtime.py`
- `dayu/fins/service_runtime.py`（material handoff继续原样传递identity inputs）
- `dayu/fins/pipelines/sec_pipeline.py`（material direct producer签名迁移）
- `dayu/fins/pipelines/sec_upload_workflow.py`（material direct producer接入同一builder/intent）
- `dayu/fins/pipelines/cn_pipeline.py`（material direct producer接入同一builder/intent）
- `dayu/cli/commands/fins.py`
- `dayu/cli/arg_parsing.py`
- `dayu/fins/tools/upload_tools.py`
- `dayu/fins/tools/fins_tools.py`
- `dayu/fins/tools/error_contract.py`
- `dayu/fins/tools/read_runtime.py`
- `dayu/fins/pipelines/sec_6k_primary_document_repair.py`（仅将`entry.company_meta.ticker`机械迁移到`entry.company_meta.ticker_identity.canonical_ticker`）

### 9.2 Storage and failure

- `dayu/fins/storage/repository_protocols.py`
- `dayu/fins/storage/__init__.py`
- `dayu/fins/storage/_fs_storage_utils.py`
- `dayu/fins/storage/_fs_company_meta_core.py`
- `dayu/fins/storage/_fs_storage_infra.py`
- `dayu/fins/storage/fs_company_meta_repository.py`
- `dayu/fins/storage/fs_batching_repository.py`（仅同步 public exception/lock/commit docstring，不增加行为 wrapper）
- `dayu/fins/upload_failure.py`

`dayu/fins/service_runtime.py`、`dayu/fins/pipelines/sec_pipeline.py`、`dayu/fins/pipelines/sec_upload_workflow.py`、`dayu/fins/pipelines/cn_pipeline.py`不新增failure分支或alias owner；它们保持material aliases handoff，并把既有CompanyMeta upsert机械迁移到同一builder/intent与mapper链。R2已裁决`_STORAGE_FAILURE_CODES`是S2 planned-new code，不把它或其它新增storage code误报成当前遗漏。

### 9.3 Tests

新增：

- `tests/fins/test_ticker_normalization.py`：grammar + `CompanyTickerIdentity` owner contract。

更新：

- `tests/fins/test_fmp_company_info_resolver.py`
- `tests/fins/test_sec_pipeline_upload_filing_stream.py`
- `tests/fins/test_sec_pipeline_upload_material_stream.py`
- `tests/fins/test_sec_pipeline_download.py`（新增或扩展public-path regression，以`target_tickers=None`精确触达`_resolve_target_tickers`的CompanyMeta projection分支）
- `tests/fins/test_cn_pipeline.py`
- `tests/fins/test_fins_storage_atomicity.py`
- `tests/fins/test_fins_storage_provider.py`
- `tests/fins/test_fins_read_runtime.py`
- `tests/fins/test_read_runtime_semantic_ownership_guards.py`
- `tests/fins/test_processor_read_consistency.py`
- `tests/fins/test_fins_ingestion_runtime.py`
- `tests/fins/test_fins_ingestion_tools.py`
- `tests/fins/test_fins_service_runtime.py`
- `tests/cli/test_fins_commands.py`
- `tests/cli/test_arg_parsing.py`
- `tests/cli/test_upload_filings_from_command.py`
- `tests/cli/test_prompt_command.py`
- `tests/service/test_fins_direct.py`
- `tests/service/test_entrypoint_runtime.py`
- `tests/tools/test_combined_tools_acceptance.py`

以上测试文件只做 public constructor/signature迁移和本 WU 行为断言；不得保留旧 fields/functions 的 compatibility expectations。`test_sec_pipeline_upload_material_stream.py`与`test_cn_pipeline.py`保留“material create/update写CompanyMeta”的owner行为，并把断言迁移为`CompanyTickerIdentity`、fresh新增alias不丢与S2 commit intent/authoritative merge；不得把event payload当作持久化证据。

### 9.4 Docs

- `dayu/fins/README.md`
- 根 `README.md`

不改：`tests/README.md`（没有测试层级、运行方式或维护规则变化）、`dayu/README.md`（没有分层/装配边界变化）、Host/Engine README/design。

## 10. Small implementation slices

### S1 — 单一 Company Ticker Identity migration checkpoint

Objective：让grammar、CompanyMeta、resolver、CLI/tool与filing/material pipelines构造/消费唯一identity contract，关闭`V.BA`、单进程fresh meta alias丢失、重复grammar及material producer未纳入统一contract的问题；storage/read public route与并发窗口明确留给强制S2，不把checkpoint表述成目标完成。

Allowed production files：§9.1 中除新增domain commit contract、`dayu/fins/tools/fins_tools.py`、`dayu/fins/tools/error_contract.py`、`dayu/fins/tools/read_runtime.py`以外的identity/producers/consumer文件（包含`sec_6k_primary_document_repair.py`），以及§9.2中的`_fs_storage_utils.py`、`_fs_company_meta_core.py`；storage文件在本slice只迁移CompanyMeta/identity builder consumer，不改public route、commit、recovery或failure projection。

Allowed tests：§9.3中被S1 public constructor/field迁移影响的文件，明确包含`tests/cli/test_prompt_command.py`与`tests/service/test_entrypoint_runtime.py`；两者的`FmpCompanyInfo` fixture必须改用`CompanyTickerIdentity`，canonical-equivalent token不得继续放入`accepted_aliases`。material request/schema/CLI/direct producers由`test_fins_ingestion_runtime.py`、`test_fins_ingestion_tools.py`、`test_fins_service_runtime.py`、material pipeline tests、CLI tests与combined acceptance tests覆盖。

Exact changes：

1. 新增 `CompanyTickerIdentity`、builder、lookup projection，并扩展 single-section US grammar。
2. CompanyMeta 切换到 `ticker_identity`，flat JSON strict round-trip，canonical不再重复进 aliases。
3. FMP、SEC、CN、upload decision与CLI统一builder；SEC/CN material create/update必须通过§5.8稳定helper调用同一个decision，而不是保留`upsert_company_meta_for_upload`的重复fresh/alias逻辑。为保持S1可review checkpoint，`UploadCompanyMetaDecision.company_meta: CompanyMeta | None`与`CompanyMetaRepositoryProtocol.upsert_company_meta`暂时保留；filing与material的单进程fresh/stale merge都用observed existing + declared aliases生成final meta。S2必须把这两个临时stage契约原子替换为§5.3/§6的`CompanyMetaCommitIntent`，因此S1的旧snapshot窗口是明确未完成项而非最终设计。
4. upload validator 仍产生既有 static usage code，但 alias grammar从同一 normalizer取得。
5. storage CompanyMeta write/read/index内部改为消费`ticker_identity`/`lookup_tickers()`。S1明确保留public `resolve_existing_ticker(ticker_candidates: list[str]) -> str | None`：direct canonical probe不变；`_resolve_existing_ticker_by_company_alias`与`_build_company_alias_index_from_meta`删除旧alias normalizers并只遍历每个`CompanyMeta.ticker_identity.lookup_tickers()`，中间index固定为`dict[str, list[str]]`，按canonical排序稳定累积owner；同一lookup出现多个owner仍在read时抛既有late `ValueError`。不得在S1提前收窄为`dict[str, str]`或引入S2 typed error。
6. 更新 upload CLI/tool schema文案；read schema与read runtime在 S2随唯一storage route一起切换。
7. `sec_6k_primary_document_repair._resolve_target_tickers`仅机械读取`entry.company_meta.ticker_identity.canonical_ticker`。现有6-K module regressions没有直接执行该分支；必须在`test_sec_pipeline_download.py`新增或扩展public-path test，以`reconcile_active_6k_primary_documents(..., target_tickers=None)`触达inventory discovery并断言canonical projection，同时由该生产文件逐文件branch coverage `>=80%`、residue scan与全量pyright兜底。
8. 按§5.8把SEC/CN material direct producer纳入同一builder/decision：保留aliases handoff与CompanyMeta batch，删除其重复decision实现；CLI `upload_material`继续解析CSV first canonical + aliases，combined schema明示两个upload kind都支持。material success必须以durable CompanyMeta/read route证明aliases未被忽略。

Non-goals：不在本 slice修改 `commit_batch` lock/validation，不新增 conflict failure code，不顺手处理 download/calendar 或其它 finding。

Tests/validation：owner grammar/identity、CompanyMeta strict round-trip、FMP`V.BA`、CLI`DELTA,MSFT`（含`upload_material`）、filing/material new/fresh/stale merge、combined schema双kind文案、SEC/CN material durable aliases、两个新增fixture consumers与6-K public-path discovery branch。S1 residue scan只临时允许`resolve_existing_ticker`、`_resolve_existing_ticker_by_company_alias`、`_build_company_alias_index`/`_build_company_alias_index_from_meta`及read runtime的旧fallback；旧`FmpCompanyInfo(canonical_ticker=..., ticker_aliases=...)`构造和canonical-equivalent accepted-alias fixture必须零命中，`_canonicalize_ticker_alias`、`_normalize_company_ticker_aliases`等重复grammar helper也必须零命中。material residue必须证明aliases仍从request贯通到统一decision/stage，但`upsert_company_meta_for_upload`旧重复owner与任何material-specific normalization/merge helper零命中。S2删除前两个route symbols，并用`_build_unique_company_identity_index`替换两个list-index helpers，最终`dict[str, str]`只能由该helper产生；全部S1临时允许项必须归零。

Completion signal：resolver output可被upload validator接受；filing与material new/fresh/stale单进程路径保留exact accepted aliases，material成功后CompanyMeta确有对应identity；CompanyMeta与storage中间index只消费唯一identity builder；focused S1 tests通过。S1只是reviewed local checkpoint，仍保留late duplicate detection与A1的prevalidation-to-commit并发窗口，不满足workspace atomicity success signal，不得部署、close或进入final closeout；accepted S1 local commit后必须立即继续S2。若发现正确identity owner需要进入Host/Engine/runtime或需要兼容旧CompanyMeta，立即停止。

### S2 — Workspace 原子 uniqueness、typed failure 与完整 closeout

Objective：让descriptor canonical与CompanyMeta aliases共享workspace unique index，使sequential/concurrent canonical/alias conflict在published side effect前原子拒绝，同时保持合法meta-less corpus canonical可读/可补meta；沿现有typed upload terminal链输出并完成docs/coverage/type validation。

Allowed production files：§9.2全部，以及`dayu/fins/domain/company_meta_contract.py`、`document_models.py`、`upload_company_meta.py`、`ingestion_runtime.py`、SEC/CN stage signature direct consumers、`tools/error_contract.py`、`tools/read_runtime.py`与`tools/fins_tools.py`；只允许实现commit intent、typed projection和S1临时route删除，不新增catch层。

Exact changes：

1. 新增domain`CompanyMetaCommitIntent`/唯一merge helper、typed incoming conflict与包含`invalid_descriptor`的closed published corruption；把S1 final-meta stage切换为transaction-local intent，并由`begin_batch`冻结`publishes_new_corpus`。
2. filing prevalidation decision与SEC/CN material `stage_company_meta_for_upload`都只stage同一种intent；material caller-owned CompanyMeta batch在commit时同样authoritative重读、stable union并校验workspace uniqueness，不能保留S1 final-meta snapshot或另建merge。后续编号中的storage lock/route步骤均同时覆盖filing与material。
3. 按§7 lock order让“meta intent或首次descriptor publication”持有既有recovery guard完成orphan sweep，在identity guard内读取same-canonical authoritative current、按需调用domain helper写final staged meta，再做descriptor canonical + valid-meta aliases的fail-closed uniqueness validation；实现primary/release error preservation与recovery identity guard。既有corpus的document-only commit保持ticker-only。
4. 将storage public route原子切换为`resolve_company_ticker`；删除`resolve_existing_ticker`/`_resolve_existing_ticker_by_company_alias`，用唯一`_scan_actual_published_company_identities` + `_build_unique_company_identity_index`替换S1两个list-index helpers并收窄为`dict[str, str]`。missing meta保留canonical-only；descriptor missing/invalid精确映射`invalid_descriptor`，invalid meta/mismatch/duplicate走各自corruption kind，incoming canonical/alias conflict独立。
5. 同一slice切换read runtime为唯一route、删除normalize/upper fallback，新增corruption/lock typed business projection，并更新九个read tools共用schema；避免guard与consumer跨slice半契约。
6. 收窄`UploadCompanyNameRequiredError`捕获；扩展`FinsUploadFailureReason` closed code/kind mapping，证明SEC/CN filing/material、direct/runtime/tool observation同源投影。
7. 更新两份职责命中的README。

Non-goals：不持久化 alias registry，不做 migration/compat，不修改 Host/Engine，不运行 UF-PF05，不刷新 evidence。

Tests/validation：sequential reverse order、barrier-controlled不同canonical conflict与同canonical lost-update（filing与material producer各至少一条）、storage-public meta-less canonical coexist/read/补meta/双向canonical conflict、update-target conflict/invalid-published-meta tree hash不变、既有corpusno-meta commit不取global guard而首次meta-less descriptor commit必须取、exact lock order、recovery/read barrier、recovery/identity/publication acquire/release failure、recovery order与swap-before-COMMITTED crash interleaving、typed mapper/SEC-CN filing-material/direct/runtime/read-tool projection、canonical/四类alias list_documents e2e、coverage与pyright。

Completion signal：所有 owner/e2e assertions通过；没有 alias conflict可进入 published tree；冲突终态 reason exact且有界；README decision完成。若 lock graph出现未列路径或必须增加第二 durable index，停止并回到 plan review。

Slice count为2：S1仅是可review/commit的identity migration checkpoint，不是可部署或可关闭增量；S2是达成全部goal confirmation success signals的强制连续后续。继续按模块拆分会延长late-conflict半契约，合并成单slice又会把grammar/API迁移与并发故障矩阵放进一次过大的review pass。两slice是在不误报S1完成语义前提下的最小可审查切分。

## 11. Owner-level 与 end-to-end test matrix

### 11.1 Identity owner

- US：`AAPL`、`AAPL.US`、`BRK.B -> BRK-B`、`V.BA -> V-BA`、`AAPL.SW -> AAPL-SW`。
- 长度：8字符有效、9字符失败；带分节按完整 canonical长度计数。
- CN/HK：现有沪深/港 canonical cases不回归。
- canonical-equivalent：`AAPL/AAPL.US/US.AAPL`只形成 canonical，无 accepted alias。
- stable distinct：`DELTA + MSFT`、`V + V.BA`、跨市场 alias首次出现顺序不变。
- invalid：空、多个分节、非法字符、空 alias整体失败。
- CompanyMeta flat JSON round-trip；当`meta.json`存在时，`ticker_aliases`字段wrong type/missing、market mismatch、invalid alias均失败关闭；整个`meta.json`不存在则由descriptor canonical-only contract处理。

### 11.2 Producers and merge

- FMP strict exact symbol + same-name两跳返回 immutable identity；garbage external symbol被producer丢弃，`V.BA`保留为accepted canonical alias。
- SEC submissions与CLI aliases合并只走 builder，不丢 `AAPL.SW`；SEC material `run_upload_material_stream`也通过同一个decision/stage helper持久化identity。
- CN/HK filing/material CompanyMeta使用相同 stable dedupe；CN `upload_material_stream`不得保留独立fresh/alias分支。
- filing与material upload new meta需要company name；fresh unchanged `keep`；fresh new alias `stage`且保持 name/id/version；stale刷新非identity字段并合并旧+新 aliases。
- material owner tests：US/CN create以`DELTA,MSFT,V.BA`成功后strict CompanyMeta包含`MSFT/V-BA`且不重复canonical；fresh material update新增alias不会被`keep`吞掉；event payload与durable meta一致但read断言只从committed CompanyMeta/route取得。CLI `upload_material --ticker DELTA,MSFT`与combined `upload_kind=material,ticker_aliases=[MSFT]`均把exact aliases送入producer。
- `UploadCompanyNameRequiredError`只在missing/stale且缺company name时产生；invalid alias始终是`INVALID_TICKER_ALIAS`，builder/identity corruption不得被catch成`COMPANY_NAME_REQUIRED`。
- commit merge owner tests：fresh current优先于prevalidation staged非identity copy；unchanged stale current应用显式refresh；prevalidation后current变fresh时保留current全部非identity facts但union declared aliases；changed-but-still-stale current抛`CompanyMetaConcurrentUpdateError`；无变化时保留`updated_at`，alias/refresh mutation才更新。
- prevalidation观察到fresh/stale CompanyMeta、commit-time合法descriptor仍在但meta已消失时，pure merge owner统一抛`CompanyMetaConcurrentUpdateError`；不得变成`invalid_meta` corruption，也不得用旧snapshot重建。
- 删除旧“fresh忽略NEW”断言，改为 owner contract断言；不得让测试逼出compat branch。

### 11.3 Storage atomicity

- Sequential A->B与B->A：第二个相同 alias commit抛 `CompanyTickerAliasConflictError`；winner可读，loser absent/保持旧树。
- Existing loser update：提交前后 loser和winner published tree SHA完全相同。
- Concurrent：两个独立 repository core、不同 canonical、同 alias，Event/barrier同时进入commit；exactly one success/one typed conflict，最终index唯一。
- Same-canonical lost-update：用`multiprocessing.get_context("spawn")`与跨进程Event/barrier固定P1 filing fresh-alias prevalidation/intent完成后暂停，P2经SEC或CN material direct producer在same-canonical writer内提交alias Y与fresh facts，随后P1继续。P1 commit必须在writer+recovery+identity保护下重读P2 current并由domain helper产生stable union，最终同时保留P1/P2 aliases且P2更晚durable非identity facts不被P1旧snapshot覆盖。另测P1 refresh intent遇到P2 changed-but-still-stale facts时P1抛`CompanyMetaConcurrentUpdateError`且P2 tree hash不变；再以两个material进程证明writer串行后两次intent均保留aliases。绝不允许silent loss或stale overwrite。
- Meta disappearance：prevalidation intent的`expected_non_identity`非空后，用受控published fixture使commit-time descriptor合法但`meta.json`缺失；commit在backup/swap前抛`CompanyMetaConcurrentUpdateError`，descriptor/document tree SHA不变，terminal projection为有界`storage/storage_io`重试语义而非corruption。
- Distinct aliases并发都成功。
- conflict validation发生在 `_replace_directory` 首次调用前；spy断言 backup/swap零调用。
- identity-changing batch lock order`writer -> recovery -> identity -> publication`；首次storage-public meta-less descriptor commit必须取得recovery/identity guard并验证descriptor canonical，只有既有corpus的document-only batch不取global guards。正常material create/update因含CompanyMeta intent也进入identity-changing路径。
- alias read `identity -> sorted publication`；不得 publication -> identity。
- meta commit注入recovery/identity/current-scan/target-publication guard acquire failure：均在首次backup/swap前失败且published SHA不变；对应release failure遵守最早primary与post-`COMMITTED`规则。
- conflict primary + identity/publication release failure保留 conflict为primary并附note；`COMMITTED`后release failure不回滚。
- orphan batch/backup recovery取得identity guard后才publication，恢复后index唯一。
- crash interleaving：A在target swap后、`COMMITTED`前留下orphan，B已持不同ticker writer准备声明A的旧alias；B必须先在recovery guard内恢复A，再做identity validation并以typed conflict失败，不能先发布B后让recovery制造歧义。
- Meta-less canonical-only：通过public storage batch API或受控“文档descriptor已发布、meta尚未到达”的恢复fixture形成合法descriptor且无`meta.json`，`list_documents(canonical)`返回自身documents；任意alias query为NOT_FOUND。与另一个valid CompanyMeta alias corpus共存时，双方canonical/healthy aliases均正常查询，workspace read不被meta-less状态阻断。该fixture不得伪装成正常material create，因为正常SEC/CN material create/update会写CompanyMeta。
- Meta-less supplement：对既有meta-less target以`refresh_if_stale(expected_non_identity=None)`提交CompanyMeta成功，descriptor canonical保持同owner，新accepted aliases随后与canonical路由同corpus。
- Canonical conflict双向：健康corpus先声明alias`MATERIAL`后通过storage public batch首次发布meta-less canonical=`MATERIAL`，后者在swap前抛`CompanyTickerAliasConflictError`；meta-less canonical=`MATERIAL`先存在时，另一corpus提交alias`MATERIAL`同样原子拒绝。两个方向winner tree SHA不变且index唯一。
- Published invalid fail-closed：实际`portfolio/` corpus的descriptor缺失、symlink/non-regular、invalid JSON/schema/namespace/locator/external canonical时，read与任何identity-changing commit都抛`CompanyTickerIdentityCorruptionError(kind="invalid_descriptor")`；meta存在但invalid JSON/schema为`invalid_meta`，valid meta/descriptor identity不一致为`identity_mismatch`。commit均在backup/swap前失败，incoming及corrupt corpus tree SHA不变；meta absent不失败，backup/lock-only locator不参与authoritative scan，permission/I/O failure不误投影corruption。
- Durable duplicate owner：read/commit scan均抛typed corruption，不伪装incoming alias conflict；commit tree hash不变。
- Recovery-read barrier：recovery在取得identity guard、第一次physical restore前暂停，另进程alias read必须等待；放行后read只得到恢复完成后的正确canonical route，不观察target/backup中间tree。
- Recovery guard failure：对单个orphan注入identity guard acquire failure，断言第一次restore/delete/swap调用为零且journal/backup/staging evidence保留；注入identity guard release failure，断言已完成的restore语义可由新repository一致读取，最早primary/release规则不被覆盖。

### 11.4 Failure projection

- unit mapper：typed conflict -> exact `storage/ticker_alias_conflict/message/hint/None`。
- JSON round-trip接受该kind/code pairing，拒绝错kind。
- SEC与CN upload conflict产生 failed terminal，不降级为 `unexpected_runtime`/`storage_io`。
- direct runtime RESULT、durable summary和awaiting tool observation中的failure JSON exact相等；原始exception、path、lock key、transaction id不出现。
- 静态非法 alias仍是既有 `FinsUploadUsageFailure(INVALID_TICKER_ALIAS)`，证明阶段owner未漂移。
- Published identity corruption（含exact `invalid_descriptor` closed kind）在upload terminal中为有界`storage/storage_io`，绝不成为`ticker_alias_conflict`；incoming conflict仍唯一是`storage/ticker_alias_conflict`。read侧同一kind投影`workspace_identity_corrupted`，普通descriptor I/O投影`storage_unavailable`。
- `CompanyMetaConcurrentUpdateError`投影有界`storage/storage_io`与重试hint，且published tree保持latest writer版本；不成为alias conflict/company-name-required。

### 11.5 Routing and LLM-facing

- 同一fixture上 `list_documents(AAPL/MSFT/AAPL-SW/V.BA)` 按其已声明identity返回同一 canonical ticker与同序 documents。
- invalid/nonaccepted token返回NOT_FOUND，不做company-name/upper fallback。
- durable duplicate/invalid identity由read runtime投影`workspace_identity_corrupted`；合法missing meta的descriptor canonical正常route且无alias；identity/publication guard获取失败投影`storage_unavailable`。read owner与tool outcome均断言固定path-free message/hint，不落入`execution_error`、不hang。
- 九个read tools共用的新ticker schema exact相等。
- upload tool ticker/aliases schema包含 canonical第一义、显式声明、同corpus和不联网核验；不含内部类型/锁/index词。
- upload tool/CLI material文案明确aliases与filing一样由成功CompanyMeta commit持久化，并可路由同一corpus；不得描述成canonical-only或后续filing才生效。
- 三个upload CLI命令help说明CSV语义；`upload_material`的CSV aliases必须进入material producer，download/process help不误宣称CSV。

## 12. Validation commands

全部 implementation validation 在 `source .venv/bin/activate` 后执行。

### 12.1 Focused tests

```bash
pytest -q \
  tests/fins/test_ticker_normalization.py \
  tests/fins/test_fmp_company_info_resolver.py \
  tests/fins/test_sec_pipeline_upload_filing_stream.py \
  tests/fins/test_sec_pipeline_upload_material_stream.py \
  tests/fins/test_cn_pipeline.py \
  tests/fins/test_fins_storage_atomicity.py \
  tests/fins/test_fins_storage_provider.py \
  tests/fins/test_fins_read_runtime.py \
  tests/fins/test_read_runtime_semantic_ownership_guards.py \
  tests/fins/test_fins_ingestion_runtime.py \
  tests/fins/test_fins_ingestion_tools.py \
  tests/fins/test_fins_service_runtime.py \
  tests/cli/test_fins_commands.py \
  tests/cli/test_arg_parsing.py \
  tests/cli/test_upload_filings_from_command.py \
  tests/cli/test_prompt_command.py \
  tests/service/test_fins_direct.py \
  tests/service/test_entrypoint_runtime.py
```

再运行受 CompanyMeta constructor/schema机械迁移影响的：

```bash
pytest -q \
  tests/fins/test_sec_pipeline_download.py \
  tests/fins/test_processor_read_consistency.py \
  tests/tools/test_combined_tools_acceptance.py
```

### 12.2 Regression suites

```bash
pytest tests/fins tests/cli tests/service tests/tools -q
```

不运行 UF-PF05、oracle/scenario registry、真实网络 FMP 或冻结 evidence smoke。

### 12.3 Coverage

用 focused + regression tests生成 coverage，然后对每个修改生产文件逐一执行 `coverage report --include=<file> --fail-under=80`，不能只看aggregate：

```bash
coverage erase
coverage run --branch -m pytest tests/fins tests/cli tests/service tests/tools -q
```

逐文件范围为 §9.1、§9.2 中实际发生代码修改的 `.py` 文件。若任一文件低于80%，补 owner行为测试；不得以 omit、pragma、降低阈值或无意义执行行绕过。仅 docstring变化的文件仍不豁免。

### 12.4 Type and residue scans

```bash
python -m pyright dayu/ tests/ utils/
rg -n '_canonicalize_ticker_alias|_normalize_company_ticker_aliases|_normalize_ticker_aliases|normalize_sec_ticker_aliases|_merge_ticker_aliases|_normalize_ticker_token|_dedupe_ticker_aliases|resolve_existing_ticker|_resolve_existing_ticker_by_company_alias|_build_company_alias_index(_from_meta)?' dayu tests
rg -n 'company_meta\.(ticker|market|ticker_aliases)|existing_meta\.(ticker|market|ticker_aliases)' dayu tests
rg -n -U 'FmpCompanyInfo\((?s:.{0,400})(canonical_ticker|ticker_aliases)=' dayu tests
rg -n 'upsert_company_meta_for_upload' dayu tests
```

以上是S2/final residue gate，四个scan预期零命中；multiline Fmp scan必须覆盖`test_prompt_command.py`、`test_entrypoint_runtime.py`与`test_upload_filings_from_command.py`的旧fixture构造，避免单行regex漏检。最后一个scan证明SEC/CN material已删除旧重复decision owner，但不删除material aliases：实现artifact还必须逐项列出`FinsUploadMaterialRequest.ticker_aliases -> service_runtime -> SEC/CN stage_company_meta_for_upload -> CompanyMetaCommitIntent`直接调用点和对应owner test，防止“零命中”被错误实现成accept-ignore。S1 checkpoint按§10明确的临时route允许项单独记录命中，不能把它误报为work unit完成。若同名字符串属于无关上下文，必须在implementation artifact逐条解释，不能保留compatibility symbol。

## 13. README decision

- `dayu/fins/README.md`：必须更新。其职责明确包含Fins public contract、storage mutation/lock、resolver与read route。更新CompanyTickerIdentity/FmpCompanyInfo接口、descriptor canonical + optional CompanyMeta aliases的owner分解、meta-less canonical-only route/后续补meta、workspace identity guard/commit validation，以及typed conflict terminal；删除“resolver aliases首项为canonical”和read loose行为的旧事实。
- 根 `README.md`：必须更新。direct `upload_filing` / `upload_material` / `upload_filings_from` 的 user-visible `--ticker` CSV语义、alias信任与冲突错误发生变化，属于最终用户工作流。
- `tests/README.md`：不更新；测试层级、运行方式、维护规则未变。
- `dayu/README.md`：不更新；UI/Service/Host/Engine/Fins分层与装配方式未变。
- Host/Engine README/design：不更新；本 WU不修改其边界。

## 14. Goal alignment matrix

| Decision / slice / validation | Confirmed goal or safety condition |
| --- | --- |
| `CompanyTickerIdentity` + builder | grammar/去重/结构化关系唯一 owner |
| CompanyMeta ticker_identity | durable meta不从散字段反推identity |
| descriptor canonical + optional valid-meta aliases | storage meta-less corpus保持canonical可读且不虚构alias；正常material producer仍写meta |
| filing/material共用builder + commit intent | 两种upload kind的accepted aliases均可靠持久化且不形成第二真源 |
| FMP/SEC/CN/CLI删除重复helper | resolver/upload同源并接受`V.BA` |
| fresh/stale merge state transition | 用户明确alias不丢失 |
| commit intent + authoritative current merge | 同canonical并发不丢alias且不覆盖更晚durable非identity facts |
| storage single-token route | canonical/accepted aliases命中同corpus；移除read fallback |
| workspace identity guard + commit validation | 冲突在published副作用前原子拒绝 |
| conflict/corruption分型（含`invalid_descriptor`）与read projection | incoming调用错误不与published损坏混淆；descriptor损坏有closed kind且read错误有界可行动 |
| existing terminal failure code | CLI/tool/direct/runtime有界可行动失败 |
| schema/help updates | LLM/用户自足理解canonical与alias语义 |
| S1 tests | owner/producer/consumer contract |
| S2 concurrency/hash/failure tests | atomicity与same-corpus e2e |
| coverage/pyright/README | 项目强制validation与文档职责 |

没有一项 slice 或 validation 来自 confirmed goal之外的finding。

## 15. Why this is not over-design

- 只新增identity value/builder、一个commit intent + pure merge helper、incoming conflict/published corruption两个不可混用的typed errors和一个workspace file lock；每项都直接对应已确认业务事实、lost-update或read/write fail-closed条件。
- unique index只从既有descriptor canonical与valid CompanyMeta accepted aliases机械派生，不新增数据库、registry、cache、journal schema或双写。
- recovery + identity guards只覆盖记录了CompanyMeta commit intent或首次发布corpus descriptor的commit；既有corpus普通filing/source/processed publication继续ticker并发。
- `publishes_new_corpus`只是begin_batch已有target-existence事实的transaction-local冻结，用于让首次meta-less descriptor canonical进入同一原子validation；不新增journal/schema，recovery仍按R1全量guard。
- material不新增validator、registry或merge state machine；只把既有SEC/CN `upsert_company_meta_for_upload`重复逻辑收敛到filing已使用的decision，并在S2机械切换为同一种commit intent。
- 复用现有 filelock、batch rollback/recovery、pipeline failure mapper、runtime summary与tool observation，不新增facade/adapter/state machine。
- Host/Engine/runtime保持层中立，不为Fins业务语义扩展公共治理层。
- 不做旧库兼容、迁移、联网校验、现实公司纠错或future market abstraction。

## 16. Risks、open questions 与 stop conditions

### 16.1 Blocking open questions

无。owner、public types、锁序、commit validation、failure transport、files、slices与tests均已冻结。

### 16.2 Classified residual risks

| Risk / uncovered area | Classification | Owner / destination |
| --- | --- | --- |
| 旧workspace可能已有歧义alias或旧CompanyMeta alias字段语义 | `assigned to later work unit` | 明确不兼容；如需升级另开migration WU |
| UF-PF05真实CLI evidence | `assigned to later work unit` | 用户明确排除 |
| oracle/scenario registry、冻结evidence、其它finding | `assigned to later work unit` | 用户明确排除 |
| 外部provider返回不满足grammar的symbol | `covered by later approved slice` | S1 producer直接输入校验，非法项不成为accepted alias |
| identity-changing commit workspace级串行带来少量延迟 | `covered by later approved slice` | S2将guard限制在authoritative validation/swap且仅meta intent或首次descriptor publication；无证据要求cache |
| workspace descriptor/meta scan成本随公司数增长 | `assigned to later work unit` | 当前无性能证据，不预建index；若真实profile超标再单独立项 |
| recovery对所有orphan tree取得identity guard可能增加读写等待 | `assigned to later work unit` | R1已拒绝用`meta.json`存在推断mutation；只有实测contention后另立性能WU且不得削弱correctness guard |
| SEC upload/SEC download/CN download既有resolver version不一致 | `assigned to later work unit` | rereview controller裁决为既有行为且本WU不恶化；如需统一另立CompanyMeta freshness WU |

没有 unclassified residual risk。

### 16.3 Implementation stop conditions

- 发现任何 publication -> identity guard 的反向锁路径。
- 正确实现必须新增第二个 durable alias source或修改Host/Engine。
- 需要兼容旧CompanyMeta/歧义workspace才能通过测试。
- 现有 pipeline typed failure链无法原样携带owner-produced conflict，且需要新公共transport。
- 发现本 WU之外 schema/业务行为必须改变。

任一条件出现时停止 implementation，回到 plan review/goal reconfirmation，不做局部fallback。

## 17. Completion report format

后续 implementation slice完成时，artifact必须逐项报告：

1. 改了什么：public contract、owner、state transition、lock/validation、failure projection、docs。
2. 验证了什么：focused/regression/coverage/pyright/residue scans及结果。
3. finding状态：accepted/rejected/deferred及re-review证据。
4. residual risks：按Gateflow分类并给owner/destination。
5. changed files与commit状态。
6. next entry point。

本第二轮plan fix gate的next entry point固定为`plan re-review`，必须使用`planreview` skill复核P1–P5（其中旧P4拒绝方案已按完整证据`rejected-with-reason`撤回），并确认A1–A8与R1/R2保持closed；re-review accepted后由Gateflow在当前分支创建accepted plan local commit并自动进入S1 implementation，不直接跳过re-review，也不执行PR/push。
