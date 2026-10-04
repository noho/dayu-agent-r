# Issue #198 S2 代码复审总控裁决

- Gate：S2 `implementation -> code review`；本文件是总控在双路审查期间持续登记的裁决，不预先宣告 review pass。
- Binding scope：`docs/gateflow/issue-198-download-failure-projection-goal-20260928.md`、同名前缀 plan 的现行 `### S2`；依赖 S1 accepted commit `7234d42dbaea603112c6fed52776281228d261a7`。
- 代码候选：`/private/tmp/dayu-issue198-s2` 的 11 个 tracked 文件，`git diff --binary` SHA-256 `d53e67f29e26c6d835c42ea81ce43aef34a27cf831959ee685c1802b42df14c5`；实施记录 SHA-256 `5e0061ea91b8f853be304173c3109247c981cba4988ee5d6a9a83d481342956a`。两个独立 reviewer worktree 逐字复算同两 SHA，HEAD 同为 S1 commit；review 期间不得把主工作区的其它 WU diff 混入。

## Sol 实施派发协议与候选事实

```yaml
setup_status: ok
agent_status: failed
tool_evidence: yes
canary_status: match
warnings: []
retry_class: provider
```

- `issue198-s2-sol-20260929-01` 进程 exit0、JSONL 有 `turn.completed`、canary `gpt-6-sol-760eeeb9` 匹配、stderr 空。但实施中一次 `pyright` 命令自身 exit1（当时 `dayu/cli/output.py:443` 误引用 `failure`），形成非豁免 failed event；最终修正后的 856 affected passed、四文件 coverage 94/91/85/85%、全量 pyright 0 仅作当前代码候选的独立验证线索，不追认本轮 agent_status completed。总控须在 review/fix 后对最终快照重新验证。
- 总控直接读四生产 diff：runtime 的纯 helper 只取经验证代码位置和安全异常类型标签；Fins producer 以公共 EXECUTION 分类驱动，先 RESULT 后 ERROR；CLI 外层最后 catch 的 download 分流使用同一 helper；`output.py` 独占 CLI 日志定位文案。未观察到违反 S2 owner boundary 的新增公开 schema。此为待双路挑战的初判，不代替 review。

## 真实 CLI 验证缺口

- Sol 在 `/private/tmp/issue198-cli.GIJPem` 用计划精确 `000333/FY/2025-03-28` 初次下载：退出 0，但 `discovered=0`，没有已发布 filing；原计划要求的注入非点号 root 条目、复跑 typed storage 因前置事实不存在而**未通过**，不能把 exit0 当通过。Sol 已核对清理该临时目录，观测保留在实施记录。
- 总控另在 `/private/tmp/issue198-cli-alt-pkyatz6s` 用用户确认的中国本地披露日 `2025-03-29`、相同 FY/000333 与独立日志初次下载：退出 0，同样 `discovered=0`、`filings=[]`，stdout/stderr 留在该隔离目录。日期调整也没有得到前置事实，不伪造成功。
- 裁决暂为 `needs-more-evidence`：外部 provider 在这两个精确筛选下均无候选，不能推断 #198 代码行为错误，也不能违反 accepted plan 声称真实 CLI canary 通过。S2 双路审查需提出最小替代受控输入或清楚的验证停止条件；若需改 accepted plan 的验收方法，先记录修订并复审，不擅自放宽成功信号。
- **追加替代验证候选**：总控读取旧 S1 隔离 case 的真实发布 PDF/Docling/meta/manifest 与 readback，复制其 `portfolio` 到全新 `/private/tmp/issue198-cli-replay-e23865b8`；本次真实 provider 三日发现同一候选且先按 `integrity_complete` 跳过。仅注入普通非点号 root 外来文件后，同参数真实 CLI 退出 1、`classification="storage"`、`reason_code="unsafe_publication"`、安全修复提示，五份已发布文件字节 SHA 不变，unknown 安全日志不误记；清除唯一 mutation 后同参数再次退出 0、同一候选 skip。精确流哈希、方法差异和未覆盖项见 `docs/gateflow/issue-198-s2-cli-replay-evidence-20260929.md`。此证据**满足 #198 storage→CLI 的真实路径复验**，但不冒充 accepted plan 所写的本轮 fresh Docling 转换；是否以方法替代关闭验证 gap 须在双路审查与总控 gate 裁决中明确。
- **fresh 主链路已补证**：另在从空目录创建的 `/private/tmp/issue198-cli-wide2-9aklx640` 真实 CNInfo→Docling→manifest 发布同一 FY2024 年报（provider 三日以上窗口 2025-03-27..31，退出 0、`discovered=1/downloaded=1`、meta `ingest_complete=true`，PDF/Docling SHA 与 meta 对上）；同请求注入唯一非点号 root 文件退出 1，公共 `storage/unsafe_publication`、源文件字节不变、无 unknown 日志；清除后同请求退出 0、`skipped=1/integrity_complete`。精确流哈希、执行边界和 180 秒首轮超时均在 `docs/gateflow/issue-198-s2-cli-fresh-evidence-20260929.md`。故 #198 的 fresh 发布→typed 失败→恢复成功信号已有当前代码候选的真实隔离证据；仅**精确单日筛选**仍失败，归独立 `fins-cninfo-single-day-discovery-window`，不能声称该 WU 已修。审查和最终代码快照核验仍待完成。

## 双路审查派发

- MiMo 与用户授权的 Kimi 额度备份 ds-flash 分别在 `/private/tmp/dayu-issue198-s2-review-mimo`、`/private/tmp/dayu-issue198-s2-review-dsflash` 深审同一候选。`sub-agent-preflight setup_status=ok`、绝对 `--cwd`、独立 output/stderr/canary，sessions `79426` 与 `10590` 在途。审查任务只允许各写自己的新 review artifact，不改产品/测试/README；任何 finding 在本文件与主修复队列即时登记。

## 残余分类

- `fins-direct-projection-failsafe`、`fins-other-raw-diagnostics-audit`、`fins-download-storage-sibling-errors`、`fins-download-no-source-retry-hint`：各为已登记独立后续 WU，本切片不伪称解决。
- 精确日期 provider 0 候选导致的 CLI 验证缺口：当前 `needs-more-evidence`，在 S2 review 后须明确验收/外部限制去向，不能无分类关闭。

## ds-flash 第一轮同版审查与即时裁决

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
canary_status: match
warnings:
  - "[claude-code:unrecognized_model] deepseek-flash[1m]"
retry_class: none
```

- `issue198-s2-code-dsflash-20260929-01` 进程 exit0，JSON `subtype=success/is_error=false/terminal_reason=completed`、92 turns，canary `ds-flash-97fd438e` 逐字匹配，stderr 仅白名单模型名提示。review `docs/reviews/code-review-20260929-201936.md`（原位置 `/private/tmp/dayu-issue198-s2-review-dsflash/docs/reviews/`）锁同一 diff SHA、实跑 856 affected passed/四生产文件覆盖率 94/91/85/85%、全量 pyright0，全部 shell 命令自身 exit0。该 review artifact 尚待从独立 clone 按无冲突文件名归入 S2 checkpoint。
- **S2-R1/F1 中／accepted 为当时验证缺口／已补证候选**：review 时只看到了 Sol 的单日 0 候选，指出不能以 owner 测试或 S1 旧 CLI 证据冒充 S2 当前真实入口。总控随后在当前 S2 候选上取得 fresh provider→Docling→manifest 发布、同请求 typed root mutation 失败和清除后 skip 的完整真实 CLI 证据，见 `issue-198-s2-cli-fresh-evidence-20260929.md`；又以旧真实来源克隆作独立 readback 复核。原单日方法仍失败且归独立 CNInfo WU，#198 的真实主链路成功信号已补；待双路 re-review 核验精确 SHA/输出后改为 `已修复`，不把原单日命令记为通过。
- **S2-R1/F2 低／accepted／未修复**：根 README 的下载专属日志提示与脱敏说明放在 §5.2 上传摘要长段，下载 §5.1 读者不可见。owner 是根 README 的最终用户下载/日志排障位置；把下载两句移到 §5.1，通用 direct 外层固定错误指引放 §3.1 日志参数或相邻通用段，§5.2 保持上传语义；不改产品代码。修后人工通读相关章节，不重复提示。
- **S2-R1/F3 低／rejected-with-reason**：consumer 主动 abort 后 `_emit_direct_result` 的 terminal claim 返回 `None`，异常 RESULT 不再投递，但 producer 真实捕获到的未知 EXECUTION 异常仍是 operator 诊断事实。日志事件 `fins.download.unexpected_failure` 只声称发生了异常，没有声称已向用户交付 FAILURE；没有从日志反推公开终态。plan 的“先 RESULT 后日志”描述正常可投递路径的操作顺序，abort 时调用先后仍成立；抑制真实安全诊断会降低排障能力。取消/RESULT 构造二次失败归已登记 `fins-direct-projection-failsafe`；本轮不改 `_emit_direct_result` 返回契约或按终态过滤 operator 异常。
- ds-flash Open Question 的已知 missing adapter 也落 EXECUTION：计划本来以**公共 EXECUTION 分类的异常**作为日志条件，事件名 `unexpected_failure` 表示非封闭下载失败，不承诺原始异常类未知；不在 S2 加第二份异常名单。逐帧重复 `source_root.resolve` 在异常诊断路径有界，没有可靠吞吐损害证据，非当前修复项。
- 下一步先等 MiMo 同版结果；若无新阻断，派 gpt-6-sol 仅修 F2 文档与补足当前 CLI 证据引用，再两路同版 re-review，合格后窄提交 S2。

## MiMo 第一轮同版审查及双路合并裁决

```yaml
setup_status: ok
agent_status: failed
tool_evidence: yes
canary_status: match
warnings:
  - "[claude-code:unrecognized_model] mimo-v2.6-pro[1m]"
retry_class: provider
```

- `issue198-s2-code-mimo-20260929-01` 进程 exit0、JSON `subtype=success/is_error=false/terminal_reason=completed`、65 turns、canary `mimo-73c9ed6a` 匹配，stderr 仅白名单模型名提示；但 review artifact 自报一条 zsh `===` 命令 exit1，违反本任务全部 shell 命令自身 exit0 及结构化 failed-event 合同，故严格 `agent_status=failed`，不能计有效 MiMo 第二路。其内容审查 `/private/tmp/dayu-issue198-s2-review-mimo/docs/reviews/code-review-20260929-204315.md` 已复制入当前 worktree 同名路径，仅作为待复核证据。
- MiMo 独立读四生产文件、四测试和三 README，内容无生产 code finding；唯一中 finding 是审查当时真实 CLI 的 0 候选缺口，与 ds-flash S2-R1/F1 同根。总控后来取得 fresh 三日窗口真实发布→typed 失败→清除后 skip 的本快照证据，且 `typed.stderr` 明确不含 EXECUTION 日志提示、`typed.log` 不含两种 `fins.download.*` unknown 事件；见 `issue-198-s2-cli-fresh-evidence-20260929.md`。单日精确窗口仍失败、不冒充通过，归独立 CNInfo WU。
- MiMo 的 cancel/abort 诊断 open question 与 ds-flash F3 同根，按上节 `rejected-with-reason`：日志记真实异常事实，不声明已交付 FAILURE 终态；RESULT 构造二次失败归独立 failsafe WU。MiMo 未发现新的当前切片修复项。
- 合并结果：S2-R1/F2 README 落位仍 `accepted/未修复`；S2-R1/F1 验证缺口已有 fresh 证据、待同版 re-review 改 `已修复`；MiMo 协议失败需在 F2 修订后的新 SHA 上用新 label 作一次同 provider 修复性重审。ds-flash 当前快照有效，但 F2 修订后也须新 SHA 同版复审。S2 gate **未通过**，不提交。
- F2 窄修已由 gpt-6-sol `issue198-s2-f2-sol-20260929-01` 经 `sub-agent-preflight setup_status=ok`，显式绝对 `/private/tmp/dayu-issue198-s2`、独立 JSONL/stderr/last-message/canary 派发 session `12689`。只准改根 README 与新增 F2 fix artifact；其结果未收齐前 F2 仍 `未修复`，不得启动新版 review 或提交。

## F2 窄修完成及新版复审输入

- `issue198-s2-f2-sol-20260929-01` 进程 exit0，JSONL `turn.completed`、canary `gpt-6-sol-14b63864` 匹配；结构化执行命令均 exit0。只修改根 README，新增 `issue-198-s2-code-review-f2-fix-20260929.md`；`git diff --check` 通过。§3.1 放通用日志参数与外层固定提示，§5.1 放下载 EXECUTION 提示、留档操作和安全诊断范围，§5.2 仅保留上传语义。README diff SHA-256 `b3a4f9ad77c5c458f899cf2817feb8a7ae5e7025385d7fe315def617c1ce97e2`。
- **S2-R1/F2 低／accepted／已修复候选**：总控已检查 F2 记录及章节字面验证，待新 SHA 双路有效 re-review 确认后关闭。11 文件候选 diff SHA-256 `2a79d0713b965be82734552d89619f56957968d62b0344a2652d8848797cfc54`。**S2-R1/F1 中／fresh 证据已补、待复审确认**；原单日 0 候选另属 CNInfo WU。

## ds-flash 新版 re-review 首路结果与新观察登记

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
canary_status: match
warnings:
  - "[claude-code:unrecognized_model] deepseek-flash[1m]"
retry_class: none
```

- `issue198-s2-r2-ds-flash-20260929-01` 进程 exit0、Claude JSON `subtype=success/is_error=false/terminal_reason=completed`、74 turns、canary `ds-flash-d6354447` 逐字匹配，stderr 仅白名单提示，reviewer 报所有 shell exit0。artifact：`/private/tmp/dayu-issue198-s2-review-dsflash/docs/reviews/issue-198-s2-r2-dsflash-20260929.md`；同版 diff/fresh 证据 SHA 匹配。复核 856 affected passed、四文件覆盖率 94/91/85/85、pyright0。
- 首路建议 F1 `已修复`、F2 `已修复`，并核对 fresh 发布→typed storage 失败→恢复及 README 章节。总控待 MiMo 有效第二路后合并裁决；单日 0 候选始终保留独立 CNInfo WU。
- **S2-R2/F1 低／新观察／rejected-with-reason 候选**：reviewer 以进程内任意代码执行手工注册 `dayu.fake` 并以真实包内 `co_filename` 执行，安全格式化会给出包内相对位置，未泄漏路径或原始异常。当前 helper 的承诺是受信元数据校验并返回有界包内相对位置，不是证明文件字节执行来源；既有任意代码执行前提超出本 issue 威胁边界。总控暂不加复杂代码对象验证，待 MiMo 独立意见后定案；该观察已登记，不能因评为非阻断而丢失。

## MiMo 有效第二路与 S2 最终裁决

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
canary_status: match
warnings:
  - "[claude-code:unrecognized_model] mimo-v2.6-pro[1m]"
retry_class: none
```

- `issue198-s2-r2-mimo-20260929-01` 进程 exit0，Claude JSON `subtype=success/is_error=false/terminal_reason=completed`、66 turns、canary `mimo-baf1b804` 逐字匹配，stderr 仅白名单提示；reviewer 报本轮 shell 均 exit0，前轮 exit1 未补算。artifact `docs/reviews/issue-198-s2-r2-mimo-20260929.md` 与 ds-flash 同版 artifact `docs/reviews/issue-198-s2-r2-dsflash-20260929.md` 均已归入本 worktree。两路锁 HEAD `7234d42d...` + 11 文件 diff SHA `2a79d071...` + fresh evidence SHA `cbb38609...`，均复跑 856 affected passed、四 owner 文件覆盖率 94/91/85/85、pyright0。
- **S2-R1/F1 中／accepted／已修复**：总控采纳两路对 fresh CLI 流、发布物、typed storage 分类及清除 mutation 恢复的复核。执行方法从计划单日修订为 `2025-03-27..31` 窗口，以取得同一 FY 候选；S2 产品/测试在 README-only F2 修改前后逐字节相同，证据适用本次最终候选。原单日 `03-28` 与中国本地 `03-29` 均 0 候选，不记通过，转独立 `fins-cninfo-single-day-discovery-window` WU；未知 EXECUTION 正例由受控 owner/CLI 注入测试证明。
- **S2-R1/F2 低／accepted／已修复**：总控与两路确认 §3.1 通用日志留档、§5.1 下载 EXECUTION/安全诊断、§5.2 上传摘要各归其位；固定提示常量由 `dayu/cli/output.py` 唯一持有，文案未承诺所有 EXECUTION 均有 unknown 日志。
- **S2-R1/F3 低／rejected-with-reason** 维持前述裁决；abort 后安全日志记录真实异常而不宣称交付 RESULT。**S2-R2/F1 低／rejected-with-reason** 定案：ds-flash 的反例必须先具备进程内任意代码执行，能手工注册伪模块及伪代码文件名；helper 只承诺有界安全位置标签，不是执行文件字节的真实性证明，反例不泄漏原始路径/异常或扩大权限。MiMo 独立复审无该 finding；不引入脆弱代码对象比对。
- 残余分类：`fins-cninfo-single-day-discovery-window`、`fins-direct-projection-failsafe`、`fins-download-storage-sibling-errors`、`fins-other-raw-diagnostics-audit`、`fins-download-no-source-retry-hint`、`fins-download-job-reason-code-persistence` 均 assigned to later work unit，已列主修复队列；没有未分类的 #198 S2 阻断项。当前 gate `S2 code re-review` 通过；下一入口 `accepted S2 slice commit`，之后为整项 `aggregate deepreview`。
