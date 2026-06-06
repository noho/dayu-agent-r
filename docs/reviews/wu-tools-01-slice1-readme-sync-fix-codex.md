# WU-TOOLS-01 Slice 1 README Sync Fix

- Gate: fix
- Work unit: WU-TOOLS-01
- Slice: S1 shared document foundations
- Agent: AgentCodex
- Scope: 仅同步 `tests/README.md` 中与新增 `tests/documents/` 测试层相关的当前事实。

## 动机判断

问题成立。`tests/documents/` 已存在当前测试层，包含 `test_import_boundary.py` 与 `test_processors.py`；`tests/README.md` 自身声明新增测试层级后应同步更新，因此缺少 `tests/documents/` 说明属于 README 同步遗漏。

## 修改文件

- `tests/README.md`
- `docs/reviews/wu-tools-01-slice1-readme-sync-fix-codex.md`

## README 同步内容

- 将常用全量测试命令从 `tests/contracts tests/host tests/runtime tests/service tests/engine` 更新为包含 `tests/documents`。
- 在 focused commands 中新增 `pytest tests/documents -q`。
- 在当前测试分层中新增 `tests/documents/` 小节，记录两类当前事实：
  - import boundary 测试阻止 `dayu.documents` 反向依赖 Engine、Host、Service、UI、Fins 或具体工具实现，并确认 Docling runtime 与 processors 子包被扫描覆盖。
  - processor fixture 测试覆盖 Markdown、HTML 与 Docling JSON 处理器的章节提取、表格读取与搜索片段输出。

## 验证

- 已运行：`git diff --check`
- 结果：通过。
- 未运行测试：本轮只改 README 与 fix artifact，不涉及代码行为或测试内容；按用户给定验证要求未额外运行 `pytest tests/documents -q`。

## 剩余风险与未覆盖项

- 无未分类剩余风险。
- 未覆盖项：未运行测试；原因见验证部分，当前变更不改变测试或生产代码行为。

## 完成状态

已完成本轮 fix gate 要求，未提交、未推送、未打开 PR，未进入 review / re-review gate。
