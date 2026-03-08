# Contributing (Linux / macOS)

This guide is for **Linux and macOS** only. It explains how to use the shared AWS account and how to make and deploy changes to the frontend and agent. For **Windows**, use [CONTRIBUTING.md](CONTRIBUTING.md).

---

## What you need installed

- **Git** – clone and push code
- **Node.js 18+** – frontend and infra
- **Python 3.11+** – agent (local runs/tests)
- **Docker** – build and push the worker image
- **AWS CLI v2** – [Install](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)

You’ll need **AWS credentials** (access key + secret) and **stack details** (API URL, region, ECR URI, ECS cluster/service names). Whoever set up the project can share these with the group, or you can find them in the AWS Console (see [Stack details](#where-to-find-stack-details)).

---

## Step 1: Log into the shared AWS account

### 1.1 Get your credentials

Someone on the project (who has AWS access) can create an **IAM user** for you and share:

1. **Access key ID** (e.g. `AKIA...`)
2. **Secret access key** (one-time; store it safely and don’t commit it)

If several people use the same account, use a **profile name** (e.g. `build-apps`) so you don’t overwrite each other’s config.

### 1.2 Configure the AWS CLI

```bash
aws configure
```

Enter when prompted:

| Prompt | What to enter |
|--------|----------------|
| **AWS Access Key ID** | Your access key |
| **AWS Secret Access Key** | Your secret key |
| **Default region name** | `us-east-2` (or whatever region the stack uses) |
| **Default output format** | `json` (or leave blank) |

With a **named profile** (good when sharing one account):

```bash
aws configure --profile build-apps
```

Then use `--profile build-apps` (or `export AWS_PROFILE=build-apps`) for AWS commands in this guide.

### 1.3 Verify

```bash
aws sts get-caller-identity
```

With a profile:

```bash
aws sts get-caller-identity --profile build-apps
```

You should see your account ID and user ARN.

---

## Step 2: Get the code and install dependencies

### 2.1 Clone

```bash
git clone <repository-url>
cd app
```

Replace `<repository-url>` with the real Git URL.

### 2.2 Frontend

```bash
cd frontend
npm install
cd ..
```

### 2.3 Agent (optional, for local runs)

```bash
cd worker
pip install -r requirements.txt
# or: python3 -m pip install -r requirements.txt
cd ..
```

### 2.4 Infra (only if you run CDK)

```bash
cd infra
npm install
cd ..
```

---

## Step 3: Run the frontend locally

```bash
cd frontend
cp .env.example .env.local
```

Edit `frontend/.env.local` and set (no trailing slash):

```bash
NEXT_PUBLIC_API_URL=https://YOUR_API_URL/prod
```

Start the dev server:

```bash
npm run dev
```

Open **http://localhost:3000**. The UI hot-reloads when you edit `frontend/app/`.

---

## Step 4: Run the agent locally (optional)

Useful for testing agent changes without deploying.

1. Create `worker/.env` (do **not** commit):

   ```bash
   cd worker
   echo 'OPENAI_API_KEY=sk-your-key' > .env
   # Or: GEMINI_API_KEY=your-key
   ```

2. Run a local build (output in `worker/output/<job_id>/`):

   ```bash
   python run_local.py "Build a simple counter with plus and minus buttons"
   # Or: python3 run_local.py "..."
   ```

   Or the complex test:

   ```bash
   python run_local_complex.py
   ```

3. Open `worker/output/<job_id>/index.html` in a browser.

---

## Step 5: Making changes

- **Frontend:** Edit `frontend/app/` (e.g. `page.tsx`, `layout.tsx`, `globals.css`). Preview with `npm run dev` in `frontend/`.
- **Agent:** Edit `worker/` (e.g. `agent.py`, `validate.py`). Test with `run_local.py` or `run_local_complex.py`.

Commit, push to your branch, and open a PR when ready.

---

## Step 6: Deploy your changes

### Frontend

- **Hosted (Vercel/Amplify, etc.):** Push to the branch that triggers deploys.
- **Local only:** No deploy; others pull and run `npm run dev` with their own `.env.local`.

### Agent (worker) to Fargate

When you change anything in `worker/`, you must:

1. Build a new Docker image
2. Push it to ECR
3. Force ECS to run the new image

Use the **region** and **ECR URI** from the stack (see [Stack details](#where-to-find-stack-details)).

**From the project root** (directory that contains `worker/`):

```bash
# Set these (get from a teammate or from stack outputs / AWS Console)
export AWS_REGION=us-east-2
export ECR_URI=464796503667.dkr.ecr.us-east-2.amazonaws.com/build-apps-worker

# Optional: if you use a named profile
export AWS_PROFILE=build-apps

# Build, tag, login, push (uses worker/build-and-push.sh)
cd worker
./build-and-push.sh "$AWS_REGION" "$ECR_URI"
cd ..
```

Then force ECS to use the new image:

```bash
aws ecs update-service \
  --cluster BuildAppsWorkerCluster \
  --service BuildAppsWorker \
  --force-new-deployment \
  --region "$AWS_REGION"
```

If you use a profile, add `--profile build-apps` to the `aws ecs update-service` command.

**One-liner** (after setting `AWS_REGION` and `ECR_URI`):

```bash
cd worker && ./build-and-push.sh "$AWS_REGION" "$ECR_URI" && cd .. && \
aws ecs update-service --cluster BuildAppsWorkerCluster --service BuildAppsWorker --force-new-deployment --region "$AWS_REGION"
```

After 1–2 minutes, new tasks will run the new image. New jobs from the frontend will use the updated agent.

---

## Where to find stack details

- **API URL:** CloudFormation → **BuildAppsStack** → **Outputs** → `ApiUrl` or `BuildAppsApiEndpoint...`
- **ECR URI:** ECR → **Repositories** → `build-apps-worker` → copy **URI**
- **Region:** Same as the stack (e.g. `us-east-2`)
- **ECS:** ECS → **Clusters** → **BuildAppsWorkerCluster** → **Services** → **BuildAppsWorker**

Or, from the repo (if you have deploy access):

```bash
cd infra
npx cdk deploy --outputs-file ../outputs.json
```

---

## Quick reference

| Task | Command |
|------|---------|
| Log into AWS | `aws configure` or `aws configure --profile build-apps` |
| Check identity | `aws sts get-caller-identity` |
| Run frontend | `cd frontend && npm run dev` (after `.env.local`) |
| Test agent | `cd worker && python run_local.py "prompt"` |
| Deploy worker | `cd worker && ./build-and-push.sh $AWS_REGION $ECR_URI` then `aws ecs update-service ... --force-new-deployment` |

---

## Troubleshooting

- **“Repository does not exist” on push:** Use the ECR URI and region that match your stack (e.g. `us-east-2`).
- **“Unable to locate credentials”:** Run `aws configure` (or with `--profile build-apps`) and confirm with `aws sts get-caller-identity`.
- **Frontend can’t reach API:** Check `NEXT_PUBLIC_API_URL` in `frontend/.env.local` (no trailing slash).
- **Jobs stuck in “queued”:** Check ECS → Cluster → Service → **Tasks** and CloudWatch logs (`/ecs/build-apps-worker`).
- **Permission denied: ./build-and-push.sh:** Run `chmod +x worker/build-and-push.sh`.
- **Worker needs API key:** ECS task definition must have `OPENAI_API_KEY` or `GEMINI_API_KEY`. Someone with AWS Console access can add it (new task definition revision) or use Secrets Manager.

For more detail or Windows instructions, see [CONTRIBUTING.md](CONTRIBUTING.md).
