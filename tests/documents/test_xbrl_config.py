"""管理员清单与只读复制 owner 合同；所有文件均为合成机制样本。"""
from __future__ import annotations
from dataclasses import replace
import hashlib
import json
import os
import struct
import zlib
from lzma import LZMAError
from pathlib import Path
from typing import cast
from zipfile import BadZipFile, ZipFile, ZipInfo, ZIP_DEFLATED, ZIP_BZIP2, ZIP_LZMA, ZIP_STORED
import pytest
from dayu.contracts.json_value import JsonValue
from dayu.documents.xbrl_config import (
    XbrlConfigurationError, XbrlConversionConfig,
    load_xbrl_conversion_config, prepare_xbrl_input, verify_prepared_xbrl_input,
)

def _deployment(tmp_path: Path) -> tuple[Path, Path, dict[str, JsonValue]]:
    """参数：独占根；返回：配置、taxonomy、清单；异常：文件系统错误透传。"""
    admin=tmp_path/'admin'; admin.mkdir(mode=0o700)
    taxonomy=admin/'taxonomy'; taxonomy.mkdir(mode=0o700)
    (taxonomy/'issuer.xsd').write_bytes(b'synthetic-not-an-instance')
    with ZipFile(taxonomy/'package.zip','w') as archive:
        archive.writestr('public/',b''); archive.writestr('public/test.xsd',b'synthetic-xsd')
    files: list[JsonValue]=[]
    for path in sorted(taxonomy.iterdir()):
        entries: list[JsonValue] | None=None
        if path.suffix=='.zip':
            with ZipFile(path) as archive:
                entries=[{'relative_path':info.filename,'size_bytes':info.file_size,'sha256':hashlib.sha256(archive.read(info)).hexdigest()} for info in archive.infolist()]
        files.append({'relative_path':path.name,'size_bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'archive_entries':entries})
    manifest: dict[str,JsonValue]={'source_urls':['https://example.org/approved-source'],'acquired_at':'2026-10-02T00:00:00+00:00','license_urls':['https://example.org/license'],'files':files}
    config=admin/'config.json'
    _save_manifest(config,taxonomy,manifest)
    return config,taxonomy,manifest

def _save_manifest(config: Path, taxonomy: Path, manifest: dict[str,JsonValue]) -> None:
    """参数：部署路径和清单；返回：无；异常：写入错误透传。"""
    path=config.parent/'manifest.json'; path.write_text(json.dumps(manifest))
    config.write_text(json.dumps({'taxonomy_root':str(taxonomy),'manifest_path':str(path),'manifest_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}))

def _loaded(config: Path, forbidden: Path) -> XbrlConversionConfig:
    """参数：显式输入；返回：真实 owner 配置；异常：校验错误透传。"""
    value=load_xbrl_conversion_config(config,forbidden); assert value is not None; return value

def test_snapshot_complete_copy_and_worker_reverification(tmp_path: Path) -> None:
    """参数：独占根；返回：无；异常：完整复制及修改拒绝不成立时断言失败。"""
    config,taxonomy,_=_deployment(tmp_path)
    loaded=_loaded(config,tmp_path/'workspace')
    prepared=prepare_xbrl_input(loaded,snapshot_root=tmp_path/'snapshot',writable_root=tmp_path/'work',stream_name='report.xml')
    assert {p.name for p in prepared.taxonomy_snapshot_root.iterdir()}=={p.name for p in taxonomy.iterdir()}
    assert (prepared.taxonomy_snapshot_root/'issuer.xsd').read_bytes()==(taxonomy/'issuer.xsd').read_bytes()
    path=prepared.taxonomy_snapshot_root/'issuer.xsd'; path.chmod(0o600); path.write_bytes(b'tampered')
    with pytest.raises(XbrlConfigurationError): verify_prepared_xbrl_input(prepared)

@pytest.mark.parametrize('mutation',['unknown','missing','relative','overlap','digest','empty','symlink','permissions','manifest-in-root','root-file'])
def test_admin_config_fail_closed(tmp_path: Path, mutation: str) -> None:
    """参数：根与非法配置类别；返回：无；异常：owner 接受非法输入时断言失败。"""
    config,taxonomy,_=_deployment(tmp_path)
    fields=cast(dict[str,JsonValue],json.loads(config.read_text()))
    forbidden=tmp_path/'workspace'
    if mutation=='unknown': fields['extra']='x'
    elif mutation=='missing': del fields['manifest_path']
    elif mutation=='relative': fields['taxonomy_root']='taxonomy'
    elif mutation=='overlap': forbidden=tmp_path
    elif mutation=='digest': fields['manifest_sha256']='0'*64
    elif mutation=='empty': fields['manifest_sha256']=''
    elif mutation=='permissions': taxonomy.chmod(0o777)
    elif mutation=='manifest-in-root': fields['manifest_path']=str(taxonomy/'issuer.xsd')
    elif mutation=='root-file': fields['taxonomy_root']=str(taxonomy/'issuer.xsd')
    else:
        alias=config.parent/'alias.json'; alias.symlink_to(config); config=alias
    if mutation!='symlink': config.write_text(json.dumps(fields))
    with pytest.raises(XbrlConfigurationError): load_xbrl_conversion_config(config,forbidden)

@pytest.mark.parametrize('mutation',['unknown','time','url','urls-empty','urls-duplicate','files-empty','size-bool','sha','absolute','traversal','duplicate','zip-missing','nonzip-entries','zip-duplicate','zip-entry-hash','zip-entry-size','zip-entry-unknown'])
def test_manifest_schema_and_zip_exactness(tmp_path: Path, mutation: str) -> None:
    """参数：根与非法声明；返回：无；异常：错误声明被接受时断言失败。"""
    config,taxonomy,manifest=_deployment(tmp_path)
    files=cast(list[dict[str,JsonValue]],manifest['files']); normal=files[0]; zipped=files[1]
    if mutation=='unknown': manifest['unknown']=False
    elif mutation=='time': manifest['acquired_at']='2026-10-02T00:00:00'
    elif mutation=='url': manifest['source_urls']=['file:///private/secret']
    elif mutation=='urls-empty': manifest['license_urls']=[]
    elif mutation=='urls-duplicate': manifest['license_urls']=['https://example.org/license','https://example.org/license']
    elif mutation=='files-empty': manifest['files']=[]
    elif mutation=='size-bool': normal['size_bytes']=True
    elif mutation=='sha': normal['sha256']='XYZ'
    elif mutation=='absolute': normal['relative_path']='/issuer.xsd'
    elif mutation=='traversal': normal['relative_path']='../issuer.xsd'
    elif mutation=='duplicate': files.append(normal)
    elif mutation=='zip-missing': zipped['archive_entries']=None
    elif mutation=='nonzip-entries': normal['archive_entries']=[]
    else:
        entries=cast(list[dict[str,JsonValue]],zipped['archive_entries'])
        if mutation=='zip-duplicate': entries.append(entries[0])
        elif mutation=='zip-entry-hash': entries[1]['sha256']='0'*64
        elif mutation=='zip-entry-size': entries[1]['size_bytes']=0
        else: entries.pop()
    _save_manifest(config,taxonomy,manifest)
    with pytest.raises(XbrlConfigurationError): _loaded(config,tmp_path/'workspace')

@pytest.mark.parametrize('mutation',['undeclared','missing','tampered','hardlink','symlink','directory-symlink','shared-write','empty-directory'])
def test_copy_input_owner_rejects_mutated_source(tmp_path: Path, mutation: str) -> None:
    """参数：根与复制前变动；返回：无；异常：owner 漏检变动时断言失败。"""
    config,taxonomy,_=_deployment(tmp_path); loaded=_loaded(config,tmp_path/'workspace'); source=taxonomy/'issuer.xsd'
    if mutation=='undeclared': (taxonomy/'extra').write_bytes(b'x')
    elif mutation=='missing': source.unlink()
    elif mutation=='tampered': source.write_bytes(b'T'*len(source.read_bytes()))
    elif mutation=='hardlink': os.link(source,tmp_path/'hardlink')
    elif mutation=='symlink': raw=source.read_bytes(); source.unlink(); target=tmp_path/'target'; target.write_bytes(raw); source.symlink_to(target)
    elif mutation=='directory-symlink': (taxonomy/'alias').symlink_to(tmp_path,target_is_directory=True)
    elif mutation=='empty-directory': (taxonomy/'undeclared-directory').mkdir()
    else: source.chmod(0o666)
    with pytest.raises(XbrlConfigurationError): prepare_xbrl_input(loaded,snapshot_root=tmp_path/'snapshot',writable_root=tmp_path/'work',stream_name='report.xml')

@pytest.mark.parametrize('stream_name',['issuer.xsd','instance.xml'])
def test_reserved_input_names_and_overlap(tmp_path: Path, stream_name: str) -> None:
    """参数：根与冲突名字；返回：无；异常：不拒绝冲突时断言失败。"""
    config,taxonomy,manifest=_deployment(tmp_path)
    if stream_name=='instance.xml':
        (taxonomy/'issuer.xsd').rename(taxonomy/'instance.xml'); cast(list[dict[str,JsonValue]],manifest['files'])[0]['relative_path']='instance.xml'; _save_manifest(config,taxonomy,manifest)
    loaded=_loaded(config,tmp_path/'workspace')
    with pytest.raises(XbrlConfigurationError): prepare_xbrl_input(loaded,snapshot_root=tmp_path/'snapshot',writable_root=tmp_path/'work',stream_name=stream_name)
    with pytest.raises(XbrlConfigurationError): prepare_xbrl_input(loaded,snapshot_root=taxonomy/'snapshot',writable_root=tmp_path/'work2',stream_name='report.xml')

def test_unset_config_is_explicit_none(tmp_path: Path) -> None:
    """参数：工作区；返回：无；异常：未配置值非 None 时断言失败。"""
    assert load_xbrl_conversion_config(None,tmp_path) is None


def test_duplicate_json_field_is_not_silently_replaced(tmp_path: Path) -> None:
    """参数：合成管理员配置；返回：无；异常：重复字段被后值覆盖时断言失败。"""
    config,_,_=_deployment(tmp_path)
    raw=config.read_text(); config.write_text(raw[:-1]+',"manifest_sha256":"'+'0'*64+'"}')
    with pytest.raises(XbrlConfigurationError,match='重复字段'): _loaded(config,tmp_path/'workspace')


_LOCAL_COMPRESSION_OFFSET = 8
_CENTRAL_COMPRESSION_OFFSET = 10
_LOCAL_FLAGS_OFFSET = 6
_CENTRAL_FLAGS_OFFSET = 8
_CENTRAL_VERSION_OFFSET = 6
_CENTRAL_LOCAL_OFFSET = 42
_ZIP64_EXTRA_TAG = 1
_ZIP64_FIELD_SIZE = 8
_ZIP32_MAX = (1 << 32) - 1
_ZIP64_MAX = (1 << 64) - 1
_LOCAL_HEADER_SIZE = 30
_CENTRAL_HEADER_SIZE = 46
_LOCAL_NAME_SIZE_OFFSET = 26
_CENTRAL_SIGNATURE = b'PK\x01\x02'
_UNSUPPORTED_COMPRESSION_METHOD = 99
_UNSUPPORTED_EXTRACT_VERSION = 100
_COMPRESSED_PATCH_FLAG = 1 << 5
_STRONG_ENCRYPTION_FLAG = 1 << 6
_UTF8_FLAG = 1 << 11
_ZIP_INPUT_FAILURES: tuple[tuple[str, type[Exception]], ...] = (
    ('container', BadZipFile), ('crc', BadZipFile),
    ('compression', NotImplementedError), ('version', NotImplementedError),
    ('patched', NotImplementedError), ('strong-encryption', NotImplementedError),
    ('deflate', zlib.error), ('bzip2', OSError), ('lzma', LZMAError),
    ('central-utf8', UnicodeDecodeError), ('local-utf8', UnicodeDecodeError),
    ('truncated-header', BadZipFile),
    ('zip64-offset', OverflowError),
)


def _corrupt_archive(config: Path, taxonomy: Path, manifest: dict[str, JsonValue], *, mutation: str) -> None:
    """参数：真实部署及 ZIP 输入损坏类别；返回：无；异常：未知类别或原 ZIP/清单错误透传。"""
    path=taxonomy/'package.zip'
    compression = {'deflate': ZIP_DEFLATED, 'bzip2': ZIP_BZIP2, 'lzma': ZIP_LZMA}.get(mutation, ZIP_STORED)
    with ZipFile(path, 'w', compression=compression) as archive:
        archive.writestr('public/', b'')
        member = ZipInfo('public/test.xsd')
        member.compress_type = compression
        if mutation == 'zip64-offset':
            member.extra = struct.pack('<HHQ', _ZIP64_EXTRA_TAG, _ZIP64_FIELD_SIZE, _ZIP64_MAX)
        archive.writestr(member, b'synthetic-xsd')
    with ZipFile(path) as archive:
        info = archive.getinfo('public/test.xsd')
    damaged = bytearray(path.read_bytes())
    local = info.header_offset
    central = damaged.rindex(_CENTRAL_SIGNATURE)
    name_size, extra_size = struct.unpack_from('<HH', damaged, local + _LOCAL_NAME_SIZE_OFFSET)
    payload = local + _LOCAL_HEADER_SIZE + name_size + extra_size
    if mutation == 'container': damaged = bytearray(b'not-a-zip-container')
    elif mutation == 'crc': damaged[payload] ^= 1
    elif mutation == 'compression':
        struct.pack_into('<H', damaged, local + _LOCAL_COMPRESSION_OFFSET, _UNSUPPORTED_COMPRESSION_METHOD)
        struct.pack_into('<H', damaged, central + _CENTRAL_COMPRESSION_OFFSET, _UNSUPPORTED_COMPRESSION_METHOD)
    elif mutation == 'version':
        struct.pack_into('<H', damaged, central + _CENTRAL_VERSION_OFFSET, _UNSUPPORTED_EXTRACT_VERSION)
    elif mutation in ('patched', 'strong-encryption', 'central-utf8', 'local-utf8'):
        flag = _COMPRESSED_PATCH_FLAG if mutation == 'patched' else _STRONG_ENCRYPTION_FLAG if mutation == 'strong-encryption' else _UTF8_FLAG
        struct.pack_into('<H', damaged, local + _LOCAL_FLAGS_OFFSET, flag)
        struct.pack_into('<H', damaged, central + _CENTRAL_FLAGS_OFFSET, flag)
        if mutation == 'central-utf8': damaged[central + _CENTRAL_HEADER_SIZE] = 0xff
        elif mutation == 'local-utf8': damaged[local + _LOCAL_HEADER_SIZE] = 0xff
    elif mutation in ('deflate', 'bzip2', 'lzma'):
        # 保持完整 ZIP 索引/size/CRC/清单，只破坏实际压缩流；LZMA 保留 framing 后损坏属性。
        damaged[payload:payload + info.compress_size] = b'\xff' * info.compress_size
        if mutation == 'lzma':
            damaged[payload:payload + 4] = path.read_bytes()[payload:payload + 4]
    elif mutation == 'truncated-header':
        struct.pack_into('<I', damaged, central + _CENTRAL_LOCAL_OFFSET, len(damaged) - 1)
    elif mutation == 'zip64-offset':
        struct.pack_into('<I', damaged, central + _CENTRAL_LOCAL_OFFSET, _ZIP32_MAX)
    else: raise ValueError('未知 ZIP 反例类别')
    raw=bytes(damaged)
    path.write_bytes(raw)
    rows=cast(list[dict[str,JsonValue]],manifest['files'])
    zipped=next(row for row in rows if row['relative_path']=='package.zip')
    zipped['size_bytes']=len(raw);zipped['sha256']=hashlib.sha256(raw).hexdigest()
    _save_manifest(config,taxonomy,manifest)


@pytest.mark.parametrize(('mutation', 'cause_type'), _ZIP_INPUT_FAILURES)
def test_zip_input_errors_have_configuration_owner(tmp_path: Path, mutation: str, cause_type: type[Exception]) -> None:
    """参数：独占目录/真实 ZIP 输入错误/原异常类型；返回：无；异常：归一或原因丢失则失败。"""
    config,taxonomy,manifest=_deployment(tmp_path)
    loaded=_loaded(config,tmp_path/'workspace')
    prepared=prepare_xbrl_input(loaded,snapshot_root=tmp_path/'snapshot',writable_root=tmp_path/'work',stream_name='report.xml')
    _corrupt_archive(config,taxonomy,manifest,mutation=mutation)
    manifest_path=config.parent/'manifest.json'
    updated=replace(loaded,manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest())
    for operation in ('load','prepare','worker'):
        with pytest.raises(XbrlConfigurationError) as error:
            if operation=='load':load_xbrl_conversion_config(config,tmp_path/'workspace')
            elif operation=='prepare':prepare_xbrl_input(updated,snapshot_root=tmp_path/'snapshot2',writable_root=tmp_path/'work2',stream_name='report.xml')
            else:
                raw=(taxonomy/'package.zip').read_bytes();snapshot=prepared.taxonomy_snapshot_root/'package.zip';snapshot.chmod(0o600);snapshot.write_bytes(raw);snapshot.chmod(0o400)
                files=tuple(replace(file,size_bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()) if file.relative_path.name=='package.zip' else file for file in prepared.manifest.files)
                verify_prepared_xbrl_input(replace(prepared,manifest=replace(prepared.manifest,files=files)))
        assert type(error.value.__cause__) is cause_type
        assert str(error.value.__cause__)


@pytest.mark.parametrize('compression', [ZIP_STORED, ZIP_DEFLATED, ZIP_BZIP2, ZIP_LZMA])
def test_supported_zip_streams_remain_valid(tmp_path: Path, compression: int) -> None:
    """参数：独占目录与当前 stdlib 支持压缩；返回：无；异常：正常 ZIP 被错误拒绝则失败。"""
    config,taxonomy,manifest=_deployment(tmp_path)
    path=taxonomy/'package.zip'
    with ZipFile(path,'w',compression=compression) as archive:
        archive.writestr('public/',b'');archive.writestr('public/test.xsd',b'synthetic-xsd')
    row=next(row for row in cast(list[dict[str,JsonValue]],manifest['files']) if row['relative_path']=='package.zip')
    row['size_bytes']=path.stat().st_size;row['sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    _save_manifest(config,taxonomy,manifest)
    loaded=_loaded(config,tmp_path/'workspace')
    prepared=prepare_xbrl_input(loaded,snapshot_root=tmp_path/'snapshot',writable_root=tmp_path/'work',stream_name='report.xml')
    verify_prepared_xbrl_input(prepared)
