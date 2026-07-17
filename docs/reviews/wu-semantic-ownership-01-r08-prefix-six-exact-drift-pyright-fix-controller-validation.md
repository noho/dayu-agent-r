# WU-SEMANTIC-OWNERSHIP-01 / R08 pyright validation fix Controller validation

## 1. Verdict

`PASS / R08-VAL-PY-F01..F03 CLOSED / FULL_REVALIDATION_GREEN / READY_FOR_DUAL_COMPLETE_IMMUTABLE_CODE_REREVIEW`。

本 validation 只允许 AgentMiMo 与 AgentDS 对同一 immutable R08 cumulative tree 做并发、独立、完整 code re-review；不授权进一步修改、aggregate deepreview、commit、push 或 PR。

## 2. Reviewed artifacts 与 locks

| Item | Controller value |
|---|---|
| accepted plan commit | `c723de5907b834f05b2701d23c1067cb3eb960ce` |
| pyright stop adjudication | `docs/reviews/wu-semantic-ownership-01-r08-prefix-six-exact-drift-pyright-stop-controller-adjudication.md` |
| AgentCodex fix artifact | `docs/reviews/wu-semantic-ownership-01-r08-prefix-six-exact-drift-pyright-fix-codex.md` |
| fix artifact SHA-256 | `29596e309d194bb898b80803e9cc0f7faa9f76285e9af2e8ba98b00c07ed2edc` |
| cumulative `git diff --binary -- dayu/fins tests` SHA-256 | `01c2a1d51e4ed048da84331bb9a2bc2613f270c8cb1863d0ad9a641a25f3092d` |
| changed-path manifest | 23 tracked paths |
| guards content | `44d9eaadcba006ef5df815a5906e7d590c712b7e991d09916944df5c8f83471a` |
| helper / actual owner / shared | `1d7b4bf1...5ea9b` / `27644d0d...0657` / `01db5538...6692` |
| S1 / S2 artifact | `d97eed50...5748` / `08085bde...648` |
| prefix-five / fresh prefix-six JSON | `43986a2d...b59fb` / `d4ec8822...c7df` |
| cumulative coverage JSON | `a0947bea...374c` |
| staged | empty |

22 个非 guards paths 的 content hash 与 STOP artifact manifest 逐项一致；本 fix 只改变 guards test 与新增 fix artifact。

## 3. Finding closure

| Finding | Controller validation |
|---|---|
| `R08-VAL-PY-F01` | `已修复`：`suggestion/caption/page_no` 均先做 membership proof 再索引；未使用 `.get()` 默认值、cast、ignore 或 schema mutation |
| `R08-VAL-PY-F02` | `已修复`：test-only taxonomy 是 optional keyword default，processor 对全部 protocol-valid calls 可调用；显式 US/custom/failure cases 保留，production protocol/registry no-touch |
| `R08-VAL-PY-F03` | `已修复`：新增 test-local XBRL success `TypeGuard`，仅以必有 public `facts` field 收窄；两个成功结果访问前显式 assert，无 `Any`、cast 或 internal/provider inference |

Candidate 6 test/import/三断言与原五个 stable-owner tests 的 AST cardinality/no-bypass proof 通过；target file runtime collection 仍为 24 cases，八文件仍为 392 cases。

## 4. Controller independent validation

Controller 在同一 tree 独立运行：

- `pyright`：`0 errors, 0 warnings, 0 informations`；
- `pytest tests/fins/test_read_runtime_semantic_ownership_guards.py`：`24 passed, 3 warnings`；
- `ruff check tests/fins/test_read_runtime_semantic_ownership_guards.py`：`All checks passed!`；
- `git diff --check`：PASS；staged empty；
- cumulative binary diff / guards / proof JSON / cumulative JSON hashes：全部匹配 §2；
- JSON direct comparison：prefix-five `387/485 = 79.79381443%`，fresh prefix-six `391/485 = 80.61855670%`，new executed lines `[344,346,348,442]`；
- test source 无 `type: ignore`、`pyright: ignore`、`typing.cast` 或 `cast(...)`。

AgentCodex 的完整新-tree evidence 还包括：focused `119 passed / 50 deselected`、fiscal `1 passed`、public `334 passed`、forced truncation `1 passed`、real smokes `3 passed`、aggregate `392 passed`、full Fins `859 passed / 1 existing environment skip`、15/15 production files coverage `>=80.00%`、full pyright zero、21 changed Python scoped Ruff pass、完整 §6.7 A-G 与 `git diff --check` pass。Controller 已核对 artifact 的 commands/results、15-file ledger、content manifest 与 residual classification。

## 5. Residual risks 与 boundary

- Docling real upload integration 仍由既有环境开关控制，owner 是 Issue 175；不是 R08 finding，不扩 scope。
- 三条 `edgar` dependency deprecation warnings 不影响 exit，依赖未修改。
- Topic 8 保持 240 字符异常投影 no-code；Topic 9 未实现统一 authorization；既有 containment、symlink、DNS/peer、budget、atomic/process/security mechanisms no-touch。
- R07、R09-R12、Issues 142/151/175/177/178 与 Web/WeChat/render deferred boundaries 保持。
- 没有 unclassified residual risk 或 blocking open question。

## 6. Next gate

AgentMiMo 与 AgentDS 必须使用 `/deepreview`，对 cumulative diff SHA
`01c2a1d51e4ed048da84331bb9a2bc2613f270c8cb1863d0ad9a641a25f3092d` 做并发、独立、完整 code re-review，不得只审 pyright fix patch。两路必须独立重算 locks，验证原 cumulative code-review finding、全部 plan/validation findings closure，重新挑战 R08 Topic 6 产品 contract、owner 唯一性、LLM-facing projection、candidate 6/prefix proof、R07/security/no-code/deferred/no-compat boundaries 与完整 validation evidence。Reviewer verdict 不授权 aggregate 或 commit；任何 accepted finding 仍须 AgentCodex fix 与双路完整 re-review。
