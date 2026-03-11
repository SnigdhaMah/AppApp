"""Upload generated app files to S3 with correct Content-Type."""
import os
import boto3

s3 = boto3.client("s3")

CT = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
}


def upload_folder_to_s3(folder: str, bucket: str, prefix: str) -> None:
    for root, _, files in os.walk(folder):
        for name in files:
            path = os.path.join(root, name)
            rel_path = os.path.relpath(path, folder)
            ext = os.path.splitext(name)[1].lower()
            content_type = CT.get(ext, "application/octet-stream")
    
            # Convert Windows backslashes to forward slashes for S3 keys
            key = prefix + rel_path.replace(os.sep, "/")
            s3.upload_file(
                path,
                bucket,
                key,
                ExtraArgs={"ContentType": content_type},
            )
