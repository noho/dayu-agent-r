# issue #198：download 失败投影与脱敏诊断 plan

- 当前修复性重试 task label：`issue198-plan-fix-sol-20260928-02`（关联上次 `issue198-plan-fix-sol-20260928-01`）；Gate：`plan review -> fix`；日期：2026-09-28。候选 plan 来自 `issue198-plan-sol-20260928-02`，本次只落实第一次 re-review 后总控裁决的两项低严重度 finding 与 RESULT/日志顺序要求，保留原已闭环条目。
- Goal confirmation：`docs/gateflow/issue-198-download-failure-projection-goal-20260928.md`，已标记 `goal confirmation pass`。裁决依据：`docs/gateflow/issue-198-plan-review-adjudication-20260928.md`。本次 plan fix 完成后仍须 re-review，不表示代码或 plan review 已通过。
- 基线：分支 `codex/upload-material-oracle`，goal 文件记录的 HEAD 为 `97a8eec8`；实施前重新核对 HEAD 和工作树。目标为现有 draft PR #197，不在本 gate 改动该 PR。

## 目标与第一性原理判断

目标是让 storage 的封闭完整性预检原因，经 Fins download 公共失败对象、direct RESULT、CLI/等待投影保持同一事实；真正未知的 direct download 异常仍给用户安全的 generic 失败，同时在 operator 日志留下**不含异常原文和用户路径**的异常类型及可定位调用栈。成功信号为 `unsafe_publication` 显示 `storage`、可操作且不鼓励盲目重试，未知异常有可查看的安全诊断，owner 测试、受影响测试、pyright 和隔离真实 CLI 验证通过。

动机成立：`dayu/fins/storage/source_integrity.py` 的 `SourceIntegrityPreflightReason` 是四值封闭枚举，`classify_source_integrity_preflight` 在 UNSAFE inventory 上抛 `SourceIntegrityPreflightError(UNSAFE_PUBLICATION)`；`dayu/fins/ingestion_runtime.py:_run_direct_stream_producer` 捕获异常后只生成 RESULT；`_download_public_failure_from_exception` 的现有未提交分支已将该异常映射为 storage，而未知异常仍映射 execution。issue #198 的事故与此代码路径一致，但事故文字不是本 plan 的唯一依据。`dayu/cli/commands/fins.py:run_fins_direct_command` 外层未知异常目前用 `_LOGGER.exception` 写原始 traceback，现有 `tests/cli/test_fins_commands.py` 甚至断言秘密异常文本进入日志；因此只在 producer 增加安全日志不足以满足 download 的脱敏目标。

## 边界、语义 owner 与契约

- storage `source_integrity.py` 独占完整性事实及四值 `SourceIntegrityPreflightReason`；不改变任何完整性判定、repair 选择或下载来源行为。Fins `ingestion_runtime.py` 独占异常到 download public failure/direct error kind 的映射；`direct_events.py:FinsPublicFailure` 独占公共字段及校验、JSON 投影；CLI `output.py` 只打印已验证的公共字段。公开 `reason_code` 在唯一映射点由 storage enum 派生，不能从 `str(exc)`、路径、日志或 CLI 反推。
- 不让共享的 `direct_events.py` 导入 `dayu.fins.storage`：storage 包的 `__init__.py` 聚合多个具体仓储实现，而 `FinsPublicFailure` 是 CLI、Service、等待路径共用的轻量公共契约，直接持有 storage enum 会把仓储实现依赖带入所有消费者。在 `direct_events.py` 定义仅含四个当前公开值的 `FinsDownloadFailureReason(str, Enum)`，将未提交 `FinsPublicFailure.reason_code: str | None` 收紧为该公共 enum 或 `None`；`__post_init__` 只接受该 enum 或 `None`，且非空 reason 只允许 `kind=STORAGE`、`transport_category=None`。`ingestion_runtime.py` 在唯一异常投影点用显式、全覆盖 `SourceIntegrityPreflightReason -> FinsDownloadFailureReason` 映射，直接消费 `exc.reason`，不反解析字符串；测试断言映射键集合等于 storage enum 全集，并对每一对语义对应的枚举成员断言 `.value` 相等。公开词汇必须保留四个 storage 原值；未来更名须显式裁决公开合同，不能静默漂移或靠字符串偶合穿透。`to_json_value()["reason_code"]` 输出公共 enum `.value` 或 `null`；CLI 的 `reason=` 输出同一 `.value` 或既有空占位符。不存在旧值兼容读取。业务展示仍用 `safe_message` 与 `retry_hint`；LLM 可见内容不要求模型凭内部代码推理，若该 JSON 进入 LLM 上下文，需同源附带现有可读消息。
- 对四个 preflight reason 均用同一个 storage public failure 分类和安全消息，保留枚举原值；`UNSAFE_PUBLICATION` 的恢复提示明确先检查/修复工作区来源状态，重复下载不会自行修复。其它三个 repair 选择失败不得误称非法文件；统一提示写“检查并修复工作区来源状态”，不猜具体损坏原因。direct `error_kind=STORAGE` 与 `failure.kind=STORAGE` 一致。provider、OSError、unknown 现有分类不变，unknown `reason_code=None`。
- 未知 `EXECUTION` 异常的 Fins `retry_hint` 由 `ingestion_runtime.py` 给出入口无关的恢复语义“请保存脱敏诊断并排查失败原因后重试。”；不得包含 `--log-file` 等 CLI 参数。CLI 展示 owner 在 `dayu/cli/output.py` 独占一处 CLI 日志提示常量，文案为“请使用 --log-file PATH 重试并查看日志”；这里的“日志”指运行日志，不承诺每个 `EXECUTION` 均有 `fins.download.*` unknown 异常诊断。仅在已验证的 `FinsPublicFailureKind.EXECUTION` download 失败详情后追加同一提示，不改变公共 `retry_hint` 或 JSON/Service 投影；此分类也包含非异常的无来源文档失败，其运行日志可含普通 INFO 文档行，而已有文档 RESULT 详情仍可用于排查，不期待 unknown 诊断。CLI 提示不按异常字符串或 `reason_code` 重新分类；有无 `--log-file` 均给出可执行指引，显式指定时日志文件必须可读。storage 等其它分类不附加该运行日志提示。无来源文档的现有 Fins `retry_hint` 在默认临时日志下仍欠可操作，归后续 `fins-download-no-source-retry-hint` work unit，本轮不以 CLI 提示冒充 Service/JSON 路径的修复。
- 诊断产生点有两个：Fins producer 捕获 **download 且公共分类为 EXECUTION** 的异常；CLI 外层 catch 捕获在 producer/stream 之外逃逸的 **download 未知异常**。producer 先构造公共失败并发出失败 RESULT，再尝试记录安全 operator 日志；无来源文档是非异常 RESULT 路径，不产出 unknown 诊断。`run_fins_direct_command` 的 typed except 已先于最后的 `except Exception` 返回；最后一支当前对所有 direct 命令调用 `_LOGGER.exception`，会把原始 traceback 放进日志。只在最后一支按 `args.command_name == COMMAND_DOWNLOAD` 分流日志：download 使用安全记录，非 download 保留现有 raw traceback 日志行为；不得改动 typed except，也不得让 producer 已转成 RESULT 的失败被 CLI 重复记录。两点共用 `dayu.runtime.log` 的层中立 `safe_exception_trace(exc: Exception, *, source_root: Path) -> str`，由调用点传入各自文件定位出的 `dayu` 包根，不让 runtime import Fins/CLI。它只负责结构安全，不负责业务分类、日志装配或公开 failure。前者记录 `fins.download.unexpected_failure`，后者记录 `fins.download.command_unexpected_failure`，均为 ERROR；默认 INFO 阈值可接收记录，但未传 `--log-file` 时 CLI 使用进程期临时文件，退出后不可查看，因此 CLI 必须明确提示用户显式保存。外层所有 direct 命令的固定错误由“命令执行失败，”加 `output.py` 唯一日志提示组合，退役 `fins.py:_FINS_DIRECT_UNKNOWN_FAILURE_MESSAGE`；非 download 最终文案必须逐字保持现有“命令执行失败，请使用 --log-file PATH 重试并查看日志”（连同既有 `dayu-cli {command_name}: ` 前缀），仅日志分流发生变化。非 download 的 raw traceback 日志风险仍列为独立残余。
- `safe_exception_trace` 用 `traceback.walk_tb(exc.__traceback__)` 取 frame 的代码位置，不调用 `traceback.format_exception`、`exc_info=True`、`logger.exception`、`str/repr(exc)`、`linecache`，不读取 locals、异常 args、cause/context/notes。输出单行有界 `exception_type=<安全类型> custom_type=<安全指纹或 redacted> stack=<帧列表>`：沿 `type(exc).__mro__` 只取第一个能以 `vars(builtins).get(name) is class` 证实身份的内建异常类型；自定义异常类型只取其类型对象的 `__module__` 与 `__qualname__`，两者均须为 `str`，以 UTF-8 编码 `module + "\0" + qualname` 作 SHA-256 输入，仅输出摘要前 16 个小写 hex 字符，不输出原始名称/模块名；任一元数据读取、类型校验、编码或哈希失败时 `custom_type=redacted`。内建异常的 `custom_type=redacted`，该指纹只是 operator 诊断标签，不是业务原因或公开分类。每帧仅在 `frame.f_globals` 与 `sys.modules` 中真实 `dayu.*` 模块的字典同一、模块 `__file__` 与 `frame.f_code.co_filename` 经严格解析同一且位于传入的受信 `dayu` 包根、相对 `.py` 路径各片段为合法 Python 标识符时，输出包内相对路径和正整数行号；其它帧仅输出固定 `[external]`，不输出函数名、外部路径或源码行。最多保留最后 16 帧（包含抛出点），以固定 `truncated` 标志表示省略；无 traceback 输出固定 `[unavailable]`。禁止绝对路径、URL、源码行和任意异常文本进入生成串。用 `deque(maxlen=16)` 有界保存帧片段；函数有中文完整 docstring 与严格类型签名，常数有命名，输出只由受信片段构造而非事后正则替换原始 traceback。这是两处日志共享的最小层中立格式化能力，不新增日志治理框架或状态。
- helper 对 `Exception` 输入的**整个格式化过程不抛出**：逐帧路径/元数据校验失败降级 `[external]`，而遍历、类型指纹、容器或其它内部步骤出现非预期 `Exception` 时统一返回固定 `exception_type=redacted custom_type=redacted stack=[unavailable]`，绝不把失败异常或原始异常交给 logger。兜底只在 `dayu.runtime.log` 的共用 helper 内实现一次；producer 和 CLI 不各自复制宽泛 catch。故 helper 自身失败不能阻断原有 RESULT/CLI 固定失败投影；这不扩展为 RESULT 构造等其它二次失败的兜底承诺。
- 公开 RESULT、CLI stdout/stderr 和等待 JSON 不承载调用栈或异常类型；CLI 外层仍给固定未知失败提示。诊断也不进入 LLM-facing trace/memory。若后续发现 log handler 另行追加原始 `exc_info`，该 slice 不得宣告通过。

## 当前未提交改动的精确归属

计划只**接纳并修正**如下现有 hunk，不能把工作树现状视为已审查：`dayu/fins/ingestion_runtime.py` 的 import、typed public failure 分支、direct error 分类；`dayu/fins/direct_events.py` 的 `reason_code` 字段/校验/JSON；`dayu/cli/output.py` 的 `reason=` 打印；`tests/fins/test_fins_ingestion_runtime.py` 的 typed case；`tests/cli/test_output.py` 的 CLI 断言；`dayu/fins/README.md` 中 download public failure 那一行；`tests/README.md` 中 download 终态那一行；根 `README.md` 同一新增行中仅与 storage failure 展示/恢复相关的句子。对同一行同时写了点号元数据忽略行为的根 README hunk，实施时必须按句拆开并改写 #198 句为自足条件：“下载显示 `classification="storage"`、`reason="unsafe_publication"` 时，请检查工作区来源状态并修复后重试；重复下载不会自行修复。”另一 work unit 的点号句须独立成句且自足，不能让 #198 句依赖它作为主语或前提；两句分别可单独 stage。实际 README 变更仍以职责与真实行为为准，不能按整行/整文件机械 stage。

`dayu/fins/storage/_fs_source_integrity.py` 的全部点号元数据判断、`tests/fins/test_fins_storage_atomicity.py` 的 109 行点号/隐藏链接测试、`dayu/fins/README.md` 中 inspector 那一行、`tests/README.md` 中仓储完整性那一行、根 README 中点号忽略句，均属于独立 work unit；它们最终也进 PR #197，但不能计入 #198 的实现、验证或 checkpoint。`docs/reviews/*`、`docs/gateflow/upload-material-issue-198-repair-sequence-20260928.md` 与其它 oracle 文件不改。实施前后记录 `git status --short` 与相关 `git diff --binary` 摘要；若派发期间这些相关 hunk/HEAD 有并发变化，停止并重新裁定归属。只对本 issue hunk 做交互式 staging，检查 `git diff --cached --check` 和 staged patch；本 plan gate 不 stage/commit。

## 可验证行为 slice（默认 2 个）

### S1：封闭预检原因贯通到公共失败

目标/对齐：实现“storage reason 保真、可行动、非盲目重试”。允许文件：`dayu/fins/ingestion_runtime.py`、`dayu/fins/direct_events.py`、`dayu/cli/output.py`、`tests/fins/test_fins_ingestion_runtime.py`、`tests/cli/test_output.py`、`tests/service/test_fins_wait_adapter.py`、`tests/service/test_fins_direct.py`，以及命中职责范围的三份 README 的 issue 句子。以前述未提交候选 hunk 为起点，在公共失败契约定义独立的封闭 reason enum；异常投影点逐项映射 storage enum 并断言映射键全集及每对成员 `.value` 一致，JSON/CLI 在公共契约边界取 `.value`。测试覆盖全部四个 reason、public 与 direct kind、JSON/CLI 相同代码、非法 string/非 storage reason 被拒绝、provider/OSError/unknown 不被错误附 reason，且秘密 URL/path 不进公开结果。Service wait adapter 用固定 `unsafe_publication` 断言序列化 `failure.reason_code`，并断言 hint 仍来自 Fins 公共 `retry_hint`；不能只与 `failure.to_json_value()` 动态比较。`tests/service/test_fins_direct.py` 运行现有 direct 消费者回归。完成信号：相关测试通过且不存在另一个消费者重算 reason。此 slice 不实现日志，也不修改 storage inspector。

### S2：未知 download 异常的安全 operator 调用栈

目标/对齐：实现“generic 公共失败 + 可查看的脱敏异常类型/调用栈”。依赖 S1 的公共分类。允许文件：`dayu/runtime/log.py`、`dayu/fins/ingestion_runtime.py`、`dayu/cli/output.py`、`dayu/cli/commands/fins.py`、`tests/runtime/test_log.py`、`tests/fins/test_fins_ingestion_runtime.py`、`tests/cli/test_output.py`、`tests/cli/test_fins_commands.py`，以及按职责检查后的 README。先在 runtime 增加上述纯格式化 helper；producer 对 download unknown EXECUTION 先发失败 RESULT、再记录一次安全日志，避免 typed preflight 被诊断为未知；CLI 最后一个 catch 只对 download 使用同一 helper 代替 raw traceback，非 download 保持原始日志行为。Fins 未知异常的公共 hint 改为入口无关；CLI 的 EXECUTION 失败展示与所有 direct 命令的外层固定错误共用 `output.py` 唯一运行日志提示，外层删除 `fins.py` 的重复提示常量，并以原非 download 完整文本作逐字断言。`tests/runtime/test_log.py` 用带 URL、token、用户绝对路径的 message/cause、外部帧文件名、两种不同动态异常类名、深栈和无 traceback 验证安全内建祖先、固定长度 hex 指纹可区分且无原始类型名/秘密、受信包内相对路径及抛出行号；注入遍历/元数据/哈希意外失败，断言 helper 不抛出且仅返回固定安全串。producer 与 CLI 的测试再让共用 helper 内部失败，断言 RESULT/固定 CLI 失败和退出码不变、无原始 traceback 或秘密进入日志/stderr；producer 测试还须观察失败 RESULT 先于安全日志写入；真实 logger 记录为 ERROR 且不带 `exc_info`。另断言 typed storage 不产生 unknown 日志；无来源文档的非异常 EXECUTION 有文档 RESULT 详情、可查看普通 INFO 运行日志，但不期待 `fins.download.*` unknown 诊断；未知异常路径则必须有对应安全诊断。CLI 外层旧“raw traceback 入日志”断言改为 download 安全诊断断言，CLI 有无 `--log-file` 均提示具体保存/查看做法，显式文件可读；分别固定 download 与非 download 外层错误文本，并验证非 download 原始日志行为保留。完成信号：未知异常的显式 `--log-file` 可读到同一安全记录，且无 raw `exc_info`；无来源文档不以 unknown 诊断作为通过条件。不引入通用异常注册器、日志持久化状态机或响应内容日志。

## 验证与文档决策

实施后在 `.venv` 中执行：

```bash
source .venv/bin/activate
python -m pytest tests/runtime/test_log.py tests/fins/test_fins_ingestion_runtime.py tests/cli/test_output.py tests/cli/test_fins_commands.py tests/service/test_fins_wait_adapter.py tests/service/test_fins_direct.py -q
python -m pyright dayu/ tests/ utils/
```

受影响测试的断言以上述两个 slice 为准；pyright 必须没有新增或扩散错误，涉及已有错误时按 AGENTS.md 修复到不扩散。单文件覆盖率目标 ≥80%，只在确有未覆盖 owner 分支时加定向用例。日志测试须配置/恢复 `dayu` namespace logger handler，捕获实际格式化文本，不只检查 helper 返回值。

真实 CLI 只在独立 `/private/tmp/issue198-cli.XXXXXX` 工作区执行，不指向用户原 workspace。用 `mktemp -d /private/tmp/issue198-cli.XXXXXX` 创建目录并显示、核对真实路径；**不运行 `dayu-cli init`**，因为它要求交互式模型选择并可能写入用户环境设置，而 direct download 由 `FinsDirectCommandService.from_workspace_root` 构造，`DefaultFinsRuntime.create` 使用 `create_directories=False`；fresh workspace 是否真能首次建库仍由本次 baseline 实跑判定，不能由该构造参数推定。先执行 `.venv/bin/dayu-cli --base "$case_root" download --ticker 000333 --forms FY --start 2025-03-28 --end 2025-03-28 --log-file "$case_root/baseline.log"` 建立真实来源；须确认退出 0、确实选中至少一个候选且 `portfolio/000333/filings/` 下有至少一个带 identity/meta 的真实 published filing 目录；若失败，区分网络/provider 阻塞与“不 init 可建库”假设被证伪，后者须退回 plan/re-review，均不得用旧事故证据或 mock 顶替。只在该临时 workspace 的 `portfolio/000333/filings/` **根**放一个唯一命名、非点号的普通外来文件，不覆盖 manifest 或既有条目；`_inspect_source_kind_unguarded` 对这个无从归属的 root entry 设置 `unassignable_root_fact` 并在 whole-kind preflight 抛 `UNSAFE_PUBLICATION`。再用同参、独立 log 文件重跑。预期退出 1、`classification="storage"`、`reason="unsafe_publication"`、修复后重试提示，且没有 `execution`/盲目重试。保留并分别核对第二次运行的 RESULT/`Fins failure detail` 与 CLI stdout/stderr 失败文本、新增 `fins.download.*` 安全诊断记录、其它普通 INFO 行：前两类不得含原始异常文本、URL/token 或绝对路径；普通 INFO 单独列出命中行并按其业务语义判断，不能仅因出现用户传入的 `$case_root` 就判为本失败投影泄漏。记录命中通道、行号和所属类别，避免混合全量搜索误判。此 typed storage 案例预期不生成 unknown 诊断；未知异常的秘密注入与日志隐私由 owner/CLI 测试验证，不能声称普通真实 CLI 稳定复现未知异常。结束后由执行人核对只清理该临时目录。

README 决策：`dayu/fins/README.md` 应说明 storage 原因经唯一映射成为封闭公共失败原因，以及诊断边界；根 `README.md` 的下载章节应只加入自足的用户可执行 storage 恢复句和 `--log-file` 定位方式，不写内部 owner/枚举推理规则；`tests/README.md` 仅更新已有测试分层/覆盖事实，若新测试不改变其读者需要则不新增清单。实施前按各 README 顶部 `Agent更新约束` 和实际改动再确认。`dayu/README.md` 不触发：既有 UI/Service/Host/Engine 装配边界不变；`dayu/config/README.md` 等不触发。当前 README 中点号元数据文字属于独立 work unit，须隔离，不修改其业务事实。

## 风险、PR 边界与报告

- 类型名/帧元数据脱敏依赖严格受信根校验。若无法证明动态/外部类型和路径不会进入日志，S2 停止，不改用 `exc_info=True` 或原始 traceback。最多 16 帧可能隐藏最外层入口，但保留抛出点；这是明确的有界诊断取舍。
- 网络或 provider 状态会使隔离真实 CLI 初次建库不稳定；必须报告为 validation gap，不从 issue 事故文字推断本次通过。点号元数据独立修改若改变复现条件，不改 #198 期望分类。
- CLI 外层其它 direct 命令仍可能原样记录异常；不是本 work unit 的 download 成功信号，留给单独安全审查。issue #198 提到的协议响应特征日志也保持非目标。
- producer 在已捕获异常后若公共失败对象或 RESULT 投影自身再次抛错，仍可能只发 Done、由 `threading.excepthook` 输出原始 traceback；本轮先发 RESULT 再尝试写安全日志，避免日志写入抢先阻断公共失败，但 logger 自身若再次抛出仍可能泄出原始 traceback。`safe_exception_trace` 自身失败在本轮保证安全，不承诺所有二次投影失败均安全。此残余归后续 `fins-direct-projection-failsafe` work unit，本轮不新增投影兜底或对应实现测试。
- `SourceIntegrityRepairBlockedError` 与 `SourceIntegrityRevisionConflictError` 仍会落 `EXECUTION`、安全诊断事件和可能误导重试的公共提示；其业务分类归后续 `fins-download-storage-sibling-errors` work unit 单独 goal confirmation，本轮不把二者偷纳入 preflight 映射。
- 非 download direct 命令及后台 job 的原始 traceback 审查归后续 `fins-other-raw-diagnostics-audit` work unit。奇异安装布局可能令全部受信帧降级 `[external]`；本轮用当前布局的真实 dayu 帧测试验证，跨布局诊断退化留在 closeout。工作树中点号元数据 hunk 归另一 work unit，只做 hunk 级隔离。
- 无来源文档的 Fins 公共 `retry_hint` 在默认临时日志模式下仍可能指向退出后不可查的日志；其 Service/JSON 路径修复归后续 `fins-download-no-source-retry-hint` work unit，本轮只让 CLI 的共用提示准确指向运行日志，不承诺 unknown 诊断。
- PR #197 已是 `codex/upload-material-oracle` → `main` 的 open draft，当前 body 主要描述旧 CNInfo work unit。后续获授权进入 PR gate 时复用并更新该 PR 的事实、issue #198 关联及新增改动 review，不新开 PR、不把独立点号元数据当作 #198、也不把既有混合提交当作本 issue 已审查。此 plan 不执行 push、PR 操作或 issue 评论；merge 由用户手工完成。

本方案只有两个行为增量：先建立封闭原因的同源公开契约，再使未知 download 异常可安全诊断。每个文件/测试/文档变更都对应 goal 的保真或脱敏成功信号；没有新 schema、下载策略、仓储规则或通用治理框架，因此没有过度设计或 goal drift。完成报告须写明实际改动、验证命令与结果、README 决策、未覆盖风险、artifact 路径和下一 gate；本次 plan fix 的下一入口是 `plan re-review`，不自动进入实施。

## Plan review finding fix 记录（本次只修 plan）

| 裁决项 | plan fix 状态 | 修订位置与下一步验收 |
| --- | --- | --- |
| Kimi F1 / MiMo F1：安全 helper 自身失败 | 已修复（计划层） | `safe_exception_trace` 对 `Exception` 输入整体不抛出，共用实现内固定安全降级；S2 注入内部失败并断言 producer/CLI 失败投影不变。待 re-review 与实施测试。 |
| MiMo F2：自定义类型全抑制 | 已修复（计划层） | 规定内建祖先 + `__module__`/`__qualname__` 的 16 hex SHA-256 指纹，元数据失败回 `redacted`；两类区分且原名不外泄。待 re-review 与实施测试。 |
| MiMo F3：默认日志不可查及提示 owner | 已修复（计划层） | Fins hint 保持入口无关；CLI `output.py` 独占 `--log-file PATH` 文案，RESULT 与外层 catch 复用；测试有/无 flag 和显式文件可读。待 re-review 与实施测试。 |
| Kimi F4：Service 消费者测试 | 已修复（计划层） | S1 与 pytest 命令加入两份 Service 测试，wait JSON 直接断言固定 `unsafe_publication`。待 re-review 与实施测试。 |
| MiMo F4：根 README 句子悬空 | 已修复（计划层） | #198 句改为“下载显示……”自足条件；点号句独立归属、分别 stage。待 re-review 与实施文档核对。 |
| MiMo F5：真实 CLI 隐私断言 | 已修复（计划层） | 按 RESULT/CLI 失败文本、安全诊断、普通 INFO 分组核对，记录通道及行号；未知异常秘密注入交 owner 测试。待 re-review 与实跑。 |
| MiMo OQ4：双 enum value 漂移 | 已修复（计划层） | S1 对全量映射键与每对成员 `.value` 相等作固定断言，未来更名须显式裁决。待 re-review 与实施测试。 |
| Kimi F2：投影机制自身二次失败 | 未修复（裁决延期） | `assigned to later work unit`：`fins-direct-projection-failsafe`；本轮不实现 RESULT 构造兜底，不宣称覆盖所有二次失败。 |
| Kimi F3 / MiMo R2：其它 typed storage 异常 | 未修复（裁决延期） | `assigned to later work unit`：`fins-download-storage-sibling-errors`；本轮不扩大 preflight 分类。 |
| MiMo re-review F1：外层固定错误文案归属 | 已修复（计划层） | `output.py` 独占 CLI 日志提示；所有 direct 外层固定错误复用，删除 `fins.py` 重复常量；S2 固定非 download 最终文案逐字不变及 download 文案。待 re-review 与实施测试。 |
| MiMo re-review F2：EXECUTION 提示误承诺 unknown 诊断 | 已修复（计划层） | 共用提示只指运行日志；S2 区分未知异常安全诊断与无来源文档非异常 RESULT/普通 INFO，后者不期待 unknown 诊断。无来源文档公共 hint 归 `fins-download-no-source-retry-hint` 后续 work unit。待 re-review 与实施测试。 |
| MiMo re-review 次要风险：producer 日志早于 RESULT | 已修复（计划层） | S2 明确构造公共失败、发出失败 RESULT 后记录安全日志并验顺序；logger 二次失败仍归 `fins-direct-projection-failsafe`。待 re-review 与实施测试。 |

上次 fix 记录：已读 goal、原两份 review、总控裁决、相关代码与工作树；当时 HEAD 与 goal 记录的 `97a8eec8` 一致。上次静态检查与基线测试记录不作为本次重试的工具成功证据或实施验收。

本次修复性重试仅修改本 plan，核对第一次 re-review 与追加裁决、goal、相关 CLI/Fins 代码、HEAD 和工作树；前后 HEAD 均为 `97a8eec81fd1f19f514dbcf5a9c5cedf82334c4e`，其它路径的 `git status --short` 列表未变。静态检查确认 S1/S2 各一次、单一 CLI 提示与非 download 逐字文案、无来源文档不期待 unknown 诊断、RESULT 先于日志、延期项和 finding 状态均在文内；文件无 NUL/行尾空白且有末尾换行；`git diff --check` 退出 0（本 plan 尚未跟踪，故另作文件内容检查）。无产品代码、测试、README 变更，故不运行实施后的 pytest、pyright 或真实 CLI，也不把总控记录的既有基线测试算作本次验收。**plan review gate 仍待 Kimi/MiMo re-review 与总控裁决**。

残余风险分类：`fins-direct-projection-failsafe`、`fins-download-storage-sibling-errors`、`fins-other-raw-diagnostics-audit`、`fins-download-no-source-retry-hint` 均为 `assigned to later work unit`；点号元数据 hunk 归另一 work unit 并在本次与 #198 隔离；奇异安装布局的受信帧降级风险由 S2 当前布局测试覆盖，跨布局诊断能力留待 closeout 记录；网络/provider 或 fresh workspace baseline 失败属本 work unit 的待取得验证证据，不能宣告真实 CLI 通过；本 plan 的 helper、Service、enum、文档与隐私断言均仍需实施后验证。没有把延期项加入 S1/S2 允许修改文件或成功信号。
