# UF-FIX07 multi-file-primary-and-collision 实施计划

## Gate 元数据

- Work unit：`UF-FIX07 multi-file-primary-and-collision`
- Gate：`plan re-review adjudication`
- 日期：2026-08-15
- 基线提交：`b7725096f408891c87755198f91e63cef041fdf5`
- 主控：AgentController
- 当前委派：收敛两路 re-review 并关闭 plan review loop；不进入实现或 commit
- 决策：`PLAN ACCEPTED / ACCEPTED PLAN COMMIT PENDING`
- Blocking open question：无
- 下一入口：由 AgentController 执行 `accepted plan commit`；本 agent 在此停止，不进入 commit、implementation 或 PR
- Artifact path：`docs/gateflow/uf-fix07-multi-file-primary-collision-plan-20260815.md`

## 1. 输入、证据与禁止边界

本计划依据以下已读取输入与当前代码事实：

- 项目约束：`AGENTS.md`，SHA-256
  `cb26618ab566804c97a3ef2f269537b7313e59370e5ddd0258d9b753b08ac45e`。
- Host 设计真源：`docs/host/design.md`，SHA-256
  `7214cbcbef21b36c9020758da8fc4c5003c3813f6ded32ed77238af58327fe06`。
- Engine 设计真源：`docs/engine/design.md`，SHA-256
  `b190e3a8ee2df84d29546ca04d4fb7d81a73877b27a3bddd04d2aaa40db17b1e`。
- 已确认 goal artifact：
  `docs/gateflow/uf-fix07-multi-file-primary-collision-goal-confirmation-20260815.md`，SHA-256
  `162a23cd7c36dc348e8e0af221ffdea4e38144a2592d80ce9fe2772a3c6368a4`。
- Accepted oracle：`docs/cli_ci_oracles.json` 的
  `upload_filing.multi-file-and-primary`，文件 SHA-256
  `88b04ca47472f320b614ad1374a9f0a243443efaca1e0565eaf29b5f0cb770b8`。
- Accepted registry evidence：`docs/cli_ci_scenarios.json` 中的 `UF-FIX07` finding record（不是 scenario id）及其引用的
  `UF-F11`–`UF-F13`、`UF-D04`–`UF-D06`、`UF-C05`–`UF-C06`、`UFS-006`，文件 SHA-256
  `a357e5a1e0ee11cb42f8ab6e25083b23761a4c8181d14ddc1876f0bf9a788efb`。
- 两路 plan review：`docs/reviews/plan-review-20260815-183830.md` 与
  `docs/reviews/plan-review-20260815-184718.md`；逐项裁决记录见
  `docs/gateflow/uf-fix07-multi-file-primary-collision-plan-fix-20260815.md`。
- 两路 plan re-review：`docs/reviews/plan-review-20260815-190003.md` 与
  `docs/reviews/plan-review-20260815-190711.md`；最终裁决记录见
  `docs/gateflow/uf-fix07-multi-file-primary-collision-plan-re-review-adjudication-20260815.md`。
- 当前 Fins raw/validated request、CLI、LLM upload tool、SEC/CN workflow、
  `DoclingUploadService`、storage snapshot/primary、`process_filing` 与相关测试。

实施期间以下文件和动作始终禁止：

- 不修改 `docs/cli_ci_oracles.json`、`docs/cli_ci_scenarios.json`、任何冻结 evidence、已确认 goal artifact、
  `docs/host/design.md` 或 `docs/engine/design.md`。
- 不执行 UF-PF07、UF-PF12 或其它真实 mandatory scenario/evidence run；pytest 的本地 deterministic owner tests
  不属于这些禁止场景。
- 不修改 Host / Engine 生命周期、EventLog、memory、trace、ToolRuntime governance 或调度代码。
- 不 commit、不 push、不创建或推进 PR；这些动作只能由后续获授权 gate 执行。

## 2. 第一性原理判断与直接代码证据

问题真实存在，严重性评估成立，而且 primary 选择、original 碰撞与 derived 碰撞是同一条缺失契约的连续后果，
不应分别在 CLI、storage reader 或 `process_filing` 做下游补偿。

1. 一个 filing 的处理输入只能有一个 primary。`FinsUploadFilingRequest` 当前只有 `files`；
   `_validate_fins_upload_filing_static()` 按 index 0 分配角色，
   `FinsUploadFilingFiles.from_upsert_paths()` 再次固定 `paths[0]`。因此 primary 不是请求事实，只是顺序副作用。
2. CLI `upload_filing` 当前只注册 `--files`，help 明说“首文件是主文件”；LLM-facing
   `start_fins_upload` schema 也只有 `files`。两个入口都无法声明同一个 primary 事实。
3. `DoclingUploadService._build_original_assets()` 把 basename 直接作为 blob/storage `name`；
   `_build_pending_assets()` 又从 stem 生成 `<stem>_docling.json`。不同目录同 basename、同 stem 不同后缀均可
   落到相同仓储 key。
4. `_store_upload_assets()` 以该 `name` 写 blob，并把它写入 source `files[]` 与 `primary_document`；碰撞已经进入
   publication contract，不只是 UI 显示问题。
5. SEC 与 CN/HK workflow 已经在 fresh published-state read 后重新调用同一个 filing validator，并把
   `authoritative_request.file_selection` 原样交给 upload service；Service/runtime 无需也不应新增第二套 primary 选择。
6. storage snapshot 的 `_parse_snapshot_files()` 已拒绝重复 `file.name`，并要求
   `primary_document` 精确命中 `files`；`snapshot.get_primary_source()` 只按该 exact pointer 取文件。
   `ingestion_runtime._preprocess_one_document()` 和 read runtime `_create_processor_from_snapshot()` 都只消费这条路径。
   因而 `process_filing` 不应重新扫描或选择文件，真正缺口在 publication 上游。
7. upload preparation 在 converter 前完成，publication batch 在全部读取/转换完成后才开启；
   `commit_prepared_upload_batch()` 与 storage batch 已拥有 commit/rollback 原子性。应保持该 owner，只改变 pending assets
   的 identity/metadata，不新建事务层。

结论：修复必须在 Fins raw request/static admission、typed role selection 与 Docling asset preparation owner 中完成；
CLI/LLM tool 只投影 raw selector，storage 只持久化 exact identity/primary，downstream 只读取 published primary。

## 3. Goal、成功信号、非目标与 scope boundary

### 3.1 Goal 与成功信号

1. 单文件 filing upsert 在未声明 selector 时自然以唯一文件为 primary；允许显式声明同一唯一文件，但不能声明集合外文件。
2. 多文件 filing upsert 必须且只能声明一个 primary，且其规范路径必须属于规范后的 `files` 集合；primary 可以位于
   `files` 任意位置，结果不依赖顺序。
3. CLI 新增单值可重复出现的 `--primary PATH` 语法并保留每次出现；重复 `--primary` 由 Fins request owner 以 usage
   failure 拒绝，不能让 argparse 的 last-wins 吞掉证据。
4. LLM-facing `start_fins_upload` schema 新增可选字符串字段 `primary`，自足说明 filing 单文件、多文件、delete 与 material
   规则；`files` 明确 `maxItems=100`。tool adapter 只把该单值映射为 raw selector，不选择 primary。
5. 同一 validator 在 workspace read、observation/job 创建、converter 与 publication 前拒绝：delete 携带 files、delete 携带
   selector、规范路径重复、multi-file 缺 primary、selector 多于一个、selector 不属于 files、超过 100 个文件。
6. validated request 只通过 `FinsUploadFilingFiles` 暴露 authoritative primary/companions；workflow 与 Service 原样消费，
   不再按 index、basename、stem、文件系统顺序或转换结果推断。
7. 每个规范后不同的输入路径产生确定、path-free、request-order-independent 的 original storage identity；不同目录同
   basename、同 stem 不同后缀可共存。storage `files[]` 同时保存用户可读 `original_filename` 投影。
8. 每个 Docling derived identity 直接从对应 original storage identity 派生，并在 metadata 中保存
   `derived_from`；filing 只为 explicit/authoritative primary 生成一个 derived asset 与一次 `conversion_started`。
9. storage `primary_document` 必须等于该 primary derived identity，并精确命中同次 publication 的 `files[].name`；
   `process_filing`/read runtime 继续只通过 snapshot `get_primary_source()` 消费它。
10. 成功 publication 时 `requested_file_count == stored_file_count == original 输入数`，derived 不计数；primary 转换失败、
    任一 original 读取失败或 batch publication 失败时 `stored_file_count=0` 且无 partial source/company/blob publication。
11. 100 个不同文件加一个明确 primary 可通过 validation 并完整发布 100 个 originals + 1 个 filing derived；101 个文件
    在 workspace read 前拒绝。
12. 受影响测试、每个修改生产文件的覆盖率目标和全仓 pyright 通过；README 按职责同步。

### 3.2 非目标

- 不处理 UF-FIX08 existing-source auto repair、UF-FIX10 concurrency、UF-FIX11 company meta warning。
- 不改变 UF-FIX06 已建立的 converter capability、primary/companion suffix 与 material 全转换规则。
- 不为 `upload_filings_from` 自动归组附件；它仍生成单文件命令，单文件规则自然产生唯一 primary，不要求脚本增加
  `--primary`。
- 不引入全局 asset catalog、数据库序列、随机 UUID、content sniffing、MIME fallback、兼容 re-export/wrapper、
  loose parsing 或旧 schema 兼容读取。
- 不按 inode/hardlink 或平台文件系统大小写规则判重；本 work unit 的相等事实是 `resolve(strict=False)` 后 path string 的
  case-sensitive exact equality。symlink 与 `..` alias 经 resolve 后若字符串相同则是同一路径；case alias 与 hardlink 即使
  指向同一 inode，只要 resolved path string 不同，仍是两个输入。
- 不改变 material 的 asset name、derived name、`files` metadata、source fingerprint、用户事件或 failure path；filing 的
  collision-free path identity、`original_filename`/`derived_from` storage schema 不扩展到 material，也不新增 material
  duplicate-path 处理。
- 不让 storage reader、manifest reader、processor 或 UI 从集合中重新挑 primary，也不为 companions 生成 Docling 占位。
- 不改变 direct result 的 requested/stored count、action/update identity、calendar/year、ticker alias、取消或 commit
  linearization。

## 4. Design document alignment

- `docs/engine/design.md` 明确 Engine 不理解财报业务语义、不直接访问财报 storage；它只接收工具 schema、调用请求与
  outcome。因此 `primary` 只进入 Fins 工具 schema/arguments，不新增 Engine request/event contract。
- `docs/host/design.md` 明确 Host 拥有 Run/Attempt/EventLog/ToolRuntime governance，但 Host 不承载财报仓储规则。
  `start_fins_upload` 仍是外部业务 ToolDefinition；Host 只执行其 callable，不校验 filing primary。
- direct CLI upload 继续走 `UI -> Service -> Fins` 的既有 direct path，不改造成 Host Run。
- Fins 文档存取继续只通过 `dayu.fins.storage` 仓储协议/实现；asset preparation 不直接操作 published 目录。
- `dayu.runtime` 不承载 primary、asset identity 或上传判重语义。

## 5. 语义 owner 决策

| 语义 | 唯一 owner | 产生/校验/持久化/投影职责 | 禁止的下游补偿 |
| --- | --- | --- | --- |
| raw filing 文件与用户 selector 次数 | `FinsUploadFilingRequest.primary_selectors` | CLI 保留所有 `--primary` occurrence；LLM `primary` 映射为 0/1 个 selector；raw request 不提前选择角色 | argparse last-wins、CLI 自行选首项、Service extra payload |
| 规范路径、不同输入集合、100 上限、selector cardinality/membership | `dayu.fins.ingestion_runtime::_validate_fins_upload_filing_static` | 在 workspace read 前统一 expand/resolve、判重、校验单/多文件与 delete 组合、产生 typed selection | tool/Service/workflow 重验或 fallback |
| authoritative primary/companions | `dayu.fins.upload_format_contract.FinsUploadFilingFiles` | 保存已验证且规范化的唯一 primary 与 companions；格式 owner 按角色校验 | `from_upsert_paths(paths[0])`、按 index/stem 重建 |
| CLI/LLM 业务文案 | `project_fins_upload_format_text()` | 显式投影 `filing_primary` 与 `upload_tool_primary`；CLI help/tool schema 各自机械消费，并共享单/多文件、membership、delete 关键规则 | 两入口分别硬编码不同规则 |
| filing original asset identity、original filename 投影 | `DoclingUploadService` 的 typed filing asset preparation | 从 authoritative normalized path 产生 storage identity；basename 只进入 `original_filename`、fingerprint 与用户事件；material 保持现状 | basename 作为 filing key、storage/CLI 重算 identity、把 filing schema扩到 material |
| filing derived identity 与 original 关联 | 同一 filing asset preparation owner | 接收 exact original identity，派生 `<original-identity>_docling.json`，保存 `derived_from`；material 保持现状 | 从 raw stem、published directory或生成顺序反推 |
| published files/primary 一致性与原子可见性 | `dayu.fins.storage` source publication contract | 同 batch 保存 exact names/metadata；commit validator/snapshot 要求 names 唯一且 primary exact 命中 | publication 后改 meta、processor 扫描挑选 |
| downstream process 输入 | storage snapshot `get_primary_source()` | `process_filing` 与 read runtime 只消费已发布 primary | 按 original、basename、mtime 或目录顺序改选 |
| requested/stored original count | 现有 upload result owner | request 数量与成功 commit 的 original 计数同源；derived 不计数 | 从 files 总数或目录重新计数 |

Owner 已清楚，无需新增跨层抽象。

## 6. Contract 与 schema 设计

### 6.1 Raw request

`FinsUploadFilingRequest` 新增 required-by-type、带空 tuple default 的显式字段：

```python
primary_selectors: tuple[Path, ...] = ()
```

选择 tuple 而不是 `Path | None` 的原因是 CLI 必须保留重复 `--primary` 的原始 cardinality，才能由 Fins request owner
一次拒绝；否则 argparse last-wins 会不可逆地丢掉错误事实。该字段只表示 selector 声明，不表示已验证 primary。

- CLI：每次 `--primary PATH` append 到 `ParsedCliArgs.primary`，随后全部执行与 `files` 相同的
  `expanduser().resolve(strict=False)` 机械路径投影，构造 tuple。
- LLM tool：schema 暴露单个 `primary: string`；省略映射为空 tuple，提供映射为单元素 tuple。JSON object 本身不允许同名
  字段表达两个 selector，故不需要 tool-local cardinality owner。
- Service/workflow：继续传递 raw request 或 validated request，不新增 primary 参数。

本计划中“normalized equality”只表示对 `resolve(strict=False)` 结果取 exact path string 后做 case-sensitive equality；不调用
`normcase()`，不查询 inode，也不以文件系统是否大小写敏感改变结果。duplicate 与 primary membership 必须复用同一个比较
helper，禁止一个使用 exact path string、另一个使用 basename、inode 或平台 alias。

### 6.2 Static admission 与 validation precedence

在 `_validate_fins_upload_filing_static()` 中冻结以下顺序；所有错误都在
`_filing_upload_request_identity()` 的 workspace state read 前发生：

1. 保持现有 ticker -> source kind -> action -> `len(files) <= 100` -> year/period/date/company 校验优先级；create/update 的
   missing-files 继续使用现有 `MISSING_FILES`。
2. action 为 delete 且 raw `files` 非空时，立即抛 `FILES_NOT_ALLOWED_FOR_DELETE`。本检查先于任何 file/selector path
   resolve、duplicate、basename、exists、regular 或 role 校验；即使同时携带 `primary_selectors`，也必须先返回此 code。
3. action 为 delete、`files=()` 且 `primary_selectors` 非空时，抛 `PRIMARY_NOT_ALLOWED_FOR_DELETE`；合法 delete 直接构造
   `for_delete()`，不进入后续 path/role 流程。
4. 仅对 upsert 的每个 raw file 与 selector 执行 `expanduser().resolve(strict=False)`，得到 canonical path string；
   normalized `files` 必须保持用户输入顺序。
5. 若 normalized `files` 的 exact case-sensitive path string 有重复，抛 `DUPLICATE_FILE_PATH`；该检查先于
   exists/regular/converter。case alias 与 hardlink 不按 inode 合并。
6. 任意 upsert selector 多于一个，抛 `MULTIPLE_PRIMARY_SELECTORS`。
7. 单文件 upsert：无 selector时选择唯一 normalized file；有一个 selector 时要求它属于 files，否则抛
   `PRIMARY_NOT_IN_FILES`。
8. 多文件 upsert：无 selector 抛 `MISSING_MULTI_FILE_PRIMARY`；一个 selector 必须按同一 exact path-string equality 属于
   files，否则抛
   `PRIMARY_NOT_IN_FILES`。
9. 按 normalized files 执行 basename、exists、regular 校验；primary 使用 primary suffix capability，其余使用 companion
   capability。不得再使用 enumerate index 分配角色。
10. 构造 `FinsUploadFilingFiles.for_upsert(primary=..., companions=...)`；companions 是从 normalized files 去除 primary 后的
    原相对顺序。

`FinsUploadUsageCode` 与现有 `_USAGE_MESSAGES: Mapping[FinsUploadUsageCode, str]` 直接增加以下六个 closed code 和固定字符串；
不新增 `_FIXED_USAGE_MESSAGES`、消息 wrapper 或第二套分发。现有 `fins_upload_usage_failure()` 对非 `_FILE_USAGE_CODES` 的分支
直接读取这些固定字符串。消息必须中文、可行动、<=240 字符且不包含本地路径：

- `FILES_NOT_ALLOWED_FOR_DELETE`：`delete 不得提供 --files`
- `DUPLICATE_FILE_PATH`：`--files 不能包含解析后相同的重复路径`
- `MULTIPLE_PRIMARY_SELECTORS`：`--primary 只能指定一次`
- `MISSING_MULTI_FILE_PRIMARY`：`多文件 filing 必须使用 --primary 明确指定主文件`
- `PRIMARY_NOT_IN_FILES`：`--primary 必须精确匹配 --files 中的一个文件`
- `PRIMARY_NOT_ALLOWED_FOR_DELETE`：`delete 不得提供 --primary`

超过 100 个文件继续使用现有 `TOO_MANY_FILES`；100 个恰好允许。不得复用 generic invalid argument 掩盖这些语义。
delete 精确 precedence 为：`TOO_MANY_FILES`（若命中既有 raw count gate）→ `FILES_NOT_ALLOWED_FOR_DELETE` →
`PRIMARY_NOT_ALLOWED_FOR_DELETE`；后两者均先于任何 path resolve/duplicate/exists/role。

### 6.3 Validated selection

删除 `FinsUploadFilingFiles.from_upsert_paths()` 这一“首项即 primary”的构造入口，不保留兼容 wrapper。新增唯一 upsert
构造入口 `for_upsert(*, primary: Path, companions: tuple[Path, ...])`；其职责是：

- 校验 `Path` 类型、primary/companion 格式角色与 delete 空状态；
- 暴露 `primary`、`companions`、`ordered_files`、`require_primary()`、`is_empty`；
- 不重新做路径 resolve、集合 membership、重复或 100 上限，这些属于 ingestion static validator。

`ValidatedFinsUploadFilingRequest.file_selection` 继续是 required typed fact。raw `request.files` 保留调用方输入，
authoritative Service input 只取 `file_selection`。fresh workflow validation 从同一 raw
`primary_selectors` 确定性重建同一 selection；不新增 selection equality fallback。

### 6.4 CLI `--primary`

`upload_filing` 注册：

```text
--primary PATH
```

- 使用 `action="append"`、单 occurrence 单值；未提供为 `None`/空 list，重复 occurrence 全部保留。
- 只在 `upload_filing` 注册；`upload_material` 与 `upload_filings_from` 不增加该选项。
- argparse 只负责语法收集，不使用 custom action 提前决定业务错误。
- `_prevalidate_upload_filing_request()` 将所有 occurrence 映射到 `primary_selectors`，由 Fins validator 返回 typed usage
  failure，CLI 既有 mapping 输出一行 stderr、exit 2、Service factory 零调用、workspace 零 mutation。
- help 机械消费 `FinsUploadFormatTextProjection.filing_primary`：单文件可省略，多文件必须指定一次，值必须属于
  `--files`，顺序不决定角色；CLI 不另写同义文案。

### 6.5 LLM-facing tool `primary`

`FinsUploadFormatTextProjection` 在现有 `filing_files`、`material_files`、`upload_tool_files` 之外显式新增两个字符串字段：

- `filing_primary`：只供 CLI `upload_filing --primary` help 机械消费；
- `upload_tool_primary`：只供 `start_fins_upload.properties.primary.description` 机械消费。

二者由 `project_fins_upload_format_text()` 内同一组模块级业务规则片段组成，不能在 CLI 或 tool adapter 重新拼写关键规则。
`start_fins_upload` schema 的 properties 增加：

```json
"primary": {
  "type": "string",
  "description": FINS_UPLOAD_FORMAT_TEXT.upload_tool_primary
}
```

文案必须在当前 schema 内自足说明：

- `upload_kind=filing` 且一个文件时可省略；省略即唯一文件；
- filing 多文件时必填，且必须精确等于 `files` 中一个路径；数组顺序不代表 primary；
- delete 与 `upload_kind=material` 必须省略；
- primary 是用户选择的业务角色，不是质量、重要性或转换成功的推断。

`filing_primary` 与 `upload_tool_primary` 可因入口名分别使用 `--files`/`files`，但必须同源包含并由测试逐字断言以下关键规则：
单文件可省略、多文件恰好一个、selector 必须属于 files、顺序不决定角色、delete 禁止；tool 字段还必须明确 material 禁止。

`files` schema 增加 `maxItems: 100`，继续说明 upsert/delete 与 suffix 规则。`primary` 不加入顶层 required，因为其必填性是
filing 多文件条件规则。tool adapter：

- filing 把可选 `primary` 解析为 0/1 个 resolved Path 后写入 raw request；
- material 若收到 `primary`，在 request union discrimination boundary 返回 invalid argument，不把字段塞入 material extra
  payload；
- 不在 adapter 中做 membership、单/多文件或 primary suffix 判定，这些仍由 Fins validator/selection owner 完成。

### 6.6 Filing asset identity、original filename、fingerprint 与 derived association

以下 schema 仅用于 filing。在 `docling_upload_service.py` 内增加 filing 专用模块级私有 helper，不新增通用 registry：

```text
namespace = "fins-upload-asset-v1"
path_digest = sha256(namespace + NUL + normalized_path.as_posix()).hexdigest()
original identity = "original-" + path_digest + normalized lower-case suffix
derived identity = original identity + "_docling.json"
```

filing identity 冻结规则：

- 输入必须来自 validated selection 的 absolute normalized Path；禁止 raw basename/stem、request index、随机值、时间戳或
  storage 路径参与 identity。
- 使用完整 64 位十六进制 SHA-256；同一 normalized path 重跑得到相同 identity，输入重排不改变 identity；不同路径即使
  basename/content 相同也得到不同 identity。
- 生成 filing original identities 后做一次 request-local uniqueness assertion；由于 static owner 已拒绝 duplicate normalized
  path，此处只防理论 digest collision 或实现错误，并在 converter/publication 前以内部不变量错误 fail closed，不能覆盖。
- derived helper 的唯一输入是 exact original identity，结果直接追加 `_docling.json`，因此仍满足现有
  `DoclingProcessor` 后缀识别，并能证明 derived 与 original 同源。

扩展 `_PendingFileAsset` 为严格 typed preparation fact，至少包含：

- `name`：filing 为 storage identity，material 保持现有 basename/stem-derived name；
- `original_filename: str | None`：filing 为用户输入 basename，material 显式为 `None`；
- `derived_from: str | None`：filing original 为 `None`，filing Docling derived 为 exact original identity，material 显式为
  `None`；
- 既有 data/content type/sha256/size/source。

不得依靠 dataclass default 隐式漏填；三个生产方法的 exact field/event mapping 冻结如下：

| 方法 | filing original / derived | material（回归边界） |
| --- | --- | --- |
| `_build_original_assets()` | original `name=<path identity>`、`original_filename=file_path.name`、`derived_from=None`；读取空文件失败仍使用既有 basename failure label | `name=file_path.name`、`original_filename=None`、`derived_from=None`，其余字段与 failure path 不变 |
| `_build_pending_assets()` | 只转换 authoritative primary；derived `name=<exact original name>_docling.json`、继承该 original 的 `original_filename`、`derived_from=<exact original name>`；`conversion_started.name=file_path.name` | 继续逐项转换，derived name 仍为 `<file_path.stem>_docling.json`，两个新字段均为 `None`，primary 仍是首个 converter derived |
| `_store_upload_assets()` | blob filename/entry `name`/URI 使用 identity；entry 对 original/derived 都写 `original_filename`，仅 derived 写 `derived_from`；`file_uploaded.name=asset.original_filename`，`payload.source` 保持区分 original/docling | blob key、entry metadata、`file_uploaded.name=asset.name`、payload、failure 与 count 全部保持现状，不写 `original_filename`/`derived_from` |

`_build_stored_file_entry()` 必须显式接收 `source_kind`（或等价的强类型 filing projection decision）并执行上表；禁止
`getattr/hasattr`、松散 dict fallback 或让 material 偶然获得 filing metadata。

filing `uri` 的 physical filename 必须与 identity `name` 一致；`primary_document` 保存 exact filing derived identity。path digest
不得进入用户/LLM 可读事件，也不得进入 `source_fingerprint`。

`_build_upload_source_fingerprint()` 冻结为 source-kind-aware 的既有 owner，不新增第二套 fingerprint helper：

- filing original descriptor 只含 `original_filename`、`sha256`、`size`、`source`，按这四项组成的稳定 tuple 排序后序列化；
  path-derived `name`/storage identity、absolute path、request order 均不得参与；
- material descriptor、排序、字段仍使用当前 `name`、`sha256`、`size`、`source`，不改变任何 material skip/update 语义；
- 因而同 basename、同内容从另一目录重传时 fingerprint 相同，`auto` 保持 identical-skip；basename 改名即使内容相同也
  fingerprint 不同并 update/version increment；内容改变同样 update。

collision-free path identity、`original_filename`/`derived_from` storage schema 与上述 filing fingerprint 变更均不适用于
material。material duplicate path 仍走现有行为，本 work unit 只做回归测试，不新增或前移 material duplicate 处理。

### 6.7 Storage primary、publication atomicity 与 `process_filing`

不修改 storage public protocol或事务状态机：

1. `_build_pending_assets()` 对 filing 只定位 authoritative `selection.require_primary()` 对应的 original asset；只调用一次
   converter，生成一次 `conversion_started` 和一个 derived。
2. `_PreparedAssetMutation.primary_document` 直接接收该 derived identity，不从 pending list 或 stem 反推。
3. `_store_upload_assets()` 仍在 caller-owned batch 中先保存全部 assets，再用同一 `SourceDocumentUpsertRequest` 一次写入
   `file_entries` 与 exact `primary_document`。成功前无 published source 可见。
4. storage commit/snapshot 继续负责 names 唯一、physical set 双向一致、primary exact 命中；新增测试证明它看到的是
   identity 而非 original filename。
5. primary conversion/read 失败发生在 `begin_batch` 前；store/final source/commit 失败沿现有 rollback owner 回滚；失败结果
   `stored_file_count=0`，existing update 的旧 published tree 保持不变。
6. `process_filing` 和 Fins read runtime 生产代码不修改：测试必须通过 storage snapshot spy/真实 repository 证明二者调用
   `get_primary_source()` 后读取 explicit primary derived 内容，而 companions/originals 不会被 processor 消费。

## 7. End-to-end data flow 与不变量

```text
CLI --files + repeated --primary / LLM files + singular primary
  -> FinsUploadFilingRequest(files, primary_selectors)
  -> static owner: <=100 -> delete/files precedence -> normalize -> distinct -> cardinality -> membership -> role format
  -> ValidatedFinsUploadFilingRequest.file_selection
  -> Service/runtime mechanical handoff
  -> SEC/CN fresh validation of same raw request
  -> authoritative FinsUploadFilingFiles
  -> DoclingUploadService
       -> deterministic original identities + original_filename projections
       -> convert authoritative primary once
       -> derived identity from exact primary original identity
  -> one storage batch: blobs + files metadata + primary_document + company/source facts
  -> commit
  -> snapshot.get_primary_source()
  -> process_filing/read processor
```

必须保持：

1. primary 是显式 validated fact，不是顺序、名字或转换结果。
2. 100 是 inclusive 上限，且计数对象是 raw input entries；重复 path 不能借去重后数量绕过上限。
3. delete-with-files 在任何 path normalization 前以 `FILES_NOT_ALLOWED_FOR_DELETE` 拒绝；同时有 primary 时仍由 files error
   胜出，只有 delete files 为空时才可能返回 `PRIMARY_NOT_ALLOWED_FOR_DELETE`。
4. normalized duplicate 使用 resolve 后 case-sensitive exact path-string equality，在 workspace state read、observation/job、
   converter、batch 前拒绝；case alias/hardlink 不按 inode 合并。
5. filing basename 只用于 `original_filename`/fingerprint/用户事件/failure label，不用于 storage key；material 保持现状。
6. filing derived identity 只从 exact original identity 派生；`derived_from` 与 `primary_document` 同源。
7. filing companions 只有 original `file_uploaded`，没有 `conversion_started` 或 derived。
8. success：stored originals 守恒；failure/cancelled/skipped/deleted：existing count contract 不变。
9. source/company/blob 继续共享现有 filing batch；不创建新 transaction/facade。
10. storage/manifest/process 不重新选择 primary。
11. 不使用 `Any`、`object`、无类型签名、`hasattr/getattr`、extra payload、兼容 shim 或魔法 identity 字符串；namespace、prefix
    与 suffix 使用模块级 `Final` 常量。

## 8. Small implementation slices

### Slice 1：Raw/validated primary contract 与 owner admission

**Objective / expected outcome**

建立可保留 selector cardinality 的 raw request、显式 validated selection 与 workspace-read 前静态规则；不触碰入口 UI 或
asset storage。

**Allowed production files**

- `dayu/fins/ingestion_runtime.py`
- `dayu/fins/upload_format_contract.py`

**Allowed test files**

- `tests/fins/test_fins_ingestion_runtime.py`
- `tests/fins/test_fins_service_runtime.py`
- `tests/fins/test_upload_format_contract.py`

**Exact allowed changes**

1. 增加 `primary_selectors`、六个 usage codes/messages 与 exact case-sensitive path-string normalization/selection 私有 helper；
   固定消息直接加入现有 `_USAGE_MESSAGES` mapping。
2. 删除 `from_upsert_paths()`，增加 `for_upsert(primary=..., companions=...)`，迁移本 slice 内调用。
3. 按 §6.2 冻结顺序校验 delete/files/primary precedence、single/multi、100、duplicate、selector membership 和 role suffix。
4. validated selection 使用 normalized paths；raw request 保持原实例。
5. 更新中文模块/类/函数 docstring，明确参数、返回与异常。

**Tests / assertions**

- single 0/1 selector、multi primary 在首/中/末位置均得到同一明确角色；companions 保持相对顺序。
- multi 缺 selector、重复 selector、集合外 selector产生 exact closed code/message。
- delete + files 精确返回 `FILES_NOT_ALLOWED_FOR_DELETE`/`delete 不得提供 --files`，且 path resolve、duplicate、exists、role、
  workspace state read、Service factory/converter/batch 均不可达；delete 同时带 files+primary 仍返回该 files error。
- delete 仅带 primary 精确返回 `PRIMARY_NOT_ALLOWED_FOR_DELETE`/`delete 不得提供 --primary`；合法空 delete 保持成功。
- `path`、`./path`、`dir/../path` 与 symlink alias 的 normalized duplicate 在 state repository read 前失败；converter/batch 不可达。
- case-variant resolved strings 不判 duplicate，大小写不同 selector 不按 inode membership 命中；hardlink 的两个不同 resolved
  path strings 同样视为不同输入。测试只断言 path-string contract，不依赖宿主文件系统是否大小写敏感。
- 两个不同目录的同 basename 不被误判 duplicate；同 stem 不同 suffix 不被误判。
- 100 个不同文件接受，101 拒绝；先计 raw entries，再判 duplicate。
- primary-only suffix 和 companion-only `.xsd` 由 explicit role 判定，不由 index 判定。
- `FinsUploadFilingFiles` 无任何顺序推断 constructor；delete empty contract 保持。

**Validation**

```bash
source .venv/bin/activate
python -m pytest tests/fins/test_upload_format_contract.py tests/fins/test_fins_ingestion_runtime.py \
  tests/fins/test_fins_service_runtime.py -q
python -m pyright dayu/fins/ingestion_runtime.py dayu/fins/upload_format_contract.py \
  tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_service_runtime.py \
  tests/fins/test_upload_format_contract.py
```

**Non-goals / stop condition**

- 不改 CLI/tool/Service/storage。
- 若 normalized-path definition 不能由现有 `Path` contract 无歧义实现，或需要改变“不同 path”业务定义，停止并交主控裁决。

### Slice 2：CLI 与 LLM-facing primary 投影

**Prerequisite**

Slice 1 accepted；raw request 与 usage failure contract 已固定。

**Objective / expected outcome**

CLI 与 LLM tool 都能机械构造同一 raw selector fact；重复 CLI selector 不被吞掉；schema 自足表达 100 与条件 primary。

**Allowed production files**

- `dayu/cli/arg_parsing.py`
- `dayu/cli/commands/fins.py`
- `dayu/fins/tools/upload_tools.py`
- `dayu/fins/upload_format_contract.py`

**Allowed test files**

- `tests/cli/test_arg_parsing.py`
- `tests/cli/test_fins_commands.py`
- `tests/fins/test_fins_ingestion_tools.py`

**Exact allowed changes**

1. 注册 append 型 `--primary`，扩展 `ParsedCliArgs`，在 prevalidation request 构造时保留所有 occurrence。
2. 修改 `FinsUploadFormatTextProjection`：移除“首文件 primary”，显式增加 `filing_primary` 与
   `upload_tool_primary`；两字段由同一关键规则片段产生。
3. CLI `--primary` help 只读取 `FINS_UPLOAD_FORMAT_TEXT.filing_primary`；tool schema `primary.description` 只读取
   `FINS_UPLOAD_FORMAT_TEXT.upload_tool_primary`，并增加 `files.maxItems=100`；tool parser 只投影 0/1 selector，material
   primary fail closed。
4. 既有 CLI/tool error mapping、observation activation 与 Service factory 顺序不变。

**Tests / assertions**

- `FinsUploadFormatTextProjection` 两个新增字段精确断言；parser help 的 `--primary` description 等于/包含
  `filing_primary`，tool schema `primary.description` 精确等于 `upload_tool_primary`，且二者逐字包含同源的单文件省略、
  多文件恰好一个、membership、顺序非角色、delete 禁止规则，不再出现“首文件是主文件”。
- CLI multi primary 可位于 `--files` 非首位置并原样进入 validated request。
- `--primary a --primary b`、multi 缺 primary、集合外 primary、duplicate files 都 exit 2；stderr 一行 bounded reason；
  Service factory/stream/converter/workspace mutation 为零。
- 单文件与 `upload_filings_from` 生成脚本无需 `--primary` 并继续可执行。
- tool schema 的 `primary` 类型/说明与 `files.maxItems=100` 精确断言；filing valid multi 能启动 observation，invalid selector 在
  observation registration/activation 前返回 failed outcome；material/delete primary 被拒绝。
- tool 文案不暴露 Python 类型、Host/Engine 内部术语或 opaque asset identity。

**Validation**

```bash
source .venv/bin/activate
python -m pytest tests/cli/test_arg_parsing.py tests/cli/test_fins_commands.py \
  tests/fins/test_fins_ingestion_tools.py -q
python -m pyright dayu/cli/arg_parsing.py dayu/cli/commands/fins.py \
  dayu/fins/tools/upload_tools.py dayu/fins/upload_format_contract.py \
  tests/cli/test_arg_parsing.py tests/cli/test_fins_commands.py tests/fins/test_fins_ingestion_tools.py
```

**Non-goals / stop condition**

- 不在 argparse/tool adapter 复制 membership 或 role validator。
- 若 ToolParametersSchema 无法表达 `maxItems` 或新增 field 需要修改 Engine/Host schema contract，停止；不得通过裸 mapping 绕过。

### Slice 3：Deterministic asset identity、storage primary 与 process consumption

**Prerequisite**

Slices 1–2 accepted；Service 收到的 filing selection 已具 authoritative primary。

**Objective / expected outcome**

只为 filing 消除 basename/stem storage collision，保留 original filename 业务投影与既有 fingerprint 业务语义，并证明
derived/storage/process/atomicity 同源；material 全链保持现状。

**Allowed production files**

- `dayu/fins/pipelines/docling_upload_service.py`

**Allowed test files**

- `tests/fins/test_docling_upload_service.py`
- `tests/fins/test_docling_upload_service_integration.py`
- `tests/fins/test_fins_ingestion_runtime.py`
- `tests/fins/test_sec_pipeline_upload_filing_stream.py`
- `tests/fins/test_sec_pipeline_upload_material_stream.py`
- `tests/fins/test_cn_pipeline.py`
- `tests/fins/test_fins_storage_atomicity.py`
- `tests/fins/test_processor_read_consistency.py`

**Exact allowed changes**

1. 实现 §6.6 filing-only identity helpers/constants，并给 `_PendingFileAsset` 的 `original_filename`/`derived_from` 增加显式 typed
   字段；material 构造点必须显式填 `None`。
2. `_build_original_assets()` 按 §6.6 table：filing `name` 使用 normalized path identity、`original_filename` 使用 basename；
   material 的 name/metadata/failure path 不变。
3. `_build_pending_assets()` 按 §6.6 table：filing derived 接收 exact original identity并继承 original filename，converter 精确绑定
   authoritative primary original；material derived name、逐项转换与首 derived primary 不变。
4. `_store_upload_assets()`/`_build_stored_file_entry()` 按 §6.6 table：filing blob key、`files[].name`、URI、
   `primary_document` 使用 identity并投影条件 metadata，filing `file_uploaded.name` 使用 original filename；material event、metadata、
   asset names 全部保持现状。
5. filing source fingerprint 由 `original_filename`、`sha256`、`size`、`source` 形成，明确排除 path-derived storage identity；
   material fingerprint 公式不变。requested/stored count 与 failure projection 不变。
6. 不修改 storage/process 生产代码；只通过真实 repository/snapshot/processor tests 固定 existing contract。

**Tests / assertions**

- 不同目录同 basename：两个 original identities、physical files、meta entries 均不同；两条 `original_filename` 相同且可读。
- 同 stem 不同 suffix：identities 不同；filing explicit primary 非首项时只转换它，companion 无 derived/conversion_started。
- 同 normalized path 不到 Service；defensive generated identity duplicate 在 converter/batch 前 fail closed。
- original identity 对相同 normalized path 稳定、对 request order 不敏感、没有绝对路径明文；derived exact 等于
  `<primary-original-identity>_docling.json`，metadata `derived_from` 精确回指。
- `_build_original_assets()` 精确断言 filing original 三字段，`_build_pending_assets()` 精确断言 filing derived 三字段及
  `conversion_started.name=original_filename`，`_store_upload_assets()` 精确断言 filing entry/event 映射；original entry 不含
  `derived_from`，derived entry含 exact 回指。
- 同 basename、同 sha256/size/source 的相同内容换到不同目录：storage identity 改变但 source fingerprint 不变，`auto` 为
  identical-skip、document version 不增长；仅 basename 改名且内容相同：fingerprint 改变并 update/version increment；内容改变
  同样 update。
- source `files` 恰有 N originals + filing 1 derived；`primary_document` 精确等于 primary derived 且命中一次；
  `stored_file_count=N`。
- 100 个小型 distinct inputs 完整发布 100 originals + 1 derived；converter 仅一次。
- primary conversion failure：converter call 仅 primary、batch begin=0、stored=0、company/source/blob 零发布。
- 第 N 次 blob store/final source/commit failure：rollback exactly once；fresh target 零发布，existing update 的 tree SHA 不变。
- snapshot `get_primary_source()` 读取 derived bytes；`process_filing` registry spy 只收到该 source，不读取 chosen companion/original；
  read runtime 同样消费 exact primary。
- material 回归精确断言：original asset name 仍是 basename、derived name 仍是 `<stem>_docling.json`、storage `files` 不含
  `original_filename`/`derived_from`、file event/fingerprint/failure path 不变、仍逐个转换且首 derived 为 primary；对代表性
  success/conversion failure path 做回归，但不为 material duplicate path 新增 admission code、前移校验或其它处理。
- optional real Docling integration 只更新 identity 断言；默认仍按现有 env gate skip，不将其冒充 mandatory evidence。

**Validation**

```bash
source .venv/bin/activate
python -m pytest tests/fins/test_docling_upload_service.py \
  tests/fins/test_docling_upload_service_integration.py \
  tests/fins/test_fins_ingestion_runtime.py \
  tests/fins/test_sec_pipeline_upload_filing_stream.py \
  tests/fins/test_sec_pipeline_upload_material_stream.py \
  tests/fins/test_cn_pipeline.py \
  tests/fins/test_fins_storage_atomicity.py \
  tests/fins/test_processor_read_consistency.py -q
python -m pyright dayu/fins/pipelines/docling_upload_service.py \
  tests/fins/test_docling_upload_service.py \
  tests/fins/test_docling_upload_service_integration.py \
  tests/fins/test_fins_ingestion_runtime.py \
  tests/fins/test_sec_pipeline_upload_filing_stream.py \
  tests/fins/test_sec_pipeline_upload_material_stream.py \
  tests/fins/test_cn_pipeline.py tests/fins/test_fins_storage_atomicity.py \
  tests/fins/test_processor_read_consistency.py
```

**Non-goals / stop condition**

- 不修改 storage/process 以接受错误 identity，不做旧 basename filename 兼容读取。
- 若 processor contract 依赖具体 basename 而不是 `_docling.json` suffix/primary source，先停止并回报 semantic owner drift；
  不在 processor 加 fallback。
- 若 filing-only 分支无法在不改变 material name/metadata/fingerprint/event/failure 的情况下实现，停止并交主控；不得把
  filing schema 扩到 material，也不得新建 material duplicate 兼容逻辑。

### Slice 4：README、全量验证与 gate closeout evidence

**Prerequisite**

Slices 1–3 accepted，生产/测试行为已稳定。

**Objective / expected outcome**

只同步已实现用户/开发者/测试事实，完成全量 affected validation；不运行冻结真实场景。

**Allowed documentation files**

- `README.md`
- `dayu/fins/README.md`
- `tests/README.md`

**Allowed artifact file**

- 后续 gate 按 Gateflow 命名创建的当前 slice implementation/review artifact；不得修改本计划、goal、oracle/scenario/evidence。

**Exact allowed changes**

1. 根 README：用户命令示例/help 说明增加 `--primary`；明确单文件可省、多文件必填一次、duplicate/集合外/100 上限、
   delete 禁止 files/primary、companions 与 atomic failure。不得写内部 digest/schema。
2. Fins README：更新 raw/validated owner、explicit selection、asset identity vs original filename、derived association、storage primary 与
   process path；明确 filing fingerprint 排除 path-derived identity，因此同 basename/同内容换目录仍 identical-skip、改名仍
   update；明确 material storage/fingerprint/event/failure 不变；删除“首项 primary”旧事实。
3. tests README：更新当前测试覆盖面与 focused command；不写未执行 UF-PF07/UF-PF12 已通过。

**Validation**

```bash
source .venv/bin/activate
python -m pytest tests/fins/test_upload_format_contract.py \
  tests/fins/test_fins_ingestion_runtime.py \
  tests/fins/test_fins_service_runtime.py \
  tests/cli/test_arg_parsing.py tests/cli/test_fins_commands.py \
  tests/fins/test_fins_ingestion_tools.py \
  tests/fins/test_docling_upload_service.py \
  tests/fins/test_docling_upload_service_integration.py \
  tests/fins/test_sec_pipeline_upload_filing_stream.py \
  tests/fins/test_sec_pipeline_upload_material_stream.py \
  tests/fins/test_cn_pipeline.py \
  tests/fins/test_fins_storage_atomicity.py \
  tests/fins/test_processor_read_consistency.py -q
python -m pyright dayu/ tests/ utils/
git diff --check
```

每个修改生产文件还必须单独检查 coverage，不用 aggregate 百分比掩盖低覆盖文件：

```bash
source .venv/bin/activate
python -m coverage erase
python -m coverage run --branch -m pytest <上述 affected tests>
python -m coverage report --include='dayu/fins/ingestion_runtime.py' --fail-under=80
python -m coverage report --include='dayu/fins/upload_format_contract.py' --fail-under=80
python -m coverage report --include='dayu/cli/arg_parsing.py' --fail-under=80
python -m coverage report --include='dayu/cli/commands/fins.py' --fail-under=80
python -m coverage report --include='dayu/fins/tools/upload_tools.py' --fail-under=80
python -m coverage report --include='dayu/fins/pipelines/docling_upload_service.py' --fail-under=80
```

该 80% gate 当前没有实测失败证据，不预先豁免、降级或改成基线比较；若实际运行失败，按下方 stop condition 留在当前 gate
修复或分类并交主控，不得为了通过而扩展到无关生产范围。

**Stop condition**

- 任一测试/pyright/coverage failure 必须留在当前 gate 修复或分类；不得带未分类失败关闭 slice。
- README 若需要描述未实现/未验证行为，停止，不预写未来能力。
- 禁止执行 UF-PF07、UF-PF12；若主控要求真实 evidence，必须作为新授权入口处理。

## 9. Overall allowed files

除 Gateflow 后续 review/implementation artifacts 外，实现不得越出以下集合；需要新增文件或修改其它文件时必须停止并先走 plan
amendment/review：

**Production**

- `dayu/fins/ingestion_runtime.py`
- `dayu/fins/upload_format_contract.py`
- `dayu/cli/arg_parsing.py`
- `dayu/cli/commands/fins.py`
- `dayu/fins/tools/upload_tools.py`
- `dayu/fins/pipelines/docling_upload_service.py`

**Tests**

- `tests/fins/test_fins_ingestion_runtime.py`
- `tests/fins/test_fins_service_runtime.py`
- `tests/fins/test_upload_format_contract.py`
- `tests/cli/test_arg_parsing.py`
- `tests/cli/test_fins_commands.py`
- `tests/fins/test_fins_ingestion_tools.py`
- `tests/fins/test_docling_upload_service.py`
- `tests/fins/test_docling_upload_service_integration.py`
- `tests/fins/test_sec_pipeline_upload_filing_stream.py`
- `tests/fins/test_sec_pipeline_upload_material_stream.py`
- `tests/fins/test_cn_pipeline.py`
- `tests/fins/test_fins_storage_atomicity.py`
- `tests/fins/test_processor_read_consistency.py`

**README**

- `README.md`
- `dayu/fins/README.md`
- `tests/README.md`

明确不改 `dayu/service`、`dayu/host`、`dayu/engine`、`dayu/runtime`、storage/processor 生产代码、
`upload_filings_from` renderer、oracle/scenario/evidence。

## 10. 为什么没有过度设计

- 只在现有 Fins request、selection 与 upload preparation 三个 owner boundary 增加必要事实；不建立全局 asset registry 或新层。
- selector tuple 仅为保留 CLI 重复 occurrence 的最小 raw contract；validated primary 仍只有一份 typed selection，不形成双真源。
- identity 使用单个私有 deterministic helper 和现有 storage filename，不增加数据库表、UUID 服务、manifest sidecar 或迁移框架。
- storage transaction、snapshot 与 `process_filing` 已满足 exact primary/atomic consumption，只补 owner-level tests，不改正确下游。
- shared upload service 只在 filing 分支应用 collision-free identity 与新 metadata；material 明确保留现状，避免把 filing 修复
  扩成未经确认的 material schema 变更。
- 不自动发现 primary、不做内容嗅探、不引入未来 provider/source kind abstraction；范围精确覆盖 accepted goal。

## 11. Stop conditions

出现以下任一情况，当前执行 agent 必须停止并回报 AgentController，不得自行扩 scope：

1. re-review 认为 `primary_selectors`、normalized-path 定义、identity namespace/shape、metadata 字段或 owner boundary 仍需改变。
2. 实现发现正确语义 owner 不在本计划指定边界，或需要 Host/Engine/runtime/storage/processor 生产代码才能成立。
3. 现有 dirty changes 与本 work unit allowed files 重叠且 ownership 不清，无法安全 review/commit。
4. 需要修改 overall allowed files、oracle/scenario/frozen evidence、执行 UF-PF07/UF-PF12、创建外部 issue/PR 或对外 comment。
5. validation failure、coverage 缺口、pyright 错误、unclassified residual risk 或 missing artifact 无法在当前 approved slice 内解决。
6. filing path-derived identity 被证明泄漏本地绝对路径、超过 storage filename boundary、不能稳定 round-trip，或与 existing
   `_docling.json` processor contract 冲突；或实现必须让该 identity 进入 fingerprint 才能成立。
7. 100-file deterministic test 暴露资源上限/事务能力需要产品决策，而非普通测试修复。
8. 实测任一修改生产文件 coverage 低于 80%；先在 current scope 内补 owner-level tests，仍无法满足时停止并交主控，不得
   预先豁免、降低门槛或扩展无关生产范围。

## 12. Residual risks / uncovered areas

| 风险或未覆盖项 | 分类 | owner / destination |
| --- | --- | --- |
| existing source 旧 basename-based schema（含旧 `name`-key source fingerprint）的兼容、首次重传或自动修复 | assigned to later work unit | `UF-FIX08`；本 work unit 按 fresh schema，不兼容读取，也不向当前 README/生产 contract 承诺迁移或首次重传行为 |
| 同 request/同 document 并发 writer 竞争 | assigned to later work unit | `UF-FIX10` |
| fresh company meta warning | assigned to later work unit | `UF-FIX11` |
| 冻结 UF-F11–F13、UF-D04–D06、UF-C05–C06、UFS-006 argv 尚无 `--primary`，记录的是修复前观察 | assigned to later work unit | 后续 registry/evidence work unit；本轮禁止修改或重跑 |
| frozen `UF-A14-delete-with-files-ignored` observation 因新增 `FILES_NOT_ALLOWED_FOR_DELETE` contract 已 stale | assigned to later work unit | 后续获授权 registry/evidence work unit 必须把 `UF-FIX07` 加入 `UF-PF03.blocked_by_finding_ids` 并更新相应 observation/evidence；当前严禁修改 registry、oracle 或 frozen evidence |
| UF-PF07 与 UF-PF12 真实 evidence 未执行 | assigned to later work unit | 后续获授权 evidence gate |
| SHA-256 理论碰撞 | fixed in current slice | 使用完整 digest并对本 request generated identities 做唯一性 fail-closed 检查 |
| filing 同一 basename/同内容从不同 normalized path 上传产生不同 storage identity | fixed in current slice | identity 隔离 collision；fingerprint 排除 identity，因此保持 identical-skip |
| filing 改 basename 但内容相同 | fixed in current slice | `original_filename` 属于 fingerprint，明确触发 update/version increment并由测试/README 固定 |
| case alias/hardlink 的不同 resolved path string 被视为两个输入 | accepted boundary | equality 是 resolve 后 case-sensitive exact string；不按 inode 或平台 case folding 合并，未来若改变需独立跨平台设计 |
| material 的 basename/stem collision 与 duplicate-path 行为保持现状 | assigned to later work unit | 本 work unit按主控裁决只修 filing；仅加 material non-regression tests，不新增 material duplicate 处理 |
| optional real Docling integration 默认可能 skip | covered by later approved slice | Slice 3 deterministic fake-converter owner tests为 correctness gate；真实 mandatory evidence 后续另行授权 |

所有当前 residual risk 已分类；无 blocking open question。

## 13. Completion report format

每个 implementation slice 完成报告必须包含：

1. gate/work unit/slice id 与 artifact path；
2. 实际 changed files，逐项确认未越 allowed files；
3. owner/contract/state/data-flow 实现决策，特别是 raw selector、validated selection、asset identity、derived association、
   storage primary 与 process consumption；
4. 测试命令、exit code、关键 assertions；
5. pyright 与单文件 coverage 结果；
6. README decision/更新；
7. findings 状态与 residual risks 分类；
8. 明确声明未修改 oracle/scenario/frozen evidence，未执行 UF-PF07/UF-PF12，未创建/推进 PR；
9. completion status 与 Gate Order 中下一个未完成 entry point。

## 14. Plan gate completion

- Artifact：`docs/gateflow/uf-fix07-multi-file-primary-collision-plan-20260815.md`
- Decision：`PLAN ACCEPTED / ACCEPTED PLAN COMMIT PENDING`
- Validation：只读核对 AGENTS、两份 design_doc、confirmed goal、两路 plan review、两路 re-review、oracle/scenario 引用、
  相关生产代码与测试；所有 finding 均有 Gateflow 闭集最终状态，artifact whitespace check 无输出；本 gate 未执行
  implementation tests、pyright、coverage 或禁止的真实场景，因为未修改生产代码/测试。
- Changed files：仅修订本 plan 与 plan-fix artifacts，并新增 plan re-review adjudication；未修改生产代码、测试或 README。
- Docs decision：README 更新已被纳入 Slice 4；本 gate 未修改 README。
- Residual risks：均已在 §12 分类，无 unclassified risk。
- Next entry point：AgentController 执行 `accepted plan commit`；本 agent 未 commit，并停止等待主控。
