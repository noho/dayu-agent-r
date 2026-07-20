# WU-SEMANTIC-OWNERSHIP-01 Aggregate Regression Fix Slice 2 Implementation Controller Authorization

## 1. Entry lock

- 日期：`2026-07-19`。
- Slice base / accepted HEAD：`ba44bf877138235d53606d082341a7f7280af488`。
- Slice 1 accepted commit validation：`docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-accepted-commit-controller-validation.md`。
- Accepted plan：`docs/host/wu-semantic-ownership-01-aggregate-regression-fix-plan.md`，SHA-256 `afaa18c5608e6eeae0046318865bd1b3dd2f9a176c4b0739aa5b099e0ae3a252`。
- Gate：Slice 2 public Fins contract / Service boundary closure，关闭 `AR-F02`。
- Dispatch前除Controller本授权、Slice 1 accepted-commit validation和control gate tracking外无worktree change；AgentCodex必须记录这些protected paths的entry hash并保持不变。

## 2. Exact mutable scope

Production：

```text
M dayu/cli/commands/fins.py
M dayu/fins/direct_events.py
D dayu/fins/direct_stream.py
A dayu/fins/ingestion/awaiting_resolution.py
M dayu/fins/ingestion_runtime.py
M dayu/fins/tools/_ingestion_tool_helpers.py
M dayu/fins/tools/download_provider.py
M dayu/fins/tools/preprocess_provider.py
M dayu/fins/tools/upload_provider.py
M dayu/service/fins_direct.py
M dayu/service/fins_wait_adapter.py
M dayu/service/host_assembly.py
```

Tests：

```text
M tests/cli/test_fins_commands.py
M tests/fins/test_fins_direct_stream.py
M tests/fins/test_fins_ingestion_tools.py
M tests/service/test_fins_direct.py
M tests/service/test_fins_wait_adapter.py
M tests/service/test_host_assembly.py
```

Validation utility与README：

```text
M utils/smoke_host_public_awaiting_entrypoint.py
M dayu/fins/README.md
A docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s2-implementation-codex.md
```

`utils/smoke_host_public_awaiting_entrypoint.py`只允许迁移一个import，其九个业务/类型uses与其它行必须byte-identical。`tests/service/test_import_boundary.py`、`dayu/fins/__init__.py`、`dayu/fins/ingestion/__init__.py`必须零diff并自然通过。其它production、tests、utils、README、workflow、design、control与既有review artifacts全部protected。不得stage、commit、push、PR、派发review或开始Slice 3/aggregate。

## 3. Required owner migration

1. 把`ValidatedFinsEventStream`实现、私有state/constants物理迁到`dayu/fins/direct_events.py`，删除`dayu/fins/direct_stream.py`并直接迁移Fins runtime、CLI、Service与tests consumers。禁止re-export、wrapper、lazy/dynamic/try-import或兼容路径。
2. 新建`dayu/fins/ingestion/awaiting_resolution.py`，唯一拥有`AWAITING_RESOLUTION_MODE_CONFIG_FIELD`、`AwaitingResolutionMode`和`parse_awaiting_resolution_mode`；从tools私有helper删除三项定义并迁移三个providers、Service、host assembly、tests和唯一utility import。禁止duplicate enum/parser、Service字符串重算或package-root re-export。
3. 保持现有业务语义：stream identity、exactly-one且末尾RESULT、missing/duplicate/after-result typed errors、clean exhaustion terminal identity、close-at-most-once、异常/取消identity、provider mode闭集与错误文本。
4. 按`dayu/fins/README.md`自身更新约束同步现行文件树与owner说明；不得承诺旧路径兼容。读取并裁决`dayu/service/README.md`、`tests/README.md`、根`README.md`和`dayu/README.md`，预期`NO_UPDATE`。

## 4. Mandatory validation

- 完整执行accepted plan §4.2 focused tests、full Fins suite、direct-stream/awaiting owner与stale-private scans、五个real Fins/Host smokes；外部provider不可用保留真实failure evidence，不能改成mock PASS。
- 执行plan §6全部门禁：canonical non-coverage 0 failed且AR-F06 node真实运行；single-node exact-exclusion coverage run 0 failed；除Slice 3九路径外全部aggregate-range production paths（含新owner）line coverage `>=80%`。
- Full pyright zero；full Ruff immutable baseline无增量且mutable Python paths零finding；wheel/sdist build；six scans；security、configured-value semantic-owner、README、deferred、Topic 8/9 no-code ledgers；diff-check、staged-empty与exact allowlist。
- Config与Host internal SQLite/EventLog是accepted trusted internal；Tool Trace、audit、public、LLM-facing、logs、其它outputs、diff/review仍要求configured-value零命中。不得建立secret storage/redaction基础设施或统一tool authorization framework。
- Gemini测试账号quota为`EXPECTED_TEST_ACCOUNT_QUOTA / NO_CODE_ACTION / NON_BLOCKING`；不改provider config/model/key/retry/quota/budget，不追加真实provider请求。
- Issue 142、151、175、177、178与Web/WeChat/render trackers继续deferred；AR-F06保持`RETAINED / UNFIXED / UNWAIVED / CURRENT_NO_FIX`，AR-F07保持真实remote Windows owner。

## 5. Stop conditions and handoff

发现额外mutable path、import cycle迫使扩域、public行为漂移、真实production correctness/type/security defect、旧private owner残留、compatibility/fallback需求、HKEX accepted evidence缺失/hash漂移或任何zero-required surface明文命中时，立即停止并提交直接证据，不能自行扩域或下游补偿。

Implementation artifact必须记录entry/protected/final hashes、完整命令/exit/result、coverage/build/smoke/scans、allowlist/README/security/deferred/no-code ledger与Slice exit verdict。完成后停在Controller validation；不得自行发送review任务。
