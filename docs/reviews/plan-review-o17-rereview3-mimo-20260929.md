# Plan Re-Review（第三轮）：UM-O17-F01 material form canonical 实施计划（MiMo 独立 adversarial 复审）

RUNTIME/PROVIDER/MODEL: claude/mimo/mimo-v2.6-pro[1m]

CANARY=mimo-271a5124

- 审查对象：`docs/gateflow/upload-material-o17-form-plan-20260929.md`，SHA-256 `37d1c13e98e4db78d9ce02afe2dd6e92c53cead7e544690daa84e8845c4a3baf`（已用 `shasum -a 256` 独立核验，与任务给定值一致）。基线 HEAD `8d8d494fbbce0052372fb1b42097c9f7222cfa28`，未实施计划。
- 工作区：`/private/tmp/dayu-upload-o17`（隔离 checkout）。
- 审查方式：planreview 独立 adversarial 复审；只读代码与文档；不修改 plan/产品/测试/goal/裁决；不 commit/push/PR/merge；不派发子 Agent。
- 审查重点（任务指定）：F1 None/空白不得提前变成 O05 typed 规则、F2 跨命令读回、新旧 form 身份边界、单一函数调用图、测试与覆盖率/README 门槛；并主动找新的真实反例。
- 依据文档：
  - Goal Confirmation（binding scope contract）：`docs/gateflow/upload-material-o17-form-goal-20260929.md`。
  - 前轮 MiMo review：`docs/reviews/plan-review-20260929-030208.md`（F1 中/F2 低）、`docs/reviews/plan-review-20260929-033846.md`（F1/F2 闭合，新低 finding 历史 raw meta 跨代分叉）。
  - 总控裁决：`docs/gateflow/upload-material-o17-plan-review-adjudication-20260929.md`（F1/F2 accepted；历史状态范围风险归 `fins-material-legacy-identity-seed-disposition`；不接受把旧不一致写成通过测试；coverage 逐实际改动文件 >=80%）。
  - 本 checkout `AGENTS.md`、当前 HEAD 的 `dayu/fins` / `dayu/service` / `dayu/cli` 代码、`tests/fins` / `tests/cli` 测试。
- 本轮回独立重证方式：不沿用前轮结论，对 plan 的每个关键声称重新读代码验证（行号为本 HEAD 实读）。

## 停止条件裁决（先行结论）

- SHA-256 与任务给定值完全一致；plan、goal、adjudication、前两轮 review 均在。
- 关键 owner 证据全部可取得：`build_material_ids`（`docling_upload_service.py:1819-1856`）、`_normalize_upload_request`（`ingestion_runtime.py:7694-7715`）、三入口验证顺序、storage 写入、manifest 投影、读回 API 签名均实读核验。
- **不触发停止条件**，正常出具审查结论。

## 重点项核验（任务指定五项）

### 1. F1：None/空白不得提前变成 O05 typed 规则 —— 收口成立

| plan 承诺 | 独立重证 | 结果 |
| --- | --- | --- |
| 函数只对有效非空文本 `strip().upper()`；空白维持 identity builder 既有 `ValueError("form_type 不能为空")`；不做 None/空白 usage 分类器 | plan 第 13 行；`build_material_ids:1842-1846` 现行为：`normalized_form_type = form_type.strip().upper()` 后 `if not normalized_form_type: raise ValueError("form_type 不能为空")` | **属实**，错误类型与文案同源，函数契约即 builder 契约 |
| admission 仅对有效非空文本 `replace(request, form_type=canonical)`；`None`/空白原样留 request、沿现有后续边界失败；不改失败类型/时序/durable job 副作用 | plan 第 14 行；`_normalize_upload_request:7709-7712` material 分支现仅 `replace(request, action=action)`，`FinsUploadMaterialRequest.form_type: str \| None = None`（`:1567`） | **属实**；`None`/空白透传是行为保持策略 |
| `None` 不传给 `str` 签名函数、空白不在 admission 调用 | plan 第 14 行明文 | **属实**（guard 谓词落点见 Open Question 1） |
| 逐入口现有失败边界锁定（slice 5） | 实读：legacy 空白在 `_upload_request_summary` 的 `_optional_bounded_text`→`_bounded_text:7460-7480` 抛 `form_type 不能为空` 且在 `_create_queued_record_with_start_lock` 之前（`ingestion_runtime.py:4686-4705`）无 durable job；legacy `None` summary 记 `None`、durable job 之后 runner `service_runtime.py:223-224` 抛 `ValueError("material 上传必须提供 form_type")`；direct/observed 空白在 stream/identity builder 抛、`None` 在 runner 抛；tool 入口 `_required_text`（`upload_tools.py:355`）在工具边已拒缺失/空白（既有行为，O17 不触碰） | **属实**，四类入口失败面 plan 均保持 |
| O05 只以未来时态出现，不预支错误契约 | plan 第 14/25/46 行 | **属实**，无提前实施暗示 |
| 身份 builder 复用函数并保留两类空白拒绝（slice 4） | plan 第 27 行；`build_material_ids:1845-1848` 两类 `ValueError` | **属实** |

结论：F1 无残留实质缺口；admission guard 谓词的实现落点已被 slice 5 测试钉住行为，属实现精度问题（Open Question 1），不是契约漏洞。

### 2. F2：跨命令读回 —— 收口成立且可执行

- plan 第 39 行要求 A/B 各另起只读命令进程，以 `FsSourceDocumentRepository(workspace_root, create_directories=False)` 的 `list_source_document_ids(ticker, SourceKind.MATERIAL)`（`fs_source_document_repository.py:760`）与 `get_source_meta(ticker, document_id, SourceKind.MATERIAL)`（`:524`）读回；构造签名实读为 `__init__(self, workspace_root, *, file_store=None, repository_set=None, create_directories=True)`（`:224-231`），与 plan 用法一致。
- `workspace_root` 语义与 CLI `--base` 一致：`fins.py:1096-1107 _resolve_workspace_root` 即 `Path(raw).expanduser().resolve()`，生产装配 `service_runtime.py:382-400` 同一把 root 直接构造仓储，无隐藏子目录偏移；读回脚本可按 plan 字面执行。
- 读回断言走 source meta read owner，禁止路径/ID 推断（plan 第 39 行），符合 AGENTS.md「财报文档存取只能经 `dayu.fins.storage` 仓储」约束。
- `FinsReadRuntime.list_documents` 公开结果不含 form：`read_runtime.py:900` 明文「屏蔽底层 SEC 表单名，不对 LLM 暴露」，输出仅 `document_id/source_kind/material_name/...`；plan 只作 `document_type` 附加核对且声明 `MATERIAL_OTHER`→`material` 映射，与 `read_runtime_helpers._resolve_document_type` 的 material 回落一致（前轮核验，本轮抽查输出投影一致）。
- argv/退出码/双流/读回 JSON 留痕要求完整（plan 第 39 行）。

结论：F2 收口成立，读回合同真实可执行，无假造字段。

### 3. 新旧 form 身份边界 —— 与裁决完全一致

- 验收句限定「本修复后新写、或此前已由同版代码写入的 material」（plan 第 42 行），并明示「历史已发布 raw form 在 skip/delete 后不满足此同源验收，本项不宣称修复它」——即裁决要求的范围声明。
- 历史残余独立处置：plan 第 49 行明确 skip 不重写 source meta、delete 不迁移旧 meta、跨命令读回可与本次事件/结果跨代分叉，归 `fins-material-legacy-identity-seed-disposition` 裁决 owner 级迁移或全新起算；本项不迁移、不在 read/事件/summary/结果层 fallback。
- plan 第 29 行明文「不得用历史 raw meta 测试把跨代不一致固化为正确合同」——正是裁决「不接受旧不一致写成 owner 级通过测试」的镜像；skip/delete 用例限定同版 canonical source 先建后核，符合裁决口径。
- 补充核验（本轮新增）：update 路径天然自愈——`_fs_source_document_core.py:1771` 的 `merged_meta["form_type"] = req.form_type or merged_meta.get("form_type")` 在 canonical 显式参数非空时恒胜出（`prepare_upload:442` 拒空白保证非空），历史 raw meta 被 update 重写为 canonical，meta 与 manifest 同步（manifest 仅 `from_source_meta`，无第二写点）。

结论：新旧身份边界清晰，无目标漂移诱导。

### 4. 单一函数调用图 —— 独立穷举无反例

- owner 选址：`docling_upload_service.py` material identity builder 边界（plan 第 13 行），与 goal「做成一个函数，其它地方调用」一致。
- 调用方穷举：`build_material_ids`（内部复用）、`_normalize_upload_request`（admission，`ingestion_runtime.py:4745` 全库唯一调用点经 `_validate_runtime_upload_request`）、US `run_upload_material_stream`（`sec_upload_workflow.py:419`，唯一实现；`sec_pipeline.py:870-918` 为纯透传 wrapper，`:141` 导入）、CN/HK `CnPipeline.upload_material_stream`（`cn_pipeline.py:1040`）。两流各有五个 raw form 投影点（ID builder、started payload、`prepare_upload`、成功结果、失败结果）实读确认：`sec_upload_workflow.py:476/509/543/582/610`、`cn_pipeline.py:1092/1125/1159/1198/1226`。
- durable/可读投影同源链：summary `_upload_request_summary:7835` 读的是 `_validate_runtime_upload_request` 归一化后的 request（三入口 `:3672/:3869/:4686` 均在 producer/observation/job 创建前验证；legacy `:4691` summary 用 `normalized_request`）；storage meta 显式参数唯一写入（`:1771`）；`MaterialManifestItem.from_source_meta` 仅从 meta 投影（`document_models.py:1047-1081`），全库无第二直构；processed manifest 的 `form_type` 亦来自 source meta（`ingestion_runtime.py:5750/5800-5840` 读 `_optional_text_from_meta(meta, "form_type")`）——本轮新扫出的潜在第二 durable 面也同源，无分叉。
- 旁路面隔离成立：`build_cn_filing_ids`（`docling_upload_service.py:1917-1948`，filing form）、SEC/CN download form filter（`sec_downloader.py:2913`、`cn_pipeline.py:1385`）、读侧 `_normalize_form_value`（`ingestion_runtime.py:7557-7569`）、batch 路由 `_validated_material_form`（`upload_batch.py:800-815`，封闭路由集合，只产 CLI argv）、`section_semantic` 均为各自语义 owner，plan 明文隔离（第 13/33 行）。
- 无 kwarg 冲突面：`UploadOperationResult.payload` 各构造点（`docling_upload_service.py:598/752/787/996/1368/1792/2110/2138`）逐一核验无 `form_type` 键，`host._build_result(action=..., form_type=..., **upload_result.payload)` 不会多值冲突，结果 form 只来自局部 canonical 值。
- 依赖方向：`ingestion_runtime.py:121-127` 已 import `docling_upload_service` 的身份/上传规则；两条 workflow 已 import `build_material_ids`；无反向依赖。

结论：单一函数调用图成立，消费者穷举无遗漏，无绕过入口。

### 5. 测试与覆盖率/README 门槛 —— 满足裁决口径

- 白名单 8 项与两个回归文件全部存在（`tests/fins/test_docling_upload_service.py`、`test_fins_ingestion_runtime.py`、`test_sec_pipeline_upload_material_stream.py`、`test_cn_pipeline.py`、`test_fins_ingestion_tools.py`、`tests/fins/test_fins_direct_stream.py`、`tests/cli/test_fins_commands.py`）。
- 现有用例均为 `MATERIAL_OTHER`（两 stream 测试实查无小写/带空格用例），捕获不到 raw 分叉；plan 新增 `" material_other "` 用例是正确 delta（slice 6）。
- slice 4 避免 digest 字面值当 public contract、slice 5 「测试真实 request/record contract，不以 fake 内部字段替代结论」符合 AGENTS.md 测试约束。
- coverage 口径与裁决一致：逐**实际改动**生产 `.py` 文件 `--cov` 单文件 >=80%，基线先行、原始输出、不用总包均值抵扣、不足扩测、失败如实报未完成（plan 第 38 行）；AGENTS.md 阈值为单文件 >=80%，一致。
- venv 锁定：本 checkout 实查无 `.venv`、`/opt/homebrew/bin/python3.11` 为 3.11.15（`python3 -V` 实测 3.11.15），与 plan 第 37 行一致；`dayu.__file__` 须指本 checkout 的要求正确防串环境。
- README 门槛：`dayu/fins/README.md` 命中触发规则（Fins material form 公共契约变化）已列入白名单第 8 项并授权实施时更新；根 README 条件更新；`tests/README.md`/`dayu/README.md` 预判不变但留「若职责确命中，先写明白名单再改」出口——符合裁决「不把扩白名单理解成重复征求授权」。

## Assumptions tested（本轮独立重证摘要）

| # | plan 声称 | 重证结果 |
| --- | --- | --- |
| 1 | `build_material_ids` 用 `strip().upper()` 写 ID seed，两类空白抛既有 `ValueError` | **属实**（`docling_upload_service.py:1842-1848`，seed 顺序 `:1849-1854`，SHA-1、`mat_` 前缀不变） |
| 2 | 两市场五投影点送 raw form | **属实**（行号见上文第 4 节） |
| 3 | prepared mutation 保存传入 form，发布为 `SourceDocumentUpsertRequest.form_type` | **属实**（`:529/:547/:610/:1089`） |
| 4 | storage `:1771` 写 `req.form_type or merged_meta.get("form_type")`；manifest 仅 meta 投影 | **属实**；material 显式非空恒胜出，fallback 为死分支 |
| 5 | summary/runner/producer 消费同一归一化 request | **属实**（`:3672/:3869/:4686` → `:4745`；summary `:7781-7845` 读归一化 request） |
| 6 | `FinsUploadMaterialRequest.form_type: str \| None = None` | **属实**（`:1567`） |
| 7 | tool 入口 `form_type=_required_text(...)` 构造请求经 runtime admission | **属实**（`upload_tools.py:351-355`）；`service/fins_direct.py:341-346` 同 |
| 8 | `sec_pipeline.upload_material` / `cn_pipeline.upload_material` 为纯透传 | **属实**（`sec_pipeline.py:799-860` 转调 `upload_material_stream`，`:918` 转调 `_run_upload_material_stream`） |
| 9 | 读回 API 签名与 workspace_root 语义 | **属实**（见 F2 节） |
| 10 | 环境事实（无本地 `.venv`、3.11.15） | **属实** |
| 11 | 白名单测试文件存在、现有用例全 `MATERIAL_OTHER` | **属实** |
| 12 | processed manifest form 来自 source meta | **属实**（`ingestion_runtime.py:5750/5800-5840`） |

## 新反例主动狩猎（本轮新增攻击面与结论）

1. `**upload_result.payload` 与显式 `form_type=` 的 kwarg 冲突 → 全部 payload 键实查无 `form_type`，不成立。
2. 第二个 material stream 实现（wrapper 分叉）→ `sec_pipeline` wrapper 纯透传，唯一实现，不成立。
3. observation/tool 投影持有 raw request → observed 路径 `_validate_runtime_upload_request` 先于 observation 创建（`:3869`→`_prepare_observed_stream`），producer 持归一化 request，不成立。
4. summary 读 raw request → 实读为归一化 request，不成立。
5. batch/CLI/读侧/processed 等旁路构成第二套 form 事实 → 各为独立语义 owner 或 meta 派生，不成立。
6. `""`（空串）与 `" "`（空白）在 guard 边界分叉导致 durable 时序变化 → 现行为与函数契约错误类型/文案一致（`form_type 不能为空`），且 slice 5 钉「发生边界」，实现被测试约束，不成立为实质缺口。
7. skip/delete 同版数据回退 raw → 局部 canonical 值恒入结果/事件，meta 本就 canonical，同源成立；历史跨代分叉已在第 49 行承接。
8. 读回脚本 `workspace_root` 与 CLI `--base` 布局错位 → `_resolve_workspace_root` 无子目录偏移，生产同构装配，不成立。
9. filing form（`cn_pipeline.py:817 form_type = normalized_period`、`build_cn_filing_ids`）被误并入 material 规则 → plan 明文隔离，且两者确属 filing 语义，不成立。

结论：本轮未发现新的真实可达反例。

## Findings

**无 material findings（0 条）。** 前轮 F1（中）、F2（低）与第二轮 Finding 1（低：历史 raw meta 跨代分叉 + 验收句无豁免）均已在本 SHA 的 plan 中按裁决真实收口，且经本轮代码事实独立重证无文字回退。上述攻击面均未产生可信、可执行、会致 plan 失败的缺口，按 finding 规则不降格凑数。

## Open Questions

1. **admission「有效非空文本」guard 谓词落点**（沿前轮 OQ1，未收敛但已被测试钉住）：plan 要求空白不在 admission 调用函数，admission 需自带空白判定（含 `""` 的口径）。两种等价实现（admission guard 本地判定 / 不可把空白判断下沉进函数后 catch）都行为保持，slice 4/5 可锁。建议实现 gate 用 docstring/行内注释声明该 guard 只是调用条件、不是第二套 usage 分类。不构成阻塞。
2. **slice 7 的断言面措辞精度**：plan 要求断言 awaiting tool 入口「observation/request 投影」与 direct 路径相同，但 `FinsObservationSnapshot`/`FinsUploadResultSummary`/`_upload_result_details` 均无 form 字段（`observation_handle.py:137-152`、`ingestion_runtime.py:1798-1828/6903-6940` 实查）；tool 入口的 form 可见面是底层事件 payload 与结果 JSON。实现 gate 应把断言面钉在「tool 入口跑出的事件流/结果 JSON 的 form 与 direct 路径同值」，避免写出无 form 断言的空测试或 fake 内部字段。不构成阻塞。
3. **stream 顶端规范化与 ticker/market 校验的先后**：plan 只写「在计算 ID、发 started、启动公司批次前」。建议实现放在 ticker/market 校验之后、ID 计算之前（与现状首错优先级一致），消除多非法输入直调时首错漂移。不构成阻塞。

## Residual Risks（含跟踪去向）

1. **历史 raw form 跨代分叉**（裁决已接受的范围风险）：skip/delete 碰历史 raw meta 时新事件/结果 canonical 而旧 meta/manifest 保持 raw。**跟踪**：`fins-material-legacy-identity-seed-disposition` 独立 work unit 裁决 owner 级迁移或全新起算。
2. **单文件 coverage gate 可能阻塞**：`ingestion_runtime.py` 等大文件基线未知，逐文件 >=80% 可能在修复正确时卡住本 work unit。**跟踪**：实现 gate 验证第 2 条（基线先行、不足扩测、失败如实报未完成）；controller 授权实现时知悉「报告阻塞」是合法终态。
3. **storage `:1771` fallback 死分支**：material 路径恒走显式分支；未来绕过 `prepare_upload` 的写入可能复活旧值。**跟踪**：O07/O10 同 owner 串行时顺带核对或独立 storage 整洁性 issue。
4. **读侧既有归一化语义独立**：`read_runtime_helpers` 别名表、`_normalize_form_value`、processed 列表精确匹配过滤对 raw 查询 + canonical 新数据组合不保证命中。**跟踪**：UM read 侧语义既有 owner，不扩本项。
5. **CLI 边界先 strip**：`--forms " material_other "` 进 admission 前已被 `_normalized_text_tuple`（`fins.py:1150-1172`）strip，CLI 配对证明的是 CLI 可见合同（含大小写等价）；空白敏感性由 slice 4/6 单元用例承担。**跟踪**：closeout 解读配对结论时注意即可，无需立顶。
6. **成功信号依赖实施后的真实 CLI 配对**：冻结 A14/A15 只证明旧偏差。**跟踪**：实现 gate 验证第 3 条。

## Final Plan Review Conclusion

**pass-with-risks**

- 停止条件不触发；SHA 与给定值一致。
- 任务指定五项全部核验通过：F1 None/空白四入口失败边界行为保持、无 O05 预支；F2 跨命令读回 API/语义真实可执行；新旧 form 身份边界与裁决一致、历史残余有跟踪去向；单一函数调用图消费者穷举无遗漏、无第二 durable 事实；测试切片、逐文件 coverage、venv 锁定、README 条件白名单均满足 AGENTS.md 与裁决口径。
- 本轮主动攻击九个新面均无可信反例；Findings 为零。剩余为 3 条 open questions（实现精度级，均有测试或措辞一句话可钉）与 6 条已接受/已登记的 residual risks。
- 计划达到 code-generation-ready，可交 implementation agent；建议实现 gate 开工前顺手钉 Open Question 1/2/3 的三处措辞/顺序细节。风险集中于 coverage gate 阻塞可能性（Residual 2），属环境/测试债事实，不是计划缺陷。
