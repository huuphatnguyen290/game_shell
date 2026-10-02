"""Verify sorted repository listings using real help-producing executables."""

import os
from pathlib import Path
import select
import subprocess
import tempfile
import unittest


BINARY = Path(__file__).resolve().parents[1] / "src" / "gsh"
PROMPT = "gsh> "
ERROR = "An error has occurred\n"


class GameListingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.repository = self.root / "games"
        self.repository.mkdir()

    def create_game(self, name, body, repository=None):
        if repository is None:
            repository = self.repository
        game = repository / name
        game.write_text("#!/bin/sh\n" + body, encoding="utf-8")
        game.chmod(0o755)
        return game

    def run_shell(self, commands="ls\nexit\n", repository=None, cwd=None):
        if repository is None:
            repository = self.repository
        return subprocess.run(
            [str(BINARY), str(repository)], input=commands,
            capture_output=True, text=True, cwd=cwd, timeout=5,
        )

    def assert_result(self, result, stdout, stderr=""):
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, stdout)
        self.assertEqual(result.stderr, stderr)

    def test_lists_files_in_lexical_order_with_help_descriptions(self):
        self.create_game("zebra", "printf 'last\\n'\n")
        self.create_game("alpha", "printf 'lowercase\\n'\n")
        self.create_game("Beta", "printf 'uppercase\\n'\n")
        self.create_game("2048", "printf 'tiles\\n'\n")
        self.assert_result(
            self.run_shell(),
            PROMPT + "2048: tiles\nBeta: uppercase\nalpha: lowercase\nzebra: last\n" + PROMPT,
        )

    def test_help_receives_exactly_the_help_switch(self):
        self.create_game(
            "probe", "if [ \"$#\" -ne 1 ] || [ \"$1\" != '--help' ]; then exit 9; fi\n"
            "printf 'description\\n'\n",
        )
        self.assert_result(self.run_shell(), PROMPT + "probe: description\n" + PROMPT)

    def test_empty_repository_has_no_rows(self):
        self.assert_result(self.run_shell(), PROMPT * 2)

    def test_hidden_files_are_listed_and_directories_are_skipped(self):
        self.create_game(".hidden", "printf 'hidden\\n'\n")
        self.create_game("..name", "printf 'two dots\\n'\n")
        (self.repository / "subdirectory").mkdir()
        (self.repository / "directory-link").symlink_to("subdirectory")
        self.assert_result(
            self.run_shell(), PROMPT + "..name: two dots\n.hidden: hidden\n" + PROMPT
        )

    def test_non_executable_files_get_empty_descriptions(self):
        game = self.create_game("blocked", "printf 'must not run\\n'\n")
        game.chmod(0o644)
        (self.repository / "readme.txt").write_text("repository notes\n")
        self.assert_result(
            self.run_shell(), PROMPT + "blocked: (empty)\nreadme.txt: (empty)\n" + PROMPT
        )

    def test_empty_and_failed_help_get_empty_descriptions(self):
        self.create_game("empty", "exit 0\n")
        self.create_game("failed", "printf 'discard this\\n'\nprintf 'failure\\n' >&2\nexit 7\n")
        self.create_game("signaled", "kill -TERM $$\n")
        self.assert_result(
            self.run_shell(),
            PROMPT + "empty: (empty)\nfailed: (empty)\nsignaled: (empty)\n" + PROMPT,
        )

    def test_help_stderr_does_not_pollute_listing(self):
        self.create_game("probe", "printf 'description\\n'\nprintf 'diagnostic\\n' >&2\n")
        self.assert_result(self.run_shell(), PROMPT + "probe: description\n" + PROMPT)

    def test_description_newlines_are_normalized_without_losing_content(self):
        self.create_game("a", "printf 'no trailing newline'\n")
        self.create_game("b", "printf 'first\\n\\nsecond\\n\\n'\n")
        self.create_game("c", "printf '\\n\\n'\n")
        self.assert_result(
            self.run_shell(),
            PROMPT + "a: no trailing newline\nb: first\n\nsecond\nc: (empty)\n" + PROMPT,
        )

    def test_large_help_output_is_captured_completely(self):
        self.create_game("long", "python3 -c 'print(\"x\" * 100000)'\n")
        self.assert_result(self.run_shell(), PROMPT + "long: " + "x" * 100000 + "\n" + PROMPT)

    def test_file_links_are_listed_including_broken_links(self):
        self.create_game("probe", "printf 'description\\n'\n")
        (self.repository / "alias").symlink_to("probe")
        (self.repository / "broken").symlink_to("missing")
        self.assert_result(
            self.run_shell(),
            PROMPT + "alias: description\nbroken: (empty)\nprobe: description\n" + PROMPT,
        )

    def test_listing_uses_selected_repository_after_path(self):
        replacement = self.root / "replacement"
        replacement.mkdir()
        self.create_game("old", "printf 'old description\\n'\n")
        self.create_game("new", "printf 'new description\\n'\n", replacement)
        self.assert_result(
            self.run_shell(f"ls\npath {replacement}\nls\nexit\n"),
            PROMPT + "old: old description\n" + PROMPT * 2 + "new: new description\n" + PROMPT,
        )

    def test_listing_accepts_relative_repository_and_command_whitespace(self):
        self.create_game("probe", "printf 'description\\n'\n")
        self.assert_result(
            self.run_shell(" \tls \t\nexit\n", Path("games"), self.root),
            PROMPT + "probe: description\n" + PROMPT,
        )

    def test_listing_accepts_spaces_in_repository_and_filenames(self):
        repository = self.root / "games with spaces"
        repository.mkdir()
        self.create_game("a game", "printf 'description\\n'\n", repository)
        self.assert_result(
            self.run_shell(repository=repository), PROMPT + "a game: description\n" + PROMPT
        )

    def test_ls_arguments_report_error_then_shell_recovers(self):
        self.create_game("probe", "printf 'description\\n'\n")
        self.assert_result(
            self.run_shell("ls extra\nls\nexit\n"),
            PROMPT * 2 + "probe: description\n" + PROMPT,
            ERROR,
        )

    def test_help_cannot_consume_following_shell_commands(self):
        self.create_game(
            "probe", "if [ \"$1\" = '--help' ]; then\n"
            "  IFS= read -r move\n  printf 'description\\n'\n"
            "else\n  printf 'played\\n'\nfi\n",
        )
        self.assert_result(
            self.run_shell("ls\nprobe\nexit\n"),
            PROMPT + "probe: description\n" + PROMPT + "played\n" + PROMPT,
        )

    def test_repeated_listing_closes_descriptors_and_creates_no_repository_files(self):
        self.create_game("probe", "printf 'description\\n'\n")
        files_before = sorted(path.name for path in self.repository.iterdir())
        with subprocess.Popen(
            [str(BINARY), str(self.repository)], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        ) as process:
            try:
                self.assertEqual(self.read_prompt(process), b"gsh> ")
                descriptor_directory = Path(f"/proc/{process.pid}/fd")
                descriptors_before = len(list(descriptor_directory.iterdir()))
                for _ in range(8):
                    process.stdin.write(b"ls\n")
                    process.stdin.flush()
                    self.assertEqual(self.read_prompt(process), b"probe: description\ngsh> ")
                    self.assertEqual(len(list(descriptor_directory.iterdir())), descriptors_before)
                stdout, stderr = process.communicate(b"exit\n", timeout=5)
                self.assertEqual(process.returncode, 0)
                self.assertEqual(stdout, b"")
                self.assertEqual(stderr, b"")
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate(timeout=5)
        self.assertEqual(sorted(path.name for path in self.repository.iterdir()), files_before)

    def read_prompt(self, process):
        output = b""
        while not output.endswith(b"gsh> "):
            readable, _, _ = select.select([process.stdout], [], [], 3)
            self.assertTrue(readable, f"Timed out after output: {output!r}")
            chunk = os.read(process.stdout.fileno(), 1)
            self.assertTrue(chunk, f"Unexpected EOF after output: {output!r}")
            output += chunk
        return output


if __name__ == "__main__":
    unittest.main()
