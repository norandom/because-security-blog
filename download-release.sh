#!/bin/bash
# Download the latest release binary (no auth required)

REPO="norandom/because-security-blog"

echo "Fetching latest release..."

# Get latest release download URL
DOWNLOAD_URL=$(curl -s "https://api.github.com/repos/${REPO}/releases/latest" | \
  jq -r '.assets[] | select(.name=="blog-backend") | .browser_download_url')

if [ -z "$DOWNLOAD_URL" ] || [ "$DOWNLOAD_URL" = "null" ]; then
  echo "No release found. Make sure to create a release with tag (e.g., git tag v1.0.0 && git push --tags)"
  exit 1
fi

echo "Downloading from: $DOWNLOAD_URL"
curl -L "$DOWNLOAD_URL" -o blog-backend
chmod +x blog-backend

echo "Binary downloaded to: ./blog-backend"
ls -la blog-backend