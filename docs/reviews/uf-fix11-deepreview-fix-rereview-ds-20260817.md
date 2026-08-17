# Code Review — UF-FIX11 aggregate deepreview fix 定向 re-review（DS）

## Scope

- Mode: current changes（finding 01 fix 定向 re-review）
- Branch: `codex/upload-filing-oracle`
- Base（对比对象）: HEAD `91dbf843` + 工作区未提交 fix diff
- Review 时间：2026-08-17
- Output file: `docs/reviews/uf-fix11-deepreview-fix-rereview-ds-20260817.md`
- 输入：
  - `docs/reviews/code-review-20260817-172506.md`（aggregate deepreview 输入之一）
  - `docs/reviews/uf-fix11-deepreview-projection-ds-20260817.md`（本 reviewer 的 finding 01）
  - `docs/gateflow/uf-fix11-deepreview-fix-20260817.md`（fix / self re-review artifact）
  - 工作区 2 个 tracked 文件 diff：`dayu/fins/pipelines/filing_upload_publication.py`、`tests/fins/test_filing_upload_publication.py`
- 定向核查项（controller 指定）：
  1. 唯一 predicate 同时供 arbitration/executor；
  2. 非法 combo 在 repository mutation 前 fail；
  3. outer rollback exactly once；
  4. 合法 keep/stage-preserve lifecycle 未变；
  5. 验证与 coverage 可信；
  6. 特别审查测试 `object.__setattr__` 注入 frozen request 是否属于合理 impossible-state drift injection，还是绕过 owner/invariant、应改为 monkeypatch validator 返回 `dataclasses.replace` 的 fresh request。

## 逐项结论

1. **唯一 predicate**：`关闭`。新增私有纯 predicate `_company_decision_allows_canonical_skip`（`filing_upload_publication.py:429-452`）唯一表达 `keep/no-intent | stage/preserve-published`。`_canonical_skip_requirements_are_met` 删除原内联规则并复用（479 行），arbitration 的两个 SKIP 判定点（stable 分支、MISSING→COMPLETE 分支）经该函数间接消费同一 predicate；SKIP executor 在 795-800 行直接消费同一 predicate。无第二处兼容性规则复制。
2. **非法 combo 在 mutation 前 fail**：`关闭`。predicate 检查（795 行）位于 `stage_upload_company_meta_decision`（808 行）、`batch_terminal_started = True`（814 行）与 `commit_batch`（815 行）之前；`batch_terminal_started` 在本分支此前从未置位，ValueError 抛出时 staging 零 mutation。新 owner test 断言 `events == ["rollback"]`、`company.stage_tokens == []`、`company.intents == []`、`batching.commit_tokens == []`、输入文件树与 bytes 无 publication side effect。
3. **outer rollback exactly once**：`关闭`。ValueError 抛出时 flag 仍 False → outer `finally`（846-851）走既有 `rollback_prepared_upload_batch` 恰一次；测试断言 `len(begin_tokens) == 1` 且 `rollback_tokens == begin_tokens`。修复前旧代码路径（无 predicate 检查 + recorder 返回 typed outcome）会把无合法 intent 的 commit 投影为成功 skip；fix artifact 的红测 `DID NOT RAISE ValueError` 与该代码路径逻辑一致，红测证据可信。
4. **合法 lifecycle 未变**：`关闭`。新增 `test_canonical_keep_skip_rolls_back_without_stage_or_commit` 断言 keep → skipped、commit 零调用、rollback 恰一次；既有 parametrize `test_metadata_only_skip_transfers_capability_and_projects_exact_outcome` 继续覆盖 stage/preserve 两条合法执行路径（name-only 与 alias-only）且实测全绿。predicate 对合法输入恒 True，未改变分支路由。
5. **验证与 coverage 可信**：`关闭`。实测复现：4 个定向测试 `5 passed`；全文件 `tests/fins/test_filing_upload_publication.py` `41 passed`，与 fix artifact 声称一致；combined `2158 passed, 1 skipped` 未重跑但与其声称边界一致（唯一 skip 为既有 Docling 环境条件）；branch coverage 84% ≥ 80% gate；pyright 0 errors；diff 边界符合冻结范围（仅 owner 生产文件 + owner 测试文件）。
6. **`object.__setattr__` 注入方式**：见 Findings 02-低——属于应改进的 owner/invariant 绕过，不属于合理 impossible-state injection。

## Findings

### 01-fix 复核结论

原 finding 01（SKIP 分支 disposition 判断不封闭、依赖 arbitration 远端不变量且无本地断言）的 root cause **已关闭**：唯一 predicate 同时供 arbitration 与 executor 消费，非法 combo 在 repository mutation 前 fail 且 rollback 恰一次，合法生命周期与 warning 语义零变化。不再作为未修复 finding 列出。

### 02-未修复-低-新测试用 `object.__setattr__` 绕过 frozen owner 构造校验注入 `company_meta_decision`，应改为 monkeypatch validator + `dataclasses.replace`

- **入口/函数**: `_force_skip_with_incompatible_company_decision`（测试 seam 注入 helper）
- **文件(行号)**: `tests/fins/test_filing_upload_publication.py:92-126`（`object.__setattr__` 在 115 行）；相关类型事实：`ValidatedFinsUploadFilingRequest` 为 `@dataclass(frozen=True, slots=True)`（`ingestion_runtime.py:761-762`），其 `__post_init__`（789-827）**不校验** `company_meta_decision` 字段组合
- **输入场景**: 测试需要构造 arbitration 漂移后的 impossible state：executor 收到 `FilingUploadPublicationDisposition.SKIP` 决策 + `company_meta_decision` 为 `skip/no-intent`
- **实际分支**: monkeypatch 的 arbitration seam 内对 executor 已产生的 frozen `fresh_request` 就地 `object.__setattr__` 篡改 `company_meta_decision`，绕过 frozen 机制与 `__post_init__`
- **预期行为**: 注入状态应由 owner 构造校验产生或等价于其产物——用 `dataclasses.replace(fresh_request, company_meta_decision=UploadCompanyMetaDecision(disposition="skip", company_meta_intent=None))`，或更忠实地 monkeypatch `publication_module.validate_fins_upload_filing_request` 包装真实 validator 后 replace 返回
- **实际行为**: 绕过 frozen owner invariant 直接写字段。当前测试断言不受影响（注入值是 typed 合法值，`__post_init__` 不校验该字段，setattr 与 replace 语义等价），但一旦未来 `__post_init__` 增加 company decision 组合校验（组合不变量的自然 owner 位置，例如校验 decision 与 resolved_action 一致），setattr 注入将静默绕过新校验，测试继续固化违反 owner invariant 的状态——违反本项目"测试必须断言 owner 级 contract 行为、禁止 fixture 绕过 owner/invariant"约束（AGENTS.md）
- **直接证据**: 115 行 `object.__setattr__(fresh_request, "company_meta_decision", ...)`；`ingestion_runtime.py:789-827` 的 `__post_init__` 无任何 `company_meta_decision` 校验；同文件既有两处 setattr 用例（1461、1505-1506）注入的是 `__post_init__` **显式拒绝**的状态（UNSAFE published state、repair 下 resolved_action=create），replace 根本无法构造、setattr 是唯一手段且带行内注释说明意图；本用例注入的值 replace 完全可以构造，且新 helper 无"为什么必须 setattr"的行内注释
- **影响**: 不影响本 fix 正确性（测试现在全绿、断言正确）；影响测试对 owner 校验演进的敏感度——未来 `__post_init__` 收紧时该测试会静默失去"状态通过 owner 校验"的语义，属低风险测试质量缺陷
- **建议改法和验证点**: 把 `_force_skip_with_incompatible_company_decision` 的 setattr 逻辑移除；改为在测试内 monkeypatch `publication_module.validate_fins_upload_filing_request`，包装真实 validator 后 `dataclasses.replace(fresh_request, company_meta_decision=UploadCompanyMetaDecision(disposition="skip", company_meta_intent=None))` 返回（`execute_prepared_filing_publication` 内部通过模块级名字调用 validator，seam 可行；`_execute_metadata_only_skip_fixture` 已走真实 execute 路径）。该模拟与真实漂移场景同构：validator owner 产生 skip decision（delete 场景真实存在），arbitration 演进后错误路由到 SKIP。保留全部现有断言（events/rollback/tokens/文件树）不变，验证 5 个定向测试仍全绿
- **修复风险（低）**: 仅改测试 seam；不改生产代码、不改变被测状态语义
- **严重程度（低）**: 修复正确性不受影响；属测试注入方式与 owner/invariant 关系问题

## Open Questions

无。

## Residual Risk

- 完整 combined regression（2158 passed）未在本 reviewer 处重跑；实测复现了 4 个定向测试与全 owner 文件（41 passed），与 fix artifact 声称一致。
- `docs/reviews/code-review-20260817-172506.md` 与本 reviewer 之外的另一路 aggregate findings（state-owner）未纳入本次定向复核范围，由 controller 汇总裁决。
- 02-低 若被 controller 接受，修复后需重新核对：注入路径不再触碰 frozen 对象、全部断言保持、全 owner 文件仍绿。

## Verdict

- Finding 01：root cause 已关闭，fix 接受。
- 新增 finding：02-低（测试注入方式），不 blocking。
- 总体：**PASS**（附 1 项低严重度测试质量 finding 供 controller 裁决）。
