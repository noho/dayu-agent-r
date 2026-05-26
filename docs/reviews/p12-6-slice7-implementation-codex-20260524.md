# P12.6 Slice 7 Implementation Artifact

## 基本信息

- Gate: implementation
- Work-unit: P12.6 conversation memory redesign
- Slice: Slice 7 Public Compact Smoke、README 同步与最终验证
- Agent: AgentCodex
- 日期: 2026-05-24
- Base checkpoint: `a2114a2 gateflow: accept P12.6 slice 6`

## 动机判断

P12.6 public smoke 的动机成立。P12.6 的成功信号不只是内部 contract 是否能构造 compact material pack，还包括 public opener 在真实 Host lifecycle、pre-start governance、memory catch-up、RunInputBuilder 和 compactor runner 边界下是否维持连续性、bounded input 与 prompt-local label 语义。仅靠 lower-level contract tests 无法发现 public watcher 超时、payload inline threshold、real provider 默认执行或 public opener 装配差异。

本 slice 不能引入真实 provider 网络依赖。deterministic public smoke 使用 `open_host(options)`、mock worker、`CompactorRunnerBaseline` 与 monkeypatched compactor runner 返回 label-only JSON。真实 compactor smoke 保留为 optional，默认通过 `DAYU_RUN_REAL_COMPACTOR_SMOKE=1` 才运行。

## 改动文件

- `tests/host/fake_compaction.py`
  - `FakeContextCompactor` 改为先基于 `CompactionRequest.llm_material_json()` 生成只含 prompt-local material / evidence labels 的 strict JSON proposal，再复用生产 LLM proposal parser 映射回 Host-owned candidate。
  - 新增 `fake_compaction_proposal_from_material_json(...)`，确保 fake compactor 不直接生成 canonical Host refs。
  - 保留既有 fake candidate id / summary title 约定，避免破坏既有 focused tests。
- `tests/host/test_public_compact_smoke.py`
  - 增加 deterministic P12.6 compact smoke：
    - no-compaction recent raw turns continuity；
    - label-only raw accepted evidence material 到 fact candidate 的最小替代覆盖；
    - 长 user input compact 后下一轮通过 minimum preserve 看到“第二个因素”；
    - 多次 compact 后 compactor prompt 与后续 memory input bounded；
    - duplicate prompt proactive compact 不因 compactor material 重复超窗失败。
  - 真实 compactor smoke 默认 skip，设置 `DAYU_RUN_REAL_COMPACTOR_SMOKE=1` 才运行。
  - deterministic compact smoke 提高测试用 payload inline threshold，避免长 compact payload 的基础设施阈值掩盖 memory / compactor 语义信号。
- `tests/README.md`
  - 同步 public compact smoke 当前事实、real compactor optional 行为与 deterministic fake compactor 位置。

## Public Path 覆盖缺口与最小替代

尝试用 public opener + mock business tool + deterministic compactor 覆盖“长章节 tool result extraction 不依赖 preview，基于 raw accepted evidence block”时，直接证据显示 public proactive compactor prompt 中 `evidence_input` 为空，即使将 soft threshold 降到 1 触发每轮 proactive compact，material JSON 仍只有 `current_input_anchor`：

```text
"evidence_input": [],
"history_input": [],
"stable_input": []
```

该信号无法在 Slice 7 允许文件范围内通过 fake/mocked public path deterministic 覆盖；修复需要生产路径让 accepted tool evidence 进入 public compactor material pack，已超出本 slice “不修改生产代码，除非先停止并记录 stop condition”的约束。

最小可维护替代：

- 在 `tests/host/test_public_compact_smoke.py` 中保留 material-label fake proposal smoke，直接验证 raw accepted evidence material block 使用 `E1` label 生成 fact candidate，且 proposal 不包含 `result_preview`、event id 或 payload ref。
- 既有 focused tests 继续覆盖生产 owner：
  - `tests/host/test_compaction_contract.py`
  - `tests/host/test_llm_compaction.py`
  - `tests/host/test_compaction_operation.py`
  - `tests/host/test_memory_projection.py`
  - `tests/host/test_run_input_builder.py`

该缺口应由后续生产修复 slice 或 Controller 裁决，不应在 Slice 7 测试中通过伪造 public evidence input 掩盖。

## README 决策

- 更新 `tests/README.md`：测试职责命中，且 public compact smoke 与 real compactor optional 行为已变化。
- 未更新 `dayu/host/README.md`：未修改 Host 生产接口、状态机、Context Governance 或 memory contract。
- 未更新 `dayu/config/README.md`：prompt asset 说明未变化。
- 未更新 `dayu/README.md`：分层关系、装配方式与术语未变化。

## 验证结果

- `source .venv/bin/activate && pytest tests/host/test_public_compact_smoke.py -q`
  - 结果：`5 passed, 1 skipped`
  - skip：默认关闭的 optional real compactor smoke。
- `source .venv/bin/activate && pytest tests/host/test_compaction_contract.py tests/host/test_llm_compaction.py tests/host/test_compaction_operation.py tests/host/test_context_compact_events.py tests/host/test_compact_artifact_store.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py tests/host/test_dispatch_scheduler.py tests/host/test_engine_ingest_mapping.py tests/host/test_public_compact_smoke.py -q`
  - 结果：`292 passed, 1 skipped`
- `source .venv/bin/activate && python -m pyright dayu/ tests/`
  - 结果：`0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - 结果：通过，无输出。

## 风险与未覆盖项

- Public opener 当前无法 deterministic 覆盖 accepted tool evidence 进入 compactor `evidence_input` 的完整链路；本 artifact 已记录为 Slice 7 stop-condition gap。
- 真实 provider compactor smoke 默认不作为通过条件；只有显式设置 `DAYU_RUN_REAL_COMPACTOR_SMOKE=1` 才会运行，避免网络、quota 或 provider 输出不稳定影响默认验证。
- 本 slice 未修改生产代码；若 Controller 接受 public evidence gap 为 blocking finding，应进入后续 fix / implementation slice，而不是在测试中伪造 public path。

## 完成状态

Slice 7 implementation 完成；存在已记录的 public accepted-tool-evidence compact 覆盖缺口，默认验证不依赖真实 provider 网络。
