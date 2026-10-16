"""Give the Garage object store what the platform needs: a node with a role, the
access key the backend uses, and the bucket -- through Garage's admin API.

Run at every start by the `storage-init` service. Each step looks first and only
acts on what is missing, so running it again changes nothing.

Settings (environment):
    GARAGE_ADMIN_URL    http://garage:3903
    GARAGE_ADMIN_TOKEN  the admin token Garage was started with
    GARAGE_CAPACITY     space given to the node, e.g. 200G (default 100G)
    S3_ACCESS_KEY       GK followed by 24 hex characters (Garage's key format)
    S3_SECRET_KEY       64 hex characters
    S3_BUCKET           default "anonymized"
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

UNITS = {"K": 10**3, "M": 10**6, "G": 10**9, "T": 10**12}


class Admin:
    def __init__(self, url: str, token: str) -> None:
        self.url, self.token = url.rstrip("/"), token

    def call(self, method: str, path: str, body: dict | None = None, **query) -> dict | None:
        """The JSON answer, or None when Garage says the thing does not exist."""
        q = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in query.items())
        req = urllib.request.Request(f"{self.url}{path}{'?' + q if q else ''}", method=method,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Authorization": f"Bearer {self.token}",
                                              "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                raw = r.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            if e.code == 404 or (e.code == 400 and b"not found" in e.read().lower()):
                return None
            raise


def capacity(text: str) -> int:
    text = text.strip().upper().rstrip("B")
    return int(float(text[:-1]) * UNITS[text[-1]]) if text[-1] in UNITS else int(text)


def wait_for(admin: Admin, seconds: int = 120) -> dict:
    deadline = time.time() + seconds
    while True:
        try:
            return admin.call("GET", "/v2/GetClusterStatus")
        except Exception as e:                      # not listening yet
            if time.time() > deadline:
                raise SystemExit(f"Garage did not answer at {admin.url}: {e}")
            time.sleep(2)


def main() -> int:
    admin = Admin(os.getenv("GARAGE_ADMIN_URL", "http://garage:3903"), os.environ["GARAGE_ADMIN_TOKEN"])
    key, secret = os.environ["S3_ACCESS_KEY"], os.environ["S3_SECRET_KEY"]
    bucket = os.getenv("S3_BUCKET", "anonymized")
    status = wait_for(admin)

    # 1. the node takes a role in the layout -- until then Garage stores nothing
    if not any(n.get("role") for n in status["nodes"]):
        node = status["nodes"][0]["id"]
        admin.call("POST", "/v2/UpdateClusterLayout", {"roles": [
            {"id": node, "zone": "dc1", "capacity": capacity(os.getenv("GARAGE_CAPACITY", "100G")), "tags": []}]})
        version = admin.call("GET", "/v2/GetClusterLayout")["version"]
        admin.call("POST", "/v2/ApplyClusterLayout", {"version": version + 1})
        print(f"storage: node {node[:12]} given a role (layout v{version + 1})")

    # 2. the backend's key, as set in .env -- imported, so the same key survives a rebuild
    if admin.call("GET", "/v2/GetKeyInfo", id=key) is None:
        admin.call("POST", "/v2/ImportKey", {"accessKeyId": key, "secretAccessKey": secret, "name": "platform"})
        print("storage: access key imported")

    # 3. the bucket, readable and writable by that key
    info = admin.call("GET", "/v2/GetBucketInfo", globalAlias=bucket)
    if info is None:
        info = admin.call("POST", "/v2/CreateBucket", {"globalAlias": bucket})
        print(f"storage: bucket {bucket} created")
    if not any(k.get("accessKeyId") == key for k in info.get("keys", [])):
        admin.call("POST", "/v2/AllowBucketKey", {"bucketId": info["id"], "accessKeyId": key,
                                                   "permissions": {"read": True, "write": True, "owner": True}})
        print(f"storage: key allowed on {bucket}")
    print("storage: ready")
    return 0


if __name__ == "__main__":
    sys.exit(main())
