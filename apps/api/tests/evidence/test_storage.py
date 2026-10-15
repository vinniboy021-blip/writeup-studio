# SPDX-License-Identifier: MIT
import io

import pytest
from moto import mock_aws

from app.config import settings
from app.modules.evidence import storage


@pytest.mark.parametrize("key", ["../outside", "/absolute", "folder/../../escape", "folder\\escape", "null\x00key"])
def test_storage_rejects_path_escape(key):
    with pytest.raises(ValueError):
        storage.put_object(key, b"evidence", "text/plain")


def test_local_storage_is_immutable_bounded_and_streamed(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    monkeypatch.setattr(settings, "storage_backend", "local")
    key = "evidences/immutable/original/proof.txt"
    source = b"authentic proof" * 10000
    storage.put_object(key, io.BytesIO(source), "text/plain")
    with pytest.raises(FileExistsError):
        storage.put_object(key, b"overwrite", "text/plain")
    assert b"".join(storage.iter_object(key)) == source
    with pytest.raises(ValueError):
        storage.read_object(key, max_bytes=100)
    assert storage.read_object(key) == source
    storage.delete_object(key)
    with pytest.raises(FileNotFoundError):
        storage.read_object(key)


@mock_aws
def test_s3_private_bucket_put_stream_read_no_overwrite_delete(monkeypatch):
    monkeypatch.setattr(settings, "storage_backend", "s3")
    monkeypatch.setattr(settings, "s3_endpoint_url", "")
    monkeypatch.setattr(settings, "s3_access_key", "testing")
    monkeypatch.setattr(settings, "s3_secret_key", "testing")
    monkeypatch.setattr(settings, "s3_region", "us-east-1")
    monkeypatch.setattr(settings, "s3_bucket", "private-evidences")
    storage._s3_client.cache_clear()
    client = storage.get_client()
    client.create_bucket(Bucket=settings.s3_bucket)
    storage.check_storage()
    data = b"authentic immutable proof" * 10000
    storage.put_object("original/proof.log", io.BytesIO(data), "text/plain")
    assert storage.read_object("original/proof.log") == data
    assert b"".join(storage.iter_object("original/proof.log")) == data
    assert client.get_object_acl(Bucket=settings.s3_bucket, Key="original/proof.log")["Grants"][0]["Permission"] == "FULL_CONTROL"
    assert len(client.get_object_acl(Bucket=settings.s3_bucket, Key="original/proof.log")["Grants"]) == 1
    with pytest.raises(FileExistsError):
        storage.put_object("original/proof.log", b"replace", "text/plain")
    assert storage.read_object("original/proof.log") == data
    with pytest.raises(ValueError):
        storage.read_object("original/proof.log", max_bytes=1)
    storage.delete_object("original/proof.log")
    from botocore.exceptions import ClientError
    with pytest.raises(ClientError):
        storage.read_object("original/proof.log")
    storage._s3_client.cache_clear()
