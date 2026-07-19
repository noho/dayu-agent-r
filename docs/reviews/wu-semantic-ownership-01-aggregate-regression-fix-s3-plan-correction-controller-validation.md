# WU-SEMANTIC-OWNERSHIP-01 Aggregate Regression Fix Slice 3 Plan Correction Controller Validation

## 1. Gate identity

- 日期：`2026-07-19`。
- Umbrella：`WU-SEMANTIC-OWNERSHIP-01` continuation；不是新 WU。
- Gate：AgentCodex plan-only correction 后的 Controller 独立验证。
- Immutable slice base / HEAD：`9e7a4e9d4796b9c382d44494bb10efa64787b199`。
- Corrected plan：`docs/host/wu-semantic-ownership-01-aggregate-regression-fix-plan.md`。
- Corrected plan SHA-256：`ef4a0832f1885e4013d673294b944a56280619baab1f97d438896af5c8cbedcf`。
- AgentCodex artifact：`docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-plan-correction-codex.md`，SHA-256 `c5b788b03ab54638841a7bd58cb8d5978ef92de8ea120ff3a3408aedbaac2072`。

## 2. Scope validation

Plan-only correction 精确修改 accepted plan 并新增一个 AgentCodex correction artifact；production/tests/README/utility均没有被本 gate 修改。此前 Slice 3 implementation test delta与Controller artifacts的entry hashes均由artifact逐项保护；staged tree为空，`git diff --check`通过。

Corrected production allowlist只增加：

```text
M dayu/documents/processors/docling_processor.py
```

其它八个AR-F05 owners继续零diff；该Docling path已属于aggregate parent到当前树的219 production集合，不改变集合成员。

## 3. Code-generation readiness

Corrected plan 已把 implementation 不应临场裁决的语义固定：

- 同一`DoclingDocument`从`_build_tables`直传caption resolver。
- 只消费current `TableItem.captions`与每个`RefItem.resolve(document)`；不保留旧单数caption、raw JSON/private parser、重新加载document、第二resolver、下游补偿或兼容fallback。
- 只接受typed `TextItem`，按source ref顺序规范化、大小写敏感精确去重、首次保留并以单空格连接；空结果为`None`。
- known dangling metadata只在单次resolve周围精确处理`AttributeError`/`IndexError`；model-invalid ref在真实Docling load边界失败；其它异常不得宽泛吞掉。
- public tests覆盖单/多caption、顺序、规范化、去重、空白、dangling、model-invalid、非文本与三个public views，不直接锁private helper。
- 修复`S3-STOP-F01`后才继续剩余owner coverage；最终仍要求canonical、219/219、pyright、Ruff、build、scan、smoke与security全门禁。

README、trusted-internal/zero-required secret分类、Gemini quota、AR-F06/07与deferred/no-code边界均保持。

## 4. Controller observations for adversarial review

双路plan review必须特别挑战：

1. `TextItem`模块级依赖是否与项目required dependency和import boundary一致。
2. 多caption连接规则是否丢失业务分隔或把独立语义错误合并。
3. dangling ref只捕获`AttributeError`/`IndexError`是否精确且不会吞编程错误。
4. model-invalid serialized payload test是否确实经过public loader而不是引入production raw JSON解析。
5. page view fixture是否具备真实provenance，避免测试伪造不可达路径。
6. 109/22行plan correction是否无历史状态误改、重复owner或门禁弱化。

这些是review questions，不是Controller预先裁决的findings。

## 5. Decision

```text
PASS / PLAN_CORRECTION_SCOPE_VALID / READY_FOR_DUAL_COMPLETE_PLAN_REVIEW
```

下一gate只授权AgentMiMo与AgentDS对完整corrected plan及全部S3证据做并发完整plan review。不得implementation、修改tests/production、stage、commit、aggregate、push、PR或closeout。
