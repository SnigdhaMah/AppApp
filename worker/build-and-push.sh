#!/usr/bin/env bash
# Build the worker Docker image and push to ECR for ECS deployment.
# Usage:
#   ./build-and-push.sh [AWS_REGION] [ECR_URI]
# If ECR_URI is omitted, run from repo root after 'cdk deploy' and use:
#   aws cloudformation describe-stacks --stack-name BuildAppsStack --query 'Stacks[0].Outputs' --output table
# to find the ECR repository URI (or get it from the CDK deploy output).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REGION="${1:-${AWS_REGION:-us-east-1}}"

# If ECR repo was created by CDK DockerImageAsset, the URI is like:
# 123456789.dkr.ecr.us-east-1.amazonaws.com/cdk-hnb659fds-container-assets-123456789-us-east-1
# You can get it from: aws ecr describe-repositories --query 'repositories[*].repositoryUri' --output text
ECR_URI="${2:-}"

if [[ -z "$ECR_URI" ]]; then
  echo "Usage: $0 [AWS_REGION] ECR_URI"
  echo "Example: $0 us-east-1 123456789.dkr.ecr.us-east-1.amazonaws.com/build-apps-worker"
  echo ""
  echo "After 'cdk deploy', CDK creates an ECR repo automatically. To find it:"
  echo "  aws ecr describe-repositories --repository-names build-apps-worker 2>/dev/null || true"
  echo "  # or list: aws ecr describe-repositories --query 'repositories[*].repositoryUri' --output text"
  exit 1
fi

IMAGE_TAG="${IMAGE_TAG:-latest}"

echo "Building worker image in $SCRIPT_DIR..."
docker build -t "build-apps-worker:${IMAGE_TAG}" "$SCRIPT_DIR"

echo "Tagging for ECR..."
docker tag "build-apps-worker:${IMAGE_TAG}" "${ECR_URI}:${IMAGE_TAG}"

echo "Logging in to ECR..."
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "${ECR_URI%%/*}"

echo "Pushing ${ECR_URI}:${IMAGE_TAG}..."
docker push "${ECR_URI}:${IMAGE_TAG}"

echo "Done. Image: ${ECR_URI}:${IMAGE_TAG}"
echo "Update your ECS task definition to use this image, or redeploy the stack."
