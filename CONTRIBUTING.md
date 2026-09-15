# 開発・変更ガイド

ドキュメント、PR本文、利用者向けの説明は日本語で記述します。

## CLIのセットアップ

[aqua](https://aquaproj.github.io/docs/install/)と[uv](https://docs.astral.sh/uv/getting-started/installation/)をインストールし、それぞれの実行ファイル用ディレクトリをPATHに追加してください。uvの必要バージョンは`pyproject.toml`の`tool.uv.required-version`で固定しています。リポジトリのルートで次を実行します。

```sh
aqua install
just test
```

`aqua.yaml`でjust、Terraform、tfcmt、yamlfmt、GitHub CLI、Google Cloud CLI、actionlint、shellcheckのバージョンを管理します。Pythonはuvが`.python-version`に従って用意します。YAML検証用のPyYAMLは`pyproject.toml`と`uv.lock`で管理し、`uv run --locked`で導入します。OSにPythonを別途インストールする必要はありません。

GitHub Actionsでは公式の`astral-sh/setup-uv`を使い、`pyproject.toml`からuvのバージョンを読み取ります。

Git・Bashは実行環境に必要です。初回はCLI、Python、Terraformプロバイダーのダウンロードが発生します。CIもaquaで同じCLI定義を使用します。Google Cloud CLIをローカルで初めて使う際は、uvのPythonを指定して認証できます。

```sh
export CLOUDSDK_PYTHON="$(uv run --locked python -c 'import sys; print(sys.executable)')"
gcloud auth login
gh auth login
```

## tfvarsの例

`terraform/terraform.tfvars.example`に入力変数の例を用意しています。既定値と同じため、通常の運用ではコピー不要です。ローカルで別ディレクトリを検証するときだけ`terraform/terraform.tfvars`としてコピーして調整します。メンバー情報は引き続きYAMLに記載し、認証情報はtfvarsに入れません。

## 変更前後の確認

```sh
just fmt       # TerraformとYAMLの書式を整える
just lint      # YAMLの書式・GitHub Actions・シェルスクリプトを検証
just test      # 入力検証・Terraform検証・モックテスト・ワークフロー検証
```

`just test`は本番stateに接続せず、GitHubやDiscordの権限を変更しません。実際のAPI動作は管理者が`Apply`で確認します。

YAMLの書式はyamlfmtで統一し、設定は`.yamlfmt.yaml`に置きます。CIでは`yamlfmt -lint`で未整形のファイルを検出します。メンバー定義・共通設定の拡張子は`.yaml`に統一し、Discord IDは引用符で囲んだ文字列にしてください。

## 変更対象

| 目的 | 変更するファイル |
| --- | --- |
| メンバーの追加・変更 | `members/<username>.yaml` |
| 申請可能なロールの追加 | `config/roles.yaml` |
| Organization・Discordサーバーの変更 | `config/organization.yaml`と関連するApp・OIDC設定 |
| 権限の展開方法の変更 | `terraform/main.tf`と`terraform/tests/` |
| 入力形式の変更 | `scripts/validate.py`、`tests/`、例、各ガイド |
| CLIの更新 | `aqua.yaml`と必要に応じて`.python-version` |
| uv・Python依存の更新 | `pyproject.toml`と`uv.lock`（変更後に`uv lock`） |

Terraformを更新する場合は、`terraform/versions.tf`の許容バージョンも確認します。プロバイダーを更新したら、ローカルとCIのチェックサムを更新してコミットします。

```sh
terraform -chdir=terraform init -backend=false -upgrade
terraform -chdir=terraform providers lock -platform=linux_amd64 -platform=darwin_arm64
just test
```

## レビュー時の注意

- メンバー変更では本人確認と要求権限を確認する。
- ロール一覧の変更は、そのロールを使う全員への影響を確認する。
- 認証・ワークフロー変更は、本番認証情報を使うジョブがPRのコードを実行しないことを確認する。
- 管理者が申請者向けの手順を読み、初見で申請できる状態を保つ。
- state、plan、トークン、秘密鍵はコミットしない。
