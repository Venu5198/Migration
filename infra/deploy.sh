#!/usr/bin/env bash
# Deploy the Topia-to-Equus migration Lambda and attach the filtered S3 trigger
# to an existing source bucket without overwriting its other notifications.
#
# Usage: infra/deploy.sh <source-bucket> <dest-bucket> [source-prefix] [dest-prefix] [stack-name]

set -euo pipefail

usage() {
  echo "Usage: $0 <source-bucket> <dest-bucket> [source-prefix] [dest-prefix] [stack-name]" >&2
  echo "Example: $0 corporate-mobility-source corporate-mobility-dest 'topia/incoming/' 'equus/' 'topia2equus-prod'" >&2
  exit 1
}

if [[ $# -lt 2 ]]; then
  echo "Error: Both <source-bucket> and <dest-bucket> arguments are required." >&2
  usage
fi

SRC_BUCKET="$1"
DEST_BUCKET="$2"
SRC_PREFIX="${3:-topia/incoming/}"
DEST_PREFIX="${4:-equus/}"
STACK="${5:-topia-equus-migration}"
HERE="$(cd "$(dirname "$0")" && pwd)"

# 1. Validate required CLI tools
for tool in aws sam; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "Error: Required CLI tool '$tool' is not installed or not in PATH." >&2
    exit 1
  fi
done

PYTHON_BIN=""
if command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="python"
else
  echo "Error: Python interpreter (python3 or python) is required for notification merging." >&2
  exit 1
fi

# 2. Anti-loop protection: ensure output prefix cannot trigger source prefix
if [[ "$SRC_BUCKET" == "$DEST_BUCKET" && "$DEST_PREFIX" == "$SRC_PREFIX"* ]]; then
  echo "Error: DEST_PREFIX ('$DEST_PREFIX') must not sit under SOURCE_PREFIX ('$SRC_PREFIX') in the same bucket." >&2
  echo "This would cause an infinite re-trigger loop." >&2
  exit 1
fi

# 3. Build and deploy the SAM stack
echo "==> Building SAM application..."
cd "$HERE/../lambda"
sam build

echo "==> Deploying CloudFormation stack: $STACK..."
sam deploy \
  --stack-name "$STACK" \
  --capabilities CAPABILITY_IAM \
  --resolve-s3 \
  --no-fail-on-empty-changeset \
  --parameter-overrides \
      SourceBucketName="$SRC_BUCKET" \
      DestBucketName="$DEST_BUCKET" \
      SourcePrefix="$SRC_PREFIX" \
      DestPrefix="$DEST_PREFIX"

# 4. Retrieve deployed Lambda Function ARN
echo "==> Fetching Lambda Function ARN..."
FN_ARN=$(aws cloudformation describe-stacks --stack-name "$STACK" \
  --query "Stacks[0].Outputs[?OutputKey=='FunctionArn'].OutputValue" --output text)

if [[ -z "$FN_ARN" || "$FN_ARN" == "None" ]]; then
  echo "Error: Could not retrieve FunctionArn from CloudFormation stack '$STACK'." >&2
  exit 1
fi
echo "    Function ARN: $FN_ARN"

# 5. Safely merge S3 event notification without clobbering existing configuration
echo "==> Fetching current notification configuration for s3://$SRC_BUCKET..."
CURRENT=$(aws s3api get-bucket-notification-configuration --bucket "$SRC_BUCKET" 2>/dev/null || echo "{}")

echo "==> Merging Topia notification filter idempotently..."
MERGED=$("$PYTHON_BIN" "$HERE/merge_notification.py" \
  --current-json "$CURRENT" \
  --filter-file "$HERE/s3-notification-filter.json" \
  --arn "$FN_ARN" \
  --prefix "$SRC_PREFIX")

echo "==> Applying merged notification configuration to s3://$SRC_BUCKET..."
aws s3api put-bucket-notification-configuration \
  --bucket "$SRC_BUCKET" \
  --notification-configuration "$MERGED"

echo "==> S3 Event Trigger successfully attached!"
echo "    Source:      s3://$SRC_BUCKET/$SRC_PREFIX*.xlsx"
echo "    Destination: s3://$DEST_BUCKET/$DEST_PREFIX"
echo "    Function:    $FN_ARN"
