# Code Review Artifact: Slice S1 — `upload_filings_from` CLI 错误投影修复

- gate: code review / fix / re-review（deepreview 方法论，DS + MiMo 两路并行 + 总控裁决）
- work unit: `upload_filings_from --output` workspace 外目标 CLI 错误投影修复
- 审查对象: `git diff dayu/cli/commands/fins.py tests/cli/test_upload_filings_from_command.py`（Slice S1 实现 + fix 后最终状态）
- 日期: 2026-09-18

## 派发记录

| 环节 | runtime | provider | instance | exit | verdict |
| --- | --- | --- | --- | --- | --- |
| code review | claude-agent-run | ds | code-review-ds-01 | 0 | approve-with-findings（2 minor） |
| code review | claude-agent-run | mimo | code-review-mimo-01 | 0 | approve（1 minor） |
| fix | claude-agent-run | glm | fix-glm-01 | 0 | done |
| re-review | claude-agent-run | ds | re-review-ds-01 | 0 | pass（F1/F2 已修复，含敏感性探针实证） |
| re-review | claude-agent-run | mimo | re-review-mimo-01 | 0 | pass（F1/F2 已修复） |

## Finding 裁决与最终状态

| id | 来源 | severity | 内容 | 裁决 | 最终状态 |
| --- | --- | --- | --- | --- | --- |
| F1 | ds | minor | tmp 残留断言硬编码 publisher 私有 temp 命名，改命名时静默假阴性 | accepted | **已修复**（改 workspace 条目集合快照 `after == before`，owner 级零副作用不变量；DS re-review 用注入残留探针实证断言有效且无假阳） |
| F2 | ds | minor | `not target.is_file()` 对变体 1/2 过弱 | accepted | **已修复**（helper 参数化 `expect_target_absent`：变体 1/2 `not target.exists()`，变体 3 `not target.is_file()`） |
| MiMo-F1 | mimo | minor | 残留断言当前恒真，建议注释注明 | 部分采纳 | **证据失效**（采纳 F1 快照方案后原 glob 断言移除，该 finding 对象不再存在；保留无副作用断言的意图由快照断言更强地承载） |
| DS-OQ1 | ds | open question | Windows 下 `monkeypatch os.name` 影响 pathlib 分派 | deferred-with-owner | 记录（既有惯例 :149/:248/:297/:348 同模式） |
| DS-OQ2 | ds | open question | D2 不加 `_LOGGER.exception` 丢 operator traceback | rejected-with-reason | 9 个 raise site 消息文本一一对应，stderr 投影已承载定位信息；维持 plan review 裁决 |
| DS-OQ3 | ds | open question | docstring 未列 `render_upload_script` ValueError | deferred-with-owner | 既有缺口、CLI 路径不可达（plan §9） |
| DS-N1 | ds re-review | minor | 同文件 :620 既有测试同类 temp 命名 glob（pre-existing，不在本 diff） | deferred-with-owner | 记录；任务 prompt 禁止顺手重构范围外模块，DS 亦建议不在本 slice 追加 |

## 验收标准逐项核对（两路独立确认 covered，总控复跑复核）

1. 原失败测试通过 ✓（21 passed, 2 skipped）；
2. workspace 外 output 无文件/无副作用 ✓（:737 `outside.sh` 不存在断言 + 快照不变量）；
3. 合法 workspace 内 output 行为不变 ✓（既有 :140/:240 用例通过；生产仅新增 except 分支）；
4. symlink/父目录不存在/目标类型非法均有具体提示 ✓（三变体测试）；
5. generic 未知异常通用提示且不泄漏 ✓（新增 generic 用例）；
6. 回归集合无新增失败 ✓（266 passed, 2 skipped）；
7. pyright 无新增/扩散 ✓（0 errors；DS 另跑 ruff 通过）。

## 环境干扰排查记录

- DS code review 期间观测到一次"表观修复失效"与一次 E2E 假失败，定位为并发 agent 干扰与既有共享目录 E2E（`workspace/tmp/r11-posix-real`）并发问题，非本改动；后续复跑全部干净。
- DS re-review 报告 `tests/cli/test_init_workspace.py` 4 个失败；总控 stash 对照验证：基线代码同样 4 failed，确认 pre-existing、与本改动无关（import 链不触碰改动文件）。不属本 work unit，记录为 residual risk（tracked by 本 artifact；建议另立调查）。

## Residual Risks（全部已分类）

1. 快照断言只比路径集合不比内容 — 当前三变体均在 publish 前失败，充分；未来新增"失败前改写已有文件"路径需扩展（assigned to later work unit）。
2. 快照不覆盖 workspace root 自身创建（`--base` mkdir 既有 bootstrap 行为，plan §3 已精确化）— 记录。
3. symlink 变体 Windows 受限环境风险 — assigned to later work unit（仓库惯例）。
4. `test_init_workspace.py` 4 个 pre-existing 失败 — 与本 work unit 无关，requiring new issue or explicit user decision。
5. 同文件 :620 既有 temp 命名 glob — deferred-with-owner（DS-N1）。
6. plan §9 既有项：`str(exc)` 无界投影、`--base` symlink 不可达、ValueError/OSError 走 generic 分支 — deferred-with-owner / assigned to later work unit。

## Gate 结论

code review gate **pass**：accepted findings 全部已修复并经两路 re-review 确认；无 blocking open question；residual risks 全部已分类。下一 gate：aggregate deepreview。
