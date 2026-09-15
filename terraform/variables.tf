variable "members_path" {
  description = "メンバー定義ディレクトリ。相対パスはこのTerraformルートを基準にする。"
  type        = string
  default     = "../members"
}

variable "config_path" {
  description = "Organization設定とロール一覧のディレクトリ。"
  type        = string
  default     = "../config"
}
