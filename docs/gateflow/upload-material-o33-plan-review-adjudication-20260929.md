# UM-O33-F01 条件性 plan 总控预审裁决

`o33-plan-sol-20260929-01` 预检 `setup_status=ok`、显式 `/private/tmp/dayu-upload-o33`、独立 output/stderr/last-message，process exit0、JSONL `turn.completed`、canary `gpt-6-sol-534bbf5e`、stderr 空；三个探测/复合命令 exit1，严格 `agent_status=failed`。总控仅把独立实读的 plan SHA `7b40e03cc857071c0172688eafa759fa3b9a388e7072cc452275262011b50906` 当候选，未实施产品/测试/README，也没有通过 plan review。

## C1 blocking：O34 独立公司事实与单 batch 假设冲突

Sol 编制时只看旧 O12 候选，将“公司 decision、source mutation/skip 共用一个 batch/一次 commit”和“败者不发布本请求公司半状态”写成硬前提；本次总控已核对主工作区用户已接受的 `docs/reviews/upload-material-um-o34-oracle-adjudication.md`：合法公司 meta 在 material 转换失败或取消后可独立保留，缺文档 manifest 不算文档成功。O12 的单 batch 候选已在其 adjudication 因此被阻断，不能成为 O33 goal 或 plan 的默认事实。隔离 goal 已同步主工作区更正，加入 O34 边界；本候选 plan 未同步，**不可进入 reviewer pass/实施**。

修复方向：Sol 只修计划，使依赖写为 O12 最终**材料发布**同版 guard 和公司决策，而不预设公司/材料同 batch。并发败者 skip 时材料 meta/manifest/资产零业务 diff；公司有合法独立更新意图时是否已经按 O34 提交，须消费 O12 最终分阶段合同并在 summary 中如实表示，不能为制造“全命令零副作用”回滚公司或误称半发布。材料 target 的权威相同性裁决仍只能在 storage guard 下同版证明，不放宽损坏/不同指纹/alias 漂移。O12/O14/O15 最终计划与代码未集成前保留 conditional，不预造函数签名。

## C2 证据输入与依赖核对

Sol 报告“本 checkout 没有 O33 oracle / O14/O15 计划”，因为 `docs/reviews/upload-material-um-o33-oracle-adjudication.md` 在主工作区未跟踪、隔离基线未含；O14/O15 合并计划实际在 `/private/tmp/dayu-upload-state/docs/gateflow/upload-material-state-plan-20260929.md`。总控已把 O33 oracle 复制进隔离 checkout；下一 Sol fix 须实读该文件、合并 state 计划以及最新 O12/O14 adjudication，纠正 plan 首段过时的“缺文件”说明。外部计划仍是候选，不把其 API 当集成 HEAD。若任何依赖核对仍不完整，停止并报告确切路径/原因。

## C3 发布确定性边界

计划将“post-commit 不确定 typed 语义”列为 O33 硬依赖是正确的 fail-closed 方向，但当前 `fins-download-indeterminate-publication-state` 是另一个待 goal 的 download/company storage WU。O33 不能要求它已完成才能规划相同已确认目标的窄竞争；须把“若当前材料 commit 可能已 swap 而 outcome 不确定，则禁止 skip 并保持既有 operational/typed 不确定结果，若公开合同不足则停回 owner”写清，不擅造 O33 public status 或借其它 WU 已集成之名。实施前再与 storage publication certainty 真源对账。

下一步 Sol 仅修 O33 plan，随后 Kimi/MiMo 有效同版 plan review；产品未实施，依赖未就绪。

## Sol 修订候选与总控独立核对（2026-09-29）

`o33-plan-fix-sol-20260929-01` 预检 ok、显式绝对 cwd、独立 output/stderr/last-message；进程 exit0、JSONL 有 `turn.completed`、canary `gpt-6-sol-ee2a35e0` 逐字匹配，但一条 Python 替换命令 exit1，stderr 又有非白名单 `apply_patch verification failed`，按严格协议 **agent_status=failed**。总控独立实读计划 SHA-256 `2ea0660f2ac5a8a5868f97bd1f2788f41e0474069f0b0011ceca763c08ad5249`：C1/C2 的 O34 公司独立事实、O14/O15 合并计划路径及未集成合同都已写明；C3 的材料提交已可能 swap/结果不确定时禁止 skip、分类不足回 owner 也已写明。当前候选只能作为后续 Kimi/MiMo 同版复审输入，不能计 plan gate pass；O12/O14/O15/O04/O23/O25/O13 实施依赖仍缺，产品未实施。
