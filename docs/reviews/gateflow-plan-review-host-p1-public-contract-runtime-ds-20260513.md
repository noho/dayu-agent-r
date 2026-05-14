# Host Phase 1 Plan Review — 公共契约与 runtime 基础设施

## Review Gate

plan review

## Reviewer

AgentDS

## Reviewed Target

- Plan: `docs/host/phase1-public-contract-runtime-plan.md`
- Design truth: `docs/host/design.md` §3, §3.1, §3.2, §10.1, §11, §18.1
- Implementation control: `docs/host/implementation-control.md`
- Project term truth: `dayu/README.md`
- Controller decision: `docs/reviews/gateflow-controller-decision-host-p1-phase-design-20260513.md`
- Round2 design fix: `docs/reviews/gateflow-phase-design-user-feedback-fix2-host-p1-codex-20260513.md`
- Round2 re-review (MiMo): `docs/reviews/gateflow-phase-design-re-review2-host-p1-mimo-20260513.md`
- Round2 re-review (DS): `docs/reviews/gateflow-phase-design-re-review2-host-p1-ds-20260513.md`

## Reviewer Conclusion

Plan 整体 **handoff-ready** 且 **code-generation-ready**。动机真实对齐设计目标，架构边界清晰，non-goals 与 stop conditions 精确，slices 有序且可独立验证。发现 4 个 finding，均为 non-blocking；其中 Finding 1 (acquire 事务边界) 和 Finding 2 (multi-process test path) 建议在 handoff 前补充澄清，其余两个为低风险文档/类型标注细节。无 design truth 冲突，无 Engine/Fins/Service/UI 反向依赖，无 ToolRuntime 提前实现夹带。

Finding 数量: 4。建议进入 user confirmation。

---

## Findings

### Finding 1: `acquire()` stale-cleanup + count + insert 事务边界未显式指定为单事务

- **状态**: 已修复
- **严重级别**: non-blocking
- **证据**:
  - Plan §Cross-Process `dayu.runtime.lane` Decisions → Claim / release semantics: "短事务内删除同 lane `expires_at <= now` 的 stale claims"、"统计 active claims"、"active count 小于 capacity 时 insert claim" 三步未用"同一事务"或等价语言明确包裹。
  - Plan §Coordinator / DB: "所有 claim / release / heartbeat / stale cleanup 使用短事务" 暗示各操作为短事务，但 stale-cleanup + count + insert 必须在**同一**事务内完成，否则两个并发 acquire 可能在各自 cleanup 后都读到 active < capacity，双双 insert，突破 capacity invariant。
  - 对比 design.md §3.1 line 153: "coordinator 在短事务内先清理同一 lane 中 `expires_at <= now` 的 stale claims，再在 active claim 数量小于 capacity 时插入一条新 claim" — design 用"在短事务内先…再…"的单句表达，比 plan 的 bullet list 更明确表达同一事务。
- **影响**: 若 implementation agent 将三步实现为独立短事务，多进程并发 acquire 可能突破 capacity invariant，导致测试 `test_lane_multiprocess` 间歇性失败或需要返工。
- **建议**: 在 plan §Claim / release semantics acquire 成功流程前增加一句 "以下步骤必须在单个 SQLite 事务内完成"，或直接引用 design.md 的原文表述。
- **Controller decision status**: accepted-fixed-by-codex-20260513

### Finding 2: Multi-process test DB path 约定与 pytest `tmp_path` fixture 存在语义摩擦

- **状态**: 已修复
- **严重级别**: non-blocking
- **证据**:
  - Plan §Coordinator / DB: "Tests 使用 `tmp_path / 'runtime_lanes.sqlite3'`；不得写入真实 `workspace/`。"
  - pytest 的 `tmp_path` 是 per-test-function 的独立临时目录。multi-process tests 需要父进程和子进程共享**同一个** DB 文件路径。若父进程在 `tmp_path` 下创建 DB，子进程无法访问（子进程是独立 Python 解释器，不继承 pytest fixture）。
  - Plan §Tests / validation Slice 2 期待 "多进程共享同一 DB 时 successful claims 总数不超过 capacity"，但未说明如何把 DB path 传递给子进程（环境变量、CLI 参数或共享临时目录）。
- **影响**: Implementation agent 可能写出无法运行的 multi-process test，或在 fixture 设计上反复返工。不影响单进程语义正确性。
- **建议**: 在 plan 的 Slice 2 test 说明中增加一句：父进程使用 `tempfile.mkstemp` 或 `tmp_path` 创建 DB 文件，通过 CLI 参数或环境变量将 `db_path` 传给子进程；子进程使用相同路径构造 `SQLiteLaneCoordinatorConfig`。
- **Controller decision status**: accepted-fixed-by-codex-20260513

### Finding 3: `LaneController.open(owner=None)` 的 auto-generation 逻辑未在 plan 中收敛

- **状态**: 已修复
- **严重级别**: non-blocking
- **证据**:
  - Plan public shape: `owner: LaneOwner | None = None` — 允许 `None`。
  - Plan §Coordinator / DB 和 §Time / heartbeat ownership 均未说明 `owner=None` 时 `owner_id`、`pid`、`process_start_token` 如何生成。
  - Design.md §3.1 line 154: "`owner` 默认由 runtime 根据当前进程生成，也允许上层显式传入稳定 owner id" — design 有语义但未给出生成算法。
  - Plan 各 slice implementation instructions 未覆盖此项。
- **影响**: Implementation agent 需自行决定 owner_id 生成方式（UUID / secrets.token_hex / hostname+pid 组合）和 process_start_token 来源（环境变量 / 启动时间戳 / 无）。不同选择不影响 Phase 1 正确性（owner 只用于 cleanup / diagnostics），但可能影响多进程测试中 owner 的可区分性。
- **建议**: 在 plan Slice 2 implementation instructions 中增加一行："`owner=None` 时，使用 `secrets.token_hex(8)` 生成 `owner_id`，`os.getpid()` 获取 `pid`，`process_start_token` 默认 `None`；调用方可通过 `owner=` 显式覆盖。" 或明确将此决策留给 implementation agent 并说明影响范围。
- **Controller decision status**: accepted-fixed-by-codex-20260513

### Finding 4: `LaneAcquireOutcome` 在 plan 正文中未标注 `TypeAlias` 语义，可能被误实现为 class

- **状态**: 已修复
- **严重级别**: non-blocking
- **证据**:
  - Plan §Public API 列出 "`LaneAcquireOutcome`" 作为导出类型之一，与 `LaneAcquired` / `LaneAcquireCancelled` / `LaneAcquireTimedOut` 并列，但正文未明确说明它是 `TypeAlias`（`LaneAcquired | LaneAcquireCancelled | LaneAcquireTimedOut`）而非 dataclass。
  - Plan 的 public shape 代码块中用 `LaneAcquireOutcome = LaneAcquired | LaneAcquireCancelled | LaneAcquireTimedOut` 表达了 union 语义，但若 implementation agent 只看文字列表不看代码块，可能创建为 wrapper class 或 dataclass。
  - Design.md §3.1 line 133 同样是 `LaneAcquireOutcome = LaneAcquired | LaneAcquireCancelled | LaneAcquireTimedOut` 的代码块表达，无额外文字说明。
- **影响**: 若实现为 class 而非 type alias，会导致使用者无法用 `isinstance(outcome, LaneAcquired)` 或 `match/case` 做 exhaustive 分支，影响公共 API 易用性。风险低，因 code block 已明确表达 union。
- **建议**: 在 plan Slice 2 implementation instructions 中增加 "`LaneAcquireOutcome` 使用 `typing.TypeAlias` 定义为 `LaneAcquired | LaneAcquireCancelled | LaneAcquireTimedOut`，不创建新 dataclass" 一句。
- **Controller decision status**: accepted-fixed-by-codex-20260513

---

## Architecture Boundary Audit

逐项核查 plan 中的架构边界，均通过：

| 检查项 | 结果 | 证据 |
|---|---|---|
| `dayu.host` 不 import Engine/Fins/Service/UI | PASS | Plan §Contract / API Decisions → `dayu.host` 放置: "`dayu.host` 不得 import `dayu.engine`、`dayu.fins`、`dayu.service`、`dayu.ui`"；Slice 1 import boundary test 锁定 |
| Engine 不 import `dayu.host` | PASS | Plan §Contract / API Decisions: "Engine 不得 import `dayu.host`，用 import boundary tests 锁定"；Engine 修改在禁止列表中 |
| `dayu.runtime` 不 import 业务层 | PASS | Plan §Cross-Process lane decisions: "不要从 `dayu.runtime.__init__` re-export lane 类型"；现有 `tests/runtime/test_import_boundary.py` 已有的 `RUNTIME_PERMANENT_FORBIDDEN_PREFIXES` 覆盖 |
| 第三方 `filelock` 只出现在 `dayu.runtime.filelock` | PASS | Plan §filelock decisions: "只有 `dayu.runtime.filelock` 可以直接 import `from filelock import FileLock`"；Slice 3 import boundary test 锁定 |
| lane DB 不保存 Host truth 字段 | PASS | Plan §Coordinator / DB: "不保存 Session / Run / Attempt / EventLog / Tool / 财报业务字段"；Slice 2 schema test 锁定 |
| Host durable store 不提前创建 | PASS | Plan §Non-Goals: "不实现 Host durable store / EventLog store / SQLite Host truth schema"；禁止修改列表涵盖 |
| ToolRuntime 不提前实现 | PASS | Plan §Non-Goals: "ToolRuntime policy resolution、framework tool injection、TruncationManager...不在 Phase 1"；Slice 4 stop condition 拦截 |
| `ToolBundle` 不塞入 request | PASS | Plan §HostToolingOptions decisions: "business_tool_bundle 是 Host construction input，不在任何 request dataclass 字段中"；Slice 4 test 锁定 |
| `HostMetadataEntry` 不承载主链字段 | PASS | Plan §Host request types: "仅用于非状态机、非幂等、非恢复、非审计主链附加说明；required fields 禁止塞入 metadata" |
| lane token 不进入 Host EventLog | PASS | Plan §Claim / release semantics: "token id 只标识 runtime capacity claim，不得传入 Host EventLog 作为 canonical identity"；与 design.md、implementation-control.md 强制约束一致 |

---

## Slice Audit

| Slice | 文件所有权 | 依赖 | Non-goals | Stop condition | 可独立验证 | 评价 |
|---|---|---|---|---|---|---|
| Slice 1: `dayu.host` public API | 新建 `dayu/host/`、`tests/host/`、`dayu/host/README.md`、修改 `dayu/README.md`、`tests/README.md` | 无（只依赖 `dayu.contracts`） | 不实现 command path、durable store、Engine import | 需决定 command path 签名以外的新状态机/store schema | 是 — `dayu.host` 可导入 + public contract tests 通过 | 纯 contract slice，范围清晰 |
| Slice 2: `dayu.runtime.lane` | 新建 `dayu/runtime/lane.py`、`tests/runtime/test_lane.py`、`tests/runtime/test_lane_multiprocess.py`、修改 `tests/runtime/test_import_boundary.py` | 只依赖 `dayu.contracts.cancellation.CancellationToken` + 标准库 | 不接入 Host dispatch、不实现 fairness、lane token 不传 EventLog | 需 Host store 默认路径/cancel propagation/Attempt owner/lease fencing/recovery proof | 是 — unit + multi-process tests 通过 | 最大 slice，multi-process tests 是复杂度高点 |
| Slice 3: `dayu.runtime.filelock` | 新建 `dayu/runtime/filelock.py`、`tests/runtime/test_filelock.py`、修改 `pyproject.toml`、`tests/runtime/test_import_boundary.py` | `filelock` (第三方) | 不实现 async wrapper、stale takeover、SQLite/EventLog 保护 | 需 async wrapper/stale takeover/删除 lock 文件 | 是 — filelock tests 通过 | 最轻量 slice |
| Slice 4: HostToolingOptions | 新建 `dayu/host/tooling.py`、`tests/host/test_tooling_options.py`、修改 `dayu/host/__init__.py`、`dayu/host/README.md` | Slice 1 (`dayu.host` package 已存在) | 不实现 ToolRuntime factory、fetch_more 注入、工具扫描 | 需决定 ToolsDiscovery/ScenePrepare provider contract | 是 — tooling types 可导入 + tests 通过 | 依赖 Slice 1 的 package skeleton |

Slice 2 与 Slice 3 均声明修改 `tests/runtime/test_import_boundary.py`。若不同 agent 分别实施，需注意合并顺序；不影响 plan 逻辑正确性，属于实施协调细节。

Slice 规模判断：Slice 2 比其他三个明显更大（SQLite coordinator + claim lifecycle + heartbeat + cancel/timeout/close + multi-process tests）。Plan 的 stop condition 清晰，若 agent 发现容量超限可交回 controller。不建议进一步拆分，因为 claim lifecycle 是一个不可分割的语义闭环。

---

## Test Coverage Assessment

Plan 的 failure path 覆盖矩阵（§Tests And Validation Commands）全面覆盖：

- **Host public contract validation**: 空字符串、非法 cursor、followup behavior/target 组合、slot binding 缺字段 — 覆盖充分。
- **Host tooling validation**: reserved name conflict、空 source refs、空 source id、enabled 不在 reserved 集合 — 覆盖充分。
- **Lane config validation**: 重复 lane、未知 lane、非正 capacity、TTL <= heartbeat、非正 heartbeat/TTL — 覆盖充分。
- **Lane acquire failure**: capacity full non-blocking、positive timeout、CancellationToken cancellation、Task.cancel propagation、close cancels pending — 覆盖充分。
- **Lane multi-process**: capacity invariant、release 后 acquire、crash/heartbeat stopped TTL cleanup — 覆盖充分（见 Finding 2）。
- **Lane busy timeout**: 并发竞争不破坏 capacity invariant — 覆盖充分。
- **Filelock failure**: parent missing、non-blocking timeout wrapping、release idempotency — 覆盖充分。
- **Import boundary**: runtime 不 import 业务层、Host 不 import Engine/Fins/Service/UI、第三方 filelock 只出现在 `dayu.runtime.filelock` — 覆盖充分。

建议补充的 edge case: 同一 `LaneController` 实例对同一 lane 并发 `acquire()` 的行为（已有 capacity 保护，但实现需确保内部状态线程安全），以及 `close()` 时仍有 pending heartbeat task 的交互。这两点可在 Slice 2 implementation 时补充测试，不阻塞 plan。

---

## Open Questions And Residual Risk

### Blocking Questions

0。Controller decision 列出的 4 个 plan 覆盖项（模块拆分、lane SQLite 细节、heartbeat ownership、busy timeout）均已在 plan 中收敛为 implementation decisions。

### Non-Blocking Residual Risks (继承自 design re-review)

1. **Heartbeat task ownership**: Plan 已选择 Controller-managed heartbeat task (§Time / heartbeat ownership)。Risk: 已收敛。
2. **SQLite busy timeout 测试覆盖**: Plan §Tests / validation Slice 2 已覆盖 "busy timeout 竞争场景不破坏 capacity invariant"。Risk: 已收敛。
3. **Clock monotonic-to-wall 策略**: Plan 已选择 `_LaneClock` 方案 (§Time / heartbeat ownership)。Risk: 跨进程 clock skew 只影响 eventual consistency，已记录。
4. **默认路径注入**: Plan 明确不提供 helper，只文档建议 `workspace/runtime/runtime_lanes.sqlite3`。Risk: 已收敛。

### Plan-Introduced Residual Risks

| Risk | Classification | Owner |
|---|---|---|
| SQLite busy timeout 可能导致高并发下 acquire loop 抖动 | later phase (Host durable store) | Plan §Residual Risks tracking |
| Heartbeat failure 标记 token lost，调用方需观测 | fixed in current slice (Slice 2) | Plan §Time / heartbeat ownership |
| 跨进程 clock skew 影响 capacity availability | existing issue (documented) | Plan §Residual Risks tracking |
| workspace runtime DB 文件残留 | later phase (Host composition root) | Plan §Non-Blocking Questions |
| Public Host contracts 可能在后续 phase 扩展 | later phase (command path) | Plan §Residual Risks tracking |
| ToolBundle digest 尚未实现 | later phase (ToolRuntime) | Plan §Non-Blocking Questions |

---

## Pyright / Code Constraints Alignment

Plan 的 Implementation instructions 明确要求:
- 禁止 `Any`、`object`、裸 `dict`、无类型参数/返回值
- 所有枚举使用 `StrEnum`
- 所有 dataclass 使用 `frozen=True, slots=True`
- JSON 值使用 `JsonValue` from `dayu.contracts.json_value`
- Weak typing guard test 机械化扫描禁止模式

上述要求与 CLAUDE.md 编码硬约束一致。Phase 1 的 `dayu.host` 类型定义只用 `str | None` 形式（非 `Optional`），符合 Python 3.11 现代风格。

一个注意点: `HostCallContext.authorization_claims: tuple[AuthorizationClaim, ...]` 使用 `tuple[..., ...]` 变长同构 tuple 表达，这在 Python 3.11 类型系统中是合法的。但 `tuple[AuthorizationClaim, ...]` 要求 mypy/pyright 较新版本支持；当前项目使用 pyright，已支持此语法。

---

## Documentation Update Alignment

Plan §Documentation Update Decision 的触发规则与 CLAUDE.md 的 README 同步要求一致：

- `dayu/README.md`: 需要更新（分层关系/boundary 变化 → 触发规则匹配）
- `dayu/host/README.md`: 需要新建（`dayu/host/` 修改 → 触发规则匹配）
- `tests/README.md`: 需要更新（`tests/` 修改 → 触发规则匹配）
- 根目录 `README.md`: 默认不更新（不改变用户命令/安装方式）
- `dayu/engine/README.md`: 不更新（禁止修改 Engine）
- `dayu/fins/README.md`: 不更新（禁止修改 Fins）
- `dayu/config/README.md`: 不更新（不改变配置）

对齐检查通过。注意：如果 `filelock` 加入 production dependencies 后 `pip install` 流程有变化，需重新评估根目录 README 是否需要更新。当前 plan 已将此项列为 "由 implementation agent 报告 controller 裁决"。

---

## Artifact Path

`docs/reviews/gateflow-plan-review-host-p1-public-contract-runtime-ds-20260513.md`
