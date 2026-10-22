# D1 Finding 1：skipped 原因输入校验修复

作者修复与验证已完成；下一入口为总控裁决并安排双路受影响面复审。本报告不代表独立 review 通过。真正 blocker：无。

依据：[DS Finding 1](../reviews/code-review-20261023-004540.md#1-未修复-低-skipped-原因对未被唯一投影严格校验分类与公开原因可能漂移)及 [D1 总控裁决](tsm-6k-rejection-20261023-d1.md#完整双路审核裁决)。当前内置生产者不会生成缺因或冲突行；这是已确认的 owner 输入边界缺口，不是历史事故，也不改变 6-K 保留政策。

## 修复边界

仅在 `sec_download_disposition.project_sec_filing_disposition` 已严格读取 skipped 两个可选原因后，增加：

- 两者均为缺失/null 时抛 ValueError。
- 两者均有文本且去首尾空白后不同，抛 ValueError。

原非法值校验顺序保留；一个合法原因即可，双同值合法。已有 `6k_filtered` 判定、显式 rejected、downloaded、failed 规则均不变。没有下游特判、默认原因或新框架；诊断、workflow、typed 投影、XBRL、日志、原原因字段、locator、存储和筛选政策均未改。

owner 中文 docstring 明确原因对要求；删除“无原因/null skipped 仍有效”的测试输入，数量分组夹具改用真实合法的 `already_downloaded_complete` 原因对。新增同一完整行在 owner、warning、typed 投影的联验：四种缺失/null 组合、两方向冲突及带空白冲突均抛相同 owner 错误，不能返回有效计数或矛盾 public 行；单 skip_reason/单 reason_code 的拒绝及完整缓存、双同值、规范化同值及一个 null 加另一个合法原因均保持正确分类/原因，输入不变。

Fins README 补充稳定输入契约；tests README 补充联验边界。根 README 的用户操作/排障及整体分层未变，无需更新。相对上轮冻结十文件快照，实际仅四个文件变化：owner、owner 测试、Fins README、tests README；`F/owner-fix.patch` 保存精确增量，`artifact-proof` 对变化集合做了等值断言。

## 本轮证据与版本

本轮新证据根目录 `F = workspace/tmp/tsm-6k-20261022/d1/fix-owner/`。旧 s1/controller/d1 既有证据保持只读，根实施报告仅补本报告链接。

分支仍为 `investigation/tsm-6k-20261022`，HEAD `26ed15b91fc3ee81d5c6cde4dbd0a4fa709d2536`，未提交。包声明保持 `0.1.6`，SEC 下载认证版本保持 `sec_pipeline_download_v1.3.0`。不能以未变化 HEAD 或旧 wheel 识别本次修后代码。

`F/source-snapshot/` 保存当前四生产模块、三测试文件、两个 README 与 pyproject 的真实副本；`F/source-manifest.json` 保存逐文件 SHA256，`F/source-changes.patch` 保存相对 HEAD 的完整组合差异：

| 身份 | SHA256 |
| --- | --- |
| 新 owner 文件 | `0e439ef2098d7c48d6667efaaa12c362e8a82c12cfdb0af53d0ed10e382e79e9` |
| 四生产模块聚合 | `bf0c9c53343c1acd4688526b8bb879e217ffe90022f6d4623b182d8e73677482` |
| 十文件快照聚合 | `e984dec5ea4080b1cea83d0efa321e976a18168893a6a1b907eb6245b9bf8b85` |
| 新 wheel | `069929799b54dfcbfcb9427102f06dd153f2311a56306e4aa26ef0f8d748bccc` |

四临时脚本采用隔离复制，未改写旧脚本：将 `run_logged.py/check_wheel.py/verify_offline.py/capture_state.py` 复制到 F，所有按 `__file__` 派生的输出因此落在 F；显式离线 output 和构建副本参数均指向 F。`capture_state` 的硬编码基线仍与真实 HEAD 相同，已实际断言；它读取的是 F 下的新 wheel manifest，不是旧 manifest。四脚本本身逐字节等于旧最终脚本。

`F/script-snapshot/` 另存四脚本独立真实副本、实际使用的 pyright 配置和 `manifest.json`，保存逐文件/hash/来源及检查结果；脚本聚合 SHA256 为 `2e9e1ab0f313b97f1315d71c7b656368e7b2edcb4a6a7d0056cd0c92f8c26e06`。

## 实际新验证

各命令均先 `source .venv/bin/activate`，使用 `.venv` Python 3.11.15；`F/commands/<标签>/command.json` 保存完整 argv/cwd/时间/实际退出，同目录 stdout/stderr 为完整输出。所有下列结果均为本轮新跑，未以旧通过结果替代。

| 标签 | 验证内容 | 实际结果 |
| --- | --- | --- |
| `owner-focused` | owner 及缺因/冲突/合法原因联验、三个信号、失败/取消/中止聚焦回归 | 退出0；61 passed |
| `affected-coverage` | owner、download、download stream、upload filing/material stream、earnings repair 六测试文件 | 退出0；345 passed，79.87秒，3条既有 edgartools 弃用告警 |
| `full-pyright` | `pyright --outputjson` | 退出0；841 files、0 errors/warnings |
| `scripts-pyright` | `pyright --project F/pyrightconfig.json --outputjson` | 退出0；显式分析4脚本、0 errors/warnings；未依赖全量默认排除 workspace |
| `offline` | F 中脚本 + 权威 `s1/pipeline-clean-requests` + fresh `F/offline` | 退出0；10/10请求消费，对账通过 |
| `package-entrypoints` | `python -m pytest tests/cli/test_public_package_entrypoints.py -q`，独立 `F/package-pytest` | 退出0；4 passed |
| `wheel-verification` | F 中脚本核对本轮 package 副本、新 wheel 与当前四生产文件 | 退出0；0.1.6、源码字节一致，不安装 |
| `source-snapshot` | 当前十文件副本、基线和新 wheel 源码摘要核对 | 退出0 |
| `artifact-proof` | 四脚本真实副本/hash、精确修复增量、当前十文件一致、raw十字段对比 | 退出0 |
| `diff-check` | `git diff --check` | 退出0 |

覆盖率在本次收集时直接使用 `--cov-config=F/coverage-strict.ini`，`exclude_lines` 为空；`F/.coverage`、`F/coverage.json`、`F/affected-pytest.xml` 及主回归输出均保留。四文件 excluded_lines 均为0：

| 文件 | 覆盖语句 | 无排除覆盖率 |
| --- | --- | --- |
| `sec_download_disposition.py` | 33/33 | 100% |
| `sec_download_diagnostics.py` | 59/60 | 98.33% |
| `sec_download_workflow.py` | 243/282 | 86.17% |
| `sec_pipeline.py` | 418/467 | 89.51% |

真实 Fs 三个成功信号在本轮新回归中仍成立：拒绝一份为有效0/rejected1/active0；完整缓存再次跳过为有效1/skipped1/active1；两有效加一拒绝为有效2/rejected1/active2，仍有低于3的 warning。原失败类别、拒绝前缀后取消、早期取消 builder、循环尾与 repair 后取消、完整性中止确认行守恒与 cause 均经过本轮回归。新缺因/冲突场景在到达这些消费者前即由统一 owner 拒绝。

## 严格离线与新 wheel

`F/offline/` 是本轮全新 base。只使用权威 `s1/pipeline-clean-requests`，按 method/URL/顺序及响应字节 SHA256 匹配，无网络 transport/缺项回退，10/10记录耗尽。`quantity-current-input.json`、`public.json`、`reconciliation.json`、`requests.json`、`exit.json`、stdout/stderr/dayu.log 保存当前真实输入和结果：

- 当前 raw 行仍为 `status=skipped`、两个原因均为 `6k_filtered`；季度 warning 有效0、低于3。
- public 的 discovered1/downloaded0/skipped0/rejected1/failed0，唯一文档原因 `6k_filtered`、locator null。
- 仓储 active0、registry1、artifact/registry 原因一致，原件 SHA256 `021c698879a544fc41f2f0064d478480308ef1b0e9e30049299f8210945aa4a2` 与捕获 GET 字节相同。
- `F/raw-row-comparison.json` 对本轮确认行与旧 `d1/offline-final` 保存行做完整对象等值断言，10字段全部一致；不只依赖 `raw_fields_preserved` 汇总标签。

新 wheel 保留在 `F/wheel/dayu_agent-0.1.6-py3-none-any.whl`。构建复用本轮 package 测试的隔离源码副本，实际 cwd 为 `F/package-pytest/test_wheel_excludes_placeholde0/source`；父目录保存 build.command.json/stdout/stderr。未在 checkout 构建、未安装。`F/wheel-verification.json` 证明当前及副本 pyproject、wheel 文件名/METADATA 均为0.1.6，当前四生产模块、隔离副本和新 wheel 的源码字节完全一致。

## 旧证据适用范围、风险与交接

旧调查的保存响应、既有 6-K 政策及历史 GET 不可恢复限制仍适用；未改动的三个消费者、失败/取消/存储/locator 与原字段契约仍可用于理解不变式。旧回归、旧覆盖率、旧 owner 快照和旧0.1.6 wheel 仅证明旧组合版本，不能替代这次新 owner 的证据；本次已全部重跑必要验证并提供新组合快照。

- `fixed in current slice`：Finding1 的 skipped 缺因/冲突输入边界。owner 为 SEC disposition；destination 为本次代码与同源测试，作者修复/验证完成，最终修复状态待总控裁决及双路受影响面复审。
- `assigned to later work unit`：总控已裁决的既有 XBRL raw 判断、workflow 流程控制宽松 status；owner 为 SEC diagnostics/workflow，destination 为以后实际触碰相关政策/分支的 work unit。本轮不扩大处理。
- 验收边界：当前合法生产者不生成本 finding 的非法行；不把测试反例描述为历史事故。离线仅证明保存响应下的当前行为，不复原历史 GET，也不宣称全仓/线上验证；剩余未覆盖行详见新 coverage JSON。
- `requiring new issue or explicit user decision`：live同步/安装及 merge；owner 为用户/总控，destination 为另行明确授权流程，不阻塞本轮修复交接。

未 stage/commit/push/PR/安装/merge、未发外部消息、未派子 Agent，未改总控裁决或原 review。下一入口仅由总控安排双路受影响面复审。
