# issue #198 S2 implementation：未知 download 的安全 operator 调用栈

- Gate：`implementation S2`；下一入口：`code review S2`，由总控裁决后续 gate。本记录不宣告 code review 或 final closeout pass。
- 基线：`codex/issue198-s2`，HEAD `7234d42dbaea603112c6fed52776281228d261a7`；修改前 `git status --short` 为空，`.venv` 中 Python 3.11.15 的 `dayu.__file__` 指向本 checkout 的 `dayu/__init__.py`。
- Scope：仅 S2 的四个生产文件、对应四个测试文件、职责命中的三份 README 和本实施记录；没有修改 S1、计划、goal、adjudication、旧 review 或主队列；没有 commit、push、PR、外部消息或子 Agent。

## 动机、owner 与实现

直接代码证据：S1 的 `ingestion_runtime.py:_download_public_failure_from_exception` 已拥有 download 公共分类，`_run_direct_stream_producer` 捕获未知异常后只发失败 RESULT；`commands/fins.py:run_fins_direct_command` 最后的宽 catch 原样以 `logger.exception` 写入所有 direct 命令的 traceback。未知 download 因此缺少可安全保存的 operator 诊断，外层又可能泄露异常原文。S2 动机成立，现有分层中的 owner 足以闭合，不需要新 schema 或通用日志框架。

- `dayu/runtime/log.py`：新增层中立的 `safe_exception_trace(exc, *, source_root)`。它仅按身份验证安全内建异常祖先；自定义类型仅输出基于模块名与限定名的 SHA-256 前 16 位十六进制指纹。帧必须属于 `sys.modules` 中字典同一的真实 `dayu` 模块，模块文件与代码文件严格解析为同一路径，且在调用方传入的包根内；只输出合法 Python 相对 `.py` 路径与正行号。外部帧为 `[external]`，无 traceback 为 `[unavailable]`，最多保留末 16 帧及截断标志，帧路径与行号另有限界。格式化内部异常统一返回固定安全串，不读取异常消息、args、cause、locals、源码行或原始 traceback 文本。
- `dayu/fins/ingestion_runtime.py`：沿既有 Fins owner 分类。仅 download 公共 `EXECUTION` 异常先投递失败 RESULT，再记一次 `fins.download.unexpected_failure` ERROR；诊断使用同一 owner 解出的 cause。typed storage 不产生该日志。未知异常公共 `retry_hint` 改为入口无关的保存脱敏诊断指引。
- `dayu/cli/output.py`：独占 `请使用 --log-file PATH 重试并查看日志` 提示；只在已验证的 download `EXECUTION` 失败详情后显示。`dayu/cli/commands/fins.py`：外层最后 catch 仅 download 使用同一安全 helper 记录 `fins.download.command_unexpected_failure` ERROR；非 download 仍用原始 `logger.exception`，所有 direct 外层固定错误仍逐字为原有文案，删除重复提示常量。

## 测试与验证

- `tests/runtime/test_log.py`：安全内建祖先、两种动态类型指纹、message/cause 的 URL、token 与绝对路径、外部伪造帧文件名、受信包内相对帧与真实抛出行、深栈、无 traceback、非法类型元数据、遍历与哈希故障。
- `tests/fins/test_fins_ingestion_runtime.py`：未知 download 的 RESULT 先于一次真实 ERROR 日志、无 `exc_info`、helper 内部故障仍保留公共终态；OSError 和四种 typed preflight 不产出 unknown 日志；非异常的无来源文档 `EXECUTION` 保留文档 RESULT 详情但不伪造 unknown 诊断。
- `tests/cli/test_output.py` 与 `tests/cli/test_fins_commands.py`：execution 详情只追加一次提示、storage 不追加；外层 download 有无显式 `--log-file` 均显示固定文案，显式日志文件可读到安全诊断；helper 内部故障不改变退出码或泄露原文；非 download 的原始 traceback 日志和完整固定用户文案保持。
- `source .venv/bin/activate` 后运行计划列出的八个受影响 pytest 文件，带四个修改生产文件的单文件 coverage：**856 passed，3 warnings**；`dayu/runtime/log.py` **94%**、`dayu/fins/ingestion_runtime.py` **91%**、`dayu/cli/output.py` **85%**、`dayu/cli/commands/fins.py` **85%**。`python -m pyright dayu/ tests/ utils/`：**0 errors、0 warnings**。`git diff --check` 通过。
- 隔离真实 CLI：在 `/private/tmp/issue198-cli.GIJPem` 执行计划中的 `000333 / FY / 2025-03-28` 初次 download，退出码 0，日志 INFO 为 `total=0 downloaded=0 skipped=0 failed=0`，公开摘要为 `discovered=0`，`portfolio/000333/filings/` 无子目录。因此计划要求的至少一份真实已发布 filing 前提未满足，未放外来文件，也未把 typed storage 复跑记为通过。这一探针只说明该精确筛选本次未发现候选，不能据此推断网络、provider 或 storage 的一般状态。已核对并只清理本次新建的隔离目录，关键观测保留在本记录。

## 文档与残余

- 已先读取各 README 的 Agent 更新约束。根 `README.md` 只校正最终用户对外层固定错误、download 失败详情及日志定位的说明；`dayu/fins/README.md` 记录 Fins 公共失败与 operator 诊断边界；`tests/README.md` 仅更新已有测试覆盖事实。`dayu/README.md` 的跨包装配职责未变化，无需更新。
- **需总控裁决当前验证缺口**：计划指定的真实 CLI 日期筛选没有候选，typed storage 实跑尚未完成。若该证据仍为 S2 接受前提，需先确定有真实候选的隔离验证输入或修订验证计划；不能用本次 `exit 0` 代替候选/发布证据。
- **assigned to later work unit** `fins-direct-projection-failsafe`：RESULT 构造或 logger handler 自身再次失败的安全收口不在 S2；本轮只保证共享格式化 helper 内部失败不抛。
- **assigned to later work unit** `fins-other-raw-diagnostics-audit`：非 download 外层与其它既有路径的原始 traceback 日志。
- **assigned to later work unit** `fins-download-storage-sibling-errors`：其它两个 typed storage sibling 的公共分类。
- **assigned to later work unit** `fins-download-no-source-retry-hint`：无来源文档在 Service/JSON 等入口的既有 retry hint 可操作性。
- 奇异安装布局可能令受信帧降级为 `[external]`；当前 checkout 的真实包内帧已由 owner 测试覆盖，此处为有界脱敏取舍，不扩大 S2 范围。
