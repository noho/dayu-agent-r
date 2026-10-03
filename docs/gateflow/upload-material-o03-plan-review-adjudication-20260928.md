# UM-O03-F01 plan review 总控裁决

- Gate：`plan review -> fix`；work unit：`UM-O03-F01`；候选 plan：`docs/gateflow/upload-material-o03-workspace-root-plan-20260928.md`。
- 两路 artifact：`docs/reviews/plan-review-20260928-222653.md`（Kimi）、`docs/reviews/plan-review-20260928-223609.md`（MiMo）。总控读取两份完整 review、goal、plan 与 CLI 路径实现；HEAD `8d8d494f` 未变。两路均确认普通文件/目录 symlink/缺失目标的核心 `resolve(strict=False)+stat()` 机制、既有 exit 2 投影和 `python -m dayu.cli` 入口成立。

## 外部派发核验

| label | runtime/provider | setup_status | agent_status | tool_evidence | canary_status | warnings | retry_class |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `o03-planreview-kimi-20260928-01` | `claude/kimi` | ok | completed | yes | match | `[claude-code:unrecognized_model]` 精确白名单提示 | none |
| `o03-planreview-mimo-20260928-01` | `claude/mimo` | ok | completed | yes | match | `[claude-code:unrecognized_model]` 精确白名单提示 | none |

两路独立以 `--cwd /private/tmp/dayu-upload-o03`、不同 output/stderr/canary 运行；退出 0，JSON `subtype=success`、`is_error=false`、有结果，分别 36/45 turns。canary 与各自 expected 逐字匹配，stderr 只有白名单提示。未触碰候选 plan 或代码。

## Findings、裁决与修复登记

| 来源 | 裁决 | 直接依据与修复要求 | 状态 |
| --- | --- | --- | --- |
| Kimi F1 / MiMo F4：新模块 stdlib-only 与复用 `require_cli_text` 冲突、结构承诺无测试 | **accepted** | 新 `dayu/cli/workspace_root.py` 自行完成 workspace 参数专属 trim/空值报文，`agent_entrypoint.require_cli_text` 继续负责其它字段，二者业务语义不同；不得回引含 Service import 的旧模块。新 owner 测试固定空值行为，并以轻量 import/调用点检查防止 resolver 再漂移。 | 未修复 |
| Kimi F2 / MiMo F1：误删 `_BASE_OPTION` | **accepted** | `fins.py:406/473` 仍用于生成脚本 argv；只删除私有 resolver，保留 `_BASE_OPTION`；新增路径模块独立持有报错字段名常量，避免魔法字符串。`upload_filings_from` argv 回归必须通过。 | 未修复 |
| Kimi F3：新模块解耦动机弱，建议原地扩展旧模块 | **rejected-with-reason** | 现有消费者仍因其它职责 import `agent_entrypoint` 属实，但 workspace 路径拥有独立、层内纯 UI 规则。新小模块作为唯一规则 owner 可直接供 Fins/Session 引用，并避免未来路径消费者被迫引入 Service 装配；无新 public 跨层契约或多余 facade。保留新模块，修正 plan 对“现有消费者依赖立即减少”的过强理由。 | 不实施 |
| Kimi F4：`upload_filings_from` 第二调用点缺行为 pin | **accepted** | 该入口也从旧 resolver 改为新 owner；加普通文件 base 的真实 parser/main 测试，固定 exit 2、早于计划生成与脚本发布、原文件不变。 | 未修复 |
| Kimi F5：无路径文案可能降低可操作性 | **rejected-with-reason** | goal 的路径安全要求允许不回显原始/解析后绝对路径；`--base must point to a directory; choose a directory path` 已指明可执行改法，CLI 命令本身保留用户输入。其它路径错误的回显惯例不强制本新规则复制；不把错误异常原文写到 stderr。 | 不实施 |
| MiMo F2：隔离 worktree 无 `.venv`，借主 editable venv 的子进程可能验证错误代码树 | **accepted** | plan 必须给出在本 worktree 按根 README 建 Python 3.11 `.venv`/锁定依赖并 editable 安装的前置步骤；真实 CLI 子进程设置 cwd/PYTHONPATH 并校验 `dayu.__file__` 指向本 worktree，pytest/pyright 也记录同一身份。不能用主工作区可执行文件在临时 cwd 静默替代。 | 未修复 |
| MiMo F3：Fins 与 Session 的首尾空白语义原本不同 | **accepted** | 收敛到 `agent_entrypoint.resolve_workspace_root` 的 trim 规则；Fins 原本只判空不裁剪的行为是已发现差异，plan 应明说统一后对首尾空白输入的变化，并测试“首尾填充”与“路径内部空格/Unicode”两种输入。 | 未修复 |
| MiMo Q1：悬空 symlink 的解析目标 | **accepted** | 在 owner 测试固定 `resolve(strict=False)` 返回目标绝对路径、目标缺失则继续交装配；不加入 no-follow 规则。 | 未修复 |

权限/父路径非目录、stat 后竞争、`init` no-follow、`upload_filings_from` 独立脚本发布与 #198 并行汇入均按现有 owner/总控队列列为 residual risk；不借 O03 扩大目标。MiMo 关于特殊节点诊断分类的建议归后续独立 goal confirmation，当前只需其“现存非目录”按本规则拒绝的目标类型语义。

本轮 **plan review 未通过**，当前 gate `plan review -> fix`。Sol 只修 plan，Kimi/MiMo 双路 re-review 后总控裁决；通过前不实施代码。计划生成 Sol 的第一次派发虽 exit 0 且 canary 匹配，但 JSONL 内有一条失败的 `rg` 命令执行事件，按 sub-agents 协议记 `agent_status=failed`；候选 plan 经总控和两路 review 作为证据使用，不能把该派发状态冒充通过。

## 第一次双路 plan re-review 追加裁决

Kimi `docs/reviews/plan-review-20260928-225738.md` 与 MiMo `docs/reviews/plan-review-20260928-231043.md` 均结构化成功、canary 匹配，独立确认原 accepted findings 在计划层修复；Sol plan fix 的 JSONL 无失败事件、canary 匹配。MiMo 提出两项低严重度新缺口，总控如下裁决：

| 新 finding / open question | 裁决 | 修复或归属 |
| --- | --- | --- |
| MiMo R1：重复 `--base` 最后值、别名与默认 `./workspace` 无具体测试归属，覆盖率目标无命令 | **accepted** | 在允许的 `tests/cli/test_fins_commands.py` 增加真实 parser/main 用例，固定重复 base 最后值、`-b`/`--workspace` 别名与省略时默认相对 cwd；完成命令加入新 owner 的 pytest-cov 覆盖率数字。plan 明确这些落点；不需修改 `test_arg_parsing.py`。状态：未修复。 |
| MiMo R2：CLI 身份断言可能写死本隔离 worktree、合入后恒红 | **accepted** | 常驻测试的期望 repo 根由该测试模块所在 checkout 计算，不写死 `/private/tmp/dayu-upload-o03`；比较子进程导入 `dayu.__file__` 与该 checkout 的 `dayu/__init__.py`。解释器归属与当前运行的虚拟环境作动态比较；借其它 editable checkout 的反例只作一次性验证证据并写入实施 artifact，不作为依赖主工作区存在的常驻测试。状态：未修复。 |
| Kimi OQ2 / MiMo OQ3：Session、prompt、interactive 是否各补重复文件 base 测试 | **rejected-with-reason** | 新 owner 的行为测试、AST 调用点收敛断言和各入口既有 usage→exit 2 测试共同覆盖目标风险；不写三份镜像用例。实施中若某消费者的错误投影实际失败，再增定向用例。 |
| MiMo OQ1：上传输入文件未读的证据机制 | **accepted** | `upload_material --base <普通文件> --files <不存在输入>` 仍应先报 base 目录用法错误；结合 forbidden factory 断言，避免 atime 等脆弱证据。纳入现有 Fins CLI 用例，不新增切片。 |
| MiMo OQ2：冻结 oracle 证据文件缺失 | **accepted** | “重跑 oracle”仅指复现 UM-O03-F01 的当前隔离真实 CLI 行为及正常路径回归，记录命令/输出/快照于实施 artifact；不依赖未进入 worktree 的历史 screen/command 文件。 |
| `upload_filings_from --infer` 先于 base 校验可能访问 FMP | **deferred-with-owner** | 既有行为且不在 O03 goal；登记总控队列与 O03 closeout 风险，不把本轮扩大为网络副作用改造。 |

当前 gate 仍 `plan review -> fix`。Sol 修正以上计划级测试/验证 recipe 后，仅对新增点做 Kimi/MiMo 双路 re-review；通过前不实施代码。

## 第二次双路 plan re-review：总控终裁

Kimi `docs/reviews/plan-review-20260928-233054.md` 与 MiMo `docs/reviews/plan-review-20260928-233143.md` 已完整读取；两路分别 `pass-with-risks`、`pass`，均无新增 material finding。两路进程退出 0，JSON 的 `subtype=success`、`is_error=false`，`num_turns=35/27`，canary 逐字匹配；stderr 仅有精确白名单 `[claude-code:unrecognized_model]` warning。调用均显式 `--cwd /private/tmp/dayu-upload-o03`，使用各自独立 output/stderr。Sol 第二次 plan fix 的 JSONL 曾有两条失败命令事件，按协议仍记 `agent_status=failed`；落盘 plan 作为候选经过两路独立源码复核，总控采纳其内容，不倒改派发状态。

前轮 accepted 的 Kimi F1/F2/F4、MiMo F1–F4/Q1/R1/R2/OQ1/OQ2 均为**已修复（计划层）**；rejected 项维持不实施。两路核对了新 owner 的标准库依赖、`_BASE_OPTION` 两处脚本用途、Fins 与 Session 的裁剪差异、悬空 symlink、真实 CLI 与 editable checkout 身份、重复/别名/默认 base 的测试落点和 `--cov-fail-under=80` 命令。总控对 `agent_entrypoint`、Fins 两个调用点和 argparse 默认值作了直接抽查，未见与计划冲突的承重事实。

MiMo 提到的一次性“错误 checkout”反例，在实施时优先借主工作区已有 editable 环境；若该环境不可用，可用临时 `PYTHONPATH` 指向伪造 `dayu` 包运行相同身份检查，并把实际命令、期望失败与退出状态写入实施 artifact。该反例不进入常驻测试。`upload_filings_from --infer` 的网络前置行为继续归总控队列及本 work unit closeout；stat 后竞争、权限及特殊路径诊断仍为已分类残余，不扩展本目标。

**裁决：plan review gate pass。** 当前/下一 gate 为 `accepted plan commit`，随后进入唯一 S1 `implementation`。本裁决只确认计划可实施，不把尚未运行的测试或代码修复记为完成。
