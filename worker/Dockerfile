# Build Apps MVP – ECS Fargate worker (SQS poll + Gemini agent + S3 upload)
FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code and branded style template
COPY main.py agent.py validate.py s3_upload.py run_local.py run_local_complex.py ./
COPY templates/ ./templates/

# Run as non-root for ECS (optional but recommended)
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

CMD ["python", "-u", "main.py"]
