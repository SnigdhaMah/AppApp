"use client";

import Link from "next/link";
import React, { useEffect, useRef, useState } from "react";

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

const EXAMPLE_PROMPTS = [
  "Roommate expense splitter",
  "Workout tracker with streaks",
  "Study group planner",
  "Coffee chat scheduler",
];

const STEP_MESSAGES: Record<string, string> = {
  expanding: "Researching what your app needs",
  planning: "Planning structure and features",
  generating: "Generating your app",
  validating: "Checking and improving output",
  uploading: "Publishing your preview",
};

export default function AppBuilder() {
  const [prompt, setPrompt] = useState("");
  const [job, setJob] = useState<Job | null>(null);
  const [previewUrl, setPreviewUrl] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [apiError, setApiError] = useState<string | null>(null);
  const [copySuccess, setCopySuccess] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const trimmedPrompt = prompt.trim();
  const canSubmit = !!trimmedPrompt && !!API_BASE && !isSubmitting;

  async function createJob() {
    if (isSubmitting) return;
    setApiError(null);
    if (!API_BASE) {
      setApiError("App backend is not configured yet.");
      return;
    }
    setIsSubmitting(true);
    setJob(null);
    setPreviewUrl("");
    try {
      const res = await fetch(`${API_BASE}/jobs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: trimmedPrompt }),
      });
      if (!res.ok) {
        const err = await res.text();
        setApiError(err || "Failed to create job");
        return;
      }
      const data = await res.json();
      setJob({ jobId: data.jobId, status: "queued", progress: 0 });
    } catch {
      setApiError("Something went wrong while creating the job.");
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

  function handlePromptKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter" && canSubmit) {
      e.preventDefault();
      createJob();
    }
  }

  return (
    <div>
      {/* Grain overlay */}
      <div className="grain" aria-hidden="true" />

      {/* Orb glow */}
      <div className="orb" aria-hidden="true" />

      {/* Nav */}
      <nav
        className="nav"
        style={{
          padding: "10px 14px",
          height: "44px",
        }}
      >
        <Link href={"/"}>
          <div className="nav-logo" aria-label="App² logo">
            <img src="/logo.svg" alt="App² logo" width="26" height="26" />
          </div>
        </Link>
      </nav>

      {/* Page */}
      <main
        className="page"
        style={{
          padding: "12px 14px 24px",
          maxWidth: "100%",
        }}
      >
        {/* Hero */}
        <h1
          className="hero-title"
          style={{
            fontSize: "clamp(28px, 10vw, 42px)",
            marginBottom: "10px",
            marginTop: "8px",
          }}
        >
          App<sup style={{ fontSize: "0.5em" }}>2</sup>
        </h1>

        {/* Subtitle */}
        <div
          style={{
            marginBottom: "10px",
            fontSize: "12px",
            opacity: 0.7,
            lineHeight: 1.4,
          }}
        >
          Describe who the app is for, what it should do, and any key features.
        </div>

        {/* Input */}
        <div className="input-wrap" style={{ gap: "8px" }}>
          <textarea
            ref={textareaRef}
            className="prompt-area"
            value={prompt}
            onChange={(e) => {
              setPrompt(e.target.value);
              if (apiError) setApiError(null);
            }}
            onKeyDown={handlePromptKeyDown}
            placeholder="e.g. a roommate expense splitter for 4 college students"
            rows={3}
            style={{
              fontSize: "14px",
              padding: "10px 12px",
            }}
          />

          {/* Example chips — compact, 2-column wrap */}
          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              gap: "6px",
              marginTop: "2px",
            }}
          >
            {EXAMPLE_PROMPTS.map((example) => (
              <button
                key={example}
                type="button"
                onClick={() => {
                  setPrompt(example);
                  if (apiError) setApiError(null);
                  textareaRef.current?.focus();
                }}
                style={{
                  padding: "5px 10px",
                  borderRadius: "999px",
                  border: "1px solid rgba(255,255,255,0.18)",
                  background: "transparent",
                  color: "inherit",
                  cursor: "pointer",
                  fontSize: "11px",
                  lineHeight: 1.3,
                  whiteSpace: "nowrap",
                }}
              >
                {example}
              </button>
            ))}
          </div>

          <button
            type="button"
            className="build-btn"
            onClick={createJob}
            disabled={!canSubmit}
            style={{
              fontSize: "13px",
              padding: "11px 16px",
              marginTop: "4px",
              borderRadius: "10px",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: "6px",
            }}
          >
            {isSubmitting ? (
              <span className="spinner" />
            ) : (
              <>
                Generate App
                <svg
                  width="13"
                  height="13"
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
          <div
            className="error-banner"
            role="alert"
            style={{ fontSize: "12px", padding: "8px 12px", marginTop: "8px" }}
          >
            {apiError}
          </div>
        )}

        {/* Job status */}
        {job && (
          <div
            className="job-card"
            style={{
              padding: "12px",
              marginTop: "12px",
              borderRadius: "12px",
            }}
          >
            <div
              className="job-header"
              style={{ marginBottom: "10px", gap: "6px" }}
            >
              <span
                className={`status-pill ${job.status}`}
                style={{ fontSize: "10px", padding: "2px 8px" }}
              >
                {job.status}
              </span>
              <span
                className="job-id"
                style={{ fontSize: "10px", opacity: 0.5 }}
              >
                {job.jobId.slice(-8)}
              </span>
            </div>

            {/* Pipeline steps — compact horizontal row */}
            <div
              className="pipeline"
              style={{
                display: "flex",
                alignItems: "center",
                gap: "0",
                marginBottom: "10px",
                overflowX: "auto",
                paddingBottom: "2px",
              }}
            >
              {STEPS.map((s, i) => {
                const isDone =
                  job.status === "complete" || activeStepIndex > i;
                const isActive = job.step === s.key;
                return (
                  <div
                    key={s.key}
                    className={`pipe-step${isDone ? " done" : ""}${isActive ? " active" : ""}`}
                    style={{ flexShrink: 0 }}
                  >
                    <div
                      className="pipe-dot"
                      style={{ width: "7px", height: "7px" }}
                    />
                    {i < STEPS.length - 1 && (
                      <div
                        className="pipe-connector"
                        style={{ width: "16px" }}
                      />
                    )}
                    <span
                      className="pipe-label"
                      style={{ fontSize: "9px", marginTop: "3px" }}
                    >
                      {s.label}
                    </span>
                  </div>
                );
              })}
            </div>

            {/* Progress bar */}
            <div
              className="progress-track"
              style={{ height: "4px", borderRadius: "2px" }}
            >
              <div
                className="progress-fill"
                style={{
                  width: `${job.progress}%`,
                  borderRadius: "2px",
                }}
              />
            </div>
            <div
              className="progress-text"
              style={{ fontSize: "11px", marginTop: "4px" }}
            >
              {job.progress}%
            </div>

            {job.status === "queued" && (
              <div
                style={{ marginTop: "8px", fontSize: "12px", opacity: 0.75 }}
              >
                Your app is in the queue and will start soon.
              </div>
            )}

            {job.step && STEP_MESSAGES[job.step] && (
              <div
                style={{ marginTop: "6px", fontSize: "12px", opacity: 0.75 }}
              >
                {STEP_MESSAGES[job.step]}
              </div>
            )}

            {job.error && (
              <pre
                className="error-block"
                style={{ fontSize: "11px", marginTop: "8px" }}
              >
                {job.error}
              </pre>
            )}
          </div>
        )}

        {/* Preview */}
        {previewUrl && (
          <div
            className="preview-wrap"
            style={{ marginTop: "12px", borderRadius: "12px" }}
          >
            <div
              className="preview-header"
              style={{
                padding: "8px 10px",
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
              }}
            >
              <span
                className="preview-label"
                style={{ fontSize: "11px", fontWeight: 600 }}
              >
                Preview
              </span>
              <div
                className="preview-actions"
                style={{ display: "flex", gap: "8px", alignItems: "center" }}
              >
                <a
                  href={previewUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="preview-link"
                  style={{ fontSize: "11px" }}
                >
                  Open ↗
                </a>
                <button
                  type="button"
                  className="copy-btn"
                  style={{ fontSize: "11px", padding: "4px 10px" }}
                  onClick={async () => {
                    try {
                      await navigator.clipboard.writeText(previewUrl);
                      setCopySuccess(true);
                      setTimeout(() => setCopySuccess(false), 1500);
                    } catch {
                      setApiError("Could not copy the preview link.");
                    }
                  }}
                >
                  {copySuccess ? "Copied!" : "Copy"}
                </button>
              </div>
            </div>
            <iframe
              title="App preview"
              src={previewUrl}
              className="preview-frame"
              style={{ height: "420px" }}
              sandbox="allow-scripts allow-forms"
            />
          </div>
        )}
      </main>
    </div>
  );
}