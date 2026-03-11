**Linux or macOS?** You can use **[CONTRIBUTING-LINUX-MACOS.md](CONTRIBUTING-LINUX-MACOS.md)** for a bash-only version of this guide.

---

## What you need installed

- **Git** – to clone and push code
- **Node.js 18+** – for frontend and infra
- **Python 3.11+** – for the agent (local runs/tests)
- **Docker Desktop** – for building and pushing the worker image
- **AWS CLI v2** – [Install](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)
- **AWS account access** 
- **Stack details**: API URL, AWS region, ECR image URI, ECS cluster and service names (or where to find them)

---

## Step 1: Log into the team AWS account

### 1.1 Get your credentials

1. **Access key ID** (e.g. `AKIA...`)
2. **Secret access key** (one-time; save it somewhere safe)

Someone on the project (with AWS access) can create an IAM user and share these with you.

They may use a **profile name** (e.g. `build-apps-team`) so multiple people can use the same account without overwriting each other’s config.

### 1.2 Configure the AWS CLI

Open a terminal and run:

```bash
aws configure
```

When prompted, enter:

| Prompt | What to enter |
|--------|----------------|
| **AWS Access Key ID** | Your access key |
| **AWS Secret Access Key** | Your secret key |
| **Default region name** | `us-east-2` (or the region the stack uses) |
| **Default output format** | `json` (or leave blank) |

If you use a **named profile** (e.g. `build-apps`), run instead:

```bash
aws configure --profile build-apps
```

Use the same values; then for any AWS or deployment command in this doc, add: `--profile build-apps`.

### 1.3 Check that it works

```bash
aws sts get-caller-identity
```

You should see your account ID and user ARN. If you use a profile:

```bash
aws sts get-caller-identity --profile build-apps-team
```

---

## Step 2: Get the code and install dependencies

### 2.1 Clone the repo

```bash
git clone <repository-url>
cd app
```

Replace `<repository-url>` with the actual Git URL (GitHub, GitLab, etc.).

### 2.2 Install frontend dependencies

```bash
cd frontend
npm install
cd ..
```

### 2.3 Install agent (Python) dependencies (optional, for local agent runs)

```bash
cd worker
pip install -r requirements.txt
cd ..
```

### 2.4 Install infra dependencies (only if you will run CDK)

```bash
cd infra
npm install
cd ..
```

---

## Step 3: Run the frontend locally

1. **Create frontend env file**

   In the `frontend` folder, copy the example env and set the API URL:

   ```bash
   cd frontend
   cp .env.example .env.local
   ```

   Edit `frontend/.env.local` and set:

   ```bash
   NEXT_PUBLIC_API_URL=https://YOUR_API_URL/prod
   ```


2. **Start the dev server**

   ```bash
   npm run dev
   ```

3. Open **http://localhost:3000**. You can change the UI here; the page will hot-reload.

---

## Step 4: Run the agent locally (optional)

Useful for testing agent/LLM changes without deploying.

1. **Create `worker/.env`** (do not commit this file):

   **Recommended: OpenAI API only** (no CLI, good for coding):

   ```bash
   OPENAI_API_KEY=sk-your-key
   # Optional: better code quality (default is gpt-4o-mini):
   # OPENAI_MODEL=gpt-4o
   ```

   Or use Gemini: `GEMINI_API_KEY=your-key`

   To use Codex instead: set `USE_CODEX=1` and ensure the Codex CLI is installed or set `CODEX_PATH_OVERRIDE`. If both USE_CODEX and OPENAI_API_KEY are set, Codex takes precedence.

2. **Run a local build** (writes to `worker/output/<job_id>/`):

   ```bash
   cd worker
   python run_local.py "Build a simple counter with plus and minus buttons"
   ```

   Or use the more complex test:

   ```bash
   python run_local_complex.py
   ```

3. Open the generated `worker/output/<job_id>/index.html` in a browser.

---

## Step 5: Making changes

- **Frontend:** Edit files under `frontend/app/` (e.g. `page.tsx`, `layout.tsx`, `globals.css`). Run `npm run dev` in `frontend` to preview.
- **Agent:** Edit files under `worker/` (e.g. `agent.py`, `validate.py`). Test locally with `run_local.py` or `run_local_complex.py` as above.


---

## Step 6: Deploy your changes

### Deploying **agent (worker)** changes to Fargate

When you change anything in `worker/` (e.g. `agent.py`, prompts, validation), you need to:

1. **Build** a new Docker image.
2. **Push** it to ECR.
3. **Tell ECS** to run the new image (force a new deployment).

Use the same **AWS region** and **ECR URI** your stack uses (see [Where to find stack details](#where-to-find-stack-details)).

---

#### Option A: Linux / macOS (bash)

From the **project root** (folder that contains `worker/`):

```bash
export AWS_REGION=us-east-2
export ECR_URI=464796503667.dkr.ecr.us-east-2.amazonaws.com/build-apps-worker

# Build, tag, login, push
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
  --region us-east-2
```

If you use a **profile**, add `--profile build-apps-team` to the `aws ecs update-service` command (and ensure `./build-and-push.sh` uses the same profile, e.g. `export AWS_PROFILE=build-apps-team` before running it).

---

#### Option B: Windows (PowerShell)

You can use the helper script from the `worker/` folder (project root one level up):

```powershell
cd worker
.\build-and-push.ps1 -Region us-east-2 -EcrUri "464796503667.dkr.ecr.us-east-2.amazonaws.com/build-apps-worker"
# If you use a named profile: -Profile build-apps-team
cd ..
```

Then force a new ECS deployment (same `aws ecs update-service` command as in the manual steps below). Or run the steps manually from the **project root** (replace region and ECR URI if yours differ):

```powershell
$AWS_REGION = "us-east-2"
$ECR_URI = "464796503667.dkr.ecr.us-east-2.amazonaws.com/build-apps-worker"

# 1) Build image
docker build -t build-apps-worker:latest ./worker

# 2) Tag for ECR
docker tag build-apps-worker:latest "${ECR_URI}:latest"

# 3) Log in to ECR
aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin ($ECR_URI -replace '/.*','')

# 4) Push
docker push "${ECR_URI}:latest"

# 5) Force ECS to use the new image
aws ecs update-service --cluster BuildAppsWorkerCluster --service BuildAppsWorker --force-new-deployment --region $AWS_REGION
```

If you use a **profile**, add `--profile build-apps-team` to the `aws ecr get-login-password` and `aws ecs update-service` commands.

---

#### After pushing

- ECS will start new tasks with the new image and drain the old ones. This usually takes 1–2 minutes.
- New jobs (from the frontend “Build” button) will use the updated agent code.

---

## Where to find stack details

If your team uses the CDK stack, someone with deploy access can run:

```bash
cd infra
npx cdk deploy --outputs-file ../outputs.json
```

**Important (frontend / localhost):** When you use the frontend (e.g. at localhost) to create jobs, the **worker runs on ECS**, not on your machine. The worker must have an LLM API key. Pass it at deploy time so the ECS task gets it:

```bash
cd infra
npx cdk deploy -c OPENAI_API_KEY=sk-your-key-here
# Or with Gemini: -c GEMINI_API_KEY=your-gemini-key
```

After changing the API key you must redeploy (e.g. `npx cdk deploy -c OPENAI_API_KEY=sk-...` again, or use `--hotswap` for faster updates).

Or in the **AWS Console**:

- **API URL:** CloudFormation → **BuildAppsStack** → **Outputs** → `ApiUrl` or `BuildAppsApiEndpoint...`
- **ECR URI:** ECR → **Repositories** → `build-apps-worker` → copy **URI**
- **Region:** Same as the stack (e.g. **us-east-2**)
- **ECS:** ECS → **Clusters** → **BuildAppsWorkerCluster** → **Services** → **BuildAppsWorker**

---

## Quick reference

| Task | Where | Command / action |
|------|--------|-------------------|
| Log into AWS | Terminal | `aws configure` (or `aws configure --profile build-apps-team`) |
| Check AWS identity | Terminal | `aws sts get-caller-identity` |
| Run frontend | `frontend/` | `npm run dev` (after setting `frontend/.env.local`) |
| Test agent locally | `worker/` | `python run_local.py "Your prompt"` |
| Deploy worker to Fargate | Project root | Build image → push to ECR → `aws ecs update-service ... --force-new-deployment` |

---

## Troubleshooting

- **“Repository does not exist” when pushing:** The ECR repo might be in a different region. Use the same region as your stack (e.g. `us-east-2`) and the ECR URI for that region.
- **“Unable to locate credentials”:** Run `aws configure` (or with `--profile build-apps-team`) and check `aws sts get-caller-identity`.
- **Frontend can’t reach API:** Ensure `NEXT_PUBLIC_API_URL` in `frontend/.env.local` has no trailing slash and matches the stack’s API URL.
- **Jobs stuck in “queued”:** The ECS service might have no running tasks, or the worker might be crashing. Check ECS → Cluster → Service → **Tasks** and **Logs** (CloudWatch log group `/ecs/build-apps-worker`).
- **Worker needs an API key (e.g. when using frontend on localhost):** Jobs from the frontend are processed by the ECS worker, which needs `OPENAI_API_KEY` or `GEMINI_API_KEY`. Redeploy with the key: `cd infra && npx cdk deploy -c OPENAI_API_KEY=sk-your-key`. For production, use Secrets Manager instead of context.
- **“Codex CLI not found” (local, USE_CODEX=1):** The Python SDK does not ship the Codex binary; it expects it to be installed or provided. Options: **(1)** Install the Codex CLI (e.g. [Codex app for Windows](https://developers.openai.com/codex/app/windows) or [CLI install](https://developers.openai.com/codex/cli)), then in `worker/.env` set `CODEX_PATH_OVERRIDE` to the full path to `codex.exe` (or put `codex` on your PATH). **(2)** Or use OpenAI instead: remove or comment out `USE_CODEX=1` and set `OPENAI_API_KEY` (or `API_KEY`) so the worker uses gpt-4o-mini.

If something isn’t covered here, just ping me