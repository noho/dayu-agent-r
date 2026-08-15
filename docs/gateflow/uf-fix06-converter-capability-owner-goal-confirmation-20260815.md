# UF-FIX06 converter-capability-owner：Goal Confirmation

## Gate

- work unit：`UF-FIX06 converter-capability-owner`
- gate：`goal confirmation`
- design inputs：`docs/host/design.md`、`docs/engine/design.md`
- oracle inputs：`docs/cli_ci_oracles.json` 的 `upload_filing.format-owner`
- scenario input：`docs/cli_ci_scenarios.json` 的 `UF-FIX06`
- frozen evidence input：第一轮 `UF-O12-format-owner-drift`
- completion status：`confirmed`
- artifact path：`docs/gateflow/uf-fix06-converter-capability-owner-goal-confirmation-20260815.md`

## Preflight

- 当前分支：`codex/upload-filing-oracle`，不是 protected trunk。
- 工作树：preflight 时干净。
- merge / rebase / cherry-pick：均未进行。
- `main` 与抓取后的 `github/main`：同为 `256786b255021ee429a20f22aad726b1ad33916c`，`main...github/main = 0/0`。
- 当前分支：以 `main` 为祖先且单向领先 43 个提交，`main...HEAD = 0/43`。

## 第一性原理判断

问题成立。上传边界真正需要承诺的不是“某个入口认识哪些扩展名”，而是两类不同事实：

1. primary 输入必须属于当前装配的 Docling converter 明确声明的输入 capability，并且真实内容转换成功；扩展名只能参与确定性路由，不能替代转换成功。
2. companion / attachment 不承担 primary 内容转换职责，只需通过受控附件格式准入并原样进入同一原子 publication；它们不得被逐个强制转换。

converter capability 必须由构造并调用真实 `DocumentConverter` 的共享转换边界拥有；Fins 上传 contract 只能对该 capability 增加 primary / companion 角色语义，CLI、Service、batch scanner 和 workflow 都机械消费同一个 typed contract。Host 与 Engine 不拥有该业务事实。

## 直接代码与数据证据

- `dayu/fins/upload_batch.py` 定义 `FINS_UPLOAD_FILE_SUFFIXES`，包含 `.csv/.json/.xbrl/.xhtml/.xls/.xml/.zip`，但缺少 `.doc/.ppt/.pptx`。
- `dayu/cli/commands/fins.py::_validated_upload_files` 用上述 batch allow-list 在 CLI 提前拒绝文件。
- `dayu/fins/ingestion_runtime.py::_validate_fins_upload_filing_static` 先检查 `FINS_UPLOAD_FILE_SUFFIXES`，随后又检查 `docling_upload_service.SUPPORTED_UPLOAD_SUFFIXES`，形成两个顺序相关的格式 owner。
- `dayu/fins/pipelines/docling_upload_service.py` 另行定义 `SUPPORTED_UPLOAD_SUFFIXES`，包含 `.doc/.ppt/.xls`，并在 `_build_pending_assets` 中对每个输入文件执行 `DoclingConverter.convert_to_json_bytes(...)`。
- `dayu/documents/docling_runtime.py::build_docling_pdf_converter` 实际构造 `DocumentConverter`；当前已安装 Docling 的 `InputFormat` / `FormatToExtensions` 直接显示 OOXML `DOCX/PPTX/XLSX`、HTML/XHTML、Markdown/TXT、CSV、XBRL/XML、Docling JSON 等能力，而没有 legacy `DOC/PPT/XLS` 或 ZIP capability。
- 冻结 `UF-O12` 直接观察到 DOC/PPT/PPTX 被 CLI 拒绝、真实 XLS 进入后转换失败、CSV/JSON/XBRL/XHTML/XML/ZIP 在 CLI 与 Service 间漂移，以及 HTML + XSD companion 组合在 CLI 被拒绝。
- `UF-C06-real-xbrl-html-xsd` 的冻结 argv 明确以 `cme_html.htm` 为首个文档输入、`cme_schema.xsd` 为 companion；失败原因是 CLI 单独维护的 suffix allow-list 不接受 `.xsd`。

## 目标与成功信号

1. 建立单一、不可变、严格类型化的 upload format capability contract，明确 primary converter 输入与原样 companion / attachment。
2. 真实 converter 的构造/调用与 capability declaration 同源；legacy DOC/PPT/XLS 与 ZIP 不被宣称为可转换输入。
3. `upload_filing --help`、CLI usage validation、Fins static admission、batch scanner 和 `DoclingUploadService` 不再维护独立 suffix allow-list，全部消费同一 contract 或其 typed projection。
4. 保持现有输入顺序语义：本 work unit 不增加 UF-FIX07 的显式 primary 参数；workflow 只要求当前隐式 primary 成功转换，其余已准入 companion 原样存储，不逐个转换。
5. XBRL/Inline XBRL 主文档与 `.xsd` 等 companion 可在同一原子 publication 中保存；primary 转换失败仍整批失败、stored count 为零。
6. CLI help 与 validation 能准确区分“可作为 primary 交给 converter”和“仅可作为 companion 原样保存”，不把后缀匹配描述成内容已可转换。
7. 受影响测试与 pyright 通过；按 README 职责约束更新 Fins、CLI 用户说明与 tests focused suite 说明（只在命中职责时修改）。

## 非目标与边界

- 不实现 UF-FIX07 的显式 primary 选择、重复路径、basename/stem collision。
- 不执行 UF-PF06、UF-PF12 真实 CLI evidence。
- 不刷新 `docs/cli_ci_oracles.json`、`docs/cli_ci_scenarios.json` 或任何冻结 evidence。
- 不修改 Host / Engine lifecycle、schema、EventLog 或 LLM loop。
- 不回退原子 publication、typed bounded failure、requested/stored summary、共享可中断 Docling converter、calendar/year 或 ticker alias contract。
- 不为未来 converter plugin、动态 capability discovery、MIME sniffing framework或任意附件类型设计扩展系统；只冻结当前 production Docling 与当前 XBRL companion 所需的最小 contract。

## 设计文档对齐

- `docs/host/design.md`：Host 不承载财报业务语义；direct upload 不能被塞入 Host lifecycle。
- `docs/engine/design.md`：Engine 不理解财报业务语义、XBRL 或仓储，不应为 upload capability 增加依赖。
- 因此实现边界限定在 `dayu.documents` 的真实 converter capability 与 `dayu.fins` 的 upload role/admission contract，以及机械消费这些事实的 CLI / Service-facing 路径。

## 本轮不做的过度设计

- 不引入运行时插件注册表、动态探测缓存或开放字符串 capability bag。
- 不加入 magic MIME fallback、loose parsing 或按文件内容猜 legacy 格式。
- 不为 attachment 生成 Docling 派生文件，也不让 CLI 自行推断 primary。
- 不增加兼容 re-export / wrapper；旧 allow-list 直接迁移到 owner contract 并删除。

## Blocking Open Questions

无。现有输入顺序和 UF-C06 冻结 argv 足以在不提前实现 UF-FIX07 的前提下保持当前隐式 primary 语义。

## Residual Risks / Uncovered Areas

| 风险或未覆盖项 | 分类 | owner / destination |
| --- | --- | --- |
| 显式 primary 选择、重复路径与 basename/stem collision | assigned to later work unit | `UF-FIX07` |
| 真实全格式矩阵与 XBRL companion CLI evidence | assigned to later work unit | `UF-PF06` |
| 137 条 full-real mandatory matrix | assigned to later work unit | `UF-PF12` |
| 冻结 evidence 与 registry 状态仍描述修复前观察 | assigned to later work unit | 后续 evidence/registry 专门 work unit；本轮禁止修改 |

## Next Entry Point

进入 `plan`；由 AgentCodex 产出 code-generation-ready plan，AgentMiMo 与 AgentDS 并行执行两路 plan review。
