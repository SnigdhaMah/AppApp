# Build Apps (MVP)

Web app that turns a text prompt into a generated static web app: you describe what you want, a worker (Fargate) uses an LLM to generate HTML/CSS/JS, uploads to S3, and the frontend shows the result in an iframe.

**Stack:** Next.js frontend → API Gateway → Lambdas (create job, get job) → DynamoDB + SQS → ECS Fargate worker (agent) → S3. Generated apps are served from S3.

---


**Start here:**

- **Linux / macOS:** [macguide.md](macguide.md) (bash-only)
- **All platforms (incl. Windows):** [guide.md](guide.md)

They cover:

1. Logging into the team AWS account (`aws configure`)
2. Cloning the repo and installing dependencies
3. Running the frontend and agent locally
4. Making changes (frontend vs agent)
5. Deploying agent changes (build image → push to ECR → update ECS)

**Testing the full stack:** [TESTING.md](TESTING.md) (API URL, worker API key, end-to-end test).

---

## Repo layout

| Folder    | Purpose |
|-----------|--------|
| `frontend/` | Next.js app (prompt input, Build button, job status, iframe preview). |
| `worker/`   | Python agent: SQS poll, LLM (OpenAI/Gemini/Codex), validate, S3 upload. `build-and-push.sh` / `build-and-push.ps1` build and push the Docker image. |
| `backend/`  | Lambdas: CreateJob (POST /jobs), GetJob (GET /jobs/{id}). |
| `infra/`    | CDK stack: DynamoDB, SQS, S3, Lambdas, API Gateway, ECS Fargate, IAM. |

---

## Requirements

- Node.js 18+, Python 3.11+, Docker, AWS CLI. See [guide.md](guide.md) for details.
