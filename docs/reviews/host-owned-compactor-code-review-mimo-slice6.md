# Code Review

## Scope

- Mode: current changes
- Branch: feat/host-p10-5-public-contract-freeze
- Base: main (当前 diff 为未提交 workspace changes)
- Output file: docs/reviews/host-owned-compactor-code-review-mimo-slice6.md
- Included scope: README.md、dayu/host/README.md、tests/README.md、docs/reviews/host-owned-compactor-implementation-slice6-codex.md
- Excluded scope: 生产代码、测试代码、dayu/README.md（已检查，无需修改）
- Parallel review coverage: 无

## 设计真源对齐

design doc: `docs/host/design.md` 关键约束：

- line 865: "Service / `open_host(options)` 只能提供 compactor runner / storage 配置…不能提供 `ContextCompactor` 实例、compact prompt、policy ref、candidate builder、quality check、artifact writer 或 repair callback"
- line 865: "Host 在 opener composition root 内部构造 Host-owned LLM compactor"
- line 869: "普通 Service 不得为了完成多轮闭环而直接装配或调用…`ContextCompactor.compact(...)`"
- line 869: "mock / test-double compactor 只能作为低层测试或显式本地辅助回归，不能作为普通本地多轮闭环的 compact success signal"

## Findings

未发现实质性问题。

各检查项逐一验证如下：

### 1）README 是否准确反映当前代码

**已验证通过。**

- `CompactorRunnerBaseline` 定义于 `dayu/host/api.py:921`，从 `dayu/host/__init__.py:58` 公开导出，是 Service-facing public contract。
- `open_host()` 在 `dayu/host/open_host.py:611` 内部构造 `LLMContextCompactor`，与 README 描述一致。
- `test_public_compact_smoke.py` 使用 `CompactorRunnerBaseline`（line 100）通过 public opener 触发 Host-owned compactor，不直接注入 `ContextCompactor`。
- `utils/smoke_host_public_multiturn.py` 使用 `CompactorRunnerBaseline`（line 348），脚本输出包含 `COMPACT_ARTIFACT_ROOT` 与 `COMPACT_ARTIFACT_FILE_COUNT`，不包含 compactor 调用次数。

### 2）旧语义是否清理干净

**已验证通过。**

```
rg 'CompactorExecutionBaseline|compactor_baseline|caller.owned|caller owned|ContextCompactor.*Service|Service.*ContextCompactor' README.md dayu/README.md dayu/host/README.md tests/README.md
```

零命中。`CompactorExecutionBaseline` 不在任何 Python 文件中（`rg` 零命中）。`compactor_baseline` 不在任何 Python 文件中。

### 3）是否没有把 Host 设计草稿/讨论痕迹写进用户 README

**已验证通过。**

- `README.md` 只更新了 §5.1 smoke 描述，内容为当前脚本行为的准确陈述。
- `dayu/host/README.md` 只更新了公共命名空间列表、`open_host` 装配描述与 Context Governance Boundary 段落，均为当前代码的稳定行为描述。
- 未出现 "计划"、"将会"、"后续"、"讨论中" 等未来设计痕迹。

### 4）README 职责是否遵守固定职责

**已验证通过。**

- `README.md`：更新了 §5.1 Host public smoke 使用说明（用户手册职责）。
- `dayu/host/README.md`：更新了 public opener contract 与 Context Governance Boundary（Host 开发手册职责）。
- `tests/README.md`：更新了 public-path smoke 描述（测试手册职责）。
- `dayu/README.md`：已检查，无残留旧术语，不修改（总览文档职责边界正确）。

### 5）smoke/test 描述是否和当前脚本/测试一致

**已验证通过。**

- `README.md` 描述的 smoke 输出项（Session / Run / terminal HostEvent 摘要、final answer 预览、mock tool 调用次数、compact artifact 路径）与 `utils/smoke_host_public_multiturn.py` 实际 print 语句一致。已删除的 "DeepSeek compactor 调用次数" 在脚本中确实不存在。
- `tests/README.md` 描述 `test_public_compact_smoke.py` 使用 `CompactorRunnerBaseline` 覆盖 public opener 内部构造 Host-owned compactor，与实际测试代码一致。该测试不使用 `FakeContextCompactor`（`FakeContextCompactor` 仅用于低层测试：`test_dispatch_scheduler.py`、`test_engine_ingest_mapping.py`、`test_compaction_contract.py`、`test_compact_artifact_store.py`）。

## Open Questions

无。

## Residual Risk

- 本次只做 README 同步，未改生产代码或测试代码，未运行 pytest。无残留风险。
- `dayu/host/api.py:746` 中 `OpenHostOptions.context_compactor: ContextCompactor | None = None` 仍为 optional 字段，允许低层测试传入自定义 compactor。README 已正确描述 "ContextCompactor 只作为 Host 内部 / 低层测试 seam"，但若后续需要彻底收紧 public contract，该字段需迁移至内部 options 或标记为 internal-only。此为已有状态，非本次 slice 引入。

## 结论

**PASS**
