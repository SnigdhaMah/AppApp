"""
Run the agent locally without AWS (no SQS, DynamoDB, S3).
Loads .env: use OPENAI_API_KEY (or API_KEY) for API-only; optional OPENAI_MODEL=gpt-4o for better code.
Writes generated app to ./output/<job_id>/.
"""
import os
import sys

# Load .env before importing agent (so env vars are set)
from dotenv import load_dotenv
load_dotenv()

# Ensure we don't require AWS env vars
os.environ.setdefault("APPS_BUCKET", "")
os.environ.setdefault("PUBLIC_BASE_URL", "")

from agent import build_app, expand_request, plan_build


def mock_update_job(job_id: str, **kwargs: object) -> None:
    step = kwargs.get("step", "")
    progress = kwargs.get("progress", 0)
    print(f"  [{progress}%] {step}")


def main() -> None:
    prompt = sys.argv[1] if len(sys.argv) > 1 else "Build a simple counter with + and - buttons and display the count."
    job_id = "local-test-1"
    print(f"Prompt: {prompt}\nJob ID: {job_id}\n")
    print("Running agent (expand → plan → build)...")
    try:
        expanded_spec = expand_request(prompt)
        build_plan = plan_build(expanded_spec)
        result_url = build_app(job_id, build_plan, mock_update_job)
        print(f"\nDone. Result: {result_url}")
        print(f"Open: output/{job_id}/index.html in your browser to view the app.")
    except Exception as e:
        print(f"\nError: {e}")
        raise


if __name__ == "__main__":
    main()
