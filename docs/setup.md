# 管理者向けセットアップ

この手順は、初回の運用開始を担当する管理者向けです。申請者は[オンボーディング](onboarding.md)を参照してください。

## 1. GitHubリポジトリとレビューの設定

`Lumos-Programming`内にリポジトリを作成し、このディレクトリを`main`にpushします。以下では`Lumos-Programming/lusy-roles`を想定します。

既存の`@Lumos-Programming/lusy-admin`チームにリポジトリへのwrite権限を付与してください。別のチームがレビューする場合は`.github/CODEOWNERS`を変更します。Code Ownerには明示的なwrite権限が必要です。

`main`を対象に、次のルールを有効にします。

- マージにはPRと1件以上の承認を必須にする。
- Code Ownerのレビューを必須にする。
- 新しいコミットが追加されたら古い承認を取り消し、最新pushへの承認を必須にする。
- ステータスチェック`Validate`の成功と、ブランチが最新であることを必須にする。
- force pushとブランチ削除を禁止し、日常的なレビュー迂回を許可しない。

`Validate`は一度実行すると必須チェックとして選択できます。**CODEOWNERSを置くだけでは承認は強制されません。** 利用中のGitHubプランとリポジトリの公開範囲で、必要なルールが使えることも確認してください。

GitHub ActionsのEnvironmentに`production`を作成し、デプロイ可能なブランチを`main`に限定します。**Required reviewersに管理者チームを設定し、可能ならPrevent self-reviewを有効にしてください。** マージ後も明示的なデプロイ承認を必須にします。管理者の承認迂回も無効にしてください。

plan用に`plan` Environmentも作成し、こちらもブランチを`main`に限定します。**`plan`にはRequired reviewersや待機時間を設定しません。** `apply`をオフにした実行は`plan`を使用し、オンにした実行だけが`production`で承認を待ちます。

Environmentの承認者はYAMLでは設定できません。GitHub側での設定が必要です。利用プラン・公開範囲によりEnvironmentの承認ルールを利用できない場合でも、この構成は手動起動しなければ適用しません。別担当者の承認まで必須にする運用は、対応プランまたは公開範囲で承認ルールを有効にしてから開始してください。

## 2. GCSとOIDC認証

### 所有者と権限

Cloud Identityの組織に所属するサークル所有のGoogle Cloudプロジェクトを使います。管理者はCloud Identityのグループで管理し、担当交代時はグループの所属を変更します。グループの管理者も複数人にしてください。

Cloud Identity Freeのユーザー・グループ管理を利用できます。Cloud Storageの保存・操作料金は別に発生します。

### state保存先

`terraform/backend.tf`に以下を設定済みです。

| 項目 | 値 |
| --- | --- |
| バケット | `lusy-roles-state` |
| stateオブジェクト | `lusy-roles/production/default.tfstate` |
| ロック | TerraformのGCSバックエンドが管理 |

バケットではObject Versioning、uniform bucket-level access、public access preventionを有効にします。ロックファイルを削除できなくなる保持ポリシーは設定しないでください。

Terraformのworkspaceは`default`を使用します。別workspaceを作ると、同じメンバーを別のstateから管理することになります。

### 初期構築スクリプト

先に[開発・変更ガイド](../CONTRIBUTING.md)に従ってaquaでCLIを導入します。Google Cloudの管理者が、`gcloud`と`gh`で認証した環境から実行します。GitHubリポジトリは先に作成してください。

```sh
export GCP_PROJECT_ID='サークルのプロジェクトID'
export STATE_ADMIN_GROUP='cloud-admins@サークルのドメイン'
export GITHUB_REPOSITORY='Lumos-Programming/lusy-roles'
# 任意。省略時はasia-northeast1。料金はリージョンによって異なります。
export GCS_LOCATION='asia-northeast1'
bash scripts/bootstrap-gcs.sh
```

このスクリプトは、バケット・サービスアカウント・専用のWorkload Identity PoolとProviderを作成します。

- Actions用サービスアカウントに、このバケットだけの`roles/storage.objectAdmin`を付与する。
- 管理者グループに、このバケットの`roles/storage.admin`を付与する。
- 指定リポジトリからサービスアカウントへのOIDC認証を許可する。

実行者にはAPI有効化、各リソース作成、IAMポリシー変更の権限が必要です。

**これは初回作成用のスクリプトです。** バケットや同名のIAMリソースが既にある場合は、スクリプト内の対応する設定コマンドを既存リソースに適用してください。途中で失敗した場合は、作成済みのものを確認し、失敗した箇所から作業を再開します。IAMの反映には数分かかる場合があります。

### OIDCで許可する実行

信頼条件を以下に限定します。

- 対象リポジトリと`Lumos-Programming`の変更されない数値ID。
- `main`ブランチと`plan`または`production` Environment。
- `.github/workflows/apply.yml`。
- 手動実行の`workflow_dispatch`イベント。
- `plan` Environmentに限り、PRの自動plan用の`pull_request_target`イベントも許可する。

リポジトリ名やワークフローファイル名を変更するときは、信頼条件も変更してください。Poolはこの用途専用にします。同じPoolへのProvider追加は認証可能な主体を増やすことがあります。

既にOIDCを構築済みでsubjectを`production`だけに限定している場合は、`repo:Lumos-Programming/lusy-roles:environment:plan`も許可します。イベントを手動実行に限定している場合は、planのsubjectに限り`pull_request_target`も許可します。リポジトリID・main・ワークフローの制限は維持してください。

Googleサービスアカウントの秘密鍵は作成しません。スクリプトが出力する以下の値を、`plan`と`production`両方のVariables、または共通のリポジトリVariablesに設定します。

| 変数 | 値 |
| --- | --- |
| `GCP_PROJECT_ID` | Google CloudプロジェクトID |
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | `projects/NUMBER/locations/global/workloadIdentityPools/lusy-roles-github/providers/lusy-roles` |
| `GCP_SERVICE_ACCOUNT` | `lusy-roles-terraform@PROJECT_ID.iam.gserviceaccount.com` |

## 3. Organization所有のGitHub App

`Lumos-Programming`を所有者とするGitHub Appを登録し、複数の管理者が管理できるようにします。

- Organization permissionsの**Members: Read and write**を許可する。
- 使用しないWebhookは無効にする。
- Appを`Lumos-Programming`にインストールする。
- 秘密鍵を発行する。

この構成にはリポジトリのwrite権限は不要です。Appのインストール先リポジトリは本リポジトリに限定できます。

GitHubリポジトリの **Settings → Environments** を開き、`plan`と`production`の両方に次を設定します。秘密鍵とBotトークンはEnvironment secrets、App IDはEnvironment variablesに登録します。plan専用Appを使う場合はMembersの読み取り権限だけで構いません。

| 種別 | 名前 | 値 |
| --- | --- | --- |
| Variable | `GH_APP_ID` | GitHub AppのID |
| Secret | `GH_APP_PRIVATE_KEY` | 発行したPEM秘密鍵の内容全体 |

Actionsは実行ごとに短期のインストールトークンを発行し、Terraformに`GITHUB_TOKEN`として渡します。planではMembers: Read、applyではMembers: Writeを要求します。トークンはジョブ終了時にActionが失効させます。リポジトリ標準の`GITHUB_TOKEN`ではOrganizationのメンバー管理はできません。

自動実行に個人のPersonal Access Tokenを使わず、必要な鍵更新はOrganizationの管理者が行います。

### tfcmtのコメント用トークン

`tfcmt`には、GitHub Actions標準のトークンを`TFCMT_GITHUB_TOKEN`として渡します。Applyジョブに`pull-requests: write`を設定しているため、追加のSecretやGitHub Appの権限追加は不要です。Organizationのメンバー権限を変更するAppトークンは、Terraform用の`GITHUB_TOKEN`として別に渡します。

## 4. 開発者チーム所有のDiscord Bot

Discord Developer Portalで複数人の開発者チームを用意し、そのチーム所有のアプリケーションを使います。

1. Botをサーバー`1368752707321729158`に招待する。
2. **Manage Roles**権限を付与する。
3. Botのロールを、Lumos Web（`1381977862831083590`）より上に配置する。
4. Botトークンを`plan`と`production`両方のSecret **`DISCORD_BOT_TOKEN`**に保存する。

`Bot `という接頭辞は付けずに保存します。BotにはAdministrator権限は不要です。追加で管理するロールもBotより下に置き、`@everyone`や外部連携が管理するロールは対象に含めません。

メンバーは適用前にサーバーへ参加する必要があります。使用するプロバイダーは初期化時にDiscord Gatewayにも接続します。接続エラーが出る場合は、トークン・ネットワーク・Botの設定を確認してください。

## 5. 初回実行

ここまでの準備が完了したら、**リポジトリのVariable**に`TERRAFORM_ENABLED=true`を設定します。この変数はジョブ開始前の条件判定に使うため、EnvironmentのVariableには置かないでください。

1. Actionsの`Apply`を開く。
2. `main`を選択し、`apply`をオフのまま手動実行する。
3. 承認なしで実行されるplanで、GCS接続と差分を確認する。
4. 最初の実メンバーのPRを作成し、[マージ前plan](operations.md#マージ前のprでplanを確認する)で差分を確認する。既存メンバーは[取り込み手順](operations.md#既存メンバーの取り込み)も確認してからレビュー・マージする。
5. 最新の`main`でApplyを起動し、`apply`をオンにする。
6. 管理者が`production`のReview deploymentsで対象コミットを確認し、承認する。
7. 招待・チーム所属・Discordロールが実際に付くことを確認する。

メンバーが空の状態では、各APIのメンバー管理権限を完全には検証できません。最初の実メンバーで一連の動作を確認します。

その後の運用は[運用ガイド](operations.md)、申請者への案内は[オンボーディング](onboarding.md)を参照してください。

## 参考資料

- [Google CloudのGitHub Actions向けWorkload Identity Federation](https://docs.cloud.google.com/iam/docs/workload-identity-federation-with-deployment-pipelines)
- [Google認証Action](https://github.com/google-github-actions/auth)
- [GitHub Appトークン発行Action](https://github.com/actions/create-github-app-token)
- [Cloud Identityのエディション比較](https://docs.cloud.google.com/identity/docs/editions)
- [GCSバックエンド](https://developer.hashicorp.com/terraform/language/backend/gcs)
