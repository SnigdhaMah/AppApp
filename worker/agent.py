"""Agent loop: generate app with LLM (OpenAI or Gemini), validate, fix, upload."""
import json
import os
import re
import tempfile
import shutil
from validate import validate_project
from s3_upload import upload_folder_to_s3

# Optional for local testing: if not set, output goes to ./output/<job_id>
S3_BUCKET = os.environ.get("APPS_BUCKET", "").strip()
PUBLIC_BASE_URL = (os.environ.get("PUBLIC_BASE_URL") or "").rstrip("/")
LOCAL_OUTPUT_DIR = os.environ.get("LOCAL_OUTPUT_DIR", "output").strip()

# OpenAI model (e.g. gpt-4o for better code, gpt-4o-mini for faster/cheaper)
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini").strip()

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

Design — a branded base stylesheet is automatically prepended to style.css. You MUST:
- Use the existing CSS variables in your style.css: --bg, --surface, --text, --text-muted, --accent, --accent-hover, --accent-text, --border, --radius, --radius-sm, --shadow, --space-xs, --space-sm, --space-md, --space-lg, --space-xl. Do NOT redefine these in :root.
- A branded navbar (logo + "Build Apps") is automatically injected at the top of the page. Do not add your own navbar or header. Use class .container for the main content wrapper (already styled; it appears below the navbar). Use semantic HTML: main, section, label, button, input, etc.
- In style.css output ONLY app-specific rules (e.g. layout for your sections, IDs, or small overrides). Do not repeat body, .container, or global button/input styles from the base. Plain CSS only — no Sass/SCSS (no darken(), no mixins).
- Result: every app shares the same branded look; your CSS only adds what is unique to this app.
"""

# Expansion: product reasoning (what the app should be, features, what users care about)
EXPANSION_SYSTEM = """You are a product expert. The user will give a short request for an app (e.g. "gym app", "todo app").
Your job is to reason about:
- What kind of app this is and what it should do.
- What features are needed (think about what similar successful apps have).
- What users usually care about for this type of app.
- What core functionality must be included.

Output a clear, detailed product spec in plain text (a few short paragraphs or bullet points). The spec will be used by a planner to produce a build plan. Assume the app will be built as a single-page static site only: HTML, CSS, JavaScript, with localStorage or a small data.json. No backend, no auth, no external CDNs. Keep the scope achievable within those constraints."""

# Planning: turn expanded spec into a concrete build brief for the code generator
PLANNING_SYSTEM = """You are a technical planner. You receive a product spec for a static web app and produce a single, detailed build brief.
The brief will be given to a code generator that outputs only: index.html, style.css, script.js, and optionally data.json. No CDNs, no external scripts. Data: localStorage or inline data.json only.

Your build brief must be concrete and complete so the generator can implement it. Include:
- All main UI sections and screens (or single-page sections).
- Every feature and behavior (e.g. add, remove, edit, persist).
- Any specific UX details from the spec.

Write the brief as one clear instruction (one or two paragraphs, or a short bullet list). Do not output code. Do not repeat the tech constraints (the generator already knows them). Focus on what to build, not how to implement it."""


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
    use_codex = os.environ.get("USE_CODEX", "").strip().lower() in ("1", "true", "yes")
    if use_codex:
        try:
            return _call_codex(prompt)
        except Exception as e:
            if "CodexExecError" in type(e).__name__ or "Codex CLI not found" in str(e):
                # Codex CLI missing; fall back to API if available
                pass
            else:
                raise
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


def _codex_options() -> dict:
    """Build Codex options from env (e.g. CODEX_PATH_OVERRIDE for custom CLI path)."""
    opts = {}
    path = (os.environ.get("CODEX_PATH_OVERRIDE") or "").strip()
    if path:
        opts["codex_path_override"] = path
    return opts


def _call_codex(prompt: str) -> dict:
    """Use OpenAI Codex SDK with structured output (files array)."""
    import asyncio
    from openai_codex_sdk import Codex

    async def _run() -> dict:
        codex = Codex(_codex_options())
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
        model=OPENAI_MODEL,
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


def call_llm_text(system_prompt: str, user_message: str) -> str:
    """Call LLM for plain-text response (expansion, planning). Uses same provider as call_llm."""
    use_codex = os.environ.get("USE_CODEX", "").strip().lower() in ("1", "true", "yes")
    if use_codex:
        try:
            return _call_codex_text(system_prompt, user_message)
        except Exception as e:
            if "CodexExecError" in type(e).__name__ or "Codex CLI not found" in str(e):
                pass
            else:
                raise
    openai_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("API_KEY")
    if openai_key:
        return _call_openai_text(system_prompt, user_message, openai_key)
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if gemini_key:
        return _call_gemini_text(system_prompt, user_message, gemini_key)
    raise RuntimeError(
        "Set USE_CODEX=1, OPENAI_API_KEY (or API_KEY), or GEMINI_API_KEY in the environment"
    )


def _call_openai_text(system_prompt: str, user_message: str, api_key: str) -> str:
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
    )
    return (response.choices[0].message.content or "").strip()


def _call_gemini_text(system_prompt: str, user_message: str, api_key: str) -> str:
    import google.generativeai as genai

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        "gemini-1.5-flash",
        system_instruction=system_prompt,
    )
    response = model.generate_content(user_message)
    return (response.text or "").strip()


def _call_codex_text(system_prompt: str, user_message: str) -> str:
    import asyncio
    from openai_codex_sdk import Codex

    async def _run() -> str:
        codex = Codex(_codex_options())
        thread = codex.start_thread({"skip_git_repo_check": True})
        full_prompt = f"{system_prompt}\n\nUser:\n{user_message}"
        turn = await thread.run(full_prompt)
        return (turn.final_response or "").strip()

    return asyncio.run(_run())


def expand_request(user_prompt: str) -> str:
    """Expand a short user request into a detailed product spec (features, what users care about)."""
    return call_llm_text(EXPANSION_SYSTEM, user_prompt)


def plan_build(expanded_spec: str) -> str:
    """Turn an expanded product spec into a concrete build brief for the code generator."""
    return call_llm_text(PLANNING_SYSTEM, expanded_spec)


def _get_base_css() -> str:
    """Load branded base template CSS (same dir as this module)."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base_dir, "templates", "base.css")
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return ""


def _get_navbar_html() -> str:
    """Load branded navbar snippet (logo + brand name)."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base_dir, "templates", "navbar.html")
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    return ""


def _inject_navbar(workdir: str) -> None:
    """Insert the branded navbar as the first child of body in index.html."""
    navbar = _get_navbar_html()
    if not navbar:
        return
    index_path = os.path.join(workdir, "index.html")
    if not os.path.exists(index_path):
        return
    with open(index_path, "r", encoding="utf-8") as f:
        html = f.read()
    # Insert navbar right after <body> or <body ...>
    if "navbar navbar-inner" in html or "class=\"navbar\"" in html:
        return  # already injected (e.g. from a previous fix round that read it back)
    pattern = re.compile(r"<body([^>]*)>\s*", re.IGNORECASE | re.DOTALL)
    replacement = r"<body\1>\n" + navbar + "\n"
    new_html = pattern.sub(replacement, html, count=1)
    if new_html != html:
        with open(index_path, "w", encoding="utf-8") as f:
            f.write(new_html)


def _apply_style_template(workdir: str) -> None:
    """Prepend branded base.css to style.css so every app uses the same design system."""
    base_css = _get_base_css()
    if not base_css:
        return
    style_path = os.path.join(workdir, "style.css")
    if not os.path.exists(style_path):
        with open(style_path, "w", encoding="utf-8") as f:
            f.write(base_css)
        return
    with open(style_path, "r", encoding="utf-8") as f:
        app_css = f.read()
    # Base first, then app-specific (app can override with same specificity)
    combined = base_css.rstrip() + "\n\n/* App-specific styles */\n" + app_css.lstrip()
    with open(style_path, "w", encoding="utf-8") as f:
        f.write(combined)


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
    _apply_style_template(workdir)
    _inject_navbar(workdir)


def build_app(job_id: str, user_prompt: str, update_job) -> str:
    workdir = tempfile.mkdtemp(prefix=f"job_{job_id}_")

    try:
        update_job(job_id, step="generating", progress=20)
        spec_prompt = f"""Generate a static web app. A branded navbar (logo + brand) is auto-injected at the top; do not add a navbar. A base stylesheet is applied; your style.css is appended after it — output only app-specific CSS using base variables. Use class="container" for the main content wrapper (below the navbar).

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
