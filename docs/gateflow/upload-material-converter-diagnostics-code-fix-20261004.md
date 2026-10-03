# S1 C04 集中 code fix02

RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/gpt-6-sol

CANARY=gpt-6-sol-0fac7b0b

- 任务：upload-material-converter-diagnostics-code-fix-sol-20261004-02；时间：2026-10-03T23:35:43.653408+00:00。
- 唯一 workspace：/Users/leo/workspace/dayu-agent-r；branch：codex/upload-material-oracle；HEAD：8009ba4e100081fd1b56f64ddf5bc0c42a06e808。
- 当前范围：同一 S1 的 C04 code fix；修复与授权验证完成，待 root 裁决及同版 delta re-review。不是 slice/gate pass，未进入后 gate。
- source11 开闭完整 SHA、逐命令真实 wait/exit、raw 引用与保护校验见本轮独占 result.json；冻结02 manifest SHA 6c3eaf3004ccd4be95afb0b01c4ed5ffa42ee932149bb325010961e7da31c01f。
- accepted plan SHA cbd771224d4fc88bcafa6a03c8e786d4e1cef6dc22e15937ed38d7dc73461709；acceptance SHA 891bbce5671cc8e6cfa03ff40d8d169830f77a3b9181e5076e66241a437ec73c。MiMo正式报告 SHA 80e6ed9fc097c43d0b2f0f4a0347f03154e05bb2301f632de86dc357d594da0c；最新 root findings 最后 C04 为本轮裁决来源。

## 问题、owner 与改动

C04 是已接受的低严重度测试敏感度缺口。当前生产正确；普通 ValueError 从 body 穿过 scope 时必须同对象传播。现有156矩阵都有 cleanup 控制流，不能钉住健康清理时的传播。异常与资源回收语义 owner 是 capture_process_diagnostics；仅在其既有测试文件补合同，不改任何生产接口或生产代码。

唯一代码 delta 为 tests/runtime/test_process_diagnostics.py，当前 SHA 5403e8b493ac8305d981702a2963a17e3f0ffd374915b7db232167532f6b7188。新增 test_scope_preserves_ordinary_body_error_with_healthy_cleanup，以及模块私有 worker/真实打开观察函数。所有新增签名严格 typed，中文 docstring 包含参数、返回与异常；观察器仅调用原 _open_private 并保存原 BinaryIO 引用，不包装媒体、不替换清理、不注入故障。worker 仅进入一次真实 capture，父进程使用真实 spawn 和 join。

新增合同断言：caught is 原 ValueError；三真实文件句柄均关闭；共享 writer 槽清空；manager 原 loggerClass 精确恢复；所有进入前 logger filters 恢复；无 capture incident；一个 log 后 exact end，完整 JSONL newline；两fd原字节分别落 stdout.bin/stderr.bin；父 capfd 双流空。JSONL检查使用 bytes.split(b'\n')。没有扩展矩阵、兼容分支、生产 seam 或永久变异框架。

## 本轮真实验证

| 验证 | 实际终态 | 原件目录（相对仓库） |
|---|---|---|
| 激活 .venv 后完整 tests/runtime/test_process_diagnostics.py | exit0，196 passed，21.98s | workspace/tmp/upload-material-converter-diagnostics-20261003/code-fix-sol-02/affected-tests/ |
| 激活 .venv 后全仓 pyright | exit0，0 errors / 0 warnings / 0 informations | workspace/tmp/upload-material-converter-diagnostics-20261003/code-fix-sol-02/full-pyright/ |
| 同一新增测试、删除 explicit re-raise 的独占加载副本 | pytest exit1，1 failed；真实 child exit1 | workspace/tmp/upload-material-converter-diagnostics-20261003/code-fix-sol-02/deleted-raise-negative/ |

每条命令各自 O_EXCL 新建 stdout/stderr/command/wait-result 原件，由 Popen.wait 保存实际终态，再读取证据；没有复合命令覆盖验证失败。正例 proof same_object=true、closed_streams=3、logger_state_restored=true、footer_complete=true。

负例只删除 capture_process_diagnostics 的 scope_error=exc 后 explicit raise，唯一匹配一次（删除14字节）；副本 SHA c743228e2a3bf3f131c7c7104793006a1795a5cec1566f8de51dde60c687d18b。仅独占 scratch sitecustomize 加载此副本，父/worker加载身份均留 PID、path、SHA；同一新增测试文件没有变异。negative proof 在身份断言前已记录三句柄关闭、logger恢复、footer完整，但 same_object=false；随后 worker 在“ordinary body ValueError must propagate as the same object”断言失败，父测试从实际exit1失败。此失败来自异常被吞，不是 setup、媒体、超时或loader错误。工作树生产始终未暂改。

pyright额外提示有新版本，是工具版本通知；未更新环境。两个README标题搜索无匹配exit1已解释；负例exit1为预期。早期批量输出及旧result读取出现截断，后续按具体段落/键恢复必要信息，不以截断输出冒完整证据。原件和失败均保留，不重复probe。

## 继承验证与 README 决策

三生产 SHA保持 process=47ed4b45a44aed212fe440347488f8bd7eded30088c81a9f2f68e5ad61c12f3d、log=52ba9519fd7cc1f78fc9aad91160cc3230651e1ccbd10af800771b041b46ecef、converter=d8847701fc17c3f825afedb3c3138dabfa03e8050961545ee227819b22075864；其它十个候选均与冻结02相同。依本轮明确授权，继承 root 已核最后889的其它六测试文件、whole coverage 90.60/94.29/90.79且excluded=[]、fresh04真实PDF/XBRL/SIGINT原证据；未重跑昂贵验收，不把继承数据称本轮运行。

已读取 tests/README.md 开头职责、现有 process diagnostics 与覆盖率说明。单测试补既有异常传播/资源回收合同，没有新测试层级、运行方式或用户工作流；现文仍准确，无需扩写。其余README无本轮职责触发，不修改。所有README、其它测试、生产、控制、审查、旧证据、registry plan、锁文件以及.git/index保持原字节。

## 风险分类与停止

- fixed in current slice：C04补测及负例敏感度，actor修复已完成，re_review_verified=false，待root独裁。
- assigned to later work unit：独立registry登记，owner=root registry controller；用户延期的Win/Linux，owner=平台验收。
- requiring new issue or explicit user decision：Docling抽取质量及quota/daemon/非标准Logger/实时输出/全局序/更强raw保证，owner=上游或未来明确goal controller；均outside当前goal，分类继承，没有实现。

无blocking open question。未派子Agent；未stage/commit/push/PR/merge/issue/comment/newbranch/worktree/clone/reset/stash/clean；未查runner/ps/pgrep/kill0，未改main、.venv、.env、pip、locks或注册计划。按本轮停止条件交结构化result，停止；下一个入口仅由root决定同版单测试delta双route复审。

产物：workspace/tmp/upload-material-converter-diagnostics-20261003/code-fix-sol-02/result.json；完整差异：该目录 test-delta.diff。
