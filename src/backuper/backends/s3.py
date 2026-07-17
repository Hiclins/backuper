"""S3 (and S3-compatible) backend.

Credentials resolution order:
  1. inline access_key_id / secret_access_key from the destination config
  2. the standard AWS chain (env vars, ~/.aws/credentials, IAM role)

Prefer (2). `boto3` is imported lazily so the tool runs without it when no S3
destination is configured.
"""

from __future__ import annotations

from pathlib import Path

from ..errors import BackendError
from .base import Backend


class S3Backend(Backend):
    def __init__(
        self,
        name: str,
        bucket: str,
        prefix: str = "",
        storage_class: str | None = None,
        region: str | None = None,
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
        endpoint_url: str | None = None,
    ) -> None:
        try:
            import boto3  # noqa: PLC0415 - lazy import, optional dependency
        except ImportError as exc:
            raise BackendError(
                "boto3 is required for S3 destinations: pip install 'backuper[s3]'"
            ) from exc

        if not bucket:
            raise BackendError(f"[{name}] s3 destination requires 'bucket'")

        self.name = name
        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self.storage_class = storage_class

        session = boto3.session.Session(
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            region_name=region,
        )
        self.client = session.client("s3", endpoint_url=endpoint_url)

    def _key(self, name: str) -> str:
        return f"{self.prefix}/{name}" if self.prefix else name

    def _extra_args(self) -> dict:
        return {"StorageClass": self.storage_class} if self.storage_class else {}

    def upload(self, local: Path, name: str) -> None:
        try:
            self.client.upload_file(
                str(local), self.bucket, self._key(name), ExtraArgs=self._extra_args()
            )
        except Exception as exc:  # botocore raises many error types
            raise BackendError(f"[{self.name}] upload {name}: {exc}") from exc

    def download(self, name: str, local: Path) -> None:
        try:
            self.client.download_file(self.bucket, self._key(name), str(local))
        except Exception as exc:
            raise BackendError(f"[{self.name}] download {name}: {exc}") from exc

    def list(self) -> list[str]:
        names: list[str] = []
        token: str | None = None
        base = f"{self.prefix}/" if self.prefix else ""
        try:
            while True:
                kwargs = {"Bucket": self.bucket, "Prefix": base}
                if token:
                    kwargs["ContinuationToken"] = token
                resp = self.client.list_objects_v2(**kwargs)
                for obj in resp.get("Contents", []):
                    key = obj["Key"]
                    names.append(key[len(base):] if base else key)
                if not resp.get("IsTruncated"):
                    break
                token = resp.get("NextContinuationToken")
        except Exception as exc:
            raise BackendError(f"[{self.name}] list: {exc}") from exc
        return [n for n in names if n]

    def delete(self, name: str) -> None:
        try:
            self.client.delete_object(Bucket=self.bucket, Key=self._key(name))
        except Exception as exc:
            raise BackendError(f"[{self.name}] delete {name}: {exc}") from exc

    def exists(self, name: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=self._key(name))
            return True
        except Exception:
            return False
