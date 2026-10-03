# Plan Review（独立）：UM-CI-N01-F01 转换器诊断遵循父进程日志规则

RUNTIME/PROVIDER/MODEL: claude/ds-flash/deepseek-flash[1m]（runtime 声明；权重身份无法由工具独立自证）

CANARY=ds-flash-4631697d

- 任务：`upload-material-converter-diagnostics-plan-review-ds-flash-20261003-01`（独立 planreview，不实施）。
- Gate：plan review；review 对象：`docs/gateflow/upload-material-converter-diagnostics-plan-20261003.md`。
- 唯一 workspace：`/Users/leo/workspace/dayu-agent-r`；实核 branch `codex/upload-material-oracle`；实核 HEAD `79977b3a52f8566672e3b462f786f1004dfd3f89`。
- 冻结计划 SHA-256：`a58b95afbc9898969bf85e0c79ed0d3597339d2bbc3ddd420aedc80d30bf7289`（实核一致）。
- 时间戳（系统时钟）：2026-10-03 17:52:52 CST（2026-10-03T09:52:52Z）。
- 结论：**pass-with-risks**（3 个 finding，最高严重程度为"中"，均不影响设计成立，可在实施前小改计划或由 controller 裁决解决）。

## 1. 绑定契约与授权实核

| 项 | 实核结果 |
|---|---|
| binding goal | `workspace/tmp/upload-material-converter-diagnostics-20261003/goal-confirmation.md`，SHA `63ca599bee4ae401714281f8a7501c63b0c6b1b1024447a01ae1f6ed9d799a06`（与计划 §10 引用一致） |
| 用户接受依据 | `workspace/tmp/upload-material-unified-repair-20261002/post-wu-preparation/oracle-candidates.json`，SHA `dbeb48a6cff69e477034adf9e57e0b8dcf09fe0147ea64132df5992c75deec46`；`candidates[0].status="accepted"`，`user_adjudication.answer="第三方诊断也遵守 CLI 日志规则（建议）"`，`accepted_predicate="第三方转换器诊断不得混入业务stdout；quiet抑制诊断但保留业务进度/终态；指定log-file时按CLI等级写文件；未指定时遵既定诊断去向。"`，`received_at=2026-10-03T09:15:58.686979+00:00`。逐字存在，非 reviewer 共识代签。 |
| 冻结 802 场景 | `workspace/evidence/upload-material-cli-20261003-79977b3a-01/public/FORMAT-PDF-NATIVE-FULL/`：stdout.bin 19,741 bytes、SHA `8b2b38db9a414058ff7027895d5d21abb4b2384433ed8dc035743825580056be`、`MatchingPostProcessor` WARNING 恰 129 行；stderr.bin 0 bytes、SHA `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。计划观察计数逐项属实。 |
| owner 源码 SHA | 工作树 `dayu/fins/pipelines/docling_process_converter.py` = `d6b6772e329c66045f634fb4994c76bbcb9ef0130d3fe498b2e7f044ae6cd1b8`；`dayu/runtime/log.py` = `908e90c85ca7d1c6281d5296667933d7eee0768cb2bfd7554bc1b0fb75d19069`；`docs/reviews/upload-material-um-o29-oracle-adjudication.md` = `1ea88fbbdb2342c144ead9819636324eb8789154caccda8c791dfc191d0db922`。三者与计划 §10 引用逐一一致。 |
| 第三方 installed 源码 | 工作树 `.venv` 与冻结 CI root `/private/tmp/dayu-cli-ci-upload-material-20261003-79977b3a-01/.venv` 两份字节相同：`docling_ibm_models/tableformer/settings.py` = `68aacd3855426e2ccc6804f51e797323dca9bfbef034fa8b49a243d81920004a`；`.../data_management/matching_post_processor.py` = `0675880799c3474bfe0355c3fe81a105d87ac0f2cdb2f51a4699a9f4096cebe3`（与计划 §10 一致，两份实际各读）。`settings.py:5` `get_custom_logger(..., stream=sys.stdout)`、`:22` `StreamHandler(stream)`、`:41` 模块 import 即建 `LOGGER`；`matching_post_processor.py:13-29` `_log()` 按需 `get_custom_logger(class_name, logging.INFO)`，真实 WARNING 在 1160/1207/1234 行产生。计划行号引用属实。 |

## 2. 本轮实际读取的实际文件（关键）

- 计划本体、goal-confirmation、oracle-candidates.json（含 user_adjudication 逐字）。
- `dayu/fins/pipelines/docling_process_converter.py`（全文）、`dayu/runtime/log.py`（全文）、`dayu/runtime/interruptible_process.py`（全文）、`dayu/runtime/log_levels.py`、`dayu/cli/main.py:60-219`、`dayu/documents/xbrl_config.py` 的 `verify_prepared_xbrl_input`、`dayu/documents/docling_runtime.py` 的 lazy import 区与两个 convert 函数。
- stdlib 3.11.15 `logging/__init__.py`：`Filterer.filter`(775-800)、`Logger.handle`(1636-1665)、`Logger.hasHandlers`(1668-1688)、`Logger.callHandlers`(1690-1718)、`Manager.getLogger/setLoggerClass/_fixupParents`(1327-1410)。
- installed 第三方 `settings.py` 全文、`matching_post_processor.py` 头部与 WARNING 行号。
- `pyproject.toml`（pytest/coverage 配置面）、tests README 覆盖命令段、根 README §3.1、`dayu/fins/README.md:903`、`dayu/README.md` runtime 职责行。
- `tests/fins/test_docling_process_converter.py` 关键结构（`_SpawnBoundaryProbeTarget`:344、direct `target()` 调用 793/871/973/1043/2252、XBRL monkeypatch direct probe 区）。
- 覆盖证据：`workspace/tmp/upload-material-unified-s3-implement-sol-20261003-01/coverage-final-combined.json`；覆盖率启动钩子 `.venv/lib/python3.11/site-packages/a1_coverage.pth`；`coverage/control.py:1437 process_startup`；`pytest_cov/engine.py:230-285`。
- 冻结场景 stdout/stderr bytes、旧 CI root 输入 PDF 存在性（`inputs/msft-native-2024.pdf` 实际存在，未重复 hash）。

## 3. 机制裁决（任务要求的专项判断，不计为 finding）

**结论：选定机制成立且是当前约束下的最小可行方案，不属于项目禁止的 monkeypatch。**

- 必要性：accepted predicate 要求"按 CLI 等级写文件、quiet 抑制"，即必须保 record 原 levelno。纯 fd 重定向会失去 level（无法做等级路由）；逐行解析文本会被伪文本/多行污染且计划已正确拒绝。故"handle 处截获 record + fd 隔离兜底"是满足 goal 的必需组合。
- 最小性实核：`Manager.setLoggerClass` 是 stdlib 文档化扩展点（`getLogger` 用 `(self.loggerClass or _loggerClass)` 实例化，3.11.15 `logging/__init__.py:1327-1360` 实读）；既有 logger 用 `Filterer` veto（`Logger.handle` = `if (not self.disabled) and self.filter(record): self.callHandlers(record)`，实读 1636-1665）停止 handler 路由。全程未替换 stdlib 任何方法/属性；被拒方案"全局替换 `logging.Logger.handle/addHandler`"才是 monkeypatch。判定不成立。
- 边界完整：已有 logger（含 root）filter 路径 + 晚建 logger 经 `_CapturingLogger.handle` 路径；`lastResort`、自装 stdout handler、`propagate=False`、`basicConfig` 后加 handler 均被 handle 级 veto 截断；fd 持续重定向使 libc/退出 flush 与未截获路径仍只能落请求文件（raw unknown），形成兜底。source-level admission（`logger.isEnabledFor` 在 `_log` 前）与 source 自带 filter 语义保持。
- 父侧准入复用实核：转发 record 经 `logging.getLogger("dayu")`（`propagate=False`）→ 恰好一个 marker handler；handler level（`callHandlers` 的 `record.levelno >= hdlr.level`）+ 原 `_DiagnosticAdmissionFilter`（STREAM_DEBUG 正交/QUIET/普通阈值，`log.py:249-278`）即父 policy；`configure` 幂等（`_reset_marker_handlers`），重复 configure/root 双装配（`configure_root=True` 当前仓内无调用方）不会对同一 record 双发。未 configure 时按 stdlib 既有路由退化，不发明默认 destination，与现有 `dayu.*` 日志语义一致。
- 层中立：新 `dayu.runtime.process_diagnostics` 仅依赖 stdlib 与低层 JsonValue；runtime 不 import 上层；raw 等级策略归 Fins helper（计划 §3 owner 表），与 CLAUDE.md 语义所有权一致。
- 不支持路径已被显式收口：直接构造独立 Logger、重写 handle/manager、恶意保存原 fd 等不扩为本任务目标，且已声明"发现实际依赖出现此类行为即停止报告、不得偷降 record"（计划 §4.2 支持边界段）。已核实际依赖 `settings/matching` 不属此类。

## 4. 八 lens 显式应用

| Lens | 裁决 |
|---|---|
| Goal-bound minimal design | 通过。S1 唯一行为 slice 与 §6 验证矩阵逐项映射 UM-CI-N01 predicate 与既有不变量（五字段/取消/XBRL/size/digest/publication）；未新增 goal、未把抽取质量或 registry 纳入；raw→INFO 是计划自證的最小语义并已归档为用户可见残余，非新承诺。 |
| Architecture boundary | 通过。fd/记录捕获与传输在层中立 runtime；父投影经 `dayu.runtime.log`；raw 业务归类在 Fins；CLI 仅装配；未改 Host/Engine/进程治理/result queue；未把诊断塞进 conversion descriptor。 |
| Best-practice | 基本通过。stdlib 扩展点、严格 schema、首错不吞、真 spawn 负例测试符合本仓约定；偏差见 F1/F2/F3。 |
| Optimal-solution | 通过。方案对照表（fd 解析/枚举 handler/直接打开父 log-file/monkeypatch/选定方案）判断与实际代码事实相符；无更简单且满足 predicate 的替代。 |
| Overengineering | 通过。仅 4 个 frozen 小类型 + 1 异常 + 2 函数 + 私有 writer/filter/logger；无 queue/线程/telemetry/订阅/exporter；无 quota/截断等未来功能。 |
| Overcoupling | 通过。1 slice 覆盖 child 捕获+父投影+converter 接线是行为闭合的最小单元，外拆会产生半可用中间态；测试按 owner 文件分布；未绑定 registry/rollout。 |
| State machine / 执行语义 | 通过但有 F2 收口次序缺口：五字段 failure 优先级、取消/outer cancel/cleanup 优先级、require_complete 选择、成功但 side channel 非法→IPC_PROTOCOL 均与现有代码事实相容；footer 与并发 record 的退出次序未钉死。 |
| Verification / test adequacy | 强（真 spawn、真 stdlib logger、真 fd、late handler/propagate=False、lastResort/root、多线程、libc 无 newline 退出、schema 负例、真 XBRL 权限 probe、SIGINT 130），但有 F1（子进程覆盖采集）与 F3（投影异常负例）两个缺口。 |

## 5. Findings

### F1-未修复-[中]-按 §6.1 命令执行时 spawn 子进程代码不被覆盖采集，"每个生产文件≥80%"成功信号不可证实

- **位置**: 计划 §1 成功信号 5（line 21）、§5.1 迁移强制（line 162）、§6.1 验证命令（lines 164-172，尤其 line 168 的 `python -m pytest ... --cov=... --cov-report=json:...`）。
- **问题类型**: 测试缺口 / 不可直接实施（验证基座缺口）。
- **当前写法**: "每个修改/新增生产文件覆盖率至少 80%；coverage JSON 逐个生产文件核对>=80%"；同时强制"target-only 控制流测试也必须迁到独立 worker probe…不得在 pytest parent 直接永久重定向 fd"。
- **反例/失败场景**: 按 §6.1 逐字执行命令。`dayu/runtime/process_diagnostics.py` 的 `capture_process_diagnostics`、`_CapturingLogger.handle`、`_ExistingLoggerCaptureFilter.filter`、`_DiagnosticWriter`、fd 重定向辅助全部只在 `multiprocessing spawn` 子进程中执行；`docling_process_converter._DoclingProcessTarget.__call__` 体同理。仓库无任何覆盖配置让子进程自行启动 coverage：`pyproject.toml` 无 `[tool.coverage]`（grep 全文件仅 line 78 的 pytest-cov 依赖），无 `.coveragerc`/`setup.cfg`；pytest-cov 7.1.0 无 `COVERAGE_PROCESS_START/process_startup` 处理。venv 里 `.venv/lib/python3.11/site-packages/a1_coverage.pth` 是既有可用机制，但它只在 `COVERAGE_PROCESS_START`/`COVERAGE_PROCESS_CONFIG` 环境变量存在时 `coverage.process_startup(slug="pth")`（coverage 7.13.5 `control.py:1437` 实读签名支持）。该 env 不在 §6.1 命令中 → 子进程行全部计为 missing → 新模块与 converter 的"每文件≥80%"无法按计划自证达成。
- **为什么有问题**: 历史达成（`upload-material-unified-s3-implement-sol-20261003-01/coverage-final-combined.json`：converter 93.75%/416 stmts，且 330-367 子进程区行被计为 executed）依赖于现存 5 处 pytest 进程内直调 `_DoclingProcessTarget.__call__`（`tests/fins/test_docling_process_converter.py:793/871/973/1043/2252`，XBRL 分支用 monkeypatch `apply_macos_sandbox` 直调，约 2248-2252）。本计划禁止这类直调后，测量基座被移除而计划未同步提供替代采集；这会让实施 agent 面临三种越界选择：保留被禁测试、改 allowfiles 外的配置、或静默降低标准。
- **直接证据**: 上述 pyproject/无配置文件事实；`a1_coverage.pth` 逐字内容；`coverage/control.py:1437-1500`（env 驱动启动，`_auto_save=True`）；`pytest_cov/engine.py:230-285`（Central 仅对已存在的 parallel 数据做 combine，不会替用户设置启动 env）；计划 line 162 与 tests 文件直调行号。
- **影响**: 验证 gate 无法按计划字面通过；返工/越界修改风险；不涉及产品运行正确性。
- **建议改法和验证点**: 二选一并写进 §6.1：(a) 在该验收命令显式设置 `COVERAGE_PROCESS_START`（指向启用 `parallel=true` 的 coverage 配置；子进程启动依赖 venv 已有 `a1_coverage.pth`，pytest-cov Central 的 combine 机制可吸收数据文件；具体配方实施时实测确认），使 spawn 子进程行进入 coverage JSON；(b) 若不做子进程采集，则把成功信号 5 明确重述为"pytest-cov 可测面（父进程执行行）≥80% + 子进程侧行为由 worker 负例 probe 证明"，并把该口径写进 result 合同。两种改法都不动 allowfiles。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 中。

### F2-未修复-[低]-capture 退出次序未钉死 footer 与并发/迟发 record 的关系，可把成功转换误判为 IPC_PROTOCOL

- **位置**: 计划 §4.2 点 5/6/8（lines 89-90, 92）、§4.1 `read_process_diagnostics`（line 76）、§5.2 父侧次序（lines 132, 134）。
- **问题类型**: 状态机漏洞 / 并发恢复风险（收口次序规格缺口）。
- **当前写法**: "退出 flush Python 流，写 footer，结束 structured logger capture 并关闭 writer 与额外文件 handle"（line 92）；读取侧规定"读到完整 footer 以后不得还有 record"（line 134），且"若原成功但正常诊断 side channel 非法/不可读，按既有 IPC_PROTOCOL 拒绝向上返回成功"（line 132）。
- **反例/失败场景**: 退出阶段仍有并发执行体（遗留 docling 线程、atexit/finalizer 钩子）在 footer 已落盘之后、scope filter 移除/ writer 关闭之前发出一条完整 record → `records.jsonl` 在 footer 后出现合法行 → 父侧成功分支按"footer 后不得还有 record"判为 side channel 非法 → IPC_PROTOCOL → 一次真实成功的转换被拒绝发布（无半成品，但业务失败）。反之若实现先把 writer 关掉再让并发 record 写入，则存在写已关闭/复用 fd 的风险窗口。
- **为什么有问题**: 计划对"成功"施加了 footer 严格不变量，却没有规定捕获侧退出的原子次序（移除 filter/恢复 loggerClass/清空 writer 槽、flush、footer、close 的相对顺序与锁参与）；这是 code-generation 必须自行发明的契约细节，两位实施者会做出不同选择。
- **直接证据**: 计划 line 92 的字面顺序（footer 在"结束 capture"之前）；line 90 仅规定 writer 用锁串行化记录，未规定 close 与在途/迟发 record 的次序；lines 132/134 的不变量与拒绝规则。
- **影响**: 低概率但在真实第三方栈上可触发；后果是成功转换被误拒（可恢复，rmtree 正常），或退化为 fd 窗口风险；不影响已失败/取消分支的既有优先级。
- **建议改法和验证点**: 在 §4.2 点 8 明确退出序列：先把 writer 槽在锁内置为关闭态（此后到达的 record 走既有"raw 兜底"路径即 fd 文件，而不是结构化写作）、移除 scope filter、恢复 manager loggerClass；再 flush、写 footer、关闭 writer 与额外 handle；或等价地让 writer 把 footer 后写入记为 transport first-error 并在 scope 外 surfaced。验证点：一条"退出竞态"负例（worker 内让后台线程在 scope 退出同时持续 emit），断言 records.jsonl 无 footer 后记录、成功不被误拒、迟到字节仅以 raw 形式存在。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 低。

### F3-未修复-[低]-child 侧逐 record 投影异常（message 格式化/created 异常）的 containment 未显式规定，负例不在测试矩阵

- **位置**: 计划 §4.2 点 6（line 90）、§4.3（line 98）、§6.1 测试行（lines 154-155）。
- **问题类型**: 契约缺失 / 测试缺口。
- **当前写法**: "记录写入首错但不让 logging callback 将其误分类为 conversion execution；退出 surfaced typed error"（line 90）；"exception/stack 内容在 child 按 stdlib Formatter 处理后加入 message"（line 98）。测试矩阵覆盖了读取侧的 schema/坏 JSON/footer 负例与写入首错回收，但未覆盖 child 捕获时的逐 record 投影异常。
- **反例/失败场景**: 第三方以 `logger.warning("%d", "x")` 之类坏参数发日志。基线 stdlib 下 `getMessage()` 的 ValueError 发生在 handler 格式化阶段，由 `Handler.handleError` 吞掉，`logger.warning(...)` 调用方无感（最常见表现为一行 stderr 诊断）。本方案在 `Logger.handle` 内、任何 handler 之前投影 record：若投影（`getMessage()`、格式化、编码）未逐条包裹，异常会穿透进第三方调用栈；docling 的转换 except 会把它归类为 CONVERTER_EXECUTION——正好违背计划 line 130 "不得把 diagnostic I/O 错套成 conversion_execution"。若 `created` 非有限值、`name` 非 str 等异常输入同理。
- **为什么有问题**: "记录写入首错"字面只覆盖写错误；投影异常是新引入的、位于第三方调用栈内的失败点，必须像 stdlib 自身一样"永不向 logging 调用方抛出"，并以同一首错语义在 scope 退出时 surfaced。这是可实施性契约缺口而非风格问题。
- **直接证据**: stdlib 3.11.15 `Logger.handle`→`self.filter`/`callHandlers` 路径（本方案插入点位于 handler 级 `handleError` 之前）；计划 line 90 措辞只点名"写入"；line 98 要求 child 做 Formatter 处理（本身可抛）；§6.1 负例清单无此场景。
- **影响**: 第三方记录格式异常时转换被误分类为 CONVERTER_EXECUTION（失败五字段固定文案，用户可见失败）；概率低，但属于新引入的行为回归面。
- **建议改法和验证点**: 在 §4.2 点 6 显式写明：逐 record 的投影、编码、写入全部位于同一 try 域；任何异常记为 capture first-error（记录安全上下文，跳过该条投影），绝不向 logging 调用方抛出；scope 退出按既有首错/typed error 规则 surfaced。§6.1 增一条负例：坏参数 record 与非法 `created`/`name`，断言 conversion 结果分类不变、first-error 按规则 surfaced、公共双流无输出。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 低。

## 6. Open Questions

1. §6.1 命令附带运行 `tests/runtime/test_macos_sandbox.py`、`tests/fins/test_docling_upload_service.py`（回归运行），但 §5.1 写 allowfiles 仅含 5 个测试文件、不含这两个。请 controller 明示"只运行、不改写"；若因本 slice 它们需要修改，应走追加 allowfile 裁决，避免实施 agent 越界（当前不构成 finding）。
2. raw 固定 64 KiB 块边界可能截断多字节 UTF-8，`backslashreplace` 会把同一字符在两块中各显示为转义片段。计划已声明"非 UTF8 字节可确定解码"（§6.1），是否接受该低影响显示噪声；若不接受，需在块边界做 UTF-8 尾缀保序（成本小但属新语义，需写入计划）。
3. 计划 §8 称"root planreview 裁决"raw 最小语义是否需用户决策。本 review 的裁决：按已接受 predicate（quiet/log-file/等级路由）不需要新用户决策，raw→INFO 路由与逐条 `source_level=unknown` 前缀是一致的可行最小语义；仅当用户后续要求"原生错误文本在高等级下也不得丢失"时才需回到用户。

## 7. 残余风险与去向分类

| 残余 | 分类与去向（按计划 §8 + 本 review 实核） |
|---|---|
| raw 高等级省略、三路无全局时间序、收口后才投影 | 已在计划内接受的最小语义（fixed-in-scope 语义选择）；user-decision 仅在更强保证时；本 review 判定无需发起新决策。 |
| 外部自建 Logger/独立 manager/重写 handle/强杀丢缓冲/脱离进程组 daemon | 已授权 later WU（runtime/converter owner）；实核当前依赖（settings/matching）不属此类，不阻塞本 slice。 |
| diag 文件增长/无 quota | 已授权 later WU（runtime owner）；本 slice 只保证写入失败显式 surfaced。 |
| Docling 抽取质量、table matching 内容 | 非本 goal；upstream Docling owner，later WU。 |
| registry/scenario 登记、campaign ready、原 802 verdict | 独立 registry WU / root controller（本 review 未审、未写其工件）。 |
| Windows/Linux 平台行为 | 用户已延期；本 slice 仅 macOS arm64 Py3.11 验收，计划无越界声明。 |
| 覆盖率测量面（本 review F1） | fixed-before-implementation 建议对象：§6.1 命令/口径修订，建议在实施前由 controller 接受；若接受为 implementation-gate 内解决则升为 gate prerequisite。 |
| 64 KiB UTF-8 边界噪声（OQ2） | 本 slice 可接受残余（计划已声明可确定解码），实施时若用户在意再升 finding。 |

## 8. 实际检查、工具问题与恢复、未运行项

- 实际检查（全部只读）：计划/契约/授权文件 SHA 与逐字内容；冻结场景 bytes；两份 venv 的第三方源码 SHA；stdlib logging 语义逐段实读；CLI/converter/runtime/xbrl_config/docling_runtime 源码；pyproject/README 边界；测试文件结构与直调点；覆盖 artifact 与覆盖启动机制；旧 CI root 输入存在性。
- 工具问题与恢复（如实记录，无掩盖）：一次 zsh 命令中 `echo ===` 被 zsh 的 `=cmd` 展开规则吞掉，报 `(eval):1: == not found`，使同一链尾部的 `shasum` 未执行；随后改用引号重跑，取得全部预期 SHA。`grep def process_startup` 在前两个候选文件无命中，改为包级检索定位到 `coverage/control.py` 后读实。除这两次外无其它失败；未出现"打印 traceback 即视为工具 crash"的混淆。
- 未运行（按授权约束）：pytest、pyright、真实 CLI/Docling/provider/network、任何产品/计划/测试/registry/locks/他人 artifact 的写入；未派发子 Agent；未 commit/push/branch/worktree 操作。本报告与 `review.json` 是唯一写入。
- 产品变化：**无**（product_writes=false）。

## 9. 结论

**pass-with-risks。** 计划目标绑定 UM-CI-N01 已接受 predicate、owner 划分与直接证据扎实、机制（filter + `setLoggerClass` + fd 持续重定向 + 父 marker handler 投影）经 stdlib 3.11.15 与真实安装源码实核成立且非 monkeypatch，1 slice/allowfiles/负例矩阵总体 code-generation-ready。三个 finding 中 F1 需在实施前修订验证基座或口径，F2/F3 是两处小规格缺口，均给出一行级最小改法与验证点；不构成 blocker，不改变计划方向。

## 10. 源引用 SHA 汇总（本报告引用真源）

- plan：`a58b95afbc9898969bf85e0c79ed0d3597339d2bbc3ddd420aedc80d30bf7289`
- HEAD：`79977b3a52f8566672e3b462f786f1004dfd3f89`（branch `codex/upload-material-oracle`）
- goal-confirmation：`63ca599bee4ae401714281f8a7501c63b0c6b1b1024447a01ae1f6ed9d799a06`
- oracle-candidates（含 user_adjudication）：`dbeb48a6cff69e477034adf9e57e0b8dcf09fe0147ea64132df5992c75deec46`
- converter owner：`d6b6772e329c66045f634fb4994c76bbcb9ef0130d3fe498b2e7f044ae6cd1b8`
- parent runtime log owner：`908e90c85ca7d1c6281d5296667933d7eee0768cb2bfd7554bc1b0fb75d19069`
- O29 adjudication：`1ea88fbbdb2342c144ead9819636324eb8789154caccda8c791dfc191d0db922`
- installed settings（两份一致）：`68aacd3855426e2ccc6804f51e797323dca9bfbef034fa8b49a243d81920004a`
- installed matching（两份一致）：`0675880799c3474bfe0355c3fe81a105d87ac0f2cdb2f51a4699a9f4096cebe3`
- frozen stdout.bin：`8b2b38db9a414058ff7027895d5d21abb4b2384433ed8dc035743825580056be`（19,741 bytes，129 行 MatchingPostProcessor WARNING）
- frozen stderr.bin：`e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`（0 bytes）
- 冻结报告：`f35d33f5ff62b1e45d6f6ecf7ae1bcf7db4139f33c5b2af714e59ea0680ef53c`（计划 §10 引用，本 gate 未整读）
- 本 artifact：见 `workspace/tmp/upload-material-converter-diagnostics-plan-review-ds-flash-20261003-01/review.json` 中 `artifact_sha256`。
