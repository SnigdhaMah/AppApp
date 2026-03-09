# Using Codex CLI with the worker

The worker can use the **OpenAI Codex CLI** (via the Python SDK) when `USE_CODEX=1`. The SDK spawns the Codex binary and uses it for expand, plan, and build steps. If Codex is unavailable (CLI not found, auth error), it falls back to OpenAI or Gemini when those keys are set.

## Local usage

### 1. Install and authenticate Codex CLI

**Option A – CLI on PATH (recommended for local dev)**

- Install the Codex CLI (Node 18+):
  ```bash
  npm install -g @openai/codex
  codex --version
  ```
- Log in (browser or device code):
  ```bash
  codex auth
  ```
  or
  ```bash
  codex login
  ```
  Credentials are stored in `~/.codex/auth.json` (or OS keychain).

**Option B – Auth via env (no CLI login)**

- On a machine where you can run `codex login`, set file-backed auth:
  - In `~/.codex/codex.toml` (or `$CODEX_HOME/codex.toml`): set `cli_auth_credentials_store = "file"`.
  - Run `codex login` and complete the flow.
  - Copy the contents of `~/.codex/auth.json` and set:
  ```bash
  set CODEX_AUTH_JSON={"auth_mode":"chatgpt", ...}   # Windows
  export CODEX_AUTH_JSON='{"auth_mode":"chatgpt", ...}'   # Linux/macOS
  ```
  The worker (and SDK) will write this to `~/.codex/auth.json` when using Codex.

### 2. Enable Codex for the worker

In `worker/.env` (or your environment):

```env
USE_CODEX=1
# Optional: if Codex CLI is not on PATH
# CODEX_PATH_OVERRIDE=C:\path\to\codex.exe
# Optional: CLI version when the SDK installs the binary (containers)
# CODEX_CLI_VERSION=rust-v0.88.0-alpha.3
```

If you use **Option B**, also set `CODEX_AUTH_JSON` as above. Then run:

```bash
cd worker
python run_local.py "Create an app that will help me with grocery shopping"
```

With `USE_CODEX=1`, the worker uses Codex for the run; if Codex fails (e.g. CLI not found), it falls back to `OPENAI_API_KEY` or `GEMINI_API_KEY` if set.

---

## ECS (Fargate) usage

The worker image does **not** include the Codex CLI binary. When `USE_CODEX=1` and the SDK is used, the agent will:

1. **Install the binary** – Call `Codex.install(...)` on first use (downloads into the SDK vendor path). Override version with `CODEX_CLI_VERSION` if needed.
2. **Auth from secret** – If `CODEX_AUTH_JSON` is set (e.g. from ECS secrets), the agent calls `Codex.login_with_auth_json(overwrite=True)` so the CLI sees `~/.codex/auth.json`.

### 1. Create the auth secret in AWS

Put the contents of your Codex `auth.json` (from a machine where you ran `codex login` with `cli_auth_credentials_store = "file"`) into Secrets Manager:

```bash
# Create secret (value = raw JSON string)
aws secretsmanager create-secret \
  --name build-apps/codex-auth \
  --secret-string "$(cat ~/.codex/auth.json)" \
  --region us-east-1
```

Note the secret ARN (e.g. `arn:aws:secretsmanager:us-east-1:123456789012:secret:build-apps/codex-auth-xxxxx`).

### 2. Deploy the stack with Codex enabled

Pass the secret ARN at deploy time so the ECS task gets `USE_CODEX=1` and `CODEX_AUTH_JSON` from the secret:

```bash
cd infra
npx cdk deploy \
  -c CODEX_AUTH_SECRET_ARN=arn:aws:secretsmanager:REGION:ACCOUNT:secret:build-apps/codex-auth-xxxxx
```

The stack will:

- Set `USE_CODEX=1` in the worker container environment.
- Attach the secret as `CODEX_AUTH_JSON` (execution role is granted read access to the secret).

Redeploy the worker (e.g. push a new image and force a new ECS deployment). On first Codex use, the container will install the CLI binary and write auth from `CODEX_AUTH_JSON`; subsequent runs will use Codex.

### 3. Optional: keep Codex auth fresh

Codex auth can expire. For long-lived ECS tasks or repeated runs, either:

- Use a **scheduled job** (or a separate task) that runs Codex occasionally so it can refresh tokens and you persist the updated `auth.json` back to Secrets Manager, or  
- Re-seed the secret from a trusted machine with a new `codex login` when needed.

For most cases, using **OpenAI API** (`OPENAI_API_KEY` + `OPENAI_MODEL`) or **Gemini** (`GEMINI_API_KEY`) in ECS is simpler and avoids managing Codex auth in the cloud.
