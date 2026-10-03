# issue #198 plan review：总控裁决与修订要求

- Gate：`plan review -> fix`；日期：2026-09-28。
- 目标：`docs/gateflow/issue-198-download-failure-projection-goal-20260928.md`；候选计划：`docs/gateflow/issue-198-download-failure-projection-plan-20260928.md`。
- 两路独立 review：`docs/reviews/plan-review-20260928-185948.md`（Kimi）、`docs/reviews/plan-review-20260928-190828.md`（MiMo）。两路均为 `pass-with-risks`，但本总控尚不判 plan review gate 通过；先修计划，再 re-review。
- 基线核验：当前部分未提交实现上的 `tests/fins/test_fins_ingestion_runtime.py tests/cli/test_output.py` 共 380 项通过；`python -m pyright dayu/ tests/ utils/` 为 0 errors。它们不是计划实施后的验收。

## 结构化派发核验

两路调用均显式传入绝对 `--cwd /Users/leo/workspace/dayu-agent-r`、独立 output/stderr、各自唯一 label；`sub-agent-preflight` 均通过。controller 读取完整 Claude JSON：Kimi/MiMo 的外层均为 `subtype=success`、`is_error=false`，`num_turns` 分别为 46/75，exit 0；各自 result 中的 canary 与独立 `canary.expected` 逐字一致。stderr 仅各有一行以 `[claude-code:unrecognized_model]` 开头的白名单 warning，无其它失败证据。

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
canary_status: match
warnings:
  - "Kimi: [claude-code:unrecognized_model]"
  - "MiMo: [claude-code:unrecognized_model]"
retry_class: none
```

Kimi：`claude-agent-run` / `kimi` / `kimi-k3[1m]`，label `issue198-planreview-kimi-20260928-01`；output `/private/var/folders/2t/vbqfkdyj40v8f4jc4x180n5c0000gn/T/sub-agents.4JhoFL/issue198-planreview-kimi-20260928-01.json`，stderr 为同目录同 stem 的 `.stderr`。MiMo：`claude-agent-run` / `mimo` / `mimo-v2.6-pro[1m]`，label `issue198-planreview-mimo-20260928-01`；output `/private/var/folders/2t/vbqfkdyj40v8f4jc4x180n5c0000gn/T/sub-agents.vtPEtH/issue198-planreview-mimo-20260928-01.json`，stderr 同 stem。均无需重试。

## Findings 裁决

| 来源 | 总控决定 | 依据和 plan fix 要求 |
| --- | --- | --- |
| Kimi F1 / MiMo F1：安全诊断 helper 自身失败 | **accepted** | `ingestion_runtime.py:_run_direct_stream_producer` 的 catch 内若再抛错，线程可只投 Done 而无 RESULT，且原始 traceback 可经 `threading.excepthook` 泄出。将 helper 规定为对 `Exception` 输入整体不抛出、内部非预期失败只返回固定安全串；增加 helper 异常注入及 producer/CLI 公共失败不变的测试。只保留一个共用实现，不在两处复制宽泛兜底。 |
| MiMo F2：自定义异常类型全抑制 | **accepted，采用安全类型指纹** | 外部帧仅为 `[external]` 时，内建祖先不能区分不同第三方失败。公开日志仍不能包含任意动态类名。plan 改为：内建祖先名加自定义类型的固定长度 SHA-256 指纹（基于类型模块名和限定名；只输出 hex，不输出原文）；读取元数据失败时回退固定 `redacted`，不得破坏不抛出契约。测试断言两种自定义类型可区分，原始名称/secret 不外泄。指纹只是诊断标签，不是业务原因。 |
| MiMo F3：默认日志短暂存在，hint 不可操作 | **accepted，纠正建议的层级归属** | `cli/main.py` 默认使用进程期临时日志，`--log-file` 才持久可查。Fins 公共 `retry_hint` 不应包含 CLI 专属 flag；将其改为入口无关的“保存脱敏诊断再排查”指引，CLI 展示层基于已验证的 `EXECUTION` 分类给出 `--log-file PATH` 的具体做法。CLI 外层既有同类提示复用同一 CLI 文案真源。测试验证无 flag 与有 flag 的用户提示及显式日志文件可读。不得把 CLI 参数放进 Fins 公共契约。 |
| Kimi F2：producer 投影自身失败 | **deferred-with-owner** | 触发需要失败对象/RESULT 构造再次出错，属于独立的失败投影鲁棒性问题；当前 goal 只保证已捕获异常的安全诊断和既定公共映射。登记为后续 `fins-direct-projection-failsafe` work unit；本轮 helper 自身失败由上项修复。实施和 closeout 不得宣称所有二次失败均安全。 |
| Kimi F3 / MiMo R2：另两种 typed storage 错误仍落 EXECUTION | **deferred-with-owner** | goal 限定 `SourceIntegrityPreflightError`。`SourceIntegrityRepairBlockedError` 与 `SourceIntegrityRevisionConflictError` 的业务分类需单独确认，不在本计划扩大；登记后续 `fins-download-storage-sibling-errors` work unit，当前计划明确此残余及误导性重试风险。 |
| Kimi F4：Service 消费者测试 | **accepted** | 公共 `FinsPublicFailure.to_json_value()` 被 wait adapter 消费；测试命令加入 `tests/service/test_fins_wait_adapter.py tests/service/test_fins_direct.py`，并断言 JSON 中 reason 值，不只动态比较对象自身。 |
| MiMo F4：根 README 句子悬空 | **accepted** | #198 句子独立成“下载显示 classification=storage、reason=unsafe_publication 时……”；点号元数据句仍归另一个 work unit。分句后各自应自足、可单独 stage。 |
| MiMo F5：真实 CLI 验证隐私断言过宽 | **accepted** | 分开检查 RESULT/CLI 失败文本、新增安全诊断记录和普通 INFO；前两类不得包含原始异常、URL/token/绝对路径；普通无关日志不以“任何路径出现”直接判隐私泄漏。记录具体命中通道和行以归因。 |
| MiMo OQ4：两层 enum value 漂移 | **accepted** | 本 plan 明确公开词汇须保留四个 storage 原值；测试断言两个枚举按语义一一映射且 `.value` 相等。未来更名必须显式裁决公开合同，不静默改值。 |

其余两路均确认的方向：storage 完整性事实由 storage owner 产生，Fins public reason 用轻量公共 enum 和显式映射，CLI/Service 只投影；外来非点号文件触发 whole-kind `UNSAFE_PUBLICATION` 的复现路径在 HEAD 成立；不做 `init` 的真实 CLI 建库仍需实跑核实。该方向保留。Kimi F1 与 MiMo F1 是计划修订的阻塞项，修后必须 re-review；其它 accepted 项一并修订，未完成时不得实施。

## Residual risks 与下一 gate

- `fins-direct-projection-failsafe`、`fins-download-storage-sibling-errors`：**assigned to later work unit**，先留在总控队列，不把未确认的新目标偷带进 issue #198。任何代码修复须另做 goal confirmation。
- 非 download direct 命令及后台 job 的原始 traceback：**assigned to later work unit** `fins-other-raw-diagnostics-audit`，本轮只处理 download 两个诊断点。
- 网络或 provider 导致独立真实 CLI 复验失败：**requiring evidence in current work unit**；不得用旧事故或 mock 充作本次真实复现。
- 奇异安装形态下受信帧全部降级 `[external]`：**covered by current slice** 的当前布局测试与运行证据；跨布局长期风险登记到 closeout，不要求扩大本轮实现。
- 工作树内点号元数据独立 hunk：**assigned to later work unit**，#198 checkpoint 必须 hunk 级 stage。

当前 gate：`plan review -> fix`；下一入口：由 gpt-6-sol 按本裁决修订 plan，随后 Kimi/MiMo re-review，再做 accepted plan commit。PR #197 是用户指定的现有 draft，后续 PR gate 复用它；用户手工 merge。

## 第一次 re-review 后的追加裁决

- Kimi：`docs/reviews/plan-review-20260928-193002.md`，`pass`，原 accepted findings 在计划层均闭环，延期项与裁决一致。
- MiMo：`docs/reviews/plan-review-20260928-194543.md`，`pass-with-risks`，原 accepted findings 在计划层均闭环，但新增两项低严重度 finding。两份完整 artifact 与相关 `fins.py:104,216-222`、`ingestion_runtime.py:4388-4394,6881-6887,7290-7296` 已由总控交叉核对。

| 新 finding | 总控裁决 | 最小 plan fix |
| --- | --- | --- |
| MiMo re-review F1：外层固定错误文案归属不清 | **accepted** | `output.py` 独占一处 CLI `--log-file PATH` 日志提示；外层所有 direct 命令的固定错误由“命令执行失败，”加该提示组合，**最终文本保持现有非 download 文案逐字一致**，删除 `fins.py` 的重复提示常量。非 download 的原始 traceback 日志行为在本 work unit 保持；download 改安全日志。CLI download RESULT 的 EXECUTION 失败详情复用该提示。测试固定上述两个用户可见场景。 |
| MiMo re-review F2：EXECUTION 分类含无来源文档而无 unknown 诊断 | **accepted** | 共用 CLI 提示使用“运行日志”，不承诺每个 EXECUTION 均有 `fins.download.*` 未知异常诊断；无来源文档时可查看普通 INFO 和已有文档 RESULT。测试分别覆盖 unknown 异常的安全诊断与无来源文档的非异常 EXECUTION，后者不应期待 unknown 日志。现有 Fins 无来源文档 `retry_hint` 在默认临时日志下仍欠可操作，登记为后续 `fins-download-no-source-retry-hint` work unit，不能以本轮 CLI 提示冒充 Service/JSON 路径的修复。 |

MiMo 对“诊断日志先于 RESULT”提出的次要风险：要求 S2 在 producer 已构造失败对象后先发 RESULT，再尝试写安全 operator 日志；这样日志写入失败不会抢先阻断公共失败。logger 本身若再次抛出、线程原始 traceback 泄出仍属已登记的 `fins-direct-projection-failsafe`，本轮不扩大为所有二次异常的捕获框架。

上述两项均为实施派发前必须收敛的计划文字与测试期待，不重写 S1/S2。待 Sol 修订并 re-review 通过后方可 accepted plan commit。残余队列新增 `fins-download-no-source-retry-hint`，分类为 **assigned to later work unit**。

## 最终 plan gate 裁决

- Sol 第二次 plan fix：`issue198-plan-fix-sol-20260928-02` 的结构化派发完整通过；原始结果和独立 stderr 见 dispatch artifact。计划固定版本 SHA-256：`0b854a97bd72eaff0dbaa2fcbdde43738e1d0a6092d4dfc22604ad5515b489f3`。
- 最终 Kimi re-review：`docs/reviews/plan-review-20260928-200635.md`，`pass`；最终 MiMo re-review：`docs/reviews/plan-review-20260928-200508.md`，`pass`。两路均显式 `--cwd /Users/leo/workspace/dayu-agent-r`、不同 output/stderr，preflight ok、exit 0、外层 `subtype=success`、`is_error=false`，`num_turns` 28/26，canary 与 expected 逐字一致；stderr 仅各一条白名单 `unrecognized_model` warning。controller 阅读完整 artifact 并复核 `fins.py:104,216-222` 的原文案和三类 EXECUTION 生产路径。

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
canary_status: match
warnings:
  - "Kimi: [claude-code:unrecognized_model]"
  - "MiMo: [claude-code:unrecognized_model]"
retry_class: none
```

最终 finding 状态：原 review 中全部 accepted 项、第一次 re-review 的 MiMo F1/F2 在**计划层已修复**，两个 reviewer 的最终 artifact 未发现新 finding；Kimi F2、Kimi F3/MiMo R2 为**未修复但 deferred-with-owner**，加上无来源文档 hint 与非 download 原始日志均有后续 work unit。网络/fresh workspace 的真实 CLI 证据仍必须在实施 gate 取得，未预判为通过。结论：**plan review / fix / re-review pass**；current gate/next entry point 为 `accepted plan commit`，commit 完成后转 `implementation S1`。PR #197 复用边界与用户手工 merge 要求不变。
