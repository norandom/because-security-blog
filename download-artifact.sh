#!/bin/bash
# Download the latest build artifact from GitHub Actions

REPO="norandom/because-security-blog"
ARTIFACT_NAME="blog-backend-binary"

echo "Fetching latest workflow run..."

# Get the latest successful workflow run
RUN_ID=$(curl -s "https://api.github.com/repos/${REPO}/actions/runs?status=success&per_page=1" | \
  jq -r '.workflow_runs[0].id')

if [ -z "$RUN_ID" ] || [ "$RUN_ID" = "null" ]; then
  echo "No successful workflow runs found"
  exit 1
fi

echo "Found workflow run: $RUN_ID"

# Get artifact download URL
ARTIFACT_URL=$(curl -s "https://api.github.com/repos/${REPO}/actions/runs/${RUN_ID}/artifacts" | \
  jq -r ".artifacts[] | select(.name==\"${ARTIFACT_NAME}\") | .archive_download_url")

if [ -z "$ARTIFACT_URL" ] || [ "$ARTIFACT_URL" = "null" ]; then
  echo "Artifact not found in workflow run"
  exit 1
fi

# Download artifact (requires authentication)
if [ -z "$GITHUB_TOKEN" ]; then
  echo "Please set GITHUB_TOKEN environment variable"
  echo "You can create a token at: https://github.com/settings/tokens"
  echo "Required scope: public_repo (or repo for private repos)"
  exit 1
fi

echo "Downloading artifact..."
curl -L -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  "$ARTIFACT_URL" -o artifact.zip

# Extract the binary
unzip -o artifact.zip
rm artifact.zip
chmod +x blog-backend

echo "Binary downloaded to: ./blog-backend"
ls -la blog-backend