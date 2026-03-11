"""
Complex local test: Pomodoro timer app with settings and localStorage.
Uses Codex when USE_CODEX=1 (and CODEX_AUTH_JSON or codex login), otherwise OpenAI/Gemini.
"""
import os
import sys

from dotenv import load_dotenv
load_dotenv()

os.environ.setdefault("APPS_BUCKET", "")
os.environ.setdefault("PUBLIC_BASE_URL", "")

from agent import build_app, expand_request, plan_build

COMPLEX_PROMPT = """Build a single-page Pomodoro timer app with:
- Configurable work duration (default 25 min) and break duration (default 5 min), stored in localStorage.
- Large display showing current countdown (MM:SS).
- Buttons: Start, Pause, Reset. When timer hits 0, switch to break (or work) and optionally play a short sound or show an alert.
- Clean, modern CSS (dark theme is fine). Use only index.html, style.css, script.js; no external CDNs.
- Persist current phase (work/break) and remaining seconds in sessionStorage so refresh doesn't lose state.
"""


def mock_update_job(job_id: str, **kwargs: object) -> None:
    step = kwargs.get("step", "")
    progress = kwargs.get("progress", 0)
    duration = kwargs.get("duration_seconds")
    if duration is not None:
        print(f"  [100%] {step} — {duration}s")
    else:
        print(f"  [{progress}%] {step}")


def main() -> None:
    job_id = "local-complex-1"
    prompt = sys.argv[1] if len(sys.argv) > 1 else COMPLEX_PROMPT
    provider = "Codex" if os.environ.get("USE_CODEX", "").strip().lower() in ("1", "true", "yes") else "OpenAI/Gemini"
    print(f"Complex test (using {provider})")
    print(f"Job ID: {job_id}\n")
    print("Running agent (expand -> plan -> build)...")
    try:
        expanded_spec = expand_request(prompt)
        build_brief = plan_build(expanded_spec)
        result_url = build_app(job_id, build_brief, mock_update_job, user_prompt=prompt)
        print(f"\nDone. Result: {result_url}")
        print(f"Open: output/{job_id}/index.html in your browser.")
    except Exception as e:
        print(f"\nError: {e}")
        raise


if __name__ == "__main__":
    main()
