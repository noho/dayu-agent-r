RUNTIME/PROVIDER/MODEL: codex/mimo/gpt-5-codex

CANARY=mimo-b316ea71

# UM-O17-F01 PR4 Plan Re-Review（MiMo 独立 adversarial 复审）

## Reviewed Target and Scope

- 审查对象：`docs/gateflow/upload-material-o17-form-plan-20260929.md`。
- 锁定 SHA-256：`7c818f9dbc2a8276b5a47a49918307efb8437823b6c2cb677b3743b1e34eacd8`；本 checkout 按文件字节独立计算，与任务给定值一致。
- 工作区：`/private/tmp/dayu-upload-o17`；分支 `codex/upload-material-o17`；HEAD `8d8d494fbbce0052372fb1b42097c9f7222cfa28`。
- Binding scope：`docs/gateflow/upload-material-o17-form-goal-20260929.md`。
- 裁决输入：`docs/gateflow/upload-material-o17-plan-review-adjudication-20260929.md`、`docs/gateflow/upload-material-o17-plan-fix-pr4-20260929.md`、上轮 Kimi `docs/reviews/plan-review-20260929-164227.md`。
- 审查方式：按 `$planreview` 做独立反证；只读 plan、goal、裁决、代码、测试与冻结 material 证据。唯一写入为本 review artifact。
- 非目标遵守：未实施 O17/O09/O05，未修改 plan/goal/旧 review/裁决/产品/测试/README，未安装依赖，未 commit/push/PR/merge，未派发子 Agent。
- 文件名使用任务指定的固定名 `plan-review-o17-pr4-mimo-20260929.md`，覆盖通用 timestamp 文件名建议；未另行生成 timestamp artifact。

## Assumptions Tested

1. PR4-F1 已把 O09 `fiscal_year` 1800–2100 校验登记为 `build_material_ids` 的 before-seed 串行集成点，且 O17 不实施该域校验。
2. PR4-F2 已把 tool 断言面改为真实 runner request、确有 `form_type` 的 material 事件流和 pipeline result JSON，不向无 form 字段的 snapshot/summary/details 造字段。
3. `normalize_material_form_type` 只有一个 canonical owner，ID、request、US/CN/HK workflow、结果、source meta 与 manifest 共用同一 canonical 值。
4. O05 的 `None`/空白边界不被 O17 提前改写成新 typed usage，也不改变现有失败类型、时序或 durable 副作用。
5. 合法 padded form 的同 ID 等价性可通过两个隔离 CLI workspace 加独立仓储读回验证，且读回走公共仓储协议。
6. 历史 raw form 跨代分叉归独立 legacy WU，不被 O17 fallback 或通过测试固化。
7. 实施门槛明确覆盖逐实际改动生产文件 coverage、pyright 和 README 职责检查。

## First-Hand Evidence

### PR4-F1：O09 同点串行成立

- `docs/reviews/upload-material-um-o09-oracle-adjudication.md` 明确 owner 为 `dayu/fins/pipelines/docling_upload_service.py` 的 material identity builder/validator，合法域为 1800–2100（含端点），状态为尚未实施。
- 当前 `build_material_ids` 位于 `dayu/fins/pipelines/docling_upload_service.py:1820`；`fiscal_year` 在 `:1850-1851` 转成字符串进入 seed，当前无域校验。
- plan `:48` 明确 O09 与 O17 同属该 owner，校验必须发生在 ID seed 前；plan `:25` 同时明确 O17 不顺带实施 O09。
- 结论：O09 的 owner、域、before-seed 插入点和未实施边界均有一手证据，PR4-F1 计划内容闭合。

### PR4-F2：真实 form 断言面成立

- plan `:30` 指向 `tests/fins/test_fins_ingestion_tools.py`，要求断言 runner 实际收到的准入后 material request，并只核对真实事件/result JSON 中存在的 `form_type`。
- `FinsUploadRunner.run_upload` 的真实 request contract 位于 `dayu/fins/ingestion_runtime.py:1963-1971`；direct 与 legacy job 均把已归一化 request 原样交给 runner（`:4528-4530`、`:5012-5014`）。
- US material started/result JSON 的 `form_type` 位于 `dayu/fins/pipelines/sec_upload_workflow.py:509,582,610`；CN/HK 对应字段位于 `dayu/fins/pipelines/cn_pipeline.py:1125,1198,1226`。
- `FinsObservationSnapshot` 只有 handle/status/message/result/error/retry 字段，无 form（`dayu/fins/ingestion/observation_handle.py:137-153`）。
- `FinsUploadResultSummary` 与 `to_json_summary()` 无 form（`dayu/fins/ingestion_runtime.py:1798-1828,1894-1941`）；`_upload_result_details` 也只投影 status/count/failure/document（`:6903-6940`）。
- 结论：plan 已明确排除三个无 form 对象，PR4-F2 不会诱导造字段或空断言。

### Canonical owner 与 published fact 链

- 当前唯一 raw canonical 化点是 `build_material_ids` 内的 `form_type.strip().upper()`（`dayu/fins/pipelines/docling_upload_service.py:1842`）。
- plan `:13-16` 新增唯一 `normalize_material_form_type(form_type: str) -> str`，由 `build_material_ids`、material request admission、US/CN/HK material stream 共用；storage/manifest/result 明确禁止二次重算。
- request contract 允许 `form_type: str | None`（`dayu/fins/ingestion_runtime.py:1541-1578`）；`_normalize_upload_request` 当前只替换 action（`:7694-7714`），plan 只对有效非空文本替换 canonical form。
- `prepare_upload` 把显式 `form_type` 写入 prepared mutation（`dayu/fins/pipelines/docling_upload_service.py:541-556`），发布为 `SourceDocumentUpsertRequest.form_type`（`:1085-1097`）。
- storage 以显式 request form 写 `merged_meta["form_type"]`（`dayu/fins/storage/_fs_source_document_core.py:1765-1772`）；manifest 仅由完整 source meta 投影（`dayu/fins/domain/document_models.py:1047-1085`）。
- 公共跨命令读回路径真实存在：`FsSourceDocumentRepository.list_source_document_ids`（`dayu/fins/storage/fs_source_document_repository.py:760-776`）和 `get_source_meta`（`:524-547`），底层从 published tree 读取。
- 冻结 UM-A14 一手记录确认历史偏差：`command.json` 的 `--forms` 为 `" material_other "`，稳定 ID 为 `mat_294e14256d78c8df2897693749d9be85160d42cd`；对应 meta 与 `material_manifest.json` 的 `form_type` 均为 `material_other`。该证据只证明旧偏差，不冒充当前 HEAD 修复证据。

### O05、历史 raw、coverage 与 README

- plan `:14,25,46` 明确 `None`/空白不进入 `str` canonical 函数，不新增 typed usage，不改失败时序；O05 后续在 admission owner 前置 typed 拒绝。
- `ProductionFinsUploadRunner._run_material_upload` 当前对 `None` form/name 先抛 `ValueError`（`dayu/fins/service_runtime.py:223-226`）；空白 form 仍会到 identity builder 的既有 `ValueError("form_type 不能为空")`。plan 没有把这两条提前搬到 O17。
- plan `:42,50` 把验收限定为修复后新写/同版 material，并把历史 raw meta 在 skip/delete 后的跨代分叉归 `fins-material-legacy-identity-seed-disposition`，不写兼容 fallback 或错误通过测试。
- plan `:38` 对实际改动的每个生产 `.py` 文件单独要求 >=80%，同一 Python 3.11 checkout 先测基线再扩测，并运行 pyright；未把总体均值或“报告阻塞”当完成。
- plan `:31,40` 已读取 README 职责边界：`dayu/fins/README.md` 命中 material 公共契约；根 README 仅在用户可见 CLI 行为变化时更新；`tests/README.md` 只覆盖测试层级/运行/维护规则，本项未命中；`dayu/README.md` 只覆盖跨包边界，本项未命中。

## Findings

### 01-未修复-低-批量 material form 分类仍存在独立 strip/upper 边界

- **位置**: plan `:13-16,24-33` 的唯一 canonical owner 与白名单；`dayu/fins/upload_batch.py:799-814`；`dayu/cli/commands/fins.py:1193-1208`。
- **问题类型**: 语义所有权 / 契约缺失 / 最佳实践偏离
- **当前写法**: plan 只要求 `docling_upload_service.py` 新增唯一 `normalize_material_form_type`，并让 request admission 与 US/CN/HK workflow 复用；没有明确处理 `upload_filings_from` 的 batch material form 分类链。该链的 `_validated_material_form` 自行执行 `value.strip().upper()` 后校验封闭集合，CLI `_single_batch_material_form` 也先 `.upper()`，最终把 `UploadBatchMaterialEntry.form_type` 投影为 `upload_material --forms`。
- **反例/失败场景**: 后续若 canonical form 规则调整为处理特定 Unicode 空白、长度或别名，batch override 与 filename routing 可能接受/拒绝或生成不同 form，而单条 `upload_material` 又按新 canonical owner 处理；同一个 material form 语义在生成脚本和实际上传之间漂移。当前值域虽只有三个 batch form，但漂移会直接进入用户可见 argv 与 typed batch fact。
- **为什么有问题**: `upload_batch.py` 模块自述是 material 路由业务语义 owner，`UploadBatchMaterialEntry.form_type` 又是后续 `upload_material` 的显式输入。AGENTS.md 要求格式化规则与派生值只有一个 owner；仅按函数名搜索“唯一”不能证明该边界没有第二套规范化。
- **直接证据**: `dayu/fins/upload_batch.py:23-27,217-232,799-814` 明确 material form typed fact 与独立 normalization；`dayu/cli/commands/fins.py:387-418` 把该值机械投影成 `--forms`。plan 的非改动白名单没有列出这条链，也没有说明它是独立 routing input classifier 而非 form canonical producer。
- **影响**: 实施 Agent 可能误改 batch owner，或保留第二套规范化后仍以“只有一个 `normalize_material_form_type` 函数”宣称通过；未来 form 规则演进会出现 batch 与单条上传不一致。
- **建议改法和验证点**:
  - 在 plan 的 owner 边界中明确区分 batch filename routing/封闭集合校验与 form 文本 canonicalization。
  - 让 `_validated_material_form` 在封闭集合校验前调用唯一 canonical 函数，或明确证明该 batch 值只属于 routing selector、不得作为 form canonical producer，并补一条 batch typed entry -> generated `--forms` 的同值断言。
  - 同步决定 CLI `_single_batch_material_form` 是保留机械 parser 还是删除重复 `.upper()`；不得由两层各自修改同一 form 语义。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

1. tool 测试如何在不复制 workflow 逻辑的前提下捕获真实 US/CN/HK `UploadMaterialEvent` 与 pipeline result JSON；plan 已限定断言字段，但未指定 capture seam、exact fixture 与事件顺序。
2. 只读读回脚本的具体路径、Python 3.11 解释器、`FsSourceDocumentRepository(..., create_directories=False)` exact argv 与输出 artifact 命名留给实施 gate；必须遵守临时脚本只放 `workspace/tmp/`。
3. batch material form 的独立 routing owner 是否明确排除在 O17 canonical producer 之外，还是改为复用唯一函数；这决定 Finding 01 是 plan 一句话边界补充还是小范围白名单扩展。

## Residual Risks

1. 历史 raw form 在 skip/delete 后仍可能与新事件/结果跨代分叉；跟踪到 `fins-material-legacy-identity-seed-disposition`，O17 不迁移旧数据。
2. `ingestion_runtime.py`、`cn_pipeline.py` 等大文件逐文件 >=80% 基线可能不足；实施 gate 必须扩测或如实报告未完成。
3. `_fs_source_document_core.py:1771` 仍存在 `req.form_type or merged_meta.get("form_type")` 的历史 fallback；O17 新写路径应始终提供显式 canonical form，但 storage 清理性问题可由后续 owner WU 跟踪。
4. read-side `_normalize_form_value` 与 processed 列表过滤是独立读侧语义，不能拿 raw 查询命中率替代 source meta 的 owner 级 form 断言。
5. CLI `_single_optional_form` 会在 admission 前 strip 用户空白；真实 CLI 配对证明用户输入与最终 published fact，不单独证明 raw padded 字符串到达 runner。slice 4/5/6 的直接入口测试承担该边界。

## Command and Validation Disclosure

- 已用 `shasum -a 256` 核对目标 plan，结果为锁定 SHA；HEAD/分支分别为 `8d8d494fbbce0052372fb1b42097c9f7222cfa28` / `codex/upload-material-o17`。
- 已用 `rg --files` 确认 AGENTS、goal、总控、PR4 fix、Kimi review、代码、测试、README 与冻结证据路径；目标 review 路径写入前记录为 `TARGET_PATH_FREE`。
- 本 review 为只读审查，未运行测试或 pyright；没有产品代码修改，因此没有实现 gate 的测试/覆盖率/pyright 结果。
- 失败命令如实披露 3 条：一次 zsh glob `evidence/UM-A14*` 因路径不存在而 exit 1；一次 `jq .items[]` 读取 material manifest 因真实结构为 `documents` 而 exit 5；一次窄化 `rg | rg` 因第二段无匹配而 exit 1。三条均未用于结论，随后分别用 `rg --files`、`.documents[]` 和单段检索完成核证。
- 其余用于结论的命令 exit 0；预期无目标 review 匹配由 awk 内部记录 `TARGET_PATH_FREE`，未依赖失败的无匹配退出码。

## Final Plan Review Conclusion

**pass-with-risks**

- SHA、goal、O09 before-seed 同点、PR4-F2 真实断言面、O05 边界、历史 raw 独立 WU、跨命令仓储读回、逐文件 coverage/pyright/README 均有直接证据。
- 停止条件未触发：目标 form owner 在 ID/request/market/published fact 主链上可实证，事件字段真实存在，O09 同点可实证。
- Finding 01 是唯一低风险边界缺口：batch material form routing 仍有独立 strip/upper。它不推翻主链的 canonical 方向，但在实施前应明确其 owner 处置，不能仅以新增函数名数量宣称全系统唯一。
- 计划总体达到可实施准备度；建议 controller 将 Finding 01 作为一句话边界裁决或最小白名单补充后再进入 implementation gate。
