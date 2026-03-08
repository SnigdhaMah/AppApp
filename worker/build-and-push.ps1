# Build the worker Docker image and push to ECR for ECS deployment.
# Usage (PowerShell):
#   .\build-and-push.ps1 -Region us-east-2 -EcrUri "464796503667.dkr.ecr.us-east-2.amazonaws.com/build-apps-worker"
# Optional: -Profile build-apps-team (if you use a named AWS profile)

param(
    [string]$Region = "us-east-2",
    [string]$EcrUri = "464796503667.dkr.ecr.us-east-2.amazonaws.com/build-apps-worker",
    [string]$Profile = "",
    [string]$ImageTag = "latest"
)

$ErrorActionPreference = "Stop"

if (-not $EcrUri) {
    Write-Host "Usage: .\build-and-push.ps1 -Region us-east-2 -EcrUri <ECR_URI>"
    Write-Host "Example: .\build-and-push.ps1 -Region us-east-2 -EcrUri 464796503667.dkr.ecr.us-east-2.amazonaws.com/build-apps-worker"
    exit 1
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RegistryHost = ($EcrUri -split "/")[0]

$AwsArgs = @("--region", $Region)
if ($Profile) { $AwsArgs += @("--profile", $Profile) }

Write-Host "Building worker image in $ScriptDir..."
docker build -t "build-apps-worker:$ImageTag" $ScriptDir

Write-Host "Tagging for ECR..."
docker tag "build-apps-worker:$ImageTag" "${EcrUri}:${ImageTag}"

Write-Host "Logging in to ECR..."
$password = & aws ecr get-login-password @AwsArgs
$password | docker login --username AWS --password-stdin $RegistryHost

Write-Host "Pushing ${EcrUri}:${ImageTag}..."
docker push "${EcrUri}:${ImageTag}"

Write-Host "Done. Image: ${EcrUri}:${ImageTag}"
Write-Host "To roll out on ECS, run:"
Write-Host "  aws ecs update-service --cluster BuildAppsWorkerCluster --service BuildAppsWorker --force-new-deployment --region $Region"
if ($Profile) { Write-Host "  (Add: --profile $Profile)" }
