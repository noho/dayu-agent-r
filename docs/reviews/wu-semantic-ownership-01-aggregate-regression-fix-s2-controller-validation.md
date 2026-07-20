# WU-SEMANTIC-OWNERSHIP-01 Aggregate Regression Fix Slice 2 Controller Validation

## 1. Gate identity

- 日期：`2026-07-19`。
- Umbrella：`WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation；不是新 WU。
- Gate：Slice 2 implementation 后的 Controller 独立验证。
- Slice base / HEAD：`ba44bf877138235d53606d082341a7f7280af488`。
- Branch：`phaseflow/host-issues-control`。

AgentCodex implementation artifact：

- 路径：`docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s2-implementation-codex.md`。
- SHA-256：`3cc7dc4caee4cac8e6620e35f1373d252c0518f1218013027bb32a30810cab5c`。
- Verdict：`PASS / IMPLEMENTATION_AND_MANDATORY_LOCAL_VALIDATION_COMPLETE / READY_FOR_CONTROLLER_VALIDATION`。

## 2. Exact immutable review target

扣除Controller/control/review artifacts后，Slice 2完整target恰好20个路径：12个production（含1 delete、1 add）、6个tests、1个validation utility、1个Fins README。十九个现存文件内容加被删除旧owner base blob的sorted manifest SHA-256为：

```text
cb0d5f96da993dd7cbe65fe513d2432a25b5c4a091515e5f1a29f2ed8d303925
```

被删除的`dayu/fins/direct_stream.py` base blob SHA-256为`f724e51ca6ff5dd687dfe4709751b8f0e9bd440b4e02f0bfd343f598a1e50c53`。新owner `dayu/fins/ingestion/awaiting_resolution.py` SHA-256为`945ffedf2ab375afc24668db4c7a327fb2008c066a954d51046e3273b79ee481`。

- `tests/service/test_import_boundary.py`、`dayu/fins/__init__.py`与`dayu/fins/ingestion/__init__.py`零diff。
- utility只有一行import owner迁移，其九个uses与其它行不变。
- staged tree为空；`git diff --check`通过。
- 全部delta精确落在authorization allowlist，无production/test/README/utility越界。

## 3. Controller independent tests and scans

Controller在相同immutable target独立执行：

| Gate | Result |
| --- | --- |
| Slice 2 focused + import boundary | `321 passed, 3 warnings in 5.56s` |
| current live-browser descendant cleanup owner | `1 passed in 2.11s` |
| full pyright | `0 errors, 0 warnings, 0 informations` |
| full Ruff | exit `1` only for immutable baseline；`143` tuples，normalized SHA-256 `c34af22...240e`，与Slice 1 accepted-final完全相同；mutable paths零finding |
| direct-stream stale scan | exit `1`，zero match |
| direct-events consumer scan | 精确3 production + 3 tests |
| awaiting definitions | 精确3项，全部在新public owner |
| old private definitions/imports | 两条均exit `1`，zero match |
| diff/staged | diff-check PASS；staged EMPTY |

AgentCodex fresh完整证据同时通过：focused `321`、Fins `950/1 skip`、canonical `5182/10 skip/5 deselected/0 failed`、single-node coverage `5180/11 skip/6 deselected/0 failed`、五条Fins/Host real smokes、build、六组scans、security matrices和configured-value owner scan。Coverage worktree集合精确`219`，其中`210 >=80%`；低于80%的只有Slice 3预定九路径。Slice 2 owners分别为`direct_events.py 94.14%`与`awaiting_resolution.py 100%`。

## 4. Semantic-owner and behavior decision

- `ValidatedFinsEventStream`、其私有state/constants与direct event/result/typed error现在由`dayu.fins.direct_events`唯一拥有；旧模块物理删除，无re-export、wrapper、lazy/dynamic/try import或兼容分支。
- Awaiting config field、closed enum与strict parser由`dayu.fins.ingestion.awaiting_resolution`唯一拥有；tools私有helper不再定义或转发该语义。
- CLI、Fins runtime、Service与tests直接消费public owner；Service没有字符串重算或第二套validator。
- 既有stream identity、exactly-one且最后RESULT、typed protocol errors、terminal identity、close-at-most-once、异常/取消identity与provider mode错误语义均由owner tests保持。
- README只同步Fins现行文件树/owner；其它README均正确判定`NO_UPDATE`。

## 5. Live-browser command disposition

Accepted plan §6.8中的历史node在Slice base不存在，原命令exit `4`。这不是本轮新finding；`docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-fifth-stop-controller-adjudication.md`已将其裁决为`VALIDATION COMMAND DRIFT / CURRENT NODE IDENTIFIED / NO CODE FIX`，并规定后续按届时current owner node运行。AgentCodex与Controller均fresh运行current owner：

```text
tests/tools/web/test_web_tools_provider.py::test_playwright_live_browser_cleanup_smoke_is_manual_and_best_effort
```

两次均真实PASS而非skip。因此该历史命令不形成新accepted code/plan finding，也不阻塞code review；Slice 3与aggregate继续按prior Controller adjudication使用current owner并如实分类。

## 6. Security / deferred / residual ledger

- Config与Host internal SQLite/EventLog仍为`ACCEPTED_TRUSTED_INTERNAL`；Tool Trace、audit、public、LLM-facing、logs、其它outputs、diff/review为`ZERO_REQUIRED`且全部零明文。
- 未引入secret storage/redaction infrastructure或统一tool authorization framework；现有containment、symlink、DNS/peer、resource budget、atomic write、process fencing均未削弱。
- Topic 8 Engine 240字符脱敏/截断零diff；Topic 9保持no-code。
- Issues 142、151、175、177、178与Web/WeChat/render trackers均未偷带实施。
- Gemini quota继续是`EXPECTED_TEST_ACCOUNT_QUOTA / NO_CODE_ACTION / NON_BLOCKING`，不改provider/config/model/key/retry/quota/budget，也不追加真实provider请求。

```text
AR-F02 = IMPLEMENTATION_PASS / CODE_REVIEW_PENDING
AR-F05 = OPEN_BY_SEQUENCE / SLICE_3
AR-F06 = RETAINED / UNFIXED / UNWAIVED / CURRENT_NO_FIX
AR-F07 = PENDING_RELEASE_BLOCKER / REAL_REMOTE_WINDOWS_EVIDENCE
```

## 7. Decision

```text
PASS / READY_FOR_CONCURRENT_COMPLETE_SLICE_2_CODE_REVIEW
```

下一gate只授权AgentMiMo与AgentDS对上述immutable20-path target并发完整code review。AgentCodex fix、commit、Slice 3、aggregate、push、PR与closeout仍未授权。
