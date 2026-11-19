"""In-memory BlobStorage; signed URLs are fake and carry the ttl so tests can assert it."""

from app.ports.blob_storage import BlobStorage


class FakeBlobStorage:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], tuple[bytes, str]] = {}
        self.signed: list[tuple[str, str, int]] = []
        self.fail_put = False

    def put(self, bucket: str, path: str, data: bytes, content_type: str) -> None:
        if self.fail_put:
            raise RuntimeError("put failed")
        self.objects[(bucket, path)] = (data, content_type)

    def signed_url(self, bucket: str, path: str, ttl_s: int) -> str:
        self.signed.append((bucket, path, ttl_s))
        return f"https://signed.test/{bucket}/{path}?ttl={ttl_s}"

    def delete_prefix(self, bucket: str, prefix: str) -> int:
        keys = [k for k in self.objects if k[0] == bucket and k[1].startswith(prefix)]
        for k in keys:
            del self.objects[k]
        return len(keys)


_conforms: BlobStorage = FakeBlobStorage()
