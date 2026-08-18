# UF-FIX03 summary-and-bounded-errors goal confirmation

## Gate

- gate: `goal confirmation`
- work unit: `UF-FIX03 summary-and-bounded-errors`
- design inputs: `docs/host/design.md`, `docs/engine/design.md`
- oracle inputs:
  - `docs/cli_ci_scenarios.json` 中 `UF-FIX03`
  - `upload_filing.irrelevant-and-repeated-options`
  - `upload_filing.direct-boundary-and-summary`
  - `upload_filing.malformed-and-empty-input`
- status: `waiting-for-user-confirmation`
- next entry point: `plan`

## First-principles judgment

问题真实存在，且属于终态业务事实错误与用户可见诊断泄漏风险，不是展示偏好：终态 summary 会进入 CLI direct result 与 durable ingestion summary；如果把请求文件数量当作成功存储数量，delete、skip、failure 会形成与仓储事实冲突的公开事实。已知失败若绕过 closed typed owner，CLI 再使用原始异常字符串，就会同时破坏稳定分类、可行动性和敏感信息边界。

本轮不把“已具备的原子 publication 机制”误判为仍需重构。当前 SEC 与 CN/HK filing workflow 都先完成 `prepare_upload`，之后才 `begin_batch`；company meta 与 source/blob publication 也已经在同一 batch 内提交。损坏输入的正确修复重点是 publication 前失败、typed failure 投影与 owner-level 回归证明，而不是新增第二套事务或补偿机制。

## Direct code evidence and root cause

1. summary 根因位于 `dayu/fins/service_runtime.py::_upload_summary_from_result`：`uploaded_files` 直接由 `request.files` 的 basename 构造。该值描述请求，不描述 pipeline/storage 的成功 publication，因此 delete+files、skip、failure 都会被误报为已上传。
2. 实际 publication 事实由 `dayu/fins/pipelines/docling_upload_service.py::DoclingUploadService._store_upload_assets` 产生：只有 batch 内 `store_file` 成功后才存在已存储文件事实。该 owner 已掌握成功写入的 original assets；summary 应消费其 typed 结果，而不是回看 request。
3. `dayu/fins/upload_failure.py` 已经是 upload closed failure code/reason owner，CN/HK 与 SEC workflow 也已在 typed catch 中记录完整 operator traceback、只向 pipeline result 放 bounded failure。正确路径是补全并贯通这一 owner contract，不在 CLI/Service 按异常字符串重新分类。
4. `dayu/fins/pipelines/docling_upload_service.py::_validate_source_files` 目前只校验存在、普通文件与 suffix；`_build_original_assets` 对 `read_bytes()` 返回空字节没有拒绝。因此空文件能进入 converter，缺少 publication 前 content admission。
5. `dayu/cli/commands/fins.py::run_fins_direct_command` 的兜底 `except Exception` 仍直接把 `str(exc)` 写到普通 stderr。即使已知 pipeline 失败通常走 typed terminal，该兜底仍不满足 upload_filing 的 bounded stderr 边界；内部异常应写 operator/debug log，用户只消费 owner 提供的安全投影或固定未知失败说明。
6. SEC/CN workflow 当前均在 `prepare_upload` 完成后才 `begin_batch`，且 publication failure 会 rollback；因此“有效文件 + 损坏文件”没有必要新增跨层补偿，只需确保空/损坏输入在 prepare 阶段形成 typed failure，并用 owner-level tests 锁定零 batch publication、零 company/source partial state。
7. `dayu/service/fins_direct.py` 直接调用 Fins ingestion runtime；该路径不装配 Host。Host design 明确 Host 不拥有财报业务语义，Engine design 也禁止依赖 Fins。UF-FIX03 不应修改 Host/Engine，也不应创建 Run、EventLog、Memory、Tool Trace 或 legacy job。

## Confirmed goal and success signals

- 终态 contract 同时表达 `requested_file_count` 与 `stored_file_count`；前者来自 validated request，后者只来自 publication owner 的成功结果。
- `stored_file_count` 按“本次成功发布的用户输入 original 文件数”解释，不把派生 Docling JSON/manifest 算作第二份用户文件；delete、skip、cancelled、failed 均为 `0`。
- upload closed failure owner 产生稳定 `kind/code/message/retry_hint`，必要时携带经过校验的单个文件名标签；pipeline、runtime、durable summary、direct event 与 CLI 只做 typed projection。
- 普通 stderr 不包含第三方 traceback、绝对路径、异常 repr 或原始无界底层文本；operator/debug log 保留完整内部异常。
- 空文件在 converter 与任何 batch publication 前被拒绝。
- 损坏 PDF、损坏 DOCX、有效文件与损坏文件混合输入均形成整批失败；不会发布 filing、company/source state 或非零 stored count。
- direct Fins command boundary 保持不变，且测试证明没有 Host/runtime durable artifacts 或 legacy ingestion job。

## Non-goals and scope boundary

- 不执行 UF-PF03 真实 CLI evidence。
- 不修改 `docs/cli_ci_oracles.json`、`docs/cli_ci_scenarios.json` 或第一轮冻结 evidence。
- 不处理日期/年份、ticker alias、格式 capability、multi-file primary/collision、existing-source repair、并发、company meta warning。
- 不引入 Host Run/EventLog/Memory/Tool Trace、workflow engine、legacy ingestion job、补偿队列或兼容 schema。
- 不为旧 `uploaded_files` 语义保留兼容字段、re-export、wrapper 或 fallback；测试随 owner contract 一起迁移。
- 不修改 `docs/host/design.md`、`docs/engine/design.md`，因为本轮实现必须保持它们冻结的分层边界。

## Expected owner boundaries

- request count owner: validated Fins upload request。
- stored count owner: Docling upload publication result，由成功写入 original assets 派生。
- closed upload failure owner: `dayu.fins.upload_failure`。
- upload terminal/durable projection owner: `FinsUploadResultSummary` 与 direct event builder。
- CLI owner: 只负责渲染 typed terminal 与把未分类内部失败写 operator log，不拥有业务分类。
- atomic publication owner: 现有 Fins batching repository + SEC/CN upload workflow。

## Validation and documentation decision

- 计划必须包含 owner contract tests、SEC/CN pipeline atomicity tests、direct runtime/durable summary tests、CLI stderr/log tests、focused pytest、pyright 与 coverage 检查。
- `dayu/fins/README.md`、`dayu/service/README.md`、`tests/README.md`、根 `README.md` 必须先读各自更新约束，再按真实职责命中决定是否更新。
- Host/Engine README 与 design docs 预期不更新。

## Residual risks

- `stored_file_count` 的业务口径需要用户确认：本 artifact 采用“成功发布的用户输入 original 文件数”，不计派生 Docling 资产。分类：`requiring explicit user confirmation at goal confirmation`。
- 真实第三方 Docling 对不同损坏样本的具体底层异常可能变化；public contract 只承诺 closed code/reason 与原子性，完整异常留 operator log。分类：`covered by implementation tests and later UF-PF03 evidence`。
- UF-PF03 未在本轮执行。分类：`assigned to explicitly excluded later evidence work`。

## Completion status

Goal confirmation artifact 已完成；等待用户确认上述目标、非目标、owner boundary 与 `stored_file_count` 口径后进入 `plan`。

## Artifact path

`docs/gateflow/uf-fix03-summary-bounded-errors-goal-confirmation-20260813.md`
