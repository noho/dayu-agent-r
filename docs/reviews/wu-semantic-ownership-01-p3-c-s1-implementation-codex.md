# WU-SEMANTIC-OWNERSHIP-01 P3-C S1 Implementation

## Gate 与状态

- Gate：P3-C S1 implementation。
- Accepted plan：commit `0dcef803`。
- 当前状态：`implementation-complete`；S1 实现与 validation 已闭合。
- Blocking questions：0。
- 下一入口：P3-C S1 code review；本 gate 按用户要求不进入 review、S2/S3、commit 或 control doc 更新。

## 第一性原理与 owner boundary 核验

动机成立。生产 producer `build_context_compacted_payload()` 持久化
`ConversationCompactOutputVNext.to_json()`；该 shape 含 Host-owned `evidence_kind`、
完整 answer-anchor children/ordinal、严格 forward-intent type/status 与 reference reason。
未发现合法 producer shape 与 accepted plan 冲突。

修复前 persisted read side 有两个事实 owner：

- `context_events.validate_context_compacted_payload()` 只校验 candidate 顶层与 list/object 基础形状；
- `memory.py` 再从 raw mapping 独立读取五类业务字段，并把三个 enum 保存为裸字符串。

S1 owner boundary 固定为：

1. 首次产生：typed compactor output + Host accept barrier。
2. 校验 owner：`compact_payload.parse_context_compacted_semantic_payload()`。
3. 持久化真源：canonical `CONTEXT_COMPACTED` EventLog payload。
4. typed projection：两个 durable event adapter 在 EventLog read boundary 各解析一次，
   `MemoryProjectionEvent` 只携带 `ContextCompactedSemanticPayload`。
5. 消费：Conversation Memory、snapshot/table codec、RunInput memory enum renderer。

## 已实施改动

### Production

- `dayu/host/compact_payload.py`
  - 新增 `ContextCompactedSemanticPayload` 与唯一 persisted semantic parser。
  - 严格恢复 summary、fact（含 `evidence_kind`）、完整 anchor children/ordinal、intent、reference、diagnostic。
  - 对缺字段、未知字段、错误 list/object/text/ordinal、非法 enum、非法或不一致 digest fail closed。
  - 新增 `accepted_compact_business_texts()`，只返回五类业务文本，不返回 labels、diagnostics、refs 或 digest。
- `dayu/host/context_events.py`
  - canonical governance 字段校验保持在本模块；nested candidate validation 委托唯一 parser。
  - 删除第二套浅层 `_validate_vnext_candidate_payload()`。
- `dayu/host/memory.py`
  - `MemoryProjectionEvent` 新增 `compacted_semantics`，并强制 compact/non-compact pairing。
  - 五类 memory projector 只消费 typed candidate；删除 raw candidate 字段常量、mapping parser 与 nested accessors。
  - `ForwardIntent.intent_type/status` 与 `ReferenceContinuityItem.reason` 收紧为严格 enum。
  - snapshot JSON 写 enum `.value`，读侧以 enum constructor 严格恢复；完整 anchor children/ordinal 保留。
- `dayu/host/durable/memory.py`
  - durable projection adapter 在 `CONTEXT_COMPACTED` EventLog boundary 调用唯一 parser。
  - memory item table JSON 显式写 enum `.value`。
- `dayu/host/run_input.py`
  - inline repair adapter 在 `CONTEXT_COMPACTED` EventLog boundary 调用唯一 parser。
  - Memory section renderer 显式渲染 enum `.value`。

### Allowed tests

- `tests/host/test_context_compact_events.py`
  - 增加 full typed roundtrip、完整 children/ordinal、business text、非法 enum、缺
    `evidence_kind`、错误 nested shape、负 ordinal、旧字段与 digest mismatch 测试。
- `tests/host/test_memory_projection.py`
  - accepted compact fixture 改走 typed candidate + `build_context_compacted_payload()`。
  - 验证 enum identity、完整 children/ordinal、snapshot `.value` roundtrip 与非法 snapshot enum fail closed。
  - 验证非法 persisted enum 使 ProjectionRunner 记录 failure，且 snapshot/checkpoint 不推进。
  - 删除原来让下游接受空 evidence-label 弱 shape 的测试路径；非法 persisted shape 只在 parser owner 测试。
- `tests/host/test_run_input_builder.py`
  - inline-repair compact fixture 改走 typed candidate + canonical builder。
- `tests/host/memory_snapshot_factories.py`
  - 按 controller-approved test scope extension，把共享 snapshot fixture 的 intent/reference 裸字符串迁为严格 enum。
- `tests/host/test_compact_material.py`
  - 仅迁移直接构造 typed memory snapshot 的 intent/reference enum constructor；未改变 previous-view、pair、renderer 或 budget 测试行为。
- `dayu/host/README.md`
  - 按 Host README 职责记录 persisted accepted compact 唯一严格 typed read boundary 与 fail-closed 语义。

## Plan 偏差与 controller adjudication

生产 contract/API 无计划偏差；未实现 S2 previous-view、ordinary duplicate renderer、budget，
也未实现 S3 evidence renderer。

发现 accepted plan 的 test file ownership 缺口：严格 enum 直接影响现有
`tests/host/memory_snapshot_factories.py` 和 `tests/host/test_compact_material.py`，但二者不在
S1 allowed tests。直接证据：

- focused matrix：`196 passed, 6 failed`；6 个失败全部由共享 snapshot fixture 用裸字符串
  构造 `ReferenceContinuityItem` 触发，生产 strict constructor 正确 fail closed。
- full pyright：`19 errors` 首次运行；修正 allowed files 自身类型问题后，剩余错误均来自上述
  两个 forbidden test files（共享 fixture 4 个、compact material test 9 个）。

不能通过生产 constructor 接受/转换字符串解决，因为那会违反 strict enum、禁止兼容与“只消费 typed candidate”约束。
Controller 基于该直接证据明确授权把 test-only 写范围最小扩展到上述两个文件，仅做 enum constructor/value 与直接 fixture/assertion 迁移。
实施结果：未增加生产兼容分支，focused matrix 与 full pyright 均闭合；这是唯一 approved plan deviation。

## 验证

已通过：

- focused matrix：
  `python -m pytest tests/host/test_context_compact_events.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py tests/host/test_compact_material.py -q`
  - `255 passed`。
- 全量 pyright：`python -m pyright dayu/ tests/ utils/`
  - `0 errors, 0 warnings, 0 informations`。
- 实际修改 production 文件逐文件 coverage（均以 `--fail-under=80` 验证）：
  - `dayu/host/compact_payload.py`：80%。
  - `dayu/host/context_events.py`：93%。
  - `dayu/host/memory.py`：92%。
  - `dayu/host/durable/memory.py`：86%。
  - `dayu/host/run_input.py`：88%。
- `python -m pytest tests/host/test_import_boundary.py tests/host/test_weak_typing_guard.py -q`
  - `25 passed`。
- import smoke：`dayu.host`、`dayu.host.compact_payload`、`dayu.host.memory`、
  `dayu.host.run_input` 通过。
- ownership source scans：
  - `memory.py` 中 `_accepted_candidate_mapping` 与五类 candidate 字段常量零匹配；
  - parser 只在 owner、canonical validator、durable adapter、inline repair adapter 出现；
  - snapshot/table 裸 enum write scan零匹配；两个扩展 fixture 文件的裸字符串 memory enum constructor scan 零匹配。
- `git diff --check` 通过。
- README decision：更新 `dayu/host/README.md` 的当前稳定 owner contract；`tests/README.md` 未新增测试层级、测试文件或常用命令职责，因此不机械更新。
- 未运行 commit、control doc、S2/S3、code review/deepreview/PR 操作。

## Propagation audit

当前实现路径：

```text
ConversationCompactOutputVNext
  -> build_context_compacted_payload / candidate.to_json + digest
  -> CONTEXT_COMPACTED EventLog payload
  -> parse_context_compacted_semantic_payload
     -> context_events canonical validation
     -> durable memory adapter / run_input inline-repair adapter
        -> MemoryProjectionEvent.compacted_semantics
        -> Conversation Memory 五类 typed projection
        -> snapshot JSON + item table JSON enum .value
        -> snapshot enum constructor strict restore
        -> RunInput memory section enum .value renderer
```

一致性结论：

- candidate digest 由 parser 与 typed candidate canonical digest 精确比对；mismatch fail closed。
- compact artifact ref 与 accepted evidence mapping refs 从同一 semantic payload view 传播到 memory fact projection。
- summary/fact/anchor/intention/reference 均从同一个 typed candidate 派生；Memory 不再读取 raw nested candidate。
- anchor title、全部 children 与 ordinal 在 producer -> parser -> memory -> snapshot roundtrip 中保持完整。
- intent type/status 与 reference reason 在 parser、memory、snapshot/table、RunInput renderer 全程为同一 enum truth；非法值不写 snapshot、不产生 unknown fallback。
- S2 的 previous compacted view 与 ordinary duplicate compact renderer 尚未触及；S3 evidence material 尚未触及。

## Residual risks

- `covered by later approved slice`：previous-view string roundtrip、ordinary duplicate compact renderer、budget owner 属于 S2。
- `covered by later approved slice`：accepted evidence typed material/renderer 与 typed mismatch 属于 S3。
- `fixed in current slice`：persisted candidate weak parsing、enum drift、anchor children/ordinal 丢失风险、snapshot enum lenient restore。
- `fixed in current slice`：accepted plan 漏列的两个 strict-enum test consumers 已按 controller 授权迁移。
- 未分类 residual risk：0；blocking questions：0。

## Artifact

`docs/reviews/wu-semantic-ownership-01-p3-c-s1-implementation-codex.md`
