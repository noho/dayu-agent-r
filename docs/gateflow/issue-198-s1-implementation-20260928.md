# issue #198 S1 implementation

- 唯一 label：`issue198-s1-implement-sol-20260928-01`
- Gate：`implementation`；下一 gate：`code review`
- 分支：`codex/upload-material-oracle`；实施前后 HEAD：`8d8d494fbbce0052372fb1b42097c9f7222cfa28`（accepted plan commit）。未 stage、commit、push 或修改 PR。
- 范围：只实现 S1 的封闭预检原因公共投影；S2 日志、CLI 外层 catch、runtime helper、storage inspector 与 upload material oracle 均未修改。

## 动机、owner 与实施

直接代码证据：storage `SourceIntegrityPreflightReason` 已有四个封闭值，原有未提交候选实现却把 `exc.reason.value` 放进 `FinsPublicFailure.reason_code: str | None`，使公共字段接收任意字符串。S1 动机成立；其严重性是公共失败契约可漂移及消费者可能误读，不能从事故文字推断其它下载错误也属于同一预检原因。

- `dayu/fins/direct_events.py` 定义独立四值 `FinsDownloadFailureReason`，将 `FinsPublicFailure.reason_code` 限定为该 enum 或 `None`，只允许 storage 且无 transport 分类携带原因；JSON 输出 `.value` 或 `null`。共享公共契约不导入 storage。
- `dayu/fins/ingestion_runtime.py` 在唯一异常投影点显式映射 storage 四值到公共四值；direct `error_kind` 与公共 `kind` 均为 storage。保留统一安全消息，以及“检查并修复工作区来源状态后重试；重复下载不会自行修复”的恢复提示。provider、OSError、unknown 均无预检原因。
- `dayu/cli/output.py` 只打印公共 enum 的 `.value`，不重新判断来源原因。
- owner 测试断言映射键全集、每对 `.value` 相等、四种结果与提示、非法字符串和非 storage 原因拒绝、其它异常原因为空及公开文本不带秘密；CLI 测试固定 JSON/终端相同值；Service wait 测试固定序列化 `unsafe_publication`，并断言 hint 来自公共 `retry_hint`。`tests/service/test_fins_direct.py` 作为现有 direct 消费者回归运行，未改其代码。

## 工作树归属与 README

实施前 `git status --short` 已有 S1 候选 hunk、点号元数据 storage/test/README hunk 与 upload material oracle 文档；S1 artifact 事前确认不存在。逐项检查了允许文件的实施前 diff 与内容，实施后 HEAD 不变，相关未提交内容仍在，未见归属外 hunk 的并发变化。实施后允许路径相对 HEAD 的 `git diff --binary` 摘要为 9 个文件、164 行新增、12 行删除；该摘要**包含实施前已有的 S1 候选与另一 work unit 的 README 句子**，不是本次净增量。`tests/service/test_fins_direct.py` 未修改；点号元数据 storage/test 和 oracle 文件未修改。

- 根 `README.md` 遵守用户手册约束，只将已有混合行拆为两句：保留点号元数据句的既有事实，#198 句以“下载显示 `classification="storage"`、`reason="unsafe_publication"` 时”独立起句并给出修复后重试建议。两句可按 hunk 单独裁决。
- `dayu/fins/README.md` 的 download public failure 句改为明确四值显式映射与公共枚举投影；另一 work unit 的 inspector 句未改。
- `tests/README.md` 的下载终态测试句按实际覆盖更新；另一 work unit 的仓储完整性句未改。
- 分层关系未变，不触发 `dayu/README.md`。S1 无日志定位行为变化，不加入 `--log-file` 文案。

## 验证

- `source .venv/bin/activate && python -m pytest tests/fins/test_fins_ingestion_runtime.py tests/cli/test_output.py tests/service/test_fins_wait_adapter.py tests/service/test_fins_direct.py -q`：退出 0，`450 passed, 3 warnings in 9.37s`。三条 warning 均来自 `edgar` 依赖的 deprecated import。
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`：退出 0，`0 errors, 0 warnings, 0 informations`。另有 pyright 新版本提示，不影响检查结果。
- `git diff --check`：退出 0；`reason_code` 使用点搜索显示 Fins 单一投影点、公共 JSON 和 CLI `.value`，Service wait 消费者未重算原因。搜索若无其它匹配视为正常。
- 首次并行读取工具调用出现 JavaScript 语法错误，未执行内部 shell 命令；修正调用后所有必读输入成功读取。后续 shell 命令均退出 0。

## 残余风险与交接

S1 未做隔离真实 CLI 验证，真实来源工作区行为仍待整个 issue 的后续验证。未知 download 异常的安全 operator 日志属于 S2，当前仍有原始日志风险。其它 storage sibling 异常、投影二次失败、无来源文档 hint 与非 download 诊断沿用 accepted plan 的后续 work unit 边界。未运行单文件覆盖率量化；本次以四值 owner 分支和受影响测试通过为 S1 验证证据，不把覆盖率目标宣称为已测得。

下一 gate：`code review`。本轮按派发要求在 S1 implementation artifact 完成后停止。
