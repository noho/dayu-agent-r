# UM-O14/O15 state plan PR-C3-F1 owner/hint 修订记录

- Gate：plan fix 候选；只修 MiMo `docs/reviews/plan-review-20260929-150200.md` 的 PR-C3-F1。未取得本版独立 Kimi/MiMo 双路复审，不能计 plan gate pass；O14/O15 产品未实施。
- 输入 state plan SHA-256：`5b74854bc10873e29fa94a716d88713d7ee48bd9236eb3d0a6d6a5445efeb191`，与任务绑定值和本轮修改前本机 `shasum -a 256` 一致。
- 输出 state plan SHA-256：`f2496dd1da34f0556cff7e032b6f68ba7e7918b525c7b7aae5318b5ddc420cee`。修改文件仅 `docs/gateflow/upload-material-state-plan-20260929.md`；本记录是唯一新增文件。
- 同轮只读依据 SHA-256：goal `6c673a48e7ed194fc060cf8569acf62974d2960ed7f9c580869cbaba92eb2c91`；MiMo review `5d7fb4e2aac166cf08e0ef8918f45b62d59fb85504791f84118c8fecfc90d0d7`；总控 adjudication `dbf5b42a768c98ee535dbaa9bfc9bc387f216d2181ad75a1c0307cdac031413e`。既有 C3 fix、goal、review、adjudication 原样保留。

## 动机与一手 owner 证据

PR-C3-F1 成立，严重程度低但会让实施选错语义 owner。当前 `dayu/fins/ingestion_runtime.py` 的 `FinsUploadUsageFailure` 只有 code/message；`fins_upload_usage_failure` 使用 `_USAGE_MESSAGES` 产生 usage fact，未承载 retry hint。`dayu/fins/upload_failure.py` 集中构造全部 `FinsUploadFailureReason`，public reason 已有 `retry_hint` 字段，但 `FinsUploadFailureCode` 尚无三个 target code。`dayu/fins/tools/upload_tools.py` 当前仅以 `except ValueError` 取 `str(exc)`，并给通用 `_INVALID_ARGUMENT_HINT`，tool 协议 error 为 `invalid_argument`。本轮对这三个真实文件只读核对；上述事实不是实施后 API。

方案把 kind-aware target code/message/hint 的生成固定在 Fins usage owner；`FinsUploadUsageFailure` 新增并校验 hint 字段明确列为**待实施**。`upload_failure.py` 作为唯一 public reason 构造/usage→public 映射 owner，消费 typed usage fact，映射三个 target public code/kind，并原样转交 fact.message/hint。tool typed usage 分支只读取同一 fact 的 message/hint，协议 error 仍为 `invalid_argument`；CLI/Service 读取同一 typed fact，direct 与可达的 awaited summary 读取同一 public reason。普通 `ValueError` 仍走既有通用 tool hint。没有第二张 code→hint 表。

依赖方向也已写入计划：runtime 已 import `upload_failure.py`，后者不能反向 import runtime。若实施需跨模块传完整 typed fact，候选仅抽出 code/fact 类型到 Fins 下层独立 contract，迁移原引用导入且不做兼容 re-export；usage 文案/hint producer 留唯一，public reason 构造仍在 `upload_failure.py`。候选文件名不是本 checkout 已存在的 API。现有 public reason JSON 已有 `retry_hint`，本项不扩 tool 协议或持久化形状。

## 未来实施受影响文件与测试白名单

以下是**候选**，须待 O12 accepted plan 的产品代码集成后按实际 owner/调用图收窄；本轮没有修改这些文件。S1 owner 与投影：`dayu/fins/pipelines/docling_upload_service.py`、`dayu/fins/ingestion_runtime.py`、`dayu/fins/upload_failure.py`、`dayu/fins/tools/upload_tools.py`。仅在 typed fact 跨模块需要时新增 `dayu/fins/upload_usage_contract.py` 并迁移 `dayu/fins/pipelines/filing_upload_publication.py` 等实际导入；仅在 O12 最终调用点确需时触及 `dayu/fins/service_runtime.py`、`dayu/fins/pipelines/sec_upload_workflow.py`、`dayu/fins/pipelines/cn_pipeline.py`、`dayu/fins/pipelines/sec_pipeline.py`、`dayu/cli/commands/fins.py`。S2 storage/guard 候选路径维持原 plan §实施切片，不因 PR-C3-F1 扩大。

S1 测试白名单：`tests/fins/test_docling_upload_service.py`、`tests/fins/test_fins_ingestion_runtime.py`、`tests/fins/test_fins_service_runtime.py`、`tests/fins/test_sec_pipeline_upload_material_stream.py`、`tests/fins/test_cn_pipeline.py`、`tests/fins/test_fins_ingestion_tools.py`、`tests/fins/test_upload_failure.py`、`tests/fins/test_filing_upload_publication.py`、`tests/cli/test_fins_commands.py`。owner 测试须逐码锁 usage fact 字段校验、kind-aware message/专用安全 hint、public reason 唯一映射及 message/hint 逐字同源；入口测试锁 tool `invalid_argument` 且无 Fins code 字段、普通 `ValueError` 通用 hint、CLI/Service/awaited 投影和 filing 旧文案。S2 测试白名单维持原 plan §实施切片及验证命令。

## 保持、验证与残余

- O12 accepted plan checkpoint `b201d9f3b1c84e49fe0751d75ea7dc31e2c0f14c`，其 plan SHA-256 `48e0598bd8c949e7257b6fd6c6a03adbdca31b0def2d680d4b0cea93f7ed5e60`；此处沿用已裁决依赖，不把 accepted plan 当已集成代码。O34 公司独立提交与材料 guard、UM-A09 同指纹恢复保留版本、F8–F11、三态动作矩阵、tool `invalid_argument` 均未回退。
- 本轮只改 Markdown，未运行产品测试/pyright；它们属于未来实施 gate。文档已核输入/输出 SHA、所列测试文件存在、`git diff --check` 退出 0（但 plan 未跟踪，故该命令不覆盖本 plan 的空白检查）；最终还须直接检查新增/修改 Markdown 和工作树范围。
- 残余：O12 产品尚未实施/集成；typed usage hint 字段、三个 public target enum、唯一映射和 tool typed 分支都只是计划。O12 实际 API 或 public schema 若无法按唯一 owner 最小承载，先回 owner/plan 裁决；本版仍需同一最终 SHA 的独立 Kimi/MiMo 复审。冻结 A04 不能证明不同内容 create，真实 CLI 证据留未来实施 gate。
- 本轮失败工具/命令：首次 `functions.exec` JavaScript 有括号语法错误，未执行任何嵌套命令；一次 `rg` 指向不存在的 `tests/fins/test_upload_tools.py`，进程 exit 2，但同次输出的其它匹配不作独立成功命令证据；其后用 `rg --files` 确认实际文件为 `tests/fins/test_fins_ingestion_tools.py`。无 Goal tool、无匹配失败查询、依赖安装、产品改动、commit/push/PR/merge 或子 Agent 派发。
