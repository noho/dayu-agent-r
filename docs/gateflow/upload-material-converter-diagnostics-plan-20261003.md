# UM-CI-N01-F01：转换器诊断遵循父进程日志规则

- Work unit：`upload-material-converter-diagnostics`；集中修订任务：`upload-material-converter-diagnostics-plan-fix-sol-20261003-01`（原 plan-sol-01 版本已独立保全）。
- Gate：plan fix；状态：code-generation-ready 修订候选，待同版双 re-review 与 root 接受；尚未实施或验收，非 gate pass。
- 唯一 workspace：`/Users/leo/workspace/dayu-agent-r`；实核 branch `codex/upload-material-oracle`；HEAD `79977b3a52f8566672e3b462f786f1004dfd3f89`。
- 绑定依据：`workspace/tmp/upload-material-converter-diagnostics-20261003/goal-confirmation.md`；新 predicate 的明确 accepted 依据是 `workspace/tmp/upload-material-unified-repair-20261002/post-wu-preparation/oracle-candidates.json` 的 `user_adjudication`。synthesis JSON 初始 pending/unadjudicated 不覆盖其后的用户接受与 synthesis Markdown 后续裁决。
- 本计划只有 **S1 一个行为 slice**。本次仅修本文件、写 `docs/gateflow/upload-material-converter-diagnostics-plan-fix-20261003.md` 与独占 `workspace/tmp/upload-material-converter-diagnostics-20261003/plan-fix-sol-01/`。plan-only 后停止来自父 Agent 本次派发边界，**不是主用户 pause**；root 按已授权目标继续全部 gates。绑定 root 裁决为 `docs/reviews/plan-review-upload-material-converter-diagnostics-root-adjudication-20261003.md` 和本 WU `root-plan-review-adjudication.json`；两审 pass-with-risks 不构成放行。

## 1. 目标、动机与成功信号

第三方转换诊断不得进入业务 stdout 或公开 stderr；有 log-file 时按当前 CLI 等级追加进入该文件，无 log-file 时进入当前 CLI 的临时诊断流；quiet 关闭诊断，仍输出公共业务进度与终态。修复发生在 converter 的 child 诊断产生/隔离边界和 parent 公共日志投影 owner，不能通过 CLI 字符串过滤实现。

问题真实成立，但严重性限定为诊断通道违例。冻结 91 页 PDF 运行已 exit 0、成功生成 Docling 并发布权威 manifest，不是转换失败或抽取质量缺陷。旧 UM-O29 仅接受其已测 direct CLI Print/log 行为；本次依据用户新增 accepted UM-CI-N01，不把 reviewer 共识当授权，不改冻结 run 的过去 verdict。

成功信号：

1. owner 测试证明真实第三方 Python WARNING 的原等级进入父侧同一准入规则，quiet/高等级 selector 不可被第三方自装 handler 绕过。
2. converter 范围 fd1/fd2 的文本、原生写入及继承这两个 fd 的后代输出不进入公共双流；有源等级的 record 与无源等级的 raw 字节分开传递。
3. 一份完整真实 PDF 的 default、quiet、显式 log-file、error 阈值组合在 fresh CI root 实验中保留正确业务结果；显式日志有真实 MatchingPostProcessor WARNING 的正例。
4. 原 closed descriptor、五字段 conversion failure、size/digest、fingerprint/version、原子 publication、公司独立更新、SIGINT 130 与资源 cleanup 保持；真实受控 XBRL 正例及禁止权限未回归。
5. 受影响测试通过；每个修改/新增生产文件覆盖率至少 80%；仓库完整 pyright 为 0 errors；README 按职责判断；后续正式双审及 root 裁决依 gate 顺序进行。

## 2. 非目标与边界

不改 Docling 提取结果或 table matching 算法，不接受抽取质量目标；不改日志 selector、日志格式、Print 业务输出、public summary/schema；不重开原已闭产品 WU；不登记 oracle/scenario/readiness；不改 locks、依赖源码或版本。纯登记 WU 的文档与控制文件由另一任务独占。

不改 Host/Agent/Engine，不生成 direct CLI 的 Host Run、trace、memory 或 durable job；不把诊断当财报事实。不改变进程启动/结果队列/terminate→kill→close 协议。不为日志扩大 XBRL 的系统权限、读取范围、平台范围、网络范围或 taxonomy 来源；child 不收到用户 log path、parent log stream 或 parent workspace 能力。

本 gate 仅可执行独占目录的必要 stdlib/coverage 小探针（可仅对此做 pyright），不执行产品测试、真实 CLI、Docling、provider 或网络，不提交、push、更新 PR，不新建 branch/worktree/clone，不 reset/stash/clean，不派发子 Agent。禁止写源 frozen evidence、旧 CI `.venv`、private、admin、workspaces 或其它 WU 控制文件。

## 3. 直接证据与第一性原理 owner 判断

| 真源/位置 | 实核事实 | 对设计的约束 |
|---|---|---|
| `dayu/fins/pipelines/docling_process_converter.py:104` `_isolated_inherited_stderr` | 仅隔离 fd2，写往 devnull；动态范围只包 conversion 调用 | 同时隔离 fd1/fd2，保存诊断；不能扩成 UI filter |
| 同文件 `_DoclingProcessTarget.__call__`（316 起） | 应用 XBRL 策略/复验后转换，随后 export，finally unload；这些动作不全在现有隔离范围 | child target 的完整第三方工作生命周期都须处于诊断边界内 |
| 同文件 `ProcessDoclingConverter.convert_to_json_bytes`（448 起） | 独占 temp、spawn、wait、close、descriptor 校验、rmtree、终态 | child 诊断交父发生在既有 close 后、temp 删除前；不能使进程治理依赖日志 |
| 已安装 `docling_ibm_models/tableformer/settings.py:5,22,41` | `get_custom_logger(..., stream=sys.stdout)`；`StreamHandler(stream)`；模块 import 就创建 LOGGER | 只在转换后枚举 handler 太迟；不能解析 WARNING 文本反推等级 |
| 已安装 `.../data_management/matching_post_processor.py:24-29` | `_log()` 按需 `get_custom_logger(self.__class__.__name__, logging.INFO)`，真实 warning 由此 logger 产生 | logger/handler 可在转换中才出现，须在其 `handle(LogRecord)` 前截获 |
| `dayu/runtime/log.py` `configure_selected_diagnostics/configure/_DiagnosticAdmissionFilter` | canonical selector →数值阈值；普通阈值与精确 STREAM_DEBUG 正交；quiet 显式拒绝 | 父侧复用当前 marker handler 的 level 与 filter，不复制 policy，不从 logger effective level 反推它 |
| `dayu/cli/main.py:99-118,160-199` | 显式日志 append；默认 TemporaryFile；退出后配置清理并关闭流 | child 无需知道 destination；诊断在 CLI finally 关闭流之前交回 |
| `dayu/runtime/interruptible_process.py` | JSON result target、独立 session、typed wait、进程组 cleanup | 不把诊断塞进原 conversion descriptor，不修改 result queue 语义 |
| `dayu/runtime/macos_sandbox.py` 与 converter `_build_xbrl_sandbox_profile` | 默认 deny；只为 prepared.writable_root 授写；input/taxonomy/runtime 只读，无 network allow | 新诊断文件必须在原 work 下，不能放在其 sibling 或直接打开用户日志 |

本地 `.venv` 与冻结 CI `.venv` 上述 settings 和 matching 源码字节 SHA 相同，已真实读取两份，不靠 warning regex 推定根因。stdlib Python 3.11 logging 源码也已核对：`Manager.getLogger` 使用 manager/global logger class；`Logger.handle` 先执行 source filter，再 callHandlers；parent 的 filter 不会自动检查 descendant，故仅加 root filter/handler不足。

语义 owner：

- **用户选择、目的地及准入**：`dayu.runtime.log`；CLI 只装配，第三方库不拥有公开 destination。
- **日志源等级与消息**：源 `logging.LogRecord`；只投影 `name/levelno/getMessage()/created` 及已有 exception/stack 文本，不重算 level、不从字符串猜业务意义。
- **无等级 raw 的业务归类**：Fins converter target 认定其完整动态范围输出是转换诊断；Fins 明确为这种输出选 INFO 路由等级。runtime 只携带 channel/bytes，不建立全系统 raw 等级规则。
- **跨进程保存/读取、fd 隔离机制**：新增层中立 `dayu.runtime.process_diagnostics`，只依赖 stdlib 与低层 JsonValue。
- **child failure 与成功输出完整性**：原 converter；**进程/取消治理**：原 interruptible_process；**材料 publication**：原 storage/workflow。均不转移到诊断 helper。

## 4. 可实现方案比较与选定方案

| 方案 | 判断 |
|---|---|
| 重定向 fd1/fd2 后逐行解析日志文本 | 能挡双流，但丢原 level、logger 身份；解析伪造或多行文本不可靠，拒绝 |
| child root handler +一次 handler 枚举 | 可控制已知 stdlib propagation，后创建的自有 handler/propagate=False 能绕过；不足 |
| child 直接 configure 并打开父 log-file | spawn 无父 policy、默认流不可传；破坏 XBRL 隔离，拒绝 |
| 以全局替换 `logging.Logger.handle/addHandler` 等方法捕捉所有 handler | monkeypatch 变框架、难恢复和验证，拒绝 |
| child 有限 stdlib logger capture +请求内磁盘 side channel +父 marker handler 投影 | **选定**：保 record 原等级，晚创建 logger 自有 handler 不执行；fd 覆盖非 logging 写入，父 owner 控制去向 |

不加 queue feeder、pipe reader thread、额外进程、异步 telemetry、日志订阅系统或通用 exporter。文件 side channel 在本请求现有 temp/work 内，child 同步追加、父 close 后串行读取，避免日志 pipe 反压妨碍取消。延迟到 conversion 收口才出现诊断是明确限制，本 goal 不承诺实时日志。

### 4.1 精确新类型与接口（DN-R1/R2/R3/R6）

新增 `dayu/runtime/process_diagnostics.py`：

- `ProcessLogDiagnostic`：frozen/slots，字段 `source_name: str`、`source_level: int`、`message: str`、`created_at: float`。不传 args、异常实例、extra 或 opaque payload。
- `ProcessRawDiagnostic`：frozen/slots，字段 `channel: Literal["stdout", "stderr"]`、`data: bytes`、`offset: int`；**没有 source_level**。
- `ProcessCaptureIncidentCode(StrEnum)`：唯一封闭值 `record_validation`、`record_format`、`record_encoding`、`record_write`、`recursive_record`、`scope_setup`、`scope_flush`、`logger_teardown`。只描述诊断 capture，不能代表 conversion failure。
- `ProcessCaptureIncident`：frozen/slots，唯一字段 `code: ProcessCaptureIncidentCode`；不携带坏 record、异常对象/异常字符串、业务状态或路径。
- `ProcessDiagnostic: TypeAlias = ProcessLogDiagnostic | ProcessRawDiagnostic | ProcessCaptureIncident`。
- `ProcessDiagnosticsFailureReason(StrEnum)`：`isolation_setup`、`transport_read`、`transport_invalid`、`transport_incomplete`。`ProcessDiagnosticsError(RuntimeError)` 持显式 `reason: ProcessDiagnosticsFailureReason`，消息只用模块固定安全常量，不调用坏对象 `str()`。
- `capture_process_diagnostics(directory: Path) -> Iterator[None]`：contextmanager，**独占一次性同步 worker 的公共寿命契约**。只能在第三方导入/执行前进入一次，不供 parent、嵌套 scope 或同进程下一请求使用。仅进入时不能建立 fd1/fd2 隔离抛 `ProcessDiagnosticsError(ISOLATION_SETUP)`；fd 已建立后的诊断 setup/record/drop/spool/flush/logger 撤销/额外 handle close 普通 Exception 均局部 containment，退出不向 body 抛普通诊断异常，也不 suppress body 原异常。控制流 BaseException 保原传播，清理规则见下文补充。退出只收 structured capture，**不恢复 fd1/fd2**，映射一直保到 worker 最终退出（含框架/native finalizer 实际 flush）。不加 profile/factory/bool restore 策略。
- `read_process_diagnostics(directory: Path, *, require_complete: bool) -> Iterator[ProcessDiagnostic]`：parent 确认 close/join 后流式读取。严格 schema；正常退出要求 end，强制取消/crash 可以读取完整前缀，但 EOF 缺 end/半行在已 yield 前缀后仍以 `TRANSPORT_INCOMPLETE` 通知 parent；不能把坏完整行或半行当 record。参数只决定能否消费未完成前缀，不创造业务成功条件。
- 私有 `_DiagnosticWriter.try_capture(record: logging.LogRecord) -> bool`（True 表示本 scope 已接管，包括 incident/drop；False 表示 closing/closed，调用者走 scope 外原 stdlib 路由）、`_DiagnosticWriter.close() -> None`、`_ExistingLoggerCaptureFilter.filter(record: logging.LogRecord) -> bool`、`_CapturingLogger.handle(record: logging.LogRecord) -> None`；模块级 `_project_record(record: logging.LogRecord) -> ProcessLogDiagnostic`、JSON 编解码、fd 与 handle 回收辅助函数。所有参数/返回严格 typed、完整中文 docstring；不覆写 opaque `Logger._log/makeRecord`，不引入 Any/object 签名。

私有构造与调用参数固定为 `_DiagnosticWriter(records_stream: BinaryIO | None)`（流由 capture 在双 fd 建好后打开，writer 唯一负责 records close；None 为媒体不可用）、`_ExistingLoggerCaptureFilter(writer: _DiagnosticWriter)`；`_CapturingLogger` 继承 stdlib 构造，不覆写 opaque 构造签名。`_ProjectionState(threading.local)` 声明 `depth: int = 0`，`_WriterState(StrEnum)` 仅 OPEN/CLOSING/CLOSED，另 `spool_faulted: bool` 表示不能继续结构化追加。`_DiagnosticWriter.note_incident(code: ProcessCaptureIncidentCode) -> None` 只接封闭 code，内部含自己的存储失败；try_capture 的外层普通 Exception containment 包括 guard/reservation/投影/编码/write/incident/finally，不允许 incident 的普通错误逃出 logging；控制流 BaseException 原样传播，finally 仍释放 depth/reservation，绝不记成诊断成功或普通 incident。scope setup 普通诊断 Exception 撤销已安装项并保双 fd，不回抛；scope 不会要求 converter 持有 writer 或诊断状态。

`dayu/runtime/log.py`：新增 `emit_process_log_diagnostic(diagnostic: ProcessLogDiagnostic) -> bool`，以及唯一私有 `_DiagnosticStreamHandler` 与其 `try_deliver_process_record(record: logging.LogRecord) -> bool`（DN-R7）。该子类的 base 使用模块级 `_DiagnosticStreamHandlerBase`：TYPE_CHECKING 分支为 `logging.StreamHandler[TextIO]` typed alias，运行分支为 stdlib `logging.StreamHandler`（Python 3.11 运行类不可下标化；不是兼容 shim），自身 `stream: TextIO` 明确声明。`_build_marker_handler` 仅将构造类型换成该子类；原 stream、handler.level、同一个 `_DiagnosticAdmissionFilter` 实例、formatter/datefmt、marker 属性/值、configure 装配与 `_reset_marker_handlers` 去重规则均不变。子类不覆写 `emit/handleError/handle/flush`，所以普通 logger 调用仍走原 stdlib 行为；只有本 helper 使用专用方法，不扩大其它普通日志的故障策略，不新增 owner 或生产 allowfile。

helper 构造干净 LogRecord，name/levelno/msg/created 分别保原 source name/level/message/created_at，无 args/exception/extra；从 `logging.getLogger("dayu")` 先执行 `isEnabledFor(record.levelno)`、disabled 与该 logger 原 filter，正常拒绝返回 True。随后仅从该 namespace 的 handlers 以 `isinstance(handler, _DiagnosticStreamHandler)` 取得唯一 owner；未 configure/缺失/非唯一时返回 False，**不得调用 namespace.handle/callHandlers、root、lastResort 或第三方 logger 兜底**，也不创建目的地。configure_root 的同目的地 twin 不再被本 helper 遍历，重复 configure 仍由原 marker 去重。这个必要的父投递边界替代此前未 configure 的 stdlib 路由，防止该路由自身写公开 stderr；不改其它调用者的路由。

专用方法在一个仅 catch Exception 的完整边界内按 `record.levelno >= self.level` 再 `self.filter(record)` 准入（只调用现 filter，不重新解释 selector），拒绝返回 True；准入后 `self.acquire()`，在 try/finally 中依次 `self.format(record)`、`self.stream.write(message + self.terminator)`、`self.flush()`，finally `self.release()`。完整完成返回 True；构造、logger/filter、handler/filter、锁或 format/write/flush/release 的普通 Exception 返回 False。**不调用 StreamHandler.emit/handleError**，因为 emit 会自行消化 Exception 后向公开 stderr 报告；不采用全局 raiseExceptions 开关、方法 monkeypatch、CLI 过滤或另建 handler/formatter/filter 副本。False 不承诺目的介质回滚已写部分，只表示本次投递失败；不递归报告、不重试、不写公开 fd。KeyboardInterrupt/SystemExit/asyncio.CancelledError/GeneratorExit 不在 Exception containment 范围，finally 释放已取得锁后传播同一对象，不返回 False 或降为 secondary。

`dayu/fins/pipelines/docling_process_converter.py`：新增 `_forward_converter_diagnostics(directory: Path, *, require_complete: bool) -> None` 与 `_emit_converter_secondary_diagnostic() -> None`。log 直接交公共 helper；raw 构造 converter-name 的 `ProcessLogDiagnostic`，`source_level=INFO_LOG_LEVEL` 只为 **路由等级**，message 固定前缀含 `raw_channel`、`source_level=unknown`、byte offset，附 UTF-8 backslashreplace 字节显示。capture incident 不是正常源 record：Fins 生成独立 WARNING 安全诊断，固定中文前缀“转换诊断捕获异常”，仅追加封闭 code.value。read/schema/footer/parent projection 的普通 Exception 只触发一次固定安全 WARNING“转换诊断不完整或无法留存；转换结果按原规则处理。”。两种派生诊断都经公共 helper；helper False 或 reporting 普通 Exception 就结束本次报告，无 raw/public stderr/旧路径兜底、无重试循环；控制流不在此 containment 范围。quiet 仍经同一公共准入关闭所有这些诊断。raw/incident 的路由语义只有此 Fins owner 产生。

### 4.2 Child 捕捉机制与边界

1. parent 只建本请求独占诊断目录（0700），非 XBRL 在原 temp_root，XBRL 在 `prepared.writable_root/diagnostics`。child 按 runtime 文件名常量创建 `stdout.bin`、`stderr.bin`、`records.jsonl`（0600）。raw 文件/目录/dup2 失败而不能确保双 fd 隔离属于 ISOLATION_SETUP，第三方不得启动；records 文件打开失败发生在 fd 隔离成功后，仍构造 `_DiagnosticWriter(records_stream=None)` 并安装同一 capture filter/logger class；writer 保 OPEN 且 `spool_faulted=True`，try_capture 仍接管/drop，不把 structured record 放流到 raw；双 fd 边界保持。parent 通过 records 缺失/不完整观察缺 carrier，不阻止原转换；媒体坏不承诺完整留存或故障逐项自报。
2. 进入在 sandbox application/verification/第三方导入前：尝试 flush 现 Python 标准流（flush fault 为 secondary，不阻止后续 dup2）；先 fd2 再 fd1 `os.dup2` 到请求文件。**不复制、保留或恢复原公开 fd**，后代继承标准 fd 仍写请求文件；只在退出关闭额外打开的 handle，fd1/2 由 OS 退出关闭。不能以替换 sys.stdout 或 devnull 代替。parent 从不进入 helper，标准流不变。部分重定向失败仅关闭额外 handle 并停止 target 第三方路径，不尝试恢复公开 fd。
3. 对现标准 manager registry 的 Logger（含 root，排除 PlaceHolder）安装 scope filter。capture OPEN 时 `try_capture` 接管该条，filter 返回 False 阻断自装 handler/lastResort；closing/closed 的 stale filter 返回 True，只恢复原 logger 路由，输出仍在原请求 raw fd。不读 registry 反推 policy；不改变原 levels/handlers/propagate/disabled。
4. `manager.setLoggerClass(_CapturingLogger)` 使晚创建 logger 在 handle 截获；保持原 source disabled/filter 与 `_log` 前 source-level admission，接管时不执行 child handlers。handle 先取 typed writer 槽：None 时直接 `super().handle(record)`；有 writer 时先按 stdlib 检查 disabled/filter，允许后调用 try_capture；若此时已 closing 返回 False，只 `self.callHandlers(record)`，不重复执行 source filters。新类与旧 filter 不对同一 record 双发；scope 内显式晚加 stdout handler/propagate=False 仍不可绕过。
5. 新类的 writer 槽只在独占 scope 有效；退出将 `manager.loggerClass` 恢复进入时保存的精确原值（含 None），移除本 scope 的 filters，清空槽；保留现 logger 原属性。这是 typed stdlib class 状态恢复，不替换 logging 的任何方法，不用 handler 方法 monkeypatch，不加白名单/factory/query 框架。
6. **投影完整 containment**：先严格验证 name 为 str、levelno 为 int 非 bool、created 为有限 float/int 非 bool（转换 float 溢出也属 validation），stack_info 为 None/str；然后 `getMessage()`、stdlib Formatter.formatException/formatStack 合成 message，JSON 编码（ensure_ascii=False、allow_nan=False、UTF-8）、完整 write/flush 都在诊断 catch Exception 边界。任何普通 Exception 跳过该 record，按上述阶段记封闭 capture incident；绝不造正常 record、拼坏对象 fallback、调用 handleError/当前 logging 或将异常抛回第三方。异常 `__str__` 抛错在本 Python 的 stdlib traceback 会输出 `<exception str() failed>`；这是 Formatter owner 的真实格式化结果，允许保留，不谎称一定抛错或强造 incident。真正 Formatter 失败仍记 record_format。record_write 后若可能留下部分行，writer 标 spool faulted，不再追加/补 footer 冒充完整；媒体同时坏时不保证自报。
7. **锁与在途 emit（DN-R2）**：writer 状态 OPEN → CLOSING → CLOSED，Condition(Lock) 只保护状态、active reservation 数、完整行追加、incident 与 footer。OPEN 的 try_capture 在锁内 active +=1 后释放锁，投影/第三方 getMessage/Formatter 在锁外执行；append 在锁内，finally active -=1 并 notify。CLOSING 拒绝新 reservation；已取得 reservation 的 healthy emit 必须完成完整 record 追加，CLOSING 本身不能令它 drop；只有真实投影/编码/spool fault 可按既定 incident/transport 缺口接管/drop，close 等 active=0 才写 footer。typed threading.local 子类的 depth 显式字段保护同线程投影递归：nested logger 调用记 recursive_record 且接管/drop，不做嵌套投影；这条 guard 在取得 reservation 前检查，故 getMessage 内递归 logger 不会卡在本线程的 writer 锁或 close 等待上。测试不能仅靠普通 RLock 掩盖无限递归。
8. **关闭唯一序列**：scope body（含 Docling unload）结束 → 锁内置 CLOSING、拒绝新 reservation → 释放 writer 锁 → 撤销 filters/恢复 loggerClass/清空槽（不在 writer 锁内取 stdlib logger 锁）→ Condition 等在途 active=0（wait 释放锁）→ 尝试 flush Python stdio/关闭额外 raw handle，pre-footer 的这些普通 flush/close 故障统一记 scope_flush（介质健康时可留存） → 锁内写 pending incident、exact end、flush/close records writer → 置 CLOSED。仅已取 writer 引用但尚未取得 reservation、随后在 CLOSING/CLOSED 被拒绝的新 emit 走原 stdlib/raw 路由；已有 reservation 的 emit 按上一项完成或因真实 fault drop，不转 raw；footer 后绝无 log/incident 追加。撤销故障逐项继续尝试，stale filter/writer 的关闭态仍保 raw 边界。收口普通诊断 Exception 都局部包含，不抛回 body；若 cleanup 收到控制流 BaseException，先保存原对象、继续资源回收，再原样 re-raise，不降为 secondary/success；body 原异常原样通过，不将 failure descriptor 当异常重分类。fd1/2 始终不恢复。post-footer records close/额外清理故障没有新持久载体，不能追加 footer 后 incident，**只承诺 parent 实际可观察的故障**，不承诺该阶段逐项自报。
9. **唯一 incident carrier（DN-R3）**：records JSONL exact log keys 保持 `schema_version=1, kind="log", source_name, source_level, message, created_at`，name/message str、level int 非 bool、created 有限数非 bool。另允许 exact `{"schema_version":1,"kind":"capture_incident","code":"record_format"}`，code 仅 §4.1 枚举值；不是 log、不是财报事实。收口最后一行仍 exact `{"schema_version":1,"kind":"end"}`，不加 payload。incident 必须在 footer 前且 writer 健康时追加；write/全媒体损坏仅 parent 能观察的 transport 不完整，禁止备用媒体/新框架来保证自报。正常缺 footer、footer 后任意内容、错 keys/type/version/非法 JSON 均 typed transport error；cancel/crash 可 yield 完整前缀再报 incomplete；不把 transport error 或正常完整 footer 用来反推业务结果。

**DN-R1 控制流边界补充**：绑定 root 本轮追加的 `root-control-flow-clarification.json`（原/新版 root Markdown 两 SHA 均保全）。仅普通 Exception 可 containment 为 capture incident/secondary。KeyboardInterrupt、SystemExit、asyncio.CancelledError、GeneratorExit 都必须原样传播；不能因 helper 同步、业务已成功或 quiet 而吞掉。try_capture 的 finally 无条件释放 reservation/depth；close 可暂存控制流以尝试其它资源，随后 re-raise 同一对象。已有 body 控制流优先保原对象；没有 body 控制流而 cleanup 新收到控制流则保首个新控制流，普通诊断 fault 不替换它。body 普通异常不妨碍新控制流原样退出。目标要求“不改 primary”同时包含这个控制流合同，不是新增日志业务 gate。

支持边界是本次实际已安装转换栈的 stdlib manager/getLogger/Logger.handle 路径。绕过 stdlib manager直接构造独立 Logger或改写其 handle/管理器、恶意寻找保存 fd、第三方主动重置 capture class，不扩为本任务的日志框架目标；这些输出即使落 fd capture 也只能有 unknown raw语义。不能据此宣称所有任意第三方 Python 实现均可保原等级；若实际支持的依赖新增这种行为，停止实施并报告证据，不能偷偷降格其 record。

### 4.3 原等级与 raw 最小确定语义

Python record 的 levelno不变，不能把 WARNING当 INFO、固定升级 ERROR或按文本重算。exception/stack 内容在 child 按 stdlib Formatter处理后加入 message；不增加 source payload_ref、digest 等内部标签给 LLM，也不投影成 business summary。

raw 没有可信原 severity；Fins 对 **converter worker raw** 仅选 INFO 路由等级（含 structured scope 外 finalizer 仍落原 fd 的字节）。这是 root 已裁的最小技术路由，不是用户逐字接受的 raw-INFO 新 oracle。文本即使出现 WARNING/ERROR也不影响它。info/debug/verbose 可留存 raw，warning/error/critical 会省略 raw，quiet全部拒绝；日志前缀始终标源等级 unknown。真实错误仍由原 typed conversion failure决定，不能以 raw推断成功/失败。风险：高等级 selector 可能省略真实原生错误文本；未接受“所有 raw 都是 warning/error”，不泛化为 Host/Runner/其它 subprocess policy。

## 5. S1：一个完整行为增量

**目标/产物**：一次 converter调用中所有可识别 Python诊断及 fd写入遵父公共日志规则，公开业务输出不受诊断 selector影响。只有 S1 一个 implementation 行为增量及其 code review/fix/re-review loop，不按 fd/stdlog/CLI/runtime拆 slice。

### 5.1 精确 implementation allowfiles

生产代码（仅三文件）：

- 新增 `dayu/runtime/process_diagnostics.py`：上述机制与 typed side channel。
- `dayu/runtime/log.py`：公共 record投影；不改现有handler身份、selector映射/format/suppression表。
- `dayu/fins/pipelines/docling_process_converter.py`：移除旧 `_isolated_inherited_stderr`，在 target完整生命周期使用新 scope；parent准备目录、close后投影；不改业务 descriptor/schema。

测试编辑（仅下列文件；已有回归文件只运行不因此扩大编辑 allowlist）：

- 新增 `tests/runtime/test_process_diagnostics.py`。
- `tests/runtime/test_log.py`。
- `tests/fins/test_docling_process_converter.py`。
- `tests/fins/test_xbrl_controlled_upload_integration.py`：必要的新沙箱诊断路径/权限真实 probe；仍将真实许可资源置外部，不能写入Git。
- `tests/cli/test_fins_commands.py`：CLI主入口日志组合与业务终态owner联验；不增加CLI生产filter。

文档：`README.md`、`dayu/fins/README.md`、`tests/README.md` 仅 §7 限定内容。`dayu/README.md` 已读职责，判定无需改，不在 allowfiles。`dayu/runtime/interruptible_process.py`、`dayu/runtime/macos_sandbox.py`、Documents、storage、workflow、所有registry/locks/control均是只读依赖，不在 allowfiles。

后续 implementation gate 的记录/pytest输出/real-CI证据只在 controller分配的本WU独占temp及fresh CI root；分析辅助代码若必要只置 `utils/` 且先经允许路径裁决，临时harness只置本WU `workspace/tmp/`，不能借当前计划授权修改已有通用CI executor。本计划不预先授权新utils产品辅助程序。

### 5.2 Call path、data flow、状态与错误处理

`CLI selected configure → Service/Fins原调用 → ProcessDoclingConverter准备input/taxonomy/work/diagnostics → 原handle.start(target) → child capture(fds+Python records) → 原XBRL policy+verify或普通转换 → export/output + unload → capture收口 → 原result queue descriptor → 原wait/interrupt/close → parent validate terminal + forward diagnostics → rmtree → 原result/cancel/error返回 → 原workflow/storage publication与CLI业务终态`。

`_DoclingProcessTarget` 增加显式 `diagnostics_directory: str`，调用方传本请求绝对路径，不藏 extra，不传用户 log path。唯一执行结构为：进入 capture → 原 XBRL application/verify → 原 input/conversion/serialization 分阶段 except 与原 descriptor return → 原 finally unload → capture 只收 structured scope → 原 runtime result queue。**只有 capture enter 的 ISOLATION_SETUP** 在原转换 execution catch 外单独映射现有 `CONVERTER_CONSTRUCTION` failure descriptor（诊断目录建立失败也由 parent 按同一 construction 原 code 处理），且 conversion/export/unload 都未启动；没有新的 public failure code。进入后 capture 自己的普通诊断 Exception 不能 throw；KeyboardInterrupt/SystemExit/asyncio.CancelledError/GeneratorExit 保原传播/退出/取消；原 body/unload 异常、五字段 failure descriptor、success size/digest descriptor 与 queue 传回步骤不变。return 触发 context exit 后仍返回原 descriptor，不能变 runtime Failed/DOCLING_IPC_PROTOCOL。

parent 精确顺序：原 wait/取消事实 → 原 `_close_handle`（outer cancellation/cleanup 按原优先级）→ 无 primary 且非 token cancel 时原 `_read_terminal_result(output_path=..., wait_result=...)`（包含 descriptor/output size/digest 验证）→ close 已确认完成时尽力 `_forward_converter_diagnostics` → 原 rmtree/原 cleanup 优先级 → 原 raise/return → 原 workflow/storage 的 Docling + 权威 manifest publication。forward 普通诊断路径只读取诊断路径，不修改 `result/primary_error/wait_outcome`，不重新读取或删除 output，不修改 descriptor 或业务判断；任何普通诊断 read/schema/projection/parent delivery Exception 至多 safe secondary，不能绕过后续 rmtree；marker 的真实 formatter/write/flush 普通故障由 §4.1 专用方法返回 False，Fins 结束该次报告，无公开双流或旧路径兜底，保原已验证 outcome。forward 调用处对四类控制流单独保存原对象，回到 parent 原 primary-error/cleanup 收口，保证 rmtree 被尝试，资源清理成功后原样 re-raise（已有 primary 控制流保持原对象）；原业务 rmtree/handle cleanup 自身失败仍由原 cleanup owner 按既有优先级裁决，诊断普通错误不得替代它。close 失败未确认 child 停止时不读 sidecar，直接沿原 cleanup，避免与在途文件竞争；不为日志新增进程治理。

| 分支 | 诊断动作与原 primary outcome（DN-R5） |
|---|---|
| 已验证 success + sidecar missing/bad JSON/缺 footer/read failure/capture incident/parent projection failure | 安全 secondary 经父公共准入；保原已验证 result，quiet 无诊断，后续材料仍按原 Docling+manifest 成功；**没有第三项日志完整性业务 gate** |
| 已有 construction/execution/serialization/IPC/crash failure descriptor或 primary exception | 在 close 成功且诊断路径存在时可读；secondary 不改原 code/五字段/异常；不拿诊断文件反推 outcome |
| token cancel、outer CancelledError | 保原取消与 130/cleanup；confirmed close 后仅读完整 prefix；缺 end/半行是 secondary incomplete，不造成业务 IPC |
| 原 handle close 或 rmtree cleanup failure | 原 cleanup 优先级不变；诊断 fault 不替换它，也不新增 cleanup failure；诊断自身额外 handle close fault 属 secondary |
| fd1/fd2 隔离范围在第三方前无法建立 | 不执行第三方，现 construction failure；允许阻止转换仅为不能保双流边界，此项不包含后续 sidecar 完整性 |

`require_complete=True` 只用于 runtime 已确认正常 child 退出；已知 cancel/crash/强制终止用 False。唯一读策略：True 先按行流式严格校验完整 structured spool（包括 exact end 以及其后无任何内容），校验成功才回读并 yield；False 按行流式 yield 合法完整前缀，遇残缺/非法内容抛 typed transport error，不能默许坏完整行。两模式固定内存、无全量缓存，schema 相同，不完整及投影错误由 `_forward_converter_diagnostics` 最外层诊断 containment 捕获并 safe secondary，正常退出也一样；读侧完整性不升级业务成功门槛，不改 descriptor。任何 secondary report 普通 Exception 静止结束，不回写 primary、不走旧 stderr/devnull 或字符串 severity 猜测。这个同步 try 域只捕获 Exception；控制流 BaseException 无论来自 primary 还是诊断内部都原样传播，不能被当成日志错误吞掉。

读取以JSONL行和raw固定64 KiB块流式处理，避免把大输出一次放内存；每channel byte offset单调，解码不能猜等级。保JSONL自身顺序和各fd内部顺序，不承诺fd1、fd2、logger三路全局时间序。只在close确认后读取并删除；不假设独立逃逸daemon已回收，原进程组cleanup范围不变。

XBRL目录建在原work下，沿用 `_build_xbrl_sandbox_profile` 的唯一writable_root；不新增sandbox条款，记录文件/FD也只指向work。admin与taxonomy复制/验证规则保持，绝不能把日志写权加到readonly runtime、parentworkspace或publicXSD。若真实内核仍拒绝本work内fd行为，停止并提供denial证据，不改到沙箱外、不提升权限。

### 5.3 不变量与完成/停止信号

无child diagnostics写公开双流；无source level重写；无CLI stdout解析；不静默devnull吞诊断；无parent/child共享用户日志句柄；无反向依赖；原conversion descriptor exact keys/固定文案/version=1保持；原size/digest/出版原子性与取消收口保持。

S1完成必须有actual diff、affectedpytest/cov、fullpyright 0、fresh真实PDF/XBRL/SIGINT证据以及双review/root裁决；不得靠Agent自报或“没有stderr”算完成。本计划本身只完成plan产物，不提前授予这些pass。

若依赖真实logger路径不符合capture机制、side channel需扩大沙箱、owner不确定、必须改上述allowfiles以外产品契约或新抽取质量要求，停止报告具体代码/原件及owner问题，不新增fallback或第二slice。

## 6. 验证：只映射本goal，以下全属未来gate

### 6.1 有意义的owner及负例测试

| owner/路径 | 断言（不固定偶然mock行为） | 对齐 |
|---|---|---|
| 新runtime process诊断测试 | 在真实独立spawn worker内用真实stdlib已有logger+stdout handler、lateimport新增handler/propagate=False、多线程record、lastResort/root、真实os.write(1/2)及继承fd后代；public双流空，原level/name/message仅一次；退出后parentfd不变、childfd映射直至exit、loggerclass/filter恢复；真实spawn worker 在 structured scope 内向 libc stdout 写无 newline，注册框架 Finalize 在 scope 外触发实际 libc flush；join 后字节只在 raw 文件，public 空。multiprocessing 可能 os._exit，不能假设自动 libc flush；另用独立解释器正常退出测 native 自动flush，均不在parent直接进capture | 双流不可绕过；晚建handler/退出缓冲 |
| 同测试 | 字符串包含WARNING但raw仍unknown；非UTF8字节可确定解码；schema缺键/多键/bool等级/坏版本/坏JSON/footer后record拒绝；normal缺footer为secondary transport error，cancel尾部半行仅前缀后通知incomplete；write/flush/dup2/close fault与资源回收，footer后绝不追加 | typed side channel，不猜severity、不隐藏丢失 |
| runtime record producer | 真 logger.warning("%d", "x")；真实异常 __str__ 抛错；用 stdlib makeLogRecord 构造非法 name/level/created（bool、NaN、Inf、溢出）及非法 exc_info traceback 成员，让真实 Formatter.formatException 抛错；UTF-8 surrogate 编码故障、真实格式化内部递归 logger、真实写入/flush fault；bad record 只 incident/drop、无伪正常 record，第三方调用继续，原 success/failure descriptor 均不变。__str__ 负例按 Formatter 真结果检查，真正格式化抛错断言 record_format，不注入生产factory或用mock制造旧行为 | DN-R1 全域 containment；不把读侧坏 JSON 当 producer 负例 |
| runtime control flow | 真实 handler与capture投影 getMessage/__str__ 分别抛 KeyboardInterrupt/SystemExit/asyncio.CancelledError/GeneratorExit，断言同一对象传播与reservation/depth最终释放；cleanup阶段同类控制流先回收后re-raise，不变secondary/success；普通TypeError仍incident | DN-R1 原取消/退出语义；不能以同步helper假定控制流在外 |
| runtime closure | 真实 spawn、多线程 Event/barrier：in-flight getMessage 暂停，close置CLOSING，stale filter/新类late emit，释放投影后 footer last；递归 formatter 不死锁；late emit仅原请求raw；状态恢复与post-footer close fault均不改body，不能用handler方法monkeypatch | DN-R2/R6 关闭与worker寿命 |
| runtime incident contract | exact capture_incident variant（封闭code、无额外字段）、footer仍exact end；healthy介质可读incident，partial write令faulted/缺footer；全媒体失败、post-footer cleanup 无可靠自报时只断言可观察范围，不新添descriptor payload | DN-R3 最小carrier及明确保证边界 |
| runtime log测试 | canonical全部等级×record等级、精确STREAM_DEBUG开关、QUIET、同stream重复configure/root双装配仍不重复；第三方原name/level；较低记录不绕过handler.level；更高record按parentpolicy准入；保留既有configureowner测试；通过真实 configure 创建的唯一 marker，分别用实际 write/flush 抛 OSError 的目的流及真实 Formatter 缺字段故障调用公共 helper，断言 False、public stdout/stderr 均空（logging.raiseExceptions 保原值）；healthy/低等级/quiet 分别 True 且按原 filter 留存或拒绝，原 source_name/level/created 与一次投递不漂移；专用方法的 write/flush/format 控制流断言四类同一对象传播和锁释放；普通 logger 仍走继承 emit，不扩大普通日志故障合同 | 同一parentpolicy；源level保全；DN-R7 父投递 |
| converter测试 | 真实installed settings.get_custom_logger在scope进入后import创建logger并emit WARNING（独立spawn避免模块cache掩盖）；conversion/export/unload中logger与fd均被捕；success/failure descriptor原样、outputdigest不变；隔离setup失败→construction且第三方零调用；已验证success时逐项注入missing/badJSON/缺footer/read/projection/parentlogging普通Exception仍保success，quiet无secondary，既有failure/cancel/cleanup优先，temp删除；parentlogging 普通负例必须实际使用配置 owner 的失败 stream.write/flush/formatter，不能仅 mock helper 抛错，断言公共双流空且业务原已验证 outcome/原 failure 不变；同路径控制流必须经原 cleanup 后传播同一对象 | 实际根因同源；原终态；DN-R7 |
| converter既有真实进程回归 | cancellationtoken/outertaskcancel、ignoringterminate的nestedchild、terminate→kill→close、flush失败与原failure优先、cleanup失败；记录FD与temp无残留 | 130和process治理不漂移 |
| CLI test_fins_commands | 走真实CLImain+Service公共事件；default临时stream owner probe、显式append、quiet仍业务progress/summary；converterdiag各等级只进log，error拒WARNING；五字段failure、company独立状态不变。可以控制conversion边界outcome，不能fake日志capture或新增兼容fixture | Print/log与失败契约 |
| XBRL owner/真实强制测试 | diagnostics路径在preparedwork；实际sandbox下log+fd可写；runtime/admin/taxonomy只读，outsideworkspace/private/userlog写及network拒绝；snapshot清单/hash复验，PDFfallback零调用、release条件保持 | 新文件不绕过sandbox |

原stderr测试迁移为两个fd+保诊断的owner合同，不保“所有错误字节永远devnull”作为fixture规则。target-only控制流测试也必须迁到独立worker probe：使用已有 `_SpawnBoundaryProbeTarget` 型式在worker内安装可控conversion并调用真实target，把descriptor/观察通过测试专用typed结果或artifact回传；不得在pytest parent直接永久重定向fd，也不得为保旧direct-call测试在生产helper中新增restore选项。XBRL既有directtarget probe同样迁移；不把测试专用观察字段加到产品descriptor。不得在测试里monkeypatch logging全局方法来假装capture有效。至少一项晚import测试显式无条件加StreamHandler，不能只用get_custom_logger.hasHandlers的偶然拒加分支获得正例。

### 6.1.1 Spawn coverage 唯一配方（DN-R4）

保持 **每个生产文件全部可执行行 >=80%**。pytest-cov 7 不默认启动 spawn collector；本地既有 `a1_coverage.pth` + coverage 7.13.5 只读复用，显式配置 `concurrency=multiprocessing/parallel=true` 和环境。选择 `coverage run` + 禁用 pytest-cov plugin，避免两个 collector 相互覆盖。只在 controller 分配的 implementation-s1 目录建配置/数据，不编辑 venv/global/pyproject；不删除旧数据，不修改生产 pragma、不 exclude/omit/ignore 生产行，不降为“可测面80%”。

未来以下命令在唯一仓库分别运行，逐步记录 actual exit，任一步失败不能用后续命令的 0 遮盖。implementation-s1 须由 controller 确认独占新目录；重测用新的子目录保存整次数据，不能混入历史 run。

```bash
source .venv/bin/activate
WU_DIAG_COV_DIR="$PWD/workspace/tmp/upload-material-converter-diagnostics-20261003/implementation-s1/coverage-run-01"
mkdir "$WU_DIAG_COV_DIR"
cat > "$WU_DIAG_COV_DIR/coverage.ini" <<EOF
[run]
parallel = true
concurrency = multiprocessing
sigterm = true
data_file = $WU_DIAG_COV_DIR/.coverage
include =
    $PWD/dayu/runtime/process_diagnostics.py
    $PWD/dayu/runtime/log.py
    $PWD/dayu/fins/pipelines/docling_process_converter.py
[report]
exclude_lines =
exclude_also =
ignore_errors = false
skip_covered = false
skip_empty = false
EOF
env -u COVERAGE_PROCESS_CONFIG -u COVERAGE_FILE -u DAYU_S3_XBRL_RESOURCE COVERAGE_PROCESS_START="$WU_DIAG_COV_DIR/coverage.ini" python -m coverage run --rcfile="$WU_DIAG_COV_DIR/coverage.ini" -m pytest -p no:pytest_cov tests/runtime/test_process_diagnostics.py tests/runtime/test_log.py tests/fins/test_docling_process_converter.py tests/runtime/test_macos_sandbox.py tests/fins/test_xbrl_controlled_upload_integration.py tests/cli/test_fins_commands.py tests/fins/test_docling_upload_service.py -q
python -m coverage combine --keep --rcfile="$WU_DIAG_COV_DIR/coverage.ini"
python -m coverage report --rcfile="$WU_DIAG_COV_DIR/coverage.ini" --show-missing
python -m coverage json --rcfile="$WU_DIAG_COV_DIR/coverage.ini" -o "$WU_DIAG_COV_DIR/coverage.json"
python - "$WU_DIAG_COV_DIR/coverage.json" <<'PY'
import json
from pathlib import Path
import sys
report = json.loads(Path(sys.argv[1]).read_text())
expected = {"dayu/runtime/process_diagnostics.py", "dayu/runtime/log.py", "dayu/fins/pipelines/docling_process_converter.py"}
actual = {Path(name).resolve().relative_to(Path.cwd()).as_posix(): data for name, data in report["files"].items()}
assert set(actual) == expected
for name in sorted(expected):
    data = actual[name]
    summary = data["summary"]
    assert not data["excluded_lines"], (name, data["excluded_lines"])
    assert summary["num_statements"] > 0
    percent = 100 * summary["covered_lines"] / summary["num_statements"]
    print(name, percent, "missing", data["missing_lines"])
    assert percent >= 80, (name, percent)
PY
pyright
```

检查 parallel 数据实际包含正常 spawn worker PID、原始 child-only capture/target 行进入 executed_lines、合并后原始数据保留（--keep），不能仅有 parent aggregate；强杀无法落 coverage 的 child 不伪造采集，相关正常路径由同真实spawn owner测试采集。配置 include 仅选择三个完整生产文件，非行级排除；缺文件/零语句/任何 excluded_lines/低于80均失败。新模块所有捕捉/关闭代码必须由普通真实spawn覆盖，绝不恢复pytest parent direct context 来凑数。pyright为后续全仓实际检查，此计划阶段仅小probe pyright，不冒 full type pass。

真实 XBRL 内核验收 **独立不带 coverage**：解除 `COVERAGE_PROCESS_START/COVERAGE_PROCESS_CONFIG/COVERAGE_FILE/COVERAGE_RCFILE` 后，用 §6.2 fresh resource 的 `DAYU_S3_XBRL_RESOURCE` 运行原集成与 work内诊断/外部拒绝测试；不向 sandbox 加 coverage config/source/private read 或数据 write。普通spawn的typed合成owner控制流覆盖实际新模块与target XBRL分支，内核只负责独立权限/真实正例；两类证据不能混称。只读运行 `test_macos_sandbox.py/test_docling_upload_service.py` 无需扩大编辑allowlist，真需修改必须先范围裁决。

本轮实际小证明位于 `workspace/tmp/upload-material-converter-diagnostics-20261003/plan-fix-sol-01/`：coverage-probe.ini 使用同 run/report 设置，仅 include 自己的 coverage_child.py；激活venv后以显式 COVERAGE_PROCESS_START 执行 `coverage run --rcfile=... coverage_spawn.py`，再 `combine --keep` / `json`。真实 child PID 39939，child-only 第12/13行实际执行，三份 parallel data 合并，5/5语句100%、excluded_lines空。仅证明采集机制，不证明产品80%；完整命令/exit/SHA见result与probe证据。closure_probe 是真实spawn的 reservation/关闭/递归/lateemit/框架finalizer FD 小证明，不是新模块实现；format_owner_probe 证明坏%d真正抛 TypeError、异常__str__由stdlib安全标记包含。另 control_flow_probe 对真实 stdlib handler 与普通 Exception 投影边界验证四种控制流均同对象传播（8/8），普通TypeError记incident；这四类小probe不代替未来owner测试与真实CLI验收。

### 6.2 Fresh真实CLI focused matrix

后续新建唯一 **数据/验收根** `/private/tmp/dayu-cli-upload-material-diagnostics-20261003-s1-01`（若存在则另分配新唯一suffix），不是新的repo checkout/worktree。源码仍唯一workspace，以其受review版本和venv运行，明确PYTHONPATH与spawn实际moduleSHA；parent/child身份不从历史HEAD继承。原CI root、`.venv`、frozen source、旧workspaces只读；只复制输入/admin/已缓存模型需要的文件到freshroot，逐字节hash前后核对，不chmod或反改原件。

输入为原 `inputs/msft-native-2024.pdf`，SHA `96de32a720641251b44c3e27e25ce2aa7ab035a15182b6260ef0ef06aa041dc0`、1,394,318 bytes、91pages（页数来源pdf-source-recovery，本gate不重新解析PDF）。provenance URL `https://www.annualreports.com/HostedData/AnnualReportArchive/m/NASDAQ_MSFT_2024.pdf`，full公司原生PDF，不拿derivedonepage冒充。

四次分别用fresh `--base`、stdin EOF、相同input与公司/材料语义（保留native矩阵重复company-name末值Microsoft测试意义），exactargv沿原command搬迁base/input路径，不照搬原sourceworkspaces：

| ID | selector/destination | 期望 |
|---|---|---|
| NATIVE-DEFAULT | default INFO，无log-file | 公共stdout只业务progress/success/summary；stderr空；默认临时诊断流终止即清理；真实发布成功 |
| NATIVE-QUIET | --quiet，无log-file | 同样业务进度终态；诊断无公开输出；真实发布成功 |
| NATIVE-LOG | --log-file freshroot/logs/native.log，INFO | log有真实MatchingPostProcessor WARNING及其原WARNING标识，public双流无diagnostic；业务发布成功 |
| NATIVE-ERROR | --error --log-file freshroot/logs/native-error.log | 真WARNING不入log；可能存在真正ERROR，不要求整log为空；业务结果仍成功 |

不强求与旧run相同129行、具体warning文案、Docling输出SHA跨运行相等或抽取质量指标。NATIVE-LOG若没有任何真实第三方WARNING则该正例证据不足，不能用emptylog假通过；转为needs-more-evidence并报告当前source/模型/runtime，不把oracle改为“必定129”。原有appendowner由CLI测试检查两次前缀；不为append重复跑91页PDF。

每次actualwait、stdout/stderr/log原bytes与SHA、exactargv/cwd/非敏感env、stdin、process tree/cleanup、publicbefore/after、repositorysource snapshot/readback、manifestprimary/size/hash、公司Microsoft、documentv1/amendedfalse/sourcefingerprint完整保存。direct无HostRun/Agentdurablejob/trace/memory要实际查询或明确N/A，不以没文件代替查询；业务五字段不能从log反推。原PDFsourcefingerprint `e5eaa08c5d2776510bc578e34db297dd2cf901c83972f5055c95e01015d6cc5b` 可在输入角色/身份保持时核对，manifest与实际生成Docling同runhash一致。

另做一项真实PDF进程已启动后SIGINT：等待child已启动的进程证据再signalparent，actualwait130、canonicalcancel终态、无半成品material/noorphan/无本请求诊断temp；company独立既决行为按公共state核对，不强行回滚公司。不得拿harnessdeadlinekill冒产品SIGINT。

真实XBRL：从旧root只读复制 `inputs/mlac.xml`、完整admintaxonomy及manifest，manifestSHA `5a1cc9986b36724cd5752b0b9389571e0fcdc31eeda9680c215213b5ecaa36af`；原instance预期SHA `04a015790c25d5a5371117bc64100335e65bfe1b3acdb71b4f2240c97e09cdf1` 必须在futurecopy前后重核。配置path只在freshadminconfig中改为fresh部署根，不能修改原config/manifest；清单含archiveentries完整性全核对。保持admin及taxonomyreadonly、kernel强制macOS arm64 Py3.11、标准runtime明确只读与公开XSD范围；无network、无userworkspace/private访问。用freshresourceJSON绑定 `DAYU_S3_XBRL_RESOURCE` 再单独激活venv运行已有真实integration正例与新增work内diagnostic/外部拒绝probe；skip、合成policy替身不计票。

不为本slice机械重跑2841测试、802场景或41kdiff审查。新owner相关完整文件回归与上述focusedmatrix足够针对当前风险；aggregate gate最终target另由root冻结与裁决，不能将focusedmatrix包装成原全量singlefull-realcampaign。

## 7. README 决策

已读根README §Agent更新约束/3.1、dayuREADME §Agent更新约束、FinsREADME同节/903附近转换隔离说明、testsREADME开头与现有XBRL说明。

- 根README：触发用户可见日志输出修复，属于用户手册；实施验证后仅在3.1补“财报转换诊断同样遵日志参数、quiet保业务输出；无可信源等级的原生诊断按info留存”。不写IPC/worker类名或WU历史。
- FinsREADME：属于converter边界，实施后替换现有“只隔离stderr/devnull”说明为父侧统一policy、请求内sidechannel、logger原等级/rawunknown、close后投影、sidecar故障仅secondary、fd保至worker退出及原取消/descriptor不变。无需新增未来框架章节。
- testsREADME：已有README说明只记录已存在测试与运行约定，实施后新增owner测试覆盖边界及真实资源/skip含义；不机械列全测试流水账。
- dayuREADME：检查已满足；本slice不改分层关系、装配入口或UI/Service/Host/Agent边界，原runtime层中立与XBRL边界仍准确，无需改。当前plan阶段四份README均不写未来实现事实。

## 8. 风险分类、open questions 与门槛

| 风险/未覆盖 | 分类/owner与去向 |
|---|---|
| 晚import stdout handler、源WARNING被降格、native/继承fd泄漏 | fixed in current slice（计划目标，尚未实施）：runtimecapture/Finsowner，S1负例与真实PDF验收 |
| 日志副通道错误覆盖conversionfailure/取消、清理残留 | fixed in current slice（计划目标）：Finsowner，首错测试与process回归 |
| XBRL日志temp需写到sandbox外 | fixed in current slice（计划目标）：work内文件无需权限新增；真实kernel验收失败即阻塞，不准扩大policy |
| raw源severity未知、高等级省略raw、三路无全局排序、收口后才投影 | requiring explicit user decision仅在要求更强保证时：当前按root裁定Fins最小unknown/INFO技术路由记录，不宣用户逐字接受rawINFO新oracle，不宣原level或实时日志 |
| 外部自建Logger/重写handle/独立manager、强杀前用户缓冲丢失或脱离现有processgroup的daemon | requiring new issue or explicit user decision（outside此goal，未授权laterWU）：runtime/converterowner，去向仅未来明确goal选择；当前实际dependency未出现前两类，若发现直接影响本goal立即阻塞重新确认；普通最终flush已由持续fd隔离覆盖，不顺手扩logging框架/进程治理 |
| diag文件增长占用磁盘 | requiring new issue or explicit user decision（outside此goal，未授权laterWU）：runtimeowner，未来明确goal选择；本goal不加quota/截断框架；本slice只保可观察incident/transport incomplete为secondary，媒体全坏/post-footer清理不保证自报，不改businessgate |
| Docling抽取准确性、tablematching warning内容 | requiring new issue or explicit user decision（outside此goal）：upstreamDoclingowner，用户未接受质量目标、未授权laterWU，不纳S1 |
| 纯oracle/scenario登记、原runverdict与整体campaignready | assigned to later work unit：独立registryWU/rootcontroller，保持其writepaths与原冻结事实 |

当前blockingopenquestions：**无**。DN-R1..R6与DN-D0均在本候选补足唯一方案，状态只是计划已修，仍待同版双re-review/root接受；不得自放行。typedsidechannel/owner/allowfiles/state/errorpriority已确定，尚未跑的产品实验是未来门槛。stdlib manager.setLoggerClass+已有filters已由两审/七项stdlib probe支撑，非方法monkeypatch；原marker机制不重构。Windows/Linux为用户明确延期；非法record字段由capture producer验证，不把它错误归到unsupported。新更强业务承诺或实际依赖不支持路径仍需root范围裁决，不能自行扩框架。

## 9. 后续正式 gates 与本gate停止

下一未完成入口是 **同版 plan re-review（MiMo/DS-flash）→root裁决**；本次按父Agent集中planfix派发边界，到plan/fixartifact/result完成后停止，不启动下一gate，不代表主用户pause。root正式续行顺序：同版双re-review→root接受→acceptedplancommit→S1implementation→deepreview双路codereview→fix→re-review→acceptedslicecommit→aggregatedeepreview→fix→re-review→accepteddeepreviewcommit→ready-to-open-draft-PR→push/更新既有draftPR197→PRreview→fix→re-review→acceptedPRreviewcommit→push→draft-PR-pass→finalcloseout。原PR197已存在，不能另建PR；用户merge，markready/approve/merge不自动授权。reviewtarget与commit范围必须每gate实核，当前不调用网络核PR状态。

完成报告须给任务/发现/gate/actualHEAD/modelruntimeprovider/canary、planpath与SHA、唯一S1owners/allowfiles/tests、read-only命令及失败、所有sourcesSHA、风险/openquestions、README决策、not-run验证、productwrites=false、nextentry=same-version-dual-plan-re-review/root-acceptance、stop=true；不把计划完成称产品修复完成或finalcloseoutpass。

## 10. 证据定位与完整性

原plan-sol-01来源与历史读取事实见其原result（仅读，不覆盖）；本次readSourceSHA、control实际状态、原全文/SHA、updatedplanSHA、精确diff和实际probe命令/exit见独占 `workspace/tmp/upload-material-converter-diagnostics-20261003/plan-fix-sol-01/result.json` 与source-manifest.json。以下历史引用不冒成本次重跑：

- goalconfirmation SHA `63ca599bee4ae401714281f8a7501c63b0c6b1b1024447a01ae1f6ed9d799a06`；acceptedcandidates SHA `dbeb48a6cff69e477034adf9e57e0b8dcf09fe0147ea64132df5992c75deec46`。
- frozen报告SHA `f35d33f5ff62b1e45d6f6ecf7ae1bcf7db4139f33c5b2af714e59ea0680ef53c` 来自授权及实读synthesis/candidates，**未重读整20MB报告或重核全部802**。synthesisMarkdown当前SHA `5cb0049b5da890a1fbe3a447042c281bbc89c946fa13ac8a6b315d09ea4a979d`；JSON `09df70c18d0c5e2485e0a395b75f6f2dd56847faec07e4e39c2cf30a707fe179` 的旧synthesis_sha不等于后续附裁决文本，作为历史字段保留，不改原件。
- 原scenario位于 `workspace/evidence/upload-material-cli-20261003-79977b3a-01/public/FORMAT-PDF-NATIVE-FULL/`，实读command/result/publicbefore/publicafter及双流bytes：stdout19,741字节，SHA `8b2b38db9a414058ff7027895d5d21abb4b2384433ed8dc035743825580056be`，129行已格式化MatchingPostProcessorWARNING；stderr0字节SHA `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。这是观察计数，不用于运行时severity解析。
- `docs/reviews/upload-material-um-o29-oracle-adjudication.md` SHA `1ea88fbbdb2342c144ead9819636324eb8789154caccda8c791dfc191d0db922`；sourceownerconverter SHA `d6b6772e329c66045f634fb4994c76bbcb9ef0130d3fe498b2e7f044ae6cd1b8`；parentruntime log SHA `908e90c85ca7d1c6281d5296667933d7eee0768cb2bfd7554bc1b0fb75d19069`。
- nativeprovenance在只读旧CI root `evidence/native-pdf-matrix.json`、`evidence/pdf-source-recovery.json`；input实际SHA/bytes已核，页数用该provenance，不新跑PDF解析。
- 两份installedsettings SHA `68aacd3855426e2ccc6804f51e797323dca9bfbef034fa8b49a243d81920004a`，matching源码SHA `0675880799c3474bfe0355c3fe81a105d87ac0f2cdb2f51a4699a9f4096cebe3`。

原plan gate读取中一次搜索不存在的 `tests/cli/test_main.py` exit2；后续通过文件清单定位真实 `test_fins_commands.py`/`test_public_package_entrypoints.py`，失败保留result，不以最终成功遮盖。并发任务生成的registryplan及rootreview文档仅status观测，未写、未作为本任务授权真源。
