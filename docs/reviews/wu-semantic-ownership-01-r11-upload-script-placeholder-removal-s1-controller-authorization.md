# WU-SEMANTIC-OWNERSHIP-01 / R11-S1 Controller implementation authorization

## 1. Gate verdict

- umbrella：既有 `WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation。
- internal remediation sub-WU：R11；current slice：`R11-S1 — Fins OLD batch classification owner`。
- accepted-plan commit：`f7b452f992b4797b32fea7c6f7212b5ec4345ec1`，parent
  `2b14b2fbc89654267e3d33daa2ae410ceff45e68`，tree
  `dc8f12cefbf5303f36d3d60b5f219f6cf675175a`，exact 12 paths。
- accepted plan：773 lines / 61,810 bytes / SHA-256
  `48bcfbaa648500d16a5148d4d0e4dba34db572a64c90e29ab8083242bd97d025`。
- plan findings：R11-PR-F01—F06 closed；accepted/open 0；blocker 0。
- authorization：`AUTHORIZED FOR R11-S1 IMPLEMENTATION ONLY`。

不授权 S2、S3、cumulative review、stage/commit、R12、push 或 PR。S1 checkpoint 通过后才可另行授权 S2。

## 2. Immutable source locks

| Path | Lines / bytes | SHA-256 |
|---|---:|---|
| `dayu/fins/upload_batch.py` | 376 / 12,000 | `6767d30cfd788e584cef22e5109b1ae0b787ecaedc8581a4cfcf2c49d5ad6178` |
| `tests/fins/test_upload_batch.py` | 187 / 5,914 | `7668bf268eab97f250684cee2ea3cacbca31e6e5a7a02c9605ab90b2b7ea6a69` |

Agent 开始时必须重验 accepted-plan commit、plan hash 和两 source locks；任一漂移立即 stop，不得兼容或猜测。

## 3. Exact write allowlist

S1 只允许修改：

1. `dayu/fins/upload_batch.py`
2. `tests/fins/test_upload_batch.py`
3. Agent evidence
   `docs/reviews/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-s1-implementation-codex.md`

Controller control、plan/review artifacts 与其它 product/test/README/design/workflow 路径全部只读。任何额外 tracked
diff、unrelated untracked path、stage 或 commit 立即 stop。

## 4. Owner contract

Fins 是文件发现、effective recursion、source containment/symlink verdict、fiscal inference、material
routing/name、same-period priority/dedup、caps、typed skips 的唯一 owner。S1 必须产出严格 typed
`UploadBatchPlanRequest`、filing/material/skipped entries 与 plan；不得含 executable、argv、shell、output、JSON
schema、extra payload 或 CLI/Service/Host/Engine/UI import。

必须逐项实现 accepted plan §5.1—§5.3：

- 复用 current suffix owner；stable discovery；structured auto-recursion；lexical/resolved containment；root-self 与
  root 内 symlink rejection；external ancestor allowance。
- filename-first fiscal recognition，只有 direct structured parent 可补齐；explicit fiscal fields 逐字段优先。
- material-first disjoint routing、OLD material form/name；filing same-period priority before caps 与 stable tie-break。
- annual=5、periodic latest-year/max6、presentation=6、call=filtered filing count、zero filing→call cap 0/all typed
  skipped、financial statements uncapped。
- canonical ticker/aliases、action `auto|create|update`、amended/dates/company/overwrite 原样 typed propagation；
  absent 保持 `None/False/()`；empty plan 使用既有 typed error 并保留 skip evidence。

S1 checkpoint 必须按 plan §5.3 的全部 S2 consumer mapping checklist 冻结 fields/enums/optional ownership。不得为
未来 S2 新增 adapter、fallback、loose parsing、兼容 branch、test-only seam 或业务重算。

## 5. Mandatory tests and evidence

在 `source .venv/bin/activate` 后至少执行并记录 exact command/output/exit：

```bash
pytest tests/fins/test_upload_batch.py -q
python -m pytest tests/fins/test_upload_batch.py::test_real_filesystem_builds_typed_old_aligned_plan -q
coverage erase
coverage run -m pytest tests/fins/test_upload_batch.py
coverage json -o workspace/tmp/r11-s1-coverage.json
python -m pyright dayu/ tests/ utils/
python -m ruff check dayu/fins/upload_batch.py tests/fins/test_upload_batch.py
python -m ruff --version
python -m ruff check dayu tests utils --output-format json
git diff --check f7b452f992b4797b32fea7c6f7212b5ec4345ec1
```

Coverage 必须从 JSON 读取 `dayu/fins/upload_batch.py` 普通 line
`summary.percent_covered >= 80.00`。Focused/smoke 不得 mock scanner；real filesystem 只写
`workspace/tmp/r11-s1-smoke`。Full pyright 必须零新增/扩散 error；target Ruff 必须零。

## 6. Ruff baseline lock

Controller 已在 accepted-plan clean tree、激活 `.venv` 后运行：

- version oracle：`ruff 0.15.11`
- full command exit：1（existing baseline findings）
- `workspace/tmp/r11-ruff-baseline.json`：3,825 lines / 99,599 bytes / 144 findings；SHA-256
  `051bd6cc84fcd32adbd792c81c9e524438dd0532a92c7504ea2edf8234ec1cea`
- sorted tuple `(relative filename, code, row, column, message)` SHA-256：
  `0d6b46d6a2ef94ac0af549698bfe96d299a9f0c00710cd60e7be9bde06bb4817`

Agent 必须先逐字匹配 version oracle，再把 current full JSON 与该 baseline 做 exact set difference；current-only 必须
为空。若版本漂移立即 stop 交 Controller 同树重锁，不得用 noqa、exclusion、baseline 更新或只看 exit code 掩盖 finding。

## 7. README/security/deferred and stop gates

- 阅读 `dayu/fins/README.md` 与 `tests/README.md` 的 Agent 更新约束；S1 不修改 README，最终用户同步留在同一
  R11-S3 allowlist，不创建 residual。
- 证明 Fins production 零 `dayu.cli/service/host/engine/ui` import，零 renderer/argv/output/public JSON protocol；
  typed reason 与业务事实仍由 S1 owner 产生。
- 不修改 storage/revision/snapshot、Service/runtime、FMP resolver、ticker normalization、design docs、constraints、
  Issue 142/151/175/177/178、R12、Topic 8/9 或统一 authorization。
- 若 OLD rule 无法映射 current typed fact、suffix owner 冲突、需要上层 classifier、containment 无法在 Fins
  boundary 保证、coverage/type/lint/test 失败或 diff 超出 exact allowlist，立即 stop 并留直接证据。

## 8. Handoff

Agent evidence 必须包含 source/final locks、exact diff manifest、owner field/enum/optional checklist、tests/smoke/
coverage/pyright/Ruff baseline delta、README trigger、security/deferred scans、workspace/staged 状态和所有 stop
condition verdict。不得 stage/commit；结束标记：`READY_FOR_CONTROLLER_S1_CHECKPOINT_VALIDATION`。

AUTHORIZED_FOR_R11_S1_IMPLEMENTATION
