# UM-O05-F01 C2 plan fix 记录

- Gate：`plan review -> fix`；仅修订候选 plan，未实施产品、测试或 README；下一 gate 仅为 Kimi/MiMo 对同版 plan 的有效 review。
- 工作区：`/private/tmp/dayu-upload-o05`；分支：`codex/upload-material-o05`；HEAD：`8d8d494fbbce0052372fb1b42097c9f7222cfa28`。
- 修订目标：`docs/gateflow/upload-material-o05-required-identity-plan-20260929.md`；修订后 SHA-256：`ed83ceb378840c3ca47e5adbd1d4a41e6c078261a80d37315034819bd4cfaef8`。
- RUNTIME/PROVIDER/MODEL：`codex/gpt-6-sol/gpt-6-sol`；CANARY=`gpt-6-sol-cfe6d58f`（从用户指定 canary.txt 实际读取）。本轮未派发子 Agent。

## 直接证据与动机判断

1. 总控 `docs/gateflow/upload-material-o05-plan-review-adjudication-20260929.md` 的 C2 已接受：旧 plan 只改 runtime，SEC/CN 独立 workflow 可绕过，造成 typed usage 与 builder raw `ValueError` 分叉。这个问题真实且影响公开独立入口；现有证据只证明拒绝时机/语义分叉，不证明错误材料已发布。
2. 当前 `dayu/fins/ingestion_runtime.py`：`FinsUploadMaterialRequest` 两字段为 `str | None`；`upload()`、`prepare_observed_upload()`、`start_upload()` 在 stream/handle/job 前走 `_validate_runtime_upload_request()` -> `_normalize_upload_request()`；后者目前只做 ticker/action/source kind。typed `FinsUploadUsageCode`、`FinsUploadUsageFailure`、`FinsUploadUsageError` 及唯一 `_USAGE_MESSAGES` 已在此模块。
3. `dayu/fins/pipelines/sec_upload_workflow.py::run_upload_material_stream()` 和 `dayu/fins/pipelines/cn_pipeline.py::CnPipeline.upload_material_stream()` 在 `build_material_ids()` 前没有 runtime admission；builder 当前对空白 form/name 抛 raw `ValueError`。两条 workflow 都先生成稳定 ID，再做显式 ID 校验、action/files selection、仓储读取、`UPLOAD_STARTED` 与文件动作；同步 facade 都委托各自 stream。两处 `try/except Exception` 在 ID 之后，故在执行体开头调用同一 owner 可让 typed usage 原样传播。
4. 实际 imports：`sec_upload_workflow`、`cn_pipeline`、SEC facade `sec_pipeline` 已依赖 `ingestion_runtime`；`ingestion_runtime` 已依赖 `docling_upload_service`；builder 模块不依赖 runtime/workflow。候选新增 `workflow -> ingestion_runtime.admit_fins_upload_material_identity -> O17 docling_upload_service.normalize_material_form_type` 沿既有方向，无当前 import cycle。O17 函数尚未集成到此 HEAD，故这只是 O17 accepted+integrated 之后的可实施接口，不冒充已验证产品行为。
5. `dayu/cli/arg_parsing.py` 的真实命令使用 `upload_material --forms/--material-name/--files`；`dayu/cli/__main__.py` 支持 `python -m dayu.cli`。现有计划的七类 CLI 输入矩阵仍适用，但不足以证明独立 workflow。`tests/fins/test_sec_pipeline_upload_material_stream.py` 与 `tests/fins/test_cn_pipeline.py` 是真实对应测试文件。

## 本次 plan 修改

- 明确唯一公开 Fins material identity admission 签名：`admit_fins_upload_material_identity(*, form_type: str | None, material_name: str | None) -> tuple[str, str]`。在现有 typed usage owner 中先按 form/name 顺序拒绝 None/空/纯白，再调用**已接受且已集成的** O17 canonical 函数；返回值贯穿 runtime normalized request 与独立 workflow 的 ID、事件、meta/result。builder 内部守卫保留，但不承担公开输入准入。
- 白名单增加 SEC facade（只同步 nullable 参数注解）、SEC workflow、CN/HK pipeline 及两份对应测试；覆盖率命令增加三个生产模块，仍要求所有拟改生产单文件分别 >=80%。增加 runtime direct/observation/job 与两条独立 workflow 的调用点/错误 owner 矩阵、零 ID/started/handle/job/业务读写断言及合法 canonical 对照。`dayu/fins/README.md` 计划覆盖 Fins 开发者契约，根 `README.md` 覆盖 CLI 用户规则；README 正文未修改。
- 固定当前可见错误先后；O16 若先集成，实施者必须消费当时实际共享 action/files owner 并重审复合错误优先级；O06 在同一公开 identity admission 增 name 长度规则，位于必填之后。O07 ID 改造、O16 文件动作、O06 长度均未纳入 O05。

## 检查、失败命令与残余

- 已读 AGENTS.md、goal、总控 C2、现有 plan 和对应生产调用链；`git rev-parse HEAD` 与 `git branch --show-current` 确认上述基线。`rg` 核对 import 边界、CLI module 与测试文件；`shasum -a 256` 计算修订 plan SHA。`git status --short` 仅见原有未跟踪 goal/plan/裁决/两份旧 review 与本记录，无产品文件改动。
- 失败命令/工具：第一次组合读取的 `functions.exec` JavaScript 因括号错误报 `SyntaxError: missing ) after argument list`，修正后读取成功；`rg -n 'upload-material-o05|O05|O17|O16|O06' /Users/leo/.codex/memories/MEMORY.md` 无命中、退出 1，未采用记忆事实；`rg` 使用未引用的 `tests/fins/test_sec_upload*` glob 被 zsh 报 `no matches found`，改用 `rg --files tests` 定位；两次 `apply_patch` 因目标行不匹配拒绝且无部分写入，拆分修订后成功；`ls -ld .venv` 退出 1，证实本工作区没有 `.venv`。这些失败均未作为产品或计划验证通过的证据。
- 本轮只有文档变更，未运行 pytest、真实 CLI、pyright 或覆盖率；这些是 O17 集成后的 implementation gate 验收，不宣称通过。风险：O17 真实集成接口及 O16 先后顺序可能改变导入拓扑或错误优先级；实施前必须按实际 HEAD 复核。若同一 owner 无法覆盖独立 workflow、出现反向依赖或须新增未授权 schema，即按 plan 停止并提交直接反例，不加 fallback。
