# dayu/README.md 同步检查

## 检查范围

- 读取 `docs/host/design.md`，对齐 Host 的分层边界、runtime 边界、Host-owned context governance、public contract 和日志语义。
- 读取 `dayu/README.md`，检查是否违反“只写当前代码已实现的整体架构、设计意图、稳定边界、扩展入口、代码阅读顺序”的约束。
- 读取必要当前代码 / public exports：
  - `dayu/host/__init__.py`
  - `dayu/host/api.py`
  - `dayu/host/open_host.py`
  - `dayu/host/tooling.py`
  - `dayu/host/compaction.py`
  - `dayu/engine/__init__.py`
  - `dayu/contracts/__init__.py`
  - `dayu/runtime/__init__.py`

## 检查结论

- 原 `dayu/README.md` 的问题真实存在：它包含大量 Host 术语真源级内容、phase / implementation / review 表述，以及 ToolRuntime、Context Governance、日志字段等细粒度实现说明，职责已经越过 `dayu/` 开发手册总览。
- `docs/host/design.md` 是 Host 设计真源；`dayu/README.md` 不应复制 Host 详细状态机、事件族、tool trace、等待、projection 等设计细节。
- 当前代码 public surface 中 `dayu.host` 包根已导出 `open_host`、`OpenHostOptions`、`Host`、普通 Host facade request / snapshot / status / error / context / cursor 类型、`HostToolingOptions`、`OrdinaryRunExecutionBaseline`、`CompactorRunnerBaseline` 和 local worker typed boundary；低层 command handle factory、`start_run`、durable store、dispatch scheduler、ToolRuntime factory 等不属于包根公共命名空间。
- 当前代码中 `OpenHostOptions` 使用 `CompactorRunnerBaseline` 装配 Host-owned LLM compaction；README 已避免旧的 caller-owned / Service-owned compactor 表述。

## 修改项

- 将 `dayu/README.md` 收敛为开发手册总览，保留：
  - 设计意图。
  - `UI -> Service -> Host -> Engine` 分层与依赖方向。
  - `dayu.contracts`、`dayu.engine`、`dayu.host`、`dayu.runtime`、`dayu.fins` 的稳定边界。
  - 少量跨包核心术语。
  - 日志语义总览。
  - 扩展入口。
  - 代码阅读顺序。
- 删除原 README 中大量 Host 详细术语表、phase / implementation / review 过程表述、runtime 详细 API 行为和 ToolRuntime 细节。
- 对齐当前命名：
  - 使用 `LLM in the loop`。
  - 使用 `CompactorRunnerBaseline`。
  - 使用 `OpenHostOptions` / `Host` / `open_host` 描述 Host public handle。
  - 使用 `Host-owned LLM compaction` 描述上下文压缩治理边界。

## 不改项

- 不修改 `docs/host/design.md`。
- 不修改其它 README。
- 不修改代码或 tests。
- 不提交、不 push。
- 不把 Host 状态机、EventLog schema、ToolRuntime 内部流程、ContextCompactor protocol 细节搬入总览 README；这些属于 Host 设计文档或包级 README。

## 验证

执行命令：

```bash
rg 'CompactorExecutionBaseline|compactor_baseline|caller-owned|caller owned|Service.*ContextCompactor|ContextCompactor.*Service|AsyncOpenAIRunner|LLM on the loop|正在|计划|未来|TODO' dayu/README.md
```

结果仅命中 `Agent更新约束` 中的固定约束句：

```text
8:- 本文档不写过程状态，不写未来计划，不写实现细节，只保留稳定说明。
```

判断：该命中合理，因为它是 README 自身的文档维护约束，不是过程状态、未来承诺或旧架构表述。

执行命令：

```bash
git diff --check
```

结果：通过，无 trailing whitespace 或 whitespace error。
