# Lusy roles

Lusyは、Lumosのシステムを管理するチームです。このリポジトリでは、GitHubとDiscordへの参加・権限変更・退会を、レビュー済みのPull Request（PR）とTerraformで管理します。

**一人につき一つのJSONファイルを作成し、PRの承認・マージ後、管理者が適用を明示的に許可するとGitHub Actionsが権限を反映します。**

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
2. `members/<GitHubユーザー名>.json`を追加してPRを作る。
3. GitHub Actionsが設定を検証する。
4. 管理者が本人確認と権限のレビューを行い、承認して`main`にマージする。
5. 管理者がApplyを手動起動し、production Environmentの承認後にTerraformのplan・applyを実行する。
6. 申請者がGitHub Organizationの招待を承諾し、両サービスの権限を確認する。

**mainへのマージでは検証だけが走ります。権限の適用には、Applyの手動起動・applyの選択・production Environmentの承認が必要です。**

## 設定済みの対象

| 項目 | 値 |
| --- | --- |
| GitHub Organization | `Lumos-Programming` |
| DiscordサーバーID | `1368752707321729158` |
| 申請できるロール | `lusy` |
| `lusy`が付与するGitHubチーム | `lusy` / `member` |
| `lusy`が付与するDiscordロール | Lumos Web / `1381977862831083590` |
| state保存先 | `gs://lusy-roles-state/lusy-roles/production/default.tfstate` |

GitHubチームとDiscordロールは既存のものを使います。このリポジトリが管理するのは、Organizationへの所属と、チーム・ロールへの割り当てです。チームやロール自体の作成、GitHubリポジトリへの権限、Discordロールの権限内容は別途設定します。

## メンバー定義の例

```json
{
  "github_username": "alice",
  "github_org_role": "member",
  "discord_user_id": "123456789012345678",
  "roles": ["lusy"]
}
```

`members/alice.json`として配置します。`examples/`とテスト用データは本番に適用されません。初期状態の`members/`は空です。

## 構成

```text
members/                    一人一ファイルのメンバー定義
config/organization.json    OrganizationとDiscordサーバーの設定
config/roles.json           申請用ロールと実際の権限の対応
terraform/                  メンバー定義から権限を管理するTerraform
terraform/tests/            外部APIを使わないTerraformテスト
scripts/                    入力検証とGCS初期構築用スクリプト
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

PRの`Validate`では、認証情報を使わずに入力・書式・Terraform構成・ロール変更のテストを検証します。**本番APIとstateを参照するplanはPR上では実行しません。** Discordへの参加状況やBotの権限は、手動起動した`Apply`で初めて確認されます。

`Apply`は保存したplanを適用し、同時に一つだけ実行します。承認対象のコミットを固定し、承認待ちの間に`main`が更新された場合は停止します。最新の`main`から再度起動してください。GitHubとDiscordをまたぐ変更は一括で成功・失敗する処理ではなく、途中で失敗した場合は一部だけ反映されることがあります。

planの差分とapplyの結果は、`tfcmt`が対象コミットに対応するマージ済みPRへコメントします。再度planを実行すると既存のplanコメントを更新します。初期コミットなど対応するPRがない場合は、Actionsの実行サマリーに表示します。差分を見てから適用を判断したい場合は、まず`apply`をオフにしてplanだけを実行してください。

## 利用開始

[セットアップ](docs/setup.md)を完了し、リポジトリ変数`TERRAFORM_ENABLED=true`を設定してから運用を開始してください。GitHubのブランチ保護、GCS、Bot、GitHub Appの設定は、ファイルを配置しただけでは有効になりません。

CLIは[aqua](aqua.yaml)で管理します。aquaを導入後、ローカルで検証できます：

```sh
aqua install
just test
```

## 参考資料

- [GitHub Organization所属のTerraformリソース](https://registry.terraform.io/providers/integrations/github/6.13.0/docs/resources/membership)
- [GitHubチーム所属のTerraformリソース](https://registry.terraform.io/providers/integrations/github/6.13.0/docs/resources/team_membership)
- [Discordロール割り当てのTerraformリソース](https://registry.terraform.io/providers/Planetaryauto60/discord/1.0.3/docs/resources/role_member)
- [TerraformのGCSバックエンド](https://developer.hashicorp.com/terraform/language/backend/gcs)
