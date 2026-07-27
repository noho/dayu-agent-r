# WU-OBS-00 Slice 1 Final Acceptance — Controller

## 裁决

- Work Unit：`WU-OBS-00`
- Gate：Slice 1 implementation final acceptance
- Decision：`pass`
- Result：`accepted-slice-ready`
- Blocking open questions：None

Slice 1 的 trusted input、只读读取与完整性边界已形成可验证闭环。实现、双路 review、
review fix、双路 re-review 和 current fresh workspace 的真实 CLI 验证均已通过，可以创建
Slice 1 保护提交并进入 Slice 2。

## 语义所有权核对

- committed EventLog 仍是事实真源；analyzer input loader 只读取 Tool Trace hot/cold projection
  与既有 artifact descriptor，不修改 EventLog、SQLite、cold JSONL 或 payload artifact。
- strict input contract 由 `dayu.host.tool_trace_analysis_input` 负责；schema/version、hot/cold
  source key、digest/ref、payload descriptor 解析错误均在 owner boundary 暴露为 typed
  diagnostic / limitation，不在下游规则或展示层补偿。
- analyzer contract 由 `dayu.host.tool_trace_analysis_contracts` 负责；后续 Slice 2/3 必须复用
  该唯一真源，不得从日志文本、时间戳、偶然顺序或 raw fields 重新推断。
- 未增加 Tool Trace producer/schema 字段，也未为旧 schema 增加兼容读取、fallback 或 loose
  parsing。

## Review 闭环

- implementation：
  `docs/reviews/wu-obs-00-slice-1-implementation-codex.md`
- initial reviews：
  `docs/reviews/code-review-20260724-124007.md`、
  `docs/reviews/code-review-20260724-123859.md`
- Controller adjudication：
  `docs/reviews/wu-obs-00-slice-1-implementation-review-controller-adjudication.md`
- review fix：
  `docs/reviews/wu-obs-00-slice-1-implementation-review-fix-codex.md`
- re-reviews：
  `docs/reviews/code-review-20260724-125106.md`、
  `docs/reviews/code-review-20260724-125418.md`
- pre-remediation re-review adjudication：
  `docs/reviews/wu-obs-00-slice-1-implementation-rereview-controller-adjudication.md`

两路 re-review 均为 `PASS`，没有新增 actionable finding。唯一接受的 review finding 是 package
export owner test allowlist 漏项；修复只修改 owner test，production contract 未被兼容分支污染。

## 真实 CLI 与 live read-only 验证

验证 artifact：
`docs/reviews/wu-obs-00-slice-1-live-workspace-remediation-codex.md`

用户明确授权删除的
`/Users/leo/workspace/dayu-agent-r/workspace/.dayu`
仅包含旧测试/验证数据；该目录已精确删除，未备份且不可恢复。未运行 `dayu-cli init`，未创建或
修改 `workspace/config`。

AgentCodex 先依据 `docs/cli_ci.md`、其 git 历史和既有真实 CLI artifact 确认交互方式，再通过
真实 `dayu-cli prompt` 经 Host 生成 current-schema 数据。CLI 两次均以 exit code `0` 完成；
第二次真实调用 `list_documents`，Tool 的业务结果为 source-owned `not_found`，但 Host producer、
hot/cold projection 与 payload resolver 链路完整执行。

fresh workspace 直接证据：

- SQLite `PRAGMA user_version=24`，`journal_mode=wal`；
- hot rows=`14`，cold rows=`14`，payload descriptors=`12`；
- hot/cold event type 与计数完全一致；
- strict loader：`source_mode=workspace_directory`、
  `hot_store_available=true`、hot watermark=`41`；
- strict loader：hot/cold/joined=`14/14/14`；
- diagnostics=`[]`，limitations=`[]`，schema versions=`[1]`；
- resolved payload measures=`25`。

同进程在 strict loader 前后重新采集 cold JSONL 与 SQLite 的 SHA-256、mtime、size、row count、
descriptor count 和 schema version，所有值完全一致，`inputs_unchanged=true`。因此 Slice 1
的生产只读承诺已由真实 WAL workspace 直接证明。

按用户约束，若真实 CLI 失败或未产生所需 hot/cold/payload 数据，本 gate 必须停止。本次两个
条件均未触发；没有使用脚本写库、raw SQLite 写入、测试 fixture、复制旧 artifact 或其他替代
producer。

## 验证结果

- focused：`111 passed`
- full Host：`2296 passed, 2 skipped, 6 deselected`
- targeted pyright：`0 errors`
- full pyright：`0 errors`
- 8 个修改 production Python 文件 branch coverage：全部 `>=81%`
- `git diff --check`：通过

## Residual risk

- macOS 可能在文件访问期间维护自身 sidecar 生命周期；验证已以同进程、同一真实 WAL workspace
  的内容哈希、元数据与逻辑计数证明 analyzer input 未被修改。
- 本次真实 Tool 业务结果是 `not_found`，没有证明财报存在时的业务返回内容；它已充分覆盖本
  Slice 所需的真实 Tool request/result producer、hot/cold projection、descriptor resolution
  与严格只读边界。具体 Host/Tool 行为诊断由 Slice 2 owner-level tests 承接。

上述风险均不阻塞 Slice 1 acceptance。

## 下一步

Controller 创建 Slice 1 保护提交；随后仅按 accepted plan 的 Slice 2 allowed files 派发
AgentCodex，实现 deterministic Host/Tool behavioral diagnostics 和 structured report skeleton。
