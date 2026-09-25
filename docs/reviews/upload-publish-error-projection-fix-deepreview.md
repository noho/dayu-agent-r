# Aggregate Deepreview Artifact: `upload_filings_from` CLI 错误投影修复

- gate: aggregate deepreview / fix / re-review（DS + MiMo 两路并行 + 总控裁决）
- work unit: `upload_filings_from --output` workspace 外目标 CLI 错误投影修复
- 审查对象: 最终代码状态（git diff）+ 全部 gate artifacts 一致性 + 验收标准 1-7 证据链 + residual risk 账目闭合
- 日期: 2026-09-18

## 派发记录

| runtime | provider | instance | exit | verdict |
| --- | --- | --- | --- | --- |
| claude-agent-run | ds | deepreview-ds-01 | 0 | pass-with-findings（5 minor） |
| claude-agent-run | mimo | deepreview-mimo-01 | 0 | pass（0 findings） |

## Finding 裁决与最终状态

| id | severity | 内容 | 裁决 | 最终状态 |
| --- | --- | --- | --- | --- |
| DS-A1 | minor | `monkeypatch os.name="posix"` 全局可变状态跨模块泄漏（Windows 运行时隐患） | deferred-with-owner | 记录；同文件 4 处既有惯例（:149/:248/:297/:348），DS 建议后续 Windows work unit 改用 `monkeypatch.setattr(fins_command, "current_upload_script_platform", ...)` owner 边界注入 |
| DS-A2 | minor | 验收标准 2 的 workspace 外副作用证据仅单点断言 | rejected-with-reason | 证据链已闭合：`:737` 单点断言 + 生产结构论证（`tempfile.mkstemp` 在 containment 之后，upload_script.py:125-130）+ publisher owner 层 tmp 清理断言（:620）+ workspace 内快照不变量；workspace 外快照属防御未来重构的强化，超出验收标准 |
| DS-A3 | minor | 既有 E2E 共享目录 `workspace/tmp/r11-posix-real` 并发/残留假失败（实测复现一次，基线对照确认 pre-existing） | accepted as residual risk | assigned to later work unit（建议后续改 `tmp_path` 或进程级 lock）；本 slice 不扩散范围 |
| DS-A4 | minor | implementation artifact 的 D4a 描述滞后于 code review fix 后代码 | accepted | **已修复**（总控回写状态行，指向 code review artifact 与 git diff 为最终状态） |
| DS-A5 | minor | residual risk 三处口径不一（implementation 清单缺 plan §9 第 2 项） | accepted | **已修复**（总控回写补齐第 5 项；final closeout 以 plan §9 五条为基线统一口径） |

## Open Questions 裁决

1. `test_init_workspace.py` 4 个 pre-existing 失败未独立复核 — **已关闭**：总控 stash 对照验证基线同样 4 failed（见 code review artifact 环境干扰排查）。
2. GLM「venv 解释器差异」理由链存疑 — **已裁决**：实测失败形态为共享目录残留（DS-A3）；已在 implementation artifact 回写修正表述。
3. stderr 中英混合消息（owner 层 family 约定，本次首次经 CLI 暴露其中 4 条）— deferred-with-owner（是否统一中文属 upload_script owner 决策，不影响本次正确性）。
4. `UploadScriptPublishError` 分支无日志，运维以日志为准据会看不到该类事件 — deferred-with-owner（D2 两轮 review 维持；如运维需要可加无 traceback 日志行，属策略选择非缺陷）。

## 验收标准终态（两路独立确认 covered；DS 另以真实 CLI 逐一复核四变体消息与退出码）

1. 原失败测试通过 ✓；2. workspace 外 output 无副作用 ✓；3. 合法 output 行为不变 ✓；4. 三类 typed 变体具体提示 ✓（真实 CLI 复核消息文本）；5. generic 不泄漏 ✓（测试确走 generic 分支）；6. 回归集合 266 passed, 2 skipped ✓（与基线数字吻合）；7. pyright 0 errors ✓（ruff 亦通过）。

## 一致性检查（8 项全部 consistent；唯一 inconsistent 项 residual-risk 账目已由 A5 fix 关闭）

语义 owner 边界、typed-before-generic MRO、D2 无日志决策、验收证据链数字、README 不更新决策（README.md:428/:451-453/:591 既有承诺，tests/README.md:357 既有层级）、artifact 放置目录、无 commit/push（git log 停在 ed7057cf）均一致。

## Residual Risks 统一账（以 plan §9 五条为基线 + 各 gate 新增，全部已分类）

| # | 风险 | 分类 |
| --- | --- | --- |
| 1 | symlink 变体 Windows 受限环境 | assigned to later work unit |
| 2 | `render_upload_script` ValueError（CLI 不可达）/ publisher OSError 走 generic 分支 | assigned to later work unit |
| 3 | `--base` symlink 使 root-symlink 检查经 CLI 不可达 | deferred-with-owner |
| 4 | `str(exc)` 无界投影（含 home 绝对路径；无 secret/storage locator/内部异常泄漏） | deferred-with-owner |
| 5 | 快照断言只比路径集合不比内容（当前变体充分） | assigned to later work unit |
| 6 | 既有 E2E 共享目录假失败（pre-existing） | assigned to later work unit |
| 7 | `test_init_workspace.py` 4 个 pre-existing 失败 | requiring new issue or explicit user decision |
| 8 | 同文件 :620 既有 temp 命名 glob（pre-existing，DS-N1） | deferred-with-owner |
| 9 | `os.name` monkeypatch 全局泄漏（既有惯例，DS-A1） | deferred-with-owner |
| 10 | stderr 中英混合消息 / typed 分支无日志（策略选择） | deferred-with-owner |

## Gate 结论

aggregate deepreview gate **pass**：无 blocking/major finding；2 项 accepted minor（A4/A5）已由总控文档回写修复，无需代码变更、无需 re-review 代码（re-review 对象为非代码 artifact，本记录即回写证据）；3 项 minor 转为分类 residual risk；无 unclassified residual risk。下一 gate：final closeout（draft PR gate 链按任务 prompt 禁止 commit/push 整体跳过）。
