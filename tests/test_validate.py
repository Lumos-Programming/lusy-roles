import copy
import importlib.util
import json
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
        for path in (ROOT / "config").glob("*.json"):
            (self.root / "config" / path.name).write_text(path.read_text())
        self.member = json.loads((ROOT / "examples/alice.json").read_text())

    def write_member(self, member=None, name="alice.json"):
        (self.root / "members" / name).write_text(json.dumps(member or self.member))

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
        self.write_member(other, "bob.json")
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
        self.write_member(name="Alice.json")
        self.reject("filename and github_username")

    def test_duplicate_json_keys_are_rejected(self):
        (self.root / "members/alice.json").write_text('{"roles": [], "roles": ["lusy"]}')
        self.reject("duplicate JSON key")

    def test_unsupported_files_are_not_silently_ignored(self):
        (self.root / "members/alice.yaml").write_text("roles: [lusy]")
        self.reject("expected a flat")

    def test_symlinks_are_rejected(self):
        (self.root / "members/alice.json").symlink_to(ROOT / "examples/alice.json")
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
        path = self.root / "config/roles.json"
        roles = json.loads(path.read_text())
        organization = json.loads((self.root / "config/organization.json").read_text())
        roles["lusy"]["discord_role_ids"] = [organization["discord_server_id"]]
        path.write_text(json.dumps(roles))
        self.reject("@everyone")


if __name__ == "__main__":
    unittest.main()
