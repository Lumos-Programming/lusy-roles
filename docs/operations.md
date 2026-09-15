# 運用ガイド

## 権限変更のレビュー

管理者は、申請者の本人確認、参加理由、ロールが付与する実際の権限を確認します。`github_org_role: admin`はOrganizationの所有者、GitHubチームの`maintainer`はチーム管理権限です。

`config/roles.yaml`を変更すると、そのロールを持つ全メンバーに影響します。個人ファイル以外の変更は影響範囲も確認してください。

## ロールの追加と重複

ロール一覧の各項目は、次の形式です。

```yaml
lusy:
  description: GitHubのLusyチームへの所属とDiscordのLumos Webロール
  github_teams:
    lusy: member
  discord_role_ids:
    - "1381977862831083590"
```

`github_teams`には既存チームのslugと`member`または`maintainer`を指定します。片方のサービスだけを対象にする場合、もう片方は空のオブジェクトまたは配列にできます。

- 同じGitHubチームへの要求が重なると、高い権限を採用する。
- 同じDiscordロールへの要求は重複させず、一つの割り当てとして管理する。
- Organization所有者は、指定したGitHubチーム内で`maintainer`になる。
- Discordは個別のロール付与・削除APIを使い、管理対象外のロールは維持する。

## 権限の取り消しと退会

| ファイルの変更 | 適用される結果 |
| --- | --- |
| `roles`から一つ削除 | 他のロールからも付与されている権限を除き、そのロールの権限を取り消す |
| `roles: []`にする | 管理中のGitHubチーム・Discordロールを取り消し、GitHub Organizationには残す |
| メンバーファイルを削除 | 管理中のDiscordロール・GitHubチーム・**GitHub Organization全体への所属**を取り消す |

Organizationからの脱退は、Lusy以外のチームやリポジトリへのアクセスにも影響します。Lumosに残る人のファイルは削除せず、適切なロール一覧に変更してください。Discordロールを削除しても、サーバーからは追放しません。

## アカウント名・IDの変更

GitHubのファイル名はTerraformのリソースアドレスにも使われます。GitHubユーザー名変更時は、単純なファイル削除・追加を避け、管理者が`moved`ブロックまたは`terraform state mv`で所属の管理を引き継ぎます。

DiscordはサーバーID・ユーザーID・ロールIDの組で管理します。ユーザーIDを変更すると、旧アカウントの割り当てを削除し、新アカウントに付け直します。

## 再実行と手動変更の修復

`main`へのマージは検証だけを実行します。`Apply`は管理者が手動起動し、初期状態ではplanのみです。権限を反映するには、最新の`main`で`apply`をオンにして起動し、別の管理者が`production` Environmentで承認します。

承認待ちの間に`main`が更新されると実行は停止します。古い実行を再実行せず、最新の`main`から新しい実行を作成してください。手動で外された管理対象の権限も、次の適用で設定に合わせて戻します。定期実行は設定していません。

GitHubとDiscordの処理は一つのトランザクションではありません。片方が成功した後でもう片方が失敗する場合があります。原因を解消して再実行し、保存済みstateから残りを反映します。

## plan差分と適用結果の確認

`tfcmt`が、指定したPRまたは実行対象コミットに対応するマージ済みPRへplanの差分とapplyの結果を投稿します。planは既存コメントを更新し、applyは結果を新しいコメントとして残します。対応するPRがない初期コミットなどでは、Actionsの実行サマリーに表示します。

### マージ前のPRでplanを確認する

1. PRが最新のmainを取り込み、変更が`members/*.yaml`だけであることを確認する（`.gitkeep`の追加・削除も可能）。
2. `gh pr view <PR番号> --json headRefOid --jq .headRefOid`で完全なhead SHAを取得する。
3. Actions → Apply → Run workflowでブランチに`main`を選び、`pr_number`と`pr_sha`に対象を入力する。`apply`はオフにする。
4. 別の管理者が実行入力のPR番号・SHAを確認し、`production`で承認する。
5. PRのtfcmtコメントで、対象SHAと権限の追加・変更・削除を確認する。PRに追加コミットがあれば、最新SHAで再実行する。

PRからは指定SHAのメンバー定義だけを一時ディレクトリへ取得します。Terraform、プロバイダー、ロール一覧、スクリプト、依存関係はmainのものを使用します。通常ファイル以外やメンバー定義以外の変更は拒否します。取得時にSHAが変わっていた場合も停止します。PRモードではapplyを実行できません。

このモードも本番stateとAPIを参照するため、GCS・App・Botの設定と`TERRAFORM_ENABLED=true`が必要です。未設定の状態で成功する`Validate`のモックテストは、本番planの代わりにはなりません。

### マージ後の適用

差分を確認してから適用を判断する場合は、次の順で実行してください。

1. `pr_number`・`pr_sha`を空にし、`apply`をオフにしてApplyを起動し、Environmentの承認後にmainのplanだけを実行する。
2. PRのtfcmtコメントで追加・変更・取り消しの差分を確認する。
3. 適用する場合は同じコミットから`apply`をオンにして新しく起動し、Environmentで承認する。

2回目の実行でもplanを作り直します。外部で権限が変更されると差分が変わる場合があるため、tfcmtコメントの対象コミットと実行リンクを確認してください。

コメントは公開PRに表示されます。現在のメンバー定義と同様に、対象のユーザーIDやロール割り当てを含みます。機密値を追加する場合は、Terraformのsensitive指定とコメント内容も確認してください。

## よくあるエラー

| エラー・症状 | 対応 |
| --- | --- |
| Applyがスキップされる | リポジトリ変数`TERRAFORM_ENABLED=true`と対象ブランチ`main`を確認する |
| Google Cloudの認証が拒否される | 数値のリポジトリID、OIDCの信頼条件、サービスアカウント権限、Environment名を確認する |
| GCSが403を返す | バケットへのIAM権限を確認し、変更直後なら反映を待つ |
| GitHubが403を返す | AppのOrganization Members権限とインストール先を確認する |
| Discordでユーザーが見つからない | IDとサーバーへの参加を確認する。退会済みならファイルの削除・変更方針を確認する |
| Discordで権限が不足する | BotのManage Rolesと、対象ロールより上にあることを確認する |
| stateがロックされている | 実行中のActionsやローカル操作を確認し、完了を待つ |

実行中のapplyは通常キャンセルしません。ロックを無効にしたり、別の実行が持つロックをforce-unlockしたりしないでください。

## 既存メンバーの取り込み

既存のOrganization所有者を追加するときは、`github_org_role`を`admin`にします。`member`を指定すると降格を要求します。

既存の所属を取り込む場合、メンバー定義を追加したうえで、最初の適用前に管理者がimportします。Googleのローカル認証には管理者グループに所属するアカウントを使います。

```sh
uv run --locked python scripts/validate.py
gcloud auth application-default login
terraform -chdir=terraform init -input=false -lockfile=readonly
# 組織Appの短期トークンをGITHUB_TOKEN、BotトークンをDISCORD_BOT_TOKENに設定する。
# 認証情報はシェル履歴やファイルに直接書かず、認証情報管理ツールから渡す。
terraform -chdir=terraform import 'github_membership.members["alice"]' Lumos-Programming:alice
terraform -chdir=terraform import 'github_team_membership.members["alice/lusy"]' lusy:alice
terraform -chdir=terraform import 'discord_role_member.members["1368752707321729158/123456789012345678/1381977862831083590"]' 1368752707321729158:1381977862831083590:123456789012345678
terraform -chdir=terraform plan
```

同じ所属を複数のstateから管理しないでください。別の構成で全員を一括管理する`github_team_members`を使っている場合も、この構成の個別管理と競合します。

## stateの復旧

stateはGitやActionsの成果物に保存しません。GCSのオブジェクトバージョンから復旧するときは、他の実行を止め、管理者が対象バージョンと実際の権限を確認して作業します。

GCSへのstate保存が失敗し、Terraformがローカル復旧ファイルを報告した場合は、古いリモートstateで再実行する前にそのファイルを保全・確認してください。GitHubの実行環境は一時的なので、該当実行のログをすぐに確認します。

## 担当者の引き継ぎ

- Cloud Identityの管理者グループに後任者を追加し、Google Cloudへのアクセスを確認する。
- GitHub Organization、App、レビュー担当チームの管理者を確認する。
- Discord開発者チームとサーバーの管理者を確認する。
- 各サービスに最低2名の管理者を維持する。
- 必要に応じてApp秘密鍵・Botトークンを更新し、`production`のSecretsを更新する。
- 後任者によるplan確認後に、退任者の権限を取り消す。
