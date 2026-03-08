"""Simple validation for generated static app files."""
import os


def validate_project(workdir: str) -> list[str]:
    issues = []

    idx = os.path.join(workdir, "index.html")
    js = os.path.join(workdir, "script.js")
    css = os.path.join(workdir, "style.css")

    if not os.path.exists(idx):
        issues.append("Missing index.html")
        return issues

    html = open(idx, "r", encoding="utf-8").read()

    if "script.js" not in html:
        issues.append("index.html must include script.js with a relative path")

    if "style.css" not in html:
        issues.append("index.html must include style.css with a relative path")

    if "http://" in html or "https://" in html:
        issues.append(
            "Do not use external scripts/styles for MVP (no CDNs)"
        )

    if not os.path.exists(js):
        issues.append("Missing script.js")
    else:
        jst = open(js, "r", encoding="utf-8").read().strip()
        if len(jst) < 20:
            issues.append("script.js seems too small / empty")

    if not os.path.exists(css):
        issues.append("Missing style.css")

    return issues
