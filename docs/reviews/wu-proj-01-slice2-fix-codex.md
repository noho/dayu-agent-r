# WU-PROJ-01 Slice 2 Fix - AgentCodex

## Artifact Path

- `docs/reviews/wu-proj-01-slice2-fix-codex.md`

## Fixed Findings

- DS-S2-L2：新增 focused test `test_proactive_fallback_material_blocks_append_current_input_once`，直接构造同源 `PreDispatchCompactMaterialView`，断言 `material_view.material_blocks` 不包含 current input source ref / event sequence，并断言 `_proactive_fallback_material_blocks` 追加后 current input anchor 只出现一次。
- MiMo INFO-3：在 `test_multi_turn_proactive_compact_feeds_subsequent_run_input` 的 policy 阈值调整附近补充简短注释，说明同源 material view 估算包含 previous view、delta 与 current input，需要超过 soft threshold 且低于 hard threshold，测试目标仍是 proactive compact lifecycle。

## Changed Files

- `tests/host/test_dispatch_scheduler.py`
- `docs/reviews/wu-proj-01-slice2-fix-codex.md`

## Validation

- `source .venv/bin/activate && python -m pytest tests/host/test_dispatch_scheduler.py -k "governance or compact or proactive"`：19 passed，48 deselected。
- `source .venv/bin/activate && pyright`：0 errors，0 warnings，0 informations。

## Blocking Open Questions

- 无。

## Residual Risks

- 未处理 deferred findings：material source failure exception taxonomy、reactive diagnostic event、reactive budget estimate 仍按 controller adjudication 留给后续 owner。
- 本轮只修 accepted test/comment items，未修改 production code、design docs、control doc、README 或 GitHub issue。
