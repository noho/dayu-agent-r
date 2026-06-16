# WU-CLI-SESSION-01 S6 documentation synchronization - Codex

## 修改摘要

- `docs/host/design.md`：把 `list_sessions(host) -> ListSessionsResult` 加入 Host public API 列表，并说明它读取未 purge Session 的 durable truth 列表摘要，不是 projection，不触发 projection catch-up 或执行；补充 CLI `session resume` 与 Host `resolve_wait` wait-resume 的术语边界。
- `dayu/host/README.md`：在 Host handle 方法、包根 facade、Host 专属契约与稳定边界中同步 `list_sessions` 当前实现能力。
- `dayu/README.md`：仅在 Host public contract 总览补充 Session 列表读取结果与 `list_sessions` typed read view，不写 CLI 用户手册。
- `tests/README.md`：确认 CLI session list/resume/purge、`interactive --new-session` 删除已在 CLI 段覆盖；在 Host 测试段补充 public `list_sessions`、空库边界与 slot row 解码 fail-closed 覆盖事实。

## README 约束检查

- 已阅读 `dayu/host/README.md` Agent 更新约束；本次只写当前 `dayu.host` 已实现接口、公共契约与 read truth 边界。
- 已阅读 `dayu/README.md` Agent 更新约束；本次只做跨包 Host public contract 总览同步，没有扩写内部机制或 CLI 使用说明。
- 已阅读 `tests/README.md` 更新边界；本次修改对应已存在测试事实，不增加测试命令清单或未来计划。
- 已核对 `docs/engine/design.md`；当前 Engine run-scoped 边界与 S5/S6 已实现事实不冲突，因此未修改该文件。

## 验证结果

- `git diff --check`：通过。
- 未运行 pytest / pyright：本 slice 仅修改文档，未改生产代码或测试代码。

## 残余风险

- 文档同步只覆盖 S6 指定的 Host public contract 和测试 README 范围；未进行全仓文档语义重写。
