# UM-O14/O15 state plan PR-C5-F1～F3 纯计划修订记录

- RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/gpt-6-sol
- CANARY=gpt-6-sol-67e4e85e
- 工作范围：只修改 `docs/gateflow/upload-material-state-plan-20260929.md` 并新增本记录；不实施 O12/state，不修改产品、测试、README、goal、adjudication、旧 review 或主队列，也不进入 review/commit/push/PR/merge。

## 锁定版本与动机

| 对象 | SHA-256 / commit |
| --- | --- |
| state plan 修改前，任务锁 | `1fe2f5462a0d7a7bdb54edda3985965713a2e87890f5c8dba9b9c823e98778b6` |
| state plan 修改后 | `4ab1546efdc7f73a5acbd79064299459b6062af95acc4db1283fbb9ae6f0b24d` |
| 本 checkout HEAD | `8d8d494fbbce0052372fb1b42097c9f7222cfa28` |
| 最新总控裁决 | `docs/gateflow/upload-material-state-plan-review-adjudication-20260929.md`，PR-C5-F1～F3 均 accepted／未修复，要求只修计划后同新 SHA 双路复审 |
| 同版 review | `docs/reviews/plan-review-state-prc4-mimo-rereview-20260929.md` 与 `docs/reviews/plan-review-state-prc4-kimi-20260929.md`，均锁修改前 SHA |

动机成立，属计划合同缺口而非已发生的产品修复。MiMo 的直接反例是 target 共码却需双文案、fact hint 与 reason optional 边界含糊、CLI raw format 可先于 runtime；Kimi 的同版 OQ 也指出 kind 维度和 CLI raw 入口。`AGENTS.md` 要求同一业务语义只由一个 owner 产生，不能由 CLI/tool 补文案。本轮据此限定 producer 输入、public 投影和早期入口，不改变已接受的状态/发布行为。

## 一手代码锚点与修订

| 项 | 当前代码直接证据 | 计划修订 |
| --- | --- | --- |
| PR-C5-F1 | `dayu/fins/ingestion_runtime.py:702-703` 两个 target code 共用；`:1027-1059` `_USAGE_MESSAGES` 一码一文案，`:1054-1055` filing 旧文案；`:1062-1097` producer 只收 code/file_name，filing 调用在 `:1506-1514`。 | §5 明确唯一 producer 对 target 必收 typed `SourceKind`，以 `(code, kind)` 同源选文案/hint；filing 两句逐字保留，material 三句明确“目标材料”，`DELETE_TARGET_MISSING + filing` 在 owner 拒绝。owner 测试同码双 kind 的精确文案/hint及负例；下游不得有第二表。 |
| PR-C5-F2 | `dayu/fins/upload_failure.py:79-95` 的 `retry_hint: str | None`；`:118-120` 仅非 None 时验证；`:280-285` 的 `UNEXPECTED_RUNTIME` 以 `None` 构造，JSON 恢复在 `:443-474` 接受 optional。 | §5 将 **usage fact `hint: str` 全 code 必填** 与 **public reason `retry_hint` 既有 optional** 分开；仅 target/format 经 mapper 投影时要求非空且等于 fact.hint，旧 reason 的 None 及 JSON 往返保持。测试两类正反例，不改全局 public schema。 |
| PR-C5-F3 | `dayu/cli/commands/fins.py:723-729` 在 Service 前构造 material files；`:1128-1147` 的 selection 可抛 raw `FinsUploadFormatError`；`:198-203` 分别捕获 typed usage 与 raw format，后者直接显示异常文本。runtime 的 `_raise_upload_format_usage` 在 `dayu/fins/ingestion_runtime.py:1121-1134` 也尚未走统一 producer。 | §5 与 S1 把 CLI `_validated_upload_files` 的 format 异常边界定为实施落点：只把原 typed format error 交给同一 Fins usage producer 装箱，再抛 typed usage；CLI 不私造 message/hint/label。`tests/cli/test_fins_commands.py` 须以真实不支持后缀验证早于 Service/runtime 的异常 fact 和 CLI usage exit，并与 runtime/tool 同 kind fact 逐字段比对；`upload_material` 的 raw catch 路径应不可达。 |
| format label owner | `dayu/fins/upload_format_contract.py:19-22,85-111,137-150` 使用并验证公共 canonical label；算法唯一真源为 `dayu/fins/direct_events.py:1080-1118`。 | 保持旧计划的格式 owner/算法分工，usage producer 和 CLI 原样透传，不迁移或复制 canonicalizer。 |

已核对 §三态动作表保持 material missing/active/tombstone 与 filing 各格；O12 accepted plan 仍是 S1/S2 **产品集成硬门槛**。当前 `dayu/fins` 未见 `MaterialUploadPublishedState`、`_material_upload_admission`、`MaterialUploadPublishedStateConflictError` 定义，不能宣称 O12 或 state 产品已集成。O34 合法公司独立提交事实、材料单独 guarded publication、O13 同指纹 tombstone 恢复版本规则、O18 amended 分工均保持原计划边界。

## 验证、残余和下一步

- 修改前 SHA 与任务锁匹配；修改后 SHA 已计算。只读核对了新 §5、S1、owner/CLI 测试、真实 CLI 格与停止条件；所有实际 shell 命令自身 exit 0，预期无 O12 符号的查询用显式 `if` 捕获。未运行 pytest/pyright：本轮只改计划，未来 implementation gate 仍须按计划激活 `.venv`、运行受影响测试/pyright/逐生产文件覆盖率。
- 计划是待独立同 SHA review 的候选，不代表 plan gate pass，更不授权实施。O12 实际集成 API、公司/材料 guard 与 alias/active-only 终态行为可能漂移，必须在实施前按主计划硬门槛实读；若 source kind 无法由唯一 producer 表达、CLI raw format 不能按既有 owner 分层归一、或需改变 filing 文案/公共 reason schema，停止相应实施并以代码调用图回总控裁决。
- 冻结 A04 尚无“已有不同内容 create”的真实 CLI 样本；O13 时间幂等、O18 amended、O33 auto 并发 skip 和 material tombstone create 新语义仍由各自 work unit 负责。下一 gate 仅由总控安排新 SHA 的独立计划复审，本轮到此停止。
