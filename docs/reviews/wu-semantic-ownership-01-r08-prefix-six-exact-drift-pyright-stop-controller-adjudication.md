# WU-SEMANTIC-OWNERSHIP-01 / R08 prefix-six exact-drift pyright stop Controller adjudication

## 1. 结论

`FIX_REQUIRED / THREE_ACCEPTED_TEST_OWNER_FINDINGS / NO_PLAN_CORRECTION_REQUIRED`。

AgentCodex STOP artifact：

- `docs/reviews/wu-semantic-ownership-01-r08-prefix-six-exact-drift-implementation-continuation-codex.md`
- SHA-256：`6dbe63576619d2b40f203acbf8fe9866cc8aa0ac92a6088a89c97e6d7f548a52`
- 状态：`STOP / PYRIGHT_FAILED / NOT ACCEPTED`

Controller 在同一 tree、Python 3.11 venv 与 pyright `1.1.409` 上复跑
`pyright tests/fins/test_read_runtime_semantic_ownership_guards.py`，精确复现
`12 errors, 0 warnings, 0 informations`。全部 diagnostics 位于当前 R08 新增的 owner-level contract tests / fixtures，且
`git diff` 直接证明相关节点、fixture 与 imports 都是 R08 cumulative delta；不是 unrelated pre-existing debt。

Plan §8 已明确：§6.6/§6.7 失败必须在原 owner/failure boundary 修复并从零完整重跑，若需越界才停止。因此本轮可以直接进入同一 R08 test-owner fix，不需要重做产品裁决或 plan correction；但旧 validation 与 tree locks 在 fix 后全部失效，必须在新 tree 上从零重跑。

## 2. Accepted findings

### `R08-VAL-PY-F01`：optional public keys 的测试断言未先证明存在

`ACCEPTED / MEDIUM`。

Direct diagnostics：

- `ListDocumentsResult["suggestion"]`：1 error；
- `TableDetailResult["caption"]` / `["page_no"]`：2 errors。

这些键按 public TypedDict contract 是 `NotRequired`，当前测试虽然业务 fixture 保证存在，却直接索引而没有先让类型系统验证 presence。正确 test-owner fix 是先用精确 membership assertion 证明键存在，再断言值；不得改 production schema、把可选键改成 required、使用 `.get()` 默认值、cast、ignore 或弱类型。

### `R08-VAL-PY-F02`：测试 processor 的 required extra constructor 参数违反 production protocol

`ACCEPTED / MEDIUM`。

`_DefaultConceptsXbrlProcessor.__init__` 新增 required keyword-only `taxonomy`，而 production
`DocumentProcessor` protocol 只允许 caller 依赖 `source/form_type/media_type`。因此三个 registry construction 点各产生一个
`reportArgumentType`。

正确 test-fixture owner fix 是让 fixture constructor 对所有 protocol-valid calls 仍可调用，同时保留每个 test 显式覆盖 US-GAAP/custom taxonomy 的能力。最小方案可把 test-only `taxonomy` 设为有业务合理默认值的 optional extra keyword；不得改 production protocol、registry annotation、使用 cast/type-ignore 或新增兼容 facade。

### `R08-VAL-PY-F03`：XBRL union result 在测试中未做 public-shape narrowing

`ACCEPTED / MEDIUM`。

`FinsReadRuntime.query_xbrl_facts` 正确返回 `PublicXbrlQueryResult | NotSupportedResult`。两个成功路径直接访问
`query_params/facts/fact_count`，共 6 个 errors；这不是 production return type 错误。

正确 test-owner fix 是复用本文件已有 `TypeGuard` 模式，新增对 XBRL success public shape 的 test-local guard，并在成功路径访问前显式断言。Guard 必须只依据成功 contract 的正向必有业务字段（例如 `facts`），不读取内部状态，不猜 provider，不使用 cast、`Any`、loose parsing 或 production fallback。

## 3. Rejected alternatives

- 不把 12 errors 标为“既有 pyright debt”或 residual risk；它们由当前 R08 diff 直接引入且 full pyright zero 是强验收门槛。
- 不修改 `dayu/fins/tools/result_types.py`、`read_runtime.py`、`DocumentProcessor` protocol 或任何 production code；owner contract 本身正确。
- 不删除/skip/xfail candidate 6、原五个 stable-owner tests 或相关 public projection tests。
- 不增加 `type: ignore`、cast、`.get()` 默认值、compatibility shim、弱类型或测试驱动 production fallback。
- 不复用本次 STOP 前的部分绿色作为 fix 后 acceptance；任何 test-file mutation 都使旧 prefix/coverage/validation tree lock 失效。

## 4. Authorized fix boundary

AgentCodex 只允许修改：

```text
tests/fins/test_read_runtime_semantic_ownership_guards.py
```

并新增 fix artifact：

```text
docs/reviews/wu-semantic-ownership-01-r08-prefix-six-exact-drift-pyright-fix-codex.md
```

Exact constraints：

1. 只修 `F01..F03` 的类型正确性；candidate 6 test/import/三断言、原五个 tests、test node count 与 production behavior 不变。
2. Production、其它 tests、README、design、control、plan、prior/controller/S1/S2 artifacts no-touch。
3. Fix 后先执行 focused pyright 与目标 tests；任何 semantic assertion、test count 或 type failure 停止。
4. 然后在新 tree 上从 entry locks/source-AST proof 开始，fresh 重跑 prefix-six exact proof与完整、从零 §6.6/§6.7，包括 15-file coverage、full pyright、scoped Ruff、全部 scans/smokes 与 `git diff --check`。Prefix-five predecessor JSON 保留，不回退 candidate 6、不重跑 prefix-five。
5. 新 tree 的 expected prefix-six 仍是相同 8 files、零 deselect、`392 passed` 与 production helper `391/485 = 80.61855670%`；任一 numerator/denominator/count drift fail closed，不得补测试或放宽 checker。
6. 完成后记录新 cumulative binary diff、guards content SHA、23-path manifest/content hashes、全部 exact results 与 residual risks；staged 保持 empty。

Topic 8-9 no-code、安全机制、R07 no-touch、R09-R12、Issues 142/151/175/177/178、统一 authorization 与 deferred boundaries 均保持。

## 5. Next gate

AgentCodex 执行同一 R08 validation-fix gate，修复 `R08-VAL-PY-F01..F03` 并完成新 tree 全量 revalidation。完成后停止回 Controller；不得 stage、commit、push、PR、code review 或 aggregate deepreview。
