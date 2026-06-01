# WU-DUR-01-02 Slice 4 Review - DS

## Scope

- **Gate**: Slice 4 code review (AgentDS)
- **Review target**: 当前未提交 diff（仅 tests/README.md）+ Slice 4 implementation artifact
- **Approved plan**: `docs/host/wu-dur-01-02-durable-bootstrap-concurrency-plan.md`
- **Implementation artifact**: `docs/reviews/wu-dur-01-02-implementation-slice4-codex-20260601.md`
- **Branch**: `feat/wu-dur-bootstrap-concurrency`
- **Base**: committed HEAD (`2fe6c22`)
- **Review lens**:
  - tests/README.md 更新是否属于测试手册职责范围，命令是否准确且不过度
  - Slice 4 artifact 是否准确记录验证结果、README decision、residual risk，且没有错误声称用户禁止 aggregate deepreview
  - 是否漏跑 approved plan 指定验证；是否如实说明未运行完整 tests/host 或全仓测试
  - 不重新审查 Slices 1-3 implementation correctness

## Conclusion

**pass-with-findings**（一条低严重度 finding，不阻塞 slice acceptance）

## Findings

### DS-C4-未修复-低-tests/README.md 窄命令中丢失 test_event_log_store.py

- **入口/函数**: `tests/README.md` "常用命令" section, 旧行 41 → 新行 41-44
- **文件(行号)**: `tests/README.md:41-44`（修改后）
- **输入场景**: 用户需要快速运行 Host durable EventLog 相关测试
- **实际分支**: Slice 4 diff 将旧行一条 durable 窄命令替换为四条与 plan 验证命令对齐的新命令
- **预期行为**: 测试手册应保留对现有测试文件的窄范围运行方式覆盖；`test_event_log_store.py` 是真实存在的 Host durable 测试文件（22646 bytes，最后修改 5 月 18 日），应有对应的窄命令入口
- **实际行为**: 旧命令包含 `test_event_log_store.py`；新四条命令均不包含该文件；全文搜索确认 `test_event_log_store` 不再出现在 tests/README.md 任何位置。用户需自行拼接命令或通过 `pytest tests/host -q` 全量运行
- **直接证据**:
  - `git diff tests/README.md` 显示旧行 `pytest tests/host/test_durable_schema.py tests/host/test_durable_transaction.py tests/host/test_event_log_store.py tests/host/test_event_log_multiprocess.py ...` 被替换
  - `grep test_event_log_store tests/README.md` 返回 No matches
  - `ls -la tests/host/test_event_log_store.py` 确认文件存在
- **影响**: 局部行为偏差 — 测试手册的窄命令覆盖出现了一个可避免的缺口；不影响测试执行正确性
- **建议改法和验证点**: 可在新命令组中追加一条 `pytest tests/host/test_event_log_store.py -q` 或将 `test_event_log_store.py` 合并到现有四条命令中的适当位置（如与 `test_event_log_multiprocess.py` 同组）；变更后确认 grep 命中
- **修复风险（低）**: 仅涉及 README 文本，不触及代码或测试逻辑
- **严重程度（低）**:
- **Controller decision status**: pending

## Verified Claims（无问题项）

以下 Slice 4 artifact 声明经逐条验证，均准确：

1. **dayu/host/README.md 内容准确、未修改**: artifact 声称 README 已说明 durable store / WAL / snapshot / checkpoint 语义。验证确认 `dayu/host/README.md:291` 包含完整原文：`"schema 按当前 fresh version 起库，版本不匹配时要求重建 durable DB；SQLite 连接启用 WAL 与 auto-checkpoint；transaction runner 的 read transaction 使用 SQLite snapshot 语义，新的短读事务读取最新 committed truth；内部 WAL checkpoint primitive 只服务显式 diagnostic / test entry，不属于 public maintenance API，也不作为 EventLog 或状态正确性的前置条件"`。该行在 Slice 4 之前已提交，artifact 的"未修改"决定符合 plan 要求（plan: "Update only stable current facts ... if existing README is inaccurate" — README 无 inaccuracy）。

2. **验证命令全部通过**: artifact 列出 4 条 pytest 命令（28 + 22 + 81 + 27 passed）和 pyright（0 errors, 0 warnings），与 plan 第 374-378 行指定命令完全对齐。

3. **未修改 forbidden files**: git diff 确认仅 `tests/README.md` 有未提交修改；未触及 root README.md、dayu/README.md、dayu/engine/README.md、dayu/fins/README.md、dayu/config/README.md。

4. **aggregate deepreview 状态如实记录**: artifact 写明"Slice 4 handoff 未进入 aggregate deepreview；aggregate deepreview 仍是 Slice 4 review / acceptance 之后的下一个 controller gate。"未声称用户禁止 aggregate deepreview。

5. **residual risk 如实说明**: artifact 明确写了三点 — 未运行完整 tests/host、aggregate deepreview 待后续 gate、未审查 Slices 1-3 实现。与 plan Review Gates 第 412 行一致。

6. **README 职责范围合规**: tests/README.md 的修改（收窄命令重组）属于"运行方式"更新，在测试手册固定职责范围内。新增的四条命令与 plan 验证命令精确对应，命令格式与周围既有命令一致，无不必要添加。

## Open Questions / Residual Risk

- **Non-blocking**: tests/README.md 中 `test_event_log_store.py` 在窄命令中的缺失是否需要修复（见 DS-C4-未修复-低）。
- **Non-blocking**: plan 第 412 行要求的 aggregate deepreview（`$deepreview --base main`）尚未执行；这是 Slice 4 acceptance 后的下一个 controller gate，不在本次 DS review scope 内。

## Stop Status

review-complete。
