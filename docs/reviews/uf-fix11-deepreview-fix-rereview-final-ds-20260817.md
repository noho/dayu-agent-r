# Code Review — UF-FIX11 aggregate deepreview fix 最终定向 re-review（DS）

## Scope

- Mode: current changes（finding 02 test-seam fix 定向 re-review）
- Branch: `codex/upload-filing-oracle`
- Base（对比对象）: HEAD `91dbf843` + 工作区未提交 fix diff
- Review 时间：2026-08-17
- Output file: `docs/reviews/uf-fix11-deepreview-fix-rereview-final-ds-20260817.md`
- 输入：
  - 最新 `tests/fins/test_filing_upload_publication.py` 工作区 diff
  - 更新后的 `docs/gateflow/uf-fix11-deepreview-fix-20260817.md`（含 "Finding 02 rereview test seam" 章节）
  - 上一轮本 reviewer 的 `docs/reviews/uf-fix11-deepreview-fix-rereview-ds-20260817.md`
- 定向核查项（controller 指定）：
  1. validator wrapper 调用真实 validator 后 `dataclasses.replace` 构造合法 frozen request；
  2. arbitration helper 只返回 SKIP；
  3. 不再有本用例 `object.__setattr__`；
  4. 红测能力、零 stage/commit、begin1/rollback exactly once/durable zero 断言未弱化；
  5. 类型/docstring/fixture owner 合理。

## 逐项结论

1. **validator wrapper + replace**：`关闭`。`_validate_with_incompatible_company_decision`（test 文件 92-118 行）先调用测试文件已导入的真实 `validate_fins_upload_filing_request(request, published_state=published_state)`——签名与生产 owner 完全一致（`ingestion_runtime.py:1451-1456`，keyword-only `published_state`）——再 `replace(fresh_request, company_meta_decision=UploadCompanyMetaDecision("skip", None))`。`replace` 对 `@dataclass(frozen=True, slots=True)` 走 `__init__` → `__post_init__` 全量 owner 构造校验，产出合法 frozen request；`UploadCompanyMetaDecision("skip", None)` 位置参数与字段顺序 `(disposition, company_meta_intent)` 一致且 typed 合法（`disposition` Literal 含 `"skip"`）；`replace` 已在文件第 5 行 import。
2. **arbitration helper 只返回 SKIP**：`关闭`。`_force_skip_publication_decision`（120-148 行）对全部入参 `del`，只构造返回 `FilingUploadPublicationDecision(disposition=SKIP, publish_mode=None, failure_reason=None)`，不再读取或修改 request。
3. **本用例 `object.__setattr__` 已移除**：`关闭`。新增代码零 `setattr`；文件剩余 3 处 `object.__setattr__`（1483、1527-1528）均为 UF-FIX10 既有 owner 用例——注入的是 `__post_init__` 显式拒绝的 UNSAFE published state 与 repair+create action 组合，`dataclasses.replace` 无法构造、setattr 是唯一手段且带行内注释说明意图——不属于本用例范围。
4. **断言未弱化**：`关闭`。`test_incompatible_company_decision_fails_before_canonical_skip_mutation` 的全部断言逐字保留：`events == ["rollback"]`、`company.intents == []`、`company.stage_tokens == []`、`batching.commit_tokens == []`、`len(begin_tokens) == 1`、`rollback_tokens == begin_tokens`、临时文件树恰为 `("metadata-skip.pdf",)`、输入 bytes 不变。红测能力逻辑推演保留：修复前生产代码（无 executor predicate）+ 新 seam 下，validator wrapper 返回 skip decision → arbitration helper 返回 SKIP → 旧 SKIP executor 走 stage（静默 return）→ commit（recorder 返回 typed outcome）→ 投影成功 skip → `pytest.raises(ValueError)` 仍以 `DID NOT RAISE` 失败；修复后先命中 predicate 抛 ValueError。两个 seam 均指向 execute 内部经模块级名字调用的 production 调用点，注入有效。
5. **类型/docstring/fixture owner**：`关闭`。两个 helper 均为模块级 typed 函数（无嵌套函数/类）；wrapper docstring 含参数、返回与三类异常（`FinsUploadUsageError`/`FinsUploadPrevalidationError`/`ValueError`），与真实 validator + replace 的实际异常面一致；monkeypatch 目标 `publication_module.validate_fins_upload_filing_request` / `publication_module.arbitrate_filing_upload_publication` 是 `execute_prepared_filing_publication` 内部的实际模块级调用名，fixture 未绕过 owner seam。

## Findings

未发现实质性问题。Finding 01（production predicate）与 Finding 02（test seam 注入方式）均已关闭：

- production diff 内容与上一轮 re-review 完全一致（唯一 predicate `_company_decision_allows_canonical_skip` 同时供 arbitration 与 SKIP executor 消费；非法 combo 在 stage/commit/capability transfer 前抛 ValueError；outer finally rollback 恰一次；合法 keep 与 stage/preserve 生命周期不变），符合"production diff SHA 不变"的声明。
- 测试 seam 已按 finding 02 建议改为 validator wrapper + `dataclasses.replace`，注入状态经 frozen owner 全量构造校验，未来 `__post_init__` 收紧 decision 校验时该测试仍保持 owner 敏感。

## Open Questions

无。

## Residual Risk

- 完整 combined regression（2158 passed）未在本 reviewer 处重跑；实测复现 4 个定向测试 `5 passed` 与全 owner 文件 `41 passed`，与 fix artifact 声称一致。
- 红测"修复前 1 failed"无法在本 reviewer 处重放（修复已应用）；已按旧生产代码路径与新 seam 的交互做逻辑推演，结论为红测能力保留。
- `docs/reviews/code-review-20260817-172506.md` 与另一路 aggregate findings 的最终裁决由 controller 汇总，不在本定向复核范围。

## Verdict

**PASS**。Finding 01 与 Finding 02 均关闭，无新 finding，无 blocking open question，无未分类 residual risk。
