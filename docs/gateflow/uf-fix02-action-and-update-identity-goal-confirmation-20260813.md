# UF-FIX02 action-and-update-identity — Goal Confirmation

## Gate context

- Work unit：`UF-FIX02 action-and-update-identity`
- 类型：bug fix / architecture-sensitive behavior correction
- 分支：`codex/upload-filing-oracle`
- 起点：`114430ce312ca6d8eb9c9f4cb7bb0a1f0bdba5a0`
- Decision：**PASS**
- Next gate：`plan`
- External policy：local-only；禁止 PR、push、切换或更新 `main`、merge 与远端更新。

## Preflight evidence

- 当前 HEAD 精确等于冻结起点。
- `git status --short` 为空。
- `MERGE_HEAD`、`CHERRY_PICK_HEAD`、`REVERT_HEAD` 均不存在，rebase 不在进行中。
- 本地 `main=256786b255021ee429a20f22aad726b1ad33916c`，且 `git merge-base --is-ancestor main HEAD` 返回成功；`main` 可 fast-forward 到当前分支。

## First-principles judgment and direct evidence

问题真实存在且严重性评估正确：

1. `dayu/fins/pipelines/docling_upload_service.py::evaluate_upload_overwrite_precondition` 仅在 `overwrite=False` 时把 explicit update missing 判为 `UPDATE_TARGET_MISSING`。
2. 同模块 `_resolve_upsert_mode` 明确把 `update + previous_meta=None + overwrite=True` 解析为 `create`，把 explicit update 错误地变成 upsert。
3. 同模块 `resolve_upload_action` 只按 `previous_meta is None` 区分 auto create/update，不识别 logical deleted state；`_can_skip_upload` 只比较 fingerprint 与 overwrite，不检查 `is_deleted`，因此 deleted source 可被成功 skip 而仍 deleted。
4. `_store_upload_assets` 只在 `overwrite=True` 时重置完整 source document；普通 update 直接向同一 document identity 写新 blob 后替换 meta file entries，输入改名时旧业务文件可能留在存储目录。
5. `ValidatedFinsUploadFilingRequest.document_id` 与 `FilingUploadStateRepositoryProtocol.read_filing_upload_state(ticker, document_id)` 已提供 filing identity 与 fresh published-state 真源；SEC/CN workflow 均在转换前重新读取 state 并重新调用 owner validator，因此应在这些既有 owner boundary 修复，而不是在 CLI、Service、basename/stem 或异常字符串上补偿。
6. `docs/engine/design.md` 明确 Engine 不拥有财报业务语义或仓储访问；`docs/host/design.md` 的 Host owner 也不承担 filing action resolution。修复归属 `dayu.fins` action/validation owner 与 `dayu.fins.storage` public repository/batch publication boundary。

## Binding scope contract

### Goal / motivation

- update 对象只由稳定 filing identity 决定，不由输入 basename/stem 决定。
- explicit update 无论 overwrite 值都要求 published target 存在；overwrite 不得把 update 变成 upsert。
- auto 对 logical deleted source 且给出完整输入时恢复或重建可用 source。
- 同一 filing 的改名 update 以 old-or-new 原子方式替换完整文件集合并移除旧业务文件。
- fresh published state 可判定的 create-existing/update-missing 冲突在 Docling conversion 前 fail closed；并发 fresh recheck 丢弃 stale preflight action。
- 保持 UF-FIX01 的 typed validation、fresh authoritative workflow、零 mutation、atomic batch、bounded stderr、cancellation contracts。

### Success signals

- 冻结 predicates `upload_filing.action-core`、`upload_filing.renamed-update`、`upload_filing.auto-after-delete` 通过。
- owner-contract tests 先失败后修复，覆盖同名/改名 update、update missing ± overwrite、deleted 后 auto、existing pre-conversion conflict 与 stale preflight action。
- UF-PF02 使用真实 `dayu-cli`，无 mock/fake，并保存独立 evidence root、manifest、report、digest、secret scan，以及屏幕/输出/文件/日志/DB/Trace/public repository/integrity 观测。
- 受影响测试通过；逐修改生产文件 coverage ≥80%；完整 pyright 无新增或扩散错误；README trigger 与 diff/static audit 完成。

### Non-goals / scope boundary

- 不处理 UF-FIX03–UF-FIX08、UF-FIX10、UF-FIX11、UF-PF03–UF-PF12。
- 不顺手修改 summary/count、calendar/year、alias、format/XBRL、multi-file primary/collision、integrity auto repair、same-request concurrency、company warning。
- 不修改冻结第一轮 evidence；不刷新 oracle/scenario registry。
- 不引入补偿删除、字符串异常分类、compat shim、lazy import、下游 fallback。
- 财报存取只能通过 `dayu.fins.storage` public repository/protocol。

### Minimality

不新增跨层 identity registry，不把业务 action 规则复制到 CLI/Service，不扩展 Engine/Host 职责。优先收敛既有 action/precondition owner、typed validation、fresh recheck 与 batch publication 的语义，使所有消费者复用同一真源。

## Blocking open questions

无。用户已明确“继续下一个”并授权 goal confirmation 后自动推进。
