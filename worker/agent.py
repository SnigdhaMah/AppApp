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
You are an expert front-end engineer generating a polished, fully-functional static web microapp.

## Output Format
- Return ONLY valid JSON with shape: {"files":[{"path":"...","content":"..."}]}
- Allowed files: index.html, style.css, script.js, data.json (optional)
- Use relative paths in HTML: ./style.css and ./script.js
- Do NOT use external CDNs or remote scripts — all logic must be self-contained.

## HTML — structure and content rules:
- ALL visible content (h1, sections, divs, everything) must be placed INSIDE .container.
  Never place any element between the navbar and .container — the first child of <body>
  after the navbar must always be the .container (or a wrapper that contains it).
- Use semantic elements: <main>, <section>, <article>, <aside>, <dialog>, <details>, <figure>.
- Accessibility: ARIA roles/labels on interactive elements, keyboard-navigable UI,
  <label for="x"> on every input with a matching id="x", role="alert" for dynamic messages.
- Use <template> tags for repeating UI patterns rendered by JS.
- Support responsive layout from the start (viewport meta, fluid containers).
- Do NOT use inline event handlers (onclick, onchange, oninput, etc.).
  ALL event binding must be done in script.js via addEventListener.
- Every <button> must have either visible text content or an aria-label attribute.

## JavaScript — write production-quality JS:
- Do NOT use <script type="module"> unless the script contains actual ES module
  import statements. For self-contained single-file scripts, use a plain <script> tag.
  type="module" is blocked by browsers on file:// URLs and will silently break the app.
- Every id referenced via getElementById or querySelector MUST exist in index.html.
  Never query an element that isn't in the DOM.
- Every CSS class toggled via classList.add/remove/toggle MUST have a corresponding
  rule in style.css. Never toggle a class that has no styles defined.
- localStorage.getItem('key') and localStorage.setItem('key') must use identical key
  strings. Never read a key that was never written.
- Use modern ES6+ features: classes, async/await, destructuring, WeakMap, generators, etc.
- Structure code with clear separation: data layer, state management, rendering, events.
- Implement rich interactivity: drag-and-drop, requestAnimationFrame animations, canvas,
  Web Audio API, real-time filtering/search, keyboard shortcuts, undo/redo — as warranted.
- Handle edge cases: empty states, input validation with clear error feedback,
  loading indicators, debounced inputs.
- Write helper utilities (uuid(), deepClone(), formatDate()) inline — no placeholders.

## CSS — rich, purposeful, explicit styling:
- Use CSS custom properties (--bg, --surface, --text, --text-muted, --accent,
  --accent-hover, --accent-text, --border, --radius, --radius-sm, --shadow,
  --space-xs, --space-sm, --space-md, --space-lg, --space-xl).
  Do NOT redefine these in :root — they are provided by the base stylesheet.
- Do NOT redefine body, .container, or global button/input styles from the base.
- Output ONLY app-specific rules. Every key element must have explicit sizing:
  specify font-size, padding, and display mode — never leave hero elements unstyled.
- Primary display values (counters, scores, results) must use font-size ≥ 4rem.
- All buttons must have enough padding and min-width that their labels never wrap.
- Define explicit button hierarchy: primary (accent bg), secondary (outlined), ghost.
- Use CSS Grid and Flexbox for layouts. Add @keyframes animations where meaningful.
- Implement responsive breakpoints. App must work cleanly at 375px and 1200px widths.
- Every CSS class toggled by JS must be defined here with actual property values.

## Design System
- A branded navbar (logo + "Build Apps") is auto-injected at the top — do not add your own.
- Use class .container for the main content wrapper (already styled; appears below navbar).
- The base stylesheet provides all design tokens. Layer your app-specific styles on top.

## Visual Quality Bar — every app must meet these before output:
- Clear visual hierarchy: one dominant hero element (the main value, CTA, or display).
- Consistent spacing using only --space-* variables — no magic pixel numbers.
- All interactive elements have hover and focus states defined in CSS.
- No text or elements overflow or clip their container at any viewport width.
- The app looks like it belongs in a modern SaaS product, not a browser default stylesheet.

## Scope & Ambition
- Build the FULL feature set implied by the request — no stubs, no TODOs, no placeholders.
- If the app has multiple views/screens, implement all of them as JS-toggled sections.
- If data visualization fits, draw it with <canvas> or inline SVG.
- If the app involves lists or cards, implement sorting, filtering, and search.
- Aim for an app a user would actually want to use daily.
"""

# Expansion: deep product reasoning
EXPANSION_SYSTEM = """You are a senior product manager and UX designer. The user will give a short request for an app.

Your job is to produce a thorough product specification covering:

1. **Core purpose** — What problem does this solve? Who uses it and why?
2. **Feature inventory** — List every feature the app should have, from primary to secondary. Think about what makes the best-in-class version of this app great.
3. **User flows** — Describe the key interactions step by step (e.g. "User adds item → sees it in list → can edit inline → deletes with confirmation").
4. **Data model** — What entities/objects need to be stored? What are their fields? How do they relate?
5. **UI layout** — Describe the screens or sections, how they're organized, what's always visible vs. toggled.
6. **Visual personality** — What should this app feel like to use? Describe the intended emotional quality (e.g. "satisfying and tactile like a physical counter", "calm and focused like a meditation tool", "energetic and gamified like a fitness tracker"). This will directly guide typography scale, animation style, and color usage decisions.
7. **Delight details** — Small UX touches that make the app feel polished: keyboard shortcuts, animations, empty states, undo, smart defaults, progress indicators, etc.

Constraints: static site only (HTML/CSS/JS), no backend, no auth, localStorage or small data.json for persistence, no external CDNs.

Be specific and complete. The planner will turn this into a build brief for an engineer."""

# Planning: turn expanded spec into a concrete, detailed build brief
PLANNING_SYSTEM = """You are a senior front-end engineer acting as a technical planner. You receive a detailed product spec and produce a complete build brief for a code generator.

The generator will output: index.html, style.css, script.js, and optionally data.json. No CDNs, no external scripts. Persistence via localStorage or inline data.json only.

Your build brief must be exhaustive and unambiguous. Include:

- **Architecture**: how the app is structured (e.g. single-page with JS-toggled sections, MVC pattern, event-driven state, etc.)
- **HTML structure**: every major element, section, and <template> needed. All content must live inside .container — call this out explicitly.
- **State & data**: exact shape of localStorage data, initial seed data if needed, state variables and what triggers re-renders. List every localStorage key name that will be used.
- **JS modules/classes**: name each major function or class, what it owns, how components communicate. List every element ID that JS will query, so the HTML author knows to include them.
- **All features**: enumerate every feature with enough detail that the generator can implement it without guessing.
- **CSS inventory**: for every key element, specify exact values — font-size, padding, color token, display mode. Example: "#counter-display: font-size 5rem, font-weight 700, color var(--accent), text-align center". Never leave hero element sizing implicit.
- **Button hierarchy**: explicitly declare which buttons are primary (accent background), secondary (outlined), or ghost — and their relative sizes/padding.
- **Animations**: name every transition or @keyframes animation, what triggers it, and what properties it affects.
- **Responsive breakpoints**: specify layout changes at 375px and any other breakpoints needed.
- **Edge cases & polish**: empty states, validation rules, error messages, keyboard shortcuts, focus management.

Write the brief as a structured technical document (headings + short bullet lists). Do not output code. Be specific enough that two different engineers given this brief would build nearly identical apps."""


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
        # Step 1: Expand the short prompt into a full product spec
        update_job(job_id, step="expanding", progress=10)
        expanded_spec = expand_request(user_prompt)

        # Step 2: Plan the build — turn spec into a technical brief
        update_job(job_id, step="planning", progress=20)
        build_brief = plan_build(expanded_spec)

        # Step 3: Generate code from the brief
        update_job(job_id, step="generating", progress=35)
        spec_prompt = f"""Build a complete, production-quality static web microapp based on the build brief below.

A branded navbar (logo + brand) is auto-injected at the top — do not add your own navbar or header element.
A base stylesheet with design tokens is already applied — output only app-specific CSS using those variables.
Use class="container" for the main content wrapper (renders below the navbar).

## Build Brief
{build_brief}

## Original Request (for context)
{user_prompt}

Return JSON only — key "files", array of {{"path": "...", "content": "..."}} covering index.html, style.css, script.js (and data.json if needed).
Implement every feature in the brief. Write complete, working code — no placeholders, no TODOs, no stubs.

## Pre-flight checklist — verify ALL of these before returning your JSON:
- [ ] Every visible element (h1, sections, all content) is inside .container — nothing sits between the navbar and .container in the DOM
- [ ] <script> tag has NO type="module" unless the JS contains actual import statements
- [ ] Every id queried in script.js via getElementById/querySelector exists in index.html
- [ ] Every CSS class toggled in script.js via classList has a rule defined in style.css
- [ ] Every localStorage.getItem('key') has an exactly matching localStorage.setItem('key')
- [ ] No inline event handlers (onclick, onchange) anywhere in index.html — all events bound in script.js
- [ ] Every <button> has visible text or an aria-label
- [ ] Every <label for="x"> has a matching id="x" on an input element
- [ ] The hero/primary display element uses font-size ≥ 4rem in style.css
- [ ] All button labels fit on one line (min-width and padding set explicitly)
- [ ] The app is functional and visually polished at both 375px and 1200px widths
"""
        out = call_llm(spec_prompt)
        files = out.get("files", [])
        write_files(workdir, files)

        # Step 4: Validate and iteratively fix
        for i in range(MAX_ITERS):
            update_job(job_id, step="validating", progress=50 + i * 10)
            issues = validate_project(workdir)

            if not issues:
                break

            update_job(job_id, step="fixing", progress=60 + i * 10)
            current = {}
            for name in ["index.html", "style.css", "script.js", "data.json"]:
                p = os.path.join(workdir, name)
                if os.path.exists(p):
                    with open(p, "r", encoding="utf-8") as fp:
                        current[name] = fp.read()

            fix_prompt = f"""The generated app has validation issues that must ALL be fixed completely.

## Issues Found
{json.dumps(issues, indent=2)}

## Current Files
{json.dumps(current, indent=2)}

## Original Build Brief (for reference)
{build_brief}

Return JSON only — key "files", full corrected array. Rules:
- Fix every issue listed above without exception.
- Preserve all existing features — do not remove functionality to make fixes easier.
- Output complete file contents only — no truncation, no "... rest unchanged ..." comments.

## Pre-flight checklist — verify ALL before returning:
- [ ] Every visible element is inside .container — nothing between navbar and .container
- [ ] <script> tag has no type="module" unless JS contains actual import statements
- [ ] Every id queried in script.js exists in index.html
- [ ] Every CSS class toggled in script.js is defined in style.css
- [ ] Every localStorage.getItem key has a matching localStorage.setItem key
- [ ] No inline event handlers in index.html
- [ ] Every <button> has visible text or aria-label
- [ ] Every <label for="x"> has a matching id="x" input
- [ ] Hero display element uses font-size ≥ 4rem
- [ ] All button labels fit on one line
"""
            out = call_llm(fix_prompt)
            files = out.get("files", [])
            write_files(workdir, files)

        # Step 5: Upload or save locally
        update_job(job_id, step="uploading", progress=88)
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
