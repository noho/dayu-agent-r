# Plan Review：UM-CI-N01-F01 转换器诊断遵循父进程日志规则

RUNTIME/PROVIDER/MODEL: claude/mimo/mimo-v2.6-pro[1m]
CANARY=mimo-51fd4755

## 0. 自身声明与实际文件读取

**自身声明**：本轮任务 `upload-material-converter-diagnostics-plan-review-mimo-20261003-01`，职责为独立 goal-bound adversarial plan review，不负责实施；不修改计划、产品代码、测试、registry、locks、冻结证据、他人 artifact 与控制文件；不运行真实 CLI / Docling 转换 / provider / 网络 / pytest / pyright；不派发子 Agent。产物仅本报告与独占 `workspace/tmp/upload-material-converter-diagnostics-plan-review-mimo-20261003-01/`（review.json、stdlib probe 及其结果）。本报告不 review 独立 registry-plan。

**实际读取/核对的文件**（均为只读或独占目录写入）：

| 类别 | 路径 | 实核结论 |
|---|---|---|
| 计划 | `docs/gateflow/upload-material-converter-diagnostics-plan-20261003.md` | SHA `a58b95afbc9898969bf85e0c79ed0d3597339d2bbc3ddd420aedc80d30bf7289`，与任务冻结 SHA 一致 |
| 绑定目标 | `workspace/tmp/upload-material-converter-diagnostics-20261003/goal-confirmation.md` | SHA `63ca599bee4ae401714281f8a7501c63b0c6b1b1024447a01ae1f6ed9d799a06`，与计划 §10 一致 |
| 用户裁决 | `workspace/tmp/upload-material-unified-repair-20261002/post-wu-preparation/oracle-candidates.json` | SHA `dbeb48a6cff69e477034adf9e57e0b8dcf09fe0147ea64132df5992c75deec46`；`UM-CI-N01.user_adjudication` 实读："第三方转换器诊断不得混入业务stdout；quiet抑制诊断但保留业务进度/终态；指定log-file时按CLI等级写文件；未指定时遵既定诊断去向。" |
| converter 真源 | `dayu/fins/pipelines/docling_process_converter.py` | SHA `d6b6772e329c66045f634fb4994c76bbcb9ef0130d3fe498b2e7f044ae6cd1b8` |
| 父侧日志真源 | `dayu/runtime/log.py` | SHA `908e90c85ca7d1c6281d5296667933d7eee0768cb2bfd7554bc1b0fb75d19069` |
| 进程治理真源 | `dayu/runtime/interruptible_process.py` | SHA `1a1ae877d60f4a483df75dac8158d0c69821e3d28b18d45c5a63448845961e91` |
| 等级常量 | `dayu/runtime/log_levels.py` | SHA `c7fc361c223f649467bc13ac25277d2a7dc4b6920fc1d4bf9c81a12317d33889`；`QUIET_LOG_LEVEL = 51` |
| 沙箱 | `dayu/runtime/macos_sandbox.py` | SHA `0794d0390706941f76d9250a02c7503aaeaaf35a08420fe27dccf5f890dd3a54`；`writable_root` 以 `(allow file-write* (subpath ...))` 授权（113 行），子目录覆盖；`apply_macos_sandbox` 为进程内 `sandbox_init`，无 re-exec |
| CLI | `dayu/cli/main.py` | SHA `a61ccd24765e9890eff71f38dbc91176d02174c5df9bab14e66d5400613dfa08`；显式 `--log-file` append、默认 `TemporaryFile`、退出清理后关流，与计划 §3 一致 |
| 已安装依赖（本地 venv） | `.venv/.../docling_ibm_models/tableformer/settings.py`；`.../matching_post_processor.py` | SHA `68aacd3855426e2ccc6804f51e797323dca9bfbef034fa8b49a243d81920004a` / `0675880799c3474bfe0355c3fe81a105d87ac0f2cdb2f51a4699a9f4096cebe3`，与计划 §10 一致；`get_custom_logger(..., stream=sys.stdout)` 且模块 import 即建 LOGGER；`MatchingPostProcessor._log()` 惰性建 logger |
| 已安装依赖（冻结 CI venv） | `/private/tmp/dayu-cli-ci-upload-material-20261003-79977b3a-01/.venv/...` 同上两文件 | 两份 SHA 与本地完全一致，计划"两份同 SHA"声明成立 |
| 冻结场景证据 | `workspace/evidence/upload-material-cli-20261003-79977b3a-01/public/FORMAT-PDF-NATIVE-FULL/{stdout.bin,stderr.bin}` | stdout 19,741 bytes SHA `8b2b38db...`、stderr 0 bytes SHA `e3b0c442...`，与计划一致（未整读 20MB 报告） |
| 测试边界 | `tests/README.md`、`tests/fins/test_docling_process_converter.py`、`tests/runtime/test_log.py`、`tests/cli/test_fins_commands.py` | tests/README 只记录已存在测试的约定成立；converter 测试存在 `_isolated_inherited_stderr`/flush 失败/直调 `target()`（696/2001/2248 行附近）与 `_SpawnBoundaryProbeTarget`（344 行），计划迁移要求与现状吻合 |
| 其它 | `dayu/documents/docling_runtime.py`（导入时机）、`dayu/fins/upload_failure.py`（五字段）、`dayu/fins/README.md:903`（现行 stderr 隔离说明）、`AGENTS.md`（SHA `cb26618a...`）、goal WU 目录清单 | docling 第三方为 lazy import（330 行注释），scope 内导入可行；五字段 `kind/code/message/retry_hint/file_label`，`IPC_PROTOCOL→DOCLING_IPC_PROTOCOL` 映射已存在；Fins README 903 行确有"只隔离 stderr"说明待 §7 替换 |

**stdlib 机制 probe**（独占目录 `workspace/tmp/upload-material-converter-diagnostics-plan-review-mimo-20261003-01/stdlib_logging_probe.py`，SHA `3028c5e5295c6d3e7dd1dd1c596fd57bb372bfbbe9b6210ba3fea27323a865c2`；结果 `probe-results.txt`，SHA `82017aa065e9c74e0032a73cf4972f76bcae9f1eaca4cc2b47484ba0b2cff0f5`；Python 3.11.15，仅 stdlib，不碰产品代码/CLI/Docling）：

| 检查 | 结果 | 对计划的意义 |
|---|---|---|
| P1 `setLoggerClass` 只影响新 logger 与 PlaceHolder 替换 | PASS | 计划 §4.2.4 机制成立 |
| P2 已有 logger filter 返 False → handler 与 lastResort 均不触发 | PASS | §4.2.3 阻断自装 handler 与 lastResort 成立 |
| P3 子 logger `callHandlers` 不经过父 logger 级 filter | PASS | 证明"仅 root/父 filter"不足，双机制（已有 filter + 新类 handle 覆盖）必要 |
| P4 组合设计恰好捕获一次，保源 name/level/message，自装 handler/propagate=False 不能绕过 | PASS | §4.2.3–4.2.5 核心承诺成立，无双发 |
| P5 fd 重定向后 print/`os.write`/StreamHandler(stdout)/无换行 native 写全入文件，无 restore 时 finalizer 迟写仍入文件，公共流为空 | PASS | §4.2.2 无 restore 设计的关键收益成立 |
| P6 `hasHandlers()` 祖先判定（root 有 handler 时为 True） | PASS | 计划"晚 import 测试须显式无条件加 StreamHandler"要求有据 |
| P7 QUIET=51 时 `isEnabledFor` 对 50/40/30/20/15/10/9 全 False | PASS | quiet 全拒成立 |

probe 首次 P1 判据写错（`p1.ph.child` 在 setLoggerClass 之后创建，应期望新类）导致 FAIL；修正判据后全 PASS。失败属探针自身错误、已按实际机制修正，未掩盖。

## 1. Reviewed target 与 scope

- **Target**：`docs/gateflow/upload-material-converter-diagnostics-plan-20261003.md`（UM-CI-N01-F01，单行为 slice S1 的 implementation plan），冻结 SHA 见上。
- **Binding goal**：goal-confirmation.md（UM-CI-N01）+ oracle-candidates.json 用户答复 receipt（已实读）。
- **Scope**：goal-bound adversarial plan review，8 lenses 显式应用；不评价依赖抽取质量、不 review registry-plan、不改计划、不实施。

## 2. Assumptions tested（逐项证伪尝试）

1. **已安装转换栈走 stdlib manager/getLogger/Logger.handle 路径** → 证实：settings.py `get_custom_logger` 用 `logging.getLogger`+`StreamHandler(sys.stdout)`；matching 惰性 `_log()`；docling_runtime 对第三方为 lazy import（scope 内导入）。
2. **仅 fd2 隔离即可绕过诊断** → 证实为原缺陷：`_isolated_inherited_stderr` 只包 conversion 调用且只 dup2 fd2→devnull（converter:342-350），export/unload 在范围外；stdout 不隔离。
3. **仅 root filter/handler 捕捉不足** → 证实（probe P3 + propagate=False 分析）。
4. **setLoggerClass + 已有 logger filter 组合可完整捕捉且不双发** → 证实（probe P1/P2/P4）。
5. **无 restore 的 fd 重定向能兜住 libc/finalizer 迟写** → 证实（probe P5）。
6. **XBRL 下 work 内诊断子目录无需新沙箱条款** → 证实（macos_sandbox.py:113 `subpath` 授权；`sandbox_init` 无 re-exec，dup2 后 fd 存活）。
7. **`ProcessDiagnosticsError`→runtime Failed→exit 0→父侧 IPC_PROTOCOL 路径存在** → 证实（interruptible_process `_run_process_target` 捕 Exception 发 `_ProcessFailed` 且进程正常退出；converter `_read_terminal_result` 对 exitcode==0 的 Failed 映射 IPC_PROTOCOL，815-818 行）。
8. **诊断损坏/成功拒绝可映射现有五字段而不增新 public code** → 证实（upload_failure.py 已有 `IPC_PROTOCOL→DOCLING_IPC_PROTOCOL`）。
9. **计划 §6 的测试迁移是实质性的** → 证实（现存 pytest 直调 `target()` 于本进程 + monkeypatch，必须迁 worker；计划已禁止为保旧测试给生产 helper 加 restore）。
10. **capture 投影路径异常安全** → **证伪**（见 F1）：计划未规定 `getMessage()/formatException` 失败行为，stdlib 基线是吞掉不改第三方控制流。
11. **"secondary capture error 供父识别"有明确载体** → **部分证伪**（见 F2）：与 exact footer/仅 kind="log" 契约无衔接。
12. **成功拒绝语义已获 goal 授权** → **未证实**（见 F3）：goal 只说"保持既决语义"，该触发面扩展在计划内被当作 settled，未按 raw 语义同等待遇列入 userdecision。

## 3. 8 lenses 显式应用结论

- **Goal-bound minimal design**：三生产文件、机制最小（无 queue/pipe 线程/额外进程/exporter/quota）、验收全部映射本 goal；raw-INFO 为用户已接受最小语义；无 registry/format/manifest/F5/日期/计数/symlink 目标混入。→ 除 F3 的一处 contract 触发面扩展未上呈外无 goal drift。
- **Architecture boundary**：`UI→Service→Host→Engine` 未动；`process_diagnostics` 只依赖 stdlib+JsonValue、层中立；raw→INFO 路由策略留在 Fins converter，不进 runtime；child 不收用户 log path；不改 result queue/close 协议。→ 无边界违规。
- **Best practice**：typed error、严格 schema、首错清理、禁 monkeypatch 假 capture、真实 spawn 测试、逐文件 80%+full pyright。→ 唯一偏离是 F1（stdlib "logging 不改调用方行为"纪律未写入投影约束）。
- **Optimal solution**：§4 备选表为真比较；文件 side channel 避免 pipe 反压干扰取消的理由成立；setLoggerClass 是拦截新 logger 的唯一 stdlib 公开扩展点（probe 证实其它路径不足）。→ 选定方案成立。
- **Overengineering**：无。`ProcessLogDiagnostic` 字段最小、raw 块 64KiB 流式、无通用日志订阅框架。→ 无发现。
- **Overcoupling**：slice 按行为不按文件；runtime/fins 测试在 owner 边界各自证明；无跨层穿透。→ 无发现。
- **State machine / execution semantics**：取消→terminate→kill→close 优先级、cleanup 失败优先于业务失败、cancel 优先于诊断 secondary、footer/prefix/半行语义明确。→ F2 一处载体缺失，其余成立。
- **Validation**：测试覆盖六域（logger 原等级/未知 raw fd/parent 准入/stdout 业务/cleanup/XBRL 真实边界），负例丰富（坏 schema/坏 JSON/缺 footer/半行/首错/晚 import handler），真实 PDF 四行矩阵+SIGINT+真实 XBRL。→ 缺 F1 对应负例；其余 code-generation-ready。

## 4. Findings

### 1-未修复-中-capture 投影路径未定义异常安全，格式化异常可改写第三方调用行为与转换分类
- **位置**: 计划 §4.1 `capture_process_diagnostics`/`_ExistingLoggerCaptureFilter.filter`/`_CapturingLogger.handle` 的投影定义（文档第 77、87-88 行）；§4.2.6（第 90 行）；§6.1 测试表第 2 行（第 155 行）。
- **问题类型**: 契约缺失 / 状态机漏洞（logging 回调异常安全未规定）。
- **当前写法**: filter/handle "同步投影 record"，只投影 `name/levelno/getMessage()/created` 及已有 exception/stack 文本；`_DiagnosticWriter` 首错机制只覆盖**写入**错误，且要求"不让 logging callback 将其误分类为 conversion execution"；对 `record.getMessage()`（坏 `%` 参数）与 `formatException`（exc_info 异常 `__str__` 抛出）本身失败时的行为无规定。
- **反例/失败场景**: 第三方在错误路径调用 `logger.warning("progress %d", obj)`（obj 格式化触发 ValueError/TypeError）或 `logger.error("...", exc_info=True)` 且异常 `__str__` 抛出。stdlib 基线（StreamHandler.emit → except → `handleError`）吞掉该异常并把 traceback 写 stderr，第三方控制流不变。计划实现若在 filter/handle 内直接调用 `getMessage()/formatException` 且不捕获，异常会穿透 `logger.warning(...)` 调用点，第三方行为被改写，转换被误判 `CONVERTER_EXECUTION` 失败或中止——恰在诊断最需要保留的错误路径上。
- **为什么有问题**: 与计划自身不变量"不让 logging callback 将其误分类为 conversion execution"冲突；且 §8 规定"不得由 codegen agent 发明替代契约"，该行为必须在计划里定死。stdlib 的 `Handler.handleError` 基线是本项目当前实测行为（stderr.bin 为证），捕获层有义务保持。
- **直接证据**: stdlib `logging/__init__.py` `StreamHandler.emit` 对 `self.format(record)` 包 try/except→`handleError`（probe 环境 Python 3.11.15）；计划 §4.2.6 首错范围仅"记录写入"；§6.1 测试表覆盖 write/flush/dup2/close 首错但无 message 投影失败负例。
- **影响**: 生成代码在错误路径改变转换结果分类/业务终态；测试无对应负例会固化该缺陷。
- **建议改法和验证点**: §4.1/§4.2.6 明确一句：record 投影（`getMessage`/exception 文本合成/任何 `str()`）不得把异常抛回第三方 logging 调用点，失败时降级为有界安全 fallback 文本（含 source_name/level 标识）并记首错，退出按既有 secondary/surfaced 规则处置；§6.1 增加负例行：坏 `%` 参数与 exc_info 格式化失败 → 第三方调用行为不变、不产生 conversion failure、record 可读或明确截断。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 中。

### 2-未修复-低-"secondary capture error 供父识别"未指定记录通道，与 exact footer 契约无衔接
- **位置**: 计划 §4.2.8（第 92 行）与 §4.1 footer exact 契约（第 91 行）、§5.2 父侧识别条件（第 132 行）。
- **问题类型**: 契约缺失。
- **当前写法**: JSONL 成功收口最后一行 exact `{"schema_version":1,"kind":"end"}`，record `kind` 仅 `"log"`；同时承诺 capture 退出错误"记录 secondary capture error 供父识别"。
- **反例/失败场景**: body 已得 failure descriptor、capture 退出在写完 footer 后的清理步骤失败（关闭额外 handle）→ side channel 完整可读，父侧只能识别"不完整/截断/投影失败"，该 secondary 无载体可写，承诺落空；或实现被迫发明未约定的记录形态，违反 §8"不得由 codegen agent 发明替代契约"。
- **为什么有问题**: "供父识别"是明示承诺但机制空缺；codegen 有多个互不兼容的自由发挥空间（stderr.bin 随手写、footer 加字段破坏 exact、静默丢失）。
- **直接证据**: §4.1"成功收口最后一行 exact"、"record 字段严格投影"；§5.2 父识别只覆盖"诊断不完整或投影失败"；§4.2.8 同句内部"已有主体异常保其分类…无主体失败时 surfaced error"与 §5.2"已有 failure descriptor 原样返回"的对应关系依赖"主体失败含 failure descriptor"这一未言明读法。
- **影响**: 实现歧义 / secondary 诊断承诺不可验收。
- **建议改法和验证点**: 二选一写死——(a) 收窄措辞：secondary 仅以父可观察的通道不完整/截断为载体，footer 后清理错误在已有 failure descriptor 路径不单独记录；或 (b) 在 JSONL footer 前允许一行明确 `kind="capture_error"` 记录并同步 §4.1 exact keys 与读取规则。同时用一句话明确"主体失败含已构造的 failure descriptor"以消除 4.2.8/5.2 读法歧义。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 低。

### 3-未修复-中-成功路径 sidechannel 损坏→拒绝成功属材料业务 contract 触发面扩展，被当作 settled 而非裁决项
- **位置**: 计划 §5.2"若原成功但正常诊断 side channel 非法/不可读，按既有 IPC_PROTOCOL 拒绝向上返回成功"（第 132 行）；§6.1"setup/投影损坏→IPC 仅在成功时"（第 157 行）；§8 风险表（第 210-219 行）。
- **问题类型**: 目标漂移 / 范围漂移（contract 触发面扩展未上呈 root/user 裁决）。
- **当前写法**: 作为设计决定直接写入 5.2；§8 把 raw 语义列为 "requiring explicit user decision"，却把本项列为 settled，两者同为影响业务可见结果的语义决定，待遇不对称。
- **反例/失败场景**: quiet 用户 + 转换成功、output digest 验证通过、材料完整 + sidecar 一行损坏（瞬时磁盘错误或未来 capture 回归）→ 业务上传失败 `DOCLING_IPC_PROTOCOL`，无 publication。用户显式要求抑制诊断，却因观测通道失败而业务失败。anti-leak 由 fd 隔离结构性保证，sidecar 损坏 ≠ 诊断泄漏公开双流；备选规则（secondary operator 诊断 + 返回已验证成功）仅损失观测完整性，且系统性 capture 回归可由 §6.2 NATIVE-LOG 正例与 secondary 诊断发现。
- **为什么有问题**: goal-confirmation 只授权"转换结果/failure descriptor/取消治理…保持既决语义"；扩大"何时算成功"的判定条件是对材料业务 contract 的修改，应按计划对 raw 语义的同等标准上呈裁决，而不是在 plan 内部闭环。同时存在两个都说得通的读法：用户 predicate"指定 log-file 时按 CLI 等级写文件"支持 fail-closed（交付承诺被破坏就该失败）；"quiet 抑制诊断但保留业务进度/终态"支持 quiet 下不因诊断通道失败业务。二者冲突正需要 root 裁决。
- **直接证据**: goal-confirmation Success/Goal 原文（"保持既决语义"）；用户 accepted_predicate 四句（oracle-candidates.json）；计划 §8 对 raw 语义标注 "requiring explicit user decision" 而对本项无此标注；upload_failure.py 映射证明该失败会以现有五字段 code `DOCLING_IPC_PROTOCOL` 呈现给用户（shape 不变、触发面变）。
- **影响**: root 裁决前实施即固化 contract 触发面扩展；quiet 反例未被用户确认；与取消路径"诊断不完整只记 secondary、保持原终态"形成未论证的不对称（取消可容忍、成功不可容忍）。
- **建议改法和验证点**: 把该决定显式移入 §8 "requiring explicit user decision" 或 root 裁决清单，附本反例与备选规则（成功路径 sidecar 损坏 → safe secondary operator 诊断 + 返回已验证成功；strict 仅保留 capture scope 本身建立失败——此时隔离保证确实未证明）的取舍；root 接受则在 §5.2 补 goal 映射与 quiet 模式确认，root 拒绝则改规则与 §6.1/§6.2 相应验收行。裁决前不实施该分支。
- **修复风险（低/中/高）**: 低（两种写法都是局部规则+测试行）。
- **严重程度（低/中/高/严重）**: 中。

## 5. 明确裁决记录（任务 stress 清单逐项判定，非 findings）

| stress 项 | 判定 | 依据 |
|---|---|---|
| source level preserved 与 logger 已有 source admission | 成立 | probe P4；filter 追加在已有源 filter 之后，源 `disabled/filter` 与 `_log` 前等级门保持；handler 级 filter 未执行属"不执行 child handler 路由"的明示边界，只会多捕获不过少捕获 |
| parent selected level / handler filter 准入 | 成立 | `emit_process_log_diagnostic` 走 `getLogger("dayu").isEnabledFor` + `handle` → handler.level + 原 `_DiagnosticAdmissionFilter`；QUIET=51 probe P7；自定义 level 边界与 dayu 自身记录一致 |
| 重配置及 root 双装配不 duplicate | 成立 | `configure` 恒置 `dayu.propagate=False`，`callHandlers` 断链；root 装配只影响 root 路径记录，不经 emit 二次走 root |
| 动态 new logger 自建 handler / propagate=False 不能绕过 | 成立 | probe P4（显式无条件加 StreamHandler + propagate=False 仍恰好捕获一次） |
| fd 原生/继承后代不公开流绕过 | 成立 | probe P5；dup2 默认可继承；不 restore 设计使 libc/finalizer 迟写只能入请求文件 |
| 线程 writer / footer / partial cancellation / restore first error | 成立 | 4.2.6 lock 序列化；4.2.8 逐项回收、首错不阻断；5.2 prefix/半行/坏完整行语义明确 |
| 原五字段取消先后次序 | 不变 | close 优先级、`_cleanup_error` 覆盖次序、cancel→`DoclingConversionCancelledError` 优先于诊断 secondary 均保持；`FinsUploadFailureReason` 五字段 shape 与 code 集合不变 |
| sidechannel 损坏是否无意改变材料业务 contract | **非无意**：deliberate 且映射现有 `DOCLING_IPC_PROTOCOL`，五字段 shape 不变；但触发面扩展未上呈裁决 → **F3** | 见 F3 |
| XBRL 诊断仅在原 work、不扩 sandbox、不 child 用户 log path | 成立 | `writable_root` subpath 授权覆盖 `work/diagnostics`；`sandbox_init` 无 re-exec；`diagnostics_directory` 为请求内路径 |
| record created / message 异常 | **message 投影异常缺口 → F1**；created_at 读侧严格校验成立 | F1；custom `makeRecord` 工厂产出非法 created 属 §4.2 声明的改写管理器边界，读侧拒收为防御 |
| bad JSON / footer | 成立 | typed transport error、不 fallback 成 raw、exact footer、footer 后 record 拒绝 |
| raw 无级别 INFO 不伪原 level、不猜 WARNING 文本 | 成立 | 前缀固定 `source_level=unknown`、路由等级仅 INFO、文本不影响归类；与用户裁决一致 |
| stream chunk 内存 / 诊断释放归属 / close 保证 | 成立 | raw 64KiB 块流式、raw 转 record 消息有界；close 确认后读取、统一 rmtree；不改 close 协议 |
| 新 runtime 接口 / manager 自定义 Logger 类必要性与最小替代 | **必要且最小** | probe P1/P3/P4 证明 root-only、filter-snapshot-only 不足；`setLoggerClass` 是 stdlib 公开扩展点而非 monkeypatch（对照被正确拒绝的全局替换 `Logger.handle`）；独占 child scope、禁嵌套/parent 安装/白名单、退出恢复等边界约束充分；`dayu.runtime.process_diagnostics` 层中立、只依赖 stdlib+JsonValue，符合 runtime 定位 |
| slice 完整性（不按文件机械切、不造 blocker/新 goal） | 成立 | 单 slice 覆盖六域；§8 风险分类无夹带目标 |
| 测试意义 / 80% / full pyright / README 职责 | 成立（缺 F1 负例） | 真实 spawn/真实 PDF/XBRL/SIGINT 矩阵、禁 monkeypatch 假 capture、direct-call 迁移真实存在；README 三处职责映射与 Fins README 903 行现状吻合；dayuREADME 无需改的判断成立 |

## 6. Open questions

1. **（源自 F3，非 blocking 结构问题）** 成功路径诊断 sidechannel 损坏是否拒绝业务成功——包括 quiet 模式——需 root 裁决（或补充用户确认）。裁决前建议不实施该分支。
2. （低，源自 F2）"secondary capture error 供父识别"的载体形态需在计划内定死一种。

## 7. Residual risks（分类与去向）

| 残余 | 分类 | owner/destination |
|---|---|---|
| 晚 import stdout handler、源 WARNING 降格、native/继承 fd 泄漏、sidechannel 优先序、XBRL work 内文件 | **固定（本 slice 计划目标，尚未实施）** | runtime capture / Fins owner，S1 负例与真实 PDF 验收 |
| 外部自建 Logger / 改写 handle 或管理器 / 重置 loggerClass、SIGKILL 前用户缓冲丢失、脱离 process group 的 daemon | **已授权 later** | runtime/converter owner（计划 §8 已分类）；实际依赖未出现前两类则维持边界声明 |
| diag 文件增长无 quota | **已授权 later** | runtime owner（计划 §8） |
| Docling 抽取准确性、table matching warning 内容 | **其它 WU** | upstream Docling owner；用户未接受质量目标 |
| 纯 registry/oracle/scenario 登记、原 run verdict、campaign ready | **其它 WU** | 独立 registry WU / root controller |
| raw 语义（INFO 路由、高等级省略 raw、三路无全局序、收口后投影） | **userdecision（已裁）** | 用户答复 receipt 已接受最小 unknown/INFO 语义；仅在要求更强保证时再问 |
| 成功拒绝语义（F3） | **userdecision（待裁）** | root 裁决/用户确认，明确去向为计划 §5.2/§8 规则与验收行 |
| custom `makeRecord`/非法 created_at、晚加第三方 filter 在 capture filter 之后不执行 | **其它（声明边界内）** | 属 §4.2"改写 handle/管理器"不支持家族；读侧严格校验为防御，不扩框架目标 |

## 8. 结论

**pass-with-risks**。

计划的动机、owner 判定、双机制捕捉设计、fd 无 restore 隔离、取消/清理优先序、XBRL 边界、测试迁移要求与验证矩阵均经直接证据与 stdlib probe 证伪尝试后成立，总体达到 code-generation-ready 结构。剩余三点均局部可修：F1（capture 投影异常安全，必须在计划定死后才能交给 codegen）、F3（成功拒绝语义需 root 裁决，不得默默固化）、F2（secondary 载体一句话收窄或扩展）。建议 root 裁决 F3 后按 F1/F2/F3 的 minimal fix 更新计划并复审；当前计划不满足"无条件直接进入 S1 implementation"，但无需结构性重写。
