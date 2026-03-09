"use client";

import { useEffect, useRef, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

type Job = {
  jobId: string;
  status: string;
  step?: string;
  progress: number;
  resultUrl?: string | null;
  error?: string | null;
  updatedAt?: number | null;
};

const STEPS: { key: string; label: string }[] = [
  { key: "expanding", label: "Research" },
  { key: "planning", label: "Plan" },
  { key: "generating", label: "Generate" },
  { key: "validating", label: "Validate" },
  { key: "uploading", label: "Deploy" },
];

export default function AppBuilder() {
  const [prompt, setPrompt] = useState("");
  const [job, setJob] = useState<Job | null>(null);
  const [previewUrl, setPreviewUrl] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [apiError, setApiError] = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  async function createJob() {
    setApiError(null);
    if (!API_BASE) {
      setApiError("NEXT_PUBLIC_API_URL is not set.");
      return;
    }
    setIsSubmitting(true);
    setJob(null);
    setPreviewUrl("");
    try {
      const res = await fetch(`${API_BASE}/jobs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt }),
      });
      if (!res.ok) {
        const err = await res.text();
        setApiError(err || "Failed to create job");
        return;
      }
      const data = await res.json();
      setJob({ jobId: data.jobId, status: "queued", progress: 0 });
    } finally {
      setIsSubmitting(false);
    }
  }

  useEffect(() => {
    if (!job?.jobId || !API_BASE) return;
    if (job.status === "complete" || job.status === "failed") return;

    const timer = setInterval(async () => {
      try {
        const res = await fetch(`${API_BASE}/jobs/${job.jobId}`);
        const data = await res.json();
        setJob(data);
        if (data.status === "complete" && data.resultUrl) {
          setPreviewUrl(data.resultUrl);
          clearInterval(timer);
        }
        if (data.status === "failed") clearInterval(timer);
      } catch {
        /* keep polling */
      }
    }, 2000);

    return () => clearInterval(timer);
  }, [job?.jobId, job?.status]);

  const activeStepIndex = job?.step
    ? STEPS.findIndex((s) => s.key === job.step)
    : -1;

  function scrollToInput() {
    textareaRef.current?.scrollIntoView({
      behavior: "smooth",
      block: "center",
    });
    textareaRef.current?.focus();
  }

  return (
    <div>
      {/* Grain overlay */}
      <div className="grain" aria-hidden="true" />

      {/* Orb glow */}
      <div className="orb" aria-hidden="true" />

      {/* Vertical accent line */}
      <div className="vert-line" aria-hidden="true" />

      {/* Nav */}
      <nav className="nav">
        <div className="nav-logo" aria-label="App² logo">
          <img src="/logo.svg" alt="App² logo" width="36" height="36" />
        </div>

        <button
          type="button"
          className="nav-arrow"
          onClick={scrollToInput}
          aria-label="Get started"
        >
          <svg
            width="17"
            height="17"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <line x1="5" y1="12" x2="19" y2="12" />
            <polyline points="12 5 19 12 12 19" />
          </svg>
        </button>
      </nav>

      {/* Page */}
      <main className="page">
        {/* Hero */}
        <h1 className="hero-title">
          App<sup>2</sup>
        </h1>
        <p className="hero-sub">
          A social network of microapps
          <br />
          made by you, for you
        </p>

        {/* Prompt */}
        <div className="input-wrap">
          <textarea
            ref={textareaRef}
            className="prompt-area"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="Describe the app you want to build…"
            rows={4}
          />
          <button
            type="button"
            className="build-btn"
            onClick={createJob}
            disabled={!prompt.trim() || !API_BASE || isSubmitting}
          >
            {isSubmitting ? (
              <span className="spinner" />
            ) : (
              <>
                Build
                <svg
                  width="15"
                  height="15"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <line x1="5" y1="12" x2="19" y2="12" />
                  <polyline points="12 5 19 12 12 19" />
                </svg>
              </>
            )}
          </button>
        </div>

        {apiError && (
          <div className="error-banner" role="alert">
            {apiError}
          </div>
        )}

        {/* Job status */}
        {job && (
          <div className="job-card">
            <div className="job-header">
              <span className={`status-pill ${job.status}`}>{job.status}</span>
              <span className="job-id">{job.jobId.slice(-10)}</span>
            </div>

            {/* Pipeline steps */}
            <div className="pipeline">
              {STEPS.map((s, i) => {
                const isDone = job.status === "complete" || activeStepIndex > i;
                const isActive = job.step === s.key;
                return (
                  <div
                    key={s.key}
                    className={`pipe-step${isDone ? " done" : ""}${isActive ? " active" : ""}`}
                  >
                    <div className="pipe-dot" />
                    {i < STEPS.length - 1 && <div className="pipe-connector" />}
                    <span className="pipe-label">{s.label}</span>
                  </div>
                );
              })}
            </div>

            {/* Progress bar */}
            <div className="progress-track">
              <div
                className="progress-fill"
                style={{ width: `${job.progress}%` }}
              />
            </div>
            <div className="progress-text">{job.progress}%</div>

            {job.error && <pre className="error-block">{job.error}</pre>}
          </div>
        )}

        {/* Preview */}
        {previewUrl && (
          <div className="preview-wrap">
            <div className="preview-header">
              <span className="preview-label">Preview</span>
              <div className="preview-actions">
                <a
                  href={previewUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="preview-link"
                >
                  Open in new tab ↗
                </a>
                <button
                  type="button"
                  className="copy-btn"
                  onClick={() => navigator.clipboard.writeText(previewUrl)}
                >
                  Copy link
                </button>
              </div>
            </div>
            <iframe
              title="App preview"
              src={previewUrl}
              className="preview-frame"
              sandbox="allow-scripts allow-forms"
            />
          </div>
        )}
      </main>
    </div>
  );
}
