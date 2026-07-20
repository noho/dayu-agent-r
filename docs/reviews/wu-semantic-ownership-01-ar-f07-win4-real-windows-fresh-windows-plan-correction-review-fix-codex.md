# WU-SEMANTIC-OWNERSHIP-01 / AR-F07 WIN4-RW-RF01 Corrected-plan Review Fix — AgentCodex

## Gate identity and verdict

- Timestamp：`2026-07-20T09:23:21+0800`。
- Umbrella：`WU-SEMANTIC-OWNERSHIP-01`。
- Continuation：`AR-F07 WIN4 real-Windows remediation`；不是新 WU。
- Gate：`WIN4-RW-RF01` corrected-plan review fix。
- Frozen plan：`docs/host/wu-semantic-ownership-01-ar-f07-win4-remediation-plan.md`。
- Controller verdict：`PASS / ACCEPTED_PLAN_FINDING=0 / ZERO-CHANGE_FIX_AND_DUAL_REREVIEW_REQUIRED`。
- AgentCodex disposition：`ZERO_CHANGE / PLAN_UNCHANGED / READY_FOR_CONTROLLER_VALIDATION_THEN_DUAL_COMPLETE_PLAN_REREVIEW / IMPLEMENTATION_NOT_AUTHORIZED`。

本 gate 的动机成立：固定流程要求 accepted finding 为零时仍形成可审计的 fix record，避免 conversation-only pass。
但没有可修的 plan finding；三个 observation 都已由 corrected plan 的 owner contract、negative matrix、exact allowlist 与
diff-review gate覆盖。修改 plan 会重开已冻结且已通过双路完整 review 的 contract，因此正确修复是只记录 disposition 与后续
implementation/review 检查点，不产生 plan delta。

## Consumed inputs and immutable locks

| Input | Lines | SHA-256 | Consumption |
| --- | ---: | --- | --- |
| Corrected plan | `1124` | `571ca834a515620283447a6c2166fc7bbd5dcf9393b685457a0ee7e959dc7ff2` | 完整读取；冻结 target |
| AgentMiMo review | `407` | `8580d4e6d9e3b4137e0f4b2cea8ea8ed9e4dd4a10c20df8cbffe50572b2de249` | 完整读取；material finding `0`，INFO `2` |
| AgentDS review | `235` | `c4d227cf99ff9ac991da030c2ab8fbc386f69d0c6c8e78bbb5e7fa88d674a9e0` | 完整读取；material finding `0`，OBS `1` |
| Controller review adjudication | `56` | `5fba7acfd70ab985b568c9457f5160537eb900c47548f22db1100043b379d729` | 完整读取；accepted plan finding `0` |
| Controller fresh-Windows evidence adjudication | `63` | `0193c1a03dd8f9c5bd7d78465c9d6d4e4aae4d661a373c7eccdc6c8f7c4d3ddb` | 完整读取；`WIN4-RW-RF01` test-oracle root cause |
| AgentCodex plan correction | `134` | `28aaa225122c17dc9083d6229556191a66734045e5bf865b71e38ddaec64dbdb` | 完整读取；corrected owner split |
| Controller plan-correction validation | `44` | `bffa43c3fd3a984ac9ea57c7de805fc387759fd9c865c2c1a190e921da4548a1` | 完整读取；corrected plan validation PASS |

同时读取并遵守 `AGENTS.md`、主总控 `docs/host/issues-implementation-control.md` 的当前 gate、附加总控
`docs/phaseflow-umbrella-optimization-control.md` 以及 corrected plan 的 governing/stop boundaries。Controller 是 finding
disposition 与 gate authorization 的唯一真源；reviewer 的 next-gate 简写不具授权效力。

## Frozen corrected-plan zero-change proof

| Measurement | Entry | Close | Result |
| --- | ---: | ---: | --- |
| Line count | `1124` | `1124` | unchanged |
| SHA-256 | `571ca834a515620283447a6c2166fc7bbd5dcf9393b685457a0ee7e959dc7ff2` | `571ca834a515620283447a6c2166fc7bbd5dcf9393b685457a0ee7e959dc7ff2` | exact match |

本 gate 未写入 plan。冻结 SHA 与用户预期 SHA 完全一致；没有 plan 格式化、措辞澄清、scan 增补或 next-gate 回写。

## Observation consumption and downstream checkpoints

### MiMo INFO-1 — optional `sha256` 的显式性

Disposition：`NO PLAN FIX / CONSUMED`。

Plan §13.2.1 已要求 raw-source descriptor 的 public `sha256` 精确等于 fixture bytes SHA-256；§13.5.1 已明确
`sha256` 为空或不匹配必须失败。因此 optional field 的 fail-closed contract已经完整，不存在 plan gap。显式检查只改善
future assertion 的 type/value locality，不改变 owner、schema或业务语义。

- `RF01-IMP-CHK-01`：future implementation只能在 exact snapshot assertion block内，先显式证明 raw-source descriptor
  `sha256 is not None`，再断言其值精确等于 `hashlib.sha256(fixture).hexdigest()`；等价的同一显式 type/value-safe assertion
  也可接受。不得靠 default、coercion、private meta或 storage read-back补偿。
- `RF01-REVIEW-CHK-01`：implementation review必须确认 optional空值 fail closed、hash只来自同一 fixture bytes与 public
  descriptor字段，并确认没有 schema/helper/import/oracle字段变化。

### MiMo INFO-2 — added-diff `rglob` scan

Disposition：`NO PLAN FIX / CONSUMED`。

Plan §13.2.1与§13.5.1已禁止用 physical tree或 `rglob` 推导 publication业务事实；§13.3把 future diff冻结为现有
snapshot assertion block；§13.6.5要求 zero-context function diff与 exact allowlist review。专门新增一条 regex只会重复
这些机械边界，不足以修改冻结 plan。

- `RF01-IMP-CHK-02`：future implementation artifact必须直接检查 target block added/changed lines没有新增 `rglob`，并证明
  既有 `rglob`/`source_artifact_count` 行零 diff、只保留 physical artifact-integrity语义。
- `RF01-REVIEW-CHK-02`：implementation review必须从 exact function diff确认 publication断言只消费 public
  `snapshot.files` descriptor `name/sha256`，没有把现有或新增 `rglob`、path count或 physical tree恢复为business oracle。

### DS OBS-DS-01 — current primary membership uses `in`

Disposition：`NO PLAN FIX / IMPLEMENTATION REQUIREMENT ALREADY EXPLICIT / CONSUMED`。

该 observation准确描述当前待修 test：membership `in` 不能拒绝 duplicate names。但 plan §13.2.1逐字要求 primary exact-name
恰好命中一个 descriptor，§13.5.1又要求 zero/multiple hits都失败；这正是 future implementation必须替换的现有行为，不是
plan omission。

- `RF01-IMP-CHK-03`：future implementation必须把 current primary `in` membership改为 exact cardinality `== 1`；raw
  source basename同样必须 exact cardinality `== 1`，两组匹配彼此独立，且只能修改现有 snapshot assertion block。
- `RF01-REVIEW-CHK-03`：implementation review必须检查 primary与raw-source两侧的 zero-hit/multiple-hit failure语义，并确认
  合法反例“primary指向非raw descriptor、raw descriptor独立存在且hash正确”通过；不得把当前 Docling filename固化为
  expected primary。

以上六个 checkpoint只消费 reviewer observation，供后续已授权 implementation/review gate使用；它们不授权本 gate修改
test，也不新增 plan finding、public contract、test helper或验证 scope。

## Reviewer next-gate wording correction

- AgentMiMo 结尾的“AgentDS 第二路 review”已过时：第二路 review已经完成。
- AgentDS 的 `READY_FOR_IMPLEMENTATION_GATE` 与 accepted-commit压缩跳过了用户固定的 fix/re-review流程，不能授权
  implementation。
- Controller 已纠正两路 wording：本 zero-change record形成后先由 Controller validation；正确的下一完整 review gate是
  AgentMiMo与AgentDS对 frozen corrected plan、两路初审、Controller adjudication及本 artifact执行双路完整 plan re-review。
  不是 implementation；accepted corrected-plan commit、implementation、remote dispatch与后续 gate均仍未授权。

## Exact write-scope proof

入场 `git status --short` 只有 Controller/plan-correction链路的八个既有 modified/untracked paths；staged tree为空。本 gate
把它们全部视为只读。入场与收口 content lock如下：

| Pre-existing path | Entry SHA-256 | Close SHA-256 |
| --- | --- | --- |
| `docs/host/issues-implementation-control.md` | `795f1705599f1ccd1633079a3ef5b22898bda8608e120b294c5f20440380c4b2` | `795f1705599f1ccd1633079a3ef5b22898bda8608e120b294c5f20440380c4b2` |
| `docs/host/wu-semantic-ownership-01-ar-f07-win4-remediation-plan.md` | `571ca834a515620283447a6c2166fc7bbd5dcf9393b685457a0ee7e959dc7ff2` | `571ca834a515620283447a6c2166fc7bbd5dcf9393b685457a0ee7e959dc7ff2` |
| fresh-Windows evidence adjudication | `0193c1a03dd8f9c5bd7d78465c9d6d4e4aae4d661a373c7eccdc6c8f7c4d3ddb` | `0193c1a03dd8f9c5bd7d78465c9d6d4e4aae4d661a373c7eccdc6c8f7c4d3ddb` |
| plan-correction AgentCodex artifact | `28aaa225122c17dc9083d6229556191a66734045e5bf865b71e38ddaec64dbdb` | `28aaa225122c17dc9083d6229556191a66734045e5bf865b71e38ddaec64dbdb` |
| plan-correction Controller validation | `bffa43c3fd3a984ac9ea57c7de805fc387759fd9c865c2c1a190e921da4548a1` | `bffa43c3fd3a984ac9ea57c7de805fc387759fd9c865c2c1a190e921da4548a1` |
| AgentMiMo review | `8580d4e6d9e3b4137e0f4b2cea8ea8ed9e4dd4a10c20df8cbffe50572b2de249` | `8580d4e6d9e3b4137e0f4b2cea8ea8ed9e4dd4a10c20df8cbffe50572b2de249` |
| AgentDS review | `c4d227cf99ff9ac991da030c2ab8fbc386f69d0c6c8e78bbb5e7fa88d674a9e0` | `c4d227cf99ff9ac991da030c2ab8fbc386f69d0c6c8e78bbb5e7fa88d674a9e0` |
| review Controller adjudication | `5fba7acfd70ab985b568c9457f5160537eb900c47548f22db1100043b379d729` | `5fba7acfd70ab985b568c9457f5160537eb900c47548f22db1100043b379d729` |

收口 path-set相对入场只新增本文件：
`docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-fresh-windows-plan-correction-review-fix-codex.md`。
没有修改 plan、control、任何既有 review/Controller artifact、product、test、README、design或workflow；staged tree保持为空；
没有创建 commit。

## Validation and stop status

| Check | Command | Result |
| --- | --- | --- |
| Full pyright | `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/` | `PASS / 0 errors, 0 warnings, 0 informations` |
| Tests | N/A | 本 gate无 product/test代码变化；未运行测试，如实记录 |
| Diff whitespace | `git diff --check` | `PASS / no output` |
| Staged tree | `git diff --cached --name-status` | `PASS / empty` |
| Scope/status | entry/close `git status --short` + pre-existing content SHA comparison | `PASS / only this artifact added` |
| README decision | 只新增 review artifact，不命中用户可见、测试运行或架构文档更新职责 | `NO UPDATE` |

Stop status：停在本 corrected-plan review fix gate。未更新 control，未进入 implementation，未 stage/commit/push/dispatch/PR。
Controller validation后只能进入双路完整 plan re-review。
