# WU-SEMANTIC-OWNERSHIP-01 aggregate regression fix Slice 1 fourth stop Controller adjudication

## 1. 裁决

- 时间：`2026-07-18 17:51:49 +0800`。
- Gate：同一 Slice 1 implementation continuation；不是新 WU、不是新 slice，allowlist不变。
- AgentCodex fourth stop：`VALID / CORRECTLY STOPPED`。第三次裁决后的functional tests通过，但full pyright仍报告结构化filter protocol不兼容；AgentCodex未猜测隐藏类型或继续后续门禁。
- Controller verdict：`PUBLIC PROTOCOL CALL-SHAPE TOO STRICT / SAME-LINE FIX AUTHORIZED / NOT_PRODUCTION_DEFECT`。

## 2. Root cause

当前public Protocol声明`filter(self, record: logging.LogRecord) -> bool`，这不仅要求实现者能被位置调用，还要求它接受名为`record`的关键字参数。Logging filter的消费契约只需要把`LogRecord`作为位置参数传入；一个只接受位置参数的合法结构对象因此不能满足当前过严Protocol。

把参数声明为positional-only的`filter(self, record: logging.LogRecord, /) -> bool`准确表达最小public调用语义，同时仍保持输入/返回类型严格。该裁决不依赖private typeshed形状，不复制private alias，也不放宽为cast/ignore/Any/object。

## 3. 补充精确授权

AgentCodex在同一任务follow-up中获准且必须：

1. 只在已授权的`tests/tools/web/test_smoke_web_ci.py`给`_LogRecordFilter.filter`的`record`参数增加positional-only标记`/`；其它type union、snapshot/restore逻辑与contract assertions均不得改变。
2. 更新同一implementation artifact；先fresh运行scoped/full pyright、topology contract、Web focused与order-sensitive联跑。
3. 随后在最终tree完整fresh重跑canonical、exact-exclusion coverage/219 ledger、三项real smokes、Ruff exact delta、build、six scans、security/secret/deferred/no-code/README/scope gates。不得复用第四次stop前结果作为final-tree签署。
4. 任何新错误、失败或额外path需求再次停止。

## 4. 不变边界与next entry

- Controller docs/control全部protected；不得修改。
- Slice 2/3、review、commit、push、PR、aggregate deepreview与closeout仍未授权。
- Topic 8/9、security、deferred owners及`AR-F06`/`AR-F07`状态不变。
- Next entry：AgentCodex same-task implementation follow-up；全部fresh gates完成后停在Controller validation。
