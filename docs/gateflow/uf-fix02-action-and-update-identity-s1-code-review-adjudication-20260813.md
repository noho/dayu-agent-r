# UF-FIX02 action-and-update-identity — S1 Code Review Adjudication

## Gate context

- Gate：`S1 code review`
- Base：`56d159cb4bf13baf82858bb237b2f73075eaf717`
- Implementation：`docs/gateflow/uf-fix02-action-and-update-identity-s1-implementation-20260813.md`
- AgentMiMo：`docs/reviews/code-review-20260813-175624.md`，未发现实质性问题
- AgentDS：`docs/reviews/code-review-20260813-180034.md`，4 findings
- Controller decision：**FIX REQUIRED**
- Next gate：`fix`，随后双路 `re-review`

## Finding adjudication

### DS-01 material create-existing conflict — deferred-with-owner

- 状态：`deferred-with-owner`
- 判断：该分支是 baseline 已存在的 material 专用行为，不由 S1 diff 引入。当前 binding goal、oracle predicates、focused-real 都限定 `upload_filing`；approved plan 只授权 material 对 update-missing 与 deleted no-skip 的 shared-owner parity，并明确禁止新增 material typed usage、workflow 生产改动或 focused-real 扩面。
- 为什么不在当前 fix：删除 FILING guard 仍不能产生 filing 同形 typed usage；要闭合 reviewer 指出的投影差异，必须设计 material request validation 与 CLI/workflow public failure contract，属于新的用户可见行为与 owner 决策，不能借 S1 顺手实施。
- Owner / destination：`dayu.fins` upload_material action/public-failure contract；后续独立 `upload_material action-contract` work unit。当前 S1 artifact 必须补登记该 residual，不能宣称 material 全矩阵闭合。

### DS-02 duplicated canonical deleted reader — accepted

- 状态：`accepted`
- 判断：`is_deleted` 是 storage-published source meta 的 canonical business fact；snapshot 与 upload skip 两个消费者不应各自拥有逐字相同的字段存在性、类型与错误文案规则。项目明确要求多个消费者复用同一 source of truth/public contract/helper。
- 修复方向：在 `dayu.fins.storage` 公共 contract boundary 提取一个严格 typed helper，由 `_fs_source_snapshot.py` 与 `docling_upload_service.py` 共同复用；删除两份 private duplicate reader。不得用默认值、loose bool、compat re-export 或上层 fallback。
- 边界：`ingestion_runtime.py:5102` 的既有 loose read 不在本调用链，继续归 `UF-FIX08`；本 fix 不扩 existing-source auto repair。

### DS-03 CLI update projection regression gap — accepted

- 状态：`accepted`
- 判断：旧 fixture 虽错误依赖 missing-update upsert，但也承担了 `--action update --overwrite` 到 Service typed request 的成功投影覆盖；迁移为 create 后该覆盖确实消失。
- 修复方向：以真实 seeded existing filing state 增加 `update` 与 `update + overwrite` 成功 handoff tests，断言 Service 收到正确 action/overwrite；不得放宽 missing-update conflict tests。

### DS-04 prepare_upload Raises docstring — accepted

- 状态：`accepted`
- 判断：S1 新增 corruption fail-closed `KeyError/ValueError` 路径，公共函数 docstring 必须完整登记。
- 修复方向：补充 source meta corruption 的 `KeyError` 与 `ValueError` 异常说明，不改变运行时行为。

## Residual risk classification

- S2 complete-set replacement 与 `_resolve_upsert_mode` 删除：covered by later approved slice S2。
- material create-existing typed admission：后续独立 `upload_material action-contract` WU。
- loose deleted reader / corruption repair：UF-FIX08。
- same-request concurrency：UF-FIX10。
- 无未分类 residual risk，无 blocking user question。
