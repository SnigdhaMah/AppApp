'use client';

import { useEffect, useState } from 'react';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || '';

type Job = {
  jobId: string;
  status: string;
  step?: string;
  progress: number;
  resultUrl?: string | null;
  error?: string | null;
  updatedAt?: number | null;
};

export default function AppBuilder() {
  const [prompt, setPrompt] = useState('');
  const [job, setJob] = useState<Job | null>(null);
  const [previewUrl, setPreviewUrl] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [apiError, setApiError] = useState<string | null>(null);

  async function createJob() {
    setApiError(null);
    if (!API_BASE) {
      setApiError('NEXT_PUBLIC_API_URL is not set. Set it in .env.local to your API Gateway URL.');
      return;
    }
    setIsSubmitting(true);
    try {
      const res = await fetch(`${API_BASE}/jobs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt }),
      });
      if (!res.ok) {
        const err = await res.text();
        setApiError(err || 'Failed to create job');
        return;
      }
      const data = await res.json();
      setJob({
        jobId: data.jobId,
        status: 'queued',
        progress: 0,
      });
      setPreviewUrl('');
    } finally {
      setIsSubmitting(false);
    }
  }

  useEffect(() => {
    if (!job?.jobId || !API_BASE) return;

    const timer = setInterval(async () => {
      try {
        const res = await fetch(`${API_BASE}/jobs/${job.jobId}`);
        const data = await res.json();
        setJob(data);

        if (data.status === 'complete' && data.resultUrl) {
          setPreviewUrl(data.resultUrl);
          clearInterval(timer);
        }
        if (data.status === 'failed') {
          clearInterval(timer);
        }
      } catch {
        // keep polling
      }
    }, 2000);

    return () => clearInterval(timer);
  }, [job?.jobId, API_BASE]);

  return (
    <div className="page">
      <header className="header">
        <h1>AI App Builder</h1>
        <p>
          Describe the web app you want. We generate static HTML/CSS/JS and show a preview.
        </p>
      </header>

      <textarea
        className="promptArea"
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
        placeholder="e.g. Build a todo list app with add, complete, and delete. Use localStorage to persist items."
        rows={5}
      />

      <button
        type="button"
        className="btnPrimary"
        onClick={createJob}
        disabled={!prompt.trim() || !API_BASE || isSubmitting}
      >
        {isSubmitting ? 'Building…' : 'Build'}
      </button>

      {apiError && (
        <div className="apiErrorBanner" role="alert">
          {apiError}
        </div>
      )}

      {job && (
        <div className="jobCard">
          <div className="jobCardRow"><strong>Job:</strong> {job.jobId}</div>
          <div className="jobCardRow"><strong>Status:</strong> {job.status} {job.step && `(${job.step})`} — {job.progress}%</div>
          <div className="stepIndicator">
            <span className={job.status === 'queued' ? 'stepDot stepDotActive' : 'stepDot'}>Queued</span>
            <span className={job.step === 'generating' || job.step === 'validating' || job.step === 'fixing' || job.step === 'uploading' ? 'stepDot stepDotActive' : job.status === 'complete' || job.status === 'failed' ? 'stepDot' : 'stepDot'}>Generating</span>
            <span className={job.step === 'validating' || job.step === 'fixing' ? 'stepDot stepDotActive' : job.status === 'complete' || job.status === 'failed' ? 'stepDot' : 'stepDot'}>Validating</span>
            <span className={job.status === 'complete' ? 'stepDot stepDotActive' : job.status === 'failed' ? 'stepDot' : 'stepDot'}>Complete</span>
          </div>
          <div className="progressBar">
            <div className="progressBarFill" style={{ width: `${job.progress}%` }} />
          </div>
          {job.error && (
            <pre className="errorBlock">
              {job.error}
            </pre>
          )}
        </div>
      )}

      {previewUrl && (
        <div className="previewSection">
          <div className="previewLabel">App preview</div>
          <div className="previewActions">
            <a href={previewUrl} target="_blank" rel="noreferrer">
              Open app in new tab
            </a>
            <button
              type="button"
              className="btnCopy"
              onClick={() => {
                navigator.clipboard.writeText(previewUrl);
              }}
            >
              Copy link
            </button>
          </div>
          <iframe
            title="App preview"
            src={previewUrl}
            className="previewFrame"
            sandbox="allow-scripts allow-forms"
          />
        </div>
      )}
    </div>
  );
}
