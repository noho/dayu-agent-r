# Host 开发手册

本文档是 `dayu.host` 的包级开发手册。它不是 `docs/host/` 的文档索引，也不记录迁移过程、
Phase 流程、review 过程或 PR 流程。

## 当前状态

`dayu.host` 代码尚未落地。当前文件只固定 Host 开发手册的定位：

- 只写 Host 架构、接口、机制、状态机、稳定边界与扩展点。
- 只写当前已经落地的事实，不把迁移计划写成已实现能力。
- 不泄漏不必要的实现类、存储细节或临时迁移方案。

在 `dayu.host` 代码落地前，不应依赖任何 `dayu.host` 导入路径，也不应为旧 Host 接口创建兼容 wrapper、facade 或 re-export。

## 稳定边界

Host 位于固定分层中的 Service 与 Engine 之间：

```text
UI -> Service -> Host -> Engine
```

Host 的职责边界是通用 Agent 执行托管、会话、运行治理、恢复、上下文构造、工具运行时边界、事件事实与派生视图。Host 不承载财报业务知识，不直接理解财报文档语义。

财报文档存取必须通过 `dayu.fins.storage` 所属仓储边界由业务工具保证，不能进入 Host 或 Engine 的通用运行语义。

## 内容边界

代码分阶段落地后，本 README 只记录当前已经实现的 Host 开发事实：

- 当前公开接口。
- 当前 Session / Run / Attempt / Outbox 状态机。
- 当前 EngineWorker / Proxy / ToolRuntime 边界。
- 当前 EventLog / projection / observer 机制。
- 当前并发治理与启动恢复契约。
- 当前扩展点与测试入口。

不得把尚未实现的迁移计划写成已落地能力。
