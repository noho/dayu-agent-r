# upload_filing ticker alias contract 收敛 goal confirmation

## Gate

- Gate: `goal confirmation`
- Work unit: `upload-filing-ticker-alias-contract`
- Completion status: `pass`
- Current gate / next entry point: `plan`
- Artifact path: `docs/reviews/wu-upload-filing-ticker-alias-contract-goal-confirmation-controller.md`

## Preflight

- Branch: `codex/upload-filing-oracle`，不是 protected trunk。
- Workspace: clean。
- Merge state: 不存在 `MERGE_HEAD`、`REBASE_HEAD` 或 `CHERRY_PICK_HEAD`。
- Remote refresh: 已成功执行 `git fetch github main`。
- Main fast-forward state: `main == github/main == 256786b2`；当前分支包含 `github/main`，相对它 ahead 38、behind 0。
- Scope ownership: 当前工作树没有未归属修改；本 work unit 只处理 ticker alias contract 漂移和必要 Gateflow artifact。
- Agent panes: `AgentMiMo=ai-0:1.1`、`AgentCodex=ai-0:1.4`、`AgentDS=ai-0:1.5`，均已唯一定位；尚未在 goal confirmation 前派发 plan/implementation/review。

## First-principles judgment

问题真实存在，且严重性评估成立。它不是 `list_documents` 的单点漏查，也不是 CLI 的单点 CSV 解析错误；根因是“同一公司可接受哪些 ticker alias、如何归一化和去重、何时成为 durable identity、冲突何时拒绝”没有唯一 contract owner，导致多个入口和持久化/查询路径各自维护不一致规则。

用户给出的总体修复方向正确，但 owner 需要拆清两个不可混淆的职责：

- Fins Company Identity / CompanyMeta domain contract 唯一拥有 alias grammar、canonicalization、稳定去重以及 canonical 与 accepted aliases 的结构化关系。
- `dayu.fins.storage` 唯一拥有 workspace durable alias uniqueness、原子发布和 alias 到 canonical corpus 的查询路由。

CLI、upload tool、resolver、pipeline 和 read runtime 都只能构造或消费上述 contract，不能继续各自解析、归一化、猜测或 fallback。Host/Engine 不应成为修复位置。

## Direct code and data-flow evidence

### 1. Grammar 与归一化存在互相矛盾的 producer

- `dayu/fins/ticker_normalization.py::normalize_ticker` 是 US/CN/HK 语法变体 owner，但当前 US grammar 不接受 resolver 实际产生的 `V.BA`。
- 直接运行结果为 `try_normalize_ticker("V.BA") is None`。
- `dayu/fins/resolver/fmp_company_info.py::_normalize_ticker_token` 在 normalizer 失败时回退到去空白大写文本；现有 owner-level 测试确认 resolver 会返回 `("V", "V.BA")`。
- `dayu/fins/ingestion_runtime.py::_validate_fins_upload_filing_static` 又要求每个 alias 必须通过 `normalize_ticker`，因此 resolver 的合法 public output 无法被 upload consumer 端到端接收。

这构成同一数据流上的直接 contract 断裂：resolver accepted output `V.BA` -> CLI merge -> upload request -> static validator rejection。

### 2. CLI、pipeline 与 storage 各自重复归一化/去重

- `dayu/cli/commands/fins.py::_parse_ticker_csv` 自行拆 CSV、逐项调用 `normalize_ticker`，再由 `_merge_ticker_aliases` 自行排除 canonical 和稳定去重。
- 当前直接结果：`DELTA,MSFT` 被解析为 `canonical=DELTA, aliases=(MSFT,)`；`AAPL,AAPL,US.AAPL` 被解析为 `canonical=AAPL, aliases=()`。
- `dayu/fins/pipelines/upload_company_meta.py::_normalize_ticker_aliases` 再实现一套严格归一化/去重。
- `dayu/fins/pipelines/sec_company_meta.py` 在 normalizer 失败时回退大写，并分别实现 normalize / extract / merge 三套 alias helper。
- `dayu/fins/pipelines/cn_download_company_meta.py::_merge_aliases` 只做 `strip` 和 exact-string 去重，不消费 ticker normalizer。
- `dayu/fins/storage/_fs_storage_utils.py::_canonicalize_ticker_alias` 再次实现 normalizer + `strip().upper()` loose fallback，`_normalize_company_ticker_aliases` 再次去重。

因此 canonicalization、长度边界、canonical-equivalent 判定和 accepted grammar 会随入口变化，当前不存在唯一 Company Identity source of truth。

### 3. 显式 alias 会在 fresh CompanyMeta 路径静默丢失

- `dayu/fins/pipelines/upload_company_meta.py::resolve_upload_company_meta_decision` 只要既有 `CompanyMeta.resolver_version` 为当前版本，就返回 `disposition="keep", company_meta=None`，完全不比较或合并本次用户明确声明的 aliases。
- 直接构造已有 `AAPL` meta 后，以 update 请求新增 `MSFT` alias，结果为 `UploadCompanyMetaDecision(disposition='keep', company_meta=None)`。
- 现有测试还将“fresh meta 保留旧 aliases、忽略新 aliases”固化为预期；该测试应迁移到正确 owner contract，不能倒逼生产代码保留语义丢失。

这直接违反用户声明 alias 必须可靠持久化并可查询的业务 contract。

### 4. 冲突映射当前在持久化后、查询时才发现

- `dayu/fins/storage/_fs_company_meta_core.py::_upsert_company_meta_impl` 只规范化并写入当前 ticker staging 的 `meta.json`，不检查 workspace 中其它 canonical corpus 已占用的 alias。
- `commit_batch` 当前只持有 ticker-scoped publication guard，并直接执行 backup/swap/COMMITTED；没有 workspace Company Identity uniqueness validation。
- `_build_company_alias_index_from_meta` 在读取时扫描全部 published `meta.json` 构建 `alias -> [ticker]`，`resolve_existing_ticker` 只有在查询遇到多个 ticker 时才抛错。
- 现有 storage 测试先成功提交两个都声明 `DUPLICATE` 的 canonical corpus，再断言查询时报 `ValueError`；该测试现状证明冲突是 late failure，而非持久化前原子拒绝。

因此当前 durable state 可以进入歧义状态，查询结果和错误依赖已提交内容，不满足 workspace 内确定性映射要求。

### 5. list_documents 存在下游 loose parsing

- `dayu/fins/tools/read_runtime.py::_resolve_canonical_ticker` 先尝试 `try_normalize_ticker`；失败时自行回退 `strip().upper()`，再交给 repository 扫描 alias。
- `dayu/fins/storage/_fs_company_meta_core.py::resolve_existing_ticker` 又先按 normalizer 猜 canonical 目录，再回退扫描 alias index。
- 查询路由虽然能处理部分 alias，却是 read runtime 与 storage 两级推断，不是消费结构化 Company Identity contract。

这正是需要移除的下游 fallback；`list_documents` 应只把用户输入交给唯一 identity resolver，由 storage 返回唯一 canonical corpus。

### 6. 用户可见和 LLM-facing 文案不自足

- CLI required ticker help 仍是“公司代码或财报主体”，没有说明 CSV 第一项/后续项语义。
- upload tool 把 `ticker` 和 `ticker_aliases` 暴露为两个字段，描述分别只是“股票代码”和“可选股票代码别名列表”，未说明 canonical 与用户声明 alias 的关系。
- read tool ticker schema 只说明自然 ticker 写法，也没有明确 accepted alias 会路由到同一 corpus。

这些文案无法让无状态 LLM 稳定构造正确输入，也没有与 durable identity contract 同源。

### 7. Design documents 排除错误 owner 路径

- `docs/host/design.md` §2 明确 Host 不承载财报业务语义、不直接管理财报原文仓储规则。
- `docs/engine/design.md` §1 明确 Engine 不负责财报业务语义、ticker 归一、工具参数校验或财报文档仓储访问。
- 所以本修复必须停留在 Fins domain / storage 及其直接 consumer，不能在 Host、Engine 或 LLM projection 下游补偿。

## Confirmed goal and motivation

建立唯一、可持久化且可查询的 Company Identity / CompanyMeta contract，使一次 ticker CSV 声明从入口到查询保持同一语义：

- CSV 第一项是 canonical corpus ticker，后续项是用户明确声明的同公司查询 aliases；系统信任该声明，不联网核验现实归属。
- 唯一 ticker normalizer 统一 US/CN/HK canonicalization、长度边界、纯语法变体以及 resolver `V.BA` 类 alias 可消费 grammar。
- 唯一 Company Identity contract 合并 canonical、用户声明 aliases、跨市场 aliases 和 resolver aliases，并对 canonical-equivalent/重复项做稳定去重；语义不同且已接受的 alias 不得丢失。
- CompanyMeta durable state 和 storage alias index 均由该 contract 投影；同一 normalized alias 只能属于一个 canonical corpus。
- 冲突必须在 canonical corpus 发布前，在 workspace 级原子 owner 下拒绝；失败必须经现有 Fins typed failure 边界投影为有界、可行动错误，不能留下歧义 published state。
- `list_documents` 传 canonical 或任一 accepted alias 都由 storage identity route 命中同一 canonical corpus并返回同一文档集合。
- CLI、upload tool、resolver、download/upload pipelines 与 read runtime 只复用 contract，不保留重复 grammar、loose fallback 或查询时猜测。

## Success signals

1. Company Identity owner tests覆盖 US/CN/HK、长度边界、纯语法变体、跨市场 alias、`V.BA`、`DELTA,MSFT`、重复和 canonical-equivalent 稳定去重。
2. `AAPL,AAPL,US.AAPL` 只产生一个 canonical identity，不产生重复映射；`DELTA,MSFT` 被无条件接受为用户声明关系，不触发联网核验或现实公司纠正。
3. upload 对全新与既有 fresh CompanyMeta 都可靠持久化新 accepted aliases；durable meta、alias index 与 resolver 输出由同一 contract 派生。
4. 同一 alias 指向多个 canonical corpora 的顺序和并发场景都在发布前原子失败，published state 保持原状；typed failure code/message 有界且可行动。
5. `list_documents(canonical)`、`list_documents(user alias)`、`list_documents(cross-market alias)` 与 `list_documents(resolver alias)` 返回同一 canonical ticker 和同一文档集合。
6. CLI help 与 upload/read tool schema 自足说明 canonical/alias 输入与查询语义，不暴露不必要内部术语。
7. 受影响 owner-level、storage atomicity、CLI/tool 和端到端边界测试通过；受影响生产文件单文件覆盖率达到目标，全量 pyright 无新增或扩散错误。
8. README 只在各文档职责和读者边界内更新。

## Non-goals and scope boundary

- 不执行 UF-PF05 真实 CLI evidence。
- 不刷新 oracle/scenario registry，不修改任何冻结 evidence。
- 不处理其它 finding，不扩展到无关 filing/calendar/download 行为。
- 不联网核验、猜测或纠正用户声明的公司 alias 现实归属。
- 不兼容读取旧歧义 alias state，不增加 compatibility shim、re-export、adapter fallback、loose parser 或下游补偿。
- 不把 Company Identity 提升为 Host/Engine/runtime 状态机，不新增网络 identity service、数据库迁移框架或无当前需求的 registry abstraction。
- 按用户明确指令不创建 PR、不 push；在当前分支按 Gateflow review checkpoints 创建本地提交并完成 final closeout。该指令覆盖 Gateflow 默认 draft-PR gate chain。

## Scope boundary and likely affected owners

- Domain contract: `dayu/fins/ticker_normalization.py` 与新的或现有的 Company Identity / CompanyMeta owner boundary。
- Durable uniqueness/routing: `dayu/fins/storage` protocol、filesystem implementation、batch publication guard/index。
- Direct producers/consumers: CLI ticker input、upload tool schema/request、FMP resolver、SEC/CN/HK company meta pipelines、upload company meta decision、read runtime。
- Tests: domain owner、resolver、upload runtime/tool、CLI、storage atomicity、read/list_documents route 与必要 end-to-end fixtures。
- Docs: 先读取 `dayu/fins/README.md`、`tests/README.md` 和根 `README.md` 的各自更新约束后裁决；Host/Engine 设计边界预计无需修改。

精确文件列表、public types/functions、atomic lock/index publication 方案、typed failure code 路径和 slice 拆分由 plan gate在 AgentCodex 读取完整 transaction/error data flow 后冻结；goal gate不提前发明实现。

## Explicitly avoided over-design

- 不引入联网公司主数据、证券主表、现实公司校验或跨 workspace 服务。
- 不建立通用 alias framework、插件 registry、callback/factory/profile/query facade 或 Host durable identity。
- 不为历史歧义 state 做双读、迁移、兼容 alias 或自动修复。
- 只为当前文件系统 workspace 的 CompanyMeta publication 增加满足并发确定性的最小原子边界。

## Validation performed at this gate

- 读取并核对 Gateflow、Init Agents、tmux-cli、项目 `AGENTS.md`、`docs/host/design.md` 与 `docs/engine/design.md` 的相关 owner 边界。
- 成功执行 `git fetch github main` 和 branch/worktree/merge/main ancestry preflight。
- 成功运行现有 resolver `V.BA` 与 storage duplicate-alias 测试：`2 passed`；它们分别证明 resolver output grammar 与 late conflict 现状。
- 成功运行纯 Python probes，确认 `V.BA` normalizer 失败、CLI CSV 去重行为和 fresh CompanyMeta 丢弃新 alias 的直接结果。
- 未修改生产代码，未运行 UF-PF05，未读取或修改冻结 evidence。

## Residual risks and uncovered areas

- Workspace-scoped alias uniqueness 应复用何种现有 lock/journal boundary、如何避免 lock ordering deadlock：由 plan gate基于完整 storage transaction data flow 冻结，分类为 `covered by next gate`。
- Conflict 如何从 storage/domain exception 映射到现有 `FinsUploadUsageFailure` 且保持 CLI/tool/direct stream 一致：由 plan gate冻结，分类为 `covered by next gate`。
- Existing CompanyMeta 更新时 company name/resolver freshness 与显式 alias 合并的精确规则：由 plan gate按“alias 声明不可丢失、其它字段不越界修改”冻结，分类为 `covered by next gate`。
- UF-PF05 真实 CLI evidence：用户明确排除，分类为 `assigned to later work unit`。
- 其它 finding 与冻结 oracle/scenario registry：用户明确排除，分类为 `assigned to later work unit`。

## Blocking open questions

没有发现需要扩展业务范围的 blocking question。进入 plan 的唯一 Gateflow stop condition 是用户确认本 artifact 复述的目标、owner boundary、成功信号与非目标。

## User decision

用户已确认以上目标、owner boundary、成功信号与非目标，可以进入 plan。
