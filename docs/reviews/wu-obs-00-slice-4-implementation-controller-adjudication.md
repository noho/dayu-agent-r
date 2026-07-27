# WU-OBS-00 Slice 4 Implementation Controller Adjudication

status=complete

work_unit=WU-OBS-00

slice=S4

gate=implementation

decision=pass-to-code-review

implementation_base=179520e08e8c6b59cdf49aefc59bc4463c9698c2

implementation_artifact=docs/reviews/wu-obs-00-slice-4-implementation-codex.md

## 动机与 owner 裁决

Slice 4 的动机成立。Slice 3 已提供 Host public analyzer 与同一 structured report 的
JSON/Markdown renderer，但 accepted base 不存在 operator command、Service input discovery
或原子 publication owner。正确分层为：

```text
CLI parser/runner
  -> Service input discovery + publication truth
  -> Host public analyzer/renderers
```

本轮实现保持该边界：Host 继续唯一拥有 analysis/report 语义；Service 唯一拥有四种路径
发现、输出文件名、临时文件、replace 顺序、partial publication 与 cleanup secondary
failure；CLI 只映射 typed Service result/error 到退出码和用户文本。

## Controller 独立核对

- implementation changed files 只包括 accepted plan 的四个 production 文件、四个 test
  文件、五份职责命中的 README 与 implementation artifact。
- `dayu/host/tool_trace_analysis.py` 无需修改，直接复用 Slice 3 public API。
- 相对 accepted Slice 3 `179520e0`，以下冻结 owner 均无 diff：
  - `dayu/host/tool_trace_analysis_contracts.py`
  - `dayu/host/tool_trace_analysis_input.py`
  - `dayu/host/tool_trace_analysis_rules.py`
  - `dayu/host/tool_trace_events.py`
  - `dayu/host/tool_trace.py`
  - `dayu/host/durable/tool_trace.py`
- Controller 预先持有的 `docs/host/issues-implementation-control.md` dirty change 未被
  AgentCodex 修改，不计入 implementation allowlist。
- `git diff --check` 通过。
- implementation artifact 明确 `status=complete`、`stop condition=not triggered`，并
  停在 code review 入口。

## 验证门槛

- focused：`93 passed`
- full affected matrix：`232 passed`
- full pyright：`0 errors, 0 warnings, 0 informations`
- changed production branch coverage：`91%~100%`；完整 analyzer matrix 单文件
  branch coverage：`81%~100%`
- README 已在修改前逐份读取各自更新约束，并只写入职责命中的当前能力。

用户定义的真实 CLI 硬停止条件已通过：

- 精确删除已授权的 `workspace/.dayu`，未运行 init；`workspace/config` 原本不存在且未被
  创建或删除；
- 真实 `dayu-cli prompt` 经 Host 调用真实工具并生成 current-schema Tool Trace：
  hot/cold/payload descriptor=`9/9/7`，SQLite schema object count=`24`；
- 未使用 fixture、test helper、直接写 SQLite/JSONL、兼容读取或替代 producer；
- directory mode 与 cold-file mode 均经真实 `python -m dayu.cli tool_trace analyze`
  发布非空 JSON/Markdown；
- 两种格式的 finding/limitation/vendor counts 同源；directory mode 无虚假 digest
  mismatch；cold-file mode 明确报告 hot/payload limitation；
- analyzer 读取前后 SQLite/cold/artifact hashes、row counts 与 schema 完全不变。

## Review 必查项

双路 independent review 必须重点挑战：

1. 四种 input mode 的唯一发现、歧义与 unsupported path 是否 fail closed；
2. Service 是否只调用 Host public API，CLI 是否完全不 import durable/internal owner；
3. JSON/Markdown 是否来自同一 report，CLI/Service 是否重复计算 finding/count 语义；
4. 同目录 temp-write、严格 UTF-8、固定 JSON→Markdown replace 顺序与旧文件保持语义；
5. 第一次/第二次 replace 失败时 `published_paths`、`failed_path` 是否稳定且不被 cleanup
   secondary failure 改写；
6. cleanup failure 是否保留 primary failure，是否存在 temp path 泄漏或错误的
   `temporary_paths_cleaned`；
7. output directory/create/write/analysis error 的退出码与旧报告保留行为；
8. parser/help/unknown action/subprocess/module entry、import boundary 与 README 是否和代码
   一致；
9. broad exception boundary、symlink/lexical path、TOCTOU、overcoupling、semantic
   ownership drift 与 owner-level test gap。

blocker=none

next_entry_point=dual independent code review; never self-advance
