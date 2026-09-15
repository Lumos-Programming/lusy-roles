set shell := ["bash", "-eu", "-o", "pipefail", "-c"]

python := "uv run --locked python"
terraform := "aqua exec -- terraform"

# 利用可能なコマンドを表示する。
default:
    @just --list

# メンバー定義・書式・Terraform構成を検証する。
validate:
    {{python}} scripts/validate.py
    {{terraform}} fmt -check -recursive terraform
    {{terraform}} -chdir=terraform init -backend=false -input=false -lockfile=readonly
    {{terraform}} -chdir=terraform validate

# 外部APIを使わず、すべての検証とモックテストを実行する。
test: validate lint
    {{python}} -m unittest discover -s tests -v
    {{terraform}} -chdir=terraform test

# YAMLの書式・GitHub Actions・初期構築スクリプトを検証する。
lint:
    aqua exec -- yamlfmt -conf .yamlfmt.yaml -lint .
    aqua exec -- actionlint .github/workflows/*.yml
    aqua exec -- shellcheck scripts/bootstrap-gcs.sh

# TerraformとYAMLの書式を整える。
fmt:
    {{terraform}} fmt -recursive terraform
    aqua exec -- yamlfmt -conf .yamlfmt.yaml .
