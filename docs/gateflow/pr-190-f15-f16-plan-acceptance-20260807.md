# PR 190 F15 / F16 Accepted Plan

- Goal Confirmation: `docs/gateflow/pr-190-f15-f16-goal-confirmation-20260807.md`
- Accepted plan: `docs/gateflow/pr-190-f15-f16-plan-20260807.md`
- Initial reviews: AgentMiMo / AgentDS 均为 `pass-with-risks`
- Controller adjudication: `docs/gateflow/pr-190-f15-f16-plan-review-adjudication-20260807.md`
- Final re-reviews: AgentMiMo / AgentDS 均为 `pass`，无新 finding

## Accepted owner decisions

- F14 frontier 不变，唯一真源仍是 strict accepted chain cumulative `compacted_source_refs`。
- F15 在 Host previous compacted pair projection owner 内，以 private typed canonical text/projection 一次生成 packed block 与 readable view；validator保持 exact，不 skip、不 fallback、不逆向解析。
- F16 只从 Host Run terminal canonical `reason_json={"reason": <non-empty str>}` 与 shared lifecycle types 投影逐 Run 事实；process outcome、Run terminal、dependency gate 与 evidence integrity 分离。
- observation helper 使用物理只读 Host store和 filtered EventLog keyset window；临时 harness 只负责 PTY orchestration及文件写入。
- 不改变 durable schema、Engine contract、CLI public surface或 compactor LLM schema；若实施发现必须改变，停止并回到 Goal Confirmation。

## Next gate

进入 implementation。AgentCodex 按 accepted plan 实现 F15/F16、owner tests与文档；AgentController 保留语义裁决和 gate 顺序。
