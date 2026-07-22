# WU-CTX-04 Slice 2 code-review fix（AgentCodex）

## Gate metadata

- Work unit：`WU-CTX-04`。
- Slice：`2/3`。
- Gate：code review fix；result：`pass-for-re-review`。
- Accepted baseline：`eda1d70eb2c2252570807e1fcdb1cd234a5aae7a`。
- Controller adjudication：
  `docs/reviews/wu-ctx-04-slice-2-code-review-controller-adjudication.md`。
- Implementation artifact：
  `docs/reviews/wu-ctx-04-slice-2-implementation-codex.md`。
- Blocking open questions：None。
- 本 gate 未 commit、未 push、未创建 PR，也未改 design、control、accepted plan、
  reviewer artifact 或 README。

## First-principles judgment 与 owner boundary

`CTRL-S2-001` 的动机成立且是 blocking correctness defect。原 projection 在没有已验证
proactive request 时直接返回 `ABSENT`，把 orphan/unknown durable row 错误转换为
`CREATE_NEW`，从而允许新 request 与 provider side effect。SQLite row 已经是 operation
状态机证据；缺少 owner 不能等价为 row 可忽略。

修复保持唯一 semantic owner：

- `dayu.host.proactive_compaction` 继续独占 request owner 索引、非-request row strict
  projection、INVALID identity 与 typed decision；没有增加兼容 parser、默认 operation id
  或第二套 integrity checker。
- dispatcher 只消费 projection decision。INVALID 没有安全 proactive id 时，它只调用既有
  `_fail_unstarted_in_transaction(...)` 收口 Run，不重新解析 raw row。
- `HostSessionAttachmentRegistry` 的 nested recovery lease 行为没有错误；只同步窄 Port 与
  implementation contract 文本，并在 owner test 固定三段状态机。
- `_PublicHostHandle._close_owned_resources` 的 mandatory/best-effort 控制流符合 accepted
  plan；只修正 docstring，不改变 close 顺序、错误传播实现或 `mark_closed()` 条件。

## Finding closure 与 exact change mapping

### CTRL-S2-001 — 已修复

1. 删除 `_project_state(...)` 的 zero-proactive-request early return。第一遍严格验证全部
   request identity/schema/trigger owner；第二遍无论是否存在 proactive request，都会处理全部
   rejection、terminal 与 runner-call rows。
2. runner-call row 先通过 strict hot parser 分类；只有明确非 `compactor_proposal` 的 call
   才忽略。compactor proposal 必须解析完整 manifest、验证 parent identity、request owner 与
   canonical sequence；只有严格归属 reactive request 后才隔离。
3. rejection/terminal 必须先通过现有 strict payload validator、known request owner 与
   request-before-row sequence 校验；合法 reactive row 才忽略。orphan、unknown、malformed、
   mismatched row 均进入 `INVALID`。
4. INVALID fallback identity 改为复用同一 strict request-owner parser，只返回最早严格验证的
   proactive request event/operation id。malformed request 与 reactive request 永不提供 id。
5. dispatcher 遇到 `FAIL_EXISTING_OPERATION` 且无安全 id 时，直接由既有 governance failure
   owner 把 Run 收口为 `FAILED`；不追加 request、`CONTEXT_COMPACTED` 或
   `CONTEXT_COMPACTION_FAILED`，不创建 Attempt，也不调用 provider。

五组 adjudication 反例均已补齐：

| 反例组 | Owner/integration evidence | 断言 |
| --- | --- | --- |
| 无 request + orphan rejection/terminal/compactor manifest | `test_orphan_non_request_row_without_request_is_invalid` 参数化 rejection/failed terminal；`test_orphan_compactor_manifest_without_request_is_invalid` 用真实 scheduler/recorder 提交 strict manifest 后删除 request | 全部 `INVALID`，`operation_id is None`，绝不 `ABSENT` |
| 合法 reactive-only request/history | `test_valid_reactive_only_history_remains_absent` | strict request/failed terminal 被正确隔离，仍为 `ABSENT/CREATE_NEW` |
| 合法 reactive request + unknown-operation row | `test_reactive_request_with_unknown_operation_row_is_invalid` | unknown terminal 为 `INVALID`，无 operation id |
| malformed request 不得误用 reactive id | `test_malformed_request_does_not_reuse_earlier_reactive_identity` | earlier reactive request 不进入 INVALID fallback identity |
| dispatcher 无安全 proactive id | `test_pre_start_governance_without_safe_operation_id_fails_run` | Run `FAILED`；Attempt/provider/request/compaction terminal 均零增量 |

### F-DS-01 — 已修复

- 同步 `SessionNewWorkAccessPort.try_acquire_new_work_lease` 与 registry implementation 的中文
  docstring：ACTIVE RW 可直接取 lease；RECOVERING RW 只有 root recovery lease 仍持有时可
  嵌套取得，root lease 释放后恢复拒绝。
- `test_recovering_record_only_allows_allocation_recovery_work` 直接证明：
  `RECOVERING + 0 lease -> None`、root lease 存续时 nested lease 成功、nested/root 释放后
  再次 `None`。production 行为未改。

### MIMO-REVIEW-001 — 文档修正已完成，behavioral change 未实施

`_close_owned_resources` docstring 现明确：mandatory 阶段失败立即阻断后续 owner close并保留
`CLOSING` retry contract；只有进入 best-effort 阶段后才会尝试全部安全 cleanup并传播首错。
`release_host_close()`、后续 owner close、`close_done` 与 `mark_closed()` 控制流零修改。

## Modified files

本 review-fix 只修改 adjudication 允许的 7 个既有 production/test 文件，并新建本 artifact：

| 文件 | 变更 |
| --- | --- |
| `dayu/host/proactive_compaction.py` | strict zero-request projection、safe proactive INVALID id |
| `dayu/host/dispatch.py` | 无安全 operation id 时复用既有 governance failure |
| `dayu/host/session_attachment.py` | Protocol/implementation recovery nested lease docstring |
| `dayu/host/open_host.py` | mandatory/best-effort close docstring；无行为变更 |
| `tests/host/test_proactive_compaction_operation.py` | orphan/reactive/unknown/malformed direct owner 反例 |
| `tests/host/test_dispatch_scheduler.py` | orphan manifest 与无安全 id dispatcher integration 反例 |
| `tests/host/test_session_attachment_registry.py` | RECOVERING nested lease owner 状态机测试 |
| `docs/reviews/wu-ctx-04-slice-2-review-fix-codex.md` | 唯一 review-fix artifact |

## Validation

所有命令均在仓库根目录通过 `source .venv/bin/activate` 使用 Python 3.11 环境执行。

1. 首轮最聚焦 owner tests：

   ```bash
   pytest tests/host/test_proactive_compaction_operation.py \
     tests/host/test_session_attachment_registry.py \
     tests/host/test_dispatch_scheduler.py -q
   ```

   结果：`138 passed in 2.17s`。

2. 最终 proactive/dispatch/session attachment focused matrix：

   ```bash
   pytest tests/host/test_proactive_compaction_operation.py \
     tests/host/test_dispatch_scheduler.py \
     tests/host/test_session_attachment_registry.py \
     tests/host/test_public_session_attachment.py -q
   ```

   结果：`153 passed in 2.29s`。

3. 受影响 Host 全套：

   ```bash
   pytest tests/host -q
   ```

   结果：`2133 passed, 1 skipped, 6 deselected in 62.45s`。

4. 全量类型检查：

   ```bash
   python -m pyright dayu/ tests/ utils/
   ```

   结果：`0 errors, 0 warnings, 0 informations`。

5. 允许的 7 个既有文件 targeted lint：

   ```bash
   ruff check dayu/host/proactive_compaction.py dayu/host/dispatch.py \
     dayu/host/session_attachment.py dayu/host/open_host.py \
     tests/host/test_proactive_compaction_operation.py \
     tests/host/test_dispatch_scheduler.py \
     tests/host/test_session_attachment_registry.py
   ```

   结果：`All checks passed!`。

6. whitespace validation：

   ```bash
   git diff --check
   ```

   结果：pass（零输出）。

新增行为分支全部由上述 direct/integration tests 执行；Slice 2 implementation artifact 已记录
相关 production 单文件 coverage 全部 `>=80%`，本 fix 没有新增未执行 production 分支。

## README / docs decision

本 gate 的行为变化是 Host 内部 durable corruption fail-closed 修正，不改变用户可见 API、命令、
安装或排障工作流。Controller 与用户都明确禁止本 gate 修改 README；现有 Slice 2 README defer
仍由 Slice 3 owner 承接，因此 README 零修改。除本 artifact 外没有新建其它文档。

## Residual risks

- `read_cancelling_runs` workspace-wide periodic path：`covered by later approved slice`，继续由
  WU-CTX-04 Slice 3 execution-owner cancel reconcile 关闭。
- consumer task exception observation：`assigned to later work unit`，semantic owner 为
  `HostDispatchScheduler` consumer-task lifecycle；两路 review 未证明由 Slice 2 引入，Controller
  明确禁止本 fix 扩大范围，后续 work unit 排期仍由 Controller 决定。
- provider crash 外部调用不承诺 exactly-once 与 Windows native mutex 环境验证：
  `assigned to later work unit`，分别归 provider/idempotency contract owner 与 cross-platform
  validation owner；本 fix 未改变其概率或边界。
- Unclassified residual risk：None。

## Completion decision

- `CTRL-S2-001`：已修复。
- `F-DS-01`：已修复。
- `MIMO-REVIEW-001`：裁决接受的 docstring correction 已完成；禁止的 behavioral change 未实施。
- Review-fix completion：`pass-for-re-review`。
- Next gate：AgentMiMo 与 AgentDS 双路独立 re-review，随后由 Controller adjudication；本 artifact
  不宣称 Slice 2 accepted，也未创建 accepted slice commit。
