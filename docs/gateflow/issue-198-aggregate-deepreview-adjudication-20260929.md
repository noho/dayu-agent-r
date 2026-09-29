# Issue #198 整项 aggregate deepreview 总控裁决

- Gate：S1+S2 accepted slice commits 后的整项 `aggregate deepreview`；目标 commit `2643de25d6258fe2d83b527ea3823ffa3eb19bff`，相对 PR #197 原 head `9735800cb55a40336469593fa2fddae43c9c69ad` 的三个 #198 提交。
- 范围：typed source integrity 公开投影、部分发布守恒、direct/job/CLI/wait 一致性，与未知 download 安全诊断交互；其它 upload/Oxx/CNInfo 单日 work unit 不在本 gate。
- MiMo `/private/tmp/dayu-issue198-aggregate-mimo` 与 ds-flash `/private/tmp/dayu-issue198-aggregate-dsflash` 独立干净 detached worktree，均从目标 commit 建立，`.venv` 指向项目环境。`sub-agent-preflight setup_status=ok`、显式绝对 cwd、独立 output/stderr/canary；sessions `66838` 与 `81219` 在途。未获两路结构化结果前不得计 pass、不得推送 PR。

## 待收结果与裁决

- MiMo：`docs/reviews/issue-198-aggregate-mimo-20260929.md`（独立 worktree 内），待 exit/JSON/canary/stderr/命令证据核验。
- ds-flash：`docs/reviews/issue-198-aggregate-dsflash-20260929.md`（独立 worktree 内），待同项核验。
- 所有新 finding 必须同时登记本文件和主修复队列；accepted finding 需 Sol 修复、双路同版 re-review。通过后下一 gate 为 `accepted deepreview commit`。

## MiMo 首轮结构化结果与协议失败

```yaml
setup_status: ok
agent_status: failed
tool_evidence: yes
canary_status: match
warnings:
  - "[claude-code:unrecognized_model] mimo-v2.6-pro[1m]"
retry_class: provider
```

- `issue198-aggregate-mimo-20260929-01` 进程 exit0、Claude JSON `subtype=success/is_error=false/terminal_reason=completed`、110 turns、canary `mimo-3ae9849b` 匹配，stderr 仅白名单提示；artifact `/private/tmp/dayu-issue198-aggregate-mimo/docs/reviews/issue-198-aggregate-mimo-20260929.md`。其内容独立走读 S1+S2、报告 856 affected passed、pyright0、八个改动生产文件覆盖率 80%–92%、fresh CLI 哈希复核，无 material finding；11 项 residual 均分类。
- 但该 reviewer 在最终结果与 artifact 明确自报一条复合 shell 命令因 zsh `=` 展开而 **exit 1**，违反此任务每条 shell 命令自身 exit0 的协议。严格 `agent_status=failed`；内容只是待复核证据，不计第一条有效 aggregate 路。按规则允许一次同 provider 新 label 修复性重试，禁止静默改写旧结果；ds-flash 首轮仍在途。
- MiMo 修复性重试 `issue198-aggregate-mimo-r2-20260929-01` 已在全新干净 commit worktree `/private/tmp/dayu-issue198-aggregate-mimo-r2` 经 preflight ok 派发 session `44045`，显式绝对 cwd、独立 JSON/stderr/canary，只能写新 review 文件；要求避开 zsh 裸 `=` 命令并如实报告每条 exit。该轮仍在途，不计有效结果。

## ds-flash 首轮结果、协议失败与总控直接核查

```yaml
setup_status: ok
agent_status: failed
tool_evidence: yes
canary_status: match
warnings:
  - "[claude-code:unrecognized_model] deepseek-flash[1m]"
retry_class: provider
```

- `issue198-aggregate-ds-flash-20260929-01` 进程 exit0，Claude JSON `subtype=success/is_error=false/terminal_reason=completed`、173 turns、canary `ds-flash-c43b217d` 匹配，stderr 仅白名单模型提示。artifact `/private/tmp/dayu-issue198-aggregate-dsflash/docs/reviews/issue-198-aggregate-dsflash-20260929.md` 的内容没有 material finding，实跑 affected 856 passed、pyright0、八生产文件覆盖率 80%–92%、fresh/replay 哈希重算。
- 但该 artifact 明列插桩测试、base/HEAD CLI 与非 CLI 大矩阵各有 exit1，并描述全量 suite 挂起/中止；任务明确要求**每条 shell 命令自身 exit0**、预期非零在 Python wrapper 捕获。无 Claude tool 细节可推翻其自报；严格判 `agent_status=failed`，首轮不能计第二条有效 aggregate 路。允许一次新 label 同 provider 修复性重试；不把大型失败矩阵伪称验证通过。两份 base/HEAD 相同失败集只作为诊断材料。
- **集成基线直接纠错**：总控以 `git merge-base --is-ancestor 9735800cb55a40336469593fa2fddae43c9c69ad 2643de25d6258fe2d83b527ea3823ffa3eb19bff` 得 exit1；共同基线实际为 `8d8d494fbbce0052372fb1b42097c9f7222cfa28`。PR head 一侧有点号元数据/O03/O20 等额外提交，#198 一侧有三提交；`git log PR..#198` 只列三提交不等于可快进。整项 aggregate 的 code scope 应用共同基线 `8d8d494f..2643de25`，后续 PR 集成必须在 PR head 上受控 merge #198 分支并对**合并结果**做 PR review，不能强推覆盖远端。
- **AG-R1/OQ1 低／deferred-with-owner**：storage `SourceIntegrityPreflightError.__init__` 目前不校验 `reason` 枚举成员。总控直接核对构造器先访问 `reason.value`：普通字符串会在构造时 AttributeError；若传带 `value` 属性的非成员伪对象，构造可过，Fins 封闭映射查表会 KeyError 并可能逃线程原始 traceback。`rg` 与各构造点核对当前生产均传有效枚举成员，旧版对异常形状同样会逃逸；不是 #198 引入的当前可达缺陷，不用下游兜底扩当前 WU。登记独立 `fins-source-integrity-reason-constructor-invariant`，由 storage 异常构造 owner 前置校验并补 owner 测试；待该 WU goal/证据确认。
- OQ2 事件名、OQ3 候选级进度 sink、OQ4 `__all__`、OQ5 mid-filing 无真实 CLI 均已分类为既有合同/有界验证风险，无当前阻断。MiMo 修复性重试在途，ds-flash 修复性重试待派；aggregate gate 未过。
- ds-flash 唯一修复性重试 `issue198-aggregate-ds-flash-r2-20260929-01` 已在新干净 commit checkout `/private/tmp/dayu-issue198-aggregate-dsflash-r2` 经 preflight ok 派发 session `20948`，显式绝对 cwd、独立 JSON/stderr/canary，只写新 review；避免运行已知 exit1 或挂起全量矩阵。MiMo r2 session `44045` 同版并行在途；两路未形成有效最终结果。

## ds-flash 有效修复性重试及 OQ1 扩展证据

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
canary_status: match
warnings:
  - "[claude-code:unrecognized_model] deepseek-flash[1m]"
retry_class: none
```

- `issue198-aggregate-ds-flash-r2-20260929-01` 进程 exit0、Claude JSON `subtype=success/is_error=false/terminal_reason=completed`、100 turns、canary `ds-flash-1f017680` 逐字匹配，stderr 仅白名单提示；本轮 13 条 shell 命令均自身 exit0。artifact `/private/tmp/dayu-issue198-aggregate-dsflash-r2/docs/reviews/issue-198-aggregate-dsflash-r2-20260929.md`。独立复核 S1+S2 组合无 material finding，affected 856 passed、全量 pyright0，S2 diff 与 fresh/replay 证据哈希逐字一致。前轮 coverage/全量矩阵属于历史诊断，本轮明确不冒充重跑。
- OQ1 新的直接代码证据：若以后有带 `.value` 的非成员伪对象进入 `SourceIntegrityPreflightError`，job `_save_typed_download_failure` 的 public 映射在该函数 `try` 外抛 KeyError，裸 Thread 会落原始 traceback 且 job 可能停 `running`；与 #198 前的 generic 保存收口相比是新结构性逃逸面。当前 `dayu/` 13 处构造点均传封闭 enum，故该路径当前不可达。总控将 job 后果写入 `fins-source-integrity-reason-constructor-invariant` 并交 `fins-direct-projection-failsafe` 后续一起核；不在 #198 的 Fins 下游加 fallback。若后续出现实际非成员生产调用，须回到 #198 gate 重新裁决可达性。
- OQ3/4/5 保留既有非阻断分类；OQ6 S1 实施摘要的 diff base 歧义仅是审计口径，生产/测试文件相同，可在 closeout 说明，不改历史实施记录。MiMo r2 仍在途，aggregate gate 尚未双路通过。

## MiMo 有效修复性重试与整项终裁

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
canary_status: match
warnings:
  - "[claude-code:unrecognized_model] mimo-v2.6-pro[1m]"
retry_class: none
```

- `issue198-aggregate-mimo-r2-20260929-01` 进程 exit0、Claude JSON `subtype=success/is_error=false/terminal_reason=completed`、100 turns、canary `mimo-1b9eff68` 匹配，stderr 仅白名单提示；本轮所有 shell 命令自身 exit0，内层预期非零探针由 Python 捕获并如实报告。artifact `docs/reviews/issue-198-aggregate-mimo-r2-20260929.md`。前轮失败的 zsh `echo ===` 是纯词法分隔命令失误，不隐藏测试失败或代码 finding。两路有效 r2 与两份失败首轮 artifact 均已归入当前工作树，保留协议失败历史。
- MiMo 独立走读 S1+S2 七条跨层链，无 material finding；受影响 856 passed、扩展 892 passed、pyright0、八生产文件覆盖率 80%–92%（有明确 deselect 口径）、fresh 原始流与产物哈希复核。ds-flash r2 同版亦无 material finding、856 passed、pyright0、哈希一致。总控直接核对真实共同基线 `8d8d494f`、两个 review 的快照与 owner 分类，采纳 **aggregate deepreview pass**；没有 accepted 未修复 finding，也无未分类 residual。
- **AG-R2/OQ2 低／needs-more-evidence／assigned to later work unit**：MiMo 的九文件 coverage 组合中两个既有取消时序用例可重复失败，而普通 856/892 套件、该测试文件单独插桩和两用例单独插桩均通过。测试函数本身存在于 #198 前，但组合失败是否由 #198 新测试/全局状态触发尚未做同口径 base 对照；不能断言已经证明为“既有失败”。登记 `fins-cancellation-coverage-order-sensitivity`，由 CLI stream owner/测试夹具 owner 判真实时序契约和组合顺序；本 issue 代码只改 download 外层未知 catch，未改取消清理主链，普通验收全绿，coverage owner 阈值满足，故当前不阻断 #198。
- OQ1 constructor invariant/job 二次后果归独立 WU；OQ3 进度 sink、OQ4 `__all__`、OQ5 typed partial 真实 CLI 覆盖及 OQ6 历史 diff base 为有界残余/审计说明，不加本 issue 兼容分支或扩大目标。下一 gate 为 `accepted deepreview commit`，之后在 PR #197 旧 head 上合并 #198 分支、验证合并快照、推送并做双路 PR review。
