"""Agent loop: generate app with LLM (OpenAI or Gemini), validate, fix, upload."""
import json
import os
import tempfile
import shutil
from validate import validate_project
from s3_upload import upload_folder_to_s3

# Optional for local testing: if not set, output goes to ./output/<job_id>
S3_BUCKET = os.environ.get("APPS_BUCKET", "").strip()
PUBLIC_BASE_URL = (os.environ.get("PUBLIC_BASE_URL") or "").rstrip("/")
LOCAL_OUTPUT_DIR = os.environ.get("LOCAL_OUTPUT_DIR", "output").strip()

MAX_ITERS = 3

SYSTEM_RULES = """
You are generating a small static web app.
Constraints:
- Output must be valid JSON with shape: {"files":[{"path":"...","content":"..."}]}
- Only create these files: index.html, style.css, script.js, data.json (optional)
- Use relative paths in HTML: ./style.css and ./script.js
- Do NOT use external CDNs or remote scripts.
- Keep it simple and functional.
- Data storage: prefer localStorage OR a tiny inline data.json.

Design (make every app look like a modern 2025-2026 web app):
- Layout: Single main column; max-width container (480-560px), centered, padding (e.g. 24px). Use a .container or main wrapper.
- Typography: Use system font stack: system-ui, -apple-system, Segoe UI, Roboto, sans-serif. Clear hierarchy: one strong h1, body 16-18px, line-height ~1.5.
- Colors: Use CSS variables for background, surface, text, and one primary/accent. Avoid raw #fff/#000 only. Light theme by default: off-white or very light gray bg, dark text, one accent for buttons/links.
- Components: Buttons and inputs with consistent padding, border-radius 8-12px, subtle shadow or border. Cards/lists with spacing and separation (padding, border or box-shadow).
- Tone: Clean, consistent spacing. No cramped or "demo-only" look. It should feel like a real product.
"""


def _parse_json_response(text: str) -> dict:
    """Extract JSON from LLM response (strip code fences if present)."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    return json.loads(text)


# JSON schema for Codex structured output (files array)
CODEX_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "files": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                "required": ["path", "content"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["files"],
    "additionalProperties": False,
}


def call_llm(prompt: str) -> dict:
    """Call Codex, OpenAI, or Gemini API and return parsed JSON."""
    if os.environ.get("USE_CODEX", "").strip().lower() in ("1", "true", "yes"):
        return _call_codex(prompt)
    openai_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("API_KEY")
    if openai_key:
        return _call_openai(prompt, openai_key)
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if gemini_key:
        return _call_gemini(prompt, gemini_key)
    raise RuntimeError(
        "Set USE_CODEX=1 (with CODEX_AUTH_JSON or codex login), "
        "OPENAI_API_KEY (or API_KEY), or GEMINI_API_KEY in the environment"
    )


def _call_codex(prompt: str) -> dict:
    """Use OpenAI Codex SDK with structured output (files array)."""
    import asyncio
    from openai_codex_sdk import Codex

    async def _run() -> dict:
        codex = Codex()
        thread = codex.start_thread({"skip_git_repo_check": True})
        full_prompt = f"{SYSTEM_RULES}\n\nUser request:\n{prompt}\n\nReturn JSON only with key 'files' (array of {{'path': '...', 'content': '...'}})."
        turn = await thread.run(full_prompt, {"output_schema": CODEX_OUTPUT_SCHEMA})
        raw = (turn.final_response or "").strip()
        return _parse_json_response(raw)

    return asyncio.run(_run())


def _call_openai(prompt: str, api_key: str) -> dict:
    """Use OpenAI API with JSON mode."""
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_RULES},
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
    )
    text = (response.choices[0].message.content or "").strip()
    return _parse_json_response(text)


def _call_gemini(prompt: str, api_key: str) -> dict:
    """Use Gemini API."""
    import google.generativeai as genai

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        "gemini-1.5-flash",
        system_instruction=SYSTEM_RULES,
    )
    response = model.generate_content(
        prompt,
        generation_config=genai.types.GenerationConfig(
            response_mime_type="application/json",
        ),
    )
    text = (response.text or "").strip()
    return _parse_json_response(text)


def write_files(workdir: str, files: list[dict]) -> None:
    allowed = {"index.html", "style.css", "script.js", "data.json"}
    for f in files:
        path = (f.get("path") or "").strip().lstrip("/")
        if path not in allowed:
            continue
        content = f.get("content") or ""
        full = os.path.join(workdir, path)
        os.makedirs(os.path.dirname(full) or ".", exist_ok=True)
        with open(full, "w", encoding="utf-8") as fp:
            fp.write(content)


def build_app(job_id: str, user_prompt: str, update_job) -> str:
    workdir = tempfile.mkdtemp(prefix=f"job_{job_id}_")

    try:
        update_job(job_id, step="generating", progress=20)
        spec_prompt = f"""Generate a static web app that looks like a modern 2026 product: clear typography, spacing, and one accent color.

User request:
{user_prompt}

Return JSON only with key "files" (array of {{"path": "...", "content": "..."}}).
"""
        out = call_llm(spec_prompt)
        files = out.get("files", [])
        write_files(workdir, files)

        for i in range(MAX_ITERS):
            update_job(job_id, step="validating", progress=40 + i * 10)
            issues = validate_project(workdir)

            if not issues:
                break

            update_job(job_id, step="fixing", progress=55 + i * 10)
            current = {}
            for name in ["index.html", "style.css", "script.js", "data.json"]:
                p = os.path.join(workdir, name)
                if os.path.exists(p):
                    with open(p, "r", encoding="utf-8") as fp:
                        current[name] = fp.read()

            fix_prompt = f"""The generated app has issues:
{json.dumps(issues, indent=2)}

Current files:
{json.dumps(current, indent=2)}

Return JSON only with full corrected "files" array (overwrite all).
"""
            out = call_llm(fix_prompt)
            files = out.get("files", [])
            write_files(workdir, files)

        update_job(job_id, step="uploading", progress=85)
        if S3_BUCKET and PUBLIC_BASE_URL:
            prefix = f"apps/{job_id}/"
            upload_folder_to_s3(workdir, S3_BUCKET, prefix)
            # Delete local workspace after successful S3 upload (no retain on worker)
            shutil.rmtree(workdir, ignore_errors=True)
            workdir = None  # avoid double-remove in finally
            result_url = f"{PUBLIC_BASE_URL}/{prefix}index.html"
        else:
            # Local mode: copy to output dir, then delete local workspace
            out_dir = os.path.join(LOCAL_OUTPUT_DIR, job_id)
            os.makedirs(out_dir, exist_ok=True)
            for name in os.listdir(workdir):
                src = os.path.join(workdir, name)
                if os.path.isfile(src):
                    with open(src, "rb") as f:
                        open(os.path.join(out_dir, name), "wb").write(f.read())
            result_url = f"file://{os.path.abspath(out_dir)}/index.html"
            shutil.rmtree(workdir, ignore_errors=True)
            workdir = None
        return result_url

    finally:
        if workdir and os.path.exists(workdir):
            shutil.rmtree(workdir, ignore_errors=True)
