#!/usr/bin/env bash
# サークルのGoogle Cloud管理者が行う初回構築。実際のクラウドリソースを作成する。
# メンバー権限のワークフローからは実行しない。
set -euo pipefail

: "${GCP_PROJECT_ID:?サークル所有のGoogle CloudプロジェクトIDを設定してください}"
TF_STATE_BUCKET="lusy-roles-state"
: "${STATE_ADMIN_GROUP:?Cloud Identity管理者グループのメールアドレスを設定してください}"
GITHUB_REPOSITORY="${GITHUB_REPOSITORY:-Lumos-Programming/lusy-roles}"
GCS_LOCATION="${GCS_LOCATION:-asia-northeast1}"
POOL_ID="lusy-roles-github"
PROVIDER_ID="lusy-roles"
SERVICE_ACCOUNT_ID="lusy-roles-terraform"

if [[ ! "$GITHUB_REPOSITORY" =~ ^Lumos-Programming/[A-Za-z0-9_.-]+$ ]]; then
  echo 'GITHUB_REPOSITORYにはLumos-Programming内の既存リポジトリを指定してください。' >&2
  exit 1
fi
if [[ ! "$STATE_ADMIN_GROUP" =~ ^[^[:space:]@]+@[^[:space:]@]+$ ]]; then
  echo 'STATE_ADMIN_GROUPにはグループのメールアドレスを指定してください。' >&2
  exit 1
fi

command -v gcloud >/dev/null
command -v gh >/dev/null
command -v uv >/dev/null
CLOUDSDK_PYTHON="$(uv run --locked python -c 'import sys; print(sys.executable)')"
export CLOUDSDK_PYTHON
PROJECT_NUMBER="$(gcloud projects describe "$GCP_PROJECT_ID" --format='value(projectNumber)')"
REPOSITORY_ID="$(gh api "repos/$GITHUB_REPOSITORY" --jq '.id')"
OWNER_ID="$(gh api orgs/Lumos-Programming --jq '.id')"
SERVICE_ACCOUNT="$SERVICE_ACCOUNT_ID@$GCP_PROJECT_ID.iam.gserviceaccount.com"
POOL="projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/$POOL_ID"

gcloud services enable iam.googleapis.com iamcredentials.googleapis.com \
  sts.googleapis.com storage.googleapis.com --project="$GCP_PROJECT_ID"

gcloud storage buckets create "gs://$TF_STATE_BUCKET" \
  --project="$GCP_PROJECT_ID" --location="$GCS_LOCATION" \
  --uniform-bucket-level-access --public-access-prevention
gcloud storage buckets update "gs://$TF_STATE_BUCKET" --versioning
gcloud storage buckets add-iam-policy-binding "gs://$TF_STATE_BUCKET" \
  --member="group:$STATE_ADMIN_GROUP" --role=roles/storage.admin

gcloud iam service-accounts create "$SERVICE_ACCOUNT_ID" \
  --project="$GCP_PROJECT_ID" --display-name='Lusy roles Terraform'
gcloud storage buckets add-iam-policy-binding "gs://$TF_STATE_BUCKET" \
  --member="serviceAccount:$SERVICE_ACCOUNT" --role=roles/storage.objectAdmin

gcloud iam workload-identity-pools create "$POOL_ID" \
  --project="$GCP_PROJECT_ID" --location=global --display-name='Lusy GitHub Actions'

# 変更されない数値IDを使い、リポジトリやOrganizationの旧名を取得した
# 別の所有者にアクセス権が移らないようにする。
CONDITION="assertion.repository_owner_id == '$OWNER_ID' && assertion.repository_id == '$REPOSITORY_ID'"
CONDITION="$CONDITION && assertion.ref == 'refs/heads/main'"
CONDITION="$CONDITION && assertion.sub in ['repo:$GITHUB_REPOSITORY:environment:plan', 'repo:$GITHUB_REPOSITORY:environment:production']"
CONDITION="$CONDITION && assertion.workflow_ref == '$GITHUB_REPOSITORY/.github/workflows/apply.yml@refs/heads/main'"
CONDITION="$CONDITION && assertion.event_name == 'workflow_dispatch'"

gcloud iam workload-identity-pools providers create-oidc "$PROVIDER_ID" \
  --project="$GCP_PROJECT_ID" --location=global --workload-identity-pool="$POOL_ID" \
  --issuer-uri='https://token.actions.githubusercontent.com' \
  --attribute-mapping='google.subject=assertion.sub,attribute.repository_id=assertion.repository_id,attribute.repository_owner_id=assertion.repository_owner_id,attribute.ref=assertion.ref,attribute.workflow_ref=assertion.workflow_ref,attribute.event_name=assertion.event_name' \
  --attribute-condition="$CONDITION"

gcloud iam service-accounts add-iam-policy-binding "$SERVICE_ACCOUNT" \
  --project="$GCP_PROJECT_ID" --role=roles/iam.workloadIdentityUser \
  --member="principalSet://iam.googleapis.com/$POOL/attribute.repository_id/$REPOSITORY_ID"

printf '\nGitHub ActionsのVariablesに次の値を設定してください：\n'
printf 'GCP_PROJECT_ID=%s\n' "$GCP_PROJECT_ID"
printf 'GCP_SERVICE_ACCOUNT=%s\n' "$SERVICE_ACCOUNT"
printf 'GCP_WORKLOAD_IDENTITY_PROVIDER=%s/providers/%s\n' "$POOL" "$PROVIDER_ID"
