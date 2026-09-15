import copy
import importlib.util
import yaml
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("validate", ROOT / "scripts/validate.py")
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


class MembershipValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "members").mkdir()
        (self.root / "config").mkdir()
        for path in (ROOT / "config").glob("*.yaml"):
            (self.root / "config" / path.name).write_text(path.read_text())
        self.member = yaml.safe_load((ROOT / "examples/alice.yaml").read_text())

    def write_member(self, member=None, name="alice.yaml"):
        (self.root / "members" / name).write_text(yaml.safe_dump(member or self.member))

    def reject(self, pattern):
        with self.assertRaisesRegex(VALIDATOR.ValidationError, pattern):
            VALIDATOR.validate(self.root)

    def test_empty_roster_is_valid_for_offboarding_last_member(self):
        self.assertEqual(VALIDATOR.validate(self.root), 0)

    def test_example_is_valid(self):
        self.write_member()
        self.assertEqual(VALIDATOR.validate(self.root), 1)

    def test_unknown_role_is_rejected(self):
        self.member["roles"] = ["typo"]
        self.write_member()
        self.reject("unknown role")

    def test_duplicate_discord_identity_is_rejected(self):
        self.write_member()
        other = copy.deepcopy(self.member)
        other["github_username"] = "bob"
        self.write_member(other, "bob.yaml")
        self.reject("duplicate Discord user ID")

    def test_numeric_discord_id_is_rejected(self):
        self.member["discord_user_id"] = 123456789012345678
        self.write_member()
        self.reject("invalid identifier")

    def test_misspelled_field_is_rejected(self):
        self.member["github_org_roles"] = self.member.pop("github_org_role")
        self.write_member()
        self.reject("expected exactly these fields")

    def test_admin_is_explicitly_supported(self):
        self.member["github_org_role"] = "admin"
        self.write_member()
        self.assertEqual(VALIDATOR.validate(self.root), 1)

    def test_filename_must_match_lowercase_username(self):
        self.write_member(name="Alice.yaml")
        self.reject("filename and github_username")

    def test_duplicate_yaml_keys_are_rejected(self):
        (self.root / "members/alice.yaml").write_text("roles: []\nroles: [lusy]\n")
        self.reject("duplicate YAML key")

    def test_unsupported_files_are_not_silently_ignored(self):
        (self.root / "members/alice.json").write_text('{"roles": ["lusy"]}')
        self.reject("expected a flat")

    def test_yaml_comments_and_block_lists_are_supported(self):
        (self.root / "members/alice.yaml").write_text(
            'github_username: alice # GitHubユーザー名\n'
            'github_org_role: member\n'
            'discord_user_id: "123456789012345678"\n'
            'roles:\n  - lusy\n'
        )
        self.assertEqual(VALIDATOR.validate(self.root), 1)

    def test_yaml_12_boolean_like_username_is_a_string(self):
        (self.root / "members/no.yaml").write_text(
            'github_username: no\ngithub_org_role: member\n'
            'discord_user_id: "123456789012345678"\nroles: [lusy]\n'
        )
        self.assertEqual(VALIDATOR.validate(self.root), 1)

    def test_multiple_yaml_documents_are_rejected(self):
        self.write_member()
        path = self.root / "members/alice.yaml"
        path.write_text(path.read_text() + "---\nroles: []\n")
        self.reject("single document")

    def test_malformed_yaml_is_rejected(self):
        (self.root / "members/alice.yaml").write_text("roles: [lusy\n")
        self.reject("alice.yaml")

    def test_python_yaml_tags_are_rejected(self):
        (self.root / "members/alice.yaml").write_text("!!python/tuple [lusy]\n")
        self.reject("constructor")

    def test_collection_mapping_keys_are_rejected(self):
        (self.root / "members/alice.yaml").write_text("? [roles]\n: [lusy]\n")
        self.reject("mapping keys must be strings")

    def test_duplicate_role_catalog_keys_are_rejected(self):
        path = self.root / "config/roles.yaml"
        path.write_text(path.read_text() + path.read_text())
        self.reject("duplicate YAML key")

    def test_symlinks_are_rejected(self):
        (self.root / "members/alice.yaml").symlink_to(ROOT / "examples/alice.yaml")
        self.reject("symlinks")

    def test_duplicate_role_is_rejected(self):
        self.member["roles"] = ["lusy", "lusy"]
        self.write_member()
        self.reject("duplicate values")

    def test_empty_roles_keeps_organization_membership(self):
        self.member["roles"] = []
        self.write_member()
        self.assertEqual(VALIDATOR.validate(self.root), 1)

    def test_everyone_role_is_rejected(self):
        path = self.root / "config/roles.yaml"
        roles = yaml.safe_load(path.read_text())
        organization = yaml.safe_load((self.root / "config/organization.yaml").read_text())
        roles["lusy"]["discord_role_ids"] = [organization["discord_server_id"]]
        path.write_text(yaml.safe_dump(roles))
        self.reject("@everyone")


if __name__ == "__main__":
    unittest.main()
