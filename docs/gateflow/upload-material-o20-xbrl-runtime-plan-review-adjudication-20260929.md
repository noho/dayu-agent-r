# UM-O20-F02 受控 XBRL 计划审查裁决登记

- 2026-09-29 用户授权受控依赖/taxonomy 的有效 XBRL instance 支持；若最终确证 Docling/Arelle 上游缺陷，保留最小复现并向相应上游提 issue。内容抽取准确率不由 Dayu 修正。
- Sol 候选计划 `upload-material-o20-xbrl-runtime-plan-20260929.md`，SHA-256 `65c55801fce6432602a7d216f7c18d15c5df57e3228b1b85cc1bf1f830fffd2d`。进程 exit 0、JSONL turn.completed、canary `gpt-6-sol-a42bac3e` 匹配；两条 command exit 1 且一次编排 JS syntax error，严格 `setup_status=ok, agent_status=failed, tool_evidence=yes, canary_status=match, retry_class=none`。总控独立读取本计划，只作候选，不计 plan gate pass。
- 总控预审待双路反证：G0-A/B/C 是证据探针还是额外产品 gate；跨 macOS/Linux/Windows 完整依赖锁的实现可达性；taxonomy 的来源/许可/分发与真实有效正样本；强制本地引用/网络边界是否可在 Docling/Arelle 当前 API 与支持平台实现，是否存在过度设计；具体 typed 配置和接口在计划中推迟到 G0 之后是否导致当前计划不够可实施；两片切分是否能各自验收。计划末句“上游 issue 发布属后续授权 gate”须纠正：用户已作条件授权，仍需确认直接证据和目标上游，无需再次索取同一授权。
- 下一步：Kimi/MiMo 对同一 SHA 独立 `$planreview`；若探针结果改变方案，重新形成具体计划并双路复审。产品未改、未向上游发布 issue。
- 派发审计：Kimi/MiMo 均通过 `sub-agent-preflight`；O20-F02 首次 Kimi 只读 review 派发被 auto-review 拒绝，理由是未明确授权把该计划/代码/测试发给 Kimi。总控核对用户先前明确授权“kimi / mimo 负责 两路同时并行review”，并对指定 goal/计划/E01 作凭据字面扫描（无匹配），以相同命令、相同独立输出和补充具体授权说明重试获准；未改任务范围或绕道发送。MiMo 及重试 Kimi 正在运行，结果未返回。

## 同版双路 plan review 与直接根因复核（2026-09-29）

Kimi `docs/reviews/plan-review-20260929-o20-f02-kimi.md` 与 MiMo `docs/reviews/plan-review-20260929-o20-f02-mimo.md` 均对计划 SHA `65c55801fce6432602a7d216f7c18d15c5df57e3228b1b85cc1bf1f830fffd2d` 完成独立审查，进程 exit0、Claude JSON success、canary 分别 `kimi-66c7add8` / `mimo-6d51405a` 与预检文件逐字匹配，stderr 只有白名单模型提示；两路结论均 **fail**。总控没有把该计划当成可实施指令。

总控另从**一手事实**核对两项关键反证，避免仅按 reviewer 判断：PyPI `arelle-release 2.45.3` 的版本元数据和 E01 留存 wheel `METADATA` 均要求 `jaconv<1,>=0`，上传时间早于 E01 观察；E01 中“2.45.3 要 `jaconv>=1,<2`”是当时解析观察/命令归因，不能视为该 wheel 的依赖声明。原始 E01 不改写，新增本裁决明确纠错；下一探针要保留当时/当前完整 pip argv、索引、wheel metadata 与 resolver 原始输出，才能解释矛盾。Arelle 2.44.8 **及 2.45.3** `ModelDimensionValue.memberQname` 对 typed member 按设计返回 `None`；Docling 2.127.0 `xbrl_backend.py:344` 无 None 防护直接取 `.localName`。repo AAPL instance 有 4 个 typed context、8 个 fact 引用这些 context，E01 栈也停在该行。因此 typed dimension 是**独立且高度确定的 Docling 导出崩溃触发条件**；缺远程 taxonomy 导致 explicit member 同样为 None 的另一支尚未归因。上游 issue 应优先制备自包含合法最小 typed instance 验证，不能拿完整远程 taxonomy 当这支的必要前置，也不能对 AAPL 现版 Docling 的成功作已可达承诺。

接受并登记的修复项：

- **F02-PR-F1（高，Kimi）**：计划重开 Arelle 本体版本选择，先以一手 wheel METADATA+完整 resolver 解释 E01 `jaconv` 矛盾，再选受约束版本；不得默认锁 2.44.8 或把二手报错当声明真源。
- **F02-PR-F2（高，MiMo）**：typed dimension 最小第三方复现与对应上游 owner 归因先行；AAPL 不能作为 Docling 2.127.0 当前成功验收的唯一正样本。若用无 typed 维度真实有效 instance 验收，明确它证明的受控支持范围；AAPL 的上游缺陷单独保留，不由 Dayu 自制 parser 修。
- **F02-PR-F3（高，两路）**：taxonomy sidecar 的可信来源、绑定规则与显式 typed 配置传递需在实施计划中冻结；当前 `--files <instance>` 无 sidecar 通道，material 把附加文件逐项转换，不能靠父目录猜测或暗用环境变量。S2 真实 CLI 验收必须包含可复现的管理员配置前置。
- **F02-PR-F4（高/中，两路）**：现有 Docling/Arelle API 无可注入的引用拦截，`workOffline` 不是本地/网络强制边界。计划须先列可行的逐平台强制机制/验证命令与 blocked 处置，不把未知的跨平台 OS 沙箱工程藏在“开启 local fetch”之后；安全承诺和能力声明同源。
- **F02-PR-F5（中，两路）**：三平台真实 runner 来源未给，当前仓库无 CI；将完整依赖验证分为当前可执行证据与平台 blocked 出口，并明示不能以 macOS 冒充 Linux/Windows。
- **F02-PR-F6（中/低，两路）**：上游 issue 的用户条件授权**已经存在**；只需最小复现、证据/目标上游复核后按授权发送，不再增一道授权 gate。
- **F02-PR-F7（低，Kimi）**：G0-C 测试引用类别数量统一，并指定 taxonomy directory/zip/catalog 的最小受控形态、大小上限和重复尝试 copytree 成本/清理验证，避免目录复制放大。

总控裁决：G0 探针本身必要，不是目标漂移；但当前计划的 runtime S1/S2 不具备可实施接口与可达验收，**plan gate fail**。下一 entry 由 Sol 先作只读/隔离第三方探针并修 plan，优先证明版本真源、最小 typed 崩溃与安全机制可行性；在得到可实施配置/边界前不改产品、依赖、锁或公开文案。若机制确实不可得，再以直接证据回 goal 裁决公开 capability 的处理，不用临时降级绕过用户受控支持目标。

## 隔离探针及上游 issue 处置

Sol `o20-f02-probe-plan-fix-sol-20260929-01` 进程 exit0、JSONL `turn.completed`、canary 匹配，但六条命令 exit 非零，严格 `agent_status=failed`；其文档仅作候选，不能代替总控裁决。总控核对新增 `docs/gateflow/upload-material-o20-f02-probe-20260929.md` 的合成 XML/XSD、Arelle 2.45.3 离线 `--validate --validationExitCode` exit0、Docling 2.127.0 Path/Stream 同行 `memberQname.localName` 异常、Arelle wheel METADATA 与目录外 sentinel 加载证据。修订计划 SHA-256 `4d01db5528156e30ea177b8c76fb2e081f7d505bbe08c2d92417f138462f9deb` 撤下未证的产品成功承诺，下一步仍是同版 Kimi/MiMo plan review；三平台强制隔离与真实财报 CLI 成功仍 blocked，产品未实施。

用户对确证上游缺陷已有条件授权。总控另查 Docling `main` 当前 `docling/backend/xml/xbrl_backend.py:344` 仍无 typed 分支、GitHub 全状态 issue 搜索无此复现，使用纯合成样本向 `docling-project/docling` 提交 [issue #4437](https://github.com/docling-project/docling/issues/4437)。提交正文来自 `/private/tmp/docling-xbrl-typed-member-issue-20260929.md`，包含两份完整合成文件、Arelle 验证命令、Path/Stream 复现和预期/实际；未发送本项目代码或用户资料。此 issue 只跟踪 Docling typed member 崩溃，不代替 Dayu taxonomy 输入、文件/网络隔离和真实验收修复。

总控另补完整 Dayu README extras + macOS lock + Arelle 2.45.3 的 `pip --dry-run --ignore-installed`，原始双流与 report 见 `/private/tmp/dayu-o20-full-resolver-20260929/`，exit0、172 项、`jaconv 0.5.0`；精确命令/哈希已续写 probe。它解除本机**解析可行性**疑点，仍不是 fresh venv 安装/`pip check` 或其它平台证据。修订计划的 P0-A 安装 gate 不因此跳过。

## MiMo 对 P0 修订计划的第二轮 review 与总控裁决

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
canary_status: match
warnings:
  - "Claude stderr: [claude-code:unrecognized_model] mimo-v2.6-pro[1m]；按精确白名单为非致命诊断"
retry_class: none
```

MiMo label `o20-f02-plan-rereview-mimo-20260929-01`，显式 `/private/tmp/dayu-upload-o20-f02`，进程 exit0、JSON `subtype=success`/`is_error=false`/`stop_reason=end_turn`、canary `mimo-52418417` 匹配。review artifact `docs/reviews/plan-review-20260929-120634.md` 已实读，锁定计划 SHA `4d01db55...2f9deb`，结论 fail。总控接受其版本真源、typed/explicit 分支、平台 blocked 的已证/未证划分；7 个 finding 逐项如下登记，均未修复：

1. **F02-PR2-F1 高，接受**。Docling 原生 taxonomy 是同一目录的相对散文件加可选顶层 catalog zip；本仓 AAPL 同构样本相对 schemaRef/linkbaseRef 与绝对 import 混合。计划的互斥 `relative_tree|zip_catalog` 无法表示该引用图。修订为最小组合形态并以合成混合引用图做 Arelle/Docling 对照；不可把接口缺陷误报为真实样本不合格。
2. **F02-PR2-F2 中，接受并限定完成态**。P0-A 按平台分别记录真实安装/`pip check` pass 或 runner blocked；macOS 成功可形成候选版本选择，但生产 pin 和全平台支持声明不得在 Linux/Windows 验证缺失时通过。runner 不可得时回 goal/总控裁决支持平台范围，不设任意「超期」魔法期限，也不在 plan 文案里自行缩范围。
3. **F02-PR2-F3 中，接受**。`/private/tmp` 原始双流、resolver report、wheel、合成样本易失；P0 明确由本 work unit 证据 owner 把可公开的最小原件复制到 repo 内被 Git 忽略但非系统临时的 `workspace/evidence/upload-material-o20-f02/`（或同等受控持久根），文档登记相对清单与 SHA。受许可限制的真实 taxonomy 另由管理员受控归档保存原件，文档只存来源/许可/布局/哈希，不上传第三方包到 PR。证据迁移须保留旧路径和来源映射，不覆盖 E01 原始记录。
4. **F02-PR2-F4 低，接受**。P0-B 先跑无外部资源的裸目录与 zip+catalog 混合合成探针，再做 SEC/FASB 许可/真实实例闭包；许可阻断不得吞掉内部机制可验证结论。
5. **F02-PR2-F5 低，接受**。安全承诺统一为转换子进程**零出站网络请求**，包含非 taxonomy URL；与 OS 规则和 C4 trace 同强度。开放远端获取必须另回 goal。
6. **F02-PR2-F6 低，接受并界定有限验证**。矩阵加入非 schemaRef 文件/网络读取向量（DOCTYPE/ENTITY、XInclude、样式/链接导入、非常规 scheme、可加载扩展），每种最小合成触发与 OS trace。有限矩阵不能逻辑证明所有未知向量，最终保证来自强制 OS 文件/网络边界；计划需把测试范围与安全不变量区分清楚。
7. **F02-PR2-F7 低，接受**。Documents runtime 输入边界必须拒绝非绝对/非规范、位于用户可写 workspace 内的 taxonomy root；管理员 provenance 清单由受控归档 owner 保留，运行时校验其 root 与布局，不靠 CLI 文案或操作者自觉。后续还要验证检查到 copytree 之间的 TOCTOU，不能把路径预检当 OS 沙箱。

OQ3 E01 冻结文档本次读到 SHA-256 `f75a0c9b20e8ad152d5d0f24964b11f4baf87ffb8f11a313671fa69b6fe0401c`，只在此记 digest，不改原文。上游 [issue #4437](https://github.com/docling-project/docling/issues/4437) 已发，无需重开；后续补证如有只更新该 issue 且先核相关授权与内容。当前 gate 仍为 `plan review -> fix`；Sol 只修 P0 文本，之后同 SHA Kimi/MiMo 复审。受控 XBRL 产品能力仍 blocked，不提交产品代码或宣称支持。

## Sol PR2 修订候选核验

label `o20-f02-plan-fix-pr2-sol-20260929-01` 预检 ok、显式绝对 O20-F02 workspace，进程 exit0、JSONL `turn.completed`、canary `gpt-6-sol-b96d9ca3` 匹配，但 34 条命令中四条 exit1、stderr 有一次 `apply_patch verification failed`，严格 `setup_status=ok, agent_status=failed, tool_evidence=yes, canary_status=match, retry_class=none`。失败命令/恢复与未运行的探针见 `docs/gateflow/upload-material-o20-f02-plan-fix-pr2-20260929.md`；候选只由总控独立读后采纳，不把 agent 最终绿字当 gate pass。

候选计划 SHA-256 `b2723237bb528bfb873add47370b8344b7daa814a1e852857b6ccc9df1f043b4` 已实读：`taxonomy_root + catalog_zip_name` 可表达同根散文件/zip 混合引用；P0-A 逐平台 pass/blocked、生产 pin 全平台 gate；P0 原始证据必须先在忽略的 `workspace/evidence/upload-material-o20-f02/` 建立跨清理/重启留存及备份并回读，真实受限包由管理员受控归档；P0-B 自足机制探针先行；零出站、C8 非 schemaRef 向量和 root/workspace 外拒绝校验均已列入。当前 worktree 位于 `/private/tmp`，`workspace/evidence/` 尚不存在，故此只是归档规格，不能算证据已持久或 P0 执行完成。下一 gate Kimi/MiMo 同 SHA plan review；产品能力仍 blocked。

## MiMo 对 P0 计划第三轮复审与总控裁决

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
canary_status: match
warnings:
  - "Claude stderr: [claude-code:unrecognized_model] mimo-v2.6-pro[1m]；精确白名单非致命诊断"
retry_class: none
```

MiMo label `o20-f02-plan-rereview3-mimo-20260929-01`，显式绝对 O20-F02 workspace、独立 JSON/stderr/canary，进程 exit0、JSON `subtype=success/is_error=false/stop_reason=end_turn`、33 turns、canary `mimo-6b5c4df5` 匹配。artifact `docs/reviews/plan-review-o20-f02-rereview3-mimo-20260929.md` 已实读；计划 SHA `b2723237...`、冻结 E01 SHA `f75a0c9b...` 均匹配，结论 pass-with-risks。总控实读计划 §3/§5、当前 Documents runtime 与 Fins 调用路径后确认 PR2-F1～F6 的 P0 候选收口成立；PR2-F7 留一个未来实施接口 owner 问题，并接受三处 P0 文案/证据缺口：

1. **O20-PR3-F1 中 accepted，实施计划硬停点**：`XbrlTaxonomyInput(root, zip_name)` 与当前 Documents converter 都没有 workspace/管理员受信根或 provenance 清单输入，故 §3 不能声称 Documents runtime 单独可执行“root 在用户 workspace 外”且比对清单。P0 是 evidence/probe slice，不冻结产品接口；当前 P0 可继续，但 P0 后的 S1 implementation plan 必须明确唯一校验 owner、显式所需输入及强制点，至少由 Fins 持有的 workspace 边界/管理员受信根与 Documents runtime 进程内完整性复验协作，不得用默认值/CLI 文案替代。若 P0 后仍无可实施接口，产品 gate blocked，不宣称 XBRL 支持。
2. **O20-PR3-F2 低 accepted**：P0-B 合成引用图补绝对 `schemaRef` 与绝对 `linkbaseRef` 经 catalog 映射的单独 Arelle→Docling 对照；§3 解析分工覆盖这些 URL，而非只写“绝对 import”。AAPL 当前相对入口只证明其形态，不能用该 fixture 代替其它形态机制证据。
3. **O20-PR3-F3 低 accepted**：当前 P0 worktree 位于 `/private/tmp`，同目录复制不算抗清理备份。P0 开始前把可公开原件复制并校验到持久主仓忽略目录 `workspace/evidence/upload-material-o20-f02/`，并以与其不同清理域的主仓忽略 `output/evidence-backup/upload-material-o20-f02/` 作第二份；两者均不进 PR，当前 `.gitignore` 已覆盖 `workspace/` 与 `output/`。按清单从第二份独立回读逐文件 SHA/大小，并在遮蔽临时源后核对；真实重启后的抽查是后续补证，不能凭路径名谎称已经实测重启。若主仓持久路径不可用则 P0 记 blocked，不以 `/private/tmp` 目录顶替。受许可 taxonomy 原件另归管理员受控仓，不放这两个公开证据目录。
4. **O20-PR3-F4 低 accepted**：P0-B 自包含样本只承诺配置级离线，所有“零出站已证明”口径留给 P0-C 的生效 OS 规则与 trace；不得从 `workOffline` 或未观察的 P0-B 推断零出站。

MiMo 的 C8 未点名向量可在 P0-C 有限矩阵实际执行时按触发能力补记，不把有限样本当全覆盖。上述 F2～F4 在同次 P0 计划修订，F1 写成后续实施计划硬停点；不改产品/依赖或 E01。修订后同 SHA Kimi/MiMo 复审。上游 #4437 只对应 typed 崩溃，Dayu XBRL 能力仍 blocked。

## Sol PR3 P0 计划修订候选核验

label `o20-f02-plan-fix-pr3-sol-20260929-01`：预检 ok、绝对 O20-F02 workspace、独立 JSONL/stderr/last-message/canary；进程 exit0、JSONL `turn.completed`、24 完成命令中一条复合 `ls` 因主仓 `output/` 尚不存在 exit1，canary `gpt-6-sol-088f915d` 匹配、stderr 空。严格 `setup_status=ok, agent_status=failed, tool_evidence=yes, canary_status=match, warnings=[], retry_class=none`，修复报告 `docs/gateflow/upload-material-o20-f02-plan-fix-pr3-20260929.md` 只作候选。总控实读计划 SHA-256 `69307018eea754b523cc81fd1055c0e7e427008276a3977edca0267af61bb7c0` 且冻结 E01 SHA `f75a0c9b...` 不变：typed 形态明标未闭合草案、S1 owner/输入硬停点；P0-B 加绝对 schemaRef/linkbaseRef catalog 对照；公开证据主仓 `workspace/evidence/` 和另一忽略 `output/evidence-backup/` 两份及遮蔽临时源后独立回读；P0-B 配置级离线与 P0-C OS 零出站分清。主仓 `.gitignore` 两规则已核，`output/` 当前不存在属 P0 未执行事实，不能称归档已建立。新版本待同版 Kimi/MiMo plan review；P0/产品均未实施。
- 2026-09-29 MiMo PR3 同版修复性 `$planreview`（label `o20-f02-plan-rereview4-mimo-20260929-01`）对计划 SHA `69307018eea754b523cc81fd1055c0e7e427008276a3977edca0267af61bb7c0` 与冻结 E01 SHA `f75a0c9b20e8ad152d5d0f24964b11f4baf87ffb8f11a313671fa69b6fe0401c` 均锁定相符；进程 exit0、Claude JSON `subtype=success/is_error=false/terminal_reason=completed`、38 turns、canary `mimo-7ffd4221` 匹配，stderr 仅精确白名单模型提示。但其 `docs/reviews/plan-review-20260929-130919.md` 明列一次 `ls` 主仓尚不存在 `output/` exit1、一次 zsh `====` 解析 exit1；按严格协议 `setup_status=ok/agent_status=failed/tool_evidence=yes/canary_status=match/retry_class=none`，此路内容不能计有效 plan gate pass。Kimi 同版第二路亦缺。
- **PR4-F1 低，accepted／未修复**：P0-B 文字中“每个向量先 Arelle 合法性验证”只紧跟两条绝对入口向量，未明确覆盖 AAPL 同构混合引用图；②绝对 `linkbaseRef` 未限定在 XSD 的 `xs:annotation/xs:appinfo` 合法宿主。总控实读计划 §5 和仓库 AAPL XSD 的 `linkbaseRef` 所在位置后接受，要求三个自足合成输入各自先留 Arelle `--validate --validationExitCode` 成功原始证据，再按时间顺序做 Docling Path/Stream；②在合法 XSD appinfo 中构造，不把无效 instance 位置误判为 Docling/catalog 不可达。只修 P0 规格，不改产品。
- **PR4-R1 残余，deferred-with-owner**：`workspace/evidence/` 与 `output/evidence-backup/` 虽独立于 `/private/tmp` 且分属不同清理目录，但同处主仓/磁盘，共同受整仓删除、`git clean -fdx` 或磁盘故障影响。P0 manifest 需明确这两份仅防定向临时清理，不宣称独立灾备；许可受限真实原件仍进管理员受控归档。若 goal 需要抗整仓失效，应由管理员指定仓外持久第二落点再重审，不临时把敏感 taxonomy 放第三处。
- 其余 PR3-F1～F4 内容反证未推翻：typed 草案不冻结、绝对 catalog 向量仅称可执行未称可用、配置离线与 OS 零出站分界、P0-A 三平台 blocked 出口和真实正样本/#4437 未完成口径均保持。下一 gate 为 gpt-6-sol 仅修 PR4-F1/R1 P0 文本，再用新 label Kimi/MiMo 对同一最终 SHA 复审；P0 尚未执行，XBRL 产品支持仍 blocked。

## Sol PR4 P0 修订候选核验

```yaml
setup_status: ok
agent_status: failed
tool_evidence: yes
canary_status: match
warnings: []
retry_class: none
```

- gpt-6-sol `o20-f02-plan-fix-pr4-sol-20260929-01` 显式绝对 O20 workspace、独立 JSONL/stderr/last-message/canary，进程 exit0、JSONL `turn.completed`、18 完成 command_execution 全 exit0、stderr 空、canary `gpt-6-sol-2be2f6c6` 匹配；但最终消息附有非白名单 `codex_core::tools::router: error=Goal tools require a persistent thread.`，不能把“无失败 shell”替代全工具成功，严格 `agent_status=failed`。该错误不涉及产品或 P0 探针，候选文本需独立 review。
- 总控实读计划新 SHA `7a496dcc97df5c922e39e0390055ea39ebbd15e45ff1951216a9e5e707d17252`，冻结 E01 SHA 仍 `f75a0c9b...`：§5 明确三个合成输入各自 Arelle 合法性原始证据先于 Docling Path/Stream、绝对 linkbaseRef 在合法 XSD appinfo；P0 归档清单说明两份同仓同盘共同失效及不宣称灾备/重启。PR4-F1 内容候选已修，R1 已分类，P0/产品仍未实施。新 fix artifact `docs/gateflow/upload-material-o20-f02-plan-fix-pr4-20260929.md`；下一 gate 是对本 SHA 的有效 Kimi/MiMo 双路 `$planreview`。

## MiMo PR4 同版复审与新增规格缺口（2026-09-29）

- MiMo `o20-f02-plan-rereview5-mimo-20260929-01` 锁计划 SHA `7a496dcc97df5c922e39e0390055ea39ebbd15e45ff1951216a9e5e707d17252`、E01 SHA `f75a0c9b...`，进程 exit0、JSON `subtype=success/is_error=false/terminal_reason=completed`、39 turns、canary `mimo-04b54854` 匹配，stderr 仅白名单模型提示。其 `docs/reviews/plan-review-20260929-133246.md` 明列复合 shell 内 zsh glob 失败、`ls .github` 不存在及无匹配 grep；虽整体工具调用 exit0，严格逐命令口径 `setup_status=ok/agent_status=failed/tool_evidence=yes/canary_status=match/retry_class=none`。内容可独立裁决，不能算有效 MiMo plan gate；Kimi 同版路仍缺。
- **PR5-F1 低，accepted／未修复**：绝对 `linkbaseRef` 向量只写 XSD appinfo 宿主，未定义 Docling 入口 instance 和到该 XSD 的 schemaRef 形态；仅 XSD 入口可过 Arelle 验证，却被 Docling `Type.INSTANCE` 硬拒，易误判 catalog 不可达。总控核实计划 §5 与 `xbrl_backend.py` 的 instance 类型检查，裁决该向量用自包含 instance、相对 schemaRef 到同根散文件 XSD、XSD appinfo 的绝对 linkbaseRef 经 catalog 到 zip 内 linkbase；先 Arelle、后 Docling，各记录真实入口及映射读取。这样单独检验绝对 linkbaseRef，不与绝对 schemaRef 向量混因。
- **PR5-F2 低，accepted／未修复**：以无 typed 真实财报验收时，若最终公开 `XML_XBRL` 不限定，仍会对已证 typed 崩溃样本误称通用支持。按用户“受控支持”目标与早期 PR-F2 裁决，P0 正样本记录须写明其证明的引用形状、无 typed 范围；S1 capability/CLI/tool 文案不得超出已验证范围，typed 支持在上游修复并重测前不得宣称。若现有共享 capability 不能诚实表达范围，S1 接口/文案计划必须停并重新双路复审，不用模糊“支持 XBRL”覆盖不支持输入。这不是撤销用户受控支持目标，只约束事实声明。
- PR4-F1/R1 内容修订获反证认可，其余安全/三平台/证据 blocked 口径未见新反例。Sol 下一步仅修 PR5-F1/F2 P0 计划及 fix artifact，E01/产品不改；之后再对新 SHA Kimi/MiMo 独立复审。P0 未开始、XBRL 产品仍 blocked。

## Sol PR5 P0 修订候选核验

```yaml
setup_status: ok
agent_status: failed
tool_evidence: yes
canary_status: match
warnings: []
retry_class: none
```

- gpt-6-sol `o20-f02-plan-fix-pr5-sol-20260929-01` 显式绝对 O20 workspace、独立 JSONL/stderr/last-message/canary，进程 exit0、JSONL `turn.completed`、17 条完成 shell 命令全 exit0、stderr 空、canary `gpt-6-sol-abdaeba1` 匹配；但最终消息及 fix artifact 如实披露首次 `functions.exec` JavaScript 包装语法错误，以及 `git diff --no-index` 检出差异的 exit1。按全工具/逐命令协议严格 `agent_status=failed`；计划文本只作总控审查候选，不以进程 exit0 充当实施可信度。
- 总控实读 `docs/gateflow/upload-material-o20-f02-plan-fix-pr5-20260929.md` 与计划 §5：新计划 SHA-256 `904ec0f2d1a97f8fce0a77d2ae886bb347470b6ea435fe8e4163678bb27adae7`，E01 仍为 `f75a0c9b...`。②以自包含 instance 为 Arelle/Docling 共同入口、相对 schemaRef 到同根 XSD、XSD appinfo 绝对 linkbaseRef 经 catalog zip，逐个保留 Arelle 在前/Docling 在后及入口/映射证据；真实无 typed 正样本的 context/维度与引用形状、版本、taxonomy、配置范围被限定，S1 capability/CLI/tool 不得过度声明，无法准确表达则硬停重新双路审查。PR5-F1/F2 **计划内容候选已修**，P0 未执行、真实无 typed 正样本未取得、产品能力未实现。
- 下一 gate：对同一 `904ec0f2...` SHA 的有效 Kimi/MiMo 独立 `$planreview`；此前旧版或失败的 reviewer 不计 gate pass，E01/产品不改。

## MiMo PR6 同版复审与新增证据机制缺口

```yaml
setup_status: ok
agent_status: failed
tool_evidence: yes
canary_status: match
warnings:
  - "Claude stderr: [claude-code:unrecognized_model] mimo-v2.6-pro[1m]；精确白名单非致命诊断"
retry_class: none
```

- MiMo `o20-f02-plan-rereview6-mimo-20260929-01` 显式绝对 O20 workspace、独立 JSON/stderr/canary，进程 exit0、JSON `subtype=success/is_error=false/stop_reason=end_turn`、30 turns、canary `mimo-5d89116e` 匹配。`docs/reviews/plan-review-20260929-135825.md` 锁 P0 plan SHA `904ec0f2d1a97f8fce0a77d2ae886bb347470b6ea435fe8e4163678bb27adae7`、E01 `f75a0c9b...`；内容 pass-with-risks，PR5-F1/F2 输入形态/声明范围已被一手 Docling/Arelle 源码反证复核。artifact 如实披露两段 Python 检查脚本因变量名笔误各 `NameError` exit1，严格逐命令协议 `agent_status=failed`，不计有效 MiMo plan gate。
- **PR6-F1 低，accepted／未修复**：P0-B 要求 Docling Path/Stream 记录该次“实际读取/映射目标”，但 Docling 2.127.0 后端的控制器日志仅给 zip 清单、model 不外传；现有 probe `taxonomy_docs` 来自独立 Arelle 重放。若计划未定约采集来源，实施者可能把重放/预期布局冒充当次运行读取证据，污染绝对引用 catalog 可用性判断。总控核读计划 §5 与 review 的 `xbrl_backend.py` 证据后接受：P0-B 每路记录必须注明当次进程内可核映射/加载记录或 OS 文件访问 trace 的实际来源；如只能 Arelle 重放，则单列“重放证据”、核版本/配置/输入哈希，不称 Docling 当次实际读取。若该次证据无法得到，记 blocked，不用猜或重放代替。只修 P0 规格，不实现 hook/产品。
- **PR6-F2 低，accepted／未修复**：真实无 typed 正样本步骤仅罗列 Arelle validation 与 Docling 输出，没有像三合成输入一样写明前者合法性成功并留证后方运行后者。此顺序影响“Docling 失败归产品还是无效样本”的归因，按同一 P0-B 规格补一句先 Arelle 离线 exit0/无验证错误，再 Docling Path/Stream；失败样本不得充正样本。不是新增验收目标。
- 其余 P0-A/B/C、三平台 blocked、OS 零出站、同仓失效及 #4437 边界无新反例。下一 gate gpt-6-sol 仅修 PR6-F1/F2 计划和新 fix artifact，E01/产品不改；之后 Kimi/MiMo 同最终 SHA 复审，P0 尚未执行。

## Sol PR6 P0 修订候选核验

```yaml
setup_status: ok
agent_status: failed
tool_evidence: yes
canary_status: match
warnings: []
retry_class: none
```

- gpt-6-sol `o20-f02-plan-fix-pr6-sol-20260929-01` 显式绝对 O20 workspace、独立 JSONL/stderr/last-message/canary，进程 exit0、JSONL `turn.completed`、15 条完成 shell 中一条记忆索引 `rg` 无匹配 exit1、stderr 空、canary `gpt-6-sol-d0831cee` 匹配。严格逐命令 `agent_status=failed`，虽该查询不影响工作区事实也不能计完成。fix artifact `docs/gateflow/upload-material-o20-f02-plan-fix-pr6-20260929.md` 原样披露；计划只作复审候选。
- 总控实读 P0-B 新计划 SHA `720cf5027420e6b1f2badf679179871ee1e30154a6ff26608013027c204f1f99`、E01 `f75a0c9b...` 不变：Docling Path/Stream 每路实际读取/映射以当次进程内可核记录或绑定进程/时间窗/输入的 OS 文件 trace 证明；独立 Arelle 重放单列并核版本/配置/输入哈希，不冒充当次记录，证据不可得记 blocked。真实无 typed 合规样本先 Arelle 离线 validation exit0/无错误并存原始证据，再用同一 instance 跑 Docling 两路；失败样本不得算正样本。PR6-F1/F2 **计划内容候选已修**，P0 未执行、当次记录机制未实测、真实样本未取得、产品能力未实现。
- 下一 gate 对同一 `720cf502...` SHA 的有效 Kimi/MiMo 独立 `$planreview`；此前失败审查与旧 SHA 均不计 plan gate。

## MiMo PR7 同版复审与当次模型证据入口

```yaml
setup_status: ok
agent_status: failed
tool_evidence: yes
canary_status: match
warnings:
  - "Claude stderr: [claude-code:unrecognized_model] mimo-v2.6-pro[1m]；精确白名单非致命诊断"
retry_class: none
```

- MiMo `o20-f02-plan-rereview7-mimo-20260929-01` 显式绝对 O20 workspace、独立 JSON/stderr/canary，进程 exit0、JSON `subtype=success/is_error=false/stop_reason=end_turn`、42 turns、canary `mimo-08265b8e` 匹配；`docs/reviews/plan-review-20260929-144041.md` 锁 plan SHA `720cf5027420e6b1f2badf679179871ee1e30154a6ff26608013027c204f1f99` 与 E01 `f75a0c9b...`。内容确认 PR6-F1/F2 来源定约及合法性时序已修；但 artifact 披露一条 Python range 越界 `IndexError` exit1，严格 `agent_status=failed`，不计有效 MiMo plan gate。
- **PR7-F1 低，accepted／未修复**：本版 P0-B 规定当次进程内映射/加载证据，不说明如何在失败路径保留 Docling 的同次结果模型；默认 `convert(..., raises_on_error=True)` 抛出会丢结果，而 OS trace 无法看见 zip 内逐条 entry，可能把可诊断向量过度记 blocked。MiMo 一手源码指出 Docling 2.127.0 的非抛出转换返回 `result.input._backend.model_xbrl`，SimplePipeline 当前不卸载，模型含 `urlDocs`/`referencesDocument`。总控接受这条**版本绑定的探针取得路径**作为 P0 规格：在同一转换进程用 `raises_on_error=False` 保留 result，及时快照模型的请求 URI→加载目标和引用边；明确该属性为第三方内部接口，仅用于 P0，先以最小自足样本实测可用，失效则记录版本/原始证据并 blocked，不把它固化为 Dayu 产品依赖。失败状态也保存同次快照；OS trace 只证明可见文件访问，不能代替 zip entry 映射。独立 Arelle 重放仍单列且不得冒充当次记录。
- PR6-F2 与 P0-A/B/C、三平台安全/证据及 #4437 边界无新反例。下一 gate gpt-6-sol 仅修 PR7-F1 P0 plan 与新 fix artifact；再 Kimi/MiMo 同最终 SHA 复审，P0/产品未实施。

## Sol PR7 P0 修订候选核验

```yaml
setup_status: ok
agent_status: failed
tool_evidence: yes
canary_status: match
warnings: []
retry_class: none
```

- gpt-6-sol `o20-f02-plan-fix-pr7-sol-20260929-01` 显式绝对 O20 workspace、独立 JSONL/stderr/last-message/canary，进程 exit0、JSONL `turn.completed`、canary `gpt-6-sol-160d98c7` 匹配；一条 `rg` 猜错 `.venv` 路径 exit2，另有 JS 包装语法错误和 `apply_patch` 匹配失败，stderr 记录后者。严格逐命令/工具协议 `agent_status=failed`，候选不算有效实施 gate。新 fix artifact 为 `docs/gateflow/upload-material-o20-f02-plan-fix-pr7-20260929.md`。
- 总控实读新版 P0 plan SHA `7bf2564dc0b828b59d5bdfddac4a7d91215cf06fac6ee5a86804d1049b906844`，E01 SHA `f75a0c9b...` 不变。新增 §5 P0-B 先要求无 typed 成功/typed 失败的合法最小样本实测属性链，再在同次进程以 `raises_on_error=False` 保留 result，及时快照 Docling 2.127.0 `result.input._backend.model_xbrl` 的 `urlDocs`/`referencesDocument`；区分临时目录已清理、初始化前无模型、OS trace 和独立 Arelle 重放。内部 API 只作 P0 探针，失效仍按 `blocked: run evidence unavailable` 回 plan/fix。**PR7-F1 计划内容候选已修**；P0 尚未执行、运行时链和真实样本未证实、产品能力未实现。
- MiMo 对同 SHA 的修复性独立 `$planreview` 已预检并派发 `o20-f02-plan-rereview8-mimo-20260929-01`，显式绝对 O20 workspace 与独立 JSONL/stderr/canary；Kimi 同版第二路待派发。两路有效结论前 plan gate 不通过。

## MiMo PR8 当次证据反例裁决

```yaml
setup_status: ok
agent_status: failed
tool_evidence: yes
canary_status: match
warnings: []
retry_class: none
```

- MiMo `o20-f02-plan-rereview8-mimo-20260929-01` 显式绝对 O20 workspace、独立 JSON/stderr/canary，进程 exit0、JSONL `turn.completed`、canary `mimo-fb722ae7` 匹配；`docs/reviews/plan-review-20260929-164018.md` 锁 plan SHA `7bf2564d...` 与 E01 `f75a0c9b...`。一条版本探测命令在非目标 Python 环境 import Docling 抛 `ModuleNotFoundError`、exit1，严格 `agent_status=failed`，不计有效 MiMo plan gate。审查正文判 fail，以下一手源码反例仍需独立裁决。
- **PR8-F1 高，accepted／未修复**：Arelle 2.45.3 `ModelDocument.referencesDocument` 按目标 `ModelDocument` 聚合引用类型，仅保留首个 referring object；同一源文档两次不同元素指向同一目标时，第二元素和 multiplicity 丢失。成功 `urlDocs` 也不含 `urlUnloadableDocs` 的失败请求。当前 P0-B 把这些内部结构写成“逐条引用边/请求 URI→实际目标”完整真源，规格不可执行，可能给 zip/catalog 映射虚假完整性。总控接受：计划必须区分已加载目标集合、失败请求集合、原始逐引用事件；用受控重复同目标及失败引用微型样本实测能否把原始 URI/元素与当次映射对账。若逐边完整来源不可得，对应向量 blocked，不能把聚合摘要冒称事件日志。保持 OS trace 和独立 Arelle 重放的已定限度，不加产品 hook。
- **PR8-F2 中，accepted／未修复**：`raises_on_error=False` 仅控制 pipeline 转换阶段；Docling `XBRLDocumentBackend.__init__` 的缺 Arelle `ImportError` 可在构造期逃出，根本没有 `ConversionResult`。当前计划只写“失败结果但无 model”，采集路径不闭合。计划分三路：成功/typed 转换阶段返回 result，`DocumentLoadError` 形成 invalid-input result，以及构造/导入异常无 result；探针最外层记录异常类型/cause/trace/双流并 blocked。用缺 Arelle、坏 taxonomy、typed 导出最小反例实测，不凭静态源码假称完成。
- PR1～PR7 其它 P0-A/B/C、Arelle 合法性前置、三平台隔离、无 typed 声明无新反例。下一 gate Sol 只修 PR8-F1/F2 P0 计划与新 fix artifact，再双路锁最终 SHA；P0/产品仍未实施。

## Sol PR8 P0 计划候选核验

```yaml
setup_status: ok
agent_status: failed
tool_evidence: yes
canary_status: match
warnings: []
retry_class: none
```

- gpt-6-sol `o20-f02-plan-fix-pr8-sol-20260929-01` JSONL `turn.completed`、canary `gpt-6-sol-ba7da004` 匹配，stderr 空、完成 shell exit0；artifact 另披露一次 JS 工具编排语法错误。中断后 exec session 退出码不可回读，严格不计有效 agent completion。总控实读新 plan SHA `4b4e18a1cf499a05cec293c3afe334aa5afe5c6ba0358ff62a92722a5f8bd545` 与 `docs/gateflow/upload-material-o20-f02-plan-fix-pr8-20260929.md`：PR8-F1 分成功目标、失败请求、原始逐引用事件三集合，`referencesDocument` 只作聚合摘要；用重复同目标/失败引用小探针实测 href 保序与遗漏，不能闭合则 blocked。PR8-F2 分三种 result/无 result 路径并以最外层捕获异常链。E01 冻结 SHA 不变。**PR8-F1/F2 计划内容候选已修**；小探针不能冒充 P0 正式验收。下一 gate 同 SHA Kimi/MiMo 独立 plan review，P0/产品未实施。

## PR9-F1 原始声明与运行事件界限（评审在途，已登记）

- MiMo 对 PR8 SHA `4b4e18a1...` 的独立 review artifact `docs/reviews/plan-review-o20-pr8-mimo-20260929.md` 已落盘，进程 exit0；其完整结构化核验和 Kimi 同版结论尚待收齐。总控先按用户要求登记修复项，不能以初稿宣告 plan gate 通过。
- **PR9-F1 中，accepted／未修复**：Arelle 2.45.3 `hrefObjects` 只保留成功 href 的逐元素关系；`referencesDocument` 按目标聚合，`urlUnloadableDocs` 按 URI 聚合；`importDiscover`、schemaLocation 与 zip entry 没有通用逐事件／实际 entry 读取真源。计划的第三集合若称“原始逐引用事件”，实施者可能把 XML 静态声明误作该次实际尝试。总控核读 review 所列 `ModelDocument.py:79-80,139-148,1065-1105,1279-1281,1488-1496` 与 `FileSource.py:482-492` 的语义链，接受修计划：改称“原始引用声明清单”，每条显式 `attempt_observation=observed|unknown`；仅有同次直接事件且可与原始元素对账才 observed。重复失败、非 href import/include/schemaLocation、zip entry 缺直接运行证据即 `blocked: run evidence unavailable`。加入重复失败 import/include 与 catalog entry 小探针，不能用静态 XML、聚合摘要或 OS zip 容器访问推断逐边执行。此项只修 P0 规格，不授权产品支持或降低 P0 验收条件。

```yaml
setup_status: ok
agent_status: failed
tool_evidence: yes
canary_status: match
warnings: []
retry_class: none
```

- MiMo `o20-f02-plan-pr8-mimo-20260929-01` 进程 exit0、JSONL 152 条均可解析、`turn.completed`、68 条 shell exit0、无 error/failed event、stderr 空、canary `mimo-d3df0beb` 逐字匹配；但任务正文额外要求“所有检查命令自身 exit0”，其中两条分别 exit127（错用隔离工作区不存在的 `.venv`）与 exit1（zsh 引号），故按本次派发合同 `agent_status=failed`。内容 `pass-with-risks` 及 PR9-F1 可作为总控独立核验输入，不能计有效同版 plan gate。

```yaml
setup_status: ok
agent_status: failed
tool_evidence: yes
canary_status: match
warnings: []
retry_class: none
```

- Kimi `o20-f02-plan-pr8-kimi-20260929-01` 进程 exit0、JSONL 179 条可解析、`turn.completed`、63 条 shell exit0、无 error/failed event、stderr 空、canary `kimi-681946f1` 匹配；一条把 `git rev-parse` 与预期不存在文件的 `ls` 串联后整体 exit1，违反本次任务额外的所有命令 exit0 要求，故 `agent_status=failed`。其 `docs/reviews/plan-review-o20-pr8-kimi-20260929.md` 内容判 P0 计划 `pass` 且无新 finding，仅作为总控核验输入；不计双路 gate。Sol 已按 accepted PR9-F1 修计划的独立任务在途。

## Sol PR9-F1 计划修订候选

```yaml
setup_status: ok
agent_status: failed
tool_evidence: yes
canary_status: match
warnings: []
retry_class: none
```

- gpt-6-sol `o20-pr9-f1-sol-20260929-01` 进程 exit0、JSONL 57 条可解析、`turn.completed`、20 条 shell exit0、stderr 空、canary `gpt-6-sol-a239e34e` 匹配；一条记忆 `rg` 无匹配 exit1 在 JSONL 中仍是 `item.status=failed`，另一次 JS 编排语法错误未改文件。按 `$sub-agents` 的非豁免 failed event 条件，**更正**先前 completed 判断为 `agent_status=failed`；内容仅作总控候选，不计有效 Sol gate。总控实读新 plan SHA `9d99f7bdc7bb0feb103bee9f71a7d6097cb10ee0a3a7d782c9fda4b33c58906c` 和 `docs/gateflow/upload-material-o20-f02-plan-fix-pr9-20260929.md`：第三集合为静态声明清单，`attempt_observation` 仅有同次逐元素直接事件才 observed；重复失败 import/include 与 catalog entry 小探针和 blocked 边界明确，PR8-F1/F2、P0-A/C 与公共能力上限不回退。**PR9-F1 计划内容候选已修**；同 SHA Kimi/MiMo 独立 plan review 在途，P0/产品未实施。

## MiMo PR9 同版复审

```yaml
setup_status: ok
agent_status: failed
tool_evidence: yes
canary_status: match
warnings: []
retry_class: none
```

- MiMo `o20-pr9-mimo-20260929-01` 进程 exit0、JSONL 133 条可解析、`turn.completed`、57 条 shell exit0、canary `mimo-2f7392c2` 匹配；两条 shell exit1/2 为 `item.status=failed`，另有 Goal tool 非持久线程失败，stderr 107 字节；均非白名单豁免，故不计有效 plan gate。`docs/reviews/plan-review-o20-pr9-mimo-20260929.md` 内容 pass、零 material finding：原始声明与 observed 同次逐元素证据的边界、blocked 停点及 PR8/P0-A/C/#4437 范围经源码核对；只作为总控证据。Kimi 同 SHA 在途，P0/产品未实施。

## Kimi PR9 取证窗口反例（进程在途，修复先登记）

- Kimi review artifact `docs/reviews/plan-review-o20-pr9-kimi-20260929.md` 已落盘，完整进程/JSON/canary 核验待终态；其源码反例已由总控独立读 Docling 2.127.0 `BasePipeline.execute` `finally: self._unload(conv_res)`、`BasePipeline._unload` 的 input backend `unload()`、XBRL backend `model_xbrl.close()` 与 Arelle `ModelXbrl.close` `__dict__.clear()` 复核。不能因 review 尚在途丢失修复项。
- **PR10-F1 高，accepted／未修复**：PR9 计划要求 `convert(..., raises_on_error=False)` 返回后从 `result.input._backend.model_xbrl` 快照 `urlDocs` 等，同次模型在返回前已被 unload/close 清空，这条中心采集链不可达。Sol 先在 P0 计划钉版本绑定、探针级的**同一次 convert 运行卸载前快照**方案（例如受控、作用域内包装 XBRL backend `unload`：先把模型数据复制为独立普通值，再调用原方法并恢复包装；只用于 P0，不进入 Dayu 产品）；以合法自足无 typed 最小样本实测卸载前可读、返回后不可读，并保存完整 argv/版本/输入哈希/异常/双流。若该作用域包装不能安全取得直接记录，则明确 fallback 为独立 backend sibling 运行，严格标其自身运行身份，不与 convert result 冒称同次；真实 Docling Path/Stream 的逐边证据仍 blocked，回 goal/证据机制裁决。不得把 Arelle 重放或 sibling 模型冒充 convert 当次。
- **PR10-F2 低，accepted／未修复**：失败 href 首次错误可能只在默认 logging 的格式化文本里带 `modelObject`，重复失败又由 URI 缓存短路；格式化日志不是可按元素身份审计的结构化直接事件。计划明确失败方向仅接受模型/文件源中可逐元素对账的结构化记录标 `observed`，文本日志/stderr 一律不能；重复失败 href/import/include 探针分别记声明、结构化事件有无、聚合失败项与文本原始证据，不用文本推断 observed。PR9 的 strict blocked 保持。

```yaml
setup_status: ok
agent_status: failed
tool_evidence: yes
canary_status: match
warnings: []
retry_class: none
```

- Kimi `o20-pr9-kimi-20260929-01` 进程 exit0、JSONL 200 条可解析、`turn.completed`、64 条 shell exit0、canary `kimi-2820b23d` 匹配；三次工具层 ERROR 见 665 字节 stderr（一次 exec 创建失败、一次函数参数缺 `cmd`、一次 patch 格式错误），均非白名单诊断，故 `agent_status=failed`，内容不能计有效 plan gate。其 `docs/reviews/plan-review-o20-pr9-kimi-20260929.md` 内容 fail，PR10-F1/F2 已由总控沿同一版本直接源码链接受。Sol 在独立 clone 修 P0 计划与最小探针，原 SHA review 不受并发写入。
