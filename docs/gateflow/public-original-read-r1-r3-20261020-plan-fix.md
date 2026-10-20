# Dayu 公开原始读取 R1–R3：plan fix 回执

日期：2026-10-20。分支：`fix/public-original-read-r1-r3-20261020`；base：`8bf8daec8a022fd705e6cfe32c4283605f1fe6ca`。

本轮仅修改 [plan](public-original-read-r1-r3-20261020-plan.md) 并新增本回执，依据 [control](public-original-read-r1-r3-20261020-control.md) 引用的[最终裁决](public-original-read-r1-r3-20261020-plan-adjudication.md)落实 accepted P1–P4。目标与授权沿用 [goal confirmation](public-original-read-r1-r3-20261020-goal-confirmation.md)，不改变最小设计、单一实施 slice 或 PR 边界。

current gate / next entry point：`plan` 内的受影响面 re-review，由总控安排双路审核并裁决；**尚未 plan-pass，未放行 implementation**。下表“已修复”仅指计划文本已实际修订及本轮自检，正式 finding 状态由总控复审后回写，本轮不修改 control 或裁决。

## 逐项修复

| 编号 | plan 改动位置 | 实际修订 | 状态 |
| --- | --- | --- | --- |
| P1：Host 截断 + Fins 分页 | §3.2 schema 说明；§5 provider 范围；§6.1 第 8 项；§6.2；§6.3 末项 | 明确实际新工具/process-backed provider、真实 Fs、Host 低截断预算联合测试的落点 `tests/host/test_fins_original_read_truncation_fetch_more.py`。使用合法 runtime 页 `truncated=true` 场景，先多次 `fetch_more` 取齐本页并精确比对，再按 `next_start` 续页，全文拼接等于原文；区分两个 `truncated`、读取范围与 cursor/scope 引用。工具 schema 自足说明顺序，不以模型服从为测试保证，不新增跨层状态/自建 cursor。若固定预算覆盖全部合法文本页，须断言该不变量、最大页完整输出及跨页拼接，仍用长结构/事实实际输出验证 Host 截断/续读。 | 已修复（计划文本；待复审确认） |
| P2：typed 角色唯一 owner | §2 owner 表；§2.1；§5 生产/测试范围；§6.1 第 1 项 | 纳入 `report_original_source.py:project_report_original` 的必要直接消费者迁移，统一消费 storage typed 角色/实际身份。保留显式 original 恰好一个且该资产为 PDF、exact publication、同版 meta/locator/非空/取消释放及安全拒绝；`read_report_pdf` 只作迁移必要调整。storage 边界验证角色/身份一致，测试随 owner 迁移，禁止 raw-meta 下游补判、fallback、primary 替代或另建 hash 真源；不改 CN/HK 准入、下载选文或重构下载。 | 已修复（计划文本；待复审确认） |
| P3：回归与 coverage 完整性 | §2.2 预算边界；§5 测试/docs decision；§6.2 | 回归及合并 coverage 实际 argv 补入 `tests/fins/test_cn_annual_report_source.py`、`tests/fins/test_sec_pipeline_download.py`、`tests/tools/test_combined_tools_acceptance.py`、`tests/host/test_toolruntime_truncation_fetch_more.py`、`tests/runtime/test_scene_prepare.py`；新联合测试同时进入新增测试组及 coverage。combined tools 精确断言更新真实新工具集，不保留兼容列表。预算使用原文 owner 具名常量/FinsToolLimits 默认，不向 `tool_discovery.json` 新增 limit 键；若实施事实必须改 JSON，向总控报告影响，并将 `test_config_loader.py` 纳入回归/coverage 实际 argv及 config README 复核，另列其单文件命令。 | 已修复（计划文本；待复审确认） |
| P4：原文 LLM 指引 | §3.1 namespace 路径；§3.2 schema/例子；§5 prompt 范围与 config README；§6.1 第 9 项；§6.3 namespace 验收 | 最小纳入 `dayu/config/prompts/base/tools.md` 的现有 `fins-read` 指引：四操作流程、文件/hash 引用意义、从公开结构的实际 namespace 声明/作用域发现 URI、双层续读先后，且 `has_financial_data` 只约束财务取数。补 provider schema 与现有 scene 实际装配断言，覆盖 false 场景不拦原文四操作；复核 config README 的默认配置/prompts 职责。沿用既有标签/manifest，不新增 scene 治理、slot、第五 API、QName 兼容输入或顶层 namespace 清单。 | 已修复（计划文本；待复审确认） |

## 裁决边界与实施 destination

- namespace 发现由既有原文结构/作用域与 span 提供；最小示例展示取值链，实施测试及真实验收必须实际走公开发现链并保存返回/绑定位置/查询参数，不猜年度 URI、不以硬编码 URI 代替发现。
- 不执行公开 storage 治理 revision 的建议（裁决 `rejected-with-reason`）；实际内容 sha/size、资产 namespace/filename 与 span 已满足文件版本绑定。同字节重发可复用坐标，metadata-only revision 仍按内部缓存失效处理。
- 保持原文四 API 与明确章节/目录投影的资产身份范围；search/table 等便利结果不升级为完整原文契约，不把可能读 sidecar 的财务结果错误绑定到单一 primary。
- 暖 identity 必须取 active borrow 所持 full snapshot；concepts 数量预算按实际参数成本决定必要具名上限并校验；固定 Host 文本预算不变量的适用性以有效配置/实现证据判断。上述局部判断进入 implementation / code review，不新增限流、调度、缓存或治理机制。
- 大件性能、malformed/target/continuation、隔离真实 workspace 复制及生命周期仍为原唯一实施 slice 的必需验收；失败不能降格为已接受限制。

## 本轮验证与版本

- 已读根 `AGENTS.md`、Gateflow skill、plan、goal、control、最终裁决和两份首轮报告；只补查修订必要的局部源码/测试及 config/tests README 职责。51 个原文锚、53 次历史调用、根因及原件版本事实引用 goal 与 [DS](../reviews/plan-review-20261020-112403.md) / [MiMo](../reviews/plan-review-20261020-114237.md) 的同版保存证据，未重扫全仓或重新核验历史原件。
- 激活 `.venv` 后以只读 Python 检查 plan 的 pytest argv、路径、合并集合、代码块及行尾空白，退出码 0：新增组 3 文件、回归组 15 文件、coverage 为二者并集 18 文件；条件性 config_loader 单文件另列。16 个既有测试路径均存在，3 个未来新测试文件仍未创建。
- 已逐段检查相对 `plan-submitted.md` 的文档差异；`git diff --name-only` 与 `git diff --cached --name-only` 均为空，退出码均为 0，无 tracked 代码/测试/配置变更或暂存。原 plan 为未跟踪 gate 文档，内容差异以保存快照为基准核对。
- goal、control、最终裁决、两份首轮报告、plan-submitted 六份只读文件的前后 SHA-256 全部一致。快照仍为 `e82cc97f92d6d712fbda151207badececb9521c8aa06f53b447920b135e2c845`；goal 仍为 `ed5737f8b6e7885fba4cb5e0da0f41bf17d7ac6f6ad2191b84282e0dd5763acb`。
- **修订后 plan SHA-256：`583596a6f754d6ff695f5b1ba4afd79c673cc485975a755bbf2229c2715d1bef`。**
- 本轮只有文档修改，未运行实施 pytest、coverage、pyright 或真实 API 验收；这些命令/断言是下一实施 slice 的要求，不是本回执中的通过证据。未派 agent、commit/push，未改 README/代码/测试/goal/control/审核产物/快照，未触及 live 或调用方。

## 未完成项与风险

尚未完成本版的双路受影响面复审与正式裁决；放行后的实际实现/验证/代码审核也未开始。以下分类区分已经修订的计划缺口与尚待执行的实施验收，不表示复审已经通过。

| 事项 | 分类 | owner / destination |
| --- | --- | --- |
| P1–P4 计划文本缺口已逐项修订，独立确认仍待完成 | fixed in current slice（仅计划文本修订） | 总控 → 按最终裁决安排 mimo-flash / ds-flash 聚焦复审并回写正式状态；确认前不实施，本回执不替代审核。 |
| R1–R3 及本次补充测试/角色迁移/prompt 指引的实际实现、测试/coverage/pyright、真实输入验收与完整代码审核 | covered by later approved slice | 指定实施 owner → plan 获放行后的唯一 implementation / validation slice 及 code review。当前没有实现通过结论。 |
| merge、live 安装同步与安装环境公开入口复验 | requiring new issue or explicit user decision | 总控 → 另获 merge 授权后按 plan §6.4；本轮不执行。 |

本轮没有待用户重新决定的目标/owner/scope 项，也没有遗留未落入计划的 accepted 编号。下一入口仍为总控双路受影响面复审，放行后才实施。
