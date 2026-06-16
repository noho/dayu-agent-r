# WU-CLI-FINS-OBS-01 Slice C Review Fix

## Gate

- Work unit: `WU-CLI-FINS-OBS-01`
- Slice: `Slice C: Fins ingestion runtime core API convergence`
- Gate: review fix
- Implementer: AgentCodex
- Date: 2026-06-16

## Review Inputs

- `docs/reviews/wu-cli-fins-obs-01-slice-c-review-mimo-20260616.md`
- `docs/reviews/wu-cli-fins-obs-01-slice-c-review-ds-20260616.md`

## Adjudication

两路 review 均通过，没有 blocking finding。

非阻塞项中，`DS-C01` 指出 runtime `_run_direct_stream` 在 producer 静默结束且未产出 `RESULT` 时依赖 Service 层兜底；该项虽不影响当前端到端行为，但 direct stream 自身契约应该保证“不静默结束”，因此在 Slice C 内修复。

`DS-C02` 指出 `_put_direct_queue` 在 consumer 已取消后静默丢弃事件缺少注释；该行为符合 best-effort cooperative cancellation 设计，但补充注释可降低后续误改风险，因此一并修复。

MiMo 的 `F1` 是 bounded sync bridge 在极端反压下的轮询开销观察。当前 queue 有界、超时有界、取消检查有界，且 bridge 仍是内部实现细节；该项不需要扩大设计，保留为已知实现限制。

## Fixes

1. `dayu/fins/ingestion_runtime.py`
   - 在 `_run_direct_stream` 中增加 producer 静默结束兜底：若收到完成哨兵但尚未见到 `RESULT`，runtime 自身 yield `RESULT(status=FAILURE)`。
   - 新增 `_direct_missing_result_event`，只投影 bounded failure summary，不包含 job id、cursor、sidecar、路径或 raw payload。
   - 在 `_put_direct_queue` 的取消分支补充注释，说明 consumer 已结束时丢弃后续事件是预期行为。

2. `tests/fins/test_fins_ingestion_runtime.py`
   - 新增 `test_direct_stream_missing_result_returns_failure_result`，直接模拟 producer 未产出终态并退出，验证 runtime 不会静默结束。

## Validation

```text
source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_runtime.py -q
60 passed, 3 warnings

source .venv/bin/activate && pyright dayu/fins/ingestion_runtime.py dayu/fins/service_runtime.py tests/fins/test_fins_ingestion_runtime.py
0 errors, 0 warnings, 0 informations

git diff --check
clean
```

## Residual Risk

- `dayu/fins/README.md` 仍待 Slice E 集中同步。
- Tools awaiting / wait adapter 仍待 Slice D 从 legacy job observation 迁移到 lightweight observation handle。
- MiMo `F1` 的极端反压轮询开销属于当前 sync adapter 桥接的实现限制，不外露为公共契约；无需为本 slice 引入更重的 runtime 机制。
