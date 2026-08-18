# UF-FIX07 multi-file-primary-and-collision：Goal Confirmation

## Gate

- work unit：`UF-FIX07 multi-file-primary-and-collision`
- gate：`goal confirmation`
- design inputs：`docs/host/design.md`、`docs/engine/design.md`
- oracle input：`docs/cli_ci_oracles.json` 的 `upload_filing.multi-file-and-primary`
- scenario input：`docs/cli_ci_scenarios.json` 的 `UF-FIX07`
- frozen evidence inputs：`UF-F11`–`UF-F13`、`UF-D04`–`UF-D06`、`UF-C05`–`UF-C06`、`UFS-006`
- completion status：`confirmed`
- artifact path：`docs/gateflow/uf-fix07-multi-file-primary-collision-goal-confirmation-20260815.md`

## Preflight

- 当前分支：`codex/upload-filing-oracle`，不是 protected trunk。
- 工作树：preflight 时干净。
- merge / rebase：均未进行。
- 本地 `main` 与抓取后的 `github/main`：同为 `256786b255021ee429a20f22aad726b1ad33916c`，`main...github/main = 0/0`，无需 fast-forward mutation。
- 当前分支：以 `main` 为祖先且单向领先 50 个提交，`main...HEAD = 0/50`。
- 当前分支未配置 upstream；本 work unit 只要求本地提交，不要求 push 或 PR，因此不构成 blocker。

## 第一性原理判断

问题成立，且三个表现是同一个契约缺失的直接后果，不应分别在 CLI、converter 或 storage 下游打补丁：

1. 一个 filing 的 downstream 处理只能有一个 primary；如果 request 没有把该事实表达为显式字段，任何“取第一项”的实现都只能依赖偶然顺序。
2. 用户输入路径、用户可读文件名与仓储资产 identity 是不同事实。basename / stem 只能作为展示投影，不能承担同一 filing 内的唯一标识。
3. Docling 派生资产属于明确 primary original 的派生物；其 identity 必须从同一 primary asset fact 派生，不能再次从 stem 或发布后目录反推。
4. 静态可判定的重复路径、primary 数量和集合关系必须在 converter、workspace 业务 mutation 与 publication 前由请求 owner 一次拒绝。

因此应建立一条严格类型化链路：raw request 携带用户声明的 primary selector；Fins 静态准入 owner 规范化并验证不同输入路径、单/多文件 primary 规则和 100 文件上限，产出唯一 authoritative filing selection；workflow 与 Service 原样传递该 selection；上传资产准备 owner 为每个 original 产生稳定无碰撞 identity，并只为 selection 的 primary 产生与其关联的 derived identity；storage publication 持久化这些 identity、角色和用户可读原始文件名；`process_filing` 继续只消费 storage 已发布的唯一 primary derived asset。

## 语义 Owner 判定

| 语义 | 唯一 owner | 其它层职责 |
| --- | --- | --- |
| multi-file request、不同路径集合、100 文件上限、primary selector 数量及集合关系 | `dayu.fins.ingestion_runtime` 的 filing upload raw/validated request 与静态 validator boundary | CLI 与 LLM tool 只构造 raw typed request；Service/workflow 不重验、不猜测 |
| validated primary / companions 角色 | `dayu.fins.upload_format_contract.FinsUploadFilingFiles` 这一 authoritative typed selection | workflow 与 `DoclingUploadService` 只消费 selection；不得按顺序重建角色 |
| original asset identity 与用户可读原始文件名投影 | `DoclingUploadService` 的 typed asset preparation boundary | storage 只校验并原子持久化 caller 给出的 exact identity/metadata；CLI/下游不从 basename 猜 identity |
| derived asset identity 及其 primary-original 关联 | 同一个 typed asset preparation boundary，从 authoritative primary original identity 单向派生 | converter 只返回内容；storage 持久化 exact derived identity；downstream 读取已发布 primary，不按 stem/目录扫描反推 |
| 已发布 primary pointer 与完整 files 集合的一致性 | `dayu.fins.storage` source publication contract | `process_filing`/read runtime 只调用 snapshot 的 `get_primary_source()`，不自行选择文件 |

这里不新增通用资产注册中心。asset identity 只服务当前 upload preparation/publication，保持在 Fins 上传边界内；用户可读 basename 是独立 metadata 投影，不充当 key。

## 直接代码与数据证据

- `dayu/fins/upload_format_contract.py::FinsUploadFilingFiles.from_upsert_paths` 当前固定 `primary=paths[0]`、`companions=paths[1:]`，直接证明 primary 依赖输入顺序。
- `dayu/fins/ingestion_runtime.py::_validate_fins_upload_filing_static` 按 `enumerate(request.files)` 把 index 0 当 primary，未拒绝重复规范路径，也没有显式 primary 字段；随后再次调用 `from_upsert_paths(request.files)` 固化同一偶然顺序。
- `dayu/cli/arg_parsing.py::_register_upload_filing_command` 只有 `--files`，没有 primary 参数；共享 help 仍宣称“首文件是主文件”。
- `dayu/fins/tools/upload_tools.py` 的 LLM-facing schema 只有 `files`，构造 `FinsUploadFilingRequest` 时同样没有 primary 字段。
- `dayu/fins/pipelines/docling_upload_service.py::_build_original_assets` 把 `file_path.name` 直接作为 original asset `name`；不同目录下同 basename 会得到相同仓储 identity。
- 同模块 `_build_pending_assets` 用 `f"{file_path.stem}_docling.json"` 生成 derived asset identity，并以首个转换结果设置 `primary_document`；相同 stem 的不同文件会碰撞。
- 同模块 `_store_upload_assets` 以 `asset.name` 调用 blob repository 并把它写入 source `files[]`，因此上述碰撞进入 publication boundary，而不是只影响展示。
- `dayu/fins/ingestion_runtime.py::_preprocess_one_document` 与 `dayu/fins/tools/read_runtime.py::_create_processor_from_snapshot` 都调用 `snapshot.get_primary_source()`；storage snapshot 又从 published `primary_document` 精确解析唯一文件。这证明 downstream 实际只消费已发布 primary，而不是全部 originals。
- accepted oracle 明确要求最多 100 个不同输入、重复路径转换前 exit 2、无 basename/stem collision、显式稳定 primary，禁止顺序推断。
- scenario registry 把 `UF-F11`–`UF-F13`、`UF-D04`–`UF-D06`、`UF-C05`–`UF-C06` 与 `UFS-006` 记录为本问题的直接 evidence；本轮只读取，不修改这些冻结事实。

## 目标与成功信号

1. 单文件 upsert 以唯一文件作为 primary；多文件 upsert 必须由用户显式指定且只能指定一个属于 `--files` / tool `files` 集合的 primary。
2. 重复规范输入路径、缺失 multi-file primary、primary 不属于 files、多个 CLI primary selector、超过 100 个文件及其它静态组合错误，在 converter、workspace 业务 mutation 与 publication 前以明确 usage failure 拒绝。
3. CLI、LLM-facing tool schema、Service、fresh workflow validation、manifest/storage publication 与 downstream process 使用同一 authoritative primary fact；不存在顺序、basename、stem、目录扫描或生成结果反推。
4. 每个不同输入获得稳定、无碰撞的 original asset identity；不同路径同 basename、同 stem 不同后缀可完整共存；files metadata 同时保留用户可理解的原始文件名。
5. 只有 explicit primary 产生 Docling derived asset 与 `conversion_started`；companions 只按 UF-FIX06 capability 原样保存，不被标记为 converted/processed。
6. primary derived identity 从同一 primary original asset identity 派生，storage `primary_document` 精确指向它；`process_filing` 通过 snapshot 消费该 exact published primary。
7. primary 转换失败或整批 publication 失败时零部分发布，`stored_file_count=0`；成功时 requested/stored originals 守恒，Docling asset 不计入 stored originals。
8. 100 个不同文件仍被接受；受影响 tests、单文件覆盖率目标与 pyright 通过，并按职责更新 README。

## 非目标与 Scope Boundary

- 不处理 UF-FIX08 existing-source auto repair、UF-FIX10 concurrency、UF-FIX11 company meta warning 或其它 finding。
- 不执行 UF-PF07、UF-PF12 真实 CLI evidence。
- 不修改 `docs/cli_ci_oracles.json`、`docs/cli_ci_scenarios.json` 或冻结 evidence。
- 不引入通用资产注册中心、内容嗅探 primary、MIME fallback、兼容 shim、loose parsing 或旧 schema 兼容读取。
- 不改变已完成的 action/update identity、原子 publication、typed bounded failure、requested/stored summary、calendar/year、ticker alias、UF-FIX06 converter capability 与 primary/companion 分离。
- 不修改 Host / Engine lifecycle、EventLog、memory、trace 或调度语义。
- `upload_filings_from` 当前每个 filing entry 只生成一个 `--files` 输入；它继续由单文件规则自然取得 primary，不在本 work unit 设计附件自动归组。

## Design Document Alignment

- `docs/engine/design.md` 明确 Engine 不理解财报业务语义、不直接访问财报 storage，只消费 tool schema 与 outcome；因此 primary/asset identity 不进入 Engine contract。
- `docs/host/design.md` 把 Host 限定为生命周期、治理、事件与 ToolRuntime owner；direct Fins upload 不应被改造成 Host Run，也不由 Host 推断文件角色。
- 真实修改边界应落在 Fins raw/validated request、Fins role contract、Fins upload preparation/publication、CLI/LLM schema 的机械投影与 owner-level tests。

## 本轮不做的过度设计

- 不建立跨 filing、跨 provider 或跨 source kind 的全局 asset catalog。
- 不使用数据库序列、随机 UUID 或输入顺序编号来掩盖碰撞；identity 由当前 request 中已验证的 path/asset fact 确定性产生。
- 不让 storage、manifest reader 或 processor 扫描文件集合后“选最像正文”的文件。
- 不为 companions 生成空 Docling 占位、不增加兼容别名，也不保留“首文件默认为 primary”的多文件兼容行为。

## Blocking Open Questions

无。用户已经明确裁定多文件必须显式 primary、单文件唯一 primary、100 文件边界、fresh schema、禁止兼容和冻结 evidence 边界；owner 与成功信号可由现有 typed request/selection/storage contract承载。

## Residual Risks / Uncovered Areas

| 风险或未覆盖项 | 分类 | owner / destination |
| --- | --- | --- |
| existing source 缺失/损坏后的 auto repair | assigned to later work unit | `UF-FIX08` |
| 同 request / 同 document 并发竞争 | assigned to later work unit | `UF-FIX10` |
| fresh company meta warning | assigned to later work unit | `UF-FIX11` |
| UF-PF07 与 full-real mandatory matrix | assigned to later work unit | 后续 evidence work unit；本轮禁止执行 |
| registry 与冻结 evidence 仍描述修复前观察 | assigned to later work unit | 后续 registry/evidence work unit；本轮禁止修改 |

## Next Entry Point

进入 `plan`：先由 AgentCodex 产出 code-generation-ready plan，再由 AgentMiMo 与 AgentDS 并行执行两路 plan review。
