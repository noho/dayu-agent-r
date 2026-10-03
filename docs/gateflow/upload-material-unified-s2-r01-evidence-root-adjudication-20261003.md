# S2 R01 同路径根因补证裁决

## 范围与状态

同一 WU、同一 S2，HEAD `f7e60c9d3e4c6e77a6c2abf18d09cd8020c19235`。本记录补充 R01 原即时记录，不覆盖失败票据。作者报告 US2-F08 与 root US2-R01 是同一项，不重复计数。裁决 **accepted**；候选修复已观察到，最终状态仍待完整同版验证及既定双路 code review，不宣布 S2 pass。

## 直接证据与唯一 owner

总控实际读取 `workspace/tmp/upload-material-unified-s2-final-completion-sol-20261003-01/company-race-root-cause/stdout.txt`：真实公司竞争提交插入 A 的读与后续 validate 之间，原 traceback 为 `execute_material_upload_company_stage → validate_material_upload_state → _require_material_state_matches`，实际 `fresh.company_meta` 已有同意图公司，`expected_company_meta=None`，抛出 `CompanyMetaConcurrentUpdateError`，再包装 typed conflict。此证据证明 C01 initial None 的同意图提交尚未到唯一公司 commit owner 就被分离的缺席检查误拒。

当前最窄候选移除 initial None 的分离缺席 validate，已有公司观察仍严格 validate；公司 writer 内按既有 C01 当前等价 merge/no-op 判定。未增加 generic conflict catch/re-read/retry、历史推断或新状态机。`company-race-fixed` 实际 76 pass，原失败票据保持。最终批准还需审查该提交 owner 与全链的同版实现。

总控另实际读取 `race-final-11/result.json`（顺序）及 `race-final-12/{result.json,trace.json,gate/a.ready.json,durable-query.json}`：顺序一 ok 一 skipped，winner→loser 业务差异为空；同时放行两 PID 39546/39547 均 actual0、一 ok 一 skipped、共同旧 MISSING/companyNone、已恢复包装、实际零 job 文件。并发轮没有可观测的提交后/另一方前快照，`business_diff=null` 如实记录，不冒称该轮单独证明差异为空；顺序轮负责这一成功信号。原 race-final-06 的非零及被中止 B 保留。

## 同路径公共错误文案登记

关联修复项 US2-R01-M：**accepted / 候选已改、待双审**。原根因 traceback 实际对材料返回“目标 filing”；该文案由 `dayu/fins/upload_failure.py` 唯一 failure owner 产生。沿既定材料 typed reason/filing 保原行为边界，允许显式 required `source_kind` 在此 owner 选择材料或 filing 文案，迁移真实调用者；保 code/kind/schema 与 filing 原文，不在 UI 改写、不给默认类型、不增新错误分类。这是当前材料失败投影的修复，不是新业务规则、slice 或额外 gate。

## 后续入口

当前实施 runner 32721 在途，继续完整 S2 收尾；最终 pyright、覆盖率与候选源版本必须一致。所有 slices 完成前不执行正式 PR review；修复 WU closeout 后再另行完整 upload_material CLI CI 和 oracle/scenario 登记。
