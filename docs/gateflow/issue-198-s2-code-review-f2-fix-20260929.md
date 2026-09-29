# Issue #198 S2-R1/F2 根 README 排障说明落位修复

- 范围：只改根 `README.md`，新增本记录；未改产品代码、测试、其它 README 或既有 gate/review 文档，也未提交、推送或创建 PR。
- 预检：HEAD 为 `7234d42dbaea603112c6fed52776281228d261a7`；改前 11 个 tracked 文件的 `git diff --binary` SHA-256 为 `d53e67f29e26c6d835c42ea81ce43aef34a27cf831959ee685c1802b42df14c5`，均与派发值一致。

## F2 根因与改动

根 README 面向最终用户。原 §5.2 上传终态摘要长段附带了通用财报命令外层未知错误的日志操作，以及下载 EXECUTION 失败提示和未知异常安全诊断范围。下载用户在 §5.1 读不到后两项；上传段也混入下载语义。`dayu/cli/output.py` 的 `CLI_LOG_LOCATION_HINT` 是固定提示真源，下载失败详情只在公共失败分类为 EXECUTION 时追加该提示；`dayu/cli/commands/fins.py` 的财报命令外层错误复用它。问题在用户手册的章节落位，不在产品投影代码。

- §3.1 全局日志参数旁说明财报命令外层未知内部错误的固定 stderr 提示，以及为 `--log-file PATH` 选择可写文件、重新执行并留存日志的操作。
- §5.1 现有 `storage/unsafe_publication` 修复句之后，说明下载 EXECUTION 失败详情后追加同一提示，并在下载章节直接给出可执行的日志留档操作。明确并非每次 EXECUTION 都产生未知异常诊断；下载未知异常的安全诊断只提供脱敏类型标签和有界包内位置，不含原始异常消息或路径；普通运行日志仍可能包含用户路径。
- §5.2 上传终态摘要只保留上传文件数、失败与 stderr 原因说明，移除通用和下载专属排障句。

## 审查裁决与验证

- S2-R1/F1 是当时真实 CLI 的验证缺口，由总控在当前 S2 候选上取得 fresh CNInfo→Docling→manifest 发布、同请求 typed storage 失败、清除后恢复的证据，见 `issue-198-s2-cli-fresh-evidence-20260929.md`。精确单日窗口仍为 0 候选；本轮没有运行真实下载，也没有将 F1 作为代码修复。
- S2-R1/F3 已由总控 `rejected-with-reason`：abort 后的安全日志仍记录真实异常事实，不承诺失败 RESULT 已投递；本轮不改日志条件或终态契约。MiMo 审查未提出新的当前切片代码修复项，其协议失败仍需新同版审查。
- 独立 Python 字面检查按 §3.1、§5.1、§5.2 标题切段，8 项均为 PASS：固定提示及留档操作只在通用段；下载段同时含 storage 恢复、EXECUTION 提示、可独立执行的日志操作、诊断范围与普通日志路径边界；上传段无下载专属句。逐字核对 §5.2 上传摘要段没有 `--log-file PATH`、下载失败详情、下载未知异常或 EXECUTION 分类句。
- `git diff --check` 退出 0；`git diff --binary -- README.md` SHA-256 为 `b3a4f9ad77c5c458f899cf2817feb8a7ae5e7025385d7fe315def617c1ce97e2`。只编辑文档，未运行 pytest、pyright 或真实 CLI；现有产品/测试验证及 fresh CLI 证据属于先前 S2 候选，不能记作本轮新执行。

## 残余与下一 gate

本轮只关闭文档落位 F2；F1 的 fresh 证据仍需总控组织新 SHA 的同版复审并裁决，原单日发现缺口属于独立 CNInfo work unit。其它已登记独立残余不纳入本修复。下一 gate 是以修订后的 README diff 为同一快照，完成 ds-flash 与 MiMo 两路有效 code re-review 和总控裁决；通过前不窄提交 S2。
