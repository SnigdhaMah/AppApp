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
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o").strip()

MAX_ITERS = 3

SYSTEM_RULES = """
You are an expert front-end engineer generating a realistic, product-grade frontend prototype.

## Architecture Requirements
- Do not compress the app into a minimal demo.
- Build a realistic frontend with separated concerns.
- Use multiple CSS and JS files when allowed.
- HTML should define app shell, sections, and templates.
- JS must separate state, rendering, events, and utilities.
- CSS must separate layout, components, and responsive behavior.

## Minimum Complexity
- At least 3 major UI sections or views
- At least 5 reusable components/patterns
- At least 8 distinct interactive behaviors
- At least 1 derived state view
- At least 1 empty state and 1 populated state
- At least 2 responsive layout changes
- At least 1200 lines total across all generated files unless the brief clearly requires less

## Output Format
- Return ONLY valid JSON with shape: {"files":[{"path":"...","content":"..."}]}
- Allowed paths: index.html, data.json, styles/, scripts/, and assets/.
- Use relative paths in HTML.
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
  ALL event binding must be done in JS via addEventListener.
- Every <button> must have either visible text content or an aria-label attribute.

## JavaScript — write production-quality JS:
- Do NOT use <script type="module"> unless the script contains actual ES module
  import statements. For self-contained scripts, use a plain <script> tag.
  type="module" is blocked by browsers on file:// URLs and will silently break the app.
- Every id referenced via getElementById or querySelector MUST exist in index.html.
  Never query an element that isn't in the DOM.
- Every CSS class toggled via classList.add/remove/toggle MUST have a corresponding
  rule in a CSS file. Never toggle a class that has no styles defined.
- localStorage.getItem('key') and localStorage.setItem('key') must use identical key
  strings. Never read a key that was never written.
- Never derive state by reading from the DOM. All state must live in JS variables
  or a state object. The DOM is output-only — always read from state, write to DOM,
  never the reverse. Example of what NOT to do:
    BAD:  this.count = document.getElementById('display').textContent + 1;
    GOOD: this.count += 1; then update the DOM from this.count.
- Always guard localStorage reads against null before arithmetic. Use:
    parseInt(localStorage.getItem('key') ?? '0', 10) || 0
  Never pass null, undefined, or an empty string into parseInt, Number(), or
  any arithmetic operation — this produces NaN which silently corrupts all state.
- After any state mutation, validate that the new value is a finite number before
  saving or rendering: if (!Number.isFinite(this.count)) this.count = 0;
- Use modern ES6+ features: classes, async/await, destructuring, WeakMap, generators, etc.
- Structure code with clear separation: data layer, state management, rendering, events. **Crucially, ensure event handlers trigger state updates, and state updates trigger re-renders.**
- Implement rich interactivity: drag-and-drop, requestAnimationFrame animations, canvas,
  Web Audio API, real-time filtering/search, keyboard shortcuts, undo/redo — as warranted.
- Handle edge cases: empty states, input validation with clear error feedback,
  loading indicators, debounced inputs.
- Write helper utilities (uuid(), deepClone(), formatDate()) inline — no placeholders.

## CSS & UX — design like a modern iOS/Android App, not a webpage:
- Layout: Use app-like paradigms. Do not just stack inputs in a column. Use bottom tab bars for navigation, floating action buttons (FABs) for primary actions, and horizontal scrolling carousels for lists where appropriate.
- Hierarchy: Use a large, bold hero element for the primary metric/focus (font-size >= 4rem, font-weight >= 700). Make the primary call-to-action massive and prominent at the bottom of the screen.
- Interactions: Build hover/active states that mimic physical touch (scale down slightly, change shadow). Add micro-animations and transitions to all state changes.
- Empty states: Build beautiful, friendly empty states with descriptive text and clear calls to action when lists are empty.
- Use CSS custom properties (--bg, --surface, --text, --text-muted, --accent,
  --accent-hover, --accent-text, --border, --radius, --radius-sm, --radius-lg,
  --radius-pill, --shadow, --shadow-hover, --shadow-lg, --shadow-card, --shadow-inset,
  --gradient-subtle, --space-xs, --space-sm, --space-md, --space-lg, --space-xl).
  Do NOT redefine these in :root — they are provided by the base stylesheet.
- Do NOT redefine body, .container, or global button/input styles from the base.
- Output ONLY app-specific rules. Every key element must have explicit sizing:
  specify font-size, padding, and display mode — never leave hero elements unstyled.
- **Tabs / bottom nav:** Inactive tabs must be ghost or muted (e.g. color: var(--text-muted), no fill).
  Only the active tab uses accent background or strong weight. Never style every tab as primary (solid accent).
- **Depth and polish:** Use layered shadows for cards (e.g. --shadow-card or --shadow-lg). Add subtle
  transitions (e.g. transition: box-shadow 0.2s, transform 0.2s) on interactive elements.
- **Inputs and controls:** Range sliders and all inputs must be styled (track, thumb, focus) using design
  tokens; avoid raw browser-default appearance.
- **Typography:** Clear type scale — hero ≥ 4rem, section titles ≥ 1.25rem, labels smaller and muted.
  Use letter-spacing and font-weight for hierarchy, not only size.
- Primary display values (counters, scores, results) must use font-size ≥ 4rem.
- All buttons must have enough padding and min-width that their labels never wrap.
- Define explicit button hierarchy: exactly ONE button per view/group is primary
  (accent background). All others must be secondary (outlined) or ghost. Never
  style two sibling buttons as primary — it destroys hierarchy.
- Button groups must always use a flex container with gap: var(--space-sm).
  Never let a button group stack vertically on desktop. Set flex-wrap: wrap only
  as a mobile fallback, never as the default layout.
- Flex containers that allow wrapping MUST set row-gap explicitly (using
  --space-sm or larger) in addition to column gap. Never rely on gap shorthand
  alone — wrapped rows will have no vertical breathing room without row-gap.
- Use CSS Grid and Flexbox for layouts. Add @keyframes animations where meaningful.
- Implement responsive breakpoints. App must work cleanly at 375px and 1200px widths.
- Every CSS class toggled by JS must be defined here with actual property values.

## Design System
- A branded navbar (logo + "Build Apps") is auto-injected at the top — do not add your own.
- Use class .container for the main content wrapper (already styled; appears below navbar).
- The base stylesheet provides all design tokens. Layer your app-specific styles on top.

## Visual Quality Bar — every app must meet these before output:
- Clear visual hierarchy: one dominant hero element (the main value, CTA, or display).
- The app title / h1 must be styled with font-weight ≥ 600 and font-size ≥ 1.25rem.
  Never leave the title as plain unstyled body text.
- Exactly ONE button per view is primary (accent bg). All others are secondary or ghost.
- **Bottom nav / tabs:** Only the active tab is primary (accent or bold); inactive tabs are ghost or
  muted (transparent background, color: var(--text-muted)). Never style all tabs as solid accent.
- All button groups are in a single flex row — no stacking on desktop viewports.
- Consistent spacing using only --space-* variables — no magic pixel numbers.
- All interactive elements have hover and focus states defined in CSS.
- No text or elements overflow or clip their container at any viewport width.
- Only include UI elements (buttons, sections, inputs) that are in the build brief.
  Do not invent extra controls (Help, Info, Settings) unless explicitly specified.
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
5. **UI layout** — Describe the screens or sections, how they're organized, what's always visible vs. toggled. Design for a mobile-first APP feel, not a desktop webpage (e.g. use bottom nav bars, floating action buttons, full height views, cards instead of raw text).
6. **Visual personality** — What should this app feel like to use? Describe the intended emotional quality (e.g. "satisfying and tactile like a physical counter", "calm and focused like a meditation tool", "energetic and gamified like a fitness tracker"). This will directly guide typography scale, animation style, and color usage decisions. Also give one sentence on **visual style** — e.g. "Soft and premium (strong shadows, rounded corners, muted palette)" or "Clear and medical (high contrast, simple shapes)" — so the planner can turn it into concrete CSS directives.
7. **Delight details** — Small UX touches that make the app feel polished: keyboard shortcuts, animations, empty states, undo, smart defaults, progress indicators, etc.

Constraints: static site only (HTML/CSS/JS), no backend, no auth, localStorage or small data.json for persistence, no external CDNs.

Be specific and complete. The planner will turn this into a build brief for an engineer.

**Completeness check**: after writing the spec, re-read the original request and verify
every sentence maps to at least one feature in the spec. Call out any requirement you
chose to omit and explicitly justify why. Never silently drop features."""

# Planning: turn expanded spec into a concrete, detailed build brief
PLANNING_SYSTEM = """You are a senior front-end engineer acting as a technical planner. You receive a detailed product spec and produce a complete build brief for a code generator.

The generator will output multiple files. Allowed paths include index.html, data.json, and files under styles/ and scripts/ directories. No CDNs, no external scripts. Persistence via localStorage or inline data.json only.

Your build brief must be exhaustive and unambiguous. Include:

- **Required file tree**: explicitly list every file the generator must create.
- **Component map**: list each component and which file owns it.
- **Render flow**: list what file triggers initial render, what file owns state, and what file binds events.
- **Architecture**: how the app is structured (e.g. single-page with JS-toggled sections, MVC pattern, event-driven state, etc.)
- **HTML structure**: every major element, section, and <template> needed. All content must live inside .container — call this out explicitly. Design like an iOS/Android app (bottom tab bars, floating action buttons, clean cards).
- **State & data**: exact shape of localStorage data, initial seed data if needed, state variables and **the exact mechanism for triggering re-renders (e.g. event listeners calling render() after state mutation).** List every localStorage key name that will be used.
- **JS modules/classes**: name each major function or class, what it owns, how components communicate. List every element ID that JS will query, so the HTML author knows to include them.
- **All features**: enumerate every feature with enough detail that the generator can implement it without guessing.
- **CSS inventory**: for every key element, specify exact values — font-size, padding, color token, display mode. Example: "#counter-display: font-size 5rem, font-weight 700, color var(--accent), text-align center". Never leave hero element sizing implicit.
- **Visual spec from personality**: Translate the spec's **Visual personality** into 2–3 concrete CSS directives (e.g. "soft shadows and rounded corners" → use --shadow-lg, --radius-lg on cards; "calm and minimal" → muted palette, generous whitespace). Include these in the brief so the generator applies a consistent visual style.
- **Tab bar / bottom nav**: If the app has a bottom nav or tab bar, the brief must specify its styling explicitly: container display flex, gap; active tab = background var(--accent), color var(--accent-text); inactive tabs = background transparent, color var(--text-muted) (ghost). Never specify that all tabs use the same primary style.
- **Button hierarchy**: for every button group, name the ONE primary button and justify
  why it is primary. All other buttons must be explicitly labelled secondary (outlined
  border, no fill) or ghost (text only). Specify the exact flex container for each group:
  display flex, flex-direction row, gap value, alignment, and whether any button is
  full-width. Example: ".btn-group: display flex, flex-direction row, gap var(--space-sm),
  align-items center — Increment=primary, Decrement=secondary, Reset=ghost".
- **Brief discipline**: only include buttons and UI controls that are directly required
  by the feature list. Do not add utility buttons (Help, Info, About, Settings) unless
  the spec explicitly calls for them.
- **Animations**: name every transition or @keyframes animation, what triggers it, and what properties it affects.
- **Responsive breakpoints**: specify layout changes at 375px and any other breakpoints needed.
- **Edge cases & polish**: empty states, validation rules, error messages, keyboard shortcuts, focus management.
- **Prompt fidelity**: go through the original user request line by line and confirm every
  explicit feature has a corresponding section in this brief. Never omit, merge, or silently
  drop features. If a feature is intentionally out of scope, say so explicitly.
- **Phase-based apps**: if the app has multiple phases or modes (e.g. work/break, round/rest,
  active/paused), each phase must be:
  - Visually distinct — different label, color, or background on the phase indicator
  - Explicitly tracked in JS state with its own named variable
  - Listed with its transition trigger (what causes the switch) and the exact consequence
    (what changes in the UI, what resets, what plays/alerts)
  - All phases must be implemented — never implement only the first phase and stub the rest.

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


def _log_llm(name: str, sys_prompt: str, user_prompt: str, response: str) -> None:
    if not os.environ.get("APPS_BUCKET"):
        try:
            print(f"\n{'='*80}\n=== AI LOG: {name} ===")
            if sys_prompt:
                print(f"SYSTEM:\n{sys_prompt}\n")
            print(f"USER:\n{user_prompt}\n\n=== OUTPUT ===\n{response}\n{'='*80}\n")
        except UnicodeEncodeError:
            # Fallback for Windows console encoding issues with emojis/arrows
            print(f"USER:\n{user_prompt.encode('ascii', 'replace').decode('ascii')}\n\n=== OUTPUT ===\n{response.encode('ascii', 'replace').decode('ascii')}\n{'='*80}\n")

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
        _log_llm("Codex (JSON)", SYSTEM_RULES, prompt, raw)
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
    _log_llm("OpenAI (JSON)", SYSTEM_RULES, prompt, text)
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
    _log_llm("Gemini (JSON)", SYSTEM_RULES, prompt, text)
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
    text = (response.choices[0].message.content or "").strip()
    _log_llm("OpenAI (Text)", system_prompt, user_message, text)
    return text


def _call_gemini_text(system_prompt: str, user_message: str, api_key: str) -> str:
    import google.generativeai as genai

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        "gemini-1.5-flash",
        system_instruction=system_prompt,
    )
    response = model.generate_content(user_message)
    text = (response.text or "").strip()
    _log_llm("Gemini (Text)", system_prompt, user_message, text)
    return text


def _call_codex_text(system_prompt: str, user_message: str) -> str:
    import asyncio
    from openai_codex_sdk import Codex

    async def _run() -> str:
        codex = Codex(_codex_options())
        thread = codex.start_thread({"skip_git_repo_check": True})
        full_prompt = f"{system_prompt}\n\nUser:\n{user_message}"
        turn = await thread.run(full_prompt)
        text = (turn.final_response or "").strip()
        _log_llm("Codex (Text)", system_prompt, user_message, text)
        return text

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


def _copy_brand_assets(workdir: str) -> None:
    """Copy branded logo SVGs from worker/assets/ into workdir/assets/ so every app has them."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    assets_src = os.path.join(base_dir, "assets")
    assets_dst = os.path.join(workdir, "assets")
    if not os.path.isdir(assets_src):
        return
    os.makedirs(assets_dst, exist_ok=True)
    for name in ("logo.svg", "red_logo.svg"):
        src = os.path.join(assets_src, name)
        if os.path.isfile(src):
            dst = os.path.join(assets_dst, name)
            shutil.copy2(src, dst)


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
    """Prepend branded base.css to the first CSS file found so every app uses the same design system."""
    base_css = _get_base_css()
    if not base_css:
        return
        
    target_css = None
    for root, _, files in os.walk(workdir):
        for name in files:
            if name.endswith(".css"):
                target_css = os.path.join(root, name)
                break
        if target_css:
            break

    if not target_css:
        target_css = os.path.join(workdir, "style.css")
        with open(target_css, "w", encoding="utf-8") as f:
            f.write(base_css)
        return

    with open(target_css, "r", encoding="utf-8") as f:
        app_css = f.read()
    # Prepend base only if design tokens are not already defined (LLM often adds
    # "Base branded styles" comment without actually defining :root, so we check for tokens)
    has_tokens = ":root" in app_css and ("--bg:" in app_css or "--bg " in app_css)
    if not has_tokens:
        combined = "/* Base branded styles */\n" + base_css.rstrip() + "\n\n/* App-specific styles */\n" + app_css.lstrip()
        with open(target_css, "w", encoding="utf-8") as f:
            f.write(combined)


def write_files(workdir: str, files: list[dict]) -> None:
    ALLOWED_PATH_PREFIXES = (
        "index.html",
        "data.json",
        "styles/",
        "scripts/",
        "assets/",
    )
    if not isinstance(files, list):
        if isinstance(files, dict) and "path" in files:
            files = [files]
        else:
            files = []
            
    for f in files:
        if not isinstance(f, dict):
            continue
        path = (f.get("path") or "").strip().lstrip("/")
        if not path.startswith(ALLOWED_PATH_PREFIXES):
            continue
        content = f.get("content") or ""
        full = os.path.join(workdir, path)
        os.makedirs(os.path.dirname(full) or ".", exist_ok=True)
        with open(full, "w", encoding="utf-8") as fp:
            fp.write(content)
    _copy_brand_assets(workdir)
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
        spec_prompt = f"""Build a complete, production-quality static web app based on the build brief below.

This is not a toy demo. Build a realistic, product-grade frontend prototype.

Required:
- multi-file architecture
- clear view decomposition
- reusable components
- state separated from render logic (BUT state changes MUST trigger a re-render of the DOM! Use callbacks, events, or explicit render calls after state mutations)
- enough implementation depth that the app feels like a real product, not a coding exercise
- UI must feel like a modern iOS/Android App (floating action buttons, bottom tabs, clean padded cards, subtle shadows) — NOT a basic 2000s webpage.

A branded navbar (logo + brand) is auto-injected at the top — do not add your own navbar or header element.
A base stylesheet with design tokens is already applied — output only app-specific CSS using those variables.
Use class="container" for the main content wrapper (renders below the navbar).

## Build Brief
{build_brief}

## Original Request (for context)
{user_prompt}

Return JSON only — key "files", array of {{"path": "...", "content": "..."}} covering index.html, data.json, and all necessary CSS and JS files within styles/ and scripts/.
Implement every feature in the brief. Write complete, working code — no placeholders, no TODOs, no stubs.

**Bottom nav / tabs styling:** Bad: all four bottom tabs use background: var(--accent). Good: active tab = background: var(--accent), color: var(--accent-text); inactive tabs = background: transparent, color: var(--text-muted) (ghost).

## Pre-flight checklist — verify ALL of these before returning your JSON:
- [ ] Every visible element (h1, sections, all content) is inside .container — nothing sits between the navbar and .container in the DOM
- [ ] <script> tag has NO type="module" unless the JS contains actual import statements
- [ ] Every id queried in JS via getElementById/querySelector exists in index.html
- [ ] Every CSS class toggled in JS via classList has a rule defined in a CSS file
- [ ] Every localStorage.getItem('key') has an exactly matching localStorage.setItem('key')
- [ ] No inline event handlers (onclick, onchange) anywhere in index.html — all events bound in JS
- [ ] Every <button> has visible text or an aria-label
- [ ] Every <label for="x"> has a matching id="x" on an input element
- [ ] The hero/primary display element uses font-size ≥ 4rem in CSS
- [ ] State mutations ALWAYS trigger a UI re-render (check that event listeners actually call render() or a callback that updates the DOM)
- [ ] Every localStorage.getItem() call is guarded with || 0 or a safe fallback before arithmetic
- [ ] The h1/app title has font-weight ≥ 600 and font-size ≥ 1.25rem in CSS
- [ ] Exactly ONE button per view is styled as primary (accent bg) — all others are secondary or ghost
- [ ] Bottom nav / tabs: only one tab (active) is primary; inactive tabs are ghost or muted (transparent, var(--text-muted))
- [ ] Every button group uses a flex row container — no button group stacks vertically on desktop
- [ ] No buttons exist that are not in the build brief (no invented Help/Info/Settings buttons)
- [ ] All button labels fit on one line (min-width and padding set explicitly)
- [ ] The app is functional and visually polished at both 375px and 1200px widths
- [ ] Every feature explicitly mentioned in the original request exists in the output —
      go through the request line by line and verify each one
- [ ] Phase-based apps show the current phase name prominently in the UI at all times
- [ ] All phases are fully implemented — not just the first one
- [ ] Flex containers with flex-wrap have row-gap set explicitly
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
            for root, _, fs in os.walk(workdir):
                for name in fs:
                    p = os.path.join(root, name)
                    rel_path = os.path.relpath(p, workdir).replace("\\", "/")
                    with open(p, "r", encoding="utf-8") as fp:
                        current[rel_path] = fp.read()

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
- [ ] Every id queried in JS exists in index.html
- [ ] Every CSS class toggled in JS is defined in a CSS file
- [ ] Every localStorage.getItem key has a matching localStorage.setItem key
- [ ] No inline event handlers in index.html
- [ ] Every <button> has visible text or aria-label
- [ ] Every <label for="x"> has a matching id="x" input
- [ ] Hero display element uses font-size ≥ 4rem
- [ ] State mutations ALWAYS trigger a UI re-render (check that event listeners actually call render() or a callback that updates the DOM)
- [ ] Every localStorage.getItem() is guarded with a safe fallback before arithmetic
- [ ] h1/app title has font-weight ≥ 600 and font-size ≥ 1.25rem
- [ ] Exactly ONE button per view is primary — all others are secondary or ghost
- [ ] Every button group is a flex row — no stacking on desktop
- [ ] No invented buttons absent from the build brief
- [ ] All button labels fit on one line
- [ ] Every feature from the original request is present in the output
- [ ] All phases of phase-based apps are fully implemented
- [ ] Flex containers with flex-wrap have row-gap set
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
            for root, _, files in os.walk(workdir):
                for name in files:
                    src = os.path.join(root, name)
                    rel = os.path.relpath(src, workdir)
                    dst = os.path.join(out_dir, rel)
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    with open(src, "rb") as f:
                        open(dst, "wb").write(f.read())
            result_url = f"file://{os.path.abspath(out_dir)}/index.html"
            shutil.rmtree(workdir, ignore_errors=True)
            workdir = None
        return result_url

    finally:
        if workdir and os.path.exists(workdir):
            shutil.rmtree(workdir, ignore_errors=True)
