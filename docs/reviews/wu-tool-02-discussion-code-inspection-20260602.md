# WU-TOOL-02 Discussion Code Inspection

## 范围

- Work unit: `WU-TOOL-02 Accept Candidate Structure Cleanup`
- Design source: `docs/host/design.md`
- Control source: `docs/host/host-core-followup-implementation-control.md`
- Gate: discussion / code inspection

## Controller 裁决

动机成立。当前 `ToolFactAcceptCandidate` 过宽问题仍真实存在，但它是维护性、可测试性和后续演进风险，不是当前运行时 correctness blocker。最佳实践是进入 plan gate，要求 planning agent 生成 code-generation-ready 的结构清理 plan，并严格保持现有 ToolRuntime / accept barrier 语义不变。

基于 `docs/host/design.md` 的设计目标，Host 必须保持 ToolRuntime governance、Host-mediated accept barrier、工具事实可追溯与分层边界清晰；把 identity、tool call、result、governance、accept idempotency、diagnostics 等职责长期堆在一个 candidate 顶层结构中，会增加后续治理字段变更时误伤 EventLog payload、trace、memory 或 compaction 消费路径的概率。

## 直接证据

- `dayu/host/tool_runtime.py` 中 `ToolFactAcceptCandidate` 当前集中承载 Session / Run / Attempt / execution identity、tool call identity、schema / identity digest、normalized args digest、fact kind、result digest / payload ref、truncation、raw tool outcome、duplicate governance、reuse refs、policy decision、tool idempotency、diagnostic refs、accept idempotency 与 semantic digest。
- `ToolFactAcceptCandidate.__post_init__` 需要按 `COMPLETED`、`FAILED`、`CANCELLED`、`GOVERNED_ERROR`、`REUSE` 分支校验字段组合，说明不同 fact kind 实际拥有不同必填与禁止字段。
- 默认 accept barrier、EventLog payload 构造、accepted evidence envelope、accepted ack、diagnostic logging 和测试 helper 均直接读取 candidate 顶层字段。
- `tests/host/test_toolruntime_accept_barrier.py` 等测试仍需要手写超宽 candidate 构造参数；这与 WU-TOOL-02 的验收信号“测试 helper 不再到处手写超宽 `ToolFactAcceptCandidate` 构造参数”一致。

## Scope Boundary

当前 work unit 应只做内部 typed structure 清理：

- 保持 `ToolFactAcceptCandidate` 为 Host 内部类型，不导出为 public API。
- 不改变 `TOOL_CALL_REQUESTED`、`TOOL_CALL_GOVERNED`、`TOOL_RESULT_ACCEPTED` 的持久语义。
- 不改变 duplicate governance attempt-local 语义。
- 不改变 raw tool outcome、accepted evidence envelope、memory、compaction、tool trace 的可观察行为。
- 不引入兼容 wrapper、旧字段 re-export 或额外 public contract。

## Blocking Open Questions

无。当前设计真源和总控文档足以进入 plan gate。
