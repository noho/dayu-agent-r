# wu-cli-download-01 Slice 1 plan amendment

## 1. Gate 与时间

- Gate：Slice 1 code-review blocker 的最小 plan amendment。
- 系统时间：`2026-08-10T00:55:37+0800`。
- Exact HEAD：`0e18abdcd1fb7edbc2fbd2e6a366580beccf5ee8`。
- Plan：`docs/gateflow/wu-cli-download-01-plan-20260809.md`。
- 本 artifact：`docs/gateflow/wu-cli-download-01-slice1-plan-amendment-20260810-005537.md`。

## 2. 动机与直接证据

DS code review 的 DL-R01 要求 `FinsDownloadDateRange.start_is_explicit` 作为独立typed事实，从adapter穿透SEC/CN pipeline与workflow；下层必须使用required boolean，禁止从 `start_date is not None` 反推，也禁止默认值或兼容fallback。

全仓调用点调查发现，现有Slice 1 allowlist外的 `tests/fins/test_cn_pipeline.py` 直接调用真实 `CnPipeline`：

- `tests/fins/test_cn_pipeline.py:337`：`pipeline.download(...)`。
- `tests/fins/test_cn_pipeline.py:402`：`pipeline.download(...)`。
- `tests/fins/test_cn_pipeline.py:454`：`pipeline.download_stream(...)`。

三处当前都显式传入非空 `start_date`，恢复实现时必须逐处传入 `start_is_explicit=True`，不得由实现者再次推断或自行分流。

若不更新这三个调用点，required signature会使全量pyright/tests失败；若提供默认值、从日期值反推或添加兼容overload/wrapper，则会破坏DL-R01要求的typed owner，不能作为替代方案。

## 3. 唯一 scope expansion

仅将 `tests/fins/test_cn_pipeline.py` 加入：

1. Slice 1 `Allowed test files / owner tests`；
2. §9 affected union。

该文件新增权限仅用于：

- 更新required `start_is_explicit` 的真实 `CnPipeline.download/download_stream` call sites；
- 验证 `start_date` 非空但 `start_is_explicit=False` 时，CN workflow仍启用默认业务限制。

第二项是pipeline-layer direct contract test：它绕过当前builder直接调用pipeline，目的是证明下游消费typed explicitness事实，而不是从非空日期反推。它不是公开端到端合法输入示例，不授权改变当前builder observable behavior。SEC对应owner test仍留在原Slice 1 allowed SEC tests中，验证相同输入组合下SC13仍可按policy扩窗。

不扩大production allowlist，不授权该测试文件的其它重构、清理或行为扩张。`tests/fins/test_cn_pipeline.py` 的全部现有 `test_upload_*`测试函数及其fixture/helper区域必须零diff；code rereview必须检查该文件unified diff的每个hunk，任何upload测试区域变更都是hard stop。

## 4. Typed contract owner 与 implementation checklist

当前 `FinsDownloadDateRange` 没有 `__post_init__`。恢复实现时必须在该typed contract owner增加不变量校验：

- `start_is_explicit=True` 时，`start_bound`必须非空；
- `end_is_explicit=True` 时，`end_bound`必须非空；
- `start_bound`与`end_bound`均存在时，必须满足`start_bound <= end_bound`；
- 允许bound非空且对应explicit为False，用于未来默认bound和本次pipeline-layer direct contract test；
- 非法组合统一抛`FinsDownloadUsageError`，不得由adapter、pipeline或workflow补救；owner tests使用现有allowed test files，不扩scope。

`build_fins_download_request`必须删除自身重复的`start > end`判断，改为构造`FinsDownloadDateRange`并由typed owner执行range校验；owner继续抛同一`FinsDownloadUsageError`中文消息，保持当前builder的可观察错误类型与文本行为。

Implementation checklist：

1. `tests/fins/test_cn_pipeline.py:337`、`:402`、`:454` 均传 `start_is_explicit=True`；新增False反例明确绕过builder。
2. 同步 `tests/fins/test_cn_download_runtime.py::_RecordingPipeline.download` 的required boolean签名。
3. 同步 `tests/fins/test_cn_download_workflow.py::_collect_events`、该文件直接`pipeline.download`及全部相关调用的显式boolean。
4. 全量pyright捕获所有漏迁签名/call site；不为通过类型检查增加默认值、兼容overload或wrapper。
5. `tests/fins/test_cn_pipeline.py` upload测试区域零diff，code rereview逐hunk确认。

## 5. 当前 working tree 保全

- Exact HEAD保持 `0e18abdcd1fb7edbc2fbd2e6a366580beccf5ee8`。
- amendment开始前已存在的未提交Slice 1 production/test diff保持原样；本gate未修改任何production或test文件。
- 两份code review artifact保持不可修改：
  - `docs/reviews/code-review-20260810-004038.md`
  - `docs/reviews/code-review-20260810-004602.md`
- 首版implementation artifact `docs/gateflow/wu-cli-download-01-slice1-implementation-20260810-003603.md`保持不变。
- 未运行真实CLI，未commit、push或创建/修改PR。

## 6. 风险与控制

| 风险 | 分类与控制 |
|---|---|
| test allowlist扩张被误用为CN pipeline广泛清理 | 当前amendment已限制为required boolean真实调用点与一个owner反例；其它变更不授权。 |
| 用默认值维持旧调用会掩盖typed fact缺失 | 明确禁止默认值、日期反推、compat overload/wrapper；所有真实调用显式传bool。 |
| pipeline direct反例被误读为公开输入 | 明确标注该测试绕过builder，只验证下层消费typed fact；不改变公开端到端输入契约。 |
| upload测试被allowlist扩张波及 | upload测试区域零diff；code rereview逐hunk核对，命中即退回。 |
| 当前dirty implementation diff在plan gate被意外改动 | 本gate仅修改plan并新增本artifact；完成后用status/diff检查产品/test集合未变化。 |
| amendment fix未经rereview即恢复代码修复 | 当前next gate固定为两位原reviewer的plan amendment rereview；两路通过并形成accepted amendment commit前禁止恢复产品/test修复。 |

## 7. Plan review adjudication

裁决对象保持不可修改：

- AgentMiMo：`docs/reviews/plan-review-20260810-010145.md`。
- AgentDS：`docs/reviews/plan-review-20260810-010500.md`。

| Review item | Disposition | 文档收敛 |
|---|---|---|
| DS DL-PA-01 | **accepted** | 锁定`test_cn_pipeline.py:337/402/454`均传`start_is_explicit=True`。 |
| DS DL-PA-02 | **accepted** | False+非空日期明确为绕过builder的pipeline-layer direct contract test，不是公开端到端示例。 |
| DS DL-PA-03 | **accepted** | upload测试区域零diff成为hard stop，code rereview逐hunk核对。 |
| DS OQ-1 | **accepted，owner已收敛** | `FinsDownloadDateRange.__post_init__`拥有explicit/bound与range不变量，非法组合抛`FinsDownloadUsageError`；不下放校验。 |
| MiMo 001 | **accepted implementation note** | `_RecordingPipeline.download`同步required boolean签名；文件已在allowlist内。 |
| MiMo 002 | **accepted implementation note** | `_collect_events`、直接`pipeline.download`及相关调用全部同步；文件已在allowlist内。 |

没有新增production或test文件scope；两项MiMo finding由全量pyright兜底，但implementation仍必须按checklist主动穷举，不能依赖失败后补漏。

## 8. Disposition 与后续 gate

- Amendment disposition：test-only、最小、无production scope expansion。
- 当前gate完成信号：plan与本artifact已记录全部plan-review裁决、唯一allowlist扩张、§9 union、typed owner不变量与implementation checklist；`git diff --check`通过；产品/test/review/implementation artifact均未修改。
- 下一合法gate：回两位原reviewer执行plan amendment rereview。
- 后续顺序：两路rereview通过 -> accepted amendment commit -> 恢复Slice 1 code-review fix（DL-R01、DL-R02）-> code rereview。
