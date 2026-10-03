# UM-O06-F01：material_name 长度前置契约实施计划

RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/gpt-6-sol

- Gate：plan 候选；基线 workspace `/private/tmp/dayu-upload-o06`、branch `codex/upload-material-o06`、HEAD `8d8d494fbbce0052372fb1b42097c9f7222cfa28`。本 artifact 是唯一新增文件；不表示 plan review、实施或 PR gate 已通过。
- 直接证据：当前 `FinsUploadMaterialRequest.material_name: str | None`；`FinsIngestionRuntime._validate_runtime_upload_request()` 的 material 分支调用 `_normalize_upload_request()`，后者只处理 ticker/action/source kind，随后 direct 创建流、observation 建 handle 或 job 生成摘要并建 queued record。US/CN/HK workflow 另可直接进入 `build_material_ids()`，该 builder 只对名称 `strip()`、判空、参与 SHA-1 seed；workflow 之后把原名称写入 `upload.started`、result、`prepare_upload(meta=...)`，存储仓储从同一 meta 投影清单。job `_upload_request_summary()` 对名称调用 `_optional_bounded_text()`，其通用 `_MAX_TEXT_CHARS=240` 仅约束 job 摘要，并非 direct/pipeline 的材料名称契约。证据代码为 `dayu/fins/ingestion_runtime.py`、`dayu/fins/pipelines/{sec_upload_workflow,cn_pipeline,docling_upload_service}.py`、`dayu/fins/storage/_fs_processed_core.py`；入口在 `dayu/cli/commands/fins.py`、`dayu/service/fins_direct.py`、`dayu/fins/tools/upload_tools.py`。
- 动机判断：goal 中隔离 S01 的 241 码点上传成功、原样持久化及稳定 ID 已说明缺少一致准入；当前代码直接印证边界缺口。严重性是入口、生命周期与身份契约不一致；没有证据宣称既有数据损坏。**240 是用户在 2026-09-29 的明确裁决**，不是由 job 摘要常量或 241 样本推算。
- 风险快照：O17、O05、O16 当前是独立计划/裁决，产品代码尚未集成；本隔离 checkout 无 `.venv`。实施前必须复核集成 HEAD、真实 Python 3.11 环境及入口调用图。若唯一名称 owner 不能覆盖上述入口，或 O05/O17 集成使必填与长度无法落在同一 owner，停止并提交直接反例，不做下游 fallback。

## 目标、边界与唯一 owner

对 `material_name` 仅计算 `len(name.strip())`，允许最多 **240 个 Unicode 码点**；241 及以上在 `upload.started`、ID 生成、job/observation 创建和公司或材料业务写入之前，产生字段明确、可行动的 `FinsUploadUsageError`。`None`、空串、纯空白由 **O05** 的同一个 material admission owner 报必填错误，O06 不再加一个空值分支或把缺失当长度错误。所有 action 使用同一规则。合法值不截断、不做 NFC/NFD 归一化；O06 校验不修改 request/name，也不更换 `build_material_ids()` 的 seed、digest 或原有 raw 名称在事件、meta、manifest 中的语义。CLI/tool 已有去首尾空白投影和 job 摘要现有投影维持原样，各入口的既有投影不由 O06 重定义。

唯一业务 owner 是 Fins material request admission：在 `dayu/fins/ingestion_runtime.py` 中与 O05 的必填分支相邻，定义专属 `_MAX_MATERIAL_NAME_CODEPOINTS: Final[int] = 240`、封闭 usage code `MATERIAL_NAME_TOO_LONG`、同源中文 usage message，并由一个具完整中文 docstring 的材料名称校验函数执行 `len(name.strip()) > _MAX_MATERIAL_NAME_CODEPOINTS`。该函数只在 O05 已将名称收窄为非空 `str` 后调用，不返回改写后的名称；不复用 job 摘要通用 `_MAX_TEXT_CHARS` 作为业务规则，不在 CLI、tool、Service、ID builder、仓储或摘要再写一次长度判断。独立 US/CN/HK pipeline 的两个实际 ID 前入口调用**同一个** owner 函数，且在 workflow `try`、`build_material_ids()` 和任何读写之前；这是共享 owner 在另一入口的调用，不是 pipeline 自创规则。若实施 HEAD 已通过 O16 建立统一 pipeline 准入调用点，复用该点，不增加第二个入口分支。

具体顺序：runtime 继续做 ticker/action/source kind 的现有校验；material 分支按已集成 O05 的 form/name 必填及 O17 合法 form canonical 流程运行，在名称非空后做本项长度检查，再返回同一 request。名称和 form 同时非法时延续 O05 已确定的 form 优先级；名称为空时只报 O05 code。`upload()`、`prepare_observed_upload()`、`start_upload()` 都经 `_validate_runtime_upload_request()`，因此 direct、tool observation、legacy job 的超长请求不会触发 runner、ID、job store 或仓储。Service 只构造 request，CLI/tool 只负责现有参数结构与输入投影，并消费 Fins typed error；tool 协议仍按现有 `invalid_argument` envelope 映射，Fins reason/message 不另建 schema。独立 workflow 直调的超长名称也从相同 owner 抛 typed usage，不能被 workflow 泛异常收口成 `unexpected_runtime`。

无需新增持久化 schema、validated material wrapper、兼容读取或历史名称迁移。O04/O23 文件名、O07 稳定 ID 对外契约、O09/O10 财年财期、O12 公司名、O14/O15 状态、O16 action/files、O17 form canonical 各守原 work unit；本项只做名称上限及必要的入口说明。此方案只有一个判断和既有失败通道，满足 goal 且没有额外状态机或截断策略。

## 集成前提与一个行为切片

实施次序固定为：**O17 唯一 form canonical accepted+integrated → O05 同 admission 必填 accepted+integrated → O16 action/files 在同一 owner 串行集成并复核前两者 → O06 在该 HEAD 上实施**。O16 若已先行集成，后两项逐次重读实际 `_normalize_upload_request()`、workflow 和测试，不按旧候选文本硬套；O06 不复制 O16 validator。O05/O17/O16 任一尚未集成时，O06 计划可审但不得实施。每项是否通过 gate 以其当前独立 artifact 和总控裁决为准，不把候选 plan 当产品代码。未来其它身份/状态 work unit 合入后复核名称 ID 与公开投影，不能由本项预先修改它们。

只设一个 S1 行为切片：共同 owner 的 240 码点 typed 准入及现有入口一致性。一次 implementation pass 和一次 code review 即可验证，无按模块拆片的额外 gate 成本。实施仅限下列**精确写入白名单**，超出时先给证据并重新裁定范围：

| 类别 | 允许文件与具体变更 |
| --- | --- |
| owner | `dayu/fins/ingestion_runtime.py`：专属常量、code/message、单一 validator、O05 material 分支插入点及对应中文 docstring；不改 job summary 或通用 `_bounded_text()`。 |
| 独立 pipeline 入口 | `dayu/fins/pipelines/sec_upload_workflow.py`、`dayu/fins/pipelines/cn_pipeline.py`：在各 material ID 前调用同一 validator；不改 ID、事件、结果、meta、storage 或 filing。 |
| 输入说明 | `dayu/fins/tools/upload_tools.py` 只更新 LLM-facing `material_name` schema 描述，明确必填及“去首尾空白后最多 240 个 Unicode 码点”；`dayu/cli/arg_parsing.py` 只更新 `--material-name` help。`maxLength` 不能准确表达 `strip()` 后上限，不新增该约束。 |
| 测试 | `tests/fins/test_fins_ingestion_runtime.py`、`tests/fins/test_sec_pipeline_upload_material_stream.py`、`tests/fins/test_cn_pipeline.py`、`tests/fins/test_fins_ingestion_tools.py`、`tests/service/test_fins_direct.py`、`tests/cli/test_fins_commands.py`、`tests/cli/test_arg_parsing.py`；只补或迁移该契约与必要的旧 fixture。 |
| 条件文档 | `dayu/fins/README.md`、根 `README.md`、`tests/README.md`，只在下述职责命中时更新。`dayu/README.md` 的跨层边界不变，默认不修改。 |

`dayu/fins/service_runtime.py` 的晚期 None guard、`docling_upload_service.py` 的身份算法、`dayu/fins/storage/`、CLI command renderer 和 Service 生产代码不在本项写入白名单；不得用它们做缺口补偿。如实测证明这些额外变更不可避免，停止 S1，附调用证据和影响评估交总控重新裁定。

## owner 测试与验收矩阵

- owner 参数矩阵：`"A"*239`、`"A"*240` 接受；`"A"*241` 抛 `MATERIAL_NAME_TOO_LONG` 且同一中文 message。`"  "+"A"*240+"  "` 接受并保留 direct request 原字符串，`"  "+"A"*241+"  "` 拒绝；`None`、`""`、纯空白只按 O05 code 拒绝。长度检查覆盖 create/update/delete/auto，文件与目标条件用合法夹具隔离，避免 O16/状态错误混淆。
- Unicode：`"😀"*240` 接受、`*241` 拒绝；`"e\u0301"*120` 是 240 码点并接受，`*121` 是 242 码点并拒绝；NFC `"é"*120` 仅 120 码点。合法 NFC 与 NFD 的既有稳定 ID 可不同，测试确认没有自动归一化，不把字形簇或 UTF-8 字节数当长度。首尾空白只参与计数，不由本校验写回名字。
- direct/Service：通过真实 Fins runtime 及 Service direct 请求验证 241 同一 typed code/message，调用时即失败、没有 stream producer、`upload.started`、ID builder、runner、仓储写入；240 合法对照用既有 builder 对照 ID，并读回 raw `material_name` 事件/source meta/manifest。不得让 mock 预先拒绝或用假 ID 掩盖 owner。独立 US 与 CN/HK workflow 入口的 241 在 ID 和 started 前抛同码，合法 240 仍走原 ID/写入路径。
- job：`start_upload()` 的 241 在 queued record、executor submit、job event/summary 写入前拒绝；239/240 形成既有摘要，持久化 record 的名称与既有 summary 投影一致。`prepare_observed_upload()` 的 241 在 handle/activation 前拒绝，复核 tool 所用路径。
- tool：实际 tool callable 用 239/240/241、emoji/组合字符，检查 241 的 `invalid_argument` 与 Fins message、无 awaiting handle/runner/storage；schema 描述自足说明规则。若 O05 已改变 raw 输入 helper，只消费其合法投影，不为本项改回旧空值或 padded 值行为。
- 真实 CLI：锁定本 checkout Python 3.11、`dayu.__file__` 与 `dayu-cli` 身份，使用单独临时 base/workroot 和一份真实可转换材料，`python -m dayu.cli upload_material --base <case-base> --ticker AAPL --action create --forms MATERIAL_OTHER --material-name <name> --files <material.pdf> --company-name 'Apple Inc.'`；分别以独立 base 跑 239/240/241、240/241 emoji、240/242 组合码点、合法首尾空白、合法短名。记录每条 argv、exit、stdout/stderr、job/Host 状态、source meta/manifest、ID 与文件树前后快照。241/242 期望 exit 2、stdout 空、stderr 为同一 owner 可行动原因、无 `upload.started`/ID/业务发布；合法用例期望成功并核对读回，不把其它转换/环境失败计为长度失败。CLI 已有 `_optional_stripped_text()`，其合法 padded 输入投影与 direct raw 输入不同是当前入口行为，不用 O06 改写。
- 命令门槛：实施 checkout 先按根 README 的锁文件创建 `.venv`，`source .venv/bin/activate` 后核 `python --version` 为 3.11、`python -c 'import dayu; print(dayu.__file__)'` 落在本 checkout。运行 `python -m pytest tests/fins/test_fins_ingestion_runtime.py tests/fins/test_sec_pipeline_upload_material_stream.py tests/fins/test_cn_pipeline.py tests/fins/test_fins_ingestion_tools.py tests/service/test_fins_direct.py tests/cli/test_fins_commands.py tests/cli/test_arg_parsing.py -q`；再以相同集合加 `--cov=dayu.fins.ingestion_runtime --cov=dayu.fins.pipelines.sec_upload_workflow --cov=dayu.fins.pipelines.cn_pipeline --cov=dayu.fins.tools.upload_tools --cov=dayu.cli.arg_parsing --cov-report=term-missing`，逐个被改生产 `.py` 文件读取覆盖率，每个 **≥80%**；不足时增加有意义的相关测试范围，不能以总体均值替代。最后运行 `python -m pyright`，确认 0 新增/扩散错误，并核 `git diff --check` 与只含白名单的 diff。命令失败均保存原命令、退出码和原始 stderr，不将失败写成通过。

## README、风险与交付格式

实施阶段先重读各 README 的更新约束。`dayu/fins/README.md` 的公共 material admission 契约属于其开发者接口职责，应在代码落地后更新。根 `README.md` 的上传参数和用法错误属于最终用户工作流，应只补当前真实 CLI 限制及计数口径。`tests/README.md` 只在新增的测试分层/运行方式需要说明时更新，不机械复制用例；若无职责命中，记录不改理由。跨层装配未变，`dayu/README.md` 不动。当前仅写计划，不改上述 README。

残余风险及 owner：已发布超长名称的处置不是本项目标，归历史数据/identity 独立裁决；O17 合法 form 的跨代身份风险归 `fins-material-legacy-identity-seed-disposition`；O16 action/files 与后续 O07/O14/O15 状态变化由各 work unit 串行复核。若真实 CLI 的转换依赖不可用，记录环境失败并保留未验证项，不能以单元测试替代真实成功读回。若 O05/O17 不能在同一 admission owner 与 ID/workflow 合流、或独立 pipeline 仍绕过唯一 validator，立即停止，附最短调用链和具体失败证据，不增 downstream fallback。

S1 完成报告应依次给出 runtime/provider/model、实施 HEAD/文件清单、owner 直接证据、每个矩阵结果、真实 CLI argv/双流与读回、各生产文件 coverage、pyright、README 决定、失败命令原样、残余风险及下一 Gateflow entry。当前下一 gate 仅是同版 plan review，由总控裁决；本计划不授权实施、commit、push、PR 或 merge。
