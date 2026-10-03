# S2 US2-R01：同时放行的真实旧受理并发出现提前冲突

## 即时登记与裁决

US2-R01：**needs-more-evidence / 未修复**，阻塞当前 S2 放行；并非新业务规则或新 slice/gate。唯一 workspace `/Users/leo/workspace/dayu-agent-r`、分支 `codex/upload-material-oracle`、HEAD `f7e60c9d3e4c6e77a6c2abf18d09cd8020c19235`。仍以已裁 O33 和 C01 的唯一公司 owner 等价 no-op 为边界。

总控直接读取本轮 `workspace/tmp/upload-material-unified-s2-final-completion-sol-20261003-01/race-final-06/` 的 ready、各自双流、trace，以及 `race-final-06-run/{stderr.txt,actual-exit.json}`。A PID 37815 与 B PID 37816 实际均观察同一 MISSING/revisionNone/companyNone、同 canonical ID/form/name 后同时放行；A actual exit1，观测到 source_publication_conflict/null 发布事实，父采集器因 assert code==0 提前进入 finally，B 被终止为 -15。所以不能把该轮当双 CLI 验收通过，也不能将有据的产品冲突归为普通状态文本采集器错误。B 未正常终态、失败的确切原始 raise 分支尚需补直接证据；不凭相邻代码猜根因。

已有顺序放行 race-final-02/03/04/05 的通过证据保留，但不能覆盖这个真实更窄窗口。该窗口属于既有“同旧受理的相同 auto/non-overwrite 请求、严格等价公司 owner 与材料竞争”目标，不是额外强化验收。

## 当前实施的必要调查与最窄修复授权

当前 runner 按 root 新裁决文件读取约定同轮处理：

1. 全新独占探针 label/base，两个已知 owned Popen 都 wait 实际终态，首个非零不提前终止另一个合法请求；bounded timeout 后才依其 own handle 收敛。保留原失败和资源 tracker warning，不覆票据，不用 ps/pgrep。
2. 保存 debug/source-correlated 原始 cause/raise 路径；必要技术包装仅暂停真实 owner/记录入口与异常原样 re-raise，不改请求、结果、仓储、converter 或生产 hook。补证明是否在公司阶段两次独立读/validate 之间合法等价公司或材料发布被误判漂移。
3. 严格按同一 cause 修复 owner。C01 initial None 的同意图当前等价例外必须由公司 writer/identity guard 下的真实 commit-time merge/no-op 判定；已有公司仍严格 snapshot/time/aliases，材料候选相同性仍由现有 pure arbiter 和材料 writer/final guard 负责。优先复用现有 writer 内同版 read 与 company intent owner，不增加第二套锁/状态机、不可观测历史、generic-conflict catch/re-read/retry、publication 层名字/时间猜测、optional repository 或新失败 code。新修复在现有白名单内按既有合同已授权；根因证据不足时先补必要同路径证据，不直接照猜想修分支。
4. 修复后，同版真实顺序/同时放行两种旧受理探针与必要 owner 失败回归、pyright、逐文件覆盖率恢复；不能从旧版本通过直接推新版本通过。正式双审仍只在全 S2 完成后，R01 要由 root 实证裁 accepted/rejected 后回写最终状态。

目前在途 session32721，不重派、不宣布终态或 S2 pass。其它独立最终验证继续；此新增发现必须在本轮最终报告前读取、处置和保留。
