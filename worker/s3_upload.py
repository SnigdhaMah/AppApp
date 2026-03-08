"""Upload generated app files to S3 with correct Content-Type."""
import os
import boto3

s3 = boto3.client("s3")

CT = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
}


def upload_folder_to_s3(folder: str, bucket: str, prefix: str) -> None:
    for name in os.listdir(folder):
        path = os.path.join(folder, name)
        if not os.path.isfile(path):
            continue
        ext = os.path.splitext(name)[1].lower()
        content_type = CT.get(ext, "application/octet-stream")

        key = prefix + name
        s3.upload_file(
            path,
            bucket,
            key,
            ExtraArgs={"ContentType": content_type},
        )
