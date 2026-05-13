# Host Phase Map Review — AgentMiMo

审查人：AgentMiMo
审查日期：2026-05-13
审查对象：
- `docs/design.md`
- `docs/host/implementation-control.md`

审查重点：phase map 的 plan assumptions、依赖正确性、半成品契约、过时引用、过度/不足设计、phase 耦合。

## 路径 / 真源发现

用户指定审查 `docs/design.md`，但 `docs/host/implementation-control.md` 的真源层级明确声明 Host 架构真源是 `docs/host/design.md`，而非项目级 `docs/design.md`。`docs/design.md` 是项目级设计文档（日志、runtime、contract ownership、工具边界），不承载 Host 架构决策。Phase entries 的 `对应设计章节` 均指向 `docs/host/design.md`，与真源层级声明一致。

如果用户意图是审查 Host 架构真源，则应以 `docs/host/design.md` 替代 `docs/design.md` 作为审查目标。本报告已审查 `docs/host/design.md` 的引用一致性，但未对 `docs/host/design.md` 做全文 adversarial 审查（不在指定范围内）。

---

## Findings

### P1-01: 真源层级路径引用可能误导 agent

**文件**：`docs/host/implementation-control.md`，真源层级代码块（约 L24-L36）

**问题**：

代码块中 Host 架构真源写为 `design.md`（相对路径），而非实际路径 `docs/host/design.md`。Phase entries 的 `对应设计章节` 字段均使用 `docs/host/design.md`（正确路径）。Phase 讨论、plan 和 implementation agent 若按代码块中的 `design.md` 查找文件，会找到项目级 `docs/design.md`（日志与 runtime 设计），而非 Host 架构真源。

**影响**：可能导致 agent 在 phase discussion / plan 阶段引用错误的设计文档，产生架构判断偏差。

**修复**：将真源层级代码块中的 `design.md` 改为 `docs/host/design.md`。

---

### P1-02: Phase 4 后续依赖未显式列出 Phase 8 的依赖关系

**文件**：`docs/host/implementation-control.md`，Phase 4 后续依赖（约 L490-L491）

**问题**：

Phase 8（Projection Core）的前置条件明确列出 `Phase 4 public read APIs 已完成`（L677）。但 Phase 4 的 `后续依赖` 只写 `public command path、Host handle、typed options、snapshot shape、API idempotency`，未提及 Phase 8 将依赖其 read API shape。Phase 4 的 `需要追踪到后续 phase 的事项` 也未提及 read model / event stream 接口属于后续 projection phase 的输入。

**影响**：Phase 4 plan 可能不把 read API shape 作为明确交付物，导致 Phase 8 进入时发现 read API contract 不完整。

**修复**：在 Phase 4 后续依赖中增加：`后续 phase 可依赖的稳定契约：... read API shape（get_run / get_session / stream_run_events 的 snapshot 与 stream contract）`；在追踪事项中增加：`Phase 8 Projection Core 依赖本 phase 的 read API shape 与 snapshot contract`。

---

### P1-03: Phase 条目模板 `对应设计章节` 字段描述歧义

**文件**：`docs/host/implementation-control.md`，Phase 条目模板（约 L108-L109, L157）

**问题**：

模板中 `对应设计章节` 示例写 `docs/host/design.md §...`（正确路径），但字段含义说明写 `phase plan 的架构依据，只能引用 design.md 和本文档，不得引用旧讨论稿`。此处 `design.md` 未带路径前缀，与真源层级代码块中的歧义一致。

**影响**：同 P1-01，可能误导 agent 引用项目级 `docs/design.md`。

**修复**：将字段含义说明中的 `design.md` 改为 `docs/host/design.md`。

---

### P1-04: Phase 4 推迟项未在 Phase 14 进入条件中追踪

**文件**：`docs/host/implementation-control.md`，Phase 4 不做（约 L460-L461）与 Phase 14 进入条件（约 L1029-L1030）

**问题**：

Phase 4 明确列出两项推迟：
- `不实现 resolve_wait 的等待结果治理语义；该能力在 Phase 7 落地。`
- `不实现 purge_session 的 destructive cleanup；该能力在 Phase 14 落地。`

Phase 7 和 Phase 14 的 scope 确实覆盖了这些能力。但 Phase 4 的 `后续依赖` 和追踪区未将这两项标记为"需要追踪到后续 phase 的事项"。Phase 7 和 Phase 14 的进入条件也未回指 Phase 4 的推迟决策。

**影响**：Phase 7 / Phase 14 plan 可能遗漏 Phase 4 推迟时积累的 context 或 contract 假设。

**修复**：在 Phase 4 追踪事项中增加：`resolve_wait contract 由 Phase 7 落地；purge_session destructive cleanup 由 Phase 14 落地。Phase 7 / Phase 14 进入条件应确认 Phase 4 中对应的 contract 假设是否仍成立`。

---

### P2-01: Phase 0 与 Phase 1 的 scope 边界有重叠

**文件**：`docs/host/implementation-control.md`，Phase 0 scope（约 L228-L231）与 Phase 1 scope（约 L284-L286）

**问题**：

Phase 0 范围：`Engine context overflow event contract、Engine README、Engine design docs、相关 Engine tests`。
Phase 1 范围：`公共契约、Host request / snapshot / error typing、dayu.runtime.lane、dayu.runtime.filelock、ToolsDiscovery / ScenePrepare 的层中立装配接口`。

Phase 0 的交付物包含 `Engine README / docs/engine/design.md / dayu/README.md 同步`（L250）。Phase 1 的交付物也包含 `dayu/README.md 与受影响包 README 同步`（L314）。`dayu/README.md` 在两个 phase 中都可能出现修改，但未说明 Phase 0 修改了 `dayu/README.md` 的哪些部分、Phase 1 如何在 Phase 0 基础上增量修改。

**影响**：Phase 1 plan 可能重复 Phase 0 已完成的 `dayu/README.md` 同步工作，或遗漏 Phase 0 已建立的术语约定。

**修复**：在 Phase 1 进入条件中增加：`确认 Phase 0 对 dayu/README.md 的修改已合入，Phase 1 只做增量同步`。

---

### P2-02: Phase 2 / Phase 3 / Phase 6 进入条件缺乏确认格式

**文件**：`docs/host/implementation-control.md`，Phase 2（约 L338-L339）、Phase 3（约 L395-L396）、Phase 6（约 L568-L569）

**问题**：

三个 phase 的进入条件均以"确认..."开头，但未说明确认的形式（用户口头确认、文档更新、typed contract 文件、测试通过等）：
- Phase 2：`确认第一版 SQLite schema、transaction runner、WAL / busy timeout / retry policy、payload threshold 与 artifact 目录注入方式。`
- Phase 3：`确认状态迁移表是否足够直接生成 typed transition service 与测试矩阵。`
- Phase 6：`确认 ToolRuntime ports、accept idempotency key、effective ToolBundle 与 truncation descriptor 的最小 typed contract。`

**影响**：进入条件的模糊性可能导致 phase discussion 产出不一致的确认标准，或在 plan review 时对"是否满足进入条件"产生分歧。

**修复**：在每个进入条件后增加确认形式说明，例如 `（用户确认或 design.md 章节已细化到可直接生成 typed contract）`。

---

### P2-03: Phase 14 scope 过宽，可能超出单次 phase discussion 承载

**文件**：`docs/host/implementation-control.md`，Phase 14 scope（约 L1032-L1034）

**问题**：

Phase 14 范围包括：`purge_session command implementation、purge delete ranges、shared artifact ref check、projection rebuild tooling、audit tombstone query support、stress / smoke tests、README sync`。建议 slice 切分为 4 个 slices（L1053-L1056），覆盖 purge、projection rebuild、multi-process smoke 和文档收口。

这个范围横跨 command path、storage、projection、testing 和 docs 五个关注点。Phase 14 的进入条件要求 Phase 8、11、12、13 均已完成，意味着它是一个收口 phase。但 scope 中 `stress / smoke tests` 和 `projection rebuild tooling` 的复杂度可能超出预期。

**影响**：Phase 14 plan 可能因 scope 过宽而产生过大的 slice，或在 phase discussion 中遗漏某些收口项。

**修复**：建议在 Phase 14 的 phase discussion 中优先确认哪些收口项是 release-blocking、哪些可以作为 follow-up issue。如果 `stress / smoke tests` 或 `projection rebuild tooling` 复杂度过高，可考虑拆出独立 phase。

---

### P2-04: Phase 1 scope 过宽，三类关注点在同一 phase 中

**文件**：`docs/host/implementation-control.md`，Phase 1 scope（约 L284-L286）

**问题**：

Phase 1 scope 包含三类关注点：
1. Host API request / snapshot / error typing（Host 治理层）
2. `dayu.runtime.lane` 与 `dayu.runtime.filelock`（runtime 基础设施层）
3. ToolsDiscovery / ScenePrepare 层中立装配接口（装配边界层）

这三类关注点分属不同架构层级，但共享同一个 phase。建议 slice 切分已按这三类拆分（L306-L308），但 phase discussion 需要一次性覆盖所有三类。

**影响**：Phase 1 discussion 可能因关注点过多而无法对每类做足够深入的细化。

**修复**：这不是阻塞问题。建议 Phase 1 discussion 按 slice 顺序逐类讨论，每类确认后再进入下一类。如果讨论中发现某类需要重大架构决策，可考虑将其拆为独立 phase。

---

### P2-05: Phase 5 的 RunInputBuilder provider protocols 未在 Phase 1 中建立

**文件**：`docs/host/implementation-control.md`，Phase 1 scope（约 L284-L286）与 Phase 5 scope（约 L512-L513）

**问题**：

Phase 1 scope 包含 `Host request / snapshot / error typing`，但未包含 RunInputBuilder 的 typed input provider protocols（`CurrentRunFactProvider`、`MemorySnapshotProvider` 等，见 design.md §23）。Phase 5 scope 包含 `RunInputBuilder provider protocols`（L512），但 Phase 5 的前置条件只有 Phase 4 和 Phase 1 runtime lane。

RunInputBuilder provider protocols 是 Phase 5 执行闭环的关键 contract。如果这些 protocols 不在 Phase 1 建立，Phase 5 plan 需要自行定义它们，可能导致 contract 定义与 Phase 1 的公共类型风格不一致。

**影响**：Phase 5 可能需要在自己的 scope 内定义额外的 typed contracts，增加 phase 内部复杂度。

**修复**：在 Phase 1 追踪事项中增加：`RunInputBuilder typed input provider protocols（design.md §23）在 Phase 5 建立，不在本 phase 落地。Phase 5 plan 应确认这些 protocols 的风格与 Phase 1 公共类型一致`。

---

## No Finding Notes

以下方面已检查，未发现问题：

- **Phase 依赖图无环**：Phase 0 → 1 → 2 → 3 → 4 → 5 → 6 → 7 / 8 → 9 → 10 → 11 → 12 → 13 → 14。无循环依赖。
- **Phase 编号连续**：Phase 0 到 Phase 14，共 15 个 phase，编号连续无跳跃。
- **Phase entries 使用统一模板**：所有 phase entries 均使用 `Phase 条目模板` 定义的字段结构。
- **design.md §引用覆盖**：implementation-control.md 引用的 design.md 章节（§3, §5, §6, §7, §8, §9, §10, §10.1, §11, §12, §13, §13.1, §13.4, §14, §14.1, §15, §16, §17, §18, §18.1, §18.2, §18.3, §19, §20, §21, §22, §23, §24, §25, §25.1, §26, §27, §27.1, §28）均在 design.md 中有对应内容。
- **追踪区覆盖完整**：追踪区包含 8 个追踪项，覆盖 Engine cleanup、External Job Cancel、Tool Trace、SQLite、Remote exactly-once、Session Purge、测试策略、UI Outbox 去重。这些追踪项与 phase entries 的进入条件和退出条件有对应关系。
- **术语一致性**：implementation-control.md 使用的术语（Session、Run、Attempt、EventLog、canonical_fact、EngineEvent stream、Host event stream、ToolRuntime、fetch_more、TruncationManager 等）与 dayu/README.md 术语表一致。
- **Phase 5 → Phase 6 → Phase 7 依赖链正确**：Phase 6 依赖 Phase 5 本地执行闭环，Phase 7 依赖 Phase 6 ToolRuntime accept barrier。Phase 5 的 `后续依赖` 明确提到 `RemoteProxy 必须保持与 LocalProxy 等价语义`，Phase 13 在此基础上实现。
- **Phase 8 → Phase 9 → Phase 10 依赖链正确**：Phase 9 依赖 Phase 8 projection runner 和 Phase 5 RunInputBuilder，Phase 10 依赖 Phase 9 memory projection 和 Phase 5 dispatch。无交叉依赖冲突。
- **Phase 12 前置条件合理**：Phase 12 依赖 Phase 8（projection framework）、Phase 6（ToolRuntime diagnostic refs）和 Phase 11（recovery）。Audit / Tool Trace / Outbox 作为 projection sinks 后置到核心治理路径稳定之后，符合设计意图。
- **Phase 13 前置条件合理**：Phase 13 依赖 Phase 5（LocalProxy 基准）、Phase 6（ToolRuntime accept barrier）和 Phase 11（recovery）。RemoteProxy 作为 transport substitution 后置到本地路径稳定之后，符合设计意图。
- **Phase 14 前置条件合理**：Phase 14 依赖 Phase 8、11、12、13 均已完成，作为收口 phase 后置，符合设计意图。
- **强制约束与 design.md 一致**：implementation-control.md 的强制约束（约 L170-L206）均来自 design.md 和 dayu/README.md 的终态设计语义，未引入新的架构决策。
- **设计目标一致**：implementation-control.md 的设计目标（L10-L17）与 design.md §1 和 dayu/README.md 设计目标一致。

---

## Residual Risks

### R-01: Phase 0 可能被跳过或推迟

Phase 0 前置条件要求"用户明确确认允许修改 Engine 代码"。如果用户决定推迟 Phase 0，Phase 1 的进入条件需要确认该例外。追踪区已写明 `Host Context Governance phase 的 plan 必须显式依赖这个 Engine cleanup 完成，或在 plan 中写明临时兼容假设并禁止消费 0/0/0 作为真实预算`。该风险有明确治理路径，不阻塞 phase map 整体正确性。

### R-02: Phase 14 scope 可能需要进一步拆分

Phase 14 的 scope 横跨 purge、projection rebuild、stress test 和 docs 五个关注点。如果 phase discussion 发现某些收口项复杂度超出预期，可能需要拆出独立 phase。当前建议 slice 切分为 4 个 slices，但未预留拆 phase 的空间。这不阻塞当前 phase map draft，但应在 Phase 14 discussion 时重新评估。

### R-03: design.md 的全面 adversarial 审查未在本次覆盖

本次审查聚焦于 implementation-control.md 的 phase map 与 design.md 的引用一致性。design.md 自身的架构正确性、状态机完整性、边界矛盾等需要单独的 adversarial 审查。此前的 host-design-review 系列报告已覆盖部分内容，但最新版 design.md 可能需要 re-review。

---

## 结论

**无阻塞发现**。Phase map 的依赖关系正确，phase 编号连续，术语一致，追踪区覆盖完整。

有 3 个 P1 发现（路径引用歧义、Phase 4 追踪缺失、模板描述歧义）和 5 个 P2 发现（phase scope 重叠、进入条件格式、Phase 14 scope 过宽等），均为可直接修复的文档改进项，不改变 phase 编排结构。

Phase map 已准备好进入下一步：逐 phase 讨论并细化 `docs/host/design.md` 对应章节，然后生成 handoff implementation-ready plan。
