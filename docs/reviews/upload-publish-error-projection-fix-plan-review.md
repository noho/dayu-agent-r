# Plan Review Artifact: `upload_filings_from` CLI 错误投影修复

- gate: plan review（planreview 方法论，两路并行独立审查 + 总控裁决）
- work unit: `upload_filings_from --output` workspace 外目标 CLI 错误投影修复
- 审查对象: `docs/plans/upload-publish-error-projection-fix.md`（修订后版本已回写全部 accepted findings）
- 日期: 2026-09-18

## 派发记录

| runtime | provider | instance | exit | subtype/is_error | artifact |
| --- | --- | --- | --- | --- | --- |
| claude-agent-run | ds | plan-review-ds-03 | 0 | success / false | `$TMPDIR/sub-agents.Gr8IuF/plan-review-ds-03.json`（result 8766 字符） |
| claude-agent-run | mimo | plan-review-mimo-03 | 0 | success / false | `$TMPDIR/sub-agents.Gr8IuF/plan-review-mimo-03.json`（result 2887 字符） |

派发故障记录：plan-review-ds-01/mimo-01（`--prompt-file`）与 plan-review-ds-02/mimo-02（`--prompt` 内联 + `-- --allowedTools` 透传）四轮均失败，stderr 为 claude CLI `Input must be provided ... when using --print`；经两次探针隔离定位为 runner `--` 透传缺陷（多行 prompt + `--` 后缀时 prompt 丢失），第三次去掉 `--` 后缀成功。两次失败原因明确，属配置错误类重试，未超协议上限。

两路 verdict 均为 `approve-with-findings`，无 blocking，无 blocking open question。

## Finding 裁决

| id | 来源 | severity | 内容摘要 | 裁决 | fix/re-review 状态 |
| --- | --- | --- | --- | --- | --- |
| DS-F1 | ds | minor | 验收标准 2 无可执行断言；plan §3.3 副作用表述不精确（`--base` mkdir 在 containment 前） | accepted | 已修复（plan §3.3 精确化；D4 新增 target 未创建 + 无 tmp 残留断言；既有用例补 `outside.sh` 不存在断言） |
| DS-F2 | ds | minor | 验收标准 4 三类变体只覆盖 symlink；success signal 3 措辞过宽 | accepted | 已修复（D4 扩展为三变体：internal symlink / 父目录不存在 / 目标类型非法；success signal 3 对齐） |
| DS-F3 / MiMo-F1 | ds + mimo（独立同源） | minor | D2 选择性引用，遗漏 `FinsUploadPrevalidationError` 反例（fins.py:203-206） | accepted | 已修复（D2 改为可判定规则：消息自足的用户输入类 contract 错误不记 traceback，运营型/遮蔽型失败才记；实现决策不变）。DS 折中建议（加 `_LOGGER.error` 无 traceback 行）驳回：消息已完整投影 stderr，再加日志行是无效语义，违反最小化 |
| DS-F4 | ds | minor | §7 未裁决 tests/README.md 触发项 | accepted | 已修复（§7 补 tests/README 裁决：既有文件既有层级，无需更新） |
| DS-F5 | ds | minor | `_run_upload_filings_from` docstring `:raises` 缺 `UploadScriptPublishError`，违反 docstring 硬约束 | accepted | 已修复（新增 D5，exact allowed changes 补 docstring 一行） |
| DS-OQ1 | ds | open question | `--base` 为 symlink 时 publisher root-symlink 检查经 CLI 不可达（既有行为） | deferred-with-owner | 已记录 plan §9 residual risk，由用户裁决是否另立 work unit |
| DS-OQ2 | ds | open question | `str(exc)` 无长度上限投影（与既有 `CliFinsUsageError` 同惯例） | rejected-as-finding / deferred-with-owner | 非本修复引入的新问题；已记录 plan §9 residual risk |
| DS-OQ3 | ds | open question | generic 未知异常在 `upload_filings_from` 路径无专属断言 | accepted | 已修复（D4 新增 `test_upload_filings_from_unknown_failure_uses_generic_message`，断言通用文案 + 不泄漏内部消息，对应验收标准 5） |

## Assumptions 交叉验证（两路全部 holds，总控抽查复核）

- typed 分支不会被更前分支截获：前置分支均为 ValueError 派生，`FinsUploadPrevalidationError` 是兄弟类非父类（MRO 无交集）——总控复核 `upload_script.py:37` 与 fins.py:183-218 属实。
- 消息无泄漏：upload_script.py 全部 9 处 raise 消息体仅含用户输入派生路径或固定文本——总控复核 :71/:293/:297/:316/:318/:322/:327/:331/:334 属实。
- `publish_upload_script` CLI 唯一消费点为 fins.py:366，无第二投影入口——总控 grep 复核属实。
- D4 internal symlink 变体真实命中 `_has_internal_symlink` 分支（非测试假象）：DS 验证了 pytest tmp_path resolve 行为（`/private/var/...` 同源），总控复核 `_resolve_publish_target` 检查顺序（:315 → :317）属实。
- 基线 `1 failed, 263 passed, 2 skipped` 与 HEAD ed7057cf：DS 实跑复核一致；pyright 受影响文件基线 0 errors。

## Residual Risks（全部已分类）

1. symlink 用例 Windows 受限环境风险 — assigned to later work unit（沿用仓库惯例）。
2. `render_upload_script` ValueError / publisher OSError 走 generic 分支 — assigned to later work unit（既有行为，CLI 路径 ValueError 不可达）。
3. `--base` symlink 使 root-symlink 检查不可达 — deferred-with-owner（DS-OQ1）。
4. `str(exc)` 无界投影 — deferred-with-owner（DS-OQ2，既有惯例）。

## Gate 结论

plan review **pass**：无 blocking finding；5+1 项 minor findings 全部 accepted 并已回写 plan（fix 完成，本文档即 re-review 记录）；open questions 均已裁决或 deferred 分类；无 unclassified residual risk。下一 gate：implementation（Slice S1，GLM 实现）。
