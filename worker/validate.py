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

def _snippet(
    content: str,
    start_pos: int | None = None,
    line_no: int | None = None,
    context_lines: int = 2,
) -> str:
    """Return a small window of lines (e.g. line_no ± context_lines) from content.
    If start_pos is given and line_no is not, derive line number from content[:start_pos].
    """
    if line_no is None and start_pos is not None:
        line_no = content[:start_pos].count("\n") + 1
    if line_no is None:
        return ""
    lines = content.splitlines()
    total = len(lines)
    if total == 0:
        return ""
    low = max(1, line_no - context_lines)
    high = min(total, line_no + context_lines)
    # 1-based to 0-based
    window = lines[low - 1 : high]
    return "\n".join(window)

def _read(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def _extract_js_queried_ids(js: str) -> set[str]:
    """Return all ids passed to getElementById or querySelector('#id')."""
    ids: set[str] = set()
    for m in re.finditer(r'getElementById\(["\']([^"\']+)["\']\)', js):
        ids.add(m.group(1))
    for m in re.finditer(r'querySelector\(["\']#([A-Za-z0-9_-]+)["\']\)', js):
        ids.add(m.group(1))
    return ids


def _extract_js_queried_ids_with_positions(js: str) -> list[tuple[str, int]]:
    """Return [(id, start_pos)] for getElementById/querySelector('#id')."""
    out: list[tuple[str, int]] = []
    for m in re.finditer(r'getElementById\(["\']([^"\']+)["\']\)', js):
        out.append((m.group(1), m.start()))
    for m in re.finditer(r'querySelector\(["\']#([A-Za-z0-9_-]+)["\']\)', js):
        out.append((m.group(1), m.start()))
    return out


def _extract_js_toggled_classes(js: str) -> set[str]:
    """Return all class names passed to classList.add/remove/toggle."""
    classes: set[str] = set()
    for m in re.finditer(
        r'classList\.(?:add|remove|toggle)\(["\']([^"\']+)["\']\)', js
    ):
        for cls in m.group(1).split():
            classes.add(cls)
    return classes


def _extract_js_toggled_classes_with_positions(js: str) -> list[tuple[str, int]]:
    """Return [(class_string, start_pos)]; class_string may contain space-separated classes."""
    out: list[tuple[str, int]] = []
    for m in re.finditer(
        r'classList\.(?:add|remove|toggle)\(["\']([^"\']+)["\']\)', js
    ):
        out.append((m.group(1), m.start()))
    return out


def _extract_localstorage_get_with_positions(js: str) -> list[tuple[str, int]]:
    """Return [(key, start_pos)] for localStorage.getItem."""
    out: list[tuple[str, int]] = []
    for m in re.finditer(r'localStorage\.getItem\(["\']([^"\']+)["\']\)', js):
        out.append((m.group(1), m.start()))
    return out


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

# Sass/SCSS-only functions (invalid in plain CSS). Exclude rgba/hsla — those are valid in plain CSS.
_SCSS_FUNCTIONS = re.compile(
    r'\b(darken|lighten|mix|saturate|desaturate|adjust-hue)\s*\('
)


# ─── Main validator ───────────────────────────────────────────────────────────

def validate_project(workdir: str) -> list[dict]:
    """
    Run all static checks against the files in workdir.
    Returns a list of issue dicts: [{check, severity, message}]
    severity is "error" (must fix) or "warning" (should fix).
    """
    issues: list[dict] = []

    def error(check: str, msg: str, file: str | None = None, snippet: str | None = None, fix_file: str | None = None):
        issue = {"check": check, "severity": "error", "message": msg}
        if file is not None:
            issue["file"] = file
        if snippet is not None:
            issue["snippet"] = snippet
        if fix_file is not None:
            issue["fix_file"] = fix_file
        issues.append(issue)

    def warning(check: str, msg: str, file: str | None = None, snippet: str | None = None, fix_file: str | None = None):
        issue = {"check": check, "severity": "warning", "message": msg}
        if file is not None:
            issue["file"] = file
        if snippet is not None:
            issue["snippet"] = snippet
        if fix_file is not None:
            issue["fix_file"] = fix_file
        issues.append(issue)

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
    inline_pattern = re.compile(r"\bon\w+\s*=", re.IGNORECASE)
    inline_matches = list(inline_pattern.finditer(html))
    for idx, handler in enumerate(analyzer.inline_handlers):
        pos = inline_matches[idx].start() if idx < len(inline_matches) else None
        snippet = _snippet(html, start_pos=pos, context_lines=2) if pos is not None else ""
        error(
            "inline_handlers",
            f"Inline event handler found in HTML: {handler}. "
            "All events must be bound in JS via addEventListener.",
            file="index.html",
            snippet=snippet or None,
        )

    # ── 7. Button accessibility ──────────────────────────────────────────────
    button_positions = [m.start() for m in re.finditer(r"<button\b", html, re.IGNORECASE)]
    for i, btn in enumerate(analyzer.buttons):
        if not btn["text"] and not btn["aria_label"]:
            pos = button_positions[i] if i < len(button_positions) else None
            snippet = _snippet(html, start_pos=pos, context_lines=2) if pos is not None else ""
            error(
                "button_accessibility",
                f"Button #{i + 1} has no visible text and no aria-label attribute.",
                file="index.html",
                snippet=snippet or None,
            )

    # ── 8. Label/input pairing ───────────────────────────────────────────────
    for for_val in analyzer.label_fors:
        if for_val not in analyzer.input_ids:
            m = re.search(rf'\bfor\s*=\s*["\']?' + re.escape(for_val) + r'["\']?', html, re.IGNORECASE)
            snippet = _snippet(html, start_pos=m.start(), context_lines=2) if m else ""
            error(
                "label_input_pairing",
                f'<label for="{for_val}"> has no matching input/select/textarea with id="{for_val}".',
                file="index.html",
                snippet=snippet or None,
            )

    # ── 9. h1 outside .container ─────────────────────────────────────────────
    if analyzer.h1_outside_container:
        m = re.search(r"<h1\b", html, re.IGNORECASE)
        snippet = _snippet(html, start_pos=m.start(), context_lines=2) if m else ""
        error(
            "content_outside_container",
            "<h1> appears outside .container. All visible content must be inside .container.",
            file="index.html",
            snippet=snippet or None,
        )

    # ── 10. JS → HTML id cross-reference (per file, fix_file=index.html) ─────
    set_keys_all: set[str] = set()
    for js_path in js_files:
        with open(js_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        sk, _ = _extract_localstorage_keys(content)
        set_keys_all |= sk

    for js_path in js_files:
        rel_js = os.path.relpath(js_path, workdir).replace("\\", "/")
        content = _read(js_path)
        for qid, pos in _extract_js_queried_ids_with_positions(content):
            if qid not in analyzer.ids:
                snippet = _snippet(content, start_pos=pos, context_lines=2)
                error(
                    "js_dom_reference",
                    f'JS queries id="{qid}" but no element with that id exists in index.html.',
                    file=rel_js,
                    snippet=snippet,
                    fix_file="index.html",
                )

    # ── 11. JS classList → CSS class cross-reference (per file) ───────────────
    if css and css_files:
        defined = _extract_css_defined_classes(css)
        rel_css = os.path.relpath(css_files[0], workdir).replace("\\", "/")
        for js_path in js_files:
            rel_js = os.path.relpath(js_path, workdir).replace("\\", "/")
            content = _read(js_path)
            for class_str, pos in _extract_js_toggled_classes_with_positions(content):
                for cls in class_str.split():
                    if cls not in defined:
                        snippet = _snippet(content, start_pos=pos, context_lines=2)
                        error(
                            "js_css_class_reference",
                            f'JS toggles class "{cls}" via classList but ".{cls}" is not defined in any CSS file.',
                            file=rel_js,
                            snippet=snippet,
                            fix_file=rel_css,
                        )
                        break  # one issue per match

    # ── 12. localStorage key consistency (per file) ───────────────────────────
    for js_path in js_files:
        rel_js = os.path.relpath(js_path, workdir).replace("\\", "/")
        content = _read(js_path)
        for key, pos in _extract_localstorage_get_with_positions(content):
            if key not in set_keys_all:
                snippet = _snippet(content, start_pos=pos, context_lines=2)
                warning(
                    "localstorage_keys",
                    f'localStorage.getItem("{key}") is called but localStorage.setItem("{key}") '
                    "was never found. Possible key name typo.",
                    file=rel_js,
                    snippet=snippet,
                )

    # ── 13. CSS: no SCSS functions (per file) ─────────────────────────────────
    for css_path in css_files:
        content = _read(css_path)
        rel_css = os.path.relpath(css_path, workdir).replace("\\", "/")
        for m in _SCSS_FUNCTIONS.finditer(content):
            snippet = _snippet(content, start_pos=m.start(), context_lines=2)
            error(
                "css_scss_functions",
                f'CSS: "{m.group(0)}" is a Sass/SCSS function and is invalid in plain CSS.',
                file=rel_css,
                snippet=snippet,
            )

    # ── 14. CSS: no redefinition of base variables (per file) ───────────────────
    for css_path in css_files:
        content = _read(css_path)
        rel_css = os.path.relpath(css_path, workdir).replace("\\", "/")
        for block_m in re.finditer(r':root\s*\{([^}]*)\}', content, re.DOTALL):
            block = block_m.group(1)
            for var_m in re.finditer(r'(--[A-Za-z][A-Za-z0-9_-]*)\s*:', block):
                var = var_m.group(1)
                if var in _BASE_VARS:
                    # Position of var in full content
                    pos = block_m.start(1) + var_m.start()
                    snippet = _snippet(content, start_pos=pos, context_lines=2)
                    error(
                        "css_base_var_redefinition",
                        f'CSS redefines base variable "{var}" in :root. '
                        "These are provided by the base stylesheet — remove the redefinition.",
                        file=rel_css,
                        snippet=snippet,
                    )

    # ── 15. JS syntax via Node.js ─────────────────────────────────────────────
    if js_files:
        for js_path in js_files:
            if os.path.exists(js_path):
                node_error = _check_node_syntax(js_path)
                if node_error:
                    content = _read(js_path)
                    snippet = _snippet(content, line_no=1, context_lines=4)
                    rel_js = os.path.relpath(js_path, workdir).replace("\\", "/")
                    error(
                        "js_syntax",
                        f"{os.path.basename(js_path)} has a syntax error:\n{node_error}",
                        file=rel_js,
                        snippet=snippet,
                    )

    return issues