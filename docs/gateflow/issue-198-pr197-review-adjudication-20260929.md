# Issue #198：既有 draft PR #197 线上复审总控裁决

- Gate：`PR review`，目标线上 `https://github.com/noho/dayu-agent-r/pull/197`，当前 OPEN/draft、base main、head `codex/upload-material-oracle`，head commit `2219d40b662ae7336dfbcaf62e5fdeb2ab9fa6d7`。PR body 含 `Closes #198`，用户手工 merge 后自动关 issue；`statusCheckRollup=[]`，没有可据以声明 CI 通过的检查。
- 前置：S1/S2 各通过双路 slice review；整项 aggregate 双路有效 r2 审查通过，accepted deepreview commit `cc6ee444`。PR 原 head `9735800c` 与 #198 分支共同基线 `8d8d494f`；受控 merge commit `2219d40b` 两父为 `9735800c`、`cc6ee444`，没有强推；隔离安装环境 863 affected passed、全量 pyright0，见 `issue-198-pr197-integration-20260929.md`。
- MiMo `/private/tmp/dayu-issue198-pr197-review-mimo` 与 ds-flash `/private/tmp/dayu-issue198-pr197-review-dsflash` 各在干净 detached HEAD `2219d40b`、独立 editable venv 中审查线上同一 PR，`sub-agent-preflight setup_status=ok`、显式绝对 cwd、独立 JSON/stderr/canary；sessions `36532`、`91779` 在途。各只能写自己的新 review 文件，不评论 PR、不改代码。

## 待收结果与下一 gate

- MiMo review：`docs/reviews/issue-198-pr197-mimo-20260929.md`（独立工作树），待结构化 exit/JSON/canary/stderr/验证核验。
- ds-flash review：`docs/reviews/issue-198-pr197-dsflash-20260929.md`（独立工作树），待同项核验。
- 所有新 finding 先登记本文件与主修复队列，accepted finding 由 Sol 修复后双路同版 re-review。没有两路有效审查和总控裁决前，不得宣告 PR review pass 或 final closeout。

## ds-flash 首轮结果及新 finding 即时登记

```yaml
setup_status: ok
agent_status: failed
tool_evidence: yes
canary_status: match
warnings:
  - "[claude-code:unrecognized_model] deepseek-flash[1m]"
retry_class: provider
```

- `issue198-pr197-ds-flash-20260929-01` 进程 exit0，Claude JSON `subtype=success/is_error=false/terminal_reason=completed`、103 turns、canary `ds-flash-1081fc08` 匹配，stderr 仅白名单提示；artifact `/private/tmp/dayu-issue198-pr197-review-dsflash/docs/reviews/issue-198-pr197-dsflash-20260929.md`。内容沿线上 `2219d40b` 合并快照审查，无 material correctness/privacy finding；本 checkout 863 affected passed、pyright0，五处合并重叠均保留 PR/#198 两侧语义。
- 但 review 自报 `gh` 首次调用因 Claude sandbox keychain/TLS 失败，随后放开该单命令 sandbox 才成功；本任务要求每条 shell 命令自身 exit0，且非白名单 failed tool event 不可由后续成功抵销。严格 `agent_status=failed`，首轮内容仅作待复核证据。允许一次新 label 同 provider 修复性重试，避免再运行已知会失败的 sandbox `gh` 路线；线上元数据由总控独立读回。
- **PR-R1/F1 低／accepted 候选／未修复（当时）**：`safe_exception_trace` 虽只输出末 16 帧，却对全部 traceback 帧逐一调用 `_safe_trace_frame`；其中**受信 `dayu.*` 帧**才进行三次 `Path.resolve(strict=True)`，外部帧早退。深栈中受信帧数量增多会使失败诊断的文件系统开销随之增长。直接代码路径成立；当前只有时延风险、无正确性/泄密证据。建议让 deque 先存帧/行号，再仅验证保留的 16 帧，保留截断计数与输出顺序；待 MiMo 意见后总控定是否当前修复，必要时 Sol 在 runtime helper owner 修并补回归测试。
- **PR-R1/F2 低／rejected-with-reason 候选**：`CLI_LOG_LOCATION_HINT` 显式跨模块 import，但未列 `dayu.cli.output.__all__`。Python 的 `__all__` 只控制 wildcard import，现有列表仅承诺 `render_*` 导出，显式 import 正常且有 pyright/CLI 测试。把内部共用固定提示纳入 wildcard API 会扩大公共面而无消费者需求；总控倾向不修，待 MiMo 意见确认。
- 其它 OQ（cancel/abort 后真实安全异常日志、无 CI checks）维持已有 residual owner/验收限制；PR gate 未通过。

## 总控基于直接代码证据的窄修裁决

- **PR-R1/F1 低／accepted／未修复（当时）**：`safe_exception_trace` 只有末 16 帧会进入输出，但现代码对遍历到的每帧都调用 `_safe_trace_frame`；只有**受信 `dayu.*` 帧**进一步做三次 `Path.resolve(strict=True)`，外部帧早退。受信 Dayu 深栈会在失败诊断路径上产生与受信帧数成比例的文件系统 I/O。复用已有 `deque(maxlen=16)`，先保留 `(frame,line_number)` 与总数，遍历后仅对保留帧做受信校验，保持顺序、`truncated` 及固定 fallback。由 `dayu.runtime.log` owner 修，不在 Fins/CLI 补分支；需 owner 级测试断言深栈仅校验 16 帧，跑受影响测试/全量 pyright/README 触发判断，再双路同版 PR re-review。
- **PR-R1/F2 低／rejected-with-reason**：当前 `output.__all__` 只列七个 render API，Python 显式导入 `CLI_LOG_LOCATION_HINT` 不依赖 `__all__`；没有 wildcard 运行消费者或对其作公开导出承诺。把提示常量加入 wildcard 面反而扩大对外契约，无当前需求。保留现有唯一真源与显式 import。
- MiMo 第一轮仍在独立旧 head clone 审查；Sol 窄修仅在 PR 集成工作树进行，未推送线上 PR，故其 review 目标快照保持 `2219d40b`。若 MiMo 报其它同版 finding，再合并裁决/修复；修订后必须两路独立 re-review，不能用旧 review 抵数。
- gpt-6-sol 窄修 `issue198-pr197-f1-sol-20260929-01` 已经 `sub-agent-preflight setup_status=ok` 派发到显式绝对 `/private/tmp/dayu-issue198-pr197-integration`，独立 JSONL/stderr/last-message/canary，session `46692` 在途。仅允许 `dayu/runtime/log.py`、`tests/runtime/test_log.py`、按约束判断的 `tests/README.md` 和新 F1 fix artifact；未收结构化完成结果前不计已修复。

## Sol 窄修候选与结构化协议裁决

```yaml
setup_status: ok
agent_status: failed
tool_evidence: yes
canary_status: match
warnings: []
retry_class: provider
```

- `issue198-pr197-f1-sol-20260929-01` 进程 exit0，JSONL 有 `turn.completed`、canary `gpt-6-sol-769d2d88` 匹配；但 event stream 有四条非白名单 `error`（websocket TLS 握手断开后 Reconnecting 2/5～5/5），另有一条 `rg` 无命中 command exit1；stderr 有对应 TLS 连接错误。严格按 `$sub-agents` 判 `agent_status=failed`，不能把 agent 自述的完成当成有效结构化 fix 结果。保留其代码候选与 `docs/gateflow/issue-198-pr197-r1-f1-fix-20260929.md` 作为待总控独立验证/复审的输入，不抹掉失败证据。
- 总控已实读候选：只改 runtime helper 与 owner 深栈测试；先有界收集 `(frame,line_number)` 后仅校验最终 16 帧，维持原输出次序与截断/fallback；无 CLI/Fins 旁路、无 README 职责变化。`git diff --check` 通过。总控正在独立重跑 863 项受影响测试与全量 pyright；两项未完成之前 F1 仍 `未修复候选`。MiMo 旧 head review 在途，线上 PR head 未移动。
- 总控独立重跑已完成：隔离 editable venv 指向当前 PR 集成 checkout，同八文件 **863 passed / 3 warnings、exit0**；`source .venv/bin/activate` 后全量 pyright **0 errors/0 warnings/0 informations、exit0**。候选 `git diff --check` 通过，owner 单测包含上述 863。**PR-R1/F1 低／accepted／已修复候选，待同版双路 re-review**；Sol 协议失败历史保留，不把自述作通过证据。MiMo 旧 head 审查仍在途。
- ds-flash 新快照 `issue198-pr197-r2-ds-flash-20260929-01` 已在独立 `/private/tmp/dayu-issue198-pr197-r2-dsflash` 经 preflight ok 派发 session `76851`；HEAD `2219d40b` + 恰两个 tracked 修复文件，diff SHA `4dc7c5d779d5bd073a952c461809a61246dbea3eaaea76b12f9a062a09e4fab7`，fix artifact SHA `d0ad6713...`，隔离 venv 指向该 checkout。该轮避免已知失败的沙箱 `gh` 路线，只审本地拟推送快照；线上状态由总控 readback。未有结构化结果前不能计有效复审。

## ds-flash 修订快照有效复审与表述精度修正

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
canary_status: match
warnings:
  - "[claude-code:unrecognized_model] deepseek-flash[1m]"
retry_class: none
```

- `issue198-pr197-r2-ds-flash-20260929-01` 进程 exit0、Claude JSON `subtype=success/is_error=false/terminal_reason=completed`、57 turns、canary `ds-flash-4f2da066` 逐字匹配，stderr 仅白名单提示、所有 shell 命令自身 exit0；artifact `/private/tmp/dayu-issue198-pr197-r2-dsflash/docs/reviews/issue-198-pr197-r2-dsflash-20260929.md`（SHA `9b45bd80...`）。锁相同两文件 diff SHA 与 fix artifact SHA，863 affected passed、owner 118 passed/94% coverage、全量 pyright0。
- **PR-R1/F1 低／accepted／已修复候选**：两侧对同一异常对象按修前/修后实现逐字节比对六组形态（深外部、混合、受信、无 traceback、格式化故障等），输出/截断/fallback 无漂移；61 个受信帧的 `Path.resolve` 由 183 次降为 48 次（3×16）。owner 测试在修前会因校验 27 帧而失败，非空断言。待 MiMo 同一修订快照有效第二路后最终关闭。
- **PR-R2/F1 低／accepted 文档精度纠正／已修复**：ds-flash 发现原总控文字把“所有 traceback 帧都做三次 resolve”写过宽。源码 `_safe_trace_frame` 对非 `dayu.*` 帧早退，实际 I/O 与**受信 Dayu 帧数量**成比例；总控已将上面两段判词校正，不改变 F1 真实动机或代码修复。残余为每个保留受信帧仍解析 source root 一次（最多 16 次），当前没有再优化证据。
- **PR-R1/F2 rejected-with-reason** 获独立确认：无 wildcard 消费者，显式导入与单真源成立。五处合并文件的 #198/O03/O20 语义均保留。MiMo 旧 head 首轮仍在途，PR gate 未过。
- MiMo 修订版独立 re-review `issue198-pr197-r2-mimo-20260929-01` 已在 `/private/tmp/dayu-issue198-pr197-r2-mimo` 经 preflight ok 派发 session `58835`，同样锁 HEAD `2219d40b` + 恰两文件 diff SHA `4dc7c5d7...`、fix artifact SHA `d0ad6713...`，隔离 venv 导入本 checkout；线上 PR 仍旧 head。MiMo 旧 head session `36532` 是另一独立任务，不能把它的结果算当前修订版复审；本轮未出结构化结果前 PR gate 未过。

## MiMo 旧 head 首轮结果与 PR body closing keyword

```yaml
setup_status: ok
agent_status: failed
tool_evidence: yes
canary_status: match
warnings:
  - "[claude-code:unrecognized_model] mimo-v2.6-pro[1m]"
retry_class: provider
```

- `issue198-pr197-mimo-20260929-01` 进程 exit0、Claude JSON `subtype=success/is_error=false/terminal_reason=completed`、108 turns、canary `mimo-3a964967` 匹配，stderr 仅白名单提示；artifact `/private/tmp/dayu-issue198-pr197-review-mimo/docs/reviews/issue-198-pr197-mimo-20260929.md`。内容无 material code finding，863 affected passed、O03/O20 owner 610 passed/2 skipped、全量 pyright0，五处合并面与 typed/unknown 语义均核实。
- 但 reviewer 自报初两次沙箱 `gh pr view` 因 keychain/TLS 失败，一次裸 `gh pr checks 197` exit1（无 checks 是预期状态，但未由 wrapper 捕获）；违反每条 shell 命令自身 exit0，且 failed tool event 非白名单。严格 `agent_status=failed`，内容只是待复核材料，不能抵作当前修订版第二有效路。MiMo 新版 session `58835` 避开该路线，仍在途。
- **PR-R1/F3 低／accepted／待修复**：PR body 目前把 closing keyword 写成反引号包裹的 `` `Closes #198` ``；GitHub 对 inline code 的自动关闭解析不应由我们猜。issue #198 的完整解决需 body 有明确普通文本 closing keyword，故改为独立普通文本行 `Closes #198` 并用线上 API 读回；用户仍自己 merge，不能提前 close issue。该项只改 PR body，不改代码或已有 review 快照。
- **PR-R1/F3 低／accepted／已修复**：`gh pr edit 197 --body-file` 将 closing keyword 移为独立普通文本行；随后线上读回 `headRefOid=2219d40b`、OPEN/draft、`body.splitlines().count('Closes #198')=1`、反引号形式 0。更直接的 GitHub GraphQL `closingIssuesReferences(first:10)` 返回 issue `198`，确认 GitHub 识别该 PR 的关闭关联；issue 仍 OPEN，只有用户 merge 后才会关闭。没有改代码或 review 快照。

## MiMo 修订快照有效复审与 PR review 总控裁决

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
canary_status: match
warnings:
  - "[claude-code:unrecognized_model] mimo-v2.6-pro[1m]"
retry_class: none
```

- `issue198-pr197-r2-mimo-20260929-01` 的进程 exit0；Claude JSON `subtype=success/is_error=false/terminal_reason=completed`、63 turns；canary `mimo-a2f0fb0c` 与独立 expected 逐字一致；stderr 只有上述白名单提示，review artifact 记录各 shell 命令自身 exit0。文件为 `docs/reviews/issue-198-pr197-r2-mimo-20260929.md`；审查快照与 ds-flash r2 一致：HEAD `2219d40b` 加恰两文件修订，`git diff --binary` SHA-256 `4dc7c5d779d5bd073a952c461809a61246dbea3eaaea76b12f9a062a09e4fab7`，fix artifact SHA-256 `d0ad6713c8bef521503e2ae2f06de4dd3d5e40d696c570d29ec3716c4e5d1c29`。独立验证 863 affected passed、owner 118 passed、`dayu/runtime/log.py` coverage 94%、pyright0。
- MiMo 对同一异常对象 A/B 比对七组输出逐字节一致，并用旧实现使新增 owner 测试精确失败、修后通过。总控复核 `dayu/runtime/log.py` 的收集/校验次序与测试断言，判 **PR-R1/F1 低／accepted／已修复**。外部帧在路径解析前早退；I/O 随受信 `dayu.*` 帧数增长的表述已经更正，**PR-R2/F1 低／accepted 文档精度纠正／已修复**。`__all__` 无 wildcard 消费，**PR-R1/F2 低／rejected-with-reason**；PR body 关联经 GraphQL 识别，**PR-R1/F3 低／accepted／已修复**。两路修订快照无新增 material finding，五处 O03/O20/#198 合并语义保留。
- 总控裁决 **PR review / re-review pass（本地拟提交快照）**。首轮 MiMo、ds-flash 的协议失败和 Sol fix 协议失败仍保留，不能算有效 gate；有效证据仅为两路 r2 与总控独立测试/代码核对。后续顺序：复制四份审查 artifact 和最新主队列，创建 accepted PR review commit，常规推送至 PR #197，线上读回 head/body/checks 后才可判 `draft-PR-pass`。本条不提前宣告线上已含修复或 final closeout。

## accepted PR review commit、final push 与 draft-PR-pass

- 四份 PR review artifact（含首轮两份协议失败的审查记录、r2 两份有效审查）和最新主队列已随两文件修复、F1 fix artifact、总控裁决一同选择性 stage；`git diff --cached --check` exit0。accepted PR review commit 为 `c37b71ee1a271e22c3a2330a0fb88bcd32f6aab4`，父提交 `2219d40b`，无强推。
- `git push github HEAD:refs/heads/codex/upload-material-oracle` 进程 exit0，报告远端 `2219d40b..c37b71ee`。同一输出中的**本地远端跟踪 ref** 更新因共享 `.git/refs/remotes/...lock` 权限失败；总控以独立 `git ls-remote` 和 `gh pr view` 核实真实远端/PR head 都是 `c37b71ee1a271e22c3a2330a0fb88bcd32f6aab4`。不能把跟踪 ref 错误误报为 push 失败，也不能把 exit0 单独当远端确认。
- 线上 PR #197 `OPEN/isDraft=true/base=main/mergeable=MERGEABLE`，`statusCheckRollup=[]`，故没有可宣称通过的 CI；PR body 唯一普通文本 `Closes #198`，GraphQL `closingIssuesReferences` 返回 OPEN issue #198。代码审查对象已进入线上 PR，用户保留 merge 权。**draft-PR-pass** 成立；下个 gate 是 final closeout，issue closeout comment 仍受额外授权约束，不提前记 final closeout pass。
