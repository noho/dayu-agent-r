# Code Review

## Scope

- Mode: current changes
- Branch: `phase/wu-tools-cancel-01`
- Base: `main` (workspace uncommitted changes since commit `4f9df113`)
- Output file: `docs/reviews/wu-tools-cancel-01-residual-hardening-s3-code-review-mimo.md`
- Included scope: Slice S3 `Tool Migration And Fins AAPL XBRL Fixture Breadth` — 6 changed files + 1 new fixture directory
- Excluded scope: S1/S2A/S2B changes (already accepted), `dayu/contracts/tool_execution.py` (S1 artifact)
- Parallel review coverage: 无

## Findings

未发现实质性问题。

### 补充观察（非 defect，severity 不适用）

**Observation 1 — `_web_process_failed_envelope` 保留了合约 helper 之前的防御性默认值**

- **文件**: `dayu/tools/web/web_tools.py:1648-1654`
- **内容**: `_web_process_failed_envelope` 在调用 `process_tool_failed_envelope` 前执行 `error_type.strip() or "execution_error"` 和 `message.strip() or "Tool execution failed."`，而 `doc_tools.py` 和 `fins_tools.py` 的 `_process_failed_envelope` 直接透传给合约 helper（由 helper 的 `ValueError` 校验兜底）。
- **评估**: 这是层内防御性设计选择，不是缺陷。Web 层保留本地默认值不影响合约一致性，也不破坏 hint/message 分离。如果未来希望三个工具层的防御策略完全对齐，可以在后续 slice 统一，但不阻塞 S3。

## Open Questions

- 无。

## Residual Risk

1. **XBRL taxonomy 网络依赖**: edgartools 的 `XBRL.from_files` 在解析本地 .xsd + instance XML 时，如果 inline XBRL 引用了外部 taxonomy schema URL，理论上可能触发 HTTP 请求。当前实测通过（114 passed），但若 edgartools 版本升级改变解析行为，fixture 可能需要补充本地 taxonomy 文件。实施 artifact 已声明"Live SEC/network taxonomy resolution was not used or required"，与实测一致。
2. **Fixture 体积**: AAPL XBRL fixture 目录约 4.6 MB（8 个文件）。对 CI 可接受，但若后续需要更多 filing fixture，应评估 git 仓库体积影响。

## Verification Summary

| 检查项 | 结果 |
|--------|------|
| Doc/Fins/Web 迁移到 `dayu.contracts` envelope helper | ✓ 三个工具文件均 import 并使用 `process_tool_completed_envelope` / `process_tool_failed_envelope` |
| 本地 envelope 常量已移除 | ✓ `grep -rn '_DOC_PROCESS_\|_FINS_PROCESS_\|_WEB_PROCESS_' dayu/` 返回空；`_process_failure_message` 函数已删除 |
| failed envelope hint 结构化分离 | ✓ 三个工具的 `_process_failed_envelope` / `_web_process_failed_envelope` 传递 `hint` 参数；message 不再拼接 `"Hint: ..."` |
| Host 通过合约解析器消费 hint | ✓ `tool_runtime.py:6586` — `hint=parsed.hint` 传入 `_tool_failed_outcome` |
| Host 未 import concrete tools | ✓ `grep -n 'import.*dayu.tools\|import.*dayu.fins' dayu/host/tool_runtime.py` 返回空 |
| runtime 无反向依赖 | ✓ `dayu/contracts/tool_execution.py` 和 `dayu/runtime/interruptible_process.py` 无 `dayu.host/engine/service/ui/fins` import |
| tool schema 未暴露 envelope 字段 | ✓ envelope 字段是输出结构，不在 `ToolSchema` 输入参数中；现有 `test_fins_read_tool_schemas_do_not_expose_execution_context` 等测试已覆盖 |
| AAPL XBRL fixture 通过 `dayu.fins.storage` 仓储协议构造 | ✓ `_build_fins_aapl_xbrl_workspace` 使用 `FsBatchingRepository` / `FsCompanyMetaRepository` / `FsSourceDocumentRepository` / `FsDocumentBlobRepository` |
| fixture 本地自足 | ✓ meta.json + 7 个 XBRL 文件均在 `tests/fins/fixtures/aapl_xbrl/` 下；无网络下载步骤 |
| fixture 无编造 fact | ✓ 数据来自已下载的真实 AAPL 2024 10-K filing (`fil_0000320193-24-000123`) |
| 新测试覆盖 S3 要求 | ✓ hint/message 分离测试、本地常量防回潮测试、AAPL XBRL spawned child 测试 |
| pytest | 114 passed, 1 skipped |
| pyright | 0 errors |
| git diff --check | passed |

## Conclusion

**PASS**

S3 实现完整、正确地完成了三项核心迁移：(1) 三个工具文件的 envelope 构造统一到 `dayu.contracts` 单一真源；(2) failed envelope 的 `hint` 从 message 拼接改为结构化独立字段；(3) AAPL XBRL fixture 通过仓储协议构造、本地自足、覆盖真实 filing 数据。无 correctness、architecture boundary 或 test coverage 的实质 defect。
