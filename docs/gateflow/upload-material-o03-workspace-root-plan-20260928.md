# UM-O03-F01：CLI workspace root 目标类型 plan

- Gate：`plan review -> fix`；本次 label：`o03-plan-fix2-sol-20260928-01`；日期：2026-09-28。
- 工作区：`/private/tmp/dayu-upload-o03`；分支：`codex/upload-material-o03`；基线 HEAD：`8d8d494fbbce0052372fb1b42097c9f7222cfa28`。
- 范围依据：本 worktree 的 `docs/gateflow/upload-material-o03-workspace-root-goal-20260928.md`（goal confirmation pass），以及主工作区冻结裁决 `docs/reviews/upload-material-um-o01-o06-oracle-adjudication.md` 的 UM-O03-F01 节。裁决里的 `storage_io` / exit 1 是历史观察，不是本 HEAD 的通过证据。
- 当前状态：第一次双路 plan re-review 已完成；本次按总控追加裁决收口验证方案，等待第二次 Kimi/MiMo 双路 `plan re-review`；没有代码、测试或 README 实施。此文件是本轮唯一修改的产物。

## 目标、动机和边界

目标：对 CLI 已解析的 `--base` / `--workspace`，若规范化后的**现存目标不是目录**，在装配 Service、读取上传文件、调用 converter 或发布 material 前，由公共 CLI workspace 路径 owner 抛出可操作且不包含原始绝对路径的用法错误。Fins direct `upload_material` 是验收入口；所有使用同一普通 CLI 路径契约的入口共用判定。预期 Fins CLI stderr 带命令前缀和 `--base` 目录提示，退出码为 `EXIT_USAGE_ERROR`（2），无业务发布，原普通文件字节不变。

保留已确认正常语义：重复 scalar `--base` 最后值生效；相对路径、默认 cwd 的 `./workspace`、路径内部空格与 Unicode；指向目录的 symlink 解析到目录；尚不存在的目标仍交现有装配流程处理。统一裁剪 workspace 参数首尾空白：Session 入口原本如此，Fins 原本仅用 `strip()` 判空、实际解析未裁剪原文，因此 Fins 的首尾空白输入行为会改变；不为旧行为留兼容分支。悬空 symlink 仍解析为其缺失目标的绝对路径，再交现有装配流程。`init` 的请求路径 no-follow、symlink 禁止、bootstrap 和原子性不变。`upload_filings_from` 的脚本输出路径规则不随本 work unit 改写。

非目标：Fins storage、Service/Fins runtime、material 字段验证、Docling、仓储协议或 schema/state machine；不加兼容旧 `storage_io` 的分支；不把 symlink 一概拒绝；不承诺解决权限、特殊路径、父路径非目录或校验后类型竞争。只在 CLI 路径 owner、直接消费者和必要测试/文档上动手。

## 第一性原理判断与直接证据

问题成立，但严重性限于 CLI 用户无法按错误修正路径，以及错误在下游装配/存储阶段才显现；当前证据不支持声称材料已被错误发布或存在通用仓储损坏。`dayu/cli/commands/fins.py` 的 `_resolve_workspace_root` 只做空文本检查与 `Path(...).expanduser().resolve(strict=False)`；`_run_fins_direct_command_async` 随后把路径传入 `FINS_DIRECT_SERVICE_FACTORY`，再打开 stream。`run_fins_direct_command` 已将 `CliFinsUsageError` 投影成 `render_cli_error` + exit 2，因此缺失的是请求目标类型判定，不是新建下游 storage 错误映射。冻结 UM-018 的通用 `storage_io` / exit 1 与该代码路径一致，但不代替当前 HEAD 的运行证据。

`dayu/cli/agent_entrypoint.py:resolve_workspace_root` 已供 `dayu/cli/session_execution.py` 的 prompt/interactive/session resume 和 `dayu/cli/commands/session.py` 的 list/purge 使用，当前同样只校验文本。它所在模块还静态导入 `dayu.service.host_assembly.ServiceRunOverrides`，并承载 SIGINT/执行 override：独立的纯 UI 路径 owner 可供今后路径消费者直接使用，不必为此引入 Agent/Service 装配。当前 Fins、session_execution 和 session 仍因 SIGINT 等其它职责 import `agent_entrypoint`；本迁移不声称即时消除这些既有 import。`dayu/cli/commands/init.py` 保留原始请求路径，用 no-follow 检查 symlink，再 bootstrap；其语义不同，不能复用普通 CLI resolver。`dayu/cli/arg_parsing.py` 已将 `--base`、`-b`、`--workspace` 映射到一个 `workspace_root`，重复值由 argparse 决定；路径 owner 不再解析 argv。

## 唯一 owner 与具体设计

1. 新建轻量 `dayu/cli/workspace_root.py`，仅依赖标准库，成为普通 CLI workspace 参数的**唯一**文本裁剪、空值报文、路径规范化与现存目标类型 owner。将 `resolve_workspace_root(value: str, *, error_factory: Callable[[str], ValueError]) -> Path` 的入口契约从 `agent_entrypoint` 迁过去，不留兼容 re-export/wrapper；新模块自持 `--base` 报错字段名常量，直接对 `value.strip()` 的结果判空并用 `error_factory` 抛 `--base must not be empty`，然后用裁剪后的文本执行 `expanduser()`、`resolve(strict=False)`。`agent_entrypoint.require_cli_text` 留在原处，只服务其它 CLI 文本字段；workspace 文本不再调用它，也不从含 Service import 的旧模块回引。`resolve` 后只对最终目标做目录类型校验：以 `Path.stat()` 读取最终目标类型，`FileNotFoundError` 代表目标尚不存在并返回解析后的路径；悬空 symlink 同样返回其缺失目标的绝对路径。现存且 `stat.S_ISDIR(mode)` 为假时通过 `error_factory` 抛出单一、无路径的 `--base must point to a directory; choose a directory path`。其它 `OSError` / `RuntimeError` 保持操作异常传播，不伪装成用法错误。该检查是请求 admission，不是仓储对路径 identity 或发布原子性的保证。
2. `dayu/cli/session_execution.py` 与 `dayu/cli/commands/session.py` 改从新模块直接 import resolver，保留各自现有 `usage_error_factory`、命令前缀和 exit 2 投影。`agent_entrypoint.py` 删除旧 resolver、仅供它使用的 `BASE_OPTION_NAME` 和 `__all__` 项，并更新不再准确的模块概览 docstring；其它通用文本/SIGINT/override helper 仍留原 owner。此处不另建 `dayu.runtime` helper：规则是 CLI 参数用法及其异常工厂，不是跨层 runtime 基础能力。
3. `dayu/cli/commands/fins.py` 从新模块直接 import resolver，并在 direct 与 `upload_filings_from` 两条调用处传 `error_factory=CliFinsUsageError`；只删除私有 `_resolve_workspace_root`。`_BASE_OPTION` 仍被 `_upload_batch_command_argv`、`_upload_batch_regeneration_argv` 用作生成脚本的 `--base` argv token，必须保留，不改为内联魔法字符串；新模块的报错字段名常量独立归其 workspace 参数 owner。现有 `run_fins_direct_command` 已处理该异常并返回 2，不改 `main.py`、`output.py`、Service 或 Fins 错误契约。普通目录 symlink 在 `resolve(strict=False)` 后检查其目标类型；指向文件的 symlink 归入非法最终目标。`init` 不接入新 helper，因其 no-follow 合同单独成立。

CLI 内部 import 路径和 Fins 首尾空白参数的解析行为发生上述收敛；CLI argv、Fins/Service 公共接口、schema、持久化状态和错误事件格式不变。按总控对 goal“路径安全”的裁决，新用法文案保留可操作的 `--base` 目录提示，不回显用户路径；同一 owner 产出同一原因，各命令只负责既有前缀与退出码。

## 一个可验证实施切片

**S1：普通 CLI workspace 路径在装配前拒绝现存非目录。** 前提为本 plan review 通过。一次 implementation/review pass 完成 `workspace_root.py` 的 owner 行为、全部直接调用者收敛、对应测试和按职责必要的 README。一个切片足以形成完整用户可见增量；按文件或层拆片会留下暂时不一致的路径规则并增加 gate 成本。

允许文件：`dayu/cli/workspace_root.py`（新）、`dayu/cli/agent_entrypoint.py`、`dayu/cli/commands/fins.py`、`dayu/cli/session_execution.py`、`dayu/cli/commands/session.py`、`tests/cli/test_workspace_root.py`（新）、`tests/cli/test_fins_commands.py`、`tests/cli/test_upload_filings_from_command.py`；README 决策见下节。Session list/purge、prompt、interactive 维持 owner 级测试 + AST 调用点收敛断言 + 各入口既有 usage→exit 2 测试，不写普通文件 `--base` 的镜像用例；实施时若某消费者错误投影实际失败，先定位该入口 owner 再决定定向用例，不预增切片。不得改 `init.py`、Fins/Service/storage、goal 或冻结 adjudication。

实现顺序：先在新 owner 建立文本和目标类型规则及 owner 级测试；再一次性迁移 import、替换 Fins 两个调用并删除私有 resolver；最后加 CLI 真实进程验收与必要回归。`_run_fins_direct_command_async` 中路径校验仍在 `FINS_DIRECT_SERVICE_FACTORY` 前。Fins direct 的既有 download/filing 静态参数校验顺序不变；若其它独立静态错误先命中，按原有错误报告，不为路径检查重排业务验证。

完成信号：所有普通 CLI 入口只从 `dayu.cli.workspace_root` 获取该解析规则；普通文件 `--base` 为路径用法错误且没有 Service factory、上传读取、converter、material publication，`upload_filings_from` 也在计划生成/脚本发布前拒绝；已确认正常路径语义保持，首尾空白按上述统一规则；受影响测试和 pyright 通过。若实施发现 `init` 以外的独立路径合同与本 owner 冲突，或必须扩大到 Service/Fins 才能实现成功信号，停止并回到 goal confirmation，不添加下游补偿。

## 测试和验证方案

- `tests/cli/test_workspace_root.py` 直接断言空文本与纯空白用同一 `error_factory` 抛准确的 `--base must not be empty`；现存普通文件、指向文件的 symlink 用准确无路径的目录提示拒绝；现存目录、目录 symlink、尚不存在的目标、相对路径返回预期绝对规范化路径。分别固定首尾填充空白被裁剪、路径内部空格/Unicode 被保留；悬空 symlink 解析到缺失目标的绝对路径并放行，而非返回 symlink 名或按 no-follow 拒绝。必要时断言非 `FileNotFoundError` 的 stat 故障不被错映射为 usage。测试只固定 owner 契约，不靠 fake storage 制造结果。
- 在同一 `test_workspace_root.py` 加轻量 AST owner/import 收敛断言：新模块的 import 仅来自 Python 标准库，不 import `agent_entrypoint`/Service；`agent_entrypoint` 无 resolver 定义、import 或兼容转发；`fins.py`、`session_execution.py`、`commands/session.py` 直接从 `dayu.cli.workspace_root` import resolver，Fins 的两个调用点均使用它。检查限定路径 owner 与直接消费者，不把无关模块 import 清单固化为测试。空值报文和 trim 只由新 owner 负责，`require_cli_text` 仍负责其它字段。
- `tests/cli/test_fins_commands.py` 用真实 parser/main 与禁止调用的 `FINS_DIRECT_SERVICE_FACTORY` 确认 `upload_material --base <ordinary-file> --files <不存在的上传输入>` 仍输出命令前缀 + 同一目录提示、exit 2、factory 零调用，而非上传文件错误；结合 resolver 先于 factory、文件读取在 factory 后的调用顺序，证明 base 错误先于上传输入读取，不用 atime 推断。断言原 `--base` 文件字节不变且无 material 树。可用同组参数覆盖指向文件的 symlink 与目录 symlink；目录 symlink 的正常流程可用记录 factory 断言收到规范化目标。对缺失路径用记录 factory 验证仍传入原规则的绝对目标，不要求本测试启动 converter。
- 同在 `tests/cli/test_fins_commands.py` 增加真实 parser/main 路径回归：一次 argv 中给两个 `--base`，令首值为普通文件、末值为有效目录，并用记录 factory 断言只收到末值规范化路径；分别以 `-b`、`--workspace` 传有效目录，断言与 `--base` 映射到同一目标；`monkeypatch.chdir(tmp_path)` 后省略全部 base 选项，断言默认 `./workspace` 按该 cwd 解析为 `tmp_path / "workspace"` 并传给 factory。测试使用静态合法命令参数和记录 factory，不依赖真实 converter；路径内部空格/Unicode 与相对路径继续由 owner 测试固定。`test_arg_parsing.py` 不在允许文件内，也不靠其既有单值用例冒充这些回归。
- `tests/cli/test_upload_filings_from_command.py` 新增普通文件 `--base` 的真实 parser/main 用例，提供有效 `--ticker` 与最小 `--from` 源目录；断言命令前缀 + 同一目录提示、exit 2、base 字节不变、无脚本发布。将 `generate_upload_batch_plan` 和 `publish_upload_script` 设为禁止调用，证明拒绝早于源目录扫描/计划生成及发布；不改变该入口的脚本输出路径合同。既有该文件回归须覆盖 `_BASE_OPTION` 保留后的两处生成脚本 argv `--base` token。
- 必做真实 CLI 子进程复验：在隔离临时目录创建普通文件 `base`，使 `--files <input>` 指向不存在的上传输入，以当前运行测试的 `sys.executable -m dayu.cli upload_material --base <base> --ticker AAPL --forms 10-K --material-name sample --files <input>` 运行；子进程 cwd 设为该临时目录，清除继承的 `PYTHONPATH`，依赖当前 checkout 的 editable 安装。常驻测试的期望代码树从测试文件本身动态推导：`Path(__file__).resolve().parents[2] / "dayu" / "__init__.py"`；同一 executable/env/cwd 下先以 `-c` 导入 `dayu`，比较子进程 `Path(dayu.__file__).resolve()` 与该期望树，同时比较子进程 `Path(sys.executable).resolve()`、`Path(sys.prefix).resolve()` 与当前测试解释器的对应值。身份不符即让测试失败，不继续把别的 checkout 当成本次验收；不写死本隔离 worktree 或其 `.venv` 的绝对路径。再断言 CLI exit 2、stderr 是 base 路径用法错误而非上传文件或 `storage_io` 错误、且不含绝对路径；stdout 无成功发布，`base` bytes 与目录快照不变，无 material 产物。用同一真实入口回归目录 symlink（若正常命令会进入 converter，可仅断言未以 base 类型拒绝并结合 owner/factory 测试，不以转换成功作为本 work unit 验收）。当前 UM-O03-F01 的“oracle 重跑”只指本隔离 checkout 的真实 CLI 错误复验及正常路径回归；实施 artifact 记录实际命令、退出码、输出、身份与文件/目录快照，不依赖缺失的历史 screen/command 文件，也不把冻结观察当当前通过证据。
- 实施 gate 环境前置：本 worktree 当前无 `.venv`。按根 `README.md` 1.1 节的源码安装方式，在 `/private/tmp/dayu-upload-o03` 执行 `python3.11 -m venv .venv`、`source .venv/bin/activate`、`python -m pip install -e ".[test,dev]" -c constraints/lock-macos-arm64-py311.txt`（当前平台 macOS arm64；其它平台选 README 对应锁文件）。只省略本 work unit 不需的 browser extra，不省略 editable 安装或锁约束。不得借用主工作区 editable `.venv`；若依赖安装失败，记录环境阻塞，不宣称测试/pyright 通过。
- 安装后先在临时 cwd、无 `PYTHONPATH` 条件下记录 `sys.prefix`、`sys.executable`、`dayu.__file__`，断言当前隔离 checkout 的 venv 与导入代码树一致；在同一已激活解释器运行 `python -m pytest tests/cli/test_workspace_root.py tests/cli/test_fins_commands.py tests/cli/test_session_command.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_upload_filings_from_command.py tests/cli/test_init_command.py -q --cov=dayu.cli.workspace_root --cov-report=term-missing --cov-fail-under=80` 和 `python -m pyright dayu/ tests/ utils/`，随验证结果记录解释器/代码树身份及新 owner 的 pytest-cov 覆盖率数字。若 focused 测试过大，可先按失败定位分批执行，但完成验收仍须覆盖所有受影响入口，且新 owner 单文件覆盖率至少 80%。另作一次性反例验证：借任一其它 checkout 的 editable 环境运行同一身份检查，确认它因导入代码树或解释器身份不符而失败；命令与结果写入实施 artifact，不作为常驻测试的外部环境依赖。本轮仅修改 plan，不把尚未运行的实施验证记为通过。

## README 决策、风险和 gate handoff

根 `README.md` 面向用户，`--base` 的用户可见错误与排障方式变化命中更新触发；实施时先复读其 `Agent更新约束`，在全局路径说明或排障处补一句现存目标须为目录、`upload_material` 等普通 Fins direct 入口可用指向目录的 symlink、文件目标 exit 2，避免与 `init` 的 symlink 禁止段落以及 `upload_filings_from` 的独立脚本发布规则混淆。`tests/README.md` 因测试修改需按既有测试分层职责检查；若新增 owner 测试改变其覆盖摘要，按当前事实加最小一句。`dayu/README.md` 仅在实际改变分层/装配边界时才更新；本方案不触发。`dayu/fins/README.md`、其它 README 不因本方案机械同步。

残余风险仅记录既有边界：stat 后到装配间的路径类型竞争、权限/父路径非目录/特殊节点的完整诊断分类、`upload_filings_from` 自身脚本发布的 symlink/containment 合同，以及 `init` 的 no-follow 生命周期。`upload_filings_from --infer` 的 FMP 网络调用发生在 base 校验前，属于现有行为；登记总控队列与 O03 closeout 风险，不在此更改时序或增加切片。本 plan 不为这些边界另开目标或切片。环境风险：本 worktree 锁定依赖安装可能失败；届时按上述前置步骤报告阻塞，不以主工作区环境替代。

Goal alignment：唯一 CLI owner、Fins 收敛和错误投影对应“现存非目录在装配前 exit 2”；dir symlink/缺失/相对等测试对应“正常路径语义不退化”；真实 CLI 文件与发布快照对应“原文件不变且无业务发布”；README 只解释新增用户可见行为。没有新增业务契约、仓储 schema、通用 symlink 禁令或未来 slice，因此没有 goal drift 或过度设计。

## Plan review finding 状态与交接

| 来源与裁决 | 本 plan 修复状态 |
| --- | --- |
| Kimi F1 / MiMo F4（accepted） | 已明确 `workspace_root.py` 独占 workspace trim/空值报文、stdlib-only，并加入轻量 owner/import 断言；待 re-review，不代表代码已实施。 |
| Kimi F2 / MiMo F1（accepted） | 已保留 Fins `_BASE_OPTION` 的两处脚本 argv 用途，并要求既有回归验证；待 re-review。 |
| Kimi F4（accepted） | 已加入 `upload_filings_from` 普通文件 base 的 parser/main 入口测试及早拒绝断言；待 re-review。 |
| MiMo F2（accepted） | 已写本 worktree Python 3.11 `.venv`、锁约束 editable 安装、解释器与真实 CLI 导入代码树身份断言；待 re-review。 |
| MiMo F3 / Q1（accepted） | 已明确 Fins 首尾空白行为收敛及悬空 symlink 的目标路径与测试；待 re-review。 |
| Kimi F3 / F5（rejected-with-reason） | 保留新模块与无路径、可操作的 usage 文案；修正解耦动机，不声称现有 Service import 即时消失。 |
| MiMo R1（accepted） | `test_fins_commands.py` 明确承接重复 `--base`、别名、默认 cwd 的真实 parser/main 断言；完成命令对新 owner 输出 pytest-cov 数字并设 80% 门槛。 |
| MiMo R2（accepted） | 常驻子进程身份期望由测试文件所在 checkout 与当前解释器动态推导；其它 editable checkout 反例仅一次性记录于实施 artifact。 |
| MiMo 上传输入 / oracle OQ（accepted） | 不存在的 `--files` 输入结合 forbidden factory 固定 base 早拒绝；当前隔离真实 CLI 重跑的命令、结果与快照进入实施 artifact，不依赖历史 screen。 |
| Kimi Session OQ / MiMo OQ3（rejected-with-reason） | Session/prompt/interactive 维持 owner + AST + 既有 exit 2 测试，不写镜像用例。 |
| `upload_filings_from --infer`（deferred-with-owner） | 网络前置行为列为总控队列与 O03 closeout 残余，不扩大本切片。 |

下一 gate：第二次 Kimi/MiMo 双路 `plan re-review`，只复核本次追加修订并由总控裁决；通过前不进入 implementation。本轮只修此 plan，不派发 review、不 commit/stage/push/PR/merge 或外部评论。
