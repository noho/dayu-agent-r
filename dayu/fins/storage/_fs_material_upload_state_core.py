"""材料状态公共读写合同的文件系统 core。"""
from __future__ import annotations
import stat
import sys
from dayu.fins.domain.document_models import BatchToken, CompanyMeta
from dayu.fins.domain.company_meta_contract import CompanyMetaCommitOutcome, CompanyMetaConcurrentUpdateError
from dayu.fins.domain.enums import SourceKind
from dayu.fins.ticker_normalization import normalize_ticker
from ._fs_identity import _require_external_identity
from ._fs_storage_infra import _FsStorageInfra
from .repository_protocols import MaterialUploadPublishedState, CompanyTickerIdentityCorruptionError
from .source_integrity import SourceIntegrityClassification, SourceIntegrityStatus

class _FsMaterialUploadStateMixin(_FsStorageInfra):
    """在单一 publication guard 下读取 material 上传校验状态。"""

    def read_material_upload_state(
        self,
        ticker: str,
        document_id: str,
    ) -> MaterialUploadPublishedState:
        """读取 company meta 与 material source meta 的同版快照。

        Args:
            ticker: 待校验的公司代码。
            document_id: 待校验的 material 文档 ID。

        Returns:
            同一 publication guard 下的 company meta、required integrity 与按状态可用的 source meta。

        Raises:
            CompanyTickerIdentityCorruptionError: published target、descriptor、meta
                或 identity durable state 损坏时抛出。
            ValueError: ticker 或 document identity 非法时抛出；source directory、meta、
                identity descriptor 等可归属 target 的结构损坏返回 ``UNSAFE`` typed state。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: identity descriptor、meta 或其它 published state operational 读取失败时
                抛出 path-free 文件系统异常。
            RuntimeError: exact inspector 未返回 target，或可信状态缺少 business meta 时抛出。
        """

        external_ticker = normalize_ticker(ticker).canonical
        external_document_id = _require_external_identity(
            document_id,
            field_name="document_id",
        )
        core = self
        target_dir = core._target_ticker_dir(external_ticker)
        target_stat = core._lstat_optional_storage_path(
            target_dir,
            action="检查 material upload published ticker directory",
        )
        if target_stat is None:
            return MaterialUploadPublishedState(
                company_meta=None,
                source_integrity=SourceIntegrityClassification(
                    ticker=external_ticker,
                    source_kind=SourceKind.MATERIAL,
                    document_id=external_document_id,
                    revision=None,
                    status=SourceIntegrityStatus.MISSING,
                    reasons=(),
                ),
                source_meta=None,
                publication_identity=None,
            )
        if not stat.S_ISDIR(target_stat.st_mode):
            raise CompanyTickerIdentityCorruptionError(kind="invalid_descriptor")
        guard_token = core._acquire_publication_guard(external_ticker)
        try:
            return core._read_material_state_unguarded(external_ticker, external_document_id, target_dir)
        finally:
            core._release_lock_after_operation(guard_token, primary_error=sys.exception(), action="material state guard release")

    def read_material_upload_state_in_batch(
        self,
        batch: BatchToken,
        document_id: str,
    ) -> MaterialUploadPublishedState:
        """读取 writer-owned staging view 中的同版 material 上传状态。

        Args:
            batch: 同一 core、ticker 且仍 open 的 batch capability。
            document_id: 待校验的 exact material 文档 ID。

        Returns:
            staging view 中同版 company meta、source state 与 publication identity。

        Raises:
            CompanyTickerIdentityCorruptionError: staging ticker descriptor、meta 或 identity
                durable state 损坏时抛出。
            ValueError: capability、ticker 或 document identity 非法时抛出。
            OSError: staging state operational 读取失败时抛出 path-free 异常。
            RuntimeError: exact inspector 缺少 target 或可信状态缺少 business meta 时抛出。
        """

        external_document_id = _require_external_identity(
            document_id,
            field_name="document_id",
        )
        core = self
        state = core._resolve_active_batch(batch, batch.ticker)
        return core._read_material_state_unguarded(state.token.ticker, external_document_id, state.staging_ticker_dir)


    def validate_material_upload_state(self, *, ticker: str, document_id: str, expected_source_state: MaterialUploadPublishedState | None, expected_company_meta: CompanyMeta | None) -> MaterialUploadPublishedState:
        """沿既有锁序校验公司、alias 与显式材料条件。

        Args:
            ticker: 目标公司代码。
            document_id: 目标材料身份。
            expected_source_state: 必填，None 只校验公司与 alias，不代表 MISSING。
            expected_company_meta: 必填的严格公司快照，None 表示公司缺席。
        Returns:
            同一 publication guard 内读取的完整材料状态。
        Raises:
            CompanyMetaConcurrentUpdateError: 公司快照漂移。
            SourceIntegrityRevisionConflictError: 非 None 的材料条件漂移。
            CompanyTickerAliasConflictError: alias 占用。
            OSError: 真实读取、锁或释放失败。
        """
        external_ticker = normalize_ticker(ticker).canonical
        external_document_id = _require_external_identity(document_id, field_name="document_id")
        # 沿既有 recovery→identity→publication 锁序，alias owner 先验证唯一性，不能被材料相同掩盖。
        recovery = self._acquire_recovery_lock()
        try:
            identity = self._acquire_company_identity_guard()
            try:
                index = self._build_unique_company_identity_index(self._scan_actual_published_company_identities())
                if expected_company_meta is not None:
                    self._require_company_lookup_tickers_available(expected_company_meta.ticker_identity.lookup_tickers(), index, external_ticker)
                guard = self._acquire_publication_guard(external_ticker)
                try:
                    fresh = self._read_material_state_unguarded(external_ticker, external_document_id, self._target_ticker_dir(external_ticker))
                    if expected_source_state is None:
                        if fresh.company_meta != expected_company_meta:
                            raise CompanyMetaConcurrentUpdateError()
                    else:
                        self._require_material_state_matches(fresh, expected_source_state, expected_company_meta)
                    return fresh
                finally:
                    self._release_lock_after_operation(guard, primary_error=sys.exception(), action="material validation publication release")
            finally:
                self._release_lock_after_operation(identity, primary_error=sys.exception(), action="material validation identity release")
        finally:
            self._release_lock_after_operation(recovery, primary_error=sys.exception(), action="material validation recovery release")

    def register_material_upload_preconditions(self, *, batch: BatchToken, expected_source_state: MaterialUploadPublishedState, expected_company_meta: CompanyMeta | None) -> None:
        """为材料写入登记完整的源与公司条件。

        Args:
            batch: 同一仓储且仍 open 的材料写入 batch。
            expected_source_state: 必填的 MaterialUploadPublishedState 完整材料状态，不允许 None。
            expected_company_meta: 严格公司快照，None 表示公司缺席。
        Returns:
            无返回值；校验成功后登记条件。
        Raises:
            TypeError: expected_source_state 不是 MaterialUploadPublishedState 类型。
            ValueError: batch capability 非法、重复登记或材料身份非法。
            CompanyMetaConcurrentUpdateError: 公司快照漂移。
            SourceIntegrityRevisionConflictError: 材料条件漂移。
            CompanyTickerIdentityCorruptionError: staging 公司身份或元数据损坏。
            OSError: staging 状态读取失败。
            RuntimeError: 材料检查结果缺少目标或可信业务元数据。
        """
        if not isinstance(expected_source_state, MaterialUploadPublishedState):
            raise TypeError("expected_source_state 必须是 MaterialUploadPublishedState 类型的完整材料状态")
        state = self._resolve_active_batch(batch, batch.ticker)
        if state.material_preconditions is not None:
            raise ValueError("材料条件不得重复登记")
        fresh = self.read_material_upload_state_in_batch(batch, expected_source_state.source_integrity.document_id)
        self._require_material_state_matches(fresh, expected_source_state, expected_company_meta)
        state.material_preconditions = (expected_source_state, expected_company_meta)

    def commit_material_upload_batch(self, batch: BatchToken) -> MaterialUploadPublishedState:
        """参数：已登记材料 batch；返回：guard 内形成且完整释放后的 final；异常：提交/释放失败，不重试。"""
        state = self._resolve_active_batch(batch, batch.ticker)
        if state.material_preconditions is None or state.company_meta_intent is not None:
            raise ValueError("材料提交必须已登记条件且不混入公司 intent")
        self.commit_batch(batch)
        if state.material_final is None or state.material_final.source_integrity.status is not SourceIntegrityStatus.COMPLETE:
            raise RuntimeError("材料提交缺可信 final")
        return state.material_final

    def commit_material_upload_company_batch(self, batch: BatchToken) -> CompanyMetaCommitOutcome:
        """参数：独立公司 intent batch；返回：公司 final，等价时零 swap；异常：公司/alias/锁/I/O。"""
        state = self._resolve_active_batch(batch, batch.ticker)
        if state.company_meta_intent is None or state.material_preconditions is not None:
            raise ValueError("材料公司阶段必须含单独 company intent")
        state.material_company_stage = True
        outcome = self.commit_batch(batch)
        if outcome is None:
            raise RuntimeError("材料公司提交缺 final")
        return outcome
