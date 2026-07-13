# R3-E Slice S3 Code Review Fix Artifact（AgentCodex）

## 1. Gate / decision

- Work unit：`WU-SEMANTIC-OWNERSHIP-01`
- Slice：`R3-E S3`
- Gate：accepted code-review findings fix
- Controller adjudication：`docs/reviews/wu-semantic-ownership-01-round3-r3-e-s3-code-review-controller-adjudication.md`
- Decision：**COMPLETE — F01 至 F09 全部已修复，等待独立 code re-review**
- Artifact path：`docs/reviews/wu-semantic-ownership-01-round3-r3-e-s3-code-review-fix-codex.md`

本 fix 仅处理 controller 已接受的 S3 findings。未 commit、未 push，未自行进入 re-review；未修改 S4 Documents、Host/Engine/Fins、`web_egress_policy.py`，也未实施通用 tool-security。

## 2. First-principles judgment

accepted findings 的动机成立：

- LLM-facing success payload 是 `final_url` 对外语义 owner 的最后边界；即使内部 requests/Playwright producer 需要 raw navigation URL，工具成功返回前也必须统一经过 safe URL projection。
- `_raise_fetch_failure` 的任意 dict 参数如果不参与 owner projection，就是虚假契约；保留它会让 caller 误以为诊断已持久化。正确修复是删除参数和无效构造，仅让 failure owner 产生封闭 projection，而不是把任意下游 dict 合并进去。
- `os.replace` 是 temp 到 final 的真实状态迁移点；`published` 必须紧随该迁移更新，否则后续 chmod 失败会让 cleanup 看见错误状态。
- storage directory helper 只拥有最终 storage dir 的 privacy mode，不拥有调用方的中间路径权限。
- HEAD method negative control 是 method/token classifier 的独立反例；如果 ledger gap 不要求它，handler 的 method 拒绝路径可以回归而 PASS 不受影响。
- challenge-control 是反向 oracle，必须同时锁定“普通 case 不得 confirmed”和“control case 必须 confirmed”。
- HEAD probe 不消费 response body contract，计算未使用 body digest 没有语义 owner，也增加无意义 materialization。

没有引入新 framework、兼容分支或下游 fallback；每项修复均落在对应 semantic owner 或 owner contract test。

## 3. Changed files in this fix

| 文件 | fix 内容 |
| --- | --- |
| `dayu/tools/web/web_tools.py` | F01：requests/Playwright 成功 payload 的 `final_url` 统一 safe projection。F02：删除 `_raise_fetch_failure.internal_diagnostics` 参数、所有无效 call-site dict 与只为该 dict 计算的局部状态；`ToolBusinessError.internal_diagnostics` 只接收 owner 的 `failed_projection().to_json()`。 |
| `dayu/tools/web/web_fetch_orchestrator.py` | F09：删除 HEAD content-type probe 中未使用的 body diagnostic 计算；main response 的 origin bytes digest 保留。 |
| `utils/diagnose_web_access.py` | F03/F08：`os.replace` 后立即设置 `published=True`，再执行 final chmod。F06：中间父目录按默认 umask 创建，只创建/chmod 最终 storage dir 为 `0700`。 |
| `utils/smoke_web_ci.py` | F05：pre-child 增加 HEAD negative control，ledger gap 强制要求 `NEGATIVE_METHOD`；HEAD observation digest 按实际未发送 body 的空 bytes 记录。 |
| `tests/tools/web/test_web_tools_provider.py` | F01/F02：覆盖 requests/Playwright LLM-facing `final_url` 删除 userinfo/query/fragment；锁定 `_raise_fetch_failure` 不再接受 arbitrary diagnostics，且 error 只携带 owner projection。 |
| `tests/tools/web/test_diagnose_web_access.py` | F03/F04/F06/F08：新增 post-replace chmod failure、private directory 新建/已有合法/非法 mode/非目录、nested intermediate permissions owner tests。 |
| `tests/tools/web/test_smoke_web_ci.py` | F05/F07：synthetic ledger 缺 HEAD method negative 必须失败；challenge-control 的 missing/none/suspected decision 均必须失败。 |
| `tests/README.md` | 按 tests README 职责更新 local smoke negative-control matrix，加入 HEAD-method。 |
| `docs/reviews/wu-semantic-ownership-01-round3-r3-e-s3-code-review-fix-codex.md` | 本 fix artifact。 |

`dayu/tools/web/web_diagnostics.py`、`dayu/tools/web/web_playwright_backend.py` 与其余 S3 implementation changes 未因本 fix 扩展；它们仍属于当前未提交 S3 工作区，但本批 findings 不需要额外修改。

## 4. Finding closure

| Finding | 状态 | Direct evidence / assertion |
| --- | --- | --- |
| `R3-E-S3-CR-F01` | **已修复** | `web_tools._build_playwright_success_payload()` 和 requests success payload 均调用 `project_safe_url_or_empty`。tests 用含 userinfo、256-bit query token、fragment 的 raw final URL，断言 LLM-facing `final_url == https://example.com/report` 且 secret 零命中。 |
| `R3-E-S3-CR-F02` | **已修复** | `_raise_fetch_failure` 签名不再含 `internal_diagnostics`；所有 call-site arbitrary dict 已删除。唯一 `internal_diagnostics=` 是 failure owner 把 `projection.to_json()` 写入 `ToolBusinessError`，没有合并 downstream dict。测试用 `inspect.signature` 锁定该契约。 |
| `R3-E-S3-CR-F03` | **已修复** | `_StorageStateLifecycle.publish()` 的顺序为 `os.replace -> temp_path=None -> published=True -> chmod(final)`。post-replace chmod failure 测试证明状态为 published，随后 `cleanup_failure()` 删除 final 并复位状态。 |
| `R3-E-S3-CR-F04` | **已修复** | owner contract tests 分别覆盖新目录创建为 `0700`、已有 `0700` 原样接受、已有非 `0700` fail closed、普通文件占用路径 fail closed。 |
| `R3-E-S3-CR-F05` | **已修复** | `_exercise_pre_child_negative_controls()` 在 child 前发送 valid-token HEAD；handler 记录 rejected `NEGATIVE_METHOD`；`_fixture_ledger_gap()` 把该 kind 纳入 required set。live fixture lifecycle test 与 synthetic missing-method ledger test 同时覆盖。 |
| `R3-E-S3-CR-F06` | **已修复** | helper 先对 `path.parent.mkdir(parents=True, exist_ok=True)` 使用普通默认权限，再只对 leaf `path.mkdir(mode=0700)` / chmod。nested path test 在确定性 `umask 022` 下断言 intermediates 为 `0755`、leaf 为 `0700`。 |
| `R3-E-S3-CR-F07` | **已修复** | 新参数化 test 对 challenge-control 分别删除 decision、设置 `none`、设置 `suspected`，均断言 `failed / challenge_control_failed`。 |
| `R3-E-S3-CR-F08` | **已修复** | 与 F03 同一 post-replace direct test 覆盖，不再只有 replace-before-publication failure。 |
| `R3-E-S3-CR-F09` | **已修复** | HEAD probe 不再读取 `response.content` 或计算 `content_diagnostic_from_bytes`；未新增 probe response 字段。剩余 origin body digest 计算只位于 main fetch producer，是 S3 exact-content artifact contract 所需。 |

## 5. Validation

| 命令 | 结果 |
| --- | --- |
| `source .venv/bin/activate && pytest tests/tools/web/test_web_tools_provider.py -q -k "diagnostic or fetch or final_url or failure"` | PASS：32 passed，92 deselected。 |
| `source .venv/bin/activate && pytest tests/tools/web/test_diagnose_web_access.py -q` | PASS：35 passed。 |
| `source .venv/bin/activate && pytest tests/tools/web/test_smoke_web_ci.py -q` | PASS：40 passed；3 条既有 edgar deprecation warnings。 |
| `source .venv/bin/activate && pytest tests/tools/web -q` | PASS：197 passed，2 skipped；3 条既有 edgar deprecation warnings。 |
| `source .venv/bin/activate && pyright` | PASS：0 errors，0 warnings，0 informations。另有 pyright 新版本提示，不是代码错误。 |
| `source .venv/bin/activate && git diff --check` | PASS。 |

### Scope scan

`git status --short`、`git diff --name-only` 与 untracked-file scan 只显示当前 S3 production/consumer/tests/README 以及 S3 implementation/controller/review/fix artifacts。没有 S4 Documents、Host/Engine/Fins、`web_egress_policy.py` 或 tool-security implementation change。

## 6. README decision

本 fix 新增测试并扩展 local smoke negative-control contract，命中 `tests/README.md` 触发规则。目标 README 没有独立 `Agent 更新约束` 章节；按其“只记录当前 tests 分层、运行方式与维护约定”的既有职责，仅把负控清单从 missing/wrong/replay/unknown-path 更新为 missing/wrong/HEAD-method/replay/unknown-path。未触发其他 README。

## 7. Residual risks / uncovered areas

| 分类 | 项目 | owner / destination |
| --- | --- | --- |
| fixed in current slice | F01–F09 全部 accepted findings。 | 上述 owner 与 direct tests；无剩余 accepted finding。 |
| assigned to later work unit | SIGKILL/主机崩溃无法保证 Python 即时 cleanup，可能保留到下次 startup/TTL。 | 沿用 accepted S3 contract：`utils/diagnose_web_access.py` startup reconciliation + TTL；若产品要求无下次启动也强制清理，进入独立 secure-artifact cleanup WU。本 fix 不伪造保证。 |
| covered by current accepted boundary | digest 对低熵正文不构成机密保护；敏感 header value 不计算 digest。 | 沿用 `dayu.tools.web.web_diagnostics` 最小披露 contract；未被本 fix 改变。 |
| covered by current accepted boundary | external live URL/search provider 继续是 diagnostic-only。 | `utils/smoke_web_ci.py`；不作为 local hard PASS oracle。 |

没有新增 unclassified residual risk、deferred finding 或 blocking open question。

## 8. Explicit exclusions / next entry point

- 无 S4 Documents / `dayu.tools.doc_tools` / `dayu.documents`。
- 无 Host、Engine、Fins 修改。
- 无 `dayu/tools/web/web_egress_policy.py` 修改或 egress policy 扩展。
- 无通用 tool-security、upload allowlist、SSRF/TLS framework、symlink-safe upload 或 LLM-facing security schema。
- 无 commit、push、aggregate 或 final closeout。
- 当前 next entry point：由 controller 安排 **R3-E S3 code re-review**；本 Agent 未自行进入该 gate。

