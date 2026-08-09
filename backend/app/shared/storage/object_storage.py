from __future__ import annotations

import hashlib
import mimetypes
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Iterator


@dataclass(frozen=True, slots=True)
class StoredObject:
    key: str
    sha256: str
    bytes: int
    content_type: str
    bucket: str | None = None


def _safe_key(key: str) -> str:
    raw = key.replace("\\", "/").lstrip("/")
    path = PurePosixPath(raw)
    if not raw or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("storage key inválida")
    return str(path)


class LocalObjectStorage:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        path = (self.root / _safe_key(key)).resolve()
        if path != self.root and self.root not in path.parents:
            raise ValueError("storage key fora do tenant")
        return path

    def put_bytes(self, key: str, data: bytes, *, content_type: str = "application/octet-stream") -> StoredObject:
        key = _safe_key(key)
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(path)
        return StoredObject(key, hashlib.sha256(data).hexdigest(), len(data), content_type)

    def put_file(self, key: str, source: Path, *, content_type: str | None = None) -> StoredObject:
        key = _safe_key(key)
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        size = 0
        with source.open("rb") as src, path.open("wb") as dst:
            while chunk := src.read(1024 * 1024):
                digest.update(chunk); size += len(chunk); dst.write(chunk)
        return StoredObject(key, digest.hexdigest(), size, content_type or mimetypes.guess_type(source.name)[0] or "application/octet-stream")

    def get_bytes(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def iter_bytes(self, key: str, chunk_size: int = 1024 * 1024) -> Iterator[bytes]:
        with self._path(key).open("rb") as fh:
            while chunk := fh.read(chunk_size):
                yield chunk

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def delete(self, key: str) -> None:
        path = self._path(key)
        if path.exists():
            path.unlink()

    def local_path(self, key: str) -> Path:
        return self._path(key)


class S3ObjectStorage:
    def __init__(self, *, endpoint_url: str, access_key: str, secret_key: str, bucket: str, region: str = "us-east-1"):
        import boto3
        from botocore.config import Config

        self.bucket = bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )

    def ensure_bucket(self) -> None:
        from botocore.exceptions import ClientError
        try:
            self.client.head_bucket(Bucket=self.bucket)
            return
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", ""))
            if code not in {"404", "NoSuchBucket", "NotFound"}:
                raise
        self.client.create_bucket(Bucket=self.bucket)
        # Versionamento e bloqueio de acesso público por padrão.
        self.client.put_bucket_versioning(Bucket=self.bucket, VersioningConfiguration={"Status": "Enabled"})
        try:
            self.client.put_public_access_block(
                Bucket=self.bucket,
                PublicAccessBlockConfiguration={
                    "BlockPublicAcls": True,
                    "IgnorePublicAcls": True,
                    "BlockPublicPolicy": True,
                    "RestrictPublicBuckets": True,
                },
            )
        except Exception:
            # Alguns endpoints S3 compatíveis não implementam esta API; bucket continua privado por ausência de policy.
            pass

    def put_bytes(self, key: str, data: bytes, *, content_type: str = "application/octet-stream") -> StoredObject:
        key = _safe_key(key)
        digest = hashlib.sha256(data).hexdigest()
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
            Metadata={"sha256": digest},
        )
        return StoredObject(key, digest, len(data), content_type, self.bucket)

    def put_file(self, key: str, source: Path, *, content_type: str | None = None) -> StoredObject:
        key = _safe_key(key)
        digest = hashlib.sha256()
        size = 0
        with source.open("rb") as fh:
            while chunk := fh.read(1024 * 1024):
                digest.update(chunk); size += len(chunk)
        ctype = content_type or mimetypes.guess_type(source.name)[0] or "application/octet-stream"
        with source.open("rb") as fh:
            self.client.upload_fileobj(fh, self.bucket, key, ExtraArgs={"ContentType": ctype, "Metadata": {"sha256": digest.hexdigest()}})
        return StoredObject(key, digest.hexdigest(), size, ctype, self.bucket)

    def get_bytes(self, key: str) -> bytes:
        obj = self.client.get_object(Bucket=self.bucket, Key=_safe_key(key))
        return obj["Body"].read()

    def iter_bytes(self, key: str, chunk_size: int = 1024 * 1024) -> Iterator[bytes]:
        obj = self.client.get_object(Bucket=self.bucket, Key=_safe_key(key))
        body = obj["Body"]
        while chunk := body.read(chunk_size):
            yield chunk

    def exists(self, key: str) -> bool:
        from botocore.exceptions import ClientError
        try:
            self.client.head_object(Bucket=self.bucket, Key=_safe_key(key)); return True
        except ClientError as exc:
            if str(exc.response.get("Error", {}).get("Code", "")) in {"404", "NoSuchKey", "NotFound"}:
                return False
            raise

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=_safe_key(key))

    def local_path(self, key: str) -> None:
        return None
