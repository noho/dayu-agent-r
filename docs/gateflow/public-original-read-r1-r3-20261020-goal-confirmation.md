# Dayu 公开原始读取 R1–R3：目标确认

日期：2026-10-20。总控及唯一承接任务：`01a152f8-3948-7ec3-bbe2-f59755fba715`。

任务书：`/Users/leo/workspace/portfolio-manager-v2/orch/workpapers/g0-refactor-implementation-20261020/dayu-upstream-task.md`。
下文证据相对路径均相对此任务书目录。

## 当前 gate 与授权

- 当前 gate / next entry point：`plan`；用户已在本线程实读并确认全部目标、非目标、owner、成功信号及独立 draft PR 边界，授权依审核裁决持续推进到 draft PR 交付。
- goal confirmation 已通过；实现 writer 尚未启动，先派发计划。
- 任务书已授权必要工作分支及新 draft PR；merge 需另获授权。合并后才执行任务书规定的 sync to live 与实际安装环境复验。
- 依任务书，确认后通过 `sub-agents` runner 派发 `gpt-6-sol` 负责 plan/implement/fix，`mimo-flash` 与 `ds-flash` 并行独立 review；本任务自行总控裁决。不启动 timer。

## 去重、分支与 PR 边界

- 检查近期任务列表（工具上限 50，返回 `truncated=true`）、本地 `docs/` 相关记录、Git branches/worktrees 和 GitHub PR。该检查不宣称穷尽所有历史会话。
- 未发现另一项同根 R1–R3 writer；任务书也声明协调方未派发另一修复。`G0-dev`（`01a14f41-449d-7313-a895-04fcd5c26a4e`）正在整理调用方证据并保持实现停点。旧 Dayu 下载修复任务最后已完成清理，不是本项 owner。
- GitHub 仓库 `noho/dayu-agent-r` 当前 open PR 为空；PR 203/204/205 已合并，均为港股下载/期间修复，不属于原始读取接口修复。
- 进入时分支 `audit/us-meta-original-20261019`、HEAD `913179cbb9506d77f49dd07dc8384c6c01a4a9fb`，工作树干净。
- 远端 main 及本地 `github/main` 均为 `8bf8daec8a022fd705e6cfe32c4283605f1fe6ca`；与进入时 HEAD 文件树完全相同。已从该 main 创建 `fix/public-original-read-r1-r3-20261020`，避免继承审计分支历史作为 PR 提交范围。
- 预期一个独立 draft PR，只纳入 R1–R3 所需共同契约、仓储/processor/read runtime 与必要公开投影、测试和相关文档。具体 API/类型在获确认后的 plan 决定，不在本 gate 预定接口名。
- 如协调方发现未列出的同根 writer，先对齐 owner 并接入已有修复，不创建第二 writer。

## 动机与直接证据

动机成立：调用方需要基于实际原件核实结构、非数值原生事实及读取覆盖范围；现有便利章节文本和 filing 级 citation 无法承担这一原始读取契约。修复不涉及推断报告是否准入。

本轮只读核对已有回执、相关源码和定点原文，未运行新的 live 公开 API 调用，不把历史成功回执当成本轮执行。

1. **版本同源。** 重新计算 `live-module-fingerprints.json` 九个模块的 installed 与源码文件 SHA/size，18 项均与记录匹配。当前文件树与任务书版本一致，故其源码证据适用于当前基线。重新核对 `targeted-original-anchors.json` 七份原件的 SHA/size 与 51 个原文切片偏移，全部一致。
2. **R1。** 直接读取 `api-probe-02/atat-body-cold.json`：正文 632,400 字符、零换行；公开字段未包含原始节点/物理单元边界、QName/context/format/namespace 等。`dayu/fins/tools/result_types.py:129` 的 `SectionContentResult` 只承诺正文、章节/页信息与 citation 等。`dayu/fins/tools/read_runtime.py:2115` 将 XBRL 查询描述为数值 facts；`dayu/fins/processors/sec_xbrl_query.py:413` 在数值不可解析时跳过该行，不能据此承诺非数值原文查询。任务书已有 SEC 表格正向读取证据，本轮不将缺口扩大为“没有表格/选框”。
3. **R2。** 直接读取 MSFT、ASML、TSM 指定 cold JSON，正文均为 5,000 字符，未见截断/续读字段。`dayu/fins/processors/sec_form_section_common.py:1260` 与 `:1292` 定义并实施 5,000 字裁剪；`SectionContentResult` 未公开被删减范围。任务书所引 ASML 尾文与指定 `api-probe-05/asml-cover-cold.json` 实际尾文不同：后者以 `STRATEGIC REPORT\nCORPORA` 结束（SHA `412bd1ff367094bd351aa0b575657414ed2bea5dc9104fc68a7e3536b4f14390`）；以实际保存文件为准，不影响静默裁剪缺陷判断。不据此断言某条业务事实必然丢失。
4. **R3。** 直接核对 `api-probe-04/tsm-6k-cover-cold.json` 与 `tsm-main-vs-attachment.json`；本轮重算主件/附件 SHA、size，并核对主件 href 原文与附件开头，均匹配。返回确为附件开头，但 citation 未标识具体 asset。`dayu/fins/tools/read_runtime.py:3045` 仅从 snapshot 的 primary source 创建当前 processor；`:2585` 附近的 citation 构造只投影 filing 级 provenance/meta，不含实际资产身份。该事实证明选择/身份公开契约不足；不证明原件损坏、入库关系错误或下载选件根因。

## 目标、owner 与边界

| 必须实现的行为 | 唯一语义 owner / 边界 |
| --- | --- |
| 已下载文件可枚举、显式选择；身份、版本、内容校验和同版读取可核验 | `dayu.fins.storage` 仓储协议与 snapshot；当前 `SourceSnapshotProtocol` 已拥有 files、revision、primary_filename、get_source(filename)。原始主件与供阅读 primary 的区别必须据真实信息表达，不按名称或 filing 元数据猜测。 |
| 原始文字/标记、必要属性、逻辑组成、物理边界、局部顺序、可回读位置；指定非数值概念的 QName/namespace、原值、format、context/target/visibility 与上下文原文 | Fins 原始内容解析/processor 及其公共结果契约；由原始资产同版字节产生，禁止从便利正文或 citation 反推。缺失、无法判定与明确值应区分，不能伪造默认事实。 |
| 原始内容完整取得，或明确说明返回范围、截断及可继续方式 | 产生读取范围与分页结果的 Fins 契约 owner；便利 section 导航可保留，但公开路径必须能够说明覆盖范围并继续读取。 |
| Python 公开入口及必要 tool 投影使用同一结果真源、同版资产及缓存 | `FinsReadRuntime` 作为共同公开读取边界，复用 storage snapshot 与既有缓存/生命周期；adapter 只投影，不另做事实判断。 |
| 用途选择、主体关系、财年、真假冲突与报告准入 | portfolio-manager 调用方；Dayu 只交付原文及结构，不输出这些业务结论。 |

不在 UI、调用方或单一 CLI 入口补解析旁路；不从原始路径绕过仓储读取。稳定原文定位必须说明文件版本和坐标含义，不能仅用本地读取前后指纹一致替代 API 身份绑定。

## 成功信号与交付

- 经 `DefaultFinsRuntime.create(...).get_read_runtime()` 的公开方法，对任务书实际输入回读所需原始文字、标记/属性、结构关系和指定非数值事实；返回定位可回读并绑定实际资产版本。
- 能区别合法内容内部空 inline 与端点外物理阻隔，保留局部顺序与物理单元边界；不把 Markdown/连续字符串当作完整结构交付。
- MSFT/ASML/TSM 等可完整读取，或有明确截断、范围及公开续读方式；大文档可分段读取并复用缓存。
- TSM `fil_0001564590-22-029201` 的 `tsm-6k_20220812.htm` 和 `tsm-ex991_18.htm` 可显式选择、分别读取及核验身份，主件 href/附件关系原文可回读；filing citation 不替代资产身份。
- 保留 A/H PDF/Docling 及 SEC sections/tables 正向能力；覆盖任务书六批公开调用所列真实正向样例、同源同版冷暖缓存一致性、版本变化及失效/错误行为。
- 实现时补 owner 级测试，激活 `.venv` 运行受影响测试与 pyright；单文件覆盖率目标 >=80%。按实际修改检查相应 README 职责后更新。
- 交付实际 commit/draft PR、并行审核与总控裁决、命令/返回/错误/退出、版本证据及剩余限制；开发树通过不等于 live 可用。
- merge 另获授权后同步 live，核 `dayu-cli` 与实际 Python API 同一安装版本，并用 `/Users/leo/.local/share/uv/tools/dayu-agent/bin/python` 从公开入口真实复验，保存同步回执及可回读结果。

## 非目标、不过度设计与待确认项

- 不改 portfolio-manager 业务判断/workflow/公司产物，不作财报准入结论，不处理无关下载/TLS 问题；保留原件与历史失败回执。
- 不为本任务重建完整 XBRL 计算/业务解释系统，不把所有财务事实或全文一次性塞给调用方，不新建与 storage snapshot 平行的文件仓储、缓存或版本真源，不为旧内部实现添加兼容 shim。
- 当前无必须由调用方决定的接口细节问题；具体 API、数据结构及内部重构在确认后的 plan 中由 Dayu 总控裁决，并接受公共契约计划审核。
- 目标确认阻塞已解除：用户明确协调方未派发另一同根修复，本线唯一承接；按指定模型和双路审核进入 plan。
- 未覆盖项：本轮未新增 live 调用、测试、pyright 或修复验证，尚不承诺 R1–R3 已修复；这些属于确认后的实施验收。merge/live 同步为后续明确授权停点。

## 协调通知

通知目标：portfolio-manager 协调线程 `01a0d71c-f706-75b2-b1a5-dc130cd78f91`；调用方证据线程 `01a14f41-449d-7313-a895-04fcd5c26a4e`。
已通过 `send_message_to_thread` 实际发送目标确认文件与范围给以上两线程，两次工具调用均成功。随后用户在本线实读确认，明确继续 plan、实施验证、审核修复与 draft PR 交付；merge 仍须另获授权，合并后再同步 live。ASML 差异说明依确认保留。
