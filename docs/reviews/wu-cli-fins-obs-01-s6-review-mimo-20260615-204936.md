# Code Review

## Scope

- Mode: current changes
- Branch: `phaseflow/host-issues-implementation`
- Base: `main`
- Output file: `docs/reviews/wu-cli-fins-obs-01-s6-review-mimo-20260615-204936.md`
- Included scope: S6 未提交文档改动 — `dayu/README.md`（unstaged）、`dayu/fins/README.md`（unstaged）、`docs/reviews/wu-cli-fins-obs-01-s6-implementation-codex.md`（untracked）
- Excluded scope: 生产代码、测试代码、`dayu/service/README.md`（已在 S3 committed 更新）、`tests/README.md`（已在 S1-S5 committed 更新）
- Parallel review coverage: 无

## Review Basis

- Slice S6 plan：`docs/host/wu-cli-fins-obs-01-fins-direct-live-events-plan.md` lines 506-540（S6-docs-sync）
- README Agent更新约束：`dayu/README.md` lines 11-17、`dayu/fins/README.md` lines 16-24
- CLAUDE.md README 更新触发规则
- 代码事实：`dayu/fins/ingestion_events.py`、`dayu/fins/ingestion_runtime.py`、`dayu/service/fins_direct.py`、`dayu/service/README.md`（S3 committed）、`tests/README.md`（S1-S5 committed）
- S1-S5 已提交实现：`git diff main...HEAD` 的 committed changes

## Findings

未发现实质性问题。

### 验证详情

#### 1. README 是否只写已落地事实

- `dayu/README.md` 三处改动（lines 72、88、111）均描述 S1-S5 已落地的 `stream_job_events_until_terminal(...)`、`read_job_events(...)`、terminal fallback、`request_cancel(job_id)` 能力。无未来计划、无 work unit 流水账。
- `dayu/fins/README.md` 四处改动（lines 147、268、373、406-408、525-530）均描述已落地的 `read_job_events(...)` API、`dayu.fins.ingestion_events` 模块、event sidecar JSONL 和事件类型分类。无未落地能力。
- 两份 README 均符合各自 Agent更新约束："只保留当前代码已经实现且对开发者稳定有用的说明"。

#### 2. 是否正确表达 Fins direct start/event observation/poll terminal fallback/cancel

- `dayu/README.md` line 72：`start / event observation / poll terminal fallback / cancel` — 与 `dayu/service/fins_direct.py` 的 `stream_job_events_until_terminal(...)` (line 550) + terminal fallback 逻辑 + `request_cancel(job_id)` 一致。
- `dayu/README.md` line 88：`event observation、poll terminal fallback` — 与 `FinsDirectCommandService` 职责一致。
- `dayu/README.md` line 111：`消费 Fins job event、必要时回退轮询 terminal job record` — 与 `stream_job_events_until_terminal(...)` 的 terminal fallback 实现（line 571+，empty event sidecar 时读 terminal job record 合成 event）一致。
- 旧边界描述 `start / poll / cancel` 在所有四份 README 中已不存在（grep 验证通过）。

#### 3. 是否明确 Fins job event sidecar 不是 Host EventLog/Host truth

- `dayu/fins/README.md` line 525：`也不写 Host EventLog` — 明确否定。
- `dayu/fins/README.md` line 530：`这些事件只服务 Service / UI 观察，不是 Host durable truth` — 明确定性。
- `dayu/fins/README.md` lines 406-408：`JOB_QUEUED`...`JOB_CANCELLED` 是 job record 已保存后的状态观察；job record 仍是状态真源。`PROGRESS` 与 `CANCEL_REQUESTED` 是观察 / 进度信号，不能被当作 job 状态转换 — 正确区分 status transition events 与 observation events，与 `FinsIngestionJobEventType` docstring（`ingestion_events.py` lines 28-46）一致。
- `dayu/fins/ingestion_events.py` module docstring（lines 1-7）：`事件用于 Service / UI 观察 Fins direct job 进展，不属于 Host EventLog、Engine stream 或 provider 原始事件` — 代码真源与 README 一致。

#### 4. 未修改 dayu/service/README.md 和 tests/README.md 的理由是否成立

- `dayu/service/README.md`：S3 commit `4164b4da` 已更新，当前内容（line 13）包含 `job event observation、poll terminal fallback`；lines 24-25 包含 `stream_job_events_until_terminal(...)` 和 terminal fallback 语义。S6 无需再改。理由成立。
- `tests/README.md`：S1-S5 commits 已更新，当前内容覆盖 Fins direct command event stream 消费（line 94-102）、Fins direct Service boundary 测试（line 136-138）、ingestion job event sidecar 测试（line 177-178）。S6 无需再改。理由成立。
- `git diff main...HEAD --stat` 确认这两份文件在 S1-S5 有 committed changes（`dayu/service/README.md` +4/-4、`tests/README.md` +19/-19）。

#### 5. 是否遗漏 README 触发

按 CLAUDE.md README 更新触发规则：
- `dayu/fins/` 修改 → `dayu/fins/README.md` ✅ 已更新
- `dayu/service/` 修改 → `dayu/service/README.md` ✅ S3 已更新，S6 无需再改
- `tests/` 修改 → `tests/README.md` ✅ S1-S5 已更新，S6 无需再改
- 跨包 Service/Fins/CLI 边界变化 → `dayu/README.md` ✅ 已更新

未遗漏触发。

#### 6. 是否有术语/分层/LLM-facing 语义错误

- `dayu/fins/README.md` 新增 `read_job_events(job_id, *, after_sequence=0, limit=100) -> tuple[FinsIngestionJobEventRecord, ...]` — 与 `FinsIngestionRuntime.read_job_events(...)` 签名（`ingestion_runtime.py` line 1840-1846）一致。
- `dayu/fins/README.md` 新增 `dayu.fins.ingestion_events` 公共入口描述 — 与 `ingestion_events.py` 的 `__all__`（line 230-237）导出一致。
- `dayu/fins/README.md` event sidecar 路径描述 `<workspace_root>/.dayu/fins_ingestion/jobs` — 与 `ingestion_runtime.py` line 63（`_JOB_EVENT_FILE_SUFFIX = ".events.jsonl"`）和 line 1479（sidecar 路径构造）一致。
- 无 Host/Engine 内部术语泄漏给 LLM-facing 内容；README 使用业务可读语义（"event observation"、"poll terminal fallback"、"durable cancel"）。
- 分层关系正确：Fins job event 是 Fins 自有 sidecar，不属于 Host EventLog；Service 是消费和投影层；CLI 是 UI renderer。

## Open Questions

无。

## Residual Risk

- S6 implementation artifact（`docs/reviews/wu-cli-fins-obs-01-s6-implementation-codex.md`）是 untracked 文件，未纳入 git history。如果需要保留 review 追溯链，应在 S6 commit 中一并提交。
- README 改动无独立测试覆盖，按 docs-only 验证处理。风险低。

## Conclusion

**PASS**

S6 文档改动准确反映 S1-S5 已落地代码事实，正确表达 Fins direct start / event observation / poll terminal fallback / cancel 语义，明确区分 Fins job event sidecar 与 Host EventLog，未遗漏 README 触发，无术语/分层/LLM-facing 语义错误。`dayu/service/README.md` 和 `tests/README.md` 已在 S1-S5 committed 更新中覆盖所需内容，S6 不再修改的理由成立。
