# WU-RUNTIME-01 Plan Controller Adjudication

## 结论

WU-RUNTIME-01 plan gate 通过。`docs/host/wu-runtime-01-filelock-contraction-plan.md` 可作为 implementation handoff。

## 裁决依据

- `docs/host/design.md` 将 `dayu.runtime.filelock` 定义为第三方 `FileLock` 的层中立同步 wrapper，只用于普通文件互斥，不表达 Host durable truth、EventLog ordering、Run / Attempt owner、lease、fencing 或 recovery。
- `docs/host/host-core-followup-implementation-control.md` 的 WU-RUNTIME-01 目标是收缩 `RuntimeFileLock`，删除或隐藏无生产调用方依赖的 token released 状态，让第三方 `FileLock` 继续持有实际 acquire / release 生命周期真源。
- 代码核对显示生产调用面只通过 `with file_lock(...)` 保护 audit / tool trace JSONL append，未读取 `RuntimeFileLockToken.released`，也未依赖同实例 `_active_token` gate。
- 用户明确补充“不做过度设计”，本裁决据此拒绝 stale lock、break lock、async wrapper、durable lease、Host recovery、lane 或 audit/tool trace 行为重构。

## Review 结果

- `docs/reviews/wu-runtime-01-plan-review-mimo-20260601.md`：`pass-with-fixes`，1 个 blocking finding，2 个 non-blocking findings。
- `docs/reviews/wu-runtime-01-plan-review-ds-20260601.md`：`pass-with-fixes`，1 个 blocking finding，3 个 non-blocking findings。
- `docs/reviews/wu-runtime-01-plan-rereview-mimo-20260601.md`：`pass`，所有 finding closed，无新增 overdesign。
- `docs/reviews/wu-runtime-01-plan-rereview-ds-20260601.md`：`pass`，所有 finding closed，无新增 overdesign。

## Finding 裁决

| Finding | 裁决 | 理由 |
|---|---|---|
| MiMo F1：context manager 私有状态存储方式未明确 | accepted / closed | 基于设计目标和第一性原理，context manager cleanup 需要最小私有 frame 引用；plan 已明确 `_context_token` 只服务 `__exit__` cleanup，不参与 acquire gate，不形成第二套 lifecycle truth。 |
| MiMo F2：`__exit__` release 抛错后应清空引用 | accepted / closed | 清空 `_context_token` 是局部 cleanup，不扩大 runtime 抽象；plan 已要求 `finally` 清空并继续传播 release 错误。 |
| MiMo F3：release 失败后 retry 行为需记录为 deliberate contract | accepted / closed | release 失败不标成功是当前 WU 的核心 correctness 目标；plan 已明确允许 retry 是 contract contraction，不是兼容旧行为。 |
| DS Finding 1：Slice 1 未点名旧同实例 gate 测试处置 | accepted / closed | 旧测试会诱导保留 `_active_token` gate；plan 已点名删除或改写相关测试，避免 implementation agent 自行设计兼容路径。 |
| DS Finding 2：`_context_token` 属性名与交互契约未指定 | accepted / closed | 明确命名和禁止 acquire 读写可降低实现自由度，符合“不做过度设计”。 |
| DS Finding 3：`tests/README.md` 更新触发条件不精确 | accepted / closed | README 只在稳定说明不一致时更新；plan 已收敛为当前证据倾向不改，避免机械文档 churn。 |
| DS Finding 4：release 失败测试需拆分 shape 与行为 | accepted / closed | shape 与行为分开验证更直接，能防止只删除 public 字段却漏掉失败后误标成功状态。 |

## Residual Risk

- 同一 `RuntimeFileLock` 实例的 reentrant / nested acquire 具体行为不承诺，符合设计真源非目标；implementation 不应为其写兼容 gate。
- Lock marker 文件不是 Host truth；release 成功后的 marker restore 仍是 best-effort debug 语义。
- WU-RUNTIME-02 的 lane clock / cancellation 风险不进入本 work unit。

## 下一步

进入 implementation gate。Implementation agent 应按 plan 的 Slice 1、Slice 2 执行，禁止扩大 scope；若实现发现必须修改 Host production source、保留 `released` 兼容 property、引入新 lock 抽象或改变 audit/tool trace 语义，必须停止并交回 controller。
