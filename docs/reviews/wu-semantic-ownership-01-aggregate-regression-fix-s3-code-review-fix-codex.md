# WU-SEMANTIC-OWNERSHIP-01 Aggregate Regression Fix Slice 3 Code Review Fix — AgentCodex Zero-Change Record

## 1. Gate identity 与结论

- 日期：`2026-07-19`。
- Umbrella / slice：既有 `WU-SEMANTIC-OWNERSHIP-01` aggregate regression fix Slice 3；不是新 WU 或新 slice。
- Gate：`code review -> fix -> re-review` 链中的 mandatory `fix` record。
- Branch：`phaseflow/host-issues-control`。
- Accepted base / HEAD：`9ad5711e20dd35d5a0cdc0cf79067333ff3b3daf`。
- Controller verdict：`PASS / MATERIAL_FINDING=0 / ACCEPTED_FIX=0 / ZERO_CHANGE_RECORD_REQUIRED`。
- 本记录结论：`ZERO_CHANGE_FIX_RECORDED / STOPPED_FOR_CONTROLLER_VALIDATION`。
- 唯一 write allowlist：本 artifact。
- Artifact path：`docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-code-review-fix-codex.md`。

两路完整 code review 均为 `PASS`，Controller final ledger 明确 material finding、needs-more-evidence、
blocking question 与 accepted current fix 全部为零。第一性原理上不存在可修的 product/test/README defect；
任何“顺手优化”都会越过已确认的 owner boundary 或改写受保护 target。因此本 gate 只新增本 zero-change
record，没有修改 production、tests、README、accepted plan、control、implementation、Controller/reviewer
artifact，也没有 stage、commit、push 或进入 aggregate。

## 2. Controller 对全部 reviewer 意见的 disposition

| 来源 / ID | Reviewer 意见 | Controller disposition | 本 gate 动作 |
|---|---|---|---|
| MiMo F-01 | `_build_markers(marked_text)` 重复计算，可考虑缓存/复用 | `REJECTED_AS_FINDING / NON_BLOCKING PERFORMANCE_OBSERVATION` | 不缓存、不扩接口。相同不可变输入上的既有 deterministic owner 没有产生第二业务真源，也没有行为或资源失败证据。 |
| MiMo F-02 | publication dict 是浅拷贝，可考虑深拷贝 | `REJECTED_AS_FINDING / OWNER-LOCAL_IDENTITY_REQUIRED` | 不深拷贝。list、index 与 mapping 属于同一 owner-private state，必须保持同一 section identity；深拷贝会破坏 identity contract。 |
| DS O01 | `_VirtualHarness` import owner-private typed types | `REJECTED_AS_FINDING / PLAN-AUTHORIZED_OWNER_HARNESS` | 不改 harness。fixture 只构造 owner state，断言经五个 public consumers 与真实 public processor 完成，没有迫使 production 保留兼容分支。 |
| DS O02 | 既有 marker producer 边界存在宽异常捕获 | `REJECTED_AS_CURRENT_FINDING / EVIDENCE-INSUFFICIENT / PROTECTED EXISTING_SAFE-DEGRADE` | 不改既有 producer、`SecProcessor` contract 或异常边界；review 未给出当前合法输入上的可复现业务错误。 |
| DS O03 | unbound base method 被用作 fallback oracle | `NOT_A_FINDING` | 不改 oracle。unbound call 明确绕过 mixin override，取得同一对象的 base truth，用于逐值验证 fallback public contract。 |

最终 ledger：`material finding=0`、`needs-more-evidence=0`、`blocking question=0`、
`accepted fix=0`。上述意见均不得实施，也不形成当前 slice 的未分类 residual。

## 3. 完整 9-path target 与 review locks

固定 review target 为：

```text
dayu/documents/processors/docling_processor.py
dayu/fins/README.md
dayu/fins/processors/sec_form_section_common.py
tests/documents/test_processors.py
tests/fins/test_sec_pipeline_download.py
tests/fins/test_processor_read_consistency.py
tests/fins/test_fins_ingestion_tools.py
tests/host/test_effective_execution_config.py
tests/runtime/test_argparse_exit.py
```

创建本 artifact 前后均以以上固定顺序复算，三个 lock 与 Controller 锁定值逐字节一致：

| Lock | Controller 锁定 SHA-256 | 创建前 | 创建后 | 结论 |
|---|---|---|---|---|
| tracked binary diff | `de39190c66121255ddd69fdb3418b9ad8bca74e455a98ff94f3fe2e9e08fb206` | MATCH | MATCH | PASS |
| 9-path content manifest | `83cddc11fc114531972ad43db8f55080c0f53803d3eed76ddeb93afacf3f8b28` | MATCH | MATCH | PASS |
| 9-path status manifest | `2c7b84432af3b37521b1618a4058bee851f02300adf11df75be1634cf7d21573` | MATCH | MATCH | PASS |

重算口径分别是：accepted base 到完整 9-path target 的 `git diff --binary`；固定顺序的逐文件
SHA-256 manifest；固定 9-path 的 `git status --short` 输出。不是只核对第二缺陷 hunk。

## 4. Protected hashes 与 zero-diff owners

### 4.1 9-path content hashes

下列逐文件内容 SHA-256 在创建本 artifact 前后完全相同：

| Path | SHA-256（before = after） |
|---|---|
| `dayu/documents/processors/docling_processor.py` | `e2ab00fd984a4c27c30254d62ce038fafb91b9bc88d03eb786ad29f27acfd649` |
| `dayu/fins/README.md` | `adcfd166ec7f9ab1c519cf3e8c161092a4a83a2317af7602bbb0c48f37242525` |
| `dayu/fins/processors/sec_form_section_common.py` | `9f66893b6c3c2af2427f02967c16ba1557fb1c5070c58978c9c8de70902c45a2` |
| `tests/documents/test_processors.py` | `4dedb3aceb2886d51427ca58a9a2c07a136072119e14679f5f612aa05e34c65f` |
| `tests/fins/test_sec_pipeline_download.py` | `840feae7b448049c2dd8f53a6b0cd831b883ff9fee26556b9b427a3df060eae6` |
| `tests/fins/test_processor_read_consistency.py` | `0ee788c2139e729f370f5533158519ca6b1968485376c7bb06781456918740c1` |
| `tests/fins/test_fins_ingestion_tools.py` | `6ece9288834ab3953be8880276079a003f58a02629a2230459d728b95ff2f747` |
| `tests/host/test_effective_execution_config.py` | `e3a85caded7bda956e95d5ebd336cd60815ec1d227c134f46a9678d6a96c6acf` |
| `tests/runtime/test_argparse_exit.py` | `3aa607842a96b7425b964f3c030dc2b427e5bba0dd89abc65e20ed7306ce3f3d` |

这同时证明 Docling protected delta、Fins publication owner、三个 entry-hash protected tests、其余
Slice 3 tests 与唯一 README 均未被本 fix gate 改写。

### 4.2 Protected zero-diff owners

相对 accepted base，以下受保护路径创建前后均由 `git diff --exit-code` 证明零 diff：

```text
dayu/documents/processors/base.py
dayu/fins/processors/sec_processor.py
dayu/fins/processors/ten_k_processor.py
dayu/fins/processors/ten_q_processor.py
dayu/fins/processors/bs_ten_k_processor.py
dayu/fins/processors/bs_ten_q_processor.py
```

因此没有修改 marker producer contract、`SecProcessor` unsupported-marker contract 或 10-K/10-Q/BS
subclass 行为。

### 4.3 Evidence-chain hashes

已读取证据在本 gate 前后保持相同：

| Evidence | SHA-256（before = after） |
|---|---|
| accepted plan | `552df22871f3eb07465b971ca3fdf182032f3b2087e27442b0d78a1b7d8acc04` |
| implementation | `32419e2193b285c4543f838d31f321f6272d200fee7061cd1178343494242fbf` |
| implementation Controller validation | `a227e8c1574d908cbe6d819a6cdf1bc53b810d670806780c8966fec188ebe155` |
| MiMo code review | `a7f2f96a2e335cdc5a27da3d2f6b628548a547b456f5282a185077d290835985` |
| DS code review | `dbdb7d728d5f868496250de329e17fe100f798dc09f9c8cbd1f04894a28112e6` |
| Controller adjudication | `48d9b55f3b978ef07a2998734cc21ca1244e9deefe3c6d6724b278078c37b10c` |

上述固定顺序 `sha256sum` 输出的 manifest SHA-256 为
`50cd61ecf2140a8ee4c5aea91e5e25e4c2620fb451b64dea04987e5a7d8dfd1d`，创建前后相同。

## 5. Zero-change 与 working-tree 证据

- 创建前 full `git status --short --untracked-files=all` 为 `17` 条，SHA-256 为
  `f1d27005043c0f36cf89314cd6ce20217f226fe8136a252456a546d3a785efe1`。
- 创建后排除本 artifact 的同一 status 输出仍为 `17` 条、同一 SHA-256；唯一新增 status 是：

```text
?? docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-code-review-fix-codex.md
```

- `git diff --check`：创建前后均 `PASS`，无输出。
- `git diff --cached --name-status`：创建前后均为空；staged tree 为 `EMPTY`。
- 新 artifact 另以 `git diff --no-index --check /dev/null <artifact>` 核对，无 whitespace diagnostic；
  status `1` 只表示新文件相对 `/dev/null` 存在内容差异。
- product、tests、README、plan、control、implementation 与既有 reviewer/Controller artifacts 的内容和
  status 均未因本 gate 改变；没有 stage、commit、push 或 aggregate 动作。

本 gate 未重跑 pytest、coverage、pyright、Ruff、build 或真实 provider。accepted fix 为零，且用户明确要求
只读核验；重复运行这些门禁不会验证任何新增实现。尤其没有追加 Gemini/provider 调用，也没有修改
config/model/key/retry/quota/budget。

## 6. README、residual 与 next gate

- README decision：`NO_UPDATE`。本 gate 无 product/public contract/用户工作流变化；锁定的
  `dayu/fins/README.md` 内容 hash 未变，其它 README 未触碰。
- `S3-STOP-F01` 与 `S3-STOP-F02` 保持 Controller 已接受的完整 review 结论；AR-F05 保持 closed。
- `AR-F06 = RETAINED / UNFIXED / UNWAIVED / CURRENT_NO_FIX`，未修改、未豁免。
- `AR-F07 = PENDING_RELEASE_BLOCKER / REAL_REMOTE_WINDOWS_EVIDENCE`，未用本地证据代签。
- Gemini/provider residual 保持
  `EXPECTED_TEST_ACCOUNT_QUOTA / PROVIDER_ADHERENCE_RESIDUAL / NO_CODE_ACTION / NON_BLOCKING`。
- 当前唯一 next gate：`Controller validation`。Controller validation 前不得启动 final re-review、stage、
  commit、aggregate、push 或 PR。

本 mandatory zero-change fix record 完成后交回 Controller。
