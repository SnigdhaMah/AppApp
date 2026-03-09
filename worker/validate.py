"""Static validation for generated microapps.

Checks performed:
  1.  Required files present (index.html, style.css, script.js)
  2.  HTML parses without unclosed or misnested tags
  3.  index.html explicitly links both style.css and script.js
  4.  Linked assets exist on disk; no external CDN URLs in <link> or <script>
  5.  No <script type="module"> without actual import statements
  6.  No inline event handlers (onclick, onchange, oninput, etc.)
  7.  Every <button> has visible text content or an aria-label
  8.  Every <label for="x"> has a matching input/select/textarea with id="x"
  9.  All visible content is inside .container (h1 not stranded outside it)
  10. Every id queried in JS via getElementById/querySelector exists in HTML
  11. Every CSS class toggled in JS via classList is defined in style.css
  12. localStorage key consistency (getItem keys have matching setItem keys)
  13. No SCSS/Sass functions in plain CSS (darken, lighten, mix, etc.)
  14. No :root block redefining reserved base CSS variables
  15. JS syntax check via `node --check` (if Node.js is available)
"""

import os
import re
import subprocess
from html.parser import HTMLParser


# ─── HTML parser ─────────────────────────────────────────────────────────────

class _HTMLAnalyzer(HTMLParser):
    """Extract structural information from index.html in one pass."""

    # Tags that don't need a closing tag
    VOID_TAGS = {
        "area", "base", "br", "col", "embed", "hr", "img", "input",
        "link", "meta", "param", "source", "track", "wbr",
    }

    def __init__(self):
        super().__init__()
        self.tag_stack: list[str] = []
        self.unclosed: list[str] = []        # tags left open at EOF
        self.misnested: list[str] = []       # unexpected closing tags

        self.ids: set[str] = set()           # all id= values in the doc
        self.input_ids: set[str] = set()     # id= on input/select/textarea
        self.label_fors: list[str] = []      # for= values on <label>
        self.buttons: list[dict] = []        # {text, aria_label} per button
        self.inline_handlers: list[str] = [] # e.g. onclick="..."

        # Track whether content lives inside .container
        self._container_depth: int = 0      # >0 when inside .container
        self._body_depth: int = 0
        self._navbar_depth: int = 0         # skip navbar content
        self.h1_outside_container: bool = False

        # Current button being parsed
        self._in_button: bool = False
        self._button_text: str = ""
        self._current_button_aria: str = ""

        self.has_module_script: bool = False
        self.linked_css: list[str] = []
        self.linked_js: list[str] = []

    def handle_starttag(self, tag: str, attrs: list):
        attr = dict(attrs)

        # Track ids
        if "id" in attr:
            self.ids.add(attr["id"])
            if tag in ("input", "select", "textarea"):
                self.input_ids.add(attr["id"])

        # Track <label for>
        if tag == "label" and "for" in attr:
            self.label_fors.append(attr["for"])

        # Track inline handlers
        handler_attrs = {k for k, _ in attrs if k.startswith("on")}
        for h in handler_attrs:
            self.inline_handlers.append(f'<{tag} {h}="...">')

        # Track linked assets
        if tag == "link" and attr.get("rel") == "stylesheet" and "href" in attr:
            self.linked_css.append(attr["href"])
        if tag == "script":
            if attr.get("type") == "module":
                self.has_module_script = True
            if "src" in attr:
                self.linked_js.append(attr["src"])

        # Track container depth
        classes = attr.get("class", "").split()
        if "navbar" in classes or tag == "nav":
            self._navbar_depth += 1
        if "container" in classes:
            self._container_depth += 1

        if tag == "body":
            self._body_depth += 1

        # h1 outside container (and outside navbar)
        if tag == "h1" and self._container_depth == 0 and self._navbar_depth == 0:
            self.h1_outside_container = True

        # Button tracking
        if tag == "button":
            self._in_button = True
            self._button_text = ""
            self._current_button_aria = attr.get("aria-label", "")

        if tag not in self.VOID_TAGS:
            self.tag_stack.append(tag)

    def handle_endtag(self, tag: str):
        if tag == "button" and self._in_button:
            self.buttons.append({
                "text": self._button_text.strip(),
                "aria_label": self._current_button_aria,
            })
            self._in_button = False

        # Unwind container/navbar depth
        if tag in ("nav",):
            self._navbar_depth = max(0, self._navbar_depth - 1)
        if tag in ("main", "div", "section", "article"):
            if self._container_depth > 0:
                self._container_depth -= 1

        if self.tag_stack and self.tag_stack[-1] == tag:
            self.tag_stack.pop()
        elif tag not in self.VOID_TAGS:
            self.misnested.append(f"Unexpected </{tag}>")

    def handle_data(self, data: str):
        if self._in_button:
            self._button_text += data

    def close(self):
        super().close()
        self.unclosed = list(self.tag_stack)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _read(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def _extract_js_queried_ids(js: str) -> set[str]:
    """Return all ids passed to getElementById or querySelector('#id')."""
    ids: set[str] = set()
    # getElementById('foo') or getElementById("foo")
    for m in re.finditer(r'getElementById\(["\']([^"\']+)["\']\)', js):
        ids.add(m.group(1))
    # querySelector('#foo') — only bare #id selectors
    for m in re.finditer(r'querySelector\(["\']#([A-Za-z0-9_-]+)["\']\)', js):
        ids.add(m.group(1))
    return ids


def _extract_js_toggled_classes(js: str) -> set[str]:
    """Return all class names passed to classList.add/remove/toggle."""
    classes: set[str] = set()
    for m in re.finditer(
        r'classList\.(?:add|remove|toggle)\(["\']([^"\']+)["\']\)', js
    ):
        # May be space-separated multiple classes
        for cls in m.group(1).split():
            classes.add(cls)
    return classes


def _extract_css_defined_classes(css: str) -> set[str]:
    """Return all class names that have at least one rule in the CSS."""
    classes: set[str] = set()
    for m in re.finditer(r'\.([A-Za-z][A-Za-z0-9_-]*)', css):
        classes.add(m.group(1))
    return classes


def _extract_localstorage_keys(js: str) -> tuple[set[str], set[str]]:
    """Return (set_keys, get_keys) from localStorage calls."""
    set_keys: set[str] = set()
    get_keys: set[str] = set()
    for m in re.finditer(r'localStorage\.setItem\(["\']([^"\']+)["\']\s*,', js):
        set_keys.add(m.group(1))
    for m in re.finditer(r'localStorage\.getItem\(["\']([^"\']+)["\']\)', js):
        get_keys.add(m.group(1))
    return set_keys, get_keys


def _has_import_statements(js: str) -> bool:
    return bool(re.search(r'^\s*import\s+', js, re.MULTILINE))


def _check_node_syntax(js_path: str) -> str | None:
    """Run `node --check` on the JS file. Returns error string or None if OK."""
    try:
        result = subprocess.run(
            ["node", "--check", js_path],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            # Trim noisy absolute path from error
            msg = (result.stderr or result.stdout).strip()
            msg = msg.replace(js_path, os.path.basename(js_path))
            return msg
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass  # Node not available — skip
    return None


# ─── Base CSS reserved variables ─────────────────────────────────────────────

_BASE_VARS = {
    "--bg", "--surface", "--surface-hover", "--text", "--text-muted",
    "--accent", "--accent-hover", "--accent-text", "--border",
    "--radius", "--radius-sm", "--shadow", "--shadow-hover",
    "--space-xs", "--space-sm", "--space-md", "--space-lg", "--space-xl",
}

_SCSS_FUNCTIONS = re.compile(
    r'\b(darken|lighten|mix|saturate|desaturate|rgba|hsla|adjust-hue)\s*\('
)


# ─── Main validator ───────────────────────────────────────────────────────────

def validate_project(workdir: str) -> list[dict]:
    """
    Run all static checks against the files in workdir.
    Returns a list of issue dicts: [{check, severity, message}]
    severity is "error" (must fix) or "warning" (should fix).
    """
    issues: list[dict] = []

    def error(check: str, msg: str):
        issues.append({"check": check, "severity": "error", "message": msg})

    def warning(check: str, msg: str):
        issues.append({"check": check, "severity": "warning", "message": msg})

    html_path = os.path.join(workdir, "index.html")

    # ── 1. Required files & Richness ─────────────────────────────────────────
    if not os.path.exists(html_path):
        error("required_files", "index.html is missing")
        return issues  # can't continue without HTML

    html = _read(html_path)

    css_files = []
    js_files = []
    total_lines = 0

    for root, _, files in os.walk(workdir):
        for name in files:
            path = os.path.join(root, name)
            if name.endswith(".css"):
                css_files.append(path)
            elif name.endswith(".js"):
                js_files.append(path)
            
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                total_lines += len(f.readlines())

    if total_lines < 1200:
        warning("project_size", f"Project too small: only {total_lines} total lines across all files. It lacks product-grade complexity. Add more architecture, views, or reusable components unless explicitly requested otherwise.")

    if not css_files:
        error("required_files", "No CSS files found")
    if not js_files:
        error("required_files", "No JS files found")

    css = "\n".join(_read(p) for p in css_files)
    js = "\n".join(_read(p) for p in js_files)

    # ── 2. HTML structure ────────────────────────────────────────────────────
    analyzer = _HTMLAnalyzer()
    analyzer.feed(html)
    analyzer.close()

    for tag in analyzer.unclosed:
        if tag not in ("html", "body", "head"):  # browsers auto-close these
            error("html_structure", f"Unclosed <{tag}> tag in index.html")

    for msg in analyzer.misnested:
        warning("html_structure", f"{msg} in index.html")

    # ── 3. HTML references both required assets ──────────────────────────────
    if not analyzer.linked_css:
        error("linked_assets", "index.html does not link any CSS. Add <link rel='stylesheet' href='./style.css'> or similar.")
    if not analyzer.linked_js:
        error("linked_assets", "index.html does not include any JS. Add <script src='./script.js'></script> or similar.")

    # ── 4. Linked assets exist on disk + no external CDNs ───────────────────
    for href in analyzer.linked_css:
        if href.startswith(("http://", "https://")):
            error("external_cdn", f"External stylesheet loaded from CDN: {href}. All assets must be self-contained.")
        else:
            rel = href.lstrip("./")
            if not os.path.exists(os.path.join(workdir, rel)):
                error("linked_assets", f"Linked stylesheet not found on disk: {href}")

    for src in analyzer.linked_js:
        if src.startswith(("http://", "https://")):
            error("external_cdn", f"External script loaded from CDN: {src}. All assets must be self-contained.")
        else:
            rel = src.lstrip("./")
            if not os.path.exists(os.path.join(workdir, rel)):
                error("linked_assets", f"Linked script not found on disk: {src}")

    # ── 5. type="module" without imports ─────────────────────────────────────
    if analyzer.has_module_script and not _has_import_statements(js):
        error(
            "module_script",
            '<script type="module"> is used but JS has no import statements. '
            "This will silently break the app on file:// URLs. "
            "Remove type=\"module\" from the <script> tag.",
        )

    # ── 6. Inline event handlers ─────────────────────────────────────────────
    for handler in analyzer.inline_handlers:
        error(
            "inline_handlers",
            f"Inline event handler found in HTML: {handler}. "
            "All events must be bound in JS via addEventListener.",
        )

    # ── 7. Button accessibility ──────────────────────────────────────────────
    for i, btn in enumerate(analyzer.buttons):
        if not btn["text"] and not btn["aria_label"]:
            error(
                "button_accessibility",
                f"Button #{i + 1} has no visible text and no aria-label attribute.",
            )

    # ── 8. Label/input pairing ───────────────────────────────────────────────
    for for_val in analyzer.label_fors:
        if for_val not in analyzer.input_ids:
            error(
                "label_input_pairing",
                f'<label for="{for_val}"> has no matching input/select/textarea with id="{for_val}".',
            )

    # ── 9. h1 outside .container ─────────────────────────────────────────────
    if analyzer.h1_outside_container:
        error(
            "content_outside_container",
            "<h1> appears outside .container. All visible content must be inside .container.",
        )

    # ── 10. JS → HTML id cross-reference ──────────────────────────────────────
    if js:
        queried_ids = _extract_js_queried_ids(js)
        for qid in queried_ids:
            if qid not in analyzer.ids:
                error(
                    "js_dom_reference",
                    f'JS queries id="{qid}" but no element with that id exists in index.html.',
                )

    # ── 11. JS classList → CSS class cross-reference ──────────────────────────
    if js and css:
        toggled = _extract_js_toggled_classes(js)
        defined = _extract_css_defined_classes(css)
        for cls in toggled:
            if cls not in defined:
                error(
                    "js_css_class_reference",
                    f'JS toggles class "{cls}" via classList but ".{cls}" is not defined in any CSS file.',
                )

    # ── 12. localStorage key consistency ──────────────────────────────────────
    if js:
        set_keys, get_keys = _extract_localstorage_keys(js)
        for key in get_keys:
            if key not in set_keys:
                warning(
                    "localstorage_keys",
                    f'localStorage.getItem("{key}") is called but localStorage.setItem("{key}") '
                    "was never found. Possible key name typo.",
                )

    # ── 13. CSS: no SCSS functions ────────────────────────────────────────────
    if css:
        for m in _SCSS_FUNCTIONS.finditer(css):
            line_no = css[: m.start()].count("\n") + 1
            error(
                "css_scss_functions",
                f'CSS: "{m.group(0)}" is a Sass/SCSS function and is invalid in plain CSS.',
            )

    # ── 14. CSS: no redefinition of base variables ────────────────────────────
    if css:
        root_blocks = re.findall(r':root\s*\{([^}]*)\}', css, re.DOTALL)
        for block in root_blocks:
            for var in re.findall(r'(--[A-Za-z][A-Za-z0-9_-]*)\s*:', block):
                if var in _BASE_VARS:
                    error(
                        "css_base_var_redefinition",
                        f'CSS redefines base variable "{var}" in :root. '
                        "These are provided by the base stylesheet — remove the redefinition.",
                    )

    # ── 15. JS syntax via Node.js ─────────────────────────────────────────────
    if js_files:
        for js_path in js_files:
            if os.path.exists(js_path):
                node_error = _check_node_syntax(js_path)
                if node_error:
                    error("js_syntax", f"{os.path.basename(js_path)} has a syntax error:\n{node_error}")

    return issues