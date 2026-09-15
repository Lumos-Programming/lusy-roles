import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from prepare_pr_plan import prepare_snapshot  # noqa: E402
from validate import ValidationError  # noqa: E402


class PRPlanSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.repo = self.directory / "repo"
        self.repo.mkdir()
        (self.repo / "members").mkdir()
        (self.repo / "members/.gitkeep").touch()
        shutil.copytree(ROOT / "config", self.repo / "config")
        self.git("init", "-b", "main")
        self.git("config", "commit.gpgsign", "false")
        self.base = self.commit()

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.repo), *args], stderr=subprocess.PIPE).decode().strip()

    def commit(self):
        self.git("add", ".")
        self.git("-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "fixture")
        return self.git("rev-parse", "HEAD")

    def add_alice(self):
        shutil.copyfile(ROOT / "examples/alice.yaml", self.repo / "members/alice.yaml")

    def prepare(self, head):
        return prepare_snapshot(self.repo, self.base, head, self.directory / "snapshot")

    def test_add_member_uses_pinned_head_and_main_config(self):
        self.add_alice()
        head = self.commit()
        self.git("checkout", self.base)
        members = self.prepare(head)
        self.assertEqual((members / "alice.yaml").read_bytes(), (ROOT / "examples/alice.yaml").read_bytes())
        self.assertFalse((self.repo / "members/alice.yaml").exists())
        self.assertEqual((members.parent / "config/roles.yaml").read_bytes(), (ROOT / "config/roles.yaml").read_bytes())

    def test_member_deletion_is_reflected_in_full_snapshot(self):
        self.add_alice()
        self.base = self.commit()
        (self.repo / "members/alice.yaml").unlink()
        members = self.prepare(self.commit())
        self.assertEqual(list(members.glob("*.yaml")), [])

    def test_code_or_catalog_changes_are_rejected(self):
        self.add_alice()
        (self.repo / "config/roles.yaml").write_text("lusy: {}\n")
        with self.assertRaisesRegex(ValidationError, "メンバー定義以外"):
            self.prepare(self.commit())

    def test_symlinks_cannot_read_runner_files(self):
        (self.repo / "members/alice.yaml").symlink_to("/etc/passwd")
        with self.assertRaisesRegex(ValidationError, "通常のメンバー"):
            self.prepare(self.commit())

    def test_executable_members_are_rejected(self):
        self.add_alice()
        (self.repo / "members/alice.yaml").chmod(0o755)
        with self.assertRaisesRegex(ValidationError, "通常のメンバー"):
            self.prepare(self.commit())

    def test_invalid_member_content_is_rejected(self):
        (self.repo / "members/alice.yaml").write_text("roles: [unknown]\n")
        with self.assertRaisesRegex(ValidationError, "expected exactly"):
            self.prepare(self.commit())

    def test_nested_members_are_rejected(self):
        (self.repo / "members/nested").mkdir()
        shutil.copyfile(ROOT / "examples/alice.yaml", self.repo / "members/nested/alice.yaml")
        with self.assertRaisesRegex(ValidationError, "メンバー定義以外"):
            self.prepare(self.commit())

    def test_pr_must_include_latest_main(self):
        self.git("checkout", "-b", "onboarding")
        self.add_alice()
        head = self.commit()
        self.git("checkout", "main")
        (self.repo / "README.md").write_text("更新\n")
        self.base = self.commit()
        with self.assertRaisesRegex(ValidationError, "最新のmain"):
            self.prepare(head)
