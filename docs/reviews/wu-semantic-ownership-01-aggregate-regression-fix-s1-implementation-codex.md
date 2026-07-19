# WU-SEMANTIC-OWNERSHIP-01 aggregate regression fix Slice 1 implementation

## 1. Gate identity / verdict

- 执行者：AgentCodex。
- Gate：Slice 1 current-schema / test-oracle closure（`AR-F01`、`AR-F03`、`AR-F04`）。
- 状态：`STOPPED / CONTROLLER_DECISION_REQUIRED / NOT_READY_FOR_REVIEW`。
- Slice exit：第五次 Controller 裁决确认计划 §6.8 的 live-browser路径漂移并指定 current owner node；该 node fresh真实运行通过（`1 passed`）。随后 fresh secret gate在不输出 secret value的前提下得到 `configured_secret_value_count=5`、`secret_value_match_count=3`、`matched_path_count=1`，触发新的 stop rule。没有打开命中内容、输出 secret、继续 deferred/no-code/README final acceptance或扩大 scope；只完成 stop后的只读 diff/protected-hash/staged-empty checkpoint，停在 Controller validation。
- 未 stage、commit、push、开 PR、启动 subagent/reviewer，也未开始 Slice 2/3。

## 2. Entry lock 与 protected paths

Entry fresh 读取并核对：

```text
branch = phaseflow/host-issues-control
SLICE_BASE / HEAD = ffbf48c2cf5f701c627fda1ebcce7aa1813383ab
accepted plan SHA-256 = 7e91421b8bc8c442dcf72e94c20eb84d4f27f2b9878b427481448d6f2f4ea714
staged tree = empty
```

三个 Controller-owned paths 的 entry/final status 与 SHA-256 均保持不变：

```text
 M  8a559d8a82f39dd918e17fe5f4b9afe6aa6d3a79d07e92bec902d8ad0b956211  docs/host/issues-implementation-control.md
??  cad213bdb7b02abf9cf4a876a0925e4318df8908cdb1f0bb17090155d3c67114  docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-accepted-plan-commit-controller-validation.md
??  ebb6a9dc92cc4ab24961228891f97442444f4c98228e2693c43aba08328dddcd  docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-implementation-controller-authorization.md
```

Entry Ruff immutable baseline：144 findings；规范化
`(filename,row,column,code,message)` 集合 SHA-256 为
`42e3602264668d0506924acb198e801eff1569d43aeb762722b86ca02807c409`。
三个 mutable tests 中只有 entry-existing
`tests/tools/web/test_smoke_web_ci.py:32:1 E402`；Slice exit 要求三个路径零 finding。

## 3. 第一性原理与 semantic owner 裁决

- `AR-F01`：`ConfigLoader` 已把 `wait_poller_policy` 定义为 Host runtime profile 的 current required schema；缺陷 owner 是测试 fixture，不是 production loader。修复只补 fixture 的 12 个必填字段。
- `AR-F03`：standalone Web smoke 的 root logging 是 operator 语义；同进程 pytest 调用造成的 registry 污染由 test harness owner 隔离。production logging 零 diff。
- `AR-F04`：runner-call manifest 的 `compactor_identity.compaction_request_digest` 与 compact artifact 顶层同名 digest 是 current owner-published association；candidate id / run-id 拼接不是业务真源，已删除该关联逻辑。
- Stop evidence 表明 production compact owner 与真实 artifact 一致发布 `input_snapshot_refs.current_input_ref`；现有测试的 `current_user_input_ref` 是另一处 stale oracle。accepted plan §4.1 要求“保持 existing current-schema continuity assertions”，但未授权裁决或替换该字段，因此不能自行继续修改。

## 4. 已完成的 authorized implementation

### 4.1 `tests/service/test_host_admin.py`

- `_write_host_runtime` 写出 current required `wait_poller_policy` 全量 12 字段及计划固定值。
- 保持“只加载 Host runtime，不要求 models/scenes/tools/secrets”的原测试目标。
- 收紧 admin storage options 断言，证明 current profile 成功加载且原 storage projection 未漂移。

### 4.2 `tests/tools/web/test_smoke_web_ci.py`

- 新增 module-level typed logging snapshot/restore harness，统一包裹现有六个 in-process `smoke.main` 调用。
- snapshot root 与 registry 中全部 concrete logger 的 level、handler identity/order、filter identity/order、propagate、disabled，并记录 registry entry identity/order。
- `finally` 恢复调用前状态，移除调用中新建的 logger entries，只卸载并关闭调用中新建的 handlers。
- success/failure contract test 预置 root 与 named logger 非默认状态，证明状态与 identity/order 均恢复、pre-existing handlers 不关闭、新增 handlers 全关闭。
- 第二次 Controller 裁决后，typed `_LoggerState` 还快照精确 `parent: logging.Logger | None`；registry entries 恢复完成后再逐一恢复所有快照 logger 的 parent identity。generic success/failure contract 预存 descendant、保留其中间 parent 的原 `PlaceHolder`，由 fake 创建 concrete parent 触发 stdlib reparent，再断言 parent、registry、logger state 与 handler identity 全部精确恢复；没有硬编码 `dayu.fins` 或 SEC。
- 删除造成 entry E402 的动态 `sys.path` 导入 seam；standalone product smoke 零 diff。

### 4.3 `tests/host/test_public_compact_smoke.py`

- 删除 `_CANDIDATE_ID_FIELD`、`llm-compact:{run_id}` 拼接及 candidate-id/raw guess 关联。
- 以 current manifest schema、`host_run_id`、`runner_call_kind=compactor_proposal` 唯一定位 manifest；严格读取 `compactor_identity.parent_host_run_id` 与 SHA-256 `compaction_request_digest`。
- 以 current compact kind/schema 与相同 request digest 唯一定位 compact artifact；无 `dict.get` 猜测链、fallback、顺序/文件名/mtime 推断。
- 增加 success、missing/duplicate manifest、missing/invalid manifest digest、parent run mismatch、missing/duplicate compact artifact、wrong/missing compact digest 的 deterministic fail-closed cases。

Stopped checkpoint 的 mutable file SHA-256：

```text
5acf57a06d1c7fee82a27ae0c3ccdfcddfe745a42439a514c0551665904f96db  tests/service/test_host_admin.py
4a63f3975faf311e4ede4d7e3b7a34329f07f1cb6639cb3e77b1c2c3e6314c53  tests/tools/web/test_smoke_web_ci.py
65f46ef935d6792cd32a39488f423ff8de12584feef64249a2eb91becdc29709  tests/host/test_public_compact_smoke.py
```

## 5. Fresh command / exit / result ledger

### 5.1 Entry / lint

```bash
git branch --show-current
git rev-parse HEAD
git status --short
git diff --cached --name-status
shasum -a 256 docs/host/wu-semantic-ownership-01-aggregate-regression-fix-plan.md \
  docs/host/issues-implementation-control.md \
  docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-accepted-plan-commit-controller-validation.md \
  docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-implementation-controller-authorization.md
```

- Exit：`0`。
- Fresh result：branch/HEAD、plan 与三个 protected hashes 全部精确匹配；staged empty。

```bash
source .venv/bin/activate && \
ruff check dayu tests utils --output-format json \
  --output-file workspace/tmp/wu-semantic-ownership-01-ar-fix-s1-entry-ruff.json
```

- Ruff exit：`1`（基线存在 findings，不冒充 tool pass）。
- Fresh result：144 findings；规范化集合 hash 见 §2；mutable paths entry finding 仅一个 E402。

```bash
source .venv/bin/activate && \
ruff check tests/service/test_host_admin.py \
  tests/tools/web/test_smoke_web_ci.py \
  tests/host/test_public_compact_smoke.py --output-format concise
```

- Exit：`0`。
- Fresh result：`All checks passed!`；三个 mutable tests 当前零 Ruff finding。

### 5.2 Focused tests

```bash
source .venv/bin/activate && pytest tests/service/test_host_admin.py -q
```

- Exit：`0`；fresh result：`1 passed in 0.29s`。

```bash
source .venv/bin/activate && pytest tests/tools/web/test_smoke_web_ci.py -q
```

- Exit：`0`；fresh result：`48 passed, 3 warnings in 1.61s`。

```bash
source .venv/bin/activate && pytest tests/tools/web/test_smoke_web_ci.py \
  tests/runtime/test_log.py::test_configure_does_not_touch_root_by_default \
  tests/fins/test_sec_downloader.py::test_sec_request_debug_logs_success_response -q
```

- Exit：`0`；fresh result：`50 passed, 3 warnings in 1.56s`。

```bash
source .venv/bin/activate && pytest tests/host/test_public_compact_smoke.py -q
```

- Exit：`0`；fresh result：`23 passed, 1 skipped in 1.04s`。
- 分类：常规 focused 命令未设置 real-smoke 环境变量，因此仅 real compactor node 按其既有 gate skip；下一命令显式开启并实际执行该 node。

### 5.3 Real compactor stop evidence

```bash
source .venv/bin/activate && \
DAYU_RUN_REAL_COMPACTOR_SMOKE=1 pytest \
  tests/host/test_public_compact_smoke.py::test_real_compactor_public_opener_compacts_and_preserves_continuity \
  --basetemp=workspace/tmp/wu-semantic-ownership-01-ar-fix-s1-real-compactor \
  -q -rs
```

- Exit：`1`；fresh result：`1 failed in 4.79s`，node 未 skip。
- 两轮 Host terminal 与 manifest/digest/compact 唯一关联均已成功；失败发生在后续 existing continuity oracle：

```text
KeyError: 'current_user_input_ref'
tests/host/test_public_compact_smoke.py:1082
```

本次 current owner-published evidence：

```text
manifest artifact SHA-256 = 4396380523800dcc48c50da291fbd835d28430389e06cbf093250d042766cf10
manifest schema_version = runner_call_input_manifest.v1
manifest runner_call_kind = compactor_proposal
manifest host_run_id = run-76fece42e4254ffe85eb47c3758be03f
manifest parent_host_run_id = run-76fece42e4254ffe85eb47c3758be03f
manifest compaction_request_digest = sha256:6ea657dae42f1d64a5aca5428cae3c7db2f23b262559242d5b510527001b4d88

compact artifact SHA-256 = b127140f620d66076ca6bd256df9b10713bd96cc3cae5b1b26762e903f933121
compact artifact_kind = context_compaction
compact schema_version = 3
compact compaction_request_digest = sha256:6ea657dae42f1d64a5aca5428cae3c7db2f23b262559242d5b510527001b4d88
compact input_snapshot_refs field = current_input_ref
compact input_snapshot_refs has current_user_input_ref = false
```

Projection artifact SHA-256 为
`c7180c4d40a42a736ddf46c751958ab3f7ba7ecf769679db908f6c865c3168ef`。
Production owner direct evidence：
`dayu/host/compact_payload.py::_input_snapshot_refs_json_vnext` 明确写出
`"current_input_ref": request.current_input_ref`；production 与真实 artifact 同源一致。

### 5.4 Stopped checkpoint scope

```bash
git rev-parse HEAD
git status --short
git diff --name-status HEAD
git diff --cached --name-status
git diff --check
shasum -a 256 <three-protected-paths> <three-mutable-tests>
```

- Exit：`0`。
- Fresh result：HEAD 未变；staged empty；`git diff --check` 通过。
- 扣除三个 protected paths 后，implementation delta 只有三个 authorized `M tests/**`；本 artifact 写入后再增加唯一 authorized `A docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-implementation-codex.md`。
- Production、README、workflow、config、其它 tests/utils/artifacts 均零 diff。

## 6. 第一处 stop 时未运行的门禁（历史状态，已被 §9—§11 续跑证据部分取代）

第一处 stop 当时，依 authorization §4“立即停止”，以下命令均为
`NOT_RUN_AFTER_STOP_RULE`，不得用旧结果补签：

- standalone Web smoke；public-awaiting smoke；
- canonical non-coverage full suite；
- exact single-node-exclusion coverage run、coverage JSON 与 219-path ledger；
- full pyright；full Ruff exact-set final delta；
- wheel/sdist build；
- six canonical scans；
- security matrix、secret scan、deferred/no-code scans；
- final standalone/real smoke completeness。

该历史状态在 Controller 补充授权后由 §9—§11 的 fresh 续跑证据部分取代；仍没有把任何非 AR-F02 失败误记为允许的中间失败，也没有把九个 AR-F05 路径签为 coverage PASS。

## 7. README / security / secret / deferred / no-code ledger

- README：已读取 `tests/README.md` 的“README 更新边界”。当前修改没有新增测试层级、测试运行方式或维护规则，决定为 `NO_UPDATE`；authorization 也禁止 README diff。
- Security：未修改 production 或 security owner；full security matrix 因 stop rule 未运行，状态 `NOT_RUN_AFTER_STOP_RULE`，不能签 PASS。
- Secret：命令输出与本 artifact 只记录 digest、run id、路径和计数事实，不记录 provider secret value；full configured-secret scan 因 stop rule 未运行，状态 `NOT_RUN_AFTER_STOP_RULE`。
- Deferred：未引入 TruncationManager wiring、storage-state lifecycle/TTL/retention/refresh、Fins hard-kill/process isolation 或 assets migration；Issues 177、178、175、142/151 owner 不变。
- No-code：production 零 diff；`dayu/engine/agent.py`、`dayu/engine/contracts/error_codes.py` 零 diff；未引入 authorization framework、capability token、policy DSL 或 role model。
- `AR-F06 = RETAINED / UNFIXED / UNWAIVED / CURRENT_NO_FIX`。
- `AR-F07 = PENDING_RELEASE_BLOCKER`。

## 8. 第一处 stop 的 classification（历史状态）

- `AR-F01`：focused owner test通过，但 full gates 未运行，不能在 stopped slice 中签最终 `CLOSED`。
- `AR-F03`：focused、success/failure harness、order-sensitive 联跑均通过，但 full gates 未运行，不能签最终 `CLOSED`。
- `AR-F04`：manifest/digest association 新 oracle 本身通过 deterministic cases与真实 artifact；existing continuity assertion 与 current production schema冲突，状态 `NOT_CLOSED / CONTROLLER_DECISION_REQUIRED`。
- Failure classification：`PLAN_EVIDENCE_CONFLICT / STALE_TEST_ORACLE / NOT_PRODUCTION_DEFECT`。
- 需要 Controller 裁决：是否修订 Slice 1 精确授权，把 existing continuity field 从 stale `current_user_input_ref` 迁到 owner-published current `current_input_ref`，并授权修复后从 focused/real smokes开始 fresh 重跑 §6全部门禁。
- Next entry point：`Controller validation`。不得自行发送 review 或进入 Slice 2/3。

## 9. Controller stop adjudication 与精确 follow-up 修复

完整读取并核对：

```text
docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-stop-controller-adjudication.md
SHA-256 = db221c9ac75fbb1029ea1ad27ead96e36fe9dd791a4cb81d4f76a90467453762

docs/host/issues-implementation-control.md
SHA-256 = a803e002e959467e35f602bde371b2699079336a7ed1aada90a7aa8557723b98
```

Controller verdict：
`PLAN_EVIDENCE_CLARIFICATION / TEST-OWNER FIX AUTHORIZED / NOT_PRODUCTION_DEFECT`。
accepted plan 拥有 continuity 业务断言，不拥有 stale 字段拼写；因此在原已授权
`tests/host/test_public_compact_smoke.py` 内完成以下唯一补充修改：

```text
_CURRENT_USER_INPUT_REF_FIELD -> _CURRENT_INPUT_REF_FIELD
"current_user_input_ref" -> "current_input_ref"
current_user_input_ref -> current_input_ref
```

字段存在性由直接索引保留，`isinstance(current_input_ref, str)` 与
`current_input_ref.strip() != ""` continuity assertions 原样保留。没有 production、其它测试、README、workflow、config、design、control 或既有 review artifact 修改。

Follow-up entry lock：

```text
branch = phaseflow/host-issues-control
HEAD = ffbf48c2cf5f701c627fda1ebcce7aa1813383ab
staged tree = empty
control = M / a803e002e959467e35f602bde371b2699079336a7ed1aada90a7aa8557723b98
accepted-plan validation = ?? / cad213bdb7b02abf9cf4a876a0925e4318df8908cdb1f0bb17090155d3c67114
Slice 1 authorization = ?? / ebb6a9dc92cc4ab24961228891f97442444f4c98228e2693c43aba08328dddcd
stop adjudication = ?? / db221c9ac75fbb1029ea1ad27ead96e36fe9dd791a4cb81d4f76a90467453762
```

## 10. Stop adjudication 后的 fresh validation ledger

### 10.1 Focused tests

```bash
source .venv/bin/activate && pytest tests/service/test_host_admin.py -q
```

- Exit：`0`；fresh result：`1 passed in 0.29s`。

```bash
source .venv/bin/activate && pytest tests/tools/web/test_smoke_web_ci.py -q
```

- Exit：`0`；fresh result：`48 passed, 3 warnings in 1.56s`。

```bash
source .venv/bin/activate && pytest tests/tools/web/test_smoke_web_ci.py \
  tests/runtime/test_log.py::test_configure_does_not_touch_root_by_default \
  tests/fins/test_sec_downloader.py::test_sec_request_debug_logs_success_response -q
```

- Exit：`0`；fresh result：`50 passed, 3 warnings in 1.58s`。

```bash
source .venv/bin/activate && pytest tests/host/test_public_compact_smoke.py -q
```

- Exit：`0`；fresh result：`23 passed, 1 skipped in 1.04s`；唯一 skip 是未设置 real-compactor gate 环境变量的既有节点，下一命令显式执行且未 skip。

### 10.2 Real smokes

```bash
source .venv/bin/activate && \
DAYU_RUN_REAL_COMPACTOR_SMOKE=1 pytest \
  tests/host/test_public_compact_smoke.py::test_real_compactor_public_opener_compacts_and_preserves_continuity \
  --basetemp=workspace/tmp/wu-semantic-ownership-01-ar-fix-s1-real-compactor \
  -q -rs
```

- Exit：`0`；fresh result：`1 passed in 3.57s`，未 skip。manifest/request digest/compact artifact/current input continuity 全链路通过。

```bash
source .venv/bin/activate && python utils/smoke_web_ci.py \
  --output-dir workspace/tmp/wu-semantic-ownership-01-ar-fix-s1-web \
  --include-playwright --external-limit 0 \
  --run-label wu-semantic-ownership-01-ar-fix-s1
```

- Exit：`0`。
- Fresh result：`status=passed`、`local_cases=11`、`search_cases=4`、`diagnostic_only=4`、`failures=0`、`skips=0`。

```bash
source .venv/bin/activate && \
python utils/smoke_host_public_awaiting_entrypoint.py \
  --workspace-root workspace/tmp/wu-semantic-ownership-01-ar-fix-s1-awaiting \
  --keep-workspace
```

- Exit：`0`。
- Fresh result：packaged composition、timeout claim release、late-publication fence、public terminal outbox 均通过；`TERMINAL_STATUS SUCCEEDED`、`SMOKE PASS Host public awaiting entrypoint`。

### 10.3 Canonical non-coverage full suite 与第二次 stop

```bash
source .venv/bin/activate && \
pytest tests/documents tests/tools tests/host tests/engine tests/runtime \
  tests/service tests/fins tests/cli
```

- Exit：`1`。
- Fresh result：`2 failed, 5175 passed, 10 skipped, 5 deselected, 3 warnings in 156.02s`。
- 允许的唯一中间失败：
  `tests/service/test_import_boundary.py::test_service_does_not_import_forbidden_layers`，精确对应计划声明的 `AR-F02`。
- 未允许且触发 stop 的额外失败：
  `tests/fins/test_sec_downloader.py::test_sec_request_debug_logs_success_response`。
- 直接失败事实：测试调用 `runtime_log.configure(..., stream=log_stream)` 后，SEC request 成功，但 `log_stream.getvalue()` 为空，缺少
  `SEC request reserved: method=GET url=https://example.com/api.json`。
- 该节点在同一 follow-up 的计划指定 Web/runtime/SEC 联跑中 exit `0`；full-order 才失败，因此当前分类为
  `AR-F03 FULL-ORDER REGISTRY RESTORATION NOT CLOSED / CONTROLLER_DECISION_REQUIRED`，不能当作 AR-F02 允许失败，也不能继续覆盖率等门禁。

失败后做过一条只读最小诊断尝试：

```bash
source .venv/bin/activate && python -c '<logger parent/registry probe using dayu.fins.downloaders.sec>'
```

- Exit：`1`；`ModuleNotFoundError: No module named 'dayu.fins.downloaders.sec'`。
- 该命令使用了错误模块路径，不构成 root-cause 证据；没有据此修改任何代码。随后只读定位确认 SEC downloader 位于 `dayu/fins/downloaders/sec_downloader.py`，日志通过 `dayu.fins._log.Log` 动态取得 `dayu.fins.FINS.SEC_DOWNLOADER` logger。未继续执行会改变状态或扩大验证范围的诊断。

## 11. 第二次 stop 后未运行的 mandatory gates

依 authorization §4，canonical 出现第二个失败后立即停止。以下均为
`NOT_RUN_AFTER_SECOND_STOP_RULE`，不得用第一处 stop 前或其它历史结果补签：

- exact single-node-exclusion coverage run、coverage JSON 与 219-path cumulative ledger；
- full pyright；
- full Ruff exact-set final delta；
- wheel/sdist build及文件 hashes；
- six canonical scans；
- full security matrix、configured secret scan、deferred/no-code scans；
- final scope acceptance签署。

README 决定仍为 `NO_UPDATE`：只修改既有测试 fixture/harness/oracle，没有新增测试层级、运行方式或维护规则。Security/secret/deferred/no-code 不能签 fresh full-gate PASS；但当前 scope 检查仍证明 production、README、workflow、config、design、其它 tests/utils 零 diff，Issues 177/178/175/142/151 与 Topic 8/9 owner 均未被实现或改变。

当前 finding / residual 分类：

- `AR-F01`：focused 通过；因 canonical 非允许失败，Slice 不能签最终 closed。
- `AR-F03`：focused 与 standalone Web 通过，但 canonical full-order SEC logging node 失败，`NOT_CLOSED`。
- `AR-F04`：deterministic、focused、fresh real compactor 均通过；因 Slice mandatory gates 未完成，不能签最终 closed。
- `AR-F06 = RETAINED / UNFIXED / UNWAIVED / CURRENT_NO_FIX`。
- `AR-F07 = PENDING_RELEASE_BLOCKER`。
- Slice verdict：`STOPPED / CONTROLLER_DECISION_REQUIRED / NOT_READY_FOR_REVIEW`。
- Next entry point：`Controller validation`；不得自行 review、stage、commit 或进入 Slice 2/3。

## 12. 第二次 Controller stop adjudication 与精确 follow-up 修复

完整读取并核对：

```text
docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-second-stop-controller-adjudication.md
SHA-256 = 7174396e8c923e9e7a142b79f34815358ed2b48f58b8aa0e2a6dbfc0b1cb8b66

docs/host/issues-implementation-control.md
SHA-256 = 03165993336a96f856a69186a82c5a83ba52d85b02076b2fbe38e38b3f6f0d7a
```

Controller verdict：
`AR-F03 ROOT CAUSE CONFIRMED / TEST-HARNESS OWNER FIX AUTHORIZED / NOT_PRODUCTION_DEFECT`。
直接根因是 stdlib logging 在原 registry `PlaceHolder` 位置创建 concrete parent 时会重挂既有 child；旧 harness 只恢复 registry entry，却没有恢复 child `.parent` identity。于是 child 仍指向已从 registry 移除的 logger，绕过原 `dayu` handler。follow-up 只修改既有
`tests/tools/web/test_smoke_web_ci.py`：

- `_LoggerState` 新增 `parent: logging.Logger | None` 并由 `_logger_state()` 快照。
- registry object 与 entries 恢复后，逐一把 root 和所有快照 concrete logger 的 `parent` 回填为原 identity。
- generic fake 创建原 `PlaceHolder` 位置的 concrete parent，明确触发预存 descendant reparent；success/failure 两路均断言触发事实与最终 parent identity 恢复。
- 保留既有 registry instance/entry identity/order、level、handlers、filters、propagate、disabled、handler close 范围断言。
- harness 常量和 contract 没有 `dayu.fins`、SEC 或 production 特例；production、SEC test 与额外 path 均零 diff。

Follow-up entry lock：

```text
branch = phaseflow/host-issues-control
HEAD = ffbf48c2cf5f701c627fda1ebcce7aa1813383ab
staged tree = empty
accepted plan = 7e91421b8bc8c442dcf72e94c20eb84d4f27f2b9878b427481448d6f2f4ea714
control = M / 03165993336a96f856a69186a82c5a83ba52d85b02076b2fbe38e38b3f6f0d7a
accepted-plan validation = ?? / cad213bdb7b02abf9cf4a876a0925e4318df8908cdb1f0bb17090155d3c67114
Slice 1 authorization = ?? / ebb6a9dc92cc4ab24961228891f97442444f4c98228e2693c43aba08328dddcd
first stop adjudication = ?? / db221c9ac75fbb1029ea1ad27ead96e36fe9dd791a4cb81d4f76a90467453762
second stop adjudication = ?? / 7174396e8c923e9e7a142b79f34815358ed2b48f58b8aa0e2a6dbfc0b1cb8b66
```

## 13. 第二次裁决后的 fresh focused / real-smoke ledger

```bash
source .venv/bin/activate
ruff check tests/tools/web/test_smoke_web_ci.py --output-format concise
pytest tests/tools/web/test_smoke_web_ci.py::test_in_process_smoke_harness_restores_complete_logging_state -q
```

- Exit：`0`。
- Fresh result：Ruff `All checks passed!`；topology contract `2 passed, 3 warnings in 0.93s`。
- success/failure 两路均实际触发 descendant reparent，并恢复原 `PlaceHolder` entry 与 descendant parent identity。

```bash
source .venv/bin/activate
pytest tests/tools/web/test_smoke_web_ci.py -q
```

- Exit：`0`；fresh result：`48 passed, 3 warnings in 1.53s`。

```bash
source .venv/bin/activate
pytest tests/tools/web/test_smoke_web_ci.py \
  tests/runtime/test_log.py::test_configure_does_not_touch_root_by_default \
  tests/fins/test_sec_downloader.py::test_sec_request_debug_logs_success_response -q
```

- Exit：`0`；fresh result：`50 passed, 3 warnings in 1.55s`。
- 先前 full-order 暴露的 SEC logging contract 在指定 order-sensitive 序列中恢复通过。

```bash
source .venv/bin/activate
pytest tests/service/test_host_admin.py -q
pytest tests/host/test_public_compact_smoke.py -q
```

- 两条命令分别 exit `0`。
- Fresh result：`1 passed in 0.28s`；`23 passed, 1 skipped in 1.00s`。compact focused 的唯一 skip 仍是未设置 real-smoke 环境变量的既有节点。

```bash
source .venv/bin/activate
DAYU_RUN_REAL_COMPACTOR_SMOKE=1 pytest \
  tests/host/test_public_compact_smoke.py::test_real_compactor_public_opener_compacts_and_preserves_continuity \
  --basetemp=workspace/tmp/wu-semantic-ownership-01-ar-fix-s1-real-compactor -q -rs
```

- Exit：`0`；fresh result：`1 passed in 2.89s`，未 skip。

```bash
source .venv/bin/activate
python utils/smoke_web_ci.py \
  --output-dir workspace/tmp/wu-semantic-ownership-01-ar-fix-s1-web \
  --include-playwright --external-limit 0 \
  --run-label wu-semantic-ownership-01-ar-fix-s1
```

- Exit：`0`。
- Fresh result：`status=passed`、`local_cases=11`、`search_cases=4`、`diagnostic_only=4`、`failures=0`、`skips=0`。

```bash
source .venv/bin/activate
python utils/smoke_host_public_awaiting_entrypoint.py \
  --workspace-root workspace/tmp/wu-semantic-ownership-01-ar-fix-s1-awaiting \
  --keep-workspace
```

- Exit：`0`。
- Fresh result：timeout claim release、late-publication drop、第二次 claim、terminal outbox identity 全部通过；`TERMINAL_STATUS SUCCEEDED`、`SMOKE PASS Host public awaiting entrypoint`。

## 14. Fresh canonical 与 coverage ledger

### 14.1 Canonical non-coverage

```bash
source .venv/bin/activate
pytest tests/documents tests/tools tests/host tests/engine tests/runtime \
  tests/service tests/fins tests/cli
```

- Exit：`1`。
- Fresh result：`1 failed, 5176 passed, 10 skipped, 5 deselected, 3 warnings in 167.93s`。
- 唯一失败为
  `tests/service/test_import_boundary.py::test_service_does_not_import_forbidden_layers`，精确对应计划允许的 Slice 1 `AR-F02` 中间失败。
- 先前第二次 stop 的
  `tests/fins/test_sec_downloader.py::test_sec_request_debug_logs_success_response` 已通过；没有其它失败。
- AR-F06 scheduler node 未排除并真实通过。

### 14.2 Exact single-node-exclusion coverage

```bash
source .venv/bin/activate
COVERAGE_FILE=workspace/tmp/wu-semantic-ownership-01-ar-fix-aggregate.coverage \
  python -m coverage erase
COVERAGE_FILE=workspace/tmp/wu-semantic-ownership-01-ar-fix-aggregate.coverage \
  python -m coverage run --branch -m pytest \
  tests/documents tests/tools tests/host tests/engine tests/runtime tests/service tests/fins tests/cli \
  --deselect=tests/host/test_dispatch_scheduler.py::test_wake_queue_promotion_uses_tracked_async_promotion_task
COVERAGE_FILE=workspace/tmp/wu-semantic-ownership-01-ar-fix-aggregate.coverage \
  python -m coverage json \
  -o workspace/tmp/wu-semantic-ownership-01-ar-fix-aggregate-coverage.json
```

- `coverage erase` exit `0`。
- Coverage pytest exit `1`；fresh result：`1 failed, 5175 passed, 10 skipped, 6 deselected, 3 warnings in 189.88s`。
- 唯一失败仍为计划允许的 `AR-F02`；相对 canonical 唯一新增 deselect 是精确 AR-F06 scheduler node，没有其它排除。
- Coverage JSON exit `0`。
- Coverage data SHA-256：`aab16f1697dadbb70e98b47aba1dbc1f4a005d053de5ae6812302db00164f5e4`。
- Coverage JSON SHA-256：`56d564bd3d1641574f9affe896952ef8f42342bcd9d14a76ef96779d91a95cff`。

按 accepted plan §6.2 从
`3410d7422655c56bdf13c643f77c27f40b9d4550..ffbf48c2cf5f701c627fda1ebcce7aa1813383ab`
取得的现存 changed production Python 集合为 `219` 个且去重后仍为 `219`。按
`covered_lines / num_statements * 100` 计算：`210` 个 `>=80%`；只有计划声明的九个 AR-F05 路径低于 80%，无第十个低覆盖路径：

| 路径 | statements | covered | missing | fresh line coverage | Slice 1 状态 |
| --- | ---: | ---: | ---: | ---: | --- |
| `dayu/documents/processors/docling_processor.py` | 635 | 403 | 232 | 63.46% | `OPEN_BY_SEQUENCE` |
| `dayu/fins/pipelines/sec_6k_rules.py` | 447 | 302 | 145 | 67.56% | `OPEN_BY_SEQUENCE` |
| `dayu/fins/processors/sec_form_section_common.py` | 1098 | 859 | 239 | 78.23% | `OPEN_BY_SEQUENCE` |
| `dayu/fins/processors/sec_report_form_common.py` | 416 | 271 | 145 | 65.14% | `OPEN_BY_SEQUENCE` |
| `dayu/fins/processors/sec_section_build.py` | 303 | 235 | 68 | 77.56% | `OPEN_BY_SEQUENCE` |
| `dayu/fins/processors/sec_table_extraction.py` | 863 | 571 | 292 | 66.16% | `OPEN_BY_SEQUENCE` |
| `dayu/fins/tools/preprocess_tools.py` | 62 | 47 | 15 | 75.81% | `OPEN_BY_SEQUENCE` |
| `dayu/host/_execution_config_projection.py` | 157 | 120 | 37 | 76.43% | `OPEN_BY_SEQUENCE` |
| `dayu/runtime/argparse_exit.py` | 0 | 0 | 0 | 0.00%（JSON 未命中，按规则记 0） | `OPEN_BY_SEQUENCE` |

## 15. Fresh pyright stop evidence

```bash
source .venv/bin/activate
pyright
```

- Exit：`1`。
- Fresh result：`1 error, 0 warnings, 0 informations`。
- 唯一错误：

```text
tests/tools/web/test_smoke_web_ci.py:178:17
Argument of type "tuple[_FilterType, ...]" cannot be assigned to parameter
"filters" of type "tuple[Filter, ...]" in function "__init__"
```

直接原因：stdlib `logging.Logger.filters` 的类型是可同时包含 `logging.Filter` 与实现 `filter()` 的 protocol `_SupportsFilter` 的 `_FilterType`；当前 test-harness `_LoggerState.filters` 窄写为 `tuple[logging.Filter, ...]`。这是授权 test owner 的 typed snapshot contract 缺口，`NOT_PRODUCTION_DEFECT`，但 full pyright 新失败属于 plan §9 / authorization §4 stop condition。依“新失败立即停”要求，没有自行放宽类型、加 cast/ignore、修改 production 或申请额外 path。

因此下列 mandatory gates 均为
`NOT_RUN_AFTER_THIRD_STOP_RULE`，不得用第二次 stop 前或 aggregate 历史结果替代：

- full Ruff final exact-set delta；
- wheel/sdist build及文件 hashes；
- six canonical scans；
- fresh security matrix、configured secret scan、deferred/no-code source scans；
- final README/security/secret/deferred/no-code acceptance与 final Slice exit签署。

## 16. 第三次 stop checkpoint / current verdict

Stop 后只执行 read-only scope/hash 检查并更新本 artifact：

```bash
git rev-parse HEAD
git status --short
git diff --name-status HEAD
git diff --cached --name-status
git diff --check
shasum -a 256 <plan/protected paths/mutable tests/artifact>
```

- Exit：`0`；HEAD 仍为 `ffbf48c2cf5f701c627fda1ebcce7aa1813383ab`。
- `git diff --check` 通过；staged tree仍为空。
- Controller-protected paths 内容未变：

```text
03165993336a96f856a69186a82c5a83ba52d85b02076b2fbe38e38b3f6f0d7a  docs/host/issues-implementation-control.md
cad213bdb7b02abf9cf4a876a0925e4318df8908cdb1f0bb17090155d3c67114  docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-accepted-plan-commit-controller-validation.md
ebb6a9dc92cc4ab24961228891f97442444f4c98228e2693c43aba08328dddcd  docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-implementation-controller-authorization.md
db221c9ac75fbb1029ea1ad27ead96e36fe9dd791a4cb81d4f76a90467453762  docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-stop-controller-adjudication.md
7174396e8c923e9e7a142b79f34815358ed2b48f58b8aa0e2a6dbfc0b1cb8b66  docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-second-stop-controller-adjudication.md
```

- Current mutable test hashes：

```text
5acf57a06d1c7fee82a27ae0c3ccdfcddfe745a42439a514c0551665904f96db  tests/service/test_host_admin.py
7939b24ea4ebc47b903f2a9e90ac434e92ff33f63a649d1fac2ea9ce6ea68bce  tests/tools/web/test_smoke_web_ci.py
f60a1d6e190c948986be355fc66ad71cb64e207691e8a12646ea23cbdcc66169  tests/host/test_public_compact_smoke.py
```

- 扣除五个 protected paths 后，implementation scope 仍精确为三个授权 `M tests/**` 与本唯一授权 `A` artifact；production、SEC test、README、workflow、config、design、其它 tests/utils/artifacts 均零 diff。
- README 决定保持 `NO_UPDATE`：只改变既有 fixture/harness/oracle，不改变测试入口、运行方式、维护层级或用户工作流。
- `AR-F01`、`AR-F03`、`AR-F04` 的 focused/real/canonical/coverage functional evidence已满足预期，但因 full pyright stop 与后续 mandatory gates未完成，不能在本 artifact 签最终 `CLOSED`。
- `AR-F06 = RETAINED / UNFIXED / UNWAIVED / CURRENT_NO_FIX`。
- `AR-F07 = PENDING_RELEASE_BLOCKER`。
- Slice verdict：`STOPPED / CONTROLLER_DECISION_REQUIRED / NOT_READY_FOR_REVIEW`。
- Next entry point：`Controller validation`；不得自行 review、stage、commit、push、PR或进入 Slice 2/3。

## 29. 第五次 Controller adjudication follow-up

完整读取并核对：

```text
docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-fifth-stop-controller-adjudication.md
SHA-256 = 220bf5f98fe3b1a131c08599aeef171b38305993d16f26bc7be306151492e4c8

docs/host/issues-implementation-control.md
SHA-256 = c0d3daa464e154f5591158131ea0a41178e7ae9cd1ed618bc94ebc87c3975d62
```

Controller verdict：
`VALIDATION COMMAND DRIFT / CURRENT NODE IDENTIFIED / NO CODE FIX`。
第五次 follow-up期间没有修改任何代码、plan、design、control、Controller artifact或额外 path；第四次裁决后的 test tree hashes保持不变。

当前唯一由 `DAYU_RUN_LIVE_BROWSER_CLEANUP_SMOKE` 控制、实际走 production Playwright termination path并验证 descendant PIDs消失的 owner node按裁决 fresh运行：

```bash
source .venv/bin/activate
DAYU_RUN_LIVE_BROWSER_CLEANUP_SMOKE=1 pytest \
  tests/tools/web/test_web_tools_provider.py::test_playwright_live_browser_cleanup_smoke_is_manual_and_best_effort \
  -q -rs
```

- Exit：`0`。
- Fresh result：`1 passed in 2.41s`，不是 skip。
- 分类：`REAL_DESCENDANT_CLEANUP_PASS`。先前 §27 的不存在路径属于 plan validation-command drift，现已由 current owner node的真实执行证据取代；没有修改 plan或测试。

## 30. Fresh secret gate stop evidence

Secret gate先从 current `dayu/config/models.json` 的 public `api_key_ref`集合读取当前环境中非空的 configured values；只处理内存中的 value bytes，不输出 value或ref名称。一次非 gate准备探针最初把 `models` 映射误当作 list，exit `1`并仅输出 `AttributeError: 'str' object has no attribute 'get'`；随后只读确认 top-level `models` 为 `dict`并纠正遍历方式，没有修改仓库或掩盖 test/production failure。纠正后的 count probe exit `0`、`configured_secret_value_count=5`。

正式 gate扫描所有 `workspace/tmp/wu-semantic-ownership-01-ar-fix*` slice outputs、本 implementation artifact及 `git diff --binary HEAD`；命令只输出计划允许的三个计数：

```bash
source .venv/bin/activate
python -c '
import json
import os
import subprocess
from pathlib import Path
config = json.loads(Path("dayu/config/models.json").read_text(encoding="utf-8"))
refs = {model["api_key_ref"] for model in config["models"].values() if model.get("api_key_ref")}
secrets = {os.environ[ref].encode() for ref in refs if os.environ.get(ref)}
paths = {path for root in Path("workspace/tmp").glob("wu-semantic-ownership-01-ar-fix*") for path in ([root] if root.is_file() else root.rglob("*")) if path.is_file()}
paths.add(Path("docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-implementation-codex.md"))
blobs = [(str(path), path.read_bytes()) for path in sorted(paths)]
blobs.append(("git-diff://HEAD", subprocess.run(["git", "diff", "--binary", "HEAD"], check=True, capture_output=True).stdout))
match_count = sum(blob.count(secret) for _, blob in blobs for secret in secrets)
matched_path_count = sum(any(secret in blob for secret in secrets) for _, blob in blobs)
print(f"configured_secret_value_count={len(secrets)}")
print(f"secret_value_match_count={match_count}")
print(f"matched_path_count={matched_path_count}")
'
```

- Process exit：`0`；scan执行本身完成。
- Fresh semantic result：

```text
configured_secret_value_count=5
secret_value_match_count=3
matched_path_count=1
```

- Gate verdict：`FAIL / SECRET_VALUE_MATCH_NONZERO / CONTROLLER_DECISION_REQUIRED`。
- 依 plan §6.7与原 authorization stop rule，要求是 `0` value match；当前 `3` occurrences / `1` matched path不满足。没有输出 secret value、ref名称或matched path，没有打开/定位命中内容，也没有据此猜测 production defect、fixture false positive或允许清理的额外 path。
- 此 failure与 AR-F02允许的 canonical/coverage单节点中间失败无关，不能 waiver；在这里立即停止。

因此下列第五次裁决要求的剩余 final gates为 `NOT_RUN_AFTER_SECRET_GATE_STOP`：

- deferred Issue 177/178/175/142/151 fresh source scans与 final ledger acceptance；
- Topic 8 / Codex F-13 / Topic 9 no-code fresh source scans与 final ledger acceptance；
- README final acceptance（先前 `NO_UPDATE`判断保留为历史判断，不冒充本 follow-up final gate）；
- Slice 1 final exit与 AR-F01、AR-F03、AR-F04正式 `CLOSED`签署。

## 31. Sixth stop read-only checkpoint / current verdict

Secret gate stop后只执行以下 read-only checkpoint并更新本 artifact：

```bash
git rev-parse HEAD
git status --short
git diff --name-status HEAD
git diff --cached --name-status
git diff --check
shasum -a 256 <eight protected paths/three mutable tests/implementation artifact>
```

- Exit：`0`；HEAD仍为 `ffbf48c2cf5f701c627fda1ebcce7aa1813383ab`。
- `git diff --check`通过；`git diff --cached --name-status`为空，staged tree为空。
- 八个 Controller-protected paths内容未变：

```text
c0d3daa464e154f5591158131ea0a41178e7ae9cd1ed618bc94ebc87c3975d62  docs/host/issues-implementation-control.md
cad213bdb7b02abf9cf4a876a0925e4318df8908cdb1f0bb17090155d3c67114  docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-accepted-plan-commit-controller-validation.md
ebb6a9dc92cc4ab24961228891f97442444f4c98228e2693c43aba08328dddcd  docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-implementation-controller-authorization.md
db221c9ac75fbb1029ea1ad27ead96e36fe9dd791a4cb81d4f76a90467453762  docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-stop-controller-adjudication.md
7174396e8c923e9e7a142b79f34815358ed2b48f58b8aa0e2a6dbfc0b1cb8b66  docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-second-stop-controller-adjudication.md
52524fdfd0e819a5c311e2a967f84667b29a1c66c57f791234e1f794ca7fe418  docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-third-stop-controller-adjudication.md
ac5cf521d2f76a73fa42132a2b7374b47b42d91273d5da1458a9788d20e6c88d  docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-fourth-stop-controller-adjudication.md
220bf5f98fe3b1a131c08599aeef171b38305993d16f26bc7be306151492e4c8  docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-fifth-stop-controller-adjudication.md
```

- Current mutable test hashes（本次 artifact更新前的测试树）：

```text
5acf57a06d1c7fee82a27ae0c3ccdfcddfe745a42439a514c0551665904f96db  tests/service/test_host_admin.py
86968b937d4289d29427a2bd68934a074ca0499dfa3563ec326eae73f2432ee3  tests/tools/web/test_smoke_web_ci.py
f60a1d6e190c948986be355fc66ad71cb64e207691e8a12646ea23cbdcc66169  tests/host/test_public_compact_smoke.py
```

- `git status --short`只有八个 protected paths、三个授权 mutable tests和本唯一授权 implementation artifact；扣除 protected集合后，scope精确为三个授权 `M tests/**`与本 `A` artifact。
- Production、SEC test、README、workflow、config、design、其它 tests/utils/artifacts均零 diff；第五次 follow-up代码 delta为零。
- 第五次 current-owner live-browser真实 cleanup通过；此前已完成的 pyright、canonical/coverage、三项 Slice 1 real smoke、Ruff、build、six scans与 local security matrices证据保持有效。
- 但 fresh secret gate非零，且 deferred/no-code/README final gates未运行，故 `AR-F01`、`AR-F03`、`AR-F04`仍不能正式签 `CLOSED`。
- `AR-F06 = RETAINED / UNFIXED / UNWAIVED / CURRENT_NO_FIX`。
- `AR-F07 = PENDING_RELEASE_BLOCKER`。
- Slice verdict：`STOPPED / CONTROLLER_DECISION_REQUIRED / NOT_READY_FOR_REVIEW`。
- Next entry point：`Controller validation`；不得自行定位 secret匹配、review、stage、commit、push、PR或进入 Slice 2/3。

## 19. 第四次 Controller adjudication follow-up

完整读取并核对：

```text
docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-fourth-stop-controller-adjudication.md
SHA-256 = ac5cf521d2f76a73fa42132a2b7374b47b42d91273d5da1458a9788d20e6c88d

docs/host/issues-implementation-control.md
SHA-256 = 0fb6650f758bf7864933854b6b743d17e3d244e0787c10df035c11fc6aa64e21
```

Controller verdict：
`PUBLIC PROTOCOL CALL-SHAPE TOO STRICT / SAME-LINE FIX AUTHORIZED / NOT_PRODUCTION_DEFECT`。
依精确授权，只在 `tests/tools/web/test_smoke_web_ci.py` 把：

```python
def filter(self, record: logging.LogRecord) -> bool:
```

改为：

```python
def filter(self, record: logging.LogRecord, /) -> bool:
```

该修改只纠正 public structural Protocol 的调用形状：logging consumer只要求位置调用，不额外要求实现者接受 `record=` 关键字。其它 union、snapshot/restore、logger parent identity、registry/handler/filter identity/order与 success/failure contract均零运行时变化；未使用 private logging/typeshed type、cast、ignore、`Any`、`object`或额外 path。

Follow-up entry lock：

```text
branch = phaseflow/host-issues-control
HEAD = ffbf48c2cf5f701c627fda1ebcce7aa1813383ab
staged tree = empty
control = M / 0fb6650f758bf7864933854b6b743d17e3d244e0787c10df035c11fc6aa64e21
accepted-plan validation = ?? / cad213bdb7b02abf9cf4a876a0925e4318df8908cdb1f0bb17090155d3c67114
Slice 1 authorization = ?? / ebb6a9dc92cc4ab24961228891f97442444f4c98228e2693c43aba08328dddcd
first stop adjudication = ?? / db221c9ac75fbb1029ea1ad27ead96e36fe9dd791a4cb81d4f76a90467453762
second stop adjudication = ?? / 7174396e8c923e9e7a142b79f34815358ed2b48f58b8aa0e2a6dbfc0b1cb8b66
third stop adjudication = ?? / 52524fdfd0e819a5c311e2a967f84667b29a1c66c57f791234e1f794ca7fe418
fourth stop adjudication = ?? / ac5cf521d2f76a73fa42132a2b7374b47b42d91273d5da1458a9788d20e6c88d
```

## 20. Fourth-adjudication fresh preflight ledger

```bash
source .venv/bin/activate
pyright tests/tools/web/test_smoke_web_ci.py
```

- Exit：`0`；fresh result：`0 errors, 0 warnings, 0 informations`。

```bash
source .venv/bin/activate
pyright
```

- Exit：`0`；fresh result：`0 errors, 0 warnings, 0 informations`。

```bash
source .venv/bin/activate
pytest tests/tools/web/test_smoke_web_ci.py::test_in_process_smoke_harness_restores_complete_logging_state -q
```

- Exit：`0`；fresh result：`2 passed, 3 warnings in 0.93s`。
- success/failure 两路均触发 descendant reparent，并精确恢复原 `PlaceHolder` registry entry、snapshot logger parent identity及所有既有 logger/handler/filter/state contract。

```bash
source .venv/bin/activate
pytest tests/tools/web/test_smoke_web_ci.py -q
```

- Exit：`0`；fresh result：`48 passed, 3 warnings in 1.50s`。

```bash
source .venv/bin/activate
pytest tests/tools/web/test_smoke_web_ci.py \
  tests/runtime/test_log.py::test_configure_does_not_touch_root_by_default \
  tests/fins/test_sec_downloader.py::test_sec_request_debug_logs_success_response -q
```

- Exit：`0`；fresh result：`50 passed, 3 warnings in 1.54s`。
- full pyright 与三组 functional tests共同证明 positional-only 修正满足 strict public type contract，且没有改变 logging runtime identity/order行为。

## 21. Final-tree fresh canonical / coverage ledger

### 21.1 Canonical non-coverage

```bash
source .venv/bin/activate
pytest tests/documents tests/tools tests/host tests/engine tests/runtime \
  tests/service tests/fins tests/cli
```

- Exit：`1`，属于 Slice 1 明确允许的单节点中间状态，不标记为全绿。
- Fresh result：`1 failed, 5176 passed, 10 skipped, 5 deselected, 3 warnings in 177.42s`。
- 唯一失败为
  `tests/service/test_import_boundary.py::test_service_does_not_import_forbidden_layers`，精确对应计划声明的 `AR-F02`。
- AR-F06 scheduler node未排除并真实通过；没有其它 failure、额外 skip或额外 deselect。

### 21.2 Exact single-node-exclusion coverage

```bash
source .venv/bin/activate
COVERAGE_FILE=workspace/tmp/wu-semantic-ownership-01-ar-fix-aggregate.coverage \
  python -m coverage erase
COVERAGE_FILE=workspace/tmp/wu-semantic-ownership-01-ar-fix-aggregate.coverage \
  python -m coverage run --branch -m pytest \
  tests/documents tests/tools tests/host tests/engine tests/runtime tests/service tests/fins tests/cli \
  --deselect=tests/host/test_dispatch_scheduler.py::test_wake_queue_promotion_uses_tracked_async_promotion_task
COVERAGE_FILE=workspace/tmp/wu-semantic-ownership-01-ar-fix-aggregate.coverage \
  python -m coverage json \
  -o workspace/tmp/wu-semantic-ownership-01-ar-fix-aggregate-coverage.json
```

- `coverage erase` exit `0`。
- Coverage pytest exit `1`；fresh result：`1 failed, 5175 passed, 10 skipped, 6 deselected, 3 warnings in 183.40s`。
- 唯一失败仍是计划允许的 `AR-F02`；相对 canonical唯一新增 deselect是精确 AR-F06 scheduler node，无其它排除。
- Coverage JSON exit `0`。
- Coverage data SHA-256：`79ce8546f4b24b2290928d19e1f66f78e8e67cc63774e1cb7c17f814c8de8a0e`。
- Coverage JSON SHA-256：`bf8a2133f911f2e196f18d48f8851de843ac5c6a2073f33465a9418549e8fd8a`。

按 accepted plan §6.2 从
`3410d7422655c56bdf13c643f77c27f40b9d4550..ffbf48c2cf5f701c627fda1ebcce7aa1813383ab`
取得的 changed production Python 集合为 `219`，排序去重后仍为 `219`。Fresh JSON ledger：`210` 个 `>=80.00%`；只有计划声明的九个 AR-F05 路径低于 80%，无第十个低覆盖路径：

| 路径 | statements | covered | missing | fresh line coverage | Slice 1 状态 |
| --- | ---: | ---: | ---: | ---: | --- |
| `dayu/documents/processors/docling_processor.py` | 635 | 403 | 232 | 63.46% | `OPEN_BY_SEQUENCE` |
| `dayu/fins/pipelines/sec_6k_rules.py` | 447 | 302 | 145 | 67.56% | `OPEN_BY_SEQUENCE` |
| `dayu/fins/processors/sec_form_section_common.py` | 1098 | 859 | 239 | 78.23% | `OPEN_BY_SEQUENCE` |
| `dayu/fins/processors/sec_report_form_common.py` | 416 | 271 | 145 | 65.14% | `OPEN_BY_SEQUENCE` |
| `dayu/fins/processors/sec_section_build.py` | 303 | 235 | 68 | 77.56% | `OPEN_BY_SEQUENCE` |
| `dayu/fins/processors/sec_table_extraction.py` | 863 | 571 | 292 | 66.16% | `OPEN_BY_SEQUENCE` |
| `dayu/fins/tools/preprocess_tools.py` | 62 | 47 | 15 | 75.81% | `OPEN_BY_SEQUENCE` |
| `dayu/host/_execution_config_projection.py` | 157 | 120 | 37 | 76.43% | `OPEN_BY_SEQUENCE` |
| `dayu/runtime/argparse_exit.py` | 0 | 0 | 0 | 0.00%（JSON未命中，按规则记0） | `OPEN_BY_SEQUENCE` |

## 22. Final-tree fresh Slice 1 real smokes

```bash
source .venv/bin/activate
DAYU_RUN_REAL_COMPACTOR_SMOKE=1 pytest \
  tests/host/test_public_compact_smoke.py::test_real_compactor_public_opener_compacts_and_preserves_continuity \
  --basetemp=workspace/tmp/wu-semantic-ownership-01-ar-fix-s1-real-compactor -q -rs
```

- Exit：`0`；fresh result：`1 passed in 3.15s`，未 skip。
- 两轮 terminal、manifest run identity -> request digest -> compact artifact digest唯一关联，以及 `input_snapshot_refs.current_input_ref` 的字段存在、`str`、非空 continuity contract均通过。

```bash
source .venv/bin/activate
python utils/smoke_web_ci.py \
  --output-dir workspace/tmp/wu-semantic-ownership-01-ar-fix-s1-web \
  --include-playwright --external-limit 0 \
  --run-label wu-semantic-ownership-01-ar-fix-s1
```

- Exit：`0`。
- Fresh result：`status=passed`、`local_cases=11`、`search_cases=4`、`diagnostic_only=4`、`failures=0`、`skips=0`。

```bash
source .venv/bin/activate
python utils/smoke_host_public_awaiting_entrypoint.py \
  --workspace-root workspace/tmp/wu-semantic-ownership-01-ar-fix-s1-awaiting \
  --keep-workspace
```

- Exit：`0`。
- Fresh result：claim timeout release、late-publication fence/drop、reclaim及 terminal outbox identity通过；`TERMINAL_STATUS SUCCEEDED`、`SMOKE PASS Host public awaiting entrypoint`。

## 23. Final-tree fresh Ruff exact delta

```bash
source .venv/bin/activate
ruff check dayu tests utils --output-format json \
  --output-file workspace/tmp/wu-semantic-ownership-01-ar-fix-s1-final-ruff.json
```

- Ruff自身 exit `1`，因为 immutable baseline存在 findings；未把 pipeline/tool exit冒充通过。
- Entry规范化集合为 `144`，final规范化集合为 `143`。
- 精确集合差：`ADDED=0`、`REMOVED=1`；唯一移除是 `tests/tools/web/test_smoke_web_ci.py` entry时的 E402 finding。

```bash
source .venv/bin/activate
ruff check tests/service/test_host_admin.py \
  tests/tools/web/test_smoke_web_ci.py \
  tests/host/test_public_compact_smoke.py --output-format concise
```

- Exit：`0`；fresh result：`All checks passed!`。
- 结论：完整 Ruff set相对 slice base零新增，三个 mutable tests零 finding，满足 plan §6.3 exact-delta规则。

## 24. Final-tree fresh build

```bash
source .venv/bin/activate
python -m build \
  --outdir workspace/tmp/wu-semantic-ownership-01-ar-fix-s1-final-build
```

- Exit：`0`；wheel与sdist均生成。

```text
dayu_agent-0.1.4-py3-none-any.whl
bytes = 2101532
SHA-256 = bf95279cf518e16b0d6b8e4d49c27c1309faf3bcffe7fad59395ff6f90a5edaa

dayu_agent-0.1.4.tar.gz
bytes = 1836409
SHA-256 = 6585ba29a50a8ce8f39a5aa4b6e0b47e222a4c44d20ef8a817a107636e78b68b
```

输出只在 gitignored `workspace/tmp`与 build工具既有临时目录，visible worktree未新增 build path。

## 25. Final-tree fresh six canonical scans

逐条执行 accepted plan §6.6 原命令：

```bash
rg -n 'DocResourceBudget|SourceBudgetExceeded|source_budget_exceeded|directory_entry_limit|source_limit|skipped_oversized_files' dayu tests README.md
rg -n 'llm_safe_replay_arguments|arguments_summary_unsafe|_INTERNAL_SOURCE_REF_KINDS' dayu tests
rg -n 'stage_source_document|ingest_complete.*false|owner_scope_id|owner_token|_BATCH_OWNER_CONTEXT|_execute_with_auto_batch' dayu/fins tests/fins
rg -n 'statement_locator|statement_method_missing|raw_total|deduped_count' dayu/fins/tools dayu/fins/domain tests/fins
rg -n '\btotal\b|raw_total' dayu/fins/domain/xbrl_result_contract.py dayu/fins/processors tests/fins
rg -n 'schema_version.*commands|JSON argv|dayu-web|dayu-wechat|dayu-render' pyproject.toml dayu tests README.md
```

- S1、S2、S3、S4分别 exit `1`，均为 `0` match；这是 rg zero-match语义，不是 scan error。
- S5 exit `0`：共 `48` occurrences；`raw_total=0`、fixture `34`、non-fixture `14`，落在 `10` 个路径，均属于 accepted immutable fixture/财务 `total` 术语分类，无新 stale public semantic或 raw-total projection。
- S6 exit `0`：精确 `3` 个 accepted operational-label命中：
  - `tests/tools/web/test_diagnose_web_access.py` 的 `dayu-web` diagnostic filename；
  - `tests/tools/web/test_web_tools_provider.py` 的 temp directory name；
  - `dayu/tools/web/web_playwright_backend.py` 的 cleanup label。
- S6没有 console script、removed entrypoint、public JSON argv/schema或 README承诺命中。

## 26. Final-tree fresh local security matrices

```bash
source .venv/bin/activate
pytest tests/tools/test_doc_tools_provider.py tests/tools/web -q
```

- Exit：`0`；fresh result：`346 passed, 1 skipped, 3 warnings in 18.45s`。
- 覆盖 Doc path containment/output truncation与 Web DNS/private/proxy/redirect/diagnostic owner矩阵。

```bash
source .venv/bin/activate
pytest tests/host/test_accepted_result_projection.py \
  tests/host/test_run_input_builder.py \
  tests/host/test_memory_projection.py \
  tests/host/test_compact_material.py \
  tests/host/test_compact_pipeline.py \
  tests/host/test_context_compact_events.py \
  tests/host/test_tool_trace_projection.py \
  tests/host/test_tool_trace_queries.py \
  tests/host/test_wait_observation_runner.py \
  tests/host/test_wait_adapter_polling.py \
  tests/host/test_wait_awaiting_accept.py \
  tests/host/test_phase7_waiting_integration.py \
  tests/engine/test_agent_phase3_tool_call.py -q
```

- Exit：`0`；fresh result：`493 passed in 3.75s`。
- 覆盖 Host digest/EventLog/opaque-ref、compact/trace、wait claim与 late-publication owner矩阵。

```bash
source .venv/bin/activate
pytest tests/fins -q
```

- Exit：`0`；fresh result：`950 passed, 1 skipped, 3 warnings in 39.04s`。
- 覆盖 Fins transaction/atomic swap/path containment/opaque id/direct validator及 deterministic HKEX矩阵。

```bash
source .venv/bin/activate
pytest \
  tests/cli/test_upload_filings_from_command.py::test_upload_filings_from_default_output_generates_posix_script_and_summary \
  tests/cli/test_upload_filings_from_command.py::test_posix_script_round_trips_adversarial_argv_with_real_sh \
  tests/cli/test_upload_filings_from_command.py::test_posix_generated_script_runs_real_cli_into_temp_storage \
  tests/cli/test_init_smoke.py -q
```

- Exit：`0`；fresh result：`8 passed, 5 skipped, 3 warnings in 24.49s`。
- 五个 skip均为 Darwin上不可执行的真实 Windows nodes，未计作成功；`AR-F07 = PENDING_RELEASE_BLOCKER`。

## 27. Fifth stop evidence — mandatory live-browser node path missing

随后执行 accepted plan §6.8 / fourth adjudication要求的 live-browser cleanup命令：

```bash
source .venv/bin/activate
DAYU_RUN_LIVE_BROWSER_CLEANUP_SMOKE=1 pytest \
  tests/tools/web/test_web_playwright_backend.py::test_playwright_live_browser_cleanup_terminates_descendants \
  -q -rs
```

- Exit：`4`。
- Fresh result：

```text
ERROR: file or directory not found:
tests/tools/web/test_web_playwright_backend.py::test_playwright_live_browser_cleanup_terminates_descendants

no tests ran
```

当前树不存在计划指定的测试文件/node，属于
`PLAN_VALIDATION_NODE_PATH_MISSING / CONTROLLER_DECISION_REQUIRED / NOT_PRODUCTION_DEFECT`。
这不是允许的 AR-F02 canonical/coverage中间失败，也不能把未运行冒充 real smoke成功。依第四次裁决“任何新错误、失败或额外path需求再次停止”，在此立即停止；未搜索、猜测或代用其它 node，未修改生产代码/其它测试/plan/control，也未申请额外 path。

因此以下门禁为 `NOT_RUN_AFTER_FIFTH_STOP_RULE`，不得使用本次 stop前或历史结果补签：

- configured-secret scan及零 value-match acceptance；
- deferred source scan与 Issue 177/178/175/142/151 final acceptance；
- no-code Topic 8/9 source scan及 final acceptance；
- README/security/secret/deferred/no-code完整最终签署；
- final Slice exit / AR-F01、AR-F03、AR-F04正式 `CLOSED` 签署。

已完成的 fresh canonical、coverage、real smokes、Ruff、build、six scans与 local security matrices只作为当前树直接证据保留；它们不覆盖上述未完成门禁，也不把 stopped slice标成 ready for review。

## 28. Fifth stop checkpoint / current verdict

Stop 后只执行 read-only scope/hash检查并更新本 artifact：

```bash
git rev-parse HEAD
git status --short
git diff --name-status HEAD
git diff --cached --name-status
git diff --check
shasum -a 256 <protected paths/mutable tests/artifact>
```

- Exit：`0`；HEAD仍为 `ffbf48c2cf5f701c627fda1ebcce7aa1813383ab`。
- `git diff --check`通过；staged tree为空。
- 七个 Controller-protected paths内容未变：

```text
0fb6650f758bf7864933854b6b743d17e3d244e0787c10df035c11fc6aa64e21  docs/host/issues-implementation-control.md
cad213bdb7b02abf9cf4a876a0925e4318df8908cdb1f0bb17090155d3c67114  docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-accepted-plan-commit-controller-validation.md
ebb6a9dc92cc4ab24961228891f97442444f4c98228e2693c43aba08328dddcd  docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-implementation-controller-authorization.md
db221c9ac75fbb1029ea1ad27ead96e36fe9dd791a4cb81d4f76a90467453762  docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-stop-controller-adjudication.md
7174396e8c923e9e7a142b79f34815358ed2b48f58b8aa0e2a6dbfc0b1cb8b66  docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-second-stop-controller-adjudication.md
52524fdfd0e819a5c311e2a967f84667b29a1c66c57f791234e1f794ca7fe418  docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-third-stop-controller-adjudication.md
ac5cf521d2f76a73fa42132a2b7374b47b42d91273d5da1458a9788d20e6c88d  docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-fourth-stop-controller-adjudication.md
```

- Current mutable test hashes（本次 artifact更新前的测试树）：

```text
5acf57a06d1c7fee82a27ae0c3ccdfcddfe745a42439a514c0551665904f96db  tests/service/test_host_admin.py
86968b937d4289d29427a2bd68934a074ca0499dfa3563ec326eae73f2432ee3  tests/tools/web/test_smoke_web_ci.py
f60a1d6e190c948986be355fc66ad71cb64e207691e8a12646ea23cbdcc66169  tests/host/test_public_compact_smoke.py
```

- 扣除七个 protected paths后，scope仍精确为三个授权 `M tests/**`与本唯一授权 `A` implementation artifact；production、SEC test、README、workflow、config、design、其它 tests/utils/artifacts均零 diff。
- README决定保持 `NO_UPDATE`：本 follow-up只纠正既有 test harness Protocol调用形状，不改变测试入口、运行方式、维护层级或用户工作流；authorization同时禁止 README diff。
- Security：已运行的 local matrices通过，但 mandatory live-browser cleanup node path冲突导致完整 security gate不能最终签 PASS。
- Secret/deferred/no-code：没有观察到代码或scope变更，但因 stop rule后的指定 final scans未运行，均不冒充 gate PASS。
- `AR-F01`、`AR-F03`、`AR-F04` 的 owner/focused/canonical/coverage/real-smoke证据符合预期，但因 mandatory validation path冲突与剩余 gates未完成，不能签最终 `CLOSED`。
- `AR-F06 = RETAINED / UNFIXED / UNWAIVED / CURRENT_NO_FIX`。
- `AR-F07 = PENDING_RELEASE_BLOCKER`。
- Slice verdict：`STOPPED / CONTROLLER_DECISION_REQUIRED / NOT_READY_FOR_REVIEW`。
- Next entry point：`Controller validation`；不得自行 review、stage、commit、push、PR或进入 Slice 2/3。

## 17. 第三次 Controller adjudication follow-up

完整读取并核对：

```text
docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-third-stop-controller-adjudication.md
SHA-256 = 52524fdfd0e819a5c311e2a967f84667b29a1c66c57f791234e1f794ca7fe418

docs/host/issues-implementation-control.md
SHA-256 = 4444703745711afe6d196ce2a1f6f13c6f0f601c3f16e638a812051628af3450
```

Controller verdict：
`TEST SNAPSHOT TYPE OWNER DEFECT / SAME-FILE FIX AUTHORIZED / NOT_PRODUCTION_DEFECT`。
依精确授权，只在 `tests/tools/web/test_smoke_web_ci.py`：

- 从 `collections.abc` 使用 public `Callable`，从 `typing` 使用 public `Protocol`。
- 定义 module-level `_LogRecordFilter`，只声明
  `filter(self, record: logging.LogRecord) -> bool`。
- 定义 `_LoggerFilter = logging.Filter | Callable[[logging.LogRecord], bool] | _LogRecordFilter`，把 `_LoggerState.filters` 改为 `tuple[_LoggerFilter, ...]`。
- `_logger_state()` 仍直接 `tuple(logger.filters)`；恢复仍为
  `state.logger.filters[:] = state.filters`，没有改变 identity/order 或任何运行时行为。
- 没有引用/复制 `logging._FilterType` 或 private typeshed；没有新增 cast、ignore、`Any`、`object`、fallback 或额外 path。

Follow-up entry lock：

```text
branch = phaseflow/host-issues-control
HEAD = ffbf48c2cf5f701c627fda1ebcce7aa1813383ab
staged tree = empty
control = M / 4444703745711afe6d196ce2a1f6f13c6f0f601c3f16e638a812051628af3450
accepted-plan validation = ?? / cad213bdb7b02abf9cf4a876a0925e4318df8908cdb1f0bb17090155d3c67114
Slice 1 authorization = ?? / ebb6a9dc92cc4ab24961228891f97442444f4c98228e2693c43aba08328dddcd
first stop adjudication = ?? / db221c9ac75fbb1029ea1ad27ead96e36fe9dd791a4cb81d4f76a90467453762
second stop adjudication = ?? / 7174396e8c923e9e7a142b79f34815358ed2b48f58b8aa0e2a6dbfc0b1cb8b66
third stop adjudication = ?? / 52524fdfd0e819a5c311e2a967f84667b29a1c66c57f791234e1f794ca7fe418
```

### 17.1 Fresh required preflight tests

```bash
source .venv/bin/activate
pytest tests/tools/web/test_smoke_web_ci.py::test_in_process_smoke_harness_restores_complete_logging_state -q
```

- Exit：`0`；fresh result：`2 passed, 3 warnings in 0.94s`。

```bash
source .venv/bin/activate
pytest tests/tools/web/test_smoke_web_ci.py -q
```

- Exit：`0`；fresh result：`48 passed, 3 warnings in 1.53s`。

```bash
source .venv/bin/activate
pytest tests/tools/web/test_smoke_web_ci.py \
  tests/runtime/test_log.py::test_configure_does_not_touch_root_by_default \
  tests/fins/test_sec_downloader.py::test_sec_request_debug_logs_success_response -q
```

- Exit：`0`；fresh result：`50 passed, 3 warnings in 1.56s`。

三条 functional 命令证明 filter type-only 修改没有改变 logging topology、filter identity/order、handler close 范围或 SEC 捕获行为。

### 17.2 Fresh full pyright stop evidence

```bash
source .venv/bin/activate
pyright
```

- Exit：`1`。
- Fresh result：`1 error, 0 warnings, 0 informations`。
- 唯一错误：

```text
tests/tools/web/test_smoke_web_ci.py:199:17
Argument of type "tuple[_FilterType, ...]" cannot be assigned to parameter
"filters" of type "tuple[_LoggerFilter, ...]" in function "__init__"
Type "_SupportsFilter" is incompatible with protocol "_LogRecordFilter"
```

直接结论：第三次裁决指定的 public 三分 union 已表达在 test owner 中，但当前 pyright/typeshed 仍不认为其 private `_SupportsFilter` 成员满足这个 public Protocol。裁决禁止读取/复制 private typeshed、private `_FilterType`、cast/ignore/`Any`/`object`；因此不能通过猜测 positional-only、返回类型或其它隐藏签名细节继续修改。该结果属于
`PUBLIC_PROTOCOL_SHAPE_STILL_INCOMPATIBLE / CONTROLLER_DECISION_REQUIRED / NOT_PRODUCTION_DEFECT`。

依“任何额外 pyright 错误、测试失败或额外 path需求再次停止”，以下均为
`NOT_RUN_AFTER_FOURTH_STOP_RULE`：

- final-tree canonical non-coverage full suite；
- final-tree exact-exclusion coverage、JSON 与 219-path ledger；
- final-tree real compactor、standalone Web 与 public-awaiting smokes；
- full Ruff final exact-set delta；
- wheel/sdist build；
- six scans；
- security/secret/deferred/no-code 与 final scope acceptance gates。

第三次 stop 前 §14 的 canonical/coverage 证据没有被复用为当前 final-tree gate。

## 18. 第四次 stop checkpoint / current verdict

Stop 后只执行 read-only scope/hash 检查并更新本 artifact：

```bash
git rev-parse HEAD
git status --short
git diff --name-status HEAD
git diff --cached --name-status
git diff --check
shasum -a 256 <protected paths/mutable tests/artifact>
```

- Exit：`0`；HEAD 仍为 `ffbf48c2cf5f701c627fda1ebcce7aa1813383ab`。
- `git diff --check` 通过；staged tree 为空。
- 六个 Controller-protected paths 内容未变：

```text
4444703745711afe6d196ce2a1f6f13c6f0f601c3f16e638a812051628af3450  docs/host/issues-implementation-control.md
cad213bdb7b02abf9cf4a876a0925e4318df8908cdb1f0bb17090155d3c67114  docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-accepted-plan-commit-controller-validation.md
ebb6a9dc92cc4ab24961228891f97442444f4c98228e2693c43aba08328dddcd  docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-implementation-controller-authorization.md
db221c9ac75fbb1029ea1ad27ead96e36fe9dd791a4cb81d4f76a90467453762  docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-stop-controller-adjudication.md
7174396e8c923e9e7a142b79f34815358ed2b48f58b8aa0e2a6dbfc0b1cb8b66  docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-second-stop-controller-adjudication.md
52524fdfd0e819a5c311e2a967f84667b29a1c66c57f791234e1f794ca7fe418  docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-third-stop-controller-adjudication.md
```

- Current mutable test hashes before本次 artifact 更新：

```text
5acf57a06d1c7fee82a27ae0c3ccdfcddfe745a42439a514c0551665904f96db  tests/service/test_host_admin.py
5538d850507044087150db47ff20a36eb53be2567a6f1857e3aad3fa4e9f574d  tests/tools/web/test_smoke_web_ci.py
f60a1d6e190c948986be355fc66ad71cb64e207691e8a12646ea23cbdcc66169  tests/host/test_public_compact_smoke.py
```

- 扣除六个 protected paths 后，scope 仍精确为三个授权 `M tests/**` 与本唯一授权 `A` artifact；production、SEC test、README、workflow、config、design、其它 tests/utils/artifacts 均零 diff。
- README 保持 `NO_UPDATE`；本 follow-up 只改变测试 harness 类型描述，不改变测试入口、维护规则或用户工作流。
- `AR-F01`、`AR-F03`、`AR-F04` 仍不能在未完成 full pyright 与 final-tree mandatory gates时签最终 `CLOSED`。
- `AR-F06 = RETAINED / UNFIXED / UNWAIVED / CURRENT_NO_FIX`。
- `AR-F07 = PENDING_RELEASE_BLOCKER`。
- Slice verdict：`STOPPED / CONTROLLER_DECISION_REQUIRED / NOT_READY_FOR_REVIEW`。
- Next entry point：`Controller validation`；不得自行 review、stage、commit、push、PR或进入 Slice 2/3。

## 32. Local-trust verification implementation continuation

### 32.1 Gate identity / entry lock

- 时间：`2026-07-19 09:28:34 +0800`。
- Gate：同一 `WU-SEMANTIC-OWNERSHIP-01` aggregate regression fix Slice 1
  local-trust verification implementation continuation；没有进入 Slice 2/3。
- Branch：`phaseflow/host-issues-control`。
- HEAD：`ffbf48c2cf5f701c627fda1ebcce7aa1813383ab`。
- Staged tree：entry 与 exit 均为空。
- Final corrected plan SHA-256：
  `afaa18c5608e6eeae0046318865bd1b3dd2f9a176c4b0739aa5b099e0ae3a252`。
- Controller adjudication SHA-256：
  `5abc0505e2ed7e47763557bfa53201afd5fd99f16d2c98115d04febdbcb3f59c`。
- Resume authorization SHA-256：
  `32f172375d49b505e8dbeeb15034d650ee83eed6e38402e6b6002e3d13315f50`。
- Control entry SHA-256：
  `33480745dc82e352c8dad5800c63059b474fce7720e9d97225e65d24672b330a`。
- 本 artifact entry：1245 lines / SHA-256
  `05800914dfd66912c05ca7eef4d8cacfab1a506572b161c4ce39362a4443b32a`。

Entry 时已用 `git status --short` 与 `shasum -a 256` 记录全部 pre-existing
tracked/untracked paths。前三个既有 mutable test hashes精确匹配授权：

```text
5acf57a06d1c7fee82a27ae0c3ccdfcddfe745a42439a514c0551665904f96db  tests/service/test_host_admin.py
86968b937d4289d29427a2bd68934a074ca0499dfa3563ec326eae73f2432ee3  tests/tools/web/test_smoke_web_ci.py
f60a1d6e190c948986be355fc66ad71cb64e207691e8a12646ea23cbdcc66169  tests/host/test_public_compact_smoke.py
```

后五个 owner test entry hashes也逐项匹配 authorization §1：

```text
6b08be06304776ba08f3a00b7c40a0e031d45c16f28203b7b52761567e5da347  tests/host/test_audit_sink.py
236dde54dcdd38428fea84784091fa63a049931a5495bb883da127e8b784ffbd  tests/host/test_tool_trace_projection.py
798a7000086b5b0cc16565c0d34c78ddc6ae8b0d8eab6d81b8cfa8aa196fb9db  tests/host/test_host_activity_event_projection.py
f4e90d9baa4db40e06a13919ae96c9632ab09075ac504a791529e49e8f91cab3  tests/host/test_run_input_builder.py
12227f892d059116d48c78f1311a2f69a40e524eff1acfb476e2286b8cd1ec21  tests/host/test_logging.py
```

全部 design/plan/control/其它 review/stop/user-decision artifacts均在 entry 与
exit 用 SHA-256 复核；29 个 protected paths无 drift。入口 hash采集命令第一次在
隔离 zsh subshell 中误用了 zsh 特殊变量名 `path`，只导致该 subshell 的 `PATH`
失效、没有写入 worktree；随即以 `pathname` 和绝对 `shasum` 路径重跑成功。

### 32.2 第一性原理与 implementation shape

动机裁决：用户已明确本地 Config、Host SQLite/EventLog 属于同一受信任本地域，
所以“内部 durable headers 明文必须 production redesign”的旧动机不成立；真实且
需要关闭的问题只是 projection owner 是否把该值投影到非受信任 surface。语义
owner 因此分别是 dispatch effective-decision、Tool Trace consumer、audit line
builder、public HostEvent projector、RunInput/Memory/Compact/runner-call projector与
LocalProxy logger，不能在下游做黑名单或补偿。

实现只修改授权的后五个 tests，使用唯一 synthetic sentinel
`synthetic-local-trust-sentinel-6f2b9d8c`；没有读取、打印、写入真实 secret value/ref：

1. `test_run_input_builder.py`：把 sentinel 写入真实
   `effective_execution_config`，经 EventLog durable read与 dispatch decision owner
   round-trip后证明 exact headers保留；再证明 `AgentRunRequest.runner_spec.headers`
   保留，同时 messages、memory JSON、pre-dispatch compact material、runner-call hot/
   manifest/projection均为零 sentinel。
2. `test_tool_trace_projection.py`：直接验证 consumer filter拒绝
   `USER_INPUT_ACCEPTED`，projection runner执行后 hot row、cold JSONL、query page均为空。
3. `test_audit_sink.py`：同一 source event进入 real sink，assert exact audit key set，
   完整 canonical serialization零 sentinel。
4. `test_host_activity_event_projection.py`：同一 source event经 public owner得到 typed
   `HostEvent(PROGRESS, activity=None)`，完整 DTO serialization零 sentinel。
5. `test_logging.py`：resolved header进入 LocalProxy accept owner，Engine request保留
   sentinel，operator caplog零 sentinel。

没有使用 `Authorization` / `api_key` 字段名黑名单、loose parsing、mock-only bypass、
下游 repair、兼容分支、secret split/descriptor/resolver/manager或统一授权框架；
production、README、workflow、config、design、plan、control、其它 tests/utils零改动。

### 32.3 Owner-node implementation feedback

第一轮五个新增 node命令：

```bash
source .venv/bin/activate
pytest -q \
  tests/host/test_audit_sink.py::test_audit_projection_excludes_internal_effective_execution_value \
  tests/host/test_tool_trace_projection.py::test_tool_trace_excludes_internal_effective_execution_value \
  tests/host/test_host_activity_event_projection.py::test_public_host_event_excludes_internal_effective_execution_value \
  tests/host/test_run_input_builder.py::test_internal_execution_value_round_trips_without_llm_projection \
  tests/host/test_logging.py::test_local_proxy_logs_exclude_internal_effective_execution_value
```

- Exit：`1`；`4 passed, 1 failed`。
- 唯一失败发生在 RunInput builder 进入 projection 前：test fixture 的
  `AttemptDispatchSnapshot.policy_snapshot_ref` 仍是 fallback ref，而真实 dispatch
  decision已从 durable effective config产生新的 ref，触发既有 fail-closed contract。
- 这是 test fixture 对真实 dispatch snapshot更新模拟不足，不是 sentinel leak；
  durable exact headers断言已经先通过。因此未触发 production-leak stop，也未改
  production；只在同一测试内用 typed `replace` 同步真实 effective policy ref。

修正后单 node：exit `0`，`1 passed`；五个 owner nodes合计全部通过。

首次 full pyright随后发现 Tool Trace test的局部 narrowing/unbound typing共4 errors；
只把 `row.run_id` 收窄为局部 `str` 并把 hot/query断言留在同一 store scope，未改变
owner oracle。fresh结果：Tool Trace file `51 passed`，full pyright
`0 errors, 0 warnings, 0 informations`，五个 modified owner paths Ruff
`All checks passed!`。

### 32.4 Final focused tests / three real smokes

Final-tree fresh §4.1 focused commands与结果：

| Command | Exit | Result |
| --- | ---: | --- |
| `pytest tests/service/test_host_admin.py -q` | 0 | `1 passed` |
| `pytest tests/tools/web/test_smoke_web_ci.py -q` | 0 | `48 passed, 3 warnings` |
| Web file + runtime log + SEC log三路径 | 0 | `50 passed, 3 warnings` |
| `pytest tests/host/test_public_compact_smoke.py -q` | 0 | `23 passed, 1 expected opt-in skip` |
| 五个 owner test files | 0 | `187 passed` |
| Engine phase2 + diagnostic payload | 0 | `81 passed` |

三个 required real smokes均在本 continuation fresh执行、exit `0`：

- real compactor：`1 passed`，没有 skip；两轮 terminal/continuity/artifact oracle通过。
- standalone Web：`status=passed`，`11 local`、`4 diagnostic-only`、
  `0 failure`、`0 skip`。
- public awaiting：typed provider modes、late-publication fence、terminal/outbox一致性通过，
  输出 `SMOKE PASS Host public awaiting entrypoint`。

### 32.5 Canonical / coverage sequence evidence

Final-tree canonical command：

```bash
source .venv/bin/activate
pytest tests/documents tests/tools tests/host tests/engine tests/runtime tests/service tests/fins tests/cli
```

- Exit：`1`。
- Result：`1 failed, 5181 passed, 10 skipped, 5 deselected`。
- 唯一失败精确为
  `tests/service/test_import_boundary.py::test_service_does_not_import_forbidden_layers`
  的三个已知 AR-F02 consumers；这是 Slice 1允许的唯一顺序失败。

Exact scheduler exclusion coverage按 plan原三条命令执行；只排除：

```text
tests/host/test_dispatch_scheduler.py::test_wake_queue_promotion_uses_tracked_async_promotion_task
```

第一次 coverage运行（最后一次 test typing修正前）为
`1 failed, 5180 passed, 10 skipped, 6 deselected`，唯一失败仍为 AR-F02。
最后一次 typing修正后的 exact run为：

```text
exit = 1
1 failed, 5179 passed, 11 skipped, 6 deselected
```

唯一 failure仍是 AR-F02，但新增的第11个 skip来自外部 Gemini provider日配额耗尽。
定位命令：

```bash
pytest tests/host/test_public_real_runner_matrix_smoke.py -q -rs
```

结果：exit `0`，`3 passed, 1 skipped`；typed reason为 provider quota/rate-limit
`resource_exhausted`。没有输出 credential。这不是本 slice代码 defect，但 plan §6.1
明确要求10 skips/既有分类不得新增，且禁止 retry掩盖，因此本 continuation不能把
最后一次 coverage gate签 PASS，必须按授权 STOP。

Coverage JSON仍用原命令生成成功，219-path cumulative ledger为：

```text
LEDGER_COUNT=219
GE80_COUNT=210
LT80_COUNT=9
MISSING_FROM_COVERAGE=1
```

低于80%的路径精确等于计划九个 AR-F05 paths；statements/covered/line percent分别为：

```text
dayu/documents/processors/docling_processor.py                 635/403 63.46%
dayu/fins/pipelines/sec_6k_rules.py                            447/302 67.56%
dayu/fins/processors/sec_form_section_common.py               1098/859 78.23%
dayu/fins/processors/sec_report_form_common.py                 416/271 65.14%
dayu/fins/processors/sec_section_build.py                      303/235 77.56%
dayu/fins/processors/sec_table_extraction.py                   863/571 66.16%
dayu/fins/tools/preprocess_tools.py                              62/47 75.81%
dayu/host/_execution_config_projection.py                      157/120 76.43%
dayu/runtime/argparse_exit.py                                     0/0  0.00%
```

九路径只登记 `OPEN_BY_SEQUENCE`；没有签最终 coverage PASS，也没有其它低覆盖路径。

### 32.6 Pyright / Ruff / build

- Full pyright final-tree fresh：exit `0`，
  `0 errors, 0 warnings, 0 informations`。
- Full Ruff JSON：tool exit `1`（pre-existing findings语义）；normalized set
  `entry=144, current=143, added=0, removed=1`。唯一 removed是
  `tests/tools/web/test_smoke_web_ci.py` 的历史 `E402`；八个 mutable tests
  `0 findings`。最后一次 Tool Trace typing-only调整后 scoped Ruff再次 exit `0`，
  `All checks passed!`。
- Build：exit `0`，wheel与sdist同时生成：

```text
dayu_agent-0.1.4-py3-none-any.whl  2101532 bytes
SHA-256 da9d325b17b3151e0ff3045c396d5b09f002d658f72fe6ed3eae25ebd4e111a7
dayu_agent-0.1.4.tar.gz             1836408 bytes
SHA-256 f9cb2fc61c83858b92fd0b0dd66b81bfc189f8e8c174347ada195c4f2b9b07a7
```

### 32.7 Six scans / security / README / deferred / no-code

Six canonical scans使用 plan §6.6 原命令：S1—S4均 exit `1`/zero match；S5/S6
exit `0`且与 immutable accepted classification一致。Added-hunk复核证明 S5/S6均
zero new match。S5仍为 accepted fixture/财务 `total` 术语，S6精确是三个既有
operational labels；没有新 stale public semantic、raw total projection、removed
entrypoint或JSON argv contract。

Final-tree local security matrices：

| Matrix | Exit | Result |
| --- | ---: | --- |
| Doc + Web path/network/proxy/redirect/diagnostic | 0 | `346 passed, 1 skipped, 3 warnings` |
| Host digest/EventLog/opaque-ref/compact/trace/wait fence + Engine | 0 | `495 passed` |
| Full Fins transaction/atomic swap/path/opaque id/HKEX | 0 | `950 passed, 1 skipped, 3 warnings` |
| CLI POSIX quoting/init containment/process fencing | 0 | `8 passed, 5 Darwin Windows skips, 3 warnings` |
| Current live-browser cleanup owner | 0 | `1 passed` |

R10 accepted immutable official evidence三文件均存在且hash不变：

```text
db1f67c5966ff32877f0c4889293a9f74f5552610a1bde793f904de47acf06fe  manifest.json
cfec10de8f3d20d8a6b7eefc73937cf00a71c61124061f49ec16704222d1ed18  round-001-body.json
548254d47e805d841a39b60fb51af879d453b36c9bb5c9987156f251969e8fdd  round-002-body.json
```

已读取 `tests/README.md` 更新约束。决定 `NO_UPDATE`：本 continuation只增加现有
Host测试层内的 owner contract cases，不新增测试层级、运行方式、维护规则或用户工作流；
authorization同时禁止 README diff。

Deferred/no-code added-hunk scans均zero match：没有引入 TruncationManager wiring、
storage-state lifecycle/TTL/retention/refresh、Fins hard-kill/process isolation、assets
migration；Issues 177/178/175/142/151 owner不变。Production diff为空；
`dayu/engine/agent.py` 与 `dayu/engine/contracts/error_codes.py` 零 diff；没有
authorization framework、capability token、policy DSL、role model或secret framework。
`AR-F06 = RETAINED / UNFIXED / UNWAIVED / CURRENT_NO_FIX`。

### 32.8 Configured-value semantic classification

只读扫描从 current typed model config 的 `api_key_ref` 在内存解析非空环境值；输出
只包含计数，不包含 value、ref、header名称或命中正文。扫描覆盖本 slice全部
`workspace/tmp/wu-semantic-ownership-01-ar-fix*` outputs、相关 reviews、本 artifact
entry内容与 `git diff --binary HEAD`。

第一次结构扫描错误地要求整个 header value与 configured value相等，因真实 template
会在值外附加协议前缀而得到 exit `1`、`Host logical other=2`；这是 scan oracle过窄，
不是 leak。只在 gitignored `workspace/tmp` 临时脚本中把计数修正为“configured value
必须出现在 exact headers value下”，未输出内容、未缩小 root、未改 production/test。
修正后 fresh exit `0`：

```text
CONFIGURED_VALUE_COUNT=5
ACCEPTED_TRUSTED_INTERNAL Config_source configured_value_count=5 matched_path_count=0
ACCEPTED_TRUSTED_INTERNAL Host_internal_physical match_count=3 matched_path_count=1
ACCEPTED_TRUSTED_INTERNAL Host_internal_exact_path logical_match_count=2 logical_row_count=2
HOST_LOGICAL_OTHER=0
ZERO_REQUIRED tool_trace match_count=0 matched_path_count=0
ZERO_REQUIRED audit match_count=0 matched_path_count=0
ZERO_REQUIRED public match_count=0 matched_path_count=0
ZERO_REQUIRED llm match_count=0 matched_path_count=0
ZERO_REQUIRED logs match_count=0 matched_path_count=0
ZERO_REQUIRED other_output match_count=0 matched_path_count=0
ZERO_REQUIRED review_diff match_count=0 matched_path_count=0
SCAN_VERDICT=PASS
```

Synthetic sentinel owner tests与 real configured-value classification同时通过；没有把
accepted internal SQLite physical occurrence合并进 ZERO_REQUIRED waiver。

### 32.9 Exit scope / mutable hashes / final finding status

Exit read-only checkpoint：

```bash
git rev-parse HEAD
git status --short
git diff --name-status HEAD
git diff --cached --name-status
git diff --check
shasum -a 256 <protected paths / mutable tests>
```

- HEAD/branch不变；`git diff --check` exit `0`；staged tree为空。
- 扣除 entry protected集合，exact mutable scope只有授权的八个 tests与本 append-only
  implementation artifact；production、README、workflow、config、design、plan、
  control、其它 reviews/artifacts/tests/utils零新 diff。
- 所有 pre-existing protected path hashes与 entry记录一致；前三个 tests保持 entry hash。
- Final mutable test hashes：

```text
5acf57a06d1c7fee82a27ae0c3ccdfcddfe745a42439a514c0551665904f96db  tests/service/test_host_admin.py
86968b937d4289d29427a2bd68934a074ca0499dfa3563ec326eae73f2432ee3  tests/tools/web/test_smoke_web_ci.py
f60a1d6e190c948986be355fc66ad71cb64e207691e8a12646ea23cbdcc66169  tests/host/test_public_compact_smoke.py
20f41229f4e0da48aa1f3904d3bd5c61f436f7a9a706dfe78e899a4d06dccda2  tests/host/test_audit_sink.py
4d9dbb9b5a215597182166b6a92c2d1d30447ae21539bf77602cc6b7c7869140  tests/host/test_tool_trace_projection.py
047b89fd099fdc3250bdcdc066487b05bcf70aeccc18b60228f3bb10cca90c77  tests/host/test_host_activity_event_projection.py
4ed1693ee6819caf99072883e850f2a11e0ccb11636a196b0af629205cd46190  tests/host/test_run_input_builder.py
e874e77e997039d7d1e907dc4df5e980edae876e3920ac4417e3836cabf5b180  tests/host/test_logging.py
```

Finding状态：

```text
AR-F01 = IMPLEMENTATION / OWNER EVIDENCE PASS; FINAL CLOSED NOT SIGNED DUE GATE STOP
AR-F03 = IMPLEMENTATION / OWNER EVIDENCE PASS; FINAL CLOSED NOT SIGNED DUE GATE STOP
AR-F04 = IMPLEMENTATION / OWNER EVIDENCE PASS; FINAL CLOSED NOT SIGNED DUE GATE STOP
S1-SEC-F01 = OWNER EVIDENCE PASS; CLOSED_AS_NO_CODE_BLOCKER NOT SIGNED DUE GATE STOP
AR-F02 = OPEN_BY_SEQUENCE
AR-F05 = OPEN_BY_SEQUENCE
AR-F06 = RETAINED / UNFIXED / UNWAIVED / CURRENT_NO_FIX
AR-F07 = PENDING_RELEASE_BLOCKER
```

Final verdict：
`STOPPED / EXTERNAL_PROVIDER_QUOTA_TYPED_SKIP / CONTROLLER_DECISION_REQUIRED / NOT_READY_FOR_REVIEW`。
这不是 local-trust owner leak或production defect；唯一未满足门禁是最后一次 exact
coverage run相对固定 baseline多一个外部 quota typed skip。没有重试、waive、改测试、
改 production或扩大 scope。Next gate只能是 `Controller validation`；不得自行发送
reviewer、stage、commit、push、PR或进入 Slice 2/3。本 artifact最终 SHA-256由写入后
外部只读命令计算并在 handoff报告。

## 33. Final validation-only close（2026-07-19）

本节是同一 `WU-SEMANTIC-OWNERSHIP-01 aggregate regression fix Slice 1` 的
validation-only close，不是新 WU，不包含 implementation/fix。除向本 artifact 追加本节外，
未修改 code、test、config、design、plan、control、README 或其它 review artifact；未
stage、commit、push、发起 PR，也未发送任何真实 provider 请求。

### 33.1 Required truth sources：FULL_READ_TO_EOF

下表是写入前的 current `wc -l` 与 SHA-256。每一项均从第一行读取到 EOF；大文件只做
顺序分段读取，没有用索引、search、相关章节或摘要替代全文。implementation artifact 的
行数与 hash 是追加本节前的 full-read snapshot。

| Truth source | current `wc -l` | Read status | SHA-256 |
| --- | ---: | --- | --- |
| `AGENTS.md` | 128 | `FULL_READ_TO_EOF` | `cb26618ab566804c97a3ef2f269537b7313e59370e5ddd0258d9b753b08ac45e` |
| `docs/host/issues-implementation-control.md` | 2320 | `FULL_READ_TO_EOF` | `efed2ece1c5fab41f6b812fe91c3f407fe8ac172da61fe5b38780685a5432f42` |
| `docs/phaseflow-umbrella-optimization-control.md` | 302 | `FULL_READ_TO_EOF` | `6d924e919a4ba797e6213879aadca7bdd4f47a37418630e1ee43cb1995e461db` |
| `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md` | 731 | `FULL_READ_TO_EOF` | `cd26760d626415c52caa13a724144b4d98f2a2b2fc159772e6d807833c01533a` |
| `docs/host/design.md` | 3704 | `FULL_READ_TO_EOF` | `2be90cc2e107ce14fd5ee594c85e2a223217b9d6689b2d4a0cafba2adf3ec628` |
| `docs/engine/design.md` | 553 | `FULL_READ_TO_EOF` | `f209126046ffdb8a55f41a538c929842817f328f8c3bbc8f080b8c1c5489bf31` |
| `docs/tool/design.md` | 134 | `FULL_READ_TO_EOF` | `ddc6efc03c15ad5ba50332593f2282b1035dbc88d243071597814c7b4dceea7c` |
| `docs/fins/design.md` | 123 | `FULL_READ_TO_EOF` | `97033cf1330e6018df2cf7bf676fa550c24e3e99beb99792f718eac31727abdd` |
| `docs/ui/design.md` | 116 | `FULL_READ_TO_EOF` | `ed25d5d4577864cbf7ca6860aad043607921bd7db4f72cffb876c871fb99b4b7` |
| `docs/host/wu-semantic-ownership-01-aggregate-regression-fix-plan.md` | 696 | `FULL_READ_TO_EOF` | `afaa18c5608e6eeae0046318865bd1b3dd2f9a176c4b0739aa5b099e0ae3a252` |
| 本 implementation artifact（pre-append） | 1577 | `FULL_READ_TO_EOF` | `2c1274e17bc37a0837782fc6cb657fa1cb566ad57c340754023796a5d8703cfe` |
| initial code review MiMo | 230 | `FULL_READ_TO_EOF` | `8b60260ce2a66dbef34b8a557fef1cc23ab6fc8b7ce7561279ec41e0a0a23fdf` |
| initial code review DS | 382 | `FULL_READ_TO_EOF` | `2cd63af805004aaebc50a2570998114836cb138d50d911245fe0c9c3902beebb` |
| initial code-review Controller adjudication | 62 | `FULL_READ_TO_EOF` | `cca15904a7d9046cc1b10f392587724f85a1b7c6940c80e9a709bcadca84e718` |
| final code rereview MiMo | 360 | `FULL_READ_TO_EOF` | `4ab6b9d36aece10030440bd8ea1da7e19c8ca5c4eb154cca730ca7beb1d8c2ca` |
| final code rereview DS | 310 | `FULL_READ_TO_EOF` | `66bb3af17ff4c07b52f28a0491619858698359f46e743c6228a700dd8566789e` |
| final rereview Controller adjudication | 48 | `FULL_READ_TO_EOF` | `2c831fb26d7c06d8b8666ffb3b281d0417a94de397b96bca3bc480f6ca3b34c9` |
| test-account quota user decision/controller record | 46 | `FULL_READ_TO_EOF` | `835361b10497beba061582855063be57d41d0e4ce1f416f275b06fff8997c02f` |

三份要求锁定的 final review hashes全部精确一致；Controller final rereview verdict仍是
`PASS / ZERO ACCEPTED FINDING / READY_FOR_AGENTCODEX_VALIDATION_ONLY_CLOSE`。

### 33.2 Immutable eight-test manifest

逐文件 fresh hash：

```text
5acf57a06d1c7fee82a27ae0c3ccdfcddfe745a42439a514c0551665904f96db  tests/service/test_host_admin.py
86968b937d4289d29427a2bd68934a074ca0499dfa3563ec326eae73f2432ee3  tests/tools/web/test_smoke_web_ci.py
f60a1d6e190c948986be355fc66ad71cb64e207691e8a12646ea23cbdcc66169  tests/host/test_public_compact_smoke.py
20f41229f4e0da48aa1f3904d3bd5c61f436f7a9a706dfe78e899a4d06dccda2  tests/host/test_audit_sink.py
4d9dbb9b5a215597182166b6a92c2d1d30447ae21539bf77602cc6b7c7869140  tests/host/test_tool_trace_projection.py
047b89fd099fdc3250bdcdc066487b05bcf70aeccc18b60228f3bb10cca90c77  tests/host/test_host_activity_event_projection.py
4ed1693ee6819caf99072883e850f2a11e0ccb11636a196b0af629205cd46190  tests/host/test_run_input_builder.py
e874e77e997039d7d1e907dc4df5e980edae876e3920ac4417e3836cabf5b180  tests/host/test_logging.py
```

以上述固定顺序对 `shasum -a 256` manifest再次计算 SHA-256：

```text
bcfc4088dfb2239236579159b71f6abc8e51a32201de240603f3a2eebd954c41
```

结论：八文件与 ordered manifest均无 hash drift。

### 33.3 Fresh executable validation

| Gate | Exit | Fresh result |
| --- | ---: | --- |
| 八个 owner test files focused suite | 0 | `259 passed, 1 skipped, 3 warnings in 3.85s` |
| full `pyright` | 0 | `0 errors, 0 warnings, 0 informations` |
| 八文件 scoped `ruff check` | 0 | `All checks passed!`，零 finding |

focused suite 的唯一 skip是未启用 real-compactor opt-in 的既有自然环境分类；三个 warnings
均为既有第三方 deprecation warnings，不是 Slice 1 failure。

### 33.4 Git / exact scope / protected baseline

- Branch：`phaseflow/host-issues-control`。
- HEAD：`ffbf48c2cf5f701c627fda1ebcce7aa1813383ab`。
- 写入前 `git diff --check` exit `0`；staged tree为 `EMPTY`。
- current dirty scope为 40 paths；排除唯一允许追加的本 artifact 后，39-path protected
  content manifest SHA-256为
  `0acf98dd16892d2ada5390750705cd746dd69279d7d8ee597d818e16e00c29fa`。
- tracked production/config/root README diff为空；没有 untracked code/test/entrypoint path。
- 本次 close不接管或改写既有 dirty worktree；design、plan、control、八个 immutable tests与
  其它 review/controller artifacts全部属于 protected scope。

### 33.5 Configured-value logical-owner semantic scan

fresh只读扫描在内存解析 current config 的非空 configured values；扫描既有 Slice 1
workspace outputs、本轮 review/controller artifacts、本 implementation artifact和
`git diff --binary HEAD`。没有输出任何 value、ref或命中正文。

| Owner/surface category | Match count | Matched path/row count | Verdict |
| --- | ---: | ---: | --- |
| Config source | configured count 5 | 0 paths | `ACCEPTED_TRUSTED_INTERNAL` |
| Host internal physical retention | 3 | 1 path | `ACCEPTED_TRUSTED_INTERNAL` |
| Host internal exact effective execution path | 2 logical | 2 rows | `ACCEPTED_TRUSTED_INTERNAL` |
| Host logical other | 0 | 0 | `ZERO_REQUIRED` |
| Tool Trace | 0 | 0 paths | `ZERO_REQUIRED` |
| audit | 0 | 0 paths | `ZERO_REQUIRED` |
| public HostEvent/output | 0 | 0 paths | `ZERO_REQUIRED` |
| LLM messages/memory/compact/runner-call projection | 0 | 0 paths | `ZERO_REQUIRED` |
| operator logs | 0 | 0 paths | `ZERO_REQUIRED` |
| other outputs | 0 | 0 paths | `ZERO_REQUIRED` |
| review prose / binary diff exposed surfaces | 0 | 0 paths | `ZERO_REQUIRED` |

Scan verdict：`PASS`。没有 waiver，也没有把 accepted Host internal physical occurrence并入
zero-required surface。

### 33.6 Source / security / deferred / no-code scans

对 current added code/test hunks与 production scope进行 fresh只读扫描：

| Prohibited/deferred shape | Added match count |
| --- | ---: |
| 字段名 blacklist | 0 |
| 下游 safe-arguments normalization | 0 |
| secret infrastructure | 0 |
| unified tool authorization framework | 0 |
| Issue 142 / 151 capability | 0 |
| Issue 175 process isolation/hard-kill | 0 |
| Issue 177 TruncationManager wiring | 0 |
| Issue 178 storage-state lifecycle/TTL/retention/refresh | 0 |
| Web / WeChat / render entrypoint capability | 0 |

`dayu/` production diff为空。Topic 8的 `dayu/engine/agent.py` 与
`dayu/engine/contracts/error_codes.py` 均对 HEAD零 diff，现有 redaction与固定 240 raw-char
行为保持不变。Topic 9没有 code；未引入 authorization framework、capability token、
policy DSL或role model。Issues 142/151/175/177/178及 Web/WeChat/render deferred owner均未被偷带。

### 33.7 README trigger adjudication

本 Slice只有既有测试与 artifact 变化；所有 README裁决均为 `NO_UPDATE`：

| README trigger | Decision | Reason |
| --- | --- | --- |
| `tests/README.md` | `NO_UPDATE` | 没有新增测试层级、运行方式或维护规则 |
| root `README.md` | `NO_UPDATE` | 没有用户可见入口、参数、输出、日志位置或工作流变化 |
| `dayu/README.md` | `NO_UPDATE` | 没有分层、装配或公共边界变化 |
| `dayu/host/README.md` | `NO_UPDATE` | Host production零 diff |
| `dayu/engine/README.md` | `NO_UPDATE` | Engine production与Topic 8零 diff |
| `dayu/fins/README.md` | `NO_UPDATE` | Fins production零 diff |
| `dayu/config/README.md` | `NO_UPDATE` | config与prompt assets零 diff |

### 33.8 Canonical / coverage / provider evidence revalidation

- 被 final rereviews锁定的 implementation pre-append SHA-256仍为
  `2c1274e17bc37a0837782fc6cb657fa1cb566ad57c340754023796a5d8703cfe`；其中 §32.5 的
  canonical final-tree证据仍是 `1 failed, 5181 passed, 10 skipped, 5 deselected`，唯一
  failure是按顺序保留给 Slice 2的 AR-F02。
- 同一被锁定 artifact中的 exact coverage证据仍是
  `1 failed, 5179 passed, 11 skipped, 6 deselected`，唯一 failure仍是 AR-F02；coverage
  outputs仍存在，JSON SHA-256为
  `d4cdfc4777959eaa6ee3495cdca7ad48d74173c4c7b2fc8cb4806c0a472a402f`，data SHA-256为
  `7d4338b7d34d596085c84bbeee1b0d69b906a73ace7034b90e9b78a913e1bf63`。
- §32.9所记录的八个 final mutable test hashes与本次逐文件 fresh hashes完全相同，ordered
  manifest也仍为 `bcfc4088…d954c41`；因此 canonical与exact coverage既有证据仍对应同一
  immutable final tree。
- 没有为 Gemini quota重跑 coverage或 full provider matrix。保留既有 `3 passed, 1 skipped`；
  typed `RESOURCE_EXHAUSTED`按用户/Controller记录固定为
  `EXPECTED_TEST_ACCOUNT_QUOTA / NO_CODE_ACTION / NON_BLOCKING`。
- 未修改 provider config/model/key/retry/quota/budget，未发送任何真实 provider 请求。

### 33.9 Final ledger and verdict

```text
AR-F01 = CLOSED
AR-F03 = CLOSED
AR-F04 = CLOSED
S1-SEC-F01 = CLOSED
AR-F02 = OPEN_BY_SEQUENCE / SLICE_2
AR-F05 = OPEN_BY_SEQUENCE / SLICE_3
AR-F06 = FUTURE_HOST_SCHEDULER_LIFECYCLE / UNFIXED / UNWAIVED
AR-F07 = WINDOWS_RELEASE_EVIDENCE / PENDING_RELEASE_BLOCKER
GEMINI_TEST_ACCOUNT_QUOTA = NON_BLOCKING / NO_CODE_ACTION
```

Validation-only verdict：`PASS / SLICE_1_CLOSED / READY_FOR_CONTROLLER_ACCEPTED_COMMIT_VALIDATION`。
本结论不授权进入 Slice 2/3，也不授权 stage、commit、push或 PR。

### 33.10 Post-append write-boundary confirmation

主 close 内容追加后的只读复核结果：`git diff --check` exit `0`，staged tree仍为
`EMPTY`，branch/HEAD仍为
`phaseflow/host-issues-control` / `ffbf48c2cf5f701c627fda1ebcce7aa1813383ab`。
dirty scope仍为 40 paths；排除本 artifact 后仍为相同 39-path protected集合，其 content
manifest仍为 `0acf98dd16892d2ada5390750705cd746dd69279d7d8ee597d818e16e00c29fa`。
八测试 ordered manifest仍为 `bcfc4088dfb2239236579159b71f6abc8e51a32201de240603f3a2eebd954c41`；
三份 final review hashes仍分别为 `4ab6b9d3…1d8c2ca`、`66bb3af1…6789e`、
`2c831fb2…b34c9`。因此本次唯一内容变化是允许文件的 append；protected scope零漂移。
