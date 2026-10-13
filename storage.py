from __future__ import annotations
import os, uuid
from pathlib import Path


def status() -> dict:
    backend=os.getenv("STORAGE_BACKEND","local").strip().lower() or "local"
    return {
        "backend": backend,
        "bucket": os.getenv("S3_BUCKET",""),
        "region": os.getenv("S3_REGION",""),
        "endpoint": os.getenv("S3_ENDPOINT_URL",""),
        "configured": backend=="local" or bool(os.getenv("S3_BUCKET") and os.getenv("AWS_ACCESS_KEY_ID") and os.getenv("AWS_SECRET_ACCESS_KEY")),
    }


def upload_file(path: Path) -> dict:
    cfg=status()
    if cfg["backend"]=="local":
        return {"backend":"local","url":f"/api/files/{path.name}","key":path.name}
    if cfg["backend"]!="s3":
        raise RuntimeError("Unsupported storage backend")
    if not cfg["configured"]:
        raise RuntimeError("S3 storage is not fully configured")
    try:
        import boto3
    except ImportError as e:
        raise RuntimeError("boto3 is required for S3 storage") from e
    client=boto3.client(
        "s3",
        region_name=cfg["region"] or None,
        endpoint_url=cfg["endpoint"] or None,
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    )
    key=f"voicelab/{uuid.uuid4().hex}/{path.name}"
    client.upload_file(str(path), cfg["bucket"], key)
    public_base=os.getenv("S3_PUBLIC_BASE_URL","").rstrip("/")
    if public_base:
        url=f"{public_base}/{key}"
    else:
        url=client.generate_presigned_url("get_object",Params={"Bucket":cfg["bucket"],"Key":key},ExpiresIn=86400)
    return {"backend":"s3","url":url,"key":key,"bucket":cfg["bucket"]}
