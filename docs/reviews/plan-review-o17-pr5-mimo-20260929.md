RUNTIME/PROVIDER/MODEL: codex/mimo/gpt-5-codex

CANARY=mimo-d2f92a18

# UM-O17-F01 PR5 Plan Re-Review（MiMo 独立 adversarial 复审）

## Reviewed Target and Scope

- 审查对象：`docs/gateflow/upload-material-o17-form-plan-20260929.md`。
- 锁定 SHA-256：`7b37c7279183bf56af2acfe722062f4b768a1f2e868eb96db37721d2578dbe24`；写入本 artifact 前按文件字节再次计算，与任务给定值一致。
- 工作区：`/private/tmp/dayu-upload-o17`；分支 `codex/upload-material-o17`；HEAD `8d8d494fbbce0052372fb1b42097c9f7222cfa28`。
- 复审时间：2026-09-29 17:58:53 CST；时间来自本机系统时钟命令 `date +%Y%m%d-%H%M%S`。文件名按任务指定固定名使用，覆盖 `planreview` 的通用 timestamp 文件名建议。
- Binding scope：`docs/gateflow/upload-material-o17-form-goal-20260929.md`。
- 裁决与修复输入：`docs/gateflow/upload-material-o17-plan-review-adjudication-20260929.md`、`docs/gateflow/upload-material-o17-plan-fix-pr5-20260929.md`、`docs/reviews/plan-review-o17-pr4-mimo-20260929.md`、`docs/reviews/plan-review-o17-pr4-kimi-20260929.md`、`docs/reviews/plan-review-o17-rereview3-mimo-20260929.md`。
- 一手代码范围：真实 batch、CLI 参数解析与 argv 生成、material identity、request admission、US/CN material stream、runner handoff、storage meta、manifest 投影、O09/O05 裁决、测试与 README 约束。
- 审查方式：按 `$planreview` 做独立反证，不沿用前轮 pass 结论；只读 plan、goal、裁决、代码、测试与文档。唯一新增文件为本 artifact。
- 非目标遵守：未实施 O17/O09/O05，未修改 plan/goal/旧 review/裁决/产品/测试/README，未运行实现 gate，未 commit/push/PR/merge，未派发子 Agent。

## Assumptions Tested

1. PR5-F1 后，batch override、filename routing、CLI `--material-forms`、typed entry、生成 `--forms`、runner material request 与 published form 不再存在第二个 canonical producer。
2. `_single_batch_material_form` 能在 `_normalized_text_tuple` 当前会 strip 的情况下返回原始非空候选，并保持空值、多值错误的类型、顺序和发生边界。
3. material stream 的 canonical 化不会把既有 ticker/market 等首错顺序改成 form 首错。
4. O09 的 fiscal_year 域校验仍是 `build_material_ids` 生成 identity seed 前的串行集成点，O17 不实施该规则。
5. PR4-F2 的 tool 测试断言面只使用真实 runner request、确有 `form_type` 的 material 事件/result JSON，不向 snapshot/summary/details 造字段。
6. O05 的 `None`/空白 typed usage 与失败时序不由 O17 提前改变。
7. 历史 raw form 在 skip/delete 后的跨代分叉归独立 legacy WU，不被 O17 fallback 或通过测试固化。
8. 逐实际改动生产文件 coverage、pyright、Python 3.11 import 来源和 README 职责检查仍是实施硬门槛。

## First-Hand Evidence

### Form canonical 主链

- 当前 material identity 只在 `dayu/fins/pipelines/docling_upload_service.py:1842` 对 form 执行 `strip().upper()`，随后参与 SHA-1 seed；`prepare_upload` 把显式 `form_type` 保存为 prepared mutation（`:529-547`），发布时构造 `SourceDocumentUpsertRequest.form_type`（`:1085-1093`）。
- storage 在 `dayu/fins/storage/_fs_source_document_core.py:1765-1772` 合并 source meta，并以显式 `req.form_type` 写入 `form_type`；`MaterialManifestItem.from_source_meta` 只从 source meta 投影同值（`dayu/fins/domain/document_models.py:1047-1078`）。
- batch 当前自行规范化 override（`dayu/fins/upload_batch.py:799-814`），routing table 只产生三个 canonical 字面值（`:82-91`），`_match_material_form` 按既有优先级返回它们（`:500-511`）；typed material entry 保存最终 form（`:217-232`、`:303-307`）。
- CLI 当前把 typed entry 的 `form_type` 机械写入生成命令的 `--forms`（`dayu/cli/commands/fins.py:387-418`）。该 argv 进入 `upload_material` 后由 request admission、runner 和 market stream 消费。
- plan 的 owner 写法把 override 规范化收敛到唯一 `normalize_material_form_type`，同时保留 batch routing 封闭域；filename routing 返回 canonical 字面值而不另设 canonicalizer。该 owner 切分成立，没有 batch/material 双 canonical 真源反例。

### `_normalized_text_tuple` 与 raw 候选

- `_normalized_text_tuple` 对每个逗号 item 先执行 `item.strip()`，空白 item 立即报错，返回值是 `stripped`（`dayu/cli/commands/fins.py:1150-1174`）。
- `_single_batch_material_form` 当前调用该函数后继续 `.upper()`（`:1193-1208`）。因此若实施仍复用该函数，返回值不可能保留两端空白；这是直接代码事实。
- 当前错误顺序是逐输入、逐 item 扫描：遇到空 item 立即报空值；完整扫描后才以 `len(...) > 1` 报多值。`["a", ""]` 会先报空值，`["a", "b"]` 会报多值。
- plan 明确要求 `_single_batch_material_form` 返回“唯一原始非空 item（保留大小写与两端空白）”，并保持空值/多值错误发生时点。该承诺可以由 raw-preserving split loop 执行：只用 stripped 副本判空，append 原始 `item`，保持当前扫描顺序，最后再判 cardinality。
- 但 plan 未点名必须绕开/改写 `_normalized_text_tuple`，也未给出上述顺序矩阵；现有测试只断言 `" esg_report "` 到 owner 的候选为 `"ESG_REPORT"`（`tests/cli/test_upload_filings_from_command.py:197-236`），不能防止实施后悄悄继续 strip。

### O09、PR4-F2、O05 与历史 raw

- O09 裁决把 1800–2100 fiscal_year 域 owner 定义在 `docling_upload_service.py` 的 material identity builder/validator，并要求 identity 生成前校验、零持久化副作用（`docs/reviews/upload-material-um-o09-oracle-adjudication.md:29-41`）。plan 第 54 行保留该 before-seed 串行点且不实施 O09，闭合。
- US material started/成功/失败结果确有 `form_type`（`dayu/fins/pipelines/sec_upload_workflow.py:501-521`、`:576-600`、`:602-628`）；CN/HK 对应字段位于 `cn_pipeline.py:1117-1137`、`:1192-1216`、`:1218-1247`。
- `FinsObservationSnapshot` 没有 form 字段（`dayu/fins/ingestion/observation_handle.py:137-153`）；`FinsUploadResultSummary.to_json_summary()` 与 `_upload_result_details` 也没有 form 字段（`ingestion_runtime.py:1894-1941`、`:6903-6940`）。plan 第 35 行明确排除这些对象，PR4-F2 不会诱导造字段或空断言。
- O05 裁决要求 form/name 缺失或空白在 upload lifecycle 前拒绝，但状态仍是 accepted direction、未实施（`docs/reviews/upload-material-um-o01-o06-oracle-adjudication.md:99-105`）。plan 只对有效文本规范化，`None`/空白保持现有边界，不预支 O05 typed usage。
- 相同 source fingerprint 的旧 source 会在 `prepare_upload` 直接返回 skipped result（`docling_upload_service.py:479-499`），不会重写旧 meta；delete mutation 也不带 form。plan 第 56 行据此把历史 raw meta 跨代分叉归 `fins-material-legacy-identity-seed-disposition`，范围正确。

### Coverage 与 README

- plan 第 44 行要求实际改动的每个生产 `.py` 文件单独 `>=80%`，先取基线、失败不得以“报告阻塞”完成；符合 AGENTS.md 的单文件门槛。
- `dayu/fins/README.md` 的更新约束允许记录当前已实现的 Fins 公共契约与稳定边界（`dayu/fins/README.md:16-24`）。实施后 material form canonical owner 与 batch routing 封闭域会成为当前公共契约，plan 第 37 行条件更新该 README 合理。
- 根 README 面向最终用户且只写当前 CLI 行为（`README.md:9-16`）；若实施只改变内部 owner 而不改变用户可见输入/输出，可不更新。`tests/README.md:1-4` 只在新增测试层级时强制同步，本计划复用现有测试文件；plan 的条件检查口径成立。

## Findings

### 01-未修复-[高]-material stream 顶端规范化可改变既有首错时序

- **位置**: plan `唯一 owner 与数据流` 的“市场入口”段（第 18 行）与 `最小实施切片` 第 3 项（第 29 行）。
- **问题类型**: 状态机漏洞 / 破坏既定失败时序 / 不可直接实施。
- **当前写法**: plan 要求 US `run_upload_material_stream` 与 CN/HK `upload_material_stream` 在“各自 material stream 顶端”生成 canonical 局部值，并在计算 ID、发 started、启动公司批次前调用唯一函数。
- **反例/失败场景**: 直接调用 SEC stream 时同时传入非法 ticker/market 与空白 form。当前先执行 ticker/market 校验（`sec_upload_workflow.py:468-475`），再进入 `build_material_ids` 的 form 空值拒绝；按“顶端”先调用 `normalize_material_form_type` 会先报 form 错误。CN stream 同样先做 ticker/company identity（`cn_pipeline.py:1087-1091`）。多非法输入的首错从 ticker/market 漂移为 form。
- **为什么有问题**: 用户停止条件明确禁止改变既定失败时序。goal 只授权有效 form canonical，不授权改变非法输入的首错优先级；O05 也只允许后续 owner 前置 missing/blank typed usage，不能由 O17 的 stream 位置预支。
- **直接证据**: plan 第 18/29 行的“顶端”落点；`sec_upload_workflow.py:468-480` 与 `cn_pipeline.py:1087-1096` 的当前顺序；`build_material_ids` 在 `docling_upload_service.py:1842-1848` 位于 ticker/market 之后。前轮 MiMo/Kimi 都把“stream 顶端规范化与 ticker/market 先后”留作 open question，PR5 未收敛。
- **影响**: 同一非法请求在直接 market 入口得到不同首错，错误归因和测试契约漂移；实施 agent 按“顶端”实现会违反用户停止条件，按其它位置实现又与 plan 文本冲突。
- **建议改法和验证点**:
  - 把 canonical 调用点明确写成“保持现有 ticker/market 与其它既有首错校验顺序；在这些校验之后、计算 ID、发 started、启动公司批次之前调用”。
  - 增加 direct market stream 的组合非法输入测试，至少锁定非法 ticker/market + 空白 form 仍先报 ticker/market，且没有 started/durable side effect。
  - 明确 `normalize_material_form_type` 在 `build_material_ids` 内的调用位置不得改变 name、period、form 的既有非法值首错关系；若要统一顺序，必须重新做 goal confirmation。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 高

### 02-未修复-[中]-raw CLI 候选契约未钉住 strip helper 与错误顺序

- **位置**: plan `batch 与 CLI 边界` 段（第 17 行）、实施白名单第 5/10 项（第 31/36 行）。
- **问题类型**: 契约缺失 / 测试缺口 / 不可直接实施。
- **当前写法**: plan 要求 `_single_batch_material_form` 只拆分、检查单值/空白并返回唯一原始 item（保留大小写与两端空白），同时保持空值/多值错误发生时点。
- **反例/失败场景**: 实施继续调用 `_normalized_text_tuple` 时，`" EARNINGS_CALL "` 会在 CLI 层变成 `"EARNINGS_CALL"`，regeneration argv 丢失原始候选；如果为保 raw 而改共享 helper，却未锁 `--forms`，又会扩大本项范围。另若 raw parser 先判 cardinality，`["a", ""]` 的首错会从空值变成多值。
- **为什么有问题**: `_normalized_text_tuple` 当前明确 strip 后返回，现有测试也固化了 strip 后候选。plan 的 raw 承诺只有在新增 raw-preserving mechanical parser、或精确改写共享 parser 并锁住 `--forms` 后才可执行；当前文本没有指定这一 owner/算法，也没有空值与多值竞争时的顺序矩阵。
- **直接证据**: `dayu/cli/commands/fins.py:1165-1174` 的 strip/return；`:1193-1208` 的调用与 `.upper()`；plan 第 17/31/36 行的 raw 返回与错误时点承诺；`tests/cli/test_upload_filings_from_command.py:227-235` 当前只断言 strip+upper 后值。
- **影响**: 可能保留第二套 CLI form 处理、regeneration 不保真，或在空值/多值组合上改变 CLI 首错；跨链同值测试若只看 canonical typed entry 会漏过 raw 输入契约。
- **建议改法和验证点**:
  - 明确 `_single_batch_material_form` 使用 raw-preserving split loop：按现有顺序遍历所有 value/item，用 stripped 副本只做空值判定，保存原始 item，完整扫描后才判多值；或明确修改 `_normalized_text_tuple` 的返回语义并同时锁定 `--forms` 行为不变。
  - 增加精确矩阵：`None`、`[]`、`""`、`"   "`、`["a", ""]`、`["", "a"]`、`["a", "b"]`、`" a "`；断言错误类型、首错顺序、batch request 原值和 regeneration argv。
  - owner 测试再断言 batch 将 raw padded/mixed-case 候选交给唯一 canonical 函数，CLI 不自行 `.upper()`。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

## Open Questions

1. raw parser 应作为 `_single_batch_material_form` 的私有机械流程，还是把 `_normalized_text_tuple` 改为 raw-preserving 后由 `--forms` 与 `--material-forms` 共用；两者都必须先锁定既有空值/多值顺序。
2. tool 测试捕获真实 US/CN/HK material 事件流的具体 seam 与 exact fixture 尚未指定；不得用 fake service 参数或无 form 的 summary 代替。
3. 只读读回脚本的 exact argv、Python 3.11 解释器和 artifact 命名留给实施 gate；临时脚本必须放 `workspace/tmp/`。

## Residual Risks

1. 历史 raw form 在 skip/delete 后仍会与新事件/结果跨代分叉；跟踪到 `fins-material-legacy-identity-seed-disposition`，O17 不迁移旧数据。
2. `ingestion_runtime.py`、`cn_pipeline.py` 等大文件逐文件 `>=80%` 可能阻塞实施；失败只能如实报告未完成，不能降低门槛。
3. storage `_fs_source_document_core.py:1771` 的 `req.form_type or merged_meta.get("form_type")` fallback 对当前 material 显式路径是死分支，但未来绕过 `prepare_upload` 的写入仍可能复活旧值；由 storage/O07/O10 或独立整洁性 issue 跟踪。
4. read-side form alias/normalization 是独立语义，不能用 raw 查询命中率替代 source meta 的 owner 级 form 断言。
5. CLI `--forms` 会先经过现有文本解析；真实 CLI 配对证明 CLI 可见合同，不替代 admission/直接 market 入口的错误时序测试。
6. 冻结 A14/A15 只证明历史偏差；成功信号仍依赖实施后同一 HEAD 的隔离 CLI 配对和公共仓储读回。

## Command and Validation Disclosure

- SHA、HEAD、分支和目标路径写入前均已复核；目标 review 路径写入前不存在。
- 本 review 为只读审查，唯一新增为本 artifact；未运行测试、coverage 或 pyright，因为没有实施代码变更。
- 非零命令如实披露：
  - 初次跨 `docs .agents .codex dayu tests` 的宽泛 `rg` 因不存在的输入路径返回 exit 2，输出未用于结论；随后改为精确 `rg --files` 与目标文档读取。
  - 检索 `.env .codex .agents pyproject.toml` 中 runtime/model 标识的 `rg` 返回 exit 2，未用于模型结论；实际 header 依据当前 Codex runtime 与既有同版 MiMo artifact 的 `codex/mimo/gpt-5-codex` 记录。
  - `/Users/leo/.codex/memories/MEMORY.md` 中检索 upload-material/O17/O09/O05/planreview 返回 exit 1（无匹配），只用于确认无可用历史记忆，不作为项目事实。
  - `tests/cli` 中检索 `material_forms/_single_batch_material_form/_normalized_text_tuple` 返回 exit 1（无直接测试匹配），随后以实际 `tests/cli/test_upload_filings_from_command.py` 与源代码完成核证。
- 其余用于结论的读取、SHA、git 和目标路径检查命令 exit 0；未把任何失败命令当作正向证据。

## Final Plan Review Conclusion

**fail**

- SHA 与锁定值一致；batch/material canonical 主链方向、O09 before-seed 登记、PR4-F2 真实事件/result 断言面、O05 延后边界、历史 raw 范围、coverage 与 README 口径均有直接证据。
- 停止条件命中：plan 的“material stream 顶端”规范化会改变非法 ticker/market 与缺失 form 同时出现时的既有首错时序；这超出 O17 的有效值 canonical 目标，必须在实施前改 plan。
- CLI raw 候选承诺并非理论上不可执行，但当前 `_normalized_text_tuple` 会 strip，plan 未指定 raw-preserving parser 及空值/多值顺序矩阵，仍不足以安全交给 implementation agent。
- 因 Finding 01 已直接触发用户停止条件，本复审不得给 pass/pass-with-risks；修复并重新锁定 plan SHA 后再做独立复审。
