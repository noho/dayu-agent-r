# R1–R3 计划审核裁决

被审版本：[plan](public-original-read-r1-r3-20261020-plan.md)，SHA-256 `e82cc97f92d6d712fbda151207badececb9521c8aa06f53b447920b135e2c845`。保存副本：`workspace/tmp/public-original-read-r1-r3-20261020/plan-submitted.md`。

独立报告：[DS](../reviews/plan-review-20261020-112403.md)、[MiMo](../reviews/plan-review-20261020-114237.md)，均为 `pass-with-risks`。总控实读两个报告及对应关键源码；退出事实以 control 为准。当前需完成有实际变更的 plan fix 与双路受影响面复审，不把建议非阻塞等同于 accepted 已修复。

## Findings 裁决

| 编号与来源 | 裁决 / 状态 | 直接证据、必要处理与 destination |
| --- | --- | --- |
| P1：DS Finding 1（Host 截断 + Fins 页续读） | `accepted` / `未修复` | 现有 Host 对指定字段执行独立截断，Fins 页的 next_start 不证明 Host 页已取齐。补实际新工具经 Host 低预算截断、fetch_more 取齐当前 Fins 页、再按 next_start 续读并精确拼接的联合断言；工具说明解释两层范围。无需新建 Host cursor、跨层状态机或追踪模型操作的许可机制。destination：plan 验证要求 → implementation/provider/Host 集成测试 → code review。报告举例中 truncated=false 却 next_start=X 不符合计划本身；改用 runtime 页仍有后续（truncated=true）的合法场景即可复现同一漏读风险，不据这一措辞否定测试缺口。 |
| P2：DS Finding 2（角色 owner 双路径） | `accepted` / `未修复` | 总控实读 `dayu/fins/pipelines/report_original_source.py:42`，其确从 raw source_meta.files 解释 original 角色。选择报告建议(a)：纳入该直接消费者的必要迁移，消费 storage 同一 typed 角色/身份，保留“恰好一个显式 original PDF”及 exact publication 的业务校验；不新增下游 fallback、不另生角色或 hash 真源，不借此重构下载/报告准入。不采用(b)保留双解释路线。destination：plan 范围及 owner 测试 → implementation → code review。 |
| P3：DS Finding 3 + MiMo Finding 1（受影响测试集） | `accepted` / `未修复` | `test_cn_annual_report_source.py`/`test_sec_pipeline_download.py` 消费 snapshot；`tests/tools/test_combined_tools_acceptance.py:312` 精确比较旧九工具列表。补回归/coverage 实际 argv，更新工具集断言至真实新契约，不留兼容工具列表。涉及新 prompt 装配时同时纳入 `tests/runtime/test_scene_prepare.py`；新联合续读测试及受影响 `tests/host/test_toolruntime_truncation_fetch_more.py` 亦需实际运行。新原文分页预算采用具名常量/FinsToolLimits 默认，不向 `dayu/config/tool_discovery.json` 增加新 limit 键；若实现事实要求改 JSON，则记录理由并纳入 `test_config_loader.py` 及 config README 核对，不机械漏测。destination：plan 命令 → implementation 实际回执 → code review。 |
| P4：总控（原始读取的 LLM 指引） | `accepted` / `未修复` | 总控实读 `dayu/config/prompts/base/tools.md:43–58`：现指引仅列旧便利路径，且无范围限定地写“调用前检查 has_financial_data”。新原文读取不能被财务数据标志拦住。最小修订纳入该 prompt：给原文四操作的任务流程、namespace 从实际原文结构取得、两层续读、文件/hash 标签含义，并把财务取数前提明确限定到财务取数。已有 interactive manifest 按 fins-read 标签选择，无需新 scene 或治理机制。`dayu/config/README.md` 按当前 prompts/配置职责复核更新；root README 仍按实际最终用户操作是否变化判断，不机械扩写。destination：plan → prompt/provider 装配测试 → code review。 |

上述修订都直接服务已确认公开契约、唯一 owner 与验收，不改变 goal/non-goals/PR 边界，不需要重复目标确认。

## Open questions 与剩余判断

- **namespace 发现（两路）**：已收敛。由公开 `read_original_structure` 的原始 namespace 声明/作用域取得 URI，工具最小示例与真实验收必须实际走此路径；不能从年份/meta猜 URI、夹具硬编码 URI，不新增 QName 兼容别名或第五 API。作为 P4/实际验收要求落实。
- **publication revision（DS）**：不新增公开 storage revision。已确认目标是原始文件字节版本绑定；SourceAssetIdentity 的 namespace、filename、实际 sha/size 与 span 自足；同字节重发允许坐标复用，metadata-only revision 仍由内部缓存失效机制处理。要求额外公开治理 revision 的方案 `rejected-with-reason`，无任务收益且增加 LLM 认知负担。
- **便利 search/table 的 asset 字段（DS）**：本轮维持计划边界：新原文 API 与明确的章节/目录投影绑定实际 source asset；其它便利视图不升级为完整原文契约，不对可能读 sidecar 的财务结果作单一 primary 来源承诺。定位原文使用新的公开原文路径；不为此无依据扩展全部便利 API。
- **暖 identity 取用（MiMo）**：已由计划约束为 active borrow 的 full snapshot；局部实现交 code review，非计划 blocker。不把 light descriptor 的可选声明摘要冒充实际身份。
- **concepts 数量预算（DS residual）**：实现按当前公开参数成本决定必要具名上限并验证参数；不为假设未来压力引入新调度/限流系统。destination：implementation 参数准入 / code review。
- **大件性能、malformed/跨 target/continuation、隔离真实 workspace 复制、生命周期**：沿已批准目标保留为唯一实施 slice 的必需验证，失败仍阻塞验收，不能仅记为已接受限制。
- **CSS/脚本、跨资产 inline document set、业务解释**：维持 plan/goal 中已说明的不承诺范围，Fins capability owner 有新需求再立项。
- **merge/live**：继续为用户另授 merge 后的入口，不提前同步安装或宣称 live-pass。

## 当前 gate

`plan` 内执行 `fix -> 受影响面 re-review`。P1–P4 均须由指定 gpt-6-sol 修订计划，并经 mimo-flash/ds-flash 双路聚焦变更及裁决事项复审；未修/部分修复/证据失效不得进入 implementation。保持已保存原计划及首轮报告，不重扫未变全仓、不重新讨论已确认目标。

## 第一轮受影响面复审裁决

被审 plan v2 SHA `583596a6f754d6ff695f5b1ba4afd79c673cc485975a755bbf2229c2715d1bef`，保存于 `workspace/tmp/public-original-read-r1-r3-20261020/plan-revised.md`；本裁决追加前版本保存于同目录 `plan-adjudication-v1.md`，使旧报告引用的 SHA 可取回。

- [MiMo 复审](../reviews/plan-review-20261020-115710.md)：pass，P1–P4 已修复。
- [DS 复审](../reviews/plan-review-20261020-115908.md)：fail，P1 部分修复，P2–P4 已修复。
- 总控不按票数裁决。已实读 `TruncationManager` 文档 `dayu/host/tool_runtime.py:1946`、`FetchMoreRequest:1091`、实际 `fetch_more:2085–2099` 及既有单次使用测试；DS 的新反例成立：cursor 成功补读后被消费，limit 只取前缀，不产生下一 cursor。v2 中“小 limit 和每次新返回的参数连续取回”无法按既有协议执行。
- **P1：维持 accepted / 部分修复**。指定 gpt-6-sol 仅修正这一处新增的错误契约及相应 schema/prompt 指令：用一次 `fetch_more` **省略 limit** 取得本页全部余量，拼接校验后再使用 Fins next_start/next_offset；说明 cursor 单次使用，不能以小 limit 期待新 cursor。limit 前缀与旧 cursor 失效只作为既有 Host 独立回归，不放在取齐页流程中。不改 Host 生产机制，不扩大 goal/slice。
- **P2/P3/P4：accepted / 已修复（计划层）**。双路一致且直接证据充分，后续复审复用当前证据，不重开这些事项；实际实现与测试仍在唯一 implementation slice 验收，不宣称代码已经修复。
- 本次需第二次窄 plan fix 与 P1 双路复审；只读 v2→v3 的实际差异和受影响句，不重扫未变计划或全仓。没有需用户再决定的范围问题。
