# Lusy roles

Lusyは、Lumosのシステムを管理するチームです。このリポジトリでは、GitHubとDiscordへの参加・権限変更・退会を、レビュー済みのPull Request（PR）とTerraformで管理します。

一人につき一つのYAMLファイルで権限を定義します。PRをレビュー・マージした後、管理者がGitHub Actionsから変更を適用します。

## このプロジェクトの目的

- メンバーの申請内容と現在の権限を、ファイルから確認できるようにする。
- 権限変更の理由と承認者をPRに記録する。
- 個人のアカウントやアクセストークンへの依存を減らし、卒業・担当交代時に引き継げるようにする。
- ロールの削除も同じ手順で反映し、不要な権限が残ることを防ぐ。

## ガイド

| 読みたい内容 | ドキュメント |
| --- | --- |
| Lusyへの参加申請 | [オンボーディング](docs/onboarding.md) |
| 管理者による初期設定 | [セットアップ](docs/setup.md) |
| 権限変更・退会・障害対応 | [運用ガイド](docs/operations.md) |
| 構成の変更とローカル検証 | [開発・変更ガイド](CONTRIBUTING.md) |

## 参加の流れ

1. 申請者がDiscordサーバーに参加する。
2. `members/<GitHubユーザー名>.yaml`を追加してPRを作る。
3. GitHub Actionsが設定を検証し、ReadyなPRにplanの差分を表示する。
4. 管理者が本人確認と権限のレビューを行い、PRのplanを確認してから承認・マージする。
5. 管理者がApplyを手動起動し、production Environmentの承認後にTerraformのplan・applyを実行する。
6. 申請者がGitHub Organizationの招待を承諾し、両サービスの権限を確認する。

マージだけでは権限は変わりません。Applyを手動起動し、production Environmentで承認すると適用されます。

## 設定済みの対象

| 項目 | 値 |
| --- | --- |
| GitHub Organization | `Lumos-Programming` |
| DiscordサーバーID | `1368752707321729158` |
| state保存先 | `gs://lusy-roles-state/lusy-roles/production/default.tfstate` |

共通の`lusy`に、担当プロジェクトのロールを追加します。

| ロール | GitHubチーム | Discordロール |
| --- | --- | --- |
| `lusy` | `Lusy`（`lusy`）/ `member` | — |
| `lumos-web` | `[Lusy] Lumos Web`（`lusy-lumos-web`）/ `member` | Lumos Web / `1381977862831083590` |
| `lumos-discord-bot` | `[Lusy] Lumos Discord Bot`（`lusy-lumos-discord-bot`）/ `member` | Discord Bot / `1383147563850535004` |

GitHubチームとDiscordロールは既存のものを使います。このリポジトリが管理するのは、Organizationへの所属と、チーム・ロールへの割り当てです。チームやロール自体の作成、GitHubリポジトリへの権限、Discordロールの権限内容は別途設定します。

メンバー定義に合わせて、その人の既存の所属・ロールも整理します。GitHubチームへの直接所属とDiscordロールを検出し、YAMLにない割り当ては削除対象になります。未登録の人、GitHubの継承所属、Discordの`@everyone`と連携サービス管理ロールは対象外です。

プロジェクトの子チームは、親チーム`Lusy`のアクセス権限も継承します。`lusy`は親チームへの直接所属を管理します。

## メンバー定義の例

```yaml
github_username: alice
github_org_role: member
discord_user_id: "123456789012345678"
roles:
  - lusy
  - lumos-web
```

`members/alice.yaml`として配置します。`examples/`とテスト用データは本番に適用されません。初期状態の`members/`は空です。

## 構成

```text
members/                    一人一ファイルのメンバー定義
config/organization.yaml    OrganizationとDiscordサーバーの設定
config/roles.yaml           申請用ロールと実際の権限の対応
terraform/                  メンバー定義から権限を管理するTerraform
terraform/tests/            外部APIを使わないTerraformテスト
scripts/                    入力検証・既存所属の検出・GCS初期構築
.github/workflows/          PR・mainの検証と承認後の手動適用
.github/CODEOWNERS          権限変更をレビューする管理者チーム
```

### 認証とstate

- **Google Cloud**：サークル所有のプロジェクトとサービスアカウントを使い、ActionsからOIDCで短期認証する。サービスアカウント鍵は発行しない。
- **GitHub**：Organization所有のGitHub Appから実行ごとに短期トークンを発行する。
- **Discord**：開発者チーム所有のBotを使う。
- **管理者**：Google CloudへのアクセスはCloud Identityのグループで管理し、各サービスに複数の管理者を置く。

GCSはTerraformのstateロックに対応しています。バージョニングも有効にし、誤操作時に以前のstateを確認できるようにします。

### 検証と適用の範囲

PRの`Validate`では、認証情報を使わずに入力・YAMLの書式・Terraform構成・ロール変更のテストを検証します。

Readyなメンバー変更PRでは、planを自動実行します。承認は不要です。PRのメンバーYAMLを読み込み、Terraformやロール一覧はmainのものを使います。最新のmainを取り込んだ、メンバーファイルのみのPRが対象です。再実行の方法は[運用ガイド](docs/operations.md#マージ前のprでplanを確認する)を参照してください。

`Apply`は保存したplanを適用し、同時に一つだけ実行します。承認対象のコミットを固定し、承認待ちの間に`main`が更新された場合は停止します。最新の`main`から再度起動してください。GitHubとDiscordをまたぐ変更は一括で成功・失敗する処理ではなく、途中で失敗した場合は一部だけ反映されることがあります。

planでは本番stateを一時ローカルstateへコピーし、検出した既存割り当てをそのコピーにimportします。本番stateと実際の権限は変更しません。承認後のapplyでは既存割り当てを本番stateにimportしてから、最新のplanを作成・適用します。

planの差分とapplyの結果は、`tfcmt`が対象PRへコメントします。PR指定時はそのPRに、mainの実行時は対象コミットに対応するマージ済みPRに投稿します。対応するPRがない場合は、Actionsの実行サマリーに表示します。

## 利用開始

[セットアップ](docs/setup.md)を完了し、リポジトリ変数`TERRAFORM_ENABLED=true`を設定してから運用を開始してください。GitHubのブランチ保護、GCS、Bot、GitHub Appの設定は、ファイルを配置しただけでは有効になりません。

Terraform・justなどのCLIは[aqua](aqua.yaml)で管理し、uvは[公式手順](https://docs.astral.sh/uv/getting-started/installation/)で別途導入します。必要なuvバージョンは`pyproject.toml`を参照してください。導入後、ローカルで検証できます：

```sh
aqua install
just test
```

## 参考資料

- [GitHub Organization所属のTerraformリソース](https://registry.terraform.io/providers/integrations/github/6.13.0/docs/resources/membership)
- [GitHubチーム所属のTerraformリソース](https://registry.terraform.io/providers/integrations/github/6.13.0/docs/resources/team_membership)
- [Discordロール割り当てのTerraformリソース](https://registry.terraform.io/providers/Alpaca744/discord/0.1.3/docs/resources/member_role)
- [TerraformのGCSバックエンド](https://developer.hashicorp.com/terraform/language/backend/gcs)
