"""SQS poll loop: receive job, run agent, update DynamoDB."""
import json
import os
import time
import boto3
from agent import build_app
from botocore.exceptions import ClientError

sqs = boto3.client("sqs")
ddb = boto3.client("dynamodb")

QUEUE_URL = os.environ["QUEUE_URL"]
JOBS_TABLE = os.environ["JOBS_TABLE"]


def update_job(job_id: str, **fields: object) -> None:
    now = int(time.time())
    names = {"#ua": "updatedAt"}
    vals = {":u": {"N": str(now)}}
    expr_parts = ["#ua = :u"]

    for k, v in fields.items():
        name_key = f"#f{k}"
        val_key = f":{k}"
        names[name_key] = k
        expr_parts.append(f"{name_key} = {val_key}")
        if isinstance(v, str):
            vals[val_key] = {"S": v}
        elif isinstance(v, int):
            vals[val_key] = {"N": str(v)}
        elif v is None:
            vals[val_key] = {"S": ""}
        else:
            vals[val_key] = {"S": json.dumps(v)}

    ddb.update_item(
        TableName=JOBS_TABLE,
        Key={"jobId": {"S": job_id}},
        UpdateExpression="SET " + ", ".join(expr_parts),
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=vals,
    )


def run_forever() -> None:
    while True:
        try:
            resp = sqs.receive_message(
                QueueUrl=QUEUE_URL,
                MaxNumberOfMessages=1,
                WaitTimeSeconds=20,
            )
        except ClientError:
            time.sleep(5)
            continue

        msgs = resp.get("Messages", [])
        if not msgs:
            continue

        msg = msgs[0]
        receipt = msg["ReceiptHandle"]
        try:
            payload = json.loads(msg["Body"])
        except (json.JSONDecodeError, KeyError):
            sqs.delete_message(QueueUrl=QUEUE_URL, ReceiptHandle=receipt)
            continue

        job_id = payload.get("jobId")
        prompt = payload.get("prompt", "")
        if not job_id or not prompt:
            sqs.delete_message(QueueUrl=QUEUE_URL, ReceiptHandle=receipt)
            continue

        try:
            update_job(job_id, status="running", step="planning", progress=5)
            result_url = build_app(job_id, prompt, update_job)
            update_job(
                job_id,
                status="complete",
                step="complete",
                progress=100,
                resultUrl=result_url,
            )
            sqs.delete_message(QueueUrl=QUEUE_URL, ReceiptHandle=receipt)
        except Exception as e:
            err_msg = str(e)[:900]
            update_job(
                job_id,
                status="failed",
                step="failed",
                progress=100,
                error=err_msg,
            )
            sqs.delete_message(QueueUrl=QUEUE_URL, ReceiptHandle=receipt)


if __name__ == "__main__":
    run_forever()
