# UF-FIX01 validation-atomic-boundary — Plan Gate Adjudication

## 1. Gate metadata

- **work unit**：`UF-FIX01 validation-atomic-boundary`
- **gate**：plan
- **Controller**：AgentController
- **branch**：`codex/upload-filing-oracle`
- **baseline HEAD**：`b3cb1f1b16f4d552eb762de3be59dc75c7586ab6`
- **decision**：`pass`
- **next gate**：accepted-plan checkpoint commit 后进入 implementation
- **external operations**：本 WU 禁止 PR、push、main 更新

## 2. Adjudicated artifacts

- Plan：`docs/gateflow/uf-fix01-validation-atomic-boundary-plan-20260813.md`
- Plan fix：`docs/gateflow/uf-fix01-validation-atomic-boundary-plan-fix-20260813.md`
- AgentMiMo initial review：`docs/reviews/plan-review-20260813-093247.md`
- AgentDS initial review：`docs/reviews/plan-review-20260813-094750-agentds.md`
- AgentDS fallback 说明：第一次 review turn 在完成探索后未能合理收口；Controller 按 Gateflow fallback
  中断、重新 discovery/clear，并以同一冻结 plan 严格限界重派。第二次 turn 未启动子 agent，产出了独立 artifact；
  未以 MiMo 单路替代。
- AgentMiMo re-review：`docs/reviews/plan-review-20260813-101232-rereview-mimo.md`
- AgentDS re-review：`docs/reviews/plan-review-20260813-101207-rereview-agentds.md`
- AgentDS R-DS1 delta：`docs/reviews/plan-review-20260813-101854-rereview-agentds-rds1.md`
- AgentMiMo C-01 delta：`docs/reviews/plan-review-20260813-102155-rereview-mimo-c01.md`

## 3. Finding adjudication

| Finding | Controller decision | Final state | Plan location |
| --- | --- | --- | --- |
| MiMo F01 / DS-08 | accepted | closed | §6.3、S1：canonical-root absent 在 guard 前短路，零目录/锁 |
| MiMo F02 | accepted | closed | §6.1、S2：23-member closed code 与 frozen scenario exact mapping |
| MiMo F03 | accepted | closed | §6.4、S1：download/preprocess/job lazy-bootstrap 回归矩阵 |
| MiMo F04 | accepted | closed | §6.1、S2：唯一 `render_cli_error` 路径与 exact stderr |
| DS-01 | accepted | closed | §6.1、§7：pure validator 与 concrete workspace assembly 唯一归属 |
| DS-02 | accepted | closed | §7、S3：service runtime → SEC/CN/HK repository 注入链 |
| DS-03 | accepted | closed | §6.2.1、S2/S3：validated handoff 与 authoritative recheck |
| DS-04 | accepted | closed | §6.5、§7：action/overwrite pure helper 唯一 owner |
| DS-05 | accepted | closed | S3：company-stage/delete-stage failure rollback evidence |
| DS-06 | accepted | closed | S3：UF-FIX09 composition owner regression |
| DS-07 | accepted | closed | §6.1、S2：typed usage catch 在 generic catch 前 |
| R-DS1 | accepted | closed | §6.1、S2：四个 basename-bearing file codes 与 exact messages |
| C-01 | accepted | closed | §3、§13：本地 commits 必需；PR/push/main 明确禁止 |
| AgentDS Q2 | rejected with evidence | closed | `build_fs_repository_set` 已有并透传 `create_directories`，无需改 factory |
| AgentDS Q1/Q3/Q4 | accepted for specification | resolved | §6.5、§6.3/S3、§6.2.1 |

无 deferred finding，无 unclassified residual risk，无 blocking open question。

## 4. Accepted owner model

1. `dayu.fins.ingestion_runtime` 的 typed filing request/validator 是可预判 usage 语义与 typed public
   failure/result 的唯一真源；workspace concrete preflight assembly 仅属于 `dayu.fins.service_runtime`。
2. CLI 只拥有 syntax、在 service factory/bootstrap 前调用 preflight、渲染 typed reason 和 exit mapping；
   不读取 storage、不拼业务路径、不按异常字符串重分类。
3. `dayu.fins.storage` 的 pure filing publication snapshot protocol 是 company/source published state 的唯一读边界；
   fresh absent 在任何 lock/mkdir 前返回。
4. SEC 与 CN/HK filing 的 caller-owned publication unit 使用同一个 `BatchToken` stage company/source；
   `BatchingRepositoryProtocol` 继续拥有 commit/rollback capability lifecycle。
5. `DoclingUploadService` 继续拥有 action/overwrite/prepare/skip/delete/cancel/commit linearization；
   UF-FIX09 shared interruptible converter 的 construction、identity 与 cancellation semantics 不变。

## 5. Scope and proof decision

- 保持 UF-FIX02–08、UF-FIX10、UF-FIX11、UF-PF12、date/year domain 与 format allow-list 漂移在非目标。
- 不修改 Host/Engine、frozen evidence 或 registry finding/rerun 状态。
- Implementation 必须按 S1–S5 小切片把 owner tests 与生产改动放在一起，完成受影响测试、完整 pyright、
  单文件覆盖率目标与 README trigger audit。
- Final validation 必须运行无 mock/fake 的 UF-PF01 focused-real matrix，并保存 exact argv、streams、exit、
  before/after tree、durable artifacts 与 SHA-256；不得提前运行 UF-PF12。

## 6. Gate decision

AgentMiMo 最终 re-review 为 `pass`；AgentDS 原 findings 全部关闭，R-DS1 final delta 为 `pass`；
Controller C-01 delta 为 `pass`。计划已达到 code-generation-ready，目标与 owner 未变化，不需要用户追加裁决。

**Plan gate：PASS。** 使用固定 commit message
`gateflow: accept plan for validation-atomic-boundary` 创建本地 checkpoint 后，自动进入 implementation gate。
