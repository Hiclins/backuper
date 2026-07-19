"""S3Backend tests (backends/s3.py) — CONSTRUCTOR-ONLY, per project decision.

No moto, no mocked/real API calls to upload/download/list/delete/exists.
Only construction/validation logic is covered here.
"""

from __future__ import annotations

import sys

import pytest

from backuper.backends.s3 import S3Backend
from backuper.errors import BackendError


def test_missing_boto3_raises_backend_error(monkeypatch):
    monkeypatch.setitem(sys.modules, "boto3", None)
    with pytest.raises(BackendError):
        S3Backend(name="s3", bucket="mybucket")


def test_missing_bucket_raises_before_client_construction():
    with pytest.raises(BackendError):
        S3Backend(name="s3", bucket="")


def test_successful_construction_no_network_call():
    backend = S3Backend(name="mys3", bucket="mybucket", storage_class="GLACIER")
    assert backend.name == "mys3"
    assert backend.bucket == "mybucket"
    assert backend.storage_class == "GLACIER"


def test_prefix_normalization_strips_slashes():
    backend = S3Backend(name="s3", bucket="b", prefix="/myprefix/")
    assert backend.prefix == "myprefix"


def test_prefix_empty_stays_empty():
    backend = S3Backend(name="s3", bucket="b", prefix="")
    assert backend.prefix == ""


def test_key_helper_with_prefix():
    backend = S3Backend(name="s3", bucket="b", prefix="myprefix")
    assert backend._key("artifact.tar") == "myprefix/artifact.tar"


def test_key_helper_without_prefix():
    backend = S3Backend(name="s3", bucket="b")
    assert backend._key("artifact.tar") == "artifact.tar"
