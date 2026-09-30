# UM-O18-F01 plan review 总控裁决

- Gate：`plan review -> fix`；候选 `docs/gateflow/upload-material-o18-amended-plan-20260929.md`，HEAD `8d8d494fbbce0052372fb1b42097c9f7222cfa28`，产品未实施。
- MiMo `docs/reviews/plan-review-20260929-044006.md`：预检 ok、显式 `/private/tmp/dayu-upload-o18`、独立 output/stderr，exit0、Claude JSON `subtype=success/is_error=false`、68 turns、canary `mimo-dd9520dd` 匹配，stderr 仅模型名白名单提示，`agent_status=completed`。Kimi 有效第二路尚缺。

## findings 与裁决

| Finding | 总控裁决 | Sol 计划修订与完成信号 |
| --- | --- | --- |
| F1 高：显式 create-existing 同内容被现有 early skip 吞掉，plan 归属矛盾 | **accepted，但不在 O18 提前实现 O14**。O14/O15 用户已裁决 active create 无 overwrite 为 typed conflict。 | 将 O14/O15 **已实施并集成**列为 O18 implementation 硬前提；O18 的 skip 与 metadata-only 只对 O14/O15 判定允许的 upsert 动作触发。显式 create-existing 无 overwrite 必须在其共享准入前置 typed conflict，不到 O18 preparation；O18 不定义过渡 FileExistsError/skip 或临时动作表。实施前核对 O14/O15 真源及四象限回归；依赖未就绪即停 implementation。 |
| F2 中：metadata-only 终态协议与 `ok` 的 stored=requested 闭集冲突 | **accepted**。 | 新增明确业务终态 `metadata_updated`，映射为 terminal completed、`requested_file_count>=1` 且 `stored_file_count=0`；不用 `ok` 偷改原件计数合同，不用 `skipped` 冒充写入。material 成功/skip/delete 结果显式 `published_amended: bool` 从已发布 source meta 投影，失败/取消不得声称发布；请求摘要/started 用 `requested_amended: bool`。定义 pipeline JSON、`FinsUploadResultSummary`、direct/CLI/tool/LLM-facing 投影的字段名、类型、必填/空值与最小示例，列白名单及四类终态测试。filing 既有状态/身份不变，material 外的可选投影应受 source kind 精确约束。 |
| F3 中：preparation 不可见私有 revision，commit guard 无现成条件钩子 | **accepted，以 O12 同版 storage owner 为前置依赖**。 | O12 计划已定义同版 company/source business meta+opaque revision 的 storage snapshot 与 guard 内 precondition，O18 应消费该已接受并实施的 public contract，不再凭普通 `get_source_meta` 猜 revision，也不自建第二套 commit hook。O18 implementation 须在 O12 已集成后启动并核对实际 API；若 O12 最终接口不能表达 material metadata-only 的 expected active/fingerprint/amended 状态，回到 plan review 明确最小 storage 扩展。真实仓储双 batch 交错测试 A prepare→B commit→A commit 必须 typed stale 拒绝，拒绝后 source meta/manifest/资产不回退；单线程 stale 测不能替代。 |
| F4 低：错误调用点符号 | **accepted**。 | `service_runtime._upload_material_with_pipeline` 改为实际 `_run_material_upload`，重读相关行。 |
| F5 低：filing 专属 canonical skip 术语误导 | **accepted**。 | material 表改为 prepare 期 identical skip，取既有发布值且本请求无业务写入；其一般并发 stale 窗口归 O33，metadata-only 条件发布则由 O12 guard 保护。 |
| F6 低：LLM-facing 请求/发布标记未分 | **accepted**。 | tool schema 的 amended 描述写清请求布尔语义与同内容仅改标记不升内容版本；job 请求回显重命名 `requested_amended`，terminal 已发布事实用 `published_amended`，不得让两个 `amended` 裸键靠结构猜语义。把 `dayu/fins/tools/upload_tools.py` 及相关 schema/summary 测试纳入白名单，用户可见文案按 README 约束更新。 |

跨工作单依赖顺序更新为 **O12 同版 storage guard、O14/O15 动作/目标准入 → O18 amended**。O13 tombstone 时间语义在 O18 合流时回归；O33 一般同 identity 并发仍独立。MiMo 提及 filing identical skip 吞 amended 的独立风险，登记 `fins-filing-amended-identical-skip`，不在 material O18 越权实现。旧库缺字段按全新 schema 起库 fail closed；若需要运维迁移说明，按本 WU README 读者边界判断，不能加兼容读取。

Sol 下一轮仅修 plan，然后有效 Kimi/MiMo 双路 re-review；未通过前不实施、不提交。以上修复项与依赖已同步主总控队列。

## 计划修订派发 setup 记录

首次 `sub-agent-preflight` 使用 label `o18-plan-fix-sol-20260929-01` 返回 `setup_status=fail`：该 label 已在本机历史 run_dir 使用；本次子 Agent 未启动，`agent_status=not_started`、`tool_evidence=no`、`canary_status=not_run`、`retry_class=setup`。不能把此事计入 provider 尝试或计划结果。已改用全新 label 重新预检。

## Sol F1–F6 修订候选核验

label `o18-plan-fix-f1f6-sol-20260929-02` 的预检 ok，显式绝对 O18 workspace，进程 exit0、JSONL `turn.completed`、canary `gpt-6-sol-208d279d` 匹配，stderr 空；49 条 command_execution 中 **三条** exit1（无权限的 `/private/tmp` find、零匹配 rg、对未跟踪新计划的 `git diff --no-index`）。按 sub-agents 严格协议 `setup_status=ok, agent_status=failed, tool_evidence=yes, canary_status=match, warnings=[], retry_class=none`，候选计划只由总控独立读后采纳。Sol 最终消息称「两条非零」与 JSONL 不符；其 fix artifact 的逐批次表实际列出三条，此处明确纠正，避免压缩后丢失。

候选 `docs/gateflow/upload-material-o18-amended-plan-20260929.md` SHA-256 `162e28ca093379e55a7cd2f34b071169c54c4fd46caa6ad23cf5e70db5a03bc6`：O12 同版 guard、O14/O15 已实施集成列为硬前置；`metadata_updated` 的 requested/stored 计数与 completed 投影、`requested_amended`/`published_amended` 的请求/发布分界、真实双 batch stale 拒绝、实际 `_run_material_upload` 符号、prepare 期 material skip、tool schema/测试白名单均已入文本。此为待反证候选，非可执行 product handoff。下一 gate 为同 SHA Kimi/MiMo `$planreview`；不得实施 O18 或改 PR #197。

## MiMo 第二轮同版 plan re-review 与总控裁决

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
canary_status: match
warnings:
  - "Claude stderr: [claude-code:unrecognized_model] mimo-v2.6-pro[1m]；精确白名单非致命诊断"
retry_class: none
```

MiMo label `o18-plan-rereview2-mimo-20260929-01`，显式绝对 O18 workspace、独立 JSON/stderr/canary，进程 exit0、JSON `subtype=success/is_error=false/stop_reason=end_turn`、55 turns、canary `mimo-9a523e3e` 匹配。artifact `docs/reviews/plan-review-o18-rereview2-mimo-20260929.md` 已实读；锁计划 SHA `162e28ca...`，结论 fail。F1–F6 首轮修订方向成立，但新文本有四中、两低缺口。总控实读 O12 候选 guard 合同、现行 Docling service skip/版本与 read runtime/request summary 后登记：

1. **O18-PR2-F1 中 accepted**：metadata-only mutation 在 `prepare_upload` 构造时拿不到 O12 snapshot 的独立 opaque revision；O12 材料 batch 还必须注册 `expected_source_state` **和**公司阶段后的 `expected_company_meta`。选择最小消费方式：mutation 只携业务目标标记与身份；持有 admission snapshot 和公司阶段结果的 workflow 在材料 batch 注册两项 typed precondition。`prepare_upload` 不从 `previous_meta`、raw JSON、时间戳或私有字段反推 revision，不为 O18 复制 storage guard。实施前按 O12 实际 public 签名逐参数核对，若不支持则回 plan review。metadata-only 仍走已完成的独立合法公司阶段，材料事实失败不回滚公司事实。
2. **O18-PR2-F2 中 accepted，修正先前 F5 边界表述**：既然 O12 是硬前置，其 material skip 报告前 guard 内验证 expected source/company 也是本项必须消费的合同；A prepare 拟 skip、B toggle 提交、A 报告前应 typed conflict，不能返回陈旧 `skipped/published_amended`。O33 仍拥有 guard 之外的同身份重试/竞争策略和底层异常诊断，不拥有已被 O12 guard 关闭的 stale 报告窗口。计划增加真实仓储 skip 交错测试；原裁决「一般 skip stale 窗口归 O33」在此被具体 O12 同版合同取代，不得继续作为 O18 的例外。
3. **O18-PR2-F3 中 accepted，公开 overwrite 行为待用户裁决**：现表缺同内容×标记×overwrite 八格。当前 `_can_skip_upload` 明确 `overwrite=True` 禁 identical skip，`_resolve_document_version` 同指纹保持原版本；O14 已裁决 `create --overwrite` 是明确替换。建议 `--overwrite` 强制重新转换/发布、同指纹版本保持，非 overwrite 的同内容切标记走 `metadata_updated`。但 binding goal 的“同内容仅改标记保持资产”未限定 overwrite；已异步向用户确认该公开行为。答复前不修 F3 计划、不实施 O18；最终计划须列八格及至少两步 overwrite canary。
4. **O18-PR2-F4 中 accepted**：把三域键名写成逐表面正/反名单：持久 source meta/manifest 内部字段仍为 `amended`；material 请求/tool 参数仍收 `amended`，material job 请求摘要/started 用 `requested_amended`，filing 请求/身份字段保持旧合同；material upload 结果/摘要及 LLM-facing 读取输出统一 `published_amended`，从 source meta 真源读取，不能从请求推断。`read_runtime` 内部 typed meta 仍可用 `amended`，但 material 列表/详情给 LLM 的字段需明确选择并测试；不改 filing read 输出。新 schema 起库，不加旧键兼容 shim。
5. **O18-PR2-F5 低 accepted**：LLM-facing 工具结果/字段说明自足解释 `published_amended` 是已发布或最后发布事实；`skipped/deleted` 时它不表示本请求改过标记，`failed/cancelled` 为 null。测试核对文案及实际结构化输出，不只在内部计划表注说明。
6. **O18-PR2-F6 低 accepted**：真实 CLI canary 每步固定 `--action`；首发 create/auto、toggle/skip 用 auto 或 update、delete 明确 delete、恢复按 O14/O15 已实施合同选 auto/update，并记录 `--overwrite` 对照。不以参数未定的命令充验证。

MiMo 提及的 O13 重删 `skipped` 0 文件与本计划 `skipped requested>=1` 潜在交界已登记为合流检查，不在本 work unit 发明 O13 终态。O12/O14/O15 未集成仍为实施硬停。当前 gate `plan review -> fix`；先等用户对 F3 明确答复，再让 Sol 一次修 F1–F6，同版 Kimi/MiMo 复审；产品未实施。

## 用户对 O18-PR2-F3 的公开 overwrite 裁决（2026-09-29）

- 用户明确选择：**同字节仅切换 amended 标记时，无 `--overwrite` 只更新元数据并保留内容版本；带 `--overwrite` 强制重新转换并发布，即使字节未变，版本仍按现有指纹规则保持。** 此授权补齐计划八格的公开行为，不降低 O12/O14/O15 集成硬前提，也不把内容版本与 amended 标记混成一个事实。
- O18-PR2-F3 状态改为 **accepted／待 Sol 修计划**。计划须以同/异指纹 × amended 相同/不同 × overwrite false/true 列八格：非 overwrite 的同指纹同标记按已发布事实 skip、同指纹切标记 `metadata_updated` 且零文件转换/发布；overwrite true 即使同指纹也转换并发布、`ok`/真实 stored original 数，版本按既有指纹规则不因 amended 或 overwrite 虚增。新内容仍按内容版本规则，delete/恢复遵 O12/O14/O15 合同。真实 CLI canary 至少覆盖同字节标记切换的无 overwrite metadata-only 与带 overwrite 强制重发，核转换调用/原件与 Docling 文件、source meta/manifest、版本、结果计数及跨命令读回。
- 原文末句“先等用户答复”已由本节取代。下一 gate gpt-6-sol 一次修复 F1–F6 同版计划，再 Kimi/MiMo 独立复审；产品仍未实施。

## Sol PR2-F1～F6 修订候选核验

```yaml
setup_status: ok
agent_status: failed
tool_evidence: yes
canary_status: match
warnings: []
retry_class: none
```

- `o18-pr2-sol-20260929-01` 进程 exit0、JSONL 131 条可解析、`turn.completed`、45 条成功命令、canary `gpt-6-sol-c144c6a3` 匹配、stderr 空；一次猜错只读路径的 `rg` exit2 是 failed item，按固定协议不计有效 agent completion。总控实读 `docs/gateflow/upload-material-o18-plan-fix-pr2-20260929.md` 和计划新 SHA `61a6cb02eacaed4e3e48e63d9bacb6b22cf1c46cd635530338a0f4250e27b62d`：F1 guard 消费、F2 拟 skip stale guard、F3 八格及 overwrite 强制转换、F4 请求/发布三域、F5 LLM-facing skip/delete/失败、F6 CLI action 形态均写入计划。O12/O14/O15 尚未集成；此为候选，待 Kimi/MiMo 同版计划复审，产品未实施。
- 用户已授权 Kimi 额度不足时使用 `ds-flash` 备份；O18 PR2 最终 SHA `61a6cb02...` 的 MiMo plan review session `7152` 与 `ds-flash` 备份 plan review session `35084` 均预检 ok、显式绝对独立 workspace/output/stderr/canary，在途。结构化结果与总控内容裁决收齐前不计 plan gate；O12/O14/O15 集成前不实施 O18。

## ds-flash PR2 同版审查内容裁决（MiMo 仍在途）

- `o18-pr2-final-dsflash-backup-20260929-01` 进程 exit0、JSON `subtype=success/is_error=false/terminal_reason=completed`、canary `ds-flash-c22d202b` 匹配，stderr 仅白名单模型名提示。review `docs/reviews/plan-review-20260929-191328.md` 锁 SHA `61a6cb02eacaed4e3e48e63d9bacb6b22cf1c46cd635530338a0f4250e27b62d`，内容 fail，F1～F8。总控实读计划与当前 owner：material 当前 `identical_skip_safe=true`、overwrite 禁 skip 但同指纹保版、O12 plan 确有所有 material batch 双 precondition；以下逐项裁决先登记，不以 reviewer 状态直接改变产品 gate。
- **PR3-F1 中／partially accepted／未修复**：O14/O15 尚无已接受 plan/已集成代码是 O18 **实施硬依赖未满足**，计划已明确这一点，不能把“依赖尚未落地”本身判为当前计划设计错误；拒绝据此要求现在创造 O14/O15 plan。但 O18 表中已删除 tombstone 上的显式 `create` 行若暗示 O14/O15 已裁决具体行为，则无直接依据。计划须将此格写为待 O14/O15 shared action/target owner 决定，未决时不能实施/实测该格，不能预设 create-existing 或过渡行为。O14/O15 目标与状态机须单独 Gateflow 闭环后再集成。
- **PR3-F2 中／accepted／未修复**：O12 的“每个材料 batch”注册 source 与 post-company 双 precondition 是通用合同，O18 计划只细写 metadata-only/skip，遗漏 delete/常规内容发布的注册与交错验收。计划明确全部 material mutation batch 同样消费双 guard，并在测试包含 delete/content stale 真实仓储竞争；skip 仍走只读 guard，不把只读 skip 称 batch mutation。
- **PR3-F3 中／accepted／未修复**：计划要求 read 的 `published_amended` LLM-facing 自足解释，但 read tool schema owner `dayu/fins/tools/fins_tools.py` 未入白名单。将真实 owner 纳入条件白名单，明确材料列表字段当前 active 发布事实、filing 仍为原 amended，并测试工具说明与混合列表；禁止在每项 payload 重复塞说明。
- **PR3-F4 中低／accepted／未修复**：当前 read 只有 `list_documents` 两类列表项含 amended，内部 `_SourceDocumentMeta` 不是 LLM-facing 详情。把“read 列表与详情”收窄为真实 `documents` 与 `recommended_documents` 两个列表投影；未来若新增详情另立契约，不在 O18 发明。
- **PR3-F5 低／accepted 为残余归属／未修复**：processed meta/manifest 确会复制 preprocess 时的 amended 快照，metadata-only 改源后不会自动重处理，形成同名但不同时间的 durable 值。O18 计划应明确它是 preprocess 时点快照，不当作当前发布 amended 的 owner，不从它投影 read/tool 现值；将其时间语义与是否须失效重处理登记独立 `fins-material-processed-amended-projection` WU。若实际消费者把 processed 快照当当前发布事实，O18 实施停止并回该 owner 修复，不能下游重算。
- **PR3-F6 低／accepted／未修复**：material 当前恒 `identical_skip_safe=true`，计划“不安全 material 指纹”是不可达例外；删除或明确仅未来 fingerprint owner 改变时重审八格，不加产品死分支。
- **PR3-F7 低／accepted／未修复**：O13 accepted 重删终态仍 `deleted`，并非 0 文件 `skipped`；现有 `skipped requested>=1`。修正 §8 残余措辞，合流时回归首次/重复 delete 与 published amended 保留，不人为制造冲突。
- **PR3-F8 信息／accepted 为依赖清单修订／未修复**：O12 的实际 implementation 又依赖 O16/O05；O18 完成报告须列明这条传递集成版本与 owner 重核，不仅列 O12/O14/O15。MiMo 同旧 SHA review 仍在途，收齐后一次性派 Sol 修计划再双路复审。O18 产品未实施。

## MiMo 同版结果与 PR3-F1 事实更正

- `o18-pr2-final-mimo-20260929-01` 进程 exit0、JSON `subtype=success/is_error=false/terminal_reason=completed`、canary `mimo-f1892bb3` 匹配，stderr 仅白名单模型名提示。独立 clone review `docs/reviews/plan-review-20260929-191435.md` 锁同一 plan SHA `61a6cb02...`，内容 pass-with-risks；新增 processed durable amended 投影 F-1 与上文 PR3-F5 同根，不重复修复项。F-2 依赖状态/路径漂移接受为 **PR3-F9 低／未修复**：O12 plan gate 已通过但产品未实施；O14/O15 共用 state 计划确在 `/private/tmp/dayu-upload-state/docs/gateflow/upload-material-state-plan-20260929.md`，SHA `1fe2f5462a0d7a7bdb54edda3985965713a2e87890f5c8dba9b9c823e98778b6`，需从 O18 计划明引并标 gate 尚未双路闭合/未实施，而非笼统“尚待 review 的候选”。
- 总控独立读取上述 state 计划第 91～103 行：material tombstone + create 无 overwrite **明定保持现有 source upsert/storage 拒绝，且不作新 typed O14 接受标准**；其它 active create / missing update/delete / tombstone auto/upsert 也有逐格表。故 ds-flash 的“本机无 O14/O15 计划”是查找范围不足，**撤回 PR3-F1 对 tombstone create 缺合同的推断**；保留 O12/O14/O15 均未集成的硬依赖。PR3-F1 现改判 **not finding**，只由 PR3-F9 更新 O18 对真实 state plan 路径、SHA、状态及 tombstone create 的准确引用，不提前承诺 typed O14 结果。其它 PR3-F2～F8 仍按已登记证据处理。两路同旧 SHA 有 finding，plan gate 未通过。
## PR3 Sol 修订候选（2026-09-29）

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
canary_status: match
warnings: []
retry_class: none
```

- `o18-pr3-sol-20260929-01` 进程 exit0，119 条 JSONL 有 `turn.completed`、无 failed/error event，stderr 空，canary `gpt-6-sol-1f75a5cf` 匹配。只改计划并新增 `docs/gateflow/upload-material-o18-plan-fix-pr3-20260929.md`；新计划 SHA-256 `0d3f109b2f538d26cddd8ca6b4dd89da03e3ac27cd7e57915aefaa4b055892ce`。
- 总控实读修订：每个 material mutation batch 的 source/post-company 双 guard、read tool 真 owner 与实际两个 list 表面、processed amended 时点快照及独立 WU、删除不安全指纹死例外、O13 重删 `deleted`、O16/O05→O12 传递依赖及 O12/state 当前 gate 状态均入计划。原 PR3-F1 关于不存在 state plan 的推断继续撤回。内容为待审候选，不代表 plan gate 通过；O18 产品未实施，实施仍以 O16/O05/O12 与 O14/O15 产品集成为硬前提。

## PR3 同版双路复审派发

- MiMo `o18-pr3-mimo-20260929-01` 与 Kimi 额度备份 ds-flash `o18-pr3-dsflash-20260929-01` 均 `sub-agent-preflight setup_status=ok`，显式绝对 `/private/tmp/dayu-upload-o18`、独立 JSON/stderr/canary、不同 review artifact，sessions `21929`/`22566` 在途，目标计划 SHA `0d3f109b2f538d26cddd8ca6b4dd89da03e3ac27cd7e57915aefaa4b055892ce`。不得以派发判 plan gate pass。

## ds-flash PR3 同版复审新修复项（MiMo 在途）

- `o18-pr3-dsflash-20260929-01` 进程 exit0、JSON success/88 turns、canary `ds-flash-d8a71a12` 匹配，stderr 仅白名单提示；review `docs/reviews/plan-review-o18-pr3-dsflash-20260929.md` 锁同一计划 SHA，所有 shell 命令自身 exit0。内容 fail，以下项在总控直接核 `begin_batch` writer lock、O12 batch-scoped 注册、O18 §6 配方与 11 步 canary 后登记。MiMo 同 SHA 仍在途，暂不派 Sol。
- **PR4-F1 中／accepted／未修复**：§6 交错①把 A 的 expected-source/post-company 注册放在 B commit 前；注册需要 `begin_batch`，该 batch 持跨进程 ticker writer lock 直至 commit/rollback，B 不可能并行 commit，反例测试会挂起而非观察 typed stale。改为 A admission/合法公司 commit/metadata-only prepare → B 完成 commit → A begin_batch+注册双 guard+commit 拒绝；post-company 漂移变体也须在 A 开 batch 前发生。②只读 skip、③delete、④内容 prepare 不持 batch 的窗口保留。
- **PR4-F2 中／accepted／未修复**：11 步真实 CLI canary 每步 `published_amended` 都恰等于本次请求 `amended`，无法证伪从请求重算。另加合法独立 identity：先以 true 发布，再无文件且省略 `--amended` 的 delete（本次输入默认 false），断言终态 `deleted` 的 `published_amended=true`、requested/stored=0、tombstone 保留 true；同时 owner 测试注入失败/取消请求 true→发布 null。该反例仍以 storage/source meta 真源读回，不用 CLI 自算。
- **PR4-F3 中低／accepted／未修复**：delete 分支 `delete_source_document` 返回 None，现有 `commit_prepared_upload_batch` 仅回公司 outcome；计划仅说终态取 typed publication outcome，却没钉 material delete 最后发布标记由谁在何阶段产生。计划在 storage batch owner 明确 delete publication outcome 的精确 bool 来自 guard 通过后实际 tombstone/source meta，首删/重删同源返回；pipeline/summary 只投影该 outcome，绝不能用请求默认 false 或 prepare 时旧 meta。若 O12 公共合同不能表达，停在 owner 扩展裁决。
- **PR4-F4 低／accepted 为集成次序／未修复**：state 计划的 active update/auto 同内容 `skipped` 是 O18 前无 amended 事实的基线；O18 实施时先由 O14/O15 判 action/target 合法，再由 O18 在已准入材料上判同字节同标记 skip、异标记 metadata_updated、overwrite 强制转换发布。计划明说集成复核，不把 state 基线 skip 套到异标记。
- **PR4-F5 低／accepted 为测试 owner／未修复**：交错③④的 typed stale 断言来自 O12 storage guard，O18 只验证 material 路径正确注册并消费，不另造 O18 业务状态或重复实现 guard。计划在配方中标这个 owner 分工。
- PR4-F1～F5 只修计划/验收证据，不更改用户八格、`--overwrite` 强制转换、O12/state 产品实施硬依赖；当前 plan gate 未过、产品未实施。

## MiMo PR3 同版复审收口与新修复登记

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
canary_status: match
warnings:
  - "[claude-code:unrecognized_model] mimo-v2.6-pro[1m]"
retry_class: none
```

- `o18-pr3-mimo-20260929-01` 进程 exit0，JSON `subtype=success/is_error=false/terminal_reason=completed`、90 turns，canary `mimo-7fa02fba` 与 expected 逐字一致。review `docs/reviews/plan-review-o18-pr3-mimo-20260929.md` 锁同一 SHA `0d3f109b...`；stderr 仅白名单模型名提示。内容 `pass-with-risks` 不等于 plan gate pass；同版 ds-flash 已给出 PR4-F1～F5，且 MiMo 也发现下面的修复项。
- MiMo finding 1 与已登记 **PR4-F4** 同根，均指 O14/O15 旧「相同内容→skipped」矩阵须在 O18 合流时限定为「同内容且同 amended 标记」。接受其新增的同内容异标记+公司更新意图反例作为 PR4-F4 的验收配方，不另造编号。
- **PR4-F6 低／accepted／未修复**：同字节异标记的 metadata-only cell 声称只改 `amended`、`updated_at`、storage revision 和 manifest，但 staged meta 构造文字允许误把本次请求的 `filing_date`/`report_date` 等非 amended 字段写入。直接证据是计划 §3 cell 2、§4 `_PreparedMaterialMetaMutation` 与 `docling_upload_service.py:_build_upsert_meta` 现有内容发布路径读取请求 base meta；§6 尚无非 amended 字段保持断言。计划应钉住 admission 同版 previous business meta 为基底，仅替换 amended，并补日期等字段逐字段不变的 owner 测试。用户确认的 O18 目标是 amended 标记，本计划不自行扩大为任意日期元数据更新；如后续需要后者，另做 goal confirmation。
- MiMo 的旧指纹无效 open question 作为实施前风险提示：八格的「同指纹」以旧指纹有效为前提；旧指纹缺失时沿现有版本 owner 保版，不在 O18 增硬编码分支。若实施时需要宣称该输入受八格覆盖，先改计划并复审。
- 根据用户「完成当前 #198 WU 后停下」的最新指示，O18 现在**暂停在 plan review -> fix**，不派 Sol 修 PR4-F1～F6、不实施、不进入 PR197。交接 Agent 须先检查上游 O05/O16/O12/O14/O15 的真实实施/集成状态。
