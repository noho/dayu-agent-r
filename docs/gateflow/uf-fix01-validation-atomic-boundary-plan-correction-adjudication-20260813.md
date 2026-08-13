# UF-FIX01 validation-atomic-boundary — Plan Correction Adjudication

## 1. Gate context

- **baseline accepted plan commit**：`5031ec6b7b7d53a41fe9fb1fc41b5b393260dfbd`
- **correction target**：`docs/gateflow/uf-fix01-validation-atomic-boundary-plan-correction-20260813.md`
- **gate**：implementation S1 blocked → factual plan correction review
- **Controller decision**：**PASS**

本次 correction 只修正 accepted plan 对三个既有代码事实的误判：absent identity locator 的真实行为、
SEC/CN pipeline fallback repository set 的 eager construction、以及 complete source fixture 的非空文件约束。
目标、语义 owner、公开 storage protocol、事务边界与 non-goals 均未改变，因此不重新打开 goal confirmation。

## 2. Independent review evidence

| Reviewer | Artifact | Result | Material findings |
| --- | --- | --- | --- |
| AgentMiMo | `docs/reviews/plan-review-20260813-correction-mimo.md` | PASS | 无 |
| AgentDS | `docs/reviews/plan-review-20260813-correction-agentds.md` | PASS | 1 项限界内待核对 factory 参数 |

两路均独立确认：

1. private tri-state helper 仍位于 storage identity/ticker owner 内，不把裸路径存在性判断泄漏给 CLI、service
   或 pipeline；absent 在 guard/mkdir 前返回，corrupt identity 继续 fail closed。
2. `create_directories=False` 是消除 constructor eager mutation 的最小变更，不需要新增 public API、wrapper
   或兼容 seam；首次真实写仍由 batch/repository owner 建目录。
3. snapshot owner tests 必须发布至少一个真实业务文件，不能用 `files=[]` 绕过 complete-source contract。
4. correction 不触及 action/date/year/format、converter capability、Host/Engine、frozen evidence 或 UF-FIX09
   shared interruptible Docling converter。

## 3. Controller finding adjudication

### DS finding：factory 是否真正支持并透传 `create_directories`

**结论：CLOSED。** Controller 直接读取
`dayu/fins/storage/_fs_repository_factory.py::build_fs_repository_set`：

- signature 已有 `create_directories: bool = True`；
- 构造 `FsStorageCore` 时传入 `create_directories=create_directories`；
- 仅在该值为 `True` 时调用 `core.ensure_batch_recovery()`。

因此 plan 不需要修改 factory、不需要新增 wrapper，也没有未覆盖的架构问题。S1 owner tests 仍需验证全量 concrete
repositories 已注入时不会构造未使用的 eager set，以及首次 begin/write 仍建立所需 infrastructure。

## 4. Agent fallback record

AgentDS 原 review turn 在完成探索后未于合理时间内写 artifact，多次 steer 也未收口。Controller 按 Gateflow agent
fallback 执行 interrupt、重新 discovery、`/clear`，并以同一冻结 correction plan 重派严格限界的独立
`/planreview`：禁止子 agent、扩散检索、生产代码修改与提交。最终 DS artifact 独立生成；MiMo 结论未被用作
第二路替代。

## 5. Gate decision

Plan correction gate **PASS**。允许创建 local-only correction checkpoint commit，并从 S1 重新进入
implementation gate。继续适用既有授权：不得创建 PR、push、切分支、更新 main；仅在 goal/owner 变化、现有
确认无法覆盖的架构问题或真实 blocker 时停止请求用户裁决。
