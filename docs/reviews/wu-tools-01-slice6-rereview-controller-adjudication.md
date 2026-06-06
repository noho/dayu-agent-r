# WU-TOOLS-01 Slice S6 Re-Review Controller Adjudication

Gate: re-review adjudication
Work unit: WU-TOOLS-01
Slice: S6 - Combined Discovery / ToolRuntime Acceptance / Docs Closure
Status: PASS-WITH-EXTERNAL-BLOCKER

## 输入

- `docs/reviews/wu-tools-01-slice6-fix-codex.md`
- `docs/reviews/wu-tools-01-slice6-rereview-mimo.md`
- `docs/reviews/wu-tools-01-slice6-rereview-ds.md`

## 裁决

MiMo 与 DS re-review 均为 PASS。Controller 接受 S6 implementation + fix。

## A1 复核

- `_legacy_adapter` defensive `fetch_more` allowlist 精确到 3 个文件：`tools/_legacy_adapter/__init__.py`、`tools/_legacy_adapter/definition_adapter.py`、`tools/_legacy_adapter/registry_collector.py`。
- Business provider 文件不在 allowlist 中，仍会被 `fetch_more` owner test 捕获。
- OLD fetch-more projection token `fetch_more_args`、`project_for_llm`、`continuation_hint` 对 `dayu/` 全包扫描，且无 allowlist 逃逸。
- `compaction_operation.py` 当前只依赖 Engine contracts，加入 Host -> Engine contract allowed boundary 合理。
- `tests/README.md` 描述与测试契约一致。

## Controller 验证

- `source .venv/bin/activate && pytest tests/host/test_import_boundary.py tests/tools/test_combined_tools_acceptance.py`: 21 passed。
- `source .venv/bin/activate && pyright`: 0 errors, 0 warnings, 0 informations。
- `git diff --check`: clean。

## Remaining External Blockers

Broad validation 仍有 11 个 Host 行为失败，均非 S6 引入，记录为 external blockers / separate Host follow-up：

- Proactive compaction missing proposal manifest ref：7 tests。
- Effective execution config one-system-message envelope expectation mismatch：2 tests。
- Wait / resume old accepted-result text expectation mismatch：2 tests。

S6 accepted with these blockers explicitly classified.
