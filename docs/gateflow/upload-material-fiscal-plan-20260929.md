# UM-O09-F01 + UM-O10-F01：material 财年与财期同源输入域计划

- Gate：`plan review → fix`；work unit：`UM-O09-F01 + UM-O10-F01`；状态：按第四轮 MiMo 两项 finding、O06 合流裁决与总控裁决修订的候选计划，待 Kimi/MiMo 双路有效 plan re-review。
- 工作区：`/private/tmp/dayu-upload-fiscal`；branch：`codex/upload-material-fiscal`；基线 HEAD：`8d8d494fbbce0052372fb1b42097c9f7222cfa28`。计划编写前 `git status --short` 只有未跟踪的 `docs/gateflow/upload-material-fiscal-goal-20260929.md`。
- 已确认 goal：`docs/gateflow/upload-material-fiscal-goal-20260929.md`。裁决依据（主工作区只读）：`/Users/leo/workspace/dayu-agent-r/docs/reviews/upload-material-um-o09-oracle-adjudication.md` 与 `upload-material-um-o10-oracle-adjudication.md`。冻结 CLI 场景只证明当时的观察；以下实现判断另由本 HEAD 代码核对。
- 本轮只修候选计划并静态核对；第四轮 MiMo 复审与总控裁决已落盘，修订后仍须 Kimi/MiMo 双路有效 plan re-review，不在本轮实现、提交或发布。

## 目标、动机与成功信号

问题成立，严重性是错误 material 身份已能发布：O09 隔离场景中的 `-1/0/10000`、O10 中的任意或 241 字符 period 被存入 source meta；本 HEAD 的 `build_material_ids` 将未检验的财年和仅 trim/uppercase 的财期加入稳定 ID seed。这是身份输入与发布事实同源性问题，不能在 CLI 展示或仓储读回时补救。O09 冻结场景同时改变材料名，不能把不同 ID 的单次比较作为单独的财年因果证据；因果依据是当前 builder 的 seed 代码。

成功信号：

1. material 的 `fiscal_year` 可省略；提供时必须是整数且位于 **1800..2100 闭区间**，`1800` 和 `2100` 均接受，`bool` 不作为整数接受；`-1/0/1799/2101/10000` 拒绝。CLI 非整数文本仍交给现有 argparse 基线。
2. material 的 `fiscal_period` 可省略；CLI 与 owner 直接输入复用 `dayu.fins.domain.filing_semantics.normalize_fiscal_period`，trim/uppercase，`None`、`""`、纯空白都成为 `None`；非空仅 `FY/H1/Q1/Q2/Q3/Q4`。`" q1 "` 成为 `Q1`；`nonsense` 和 241 字符输入被拒绝。tool 参数层另有输入形状契约：省略或 `null` 表示未提供，空串/纯空白先以 `invalid_argument` 拒绝，不进入 Fins admission，也不创建 awaiting handle；不为表面一致改共享 tool 参数 helper。枚举已经吸收长度限制，不新增长度规则。
3. 通过 Fins admission 的非法域值在 direct producer、`upload.started`、observation/job、runner、converter 与公司/材料业务持久化之前成为字段明确的 typed usage failure；CLI 用法错误退出 `2`，tool 对已通过参数读取的域值错误给出同一 Fins usage message。tool 的空串/纯空白 period 在参数层返回 `invalid_argument`，同样无发布副作用或 awaiting handle。合法值的稳定 ID seed、事件/结果中存在的 fiscal 字段、source meta 与 manifest **已有身份字段**来自同一 canonical 请求事实。material manifest 当前不含 `fiscal_year/fiscal_period`（`MaterialManifestItem` 只投影 document/internal ID、form/name、日期等），本项不新增字段或修改 schema。

## 范围、直接代码证据与 owner

- `dayu/fins/ingestion_runtime.py`：`FinsUploadMaterialRequest` 两字段可选；`_normalize_upload_request` 对 material 只替换 action。`upload`、`prepare_observed_upload`、`start_upload` 都先调用 `_validate_runtime_upload_request`，然后才创建 direct producer、observation 或 job；这是共享前置 usage admission。Service `upload_material` 与 tool 的请求最终进入这里。
- `dayu/fins/pipelines/docling_upload_service.py`：`build_material_ids` 是 material 稳定身份 owner，现将 year 直接 `str()` 放入 seed；私有 `_normalize_optional_upload_fiscal_period` 只做 trim/uppercase。它也被 US、CN/HK workflow 调用，故可在此边界保护公开 builder 与绕过 runtime 的直接 workflow。
- `dayu/fins/domain/filing_semantics.py`：`normalize_fiscal_period` 是既有唯一财期枚举真源。`parse_calendar_year` 与 filing 的 `INVALID_FISCAL_YEAR` 则承诺 **1000..9999**；`ingestion_runtime.py:_USAGE_MESSAGES` 现有文案正是“财年（fiscal_year）必须是 1000..9999 的整数”。**不能直接复用该 usage code 给 material 误报范围，也不能把 filing 范围改成 1800..2100。**
- `dayu/fins/pipelines/sec_upload_workflow.py:run_upload_material_stream` 与 `cn_pipeline.py:CnPipeline.upload_material_stream` 现各自 `str(...).strip().upper()` 后同时构造 ID 和 source meta；US、CN/HK 直接 facade 是公开可达路径。它们必须调用同一 owner 的校验/规范化，并只使用返回值；不能保留各自的独立 period 规则。`MaterialManifestItem.from_source_meta` 从 source meta 投影已有身份字段，不为本项改仓储。
- `dayu/cli/commands/fins.py` 对 material 只转发 CLI 参数，其空文本先成为 `None`；`dayu/fins/tools/upload_tools.py` 构造原始请求且 schema 目前只说 material 财年/财期“可选”。现有 tool 参数读取对空串/纯空白 `fiscal_period` 直接拒绝；CLI 不增第二套判定，tool schema 需自足说明入口真实差异及新增域。

**唯一语义 owner：**material 年份 1800..2100 规则与 material 稳定身份边界放在 `docling_upload_service.py`；该身份 builder/validator 也承担 O07-F02 的稳定 ID 一致性语义。period 的允许域及 canonical 规则继续由 `filing_semantics.normalize_fiscal_period` 唯一拥有。`ingestion_runtime.py` 只把这两个 owner 的失败映射成 material typed usage，并将 canonical 值写回同一 immutable material request。US/CN/HK 直接入口调用这一共享 admission；公开 `build_material_ids` 复用同样的底层规则，避免公开绕行。O07 在后续同一前置链串行合并，不由本项预做 ID 输入移除或另造 admission。不要新增第二个 year parser、period 域、loose parsing、下游 fallback 或新持久化字段。

## 最小实现契约与数据流

1. 在 `docling_upload_service.py` 增加公开、带完整中文 docstring 的 `validate_material_fiscal_year(value: int | None) -> int | None`。`None` 原样返回；对 `bool`、非 `int`、小于 1800 或大于 2100 抛 `ValueError`。上下界用该模块命名私有常量，错误指明 `fiscal_year` 与 1800..2100。`build_material_ids` 在任何 seed 拼接前调用它，同时直接调用 `normalize_fiscal_period(..., field_name="fiscal_period")`；删除 material 私有 `_normalize_optional_upload_fiscal_period`，不留下兼容 wrapper。合法既有 seed 结构、ID 前缀及 hash 算法不变。
2. 在 `ingestion_runtime.py` 为 material 增加独立 `FinsUploadUsageCode.INVALID_MATERIAL_FISCAL_YEAR`；其精确文案为“材料财年（fiscal_year）必须是 1800..2100 的整数”，字段和值域自足，通道中立，不含 `--flag` 或其它 CLI 术语。filing `INVALID_FISCAL_YEAR` 及其 1000..9999 文案保持原样。material 的非法 period 可使用既有 `UNSUPPORTED_FISCAL_PERIOD`（其文案已准确列出同一枚举），但不使用 filing 的必填或 240 长度错误。增加公开 `admit_fins_upload_material_fiscal(*, fiscal_year: int | None, fiscal_period: str | None) -> tuple[int | None, FiscalPeriod | None]`：分别调用 `validate_material_fiscal_year`、`normalize_fiscal_period`，逐字段捕获 `ValueError` 并通过 `_raise_upload_usage` 映射相应 closed code；不解析异常字符串。`_normalize_upload_request` 的 material 分支调用它，返回 `replace(request, action=..., fiscal_year=validated_year, fiscal_period=canonical_period)`。CLI/tool/Service 不重校验；调用早于摘要和生命周期创建。
3. 在 US 与 CN/HK material workflow 开头、任何上传事件/仓储读取或写入前，调用同一个 `admit_fins_upload_material_fiscal`，保存局部 canonical year/period。此处保护直接调用 facade 的公开路径，失败同为 `FinsUploadUsageError`。删除两个 workflow 的独立 `str(...).strip().upper()`；ID builder、`UPLOAD_STARTED`、`prepare_upload(meta=...)`、completed/failed result 均取同一 canonical 局部值。CN 与 HK 共用 `CnPipeline` 分支，测试分别覆盖。builder 对直接调用者再次保证自己的公开契约，但不产生第二套规则。
4. 在 `upload_tools.py` 的 `fiscal_year`/`fiscal_period` schema description 中写明 material 可选及准确域、非空财期 trim/uppercase；共享 `fiscal_period` 参数必须按业务上下文分句：filing 分句明确财期必填，省略或传 `null` 均按必填错误拒绝，且只支持 `FY/H1/Q1/Q2/Q3/Q4`；material 分句明确财期可省略或传 `null` 表示未提供，非空文本去首尾空白并转大写后只支持这六个值。空字符串或纯空白在 tool 参数层均以 `invalid_argument` 拒绝，不能写成 material 的“未提供”，也不能把 material 的省略/`null` 规则写成共享参数的全局规则。`fiscal_year` 保持 filing 必填与 1000..9999 范围，material 可选且提供时为 1800..2100。只改 LLM-facing 描述，不引入内部类型名或治理状态。CLI parser/Service/仓储契约无需修改，CLI 空文本与 owner 直接空值转 `None` 的已接受行为保留。

入口与失败状态：CLI `dayu-cli upload_material` → Service → runtime `upload`；`start_fins_upload` → runtime `prepare_observed_upload`；legacy `start_upload` → 同一 `_validate_runtime_upload_request`。输入非法时这三条均在 producer/observation/job 前终止。直接 US/CN/HK workflow 同样得到 typed usage；公开 ID builder 在相同年/期底层规则下抛 `ValueError`，两者都无上传事件或存储变更。有效值进入同一请求/局部事实，身份和发布读同值。不存在新 operation status、schema migration 或持久化兼容路径。

## 文件白名单与行为切片

Goal alignment（本项没有另附 design document；已确认 goal 与两份裁决为范围合同）：年份 helper、新 usage code 及边界测试对应 O09 的 1800..2100/零副作用；period 真源复用、空值/枚举测试对应 O10；US/CN/HK 同源投影、真实 CLI 与 owner 测试共同验证两项的身份不分叉和前置拒绝。tool schema 与 README 只更新这两项已有公开字段的必要说明。S1 每一步均由这两个 success signal 或防止绕过的必要 correctness 条件推出；其它修复项仅列 residual，不作为本切片验收扩展。

**本 work unit 实现唯一允许的文件白名单**（计划审查如发现必需的新文件，先修改获批计划，不在实现时顺手扩围）：

| 用途 | 文件 |
| --- | --- |
| fiscal 身份 owner、runtime admission、US/CN/HK 直接入口、LLM tool schema | `dayu/fins/pipelines/docling_upload_service.py`；`dayu/fins/ingestion_runtime.py`；`dayu/fins/pipelines/sec_upload_workflow.py`；`dayu/fins/pipelines/cn_pipeline.py`；`dayu/fins/tools/upload_tools.py` |
| owner、runtime、US/CN/HK、tool、CLI 验证 | `tests/fins/test_docling_upload_service.py`；`tests/fins/test_fins_ingestion_runtime.py`；`tests/fins/test_sec_pipeline_upload_material_stream.py`；`tests/fins/test_cn_pipeline.py`；`tests/fins/test_fins_ingestion_tools.py`；`tests/cli/test_fins_commands.py` |
| 触发时按职责更新 | `dayu/fins/README.md`；`tests/README.md`；`README.md` |
| 本 gate artifact | `docs/gateflow/upload-material-fiscal-plan-20260929.md` |

**一个行为切片 S1：material fiscal identity admission 与同源发布。** 前提是本计划通过 review 且集成基线未漂移。一次实现 pass 完成上述 owner、前置 typed usage、直接 facade 同源化和 schema 描述；一次 review pass 对照 O09/O10。按文件拆成多个 slice 会留下“已拒绝但 meta 仍分叉”或“pipeline 修好但 job 已开始”的中间状态，增加 gate 成本而无独立可验收业务增量。

S1 测试契约：owner 层覆盖 `None`、1800、2024、2100 与域外/`bool`；period 全枚举、大小写/空白、空/缺失、任意和 241 字符；相同 canonical 输入得到相同稳定 ID，非法输入不生成 ID。runtime 三入口对 US/CN/HK 均在 producer/observation/job/executor 前抛对应 `FinsUploadUsageError.failure.code`，runner 零调用、隔离 workspace 前后树一致、无 `upload.started`。owner usage 测试逐字断言 `INVALID_MATERIAL_FISCAL_YEAR` 的 message 等于“材料财年（fiscal_year）必须是 1800..2100 的整数”，并断言 `"--" not in message`；tool 测试对该 code 的实际错误投影也逐字断言同一 message 且无 CLI 术语。US/CN/HK 直接 workflow 非法值在首个事件/仓储变更前抛相同 typed usage code；合法输入以同一个 canonical period 出现在 ID、事件、source meta、result，manifest 的 `document_id/internal_document_id` 与 source meta 相等且不增加 fiscal 字段。tool 对已通过参数读取、进入 Fins admission 的**域值错误**（year `-1/0/10000`、period `nonsense`/241 字符）验证同一 Fins usage message 与 awaiting handle 零创建；`bool`/非整数 year 由 tool 参数读取层按现有类型错误拒绝，不断言 Fins usage message，也不为了该断言透传类型垃圾；tool 另测 material 省略或 `null` 的 period 表示未提供，filing 省略或 `null` 的 period 因必填在 tool 参数层返回 `invalid_argument`，两种业务上下文的空串/纯空白 period 也均在参数层返回 `invalid_argument`；这些参数层失败不进入 Fins admission 且 awaiting handle 零创建；owner 层另测 `bool` 拒绝。同步迁移 `tests/fins/test_fins_ingestion_tools.py:1718-1723` 对 `fiscal_year`/`fiscal_period` schema description 的精确旧断言至新文案，不为保住旧断言回退生产 schema；新断言逐字核对 filing 必填及六枚举、material 可省略/`null` 及六枚举、两种业务上下文的空串/纯空白均在参数层拒绝，并与上述行为测试一致。CLI 使用真实可执行入口而非只断言 fake Service，验证退出码/双流/文件系统与合法发布，其中 `--fiscal-period ""` 仍按 `None` 验收。

S1 完成信号：两项修复均满足上列测试及真实 CLI、pyright、覆盖率和 README 判定；任一公开路径仍绕过同源 owner、需要修改 filing 年域/持久化 schema、或校验晚于 `upload.started`，均停止并回到计划裁决。

## 验证命令与证据

实现 gate **先在本隔离 checkout 建锁定 Python 3.11 环境**。本工作区当前缺少 `.venv`；不得借用主工作区 editable venv，亦不得把未安装依赖导致的收集失败算作产品错误或测试通过。当前平台为 macOS arm64，按仓库约束文件安装；安装完成后，在任何测试、coverage、pyright 或真实 CLI 前检查解释器版本、venv 所在位置及 `dayu.__file__` 指向本 checkout。若其中任一项失败，记录原命令与错误并先修环境，不产出实施验证结论。实施验证 artifact 记录解释器路径、`python -V`、`dayu.__file__`、约束文件和安装命令；所有验证均使用该环境。

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[test,dev,browser]" -c constraints/lock-macos-arm64-py311.txt
python -c 'import dayu, pathlib, sys; root = pathlib.Path.cwd().resolve(); print(sys.executable, sys.version, dayu.__file__); assert sys.version_info[:2] == (3, 11); assert pathlib.Path(sys.prefix).resolve() == (root / ".venv").resolve(); assert pathlib.Path(dayu.__file__).resolve() == root / "dayu/__init__.py"'
```

受影响测试至少运行：

```bash
python -m pytest tests/fins/test_docling_upload_service.py tests/fins/test_fins_ingestion_runtime.py tests/fins/test_sec_pipeline_upload_material_stream.py tests/fins/test_cn_pipeline.py tests/fins/test_fins_ingestion_tools.py tests/cli/test_fins_commands.py -q
python -m pyright dayu/ tests/ utils/
```

覆盖率分两种明确口径：下列六文件定向子集用于定位本项新增分支；再运行 `tests/` 全量测试，作为每个被改生产文件的单文件 ≥80% 判定口径。两次均使用相同五个 `--cov` 目标及 `term-missing`，在实施验证 artifact 中逐文件抄录**实测**语句数、未覆盖语句数、覆盖率百分比和缺失行；不得把定向子集百分比称为全量覆盖率，也不得用五文件合计百分比代替单文件判定。本计划修订只作静态核对，尚无修复后实测数字，不预填或推测覆盖率。若全量某文件不足 80%，先补有效相关测试并重测，记录补测前后真实数字、未覆盖原因及剩余缺口；仍不足时分类为 residual 交 gate 裁决，不虚报达标。

```bash
python -m pytest tests/fins/test_docling_upload_service.py tests/fins/test_fins_ingestion_runtime.py tests/fins/test_sec_pipeline_upload_material_stream.py tests/fins/test_cn_pipeline.py tests/fins/test_fins_ingestion_tools.py tests/cli/test_fins_commands.py -q --cov=dayu.fins.pipelines.docling_upload_service --cov=dayu.fins.ingestion_runtime --cov=dayu.fins.pipelines.sec_upload_workflow --cov=dayu.fins.pipelines.cn_pipeline --cov=dayu.fins.tools.upload_tools --cov-report=term-missing
python -m pytest tests/ -q --cov=dayu.fins.pipelines.docling_upload_service --cov=dayu.fins.ingestion_runtime --cov=dayu.fins.pipelines.sec_upload_workflow --cov=dayu.fins.pipelines.cn_pipeline --cov=dayu.fins.tools.upload_tools --cov-report=term-missing
```

实施验证记录须对 `dayu/fins/pipelines/docling_upload_service.py`、`dayu/fins/ingestion_runtime.py`、`dayu/fins/pipelines/sec_upload_workflow.py`、`dayu/fins/pipelines/cn_pipeline.py`、`dayu/fins/tools/upload_tools.py` **逐个生产文件**分别列出定向子集与全量的命令/结果来源、实际数值和是否达到 80%；不足项另列有效补测及复测数字、残余与 owner。若全量测试不能跑完或覆盖率输出不可比，记录真实失败原因与已取得数字，并将该文件的门槛状态标为未验证，不用子集数字代填。

真实 CLI 在 `tmp_path` 或独立临时工作区准备可转换的材料输入和有效公司信息，使用 `.venv/bin/dayu-cli upload_material --ticker AAPL/600519/0700.HK --forms MATERIAL_OTHER --material-name Deck --files <文件>` 为基线；分别组合 `--fiscal-year` 的 1800、2024、2100、-1、0、1799、2101、10000，`--fiscal-period` 的 `" q1 "`、`""`、`nonsense`、241 个 `P`，并包含省略两字段。每个非法场景使用独立 fresh/可归因的已存在目标，捕获 exact argv、退出码、stdout、stderr、工作区前后快照、source meta/manifest；预期 exit `2`、一行字段明确 usage、stdout 无 `upload.started`、无公司/材料业务发布及 job/observation。合法场景预期 exit `0`，核对 ID 与 source meta 的 canonical year/period、manifest 已有身份字段；单独同 form/name/year 对比 `" q1 "` 与 `Q1` 的稳定 ID。真实 CLI 对三市场各至少覆盖一组合法与非法，避免只由模拟服务证明入口行为。当前计划 gate 不执行这些实现验证。

文档判定：实现时先按已读的各 README `Agent更新约束` 复核当前入口。`dayu/fins/README.md` 的 material admission/公开契约属于职责范围，应更新；根 `README.md` 的 material CLI 可选年/期规则及错误属于用户手册范围，应更新；`tests/README.md` 只有新增测试层级或其现有说明受影响才更新，不机械同步。计划 gate 不修改这些文档。

## 依赖、residual 与修复项登记

| 项 | 状态与本项边界 |
| --- | --- |
| `UM-O09-F01` | **本计划登记实施**：material 可选 year 的 1800..2100 闭区间前置 typed usage，身份与 source meta 同源；filing 1000..9999 不动。 |
| `UM-O10-F01` | **本计划登记实施**：复用 filing period canonical 真源，空→`None`、非空限六枚举；不另设长度上限。 |
| `UM-O05-F01` | 另一个 work unit 的 form/name 无条件必填；共用 material admission，汇入时串行复核校验顺序、usage code 与 `replace(request, ...)`，本项不实现必填。 |
| `UM-O06-F01` | 另一个 work unit 已确认的 `material_name` 规则为去首尾空白后最多 240 个 Unicode 码点，超限须在上传启动前拒绝；其名称真源与本项 `build_material_ids`/共同 admission 相接。汇入时串行核对同一 canonical 名称先于 ID、source meta 与 LLM 投影，复用 O06 owner 的长度常量/校验，不在本项复制实现、常量或测试验收。O05 必填与 O06 长度合用同一 admission。 |
| `UM-O07-F01/F02` | 与 O09/O10 用户裁决指定的 material identity builder/validator 共 owner；后续串行合并 fiscal admission 与 `validate_material_upload_ids` 为同一前置链。稳定 ID 依赖 canonical fiscal/form/name，因此联合非法时先报 fiscal typed usage，只有 fiscal 合法、身份 seed 输入规范化后才做 `document_id` 一致性检查并投影 O07-F02 字段级错误；两者均在 `upload.started`/持久化前结束，不增第二套 admission。O07-F01 移除公开 `internal_document_id` 输入时，逐处合并 `FinsUploadMaterialRequest` 字段、`replace(request, ...)`、CLI/Service 透传、US/CN/HK workflow 参数及 `validate_material_upload_ids`，并核对本项 `upload_tools.py` 财年/财期描述与 O07 tool schema 删除输入项的同块修改；底层生成的 internal ID 与既有 manifest 投影仍由 owner 派生。本项不实施 O07。 |
| `UM-O11-F01` | 另一个 work unit 的 material 日期校验；与本项共用 runtime 前置边界，汇入时串行合并并核对同一 canonical 请求，本项不处理日期。 |
| `UM-O16-F01` | 另一个 work unit 的 action/files 组合；汇入时确保其优先级与 typed usage 不被本项遮蔽，本项不改 action/files。 |
| `UM-O17-F01` | form canonical 与其 meta/manifest 投影另案；本项只保证 fiscal canonical。A14 的 form 分叉仍是 residual，不能误标为 O09，也不能借本项实现 form 规范化。 |
| `fins-upload-usage-message-channel-neutral` | 独立修复项；审计 tool 可见的其它 upload usage message 中 CLI flag 等入口术语，并在各语义 owner 改写。本项仅处理 O09/O10 财年/财期输入域与上述 schema 文案，不实施全局 usage 文案清理。 |
| `fins-material-legacy-invalid-fiscal-identity-recovery` | **独立待裁决 work unit；本项未修复。** 修复前以非法 fiscal year/period 已发布的 material，其旧值已进入稳定 ID seed；新 admission 拒绝旧值，`upload_material` 的 update/delete 无法再生成旧 ID 寻址。换成合法值或省略字段会形成不同 seed，显式传入旧 `document_id` 也受稳定 ID 一致性校验拒绝。依据是本 HEAD `build_material_ids`/`validate_material_upload_ids` 与 O09/O10 冻结隔离场景的已发布证据；不能据此断言真实用户工作区也存在存量。本 S1 不兼容读取旧库、不加绕过准入的维护命令、不作手工文件系统处置。实施完成报告须明说该不可再寻址范围、证据身份及是否另有真实工作区核实；若真实用户工作区受影响，由总控另行确认目标与处置策略。 |

Residual：O05 的必填、O06 的名称长度、O07 的公开 ID 输入/一致性错误、O11 的日期、O16 的 action/files、O17 的 form 投影归后续已裁决 work unit；汇入实施检查按上表串行复核：O16 既定 action/files 优先级不被遮蔽，O05/O06/O17 与 fiscal 均先于稳定 ID，fiscal 与 ID 同时非法时先报 fiscal typed usage；检查 `replace(request, ...)`、US/CN/HK workflow 与 tool schema 重叠改动无字段残留或独立规则，O07 字段级错误不遮蔽 fiscal typed usage。此处只规定身份计算所需的偏序，不替其它 work unit 决定 O05/O06/O17 之间的完整错误顺序。O11 日期字段与本项使用同一个 tool 参数读取 helper，其空文本输入形状由 O11 work unit 单独验收。旧非法 fiscal 身份不可再寻址归独立待裁决 `fins-material-legacy-invalid-fiscal-identity-recovery`，与 `fins-material-legacy-identity-seed-disposition` 的归属关系由总控集成前核对，避免两个 owner 分叉，不算本项完成。当前 HEAD 的 frozen 场景不是修复后证据；本计划仅静态核对，锁定 venv、真实 CLI 补跑、测试、逐文件 coverage、pyright 和 review gate 仍待实施 gate。若后续发现其它公开路径绕过上述共同 owner 且不能同源，或正确实现需要变更 filing 年域/持久化 schema，停止并重新裁决，不作局部补丁。

## 完成报告与下一 gate

实现完成时按修复标签分别报告：实际修改文件、owner/入口/状态与失败行为、真实 CLI 的原始证据位置及退出码、owner 测试/pyright、五个被改生产文件逐个的定向子集/全量覆盖率真实数字与不足残余、README 判定，以及旧非法 fiscal 已发布身份不能再由 update/delete 寻址的证据与独立待裁决归属。本 plan fix 完成后的下一 gate 是 **Kimi/MiMo 双路有效 plan re-review**；未通过复审不进入 implementation。本计划仅涵盖 goal 已确认的 fiscal 两字段及必要的同源/零副作用条件，没有扩大到旧库兼容、存量处置、新 period 域、form canonical、其它 material 修复或 schema。
