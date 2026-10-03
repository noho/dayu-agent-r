# Plan Re-Review：UM-O17-F01 material form canonical 实施计划 PR4 修订版（Kimi 独立 adversarial 复审）

RUNTIME/PROVIDER/MODEL: codex/kimi/gpt-5-codex

CANARY=kimi-84ae6c04

- 审查对象：`docs/gateflow/upload-material-o17-form-plan-20260929.md`，SHA-256 `7c818f9dbc2a8276b5a47a49918307efb8437823b6c2cb677b3743b1e34eacd8`（本 checkout 以 `shasum -a 256` 独立核验，与任务锁定值一致）。基线 HEAD `8d8d494fbbce0052372fb1b42097c9f7222cfa28`，分支 `codex/upload-material-o17`；`git status --porcelain` 实证工作树仅含未跟踪 gateflow/review 文档，无产品改动。
- 工作区：`/private/tmp/dayu-upload-o17`（隔离 checkout）。复审本机时间 2026-09-29 17:32 CST。
- 审查方式：planreview 独立 adversarial 复审；全程只读代码、冻结证据与文档；唯一新增文件为本 artifact；不修改 plan/goal/产品/测试/README/旧 review/裁决；不实施 O17/O09/O05；不安装依赖；不 commit/push/PR/merge；不派发子 Agent。
- 审查重点（任务指定）：重点反证 PR4-F1（O09 fiscal_year 同 `build_material_ids` before-seed 串行集成，O17 不偷做域校验）与 PR4-F2（slice 7 锁 tool 真实 runner request/事件/结果 JSON form 断言，不对无 form 的 snapshot/summary 造字段）；兼审唯一 `normalize_material_form_type`、O05 `None`/空白边界、合法 padded form 跨命令读回、历史 raw 独立 WU、逐文件 coverage/README。
- 依据文档：
  - Goal Confirmation（binding scope contract）：`docs/gateflow/upload-material-o17-form-goal-20260929.md`。
  - 总控裁决：`docs/gateflow/upload-material-o17-plan-review-adjudication-20260929.md`（含 PR4-F1/F2 accepted/未修复记录与 Sol PR4 候选核验结论）。
  - Sol PR4 修复记录：`docs/gateflow/upload-material-o17-plan-fix-pr4-20260929.md`。
  - 前轮 Kimi 复审（旧 SHA `37d1c13e...`，自报 failed，不计有效第二路）：`docs/reviews/plan-review-20260929-164227.md`。
  - MiMo 同版（旧 SHA）第三次 review：`docs/reviews/plan-review-o17-rereview3-mimo-20260929.md`。
  - O09 用户裁决（本 checkout 存在）：`docs/reviews/upload-material-um-o09-oracle-adjudication.md`（2026-09-16，fiscal_year 1800-2100 含端点，同 owner，尚未实施）。
  - O17 用户裁决（本 checkout 缺失，按前轮同法从主工作区只读核对，内容支持 goal 引用）：`/Users/leo/workspace/dayu-agent-r/docs/reviews/upload-material-um-o17-oracle-adjudication.md`（2026-09-28，用户原文「处理form类别的代码做成一个函数，其它地方调用，防止逻辑漂移」）。
  - 冻结证据 root（只读）：`/Users/leo/workspace/.dayu-cli-ci/upload-material-calibration-20260818-mNeTId`。
- 独立重证方式：不沿用前轮 Kimi/MiMo 结论，对 PR4 两处修订点与五项兼审点重新读当前 HEAD 代码与冻结一手证据（行号为本 HEAD 实读）。

## 停止条件裁决（先行结论）

- 计划 SHA-256 与任务锁定值一致；goal、总控裁决、Sol PR4 记录、前轮 Kimi review 均在。
- 唯一 form owner 可实证：`normalize_material_form_type` 在当前 HEAD 全库无匹配（预期无匹配，产品未实施）；plan 指定 `docling_upload_service.py` material identity builder/validator 边界新增唯一公开纯函数，`ingestion_runtime.py:121-127` 已有从该模块导入身份/上传规则的先例，依赖方向合法，无反向依赖反例。
- 事件字段可实证：US `sec_upload_workflow.py:509`（started payload）、`:582`（成功结果）、`:610`（失败结果）与 CN/HK `cn_pipeline.py:1125`、`:1198`、`:1226` 均含 `form_type`。
- O09 同点可实证：O09 裁决明确 owner 为 `docling_upload_service.py` material identity builder/validator 且要求身份生成前完成校验；当前 `build_material_ids`（`:1820-1856`）对 `fiscal_year` 仅在 `:1850-1851` `str()` 入 seed，无 1800-2100 域校验，O09 未实施属实。
- **不触发停止条件**，正常出具审查结论。

## PR4-F1 专项核验：O09 before-seed 串行集成登记 —— 闭合

- **plan 文本实证**：串行集成段登记「O09-F01 的 `fiscal_year` 1800–2100（含端点）域校验与 O17 同属 `build_material_ids` 的 material identity builder/validator，必须在生成 ID seed 前完成。实施 gate 按最终 HEAD 复核 O09 与 O17 的合入先后、该函数的校验位置及原 seed 拼接顺序，再集成各自改动；O17 不实施、重写或预支 O09 的财年域规则」；slice 2 不顺带实施清单同步含 O09（「只改有效 form 投影，不顺带实施 O05/O07/O09/O10」）。
- **代码事实实证**：`build_material_ids`（`docling_upload_service.py:1820-1856`）当前对 form 做 `strip().upper()`（`:1842`）、空白 form 抛既有 `ValueError("form_type 不能为空")`（`:1845-1846`）、seed 顺序为 form/name/fiscal_year/period（`:1849-1853`）、SHA-1 + `mat_` 前缀（`:1854-1855`）；`fiscal_year: int | None` 仅 `str()` 入 seed，无任何域校验。O09 裁决文档（本 checkout 实读）要求同 owner、身份生成前校验、1800-2100 含端点、尚未实施，与 plan 登记一致。
- **反证尝试**：检查 plan 全文是否仍残留 O17 自行做 fiscal 域校验的暗示——函数 owner 段「不新设 form 枚举、长度或业务别名」「保持原 seed 拼接顺序、SHA-1、`mat_` 前缀、name 和 fiscal 字段的现有独立含义」、slice 4「断言 identity builder 对空白 form 与空白 material name 仍分别抛出既有 `ValueError`」「name/fiscal seed 不受本项改动」，均未把 fiscal 域规则纳入 O17 实施面。无反例。
- **裁决对照**：总控裁决 PR4-F1 要求「补 O09 依赖登记及实施前按最终 HEAD 复核，不在 O17 偷做 fiscal 校验」，plan 两处文本精确对应。**结论：PR4-F1 计划内容已修，闭合。**

## PR4-F2 专项核验：tool 断言面锁真实字段 —— 闭合

- **plan 文本实证**：slice 7 写「awaiting tool 入口断言 runner 实际收到的准入后 material request 的 canonical `form_type`，并沿真实 US/CN/HK material 事件流和 pipeline 结果 JSON 中确有的 `form_type` 字段核对与 direct 路径同值；使用能执行 material 路径的 runner，不复制函数逻辑到 tool provider。`FinsObservationSnapshot`、`FinsUploadResultSummary` 和 `_upload_result_details` 均无 form 字段，不作为 form 断言对象，也不造字段或写空断言」。
- **runner 准入后 request 链实证**：tool 入口 `dayu/fins/tools/upload_tools.py:103` 调 `runtime.prepare_observed_upload(request, ...)`；observed 入口 `ingestion_runtime.py:3869` 在 observation 创建前经 `_validate_runtime_upload_request`；material 分支 `:4745` 调 `_normalize_upload_request`（`:7694-7715`，当前仅 `replace(request, action=action)`，plan 改为有效值时同函数替换 form）并返回准入后 request；`:4706-4711` 以 `normalized_request` 提交 `_run_upload_job`，`:5012` `self.upload_runner.run_upload(request, ...)` 把同一对象交给 runner。「runner 实际收到的准入后 material request」断言目标真实存在。
- **事件/结果 JSON 有 form 实证**：US started payload `sec_upload_workflow.py:509`、成功结果 `:582`、失败结果 `:610`；CN/HK started payload `cn_pipeline.py:1125`、成功结果 `:1198`、失败结果 `:1226`，均为 `form_type` 字段。
- **无 form 投影排除实证**：`FinsObservationSnapshot`（`dayu/fins/ingestion/observation_handle.py:137-152`）字段为 handle/status/message/result/error_kind/retry_after_seconds，无 form；`FinsUploadResultSummary`（`ingestion_runtime.py:1798-1828`）及其 `to_json_summary`（`:1894` 起）字段无 form；`_upload_result_details`（`:6903-6945`）由该 summary 构造 details，无 form detail。plan 排除清单与代码事实一一对应。
- **反证尝试**：检索是否还有其它 LLM-facing tool 投影带 form 而 plan 未覆盖——`_upload_context_request_progress_payload` 与 summary renderer 均以准入后 request 为输入（plan owner 段「不在 summary renderer 单独改写」），tool 侧无独立 form 投影面。无反例。
- **裁决对照**：总控裁决 PR4-F2 要求「测试应锁真实事件流/结果 JSON 的 form 值与 runner 接收的准入后 request 值；不得给 observation snapshot 造字段或写空断言」，slice 7 文本精确对应。**结论：PR4-F2 计划内容已修，闭合。**

## 五项兼审核验

### 1. 唯一 `normalize_material_form_type` —— 成立

- 当前 HEAD 全库无该函数（rg 无匹配，预期内）；plan 指定唯一 owner（`docling_upload_service.py` material identity builder/validator 边界），四入口（`build_material_ids`、`_normalize_upload_request`、US `run_upload_material_stream`、CN/HK `CnPipeline.upload_material_stream`）共用同一函数，禁止消费者复制 `.strip().upper()`。
- 同模块 `:1920-1946` 的 filing ID builder 自带 `form_type.strip().upper()`，plan 明确「与 `build_cn_filing_ids`、`build_sec_filing_ids`、SEC form parser、download form filter 隔离，不将 material 类别解释为 filing form」，不构成第二 owner。
- durable 链实证：`prepare_upload` 校验并存 form（`:442-443`、`:529`/`:547`）、发布为 `SourceDocumentUpsertRequest.form_type`（`:610`、`:1089`）；storage `merged_meta["form_type"] = req.form_type or merged_meta.get("form_type")`（`_fs_source_document_core.py:1771`）；`MaterialManifestItem.from_source_meta`（`dayu/fins/domain/document_models.py:1047-1078`）仅从 meta 投影 `form_type`，全链单一真源方向成立。

### 2. O05 `None`/空白边界 —— 成立

- `FinsUploadMaterialRequest.form_type: str | None = None`（`ingestion_runtime.py:1541` 类定义体内），`None` 可表示；plan 仅对有效非空文本调用 canonical 函数，`None`/空白原样留在 request 沿现有后续边界失败，不改失败类型、时序或 durable job 副作用，不预支 O05 typed usage。
- 现有失败边界实证：空白 form 在 `build_material_ids:1845-1846` 抛既有 `ValueError`；`None` 沿 stream 进入同一 builder 的现存行为保持原样（O17 不触碰该路径）。slice 5 锁定各入口现有错误类型/边界/副作用，防止无意改写。slice 2 已把 O05 列入不顺带实施清单。

### 3. 合法 padded form 跨命令读回 —— 方案可执行

- 公共读回协议实证：`list_source_document_ids(ticker, source_kind)`（`repository_protocols.py:1244`；FS 实现 `fs_source_document_repository.py:760`）与 `get_source_meta(ticker, document_id, source_kind)`（`repository_protocols.py:1044`；FS 实现 `:524`、核心 `:557`）均存在且为公共 contract；plan 验证第 3 条要求以 `FsSourceDocumentRepository(workspace_root, create_directories=False)` 另起只读进程读回，禁止从文件路径或 ID 字符串推断 form，符合仓储协议约束。
- 冻结 A14 一手核对：`evidence/actions/UM-A14-form-case-space-normalization/command.json:11-12` 输入为 `" material_other "`；同目录 `key-json-artifacts.json:58`（meta）与 `:85`（manifest）`form_type` 均为 `material_other`；`workspaces/identity/form-normalization/portfolio/AAPL/materials/id-01bf6b001045d2029873218bd04e13c4f131d475cf7b8457039b14a5abd0aa99/meta.json:22` 与 `material_manifest.json:11` 同为 `material_other`；`observed-behavior.md:152-158` 记录「form ID 按 MATERIAL_OTHER 生成，source meta 却持久化原始 lowercase」分叉。稳定 ID `mat_294e14256d78c8df2897693749d9be85160d42cd` 在 key-json/meta/manifest 三处一致。旧偏差属实，且当前 HEAD 代码路径仍可复现该分叉（动机成立）。
- O17 用户裁决（主工作区只读核对）要求「真实 CLI 在隔离 workspace 补跑 `" material_other "` 与 `MATERIAL_OTHER`，核对 canonical 身份、meta/manifest、事件/summary 及跨命令读取一致……不以单次 SHA-1 推算替代」，plan 验证第 3 条逐项对应。

### 4. 历史 raw 独立 WU —— 成立

- plan 串行集成段与验收句明示：验收限「本修复后新写、或此前已由同版代码写入的 material」；历史已发布 raw form 在 skip/delete 后不满足同源验收，本项不宣称修复，归 `fins-material-legacy-identity-seed-disposition` 独立 WU 裁决 owner 级迁移或全新起算；不在 read/事件/summary/结果层加 fallback，也不写测试把跨代不一致固化为通过合同。与总控裁决「不接受把旧不一致写成 owner 级通过测试」一致。该跟踪句柄已在总控裁决与两轮 review 中登记。

### 5. 逐文件 coverage / README —— 成立

- 验证第 1 条锁本 checkout Python 3.11 环境（当前无本地 `.venv`，要求建立/确认后以 `dayu.__file__` 指向 `/private/tmp/dayu-upload-o17/dayu/__init__.py` 为判据，不拿其它 checkout 结果冒充）；验证第 2 条按**实际改动的每个生产 `.py` 文件**逐一 `pytest --cov=<对应模块> --cov-report=term-missing` 核对 `>=80%`，不用总包均值抵扣，失败如实报未完成；pyright 对照基线不得新增/扩散/掩盖。与总控裁决 coverage 口径一致。
- README：slice 8 条件白名单（`dayu/fins/README.md` 已确认职责命中，实施时更新；根 `README.md` 仅当 CLI 用户可见说明变化时更新；`tests/README.md`/`dayu/README.md` 职责未命中不机械同步），验证第 4 条要求按 AGENTS.md 触发规则先读目标 README 更新约束；本 plan gate 不改 README。符合约束。

## Assumptions Tested

1. PR4 两处修订为对旧 SHA `37d1c13e...` 的最小文字修订、其余条款未回退——通过全文通读新 SHA 文件并与总控裁决/Sol PR4 修复映射逐条对照验证，唯一 owner/O05/历史 raw/coverage/README 条款均在，未发现回退。
2. O09 与 O17 的集成冲突面仅限 `build_material_ids` before-seed 插入点——代码实证该函数是当前唯一 material seed 构造处，O09 裁决指定同 owner；两条改动按最终 HEAD 复核合入先后的安排可执行。
3. tool 断言面（runner request + 事件流 + 结果 JSON）足以证明 canonical 同源而不需给无 form 投影造字段——逐字段实证三类无 form 投影与三处有 form 事件/结果。
4. 跨命令读回不依赖文件系统路径推断——公共仓储协议方法实证存在。
5. 历史 raw 范围风险已被裁决接受且有登记去向——plan/裁决/前轮 review 三处文本互证。

## Findings

本轮**零新 finding**。任务指定的两个重点反证对象 PR4-F1、PR4-F2 均以 plan 文本 + 当前 HEAD 代码事实 + 裁决要求三方对照闭合；五项兼审点全部成立。前轮低 finding（O09 未登记、tool 断言面指向无 form 投影）正是本轮修订对象，已修。

## Open Questions（实施精度级，不阻塞，沿用前轮并仍适用于本 SHA）

1. admission「有效非空文本」guard 的精确判定（如 `isinstance(form_type, str) and form_type.strip()`）是实现级调用条件，实施时以 docstring/行内注释声明其非公开 usage 分类器语义，避免被读成 O17 私设分类规则（前轮 open question 1，仍适用）。
2. stream 顶端规范化与 ticker/market 校验的首错顺序：现状 SEC 为 market 校验（`sec_upload_workflow.py:470-471`）先于 `build_material_ids`（`:475`），实施应保持该首错优先级（前轮 open question 2，仍适用）。
3. 验证第 3 条只读读回脚本的存放与执行形式未指定：按 AGENTS.md 目录约束临时脚本仅放 `workspace/tmp/`，实施时应明确脚本路径、exact argv、退出码与读回 JSON 的 artifact 化方式（前轮 open question 3，仍适用）。

## Residual Risks（含跟踪去向，沿用前轮并经本轮复核仍成立）

1. **历史 raw form 跨代分叉**：skip/delete 碰历史 raw meta 时新事件/结果 canonical 而旧 meta/manifest 保持 raw（裁决已接受的范围风险）。**跟踪**：`fins-material-legacy-identity-seed-disposition` 独立 WU。
2. **单文件 coverage gate 可能阻塞**：`ingestion_runtime.py`、`cn_pipeline.py` 等大文件逐文件 >=80% 基线未知。**跟踪**：实施 gate 按 plan 验证第 2 条基线先行、不足扩测、失败如实报未完成。
3. **storage `_fs_source_document_core.py:1771` 的 `or` fallback 死分支**：material 路径恒走显式分支；未来绕过 `prepare_upload` 的写入可能复活旧值。**跟踪**：O07/O10 同 owner 串行时顺带核对，或独立 storage 整洁性 issue。
4. **读侧既有归一化语义独立**：`read_runtime_helpers` 别名表、`_normalize_form_value`、processed 精确匹配过滤对 raw 查询 + canonical 新数据组合不保证全部命中。**跟踪**：UM read 侧语义既有 owner，不扩本项。
5. **CLI 边界先 strip**：`--forms " material_other "` 进 admission 前已被 CLI strip，CLI 配对证明 CLI 可见合同；admission 级空白敏感性由 slice 4/5/6 承担。**跟踪**：closeout 解读配对结论时注意。
6. **成功信号依赖实施后的真实 CLI 配对**：冻结 A14/A15 只证明旧偏差；O17 裁决要求真实 CLI 配对证据，不以单次 SHA-1 推算替代。**跟踪**：实施 gate 验证第 3 条。

## 探索命令与退出状态披露

- 全部命令按任务要求设计为自身 exit 0；预期无匹配一律程序内记录：`rg -n "normalize_material_form_type" --type py` → 无匹配（产品未实施，符合预期）；`rg -n "UM-O17|upload-material" MEMORY.md`（本机记忆登记）→ 无匹配；`rg -n "submit|upload_material|FinsUploadMaterialRequest|run_upload" dayu/fins/tools/upload_provider.py` → 无匹配（upload 提交逻辑在 `upload_tools.py`，随后核实）。
- 预期失败已记录：`ls docs/reviews/upload-material-um-o17-oracle-adjudication.md` → exit 1 `No such file or directory`（本 checkout 缺失，与 plan 声明一致；随后从主工作区只读核对存在且内容支持 goal 引用）；`ls docs/reviews/plan-review-o17-pr4-kimi-20260929.md` → exit 1（写入前确认 PATH_FREE）。
- 失败命令如实披露 3 条：探索性 `rg -n "upload" dayu/fins/ingestion/tools.py` exit 2（路径猜测错误，`No such file or directory`；真实路径为 `dayu/fins/tools/upload_tools.py`，经 `rg --files dayu/fins` 定位后完成核验），该失败未用于任何结论；首次 `apply_patch` 因缺 `*** End Patch` 标记校验失败，第二次因本机 apply_patch 实现要求新增行带 `+` 前缀而校验失败，两次均未产生任何文件写入，第三次以正确语法写入成功。
- 未运行任何测试、pyright、依赖安装或写产品操作；未修改 plan/goal/产品/测试/README/旧 review/裁决；未 commit/push/PR/merge；未派发子 Agent；未使用 Goal tool 与进程列表。

## Final Plan Review Conclusion

**pass-with-risks**

- 停止条件不触发；plan SHA-256 `7c818f9dbc2a8276b5a47a49918307efb8437823b6c2cb677b3743b1e34eacd8` 与任务锁定值一致；基线 HEAD 与分支属实。
- PR4-F1（O09 before-seed 串行集成登记，O17 不偷做域校验）与 PR4-F2（tool 断言面锁真实 runner request/事件/结果 JSON form，不对无 form 的 snapshot/summary/details 造字段）均以直接证据闭合；总控裁决的两项 accepted 修订要求在 plan 文本中精确落地。
- 五项兼审全部成立：唯一 `normalize_material_form_type` owner 与依赖方向合法；O05 `None`/空白边界不预支；合法 padded form 跨命令仓储读回方案可执行且有冻结 A14 一手对照；历史 raw 归 `fins-material-legacy-identity-seed-disposition` 独立 WU；逐文件 coverage 与 README 条件白名单符合裁决口径。
- 本轮零新 finding；3 条实施精度级 open questions 与 6 条已登记 residual risks 沿用前轮，建议在实施任务下达时随附。
- 计划达到 code-generation-ready；本复审仅覆盖 plan gate，不构成实施授权；下一 gate 按总控流程裁决。
