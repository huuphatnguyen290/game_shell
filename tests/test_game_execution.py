"""Run real executable fixtures to verify game dispatch and process behavior."""

import os
from pathlib import Path
import select
import subprocess
import tempfile
import time
import unittest


BINARY = Path(__file__).resolve().parents[1] / "src" / "gsh"
PROMPT = "gsh> "
ERROR = "An error has occurred\n"


class GameExecutionTests(unittest.TestCase):
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

    def run_shell(self, commands, repository=None, cwd=None):
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

    def test_runs_repository_game_and_forwards_arguments(self):
        self.create_game("probe", "printf 'arg:%s\\n' \"$@\"\n")
        self.assert_result(
            self.run_shell(" \tprobe\t--seed  0 \t\nexit\n"),
            PROMPT + "arg:--seed\narg:0\n" + PROMPT,
        )

    def test_runs_game_from_repository_containing_spaces(self):
        repository = self.root / "games with spaces"
        repository.mkdir()
        self.create_game("probe", "printf 'hello\\n'\n", repository)
        self.assert_result(
            self.run_shell("probe\nexit\n", repository),
            PROMPT + "hello\n" + PROMPT,
        )

    def test_runs_game_from_relative_repository(self):
        self.create_game("probe", "printf 'relative\\n'\n")
        self.assert_result(
            self.run_shell("probe\nexit\n", Path("games"), self.root),
            PROMPT + "relative\n" + PROMPT,
        )

    def test_path_selects_replacement_repository(self):
        replacement = self.root / "replacement"
        replacement.mkdir()
        self.create_game("probe", "printf 'old\\n'\n")
        self.create_game("probe", "printf 'new\\n'\n", replacement)
        self.assert_result(
            self.run_shell(f"probe\npath {replacement}\nprobe\nexit\n"),
            PROMPT + "old\n" + PROMPT * 2 + "new\n" + PROMPT,
        )

    def test_invalid_path_preserves_repository_for_game_execution(self):
        self.create_game("probe", "printf 'original\\n'\n")
        regular_file = self.root / "file.txt"
        regular_file.write_text("not a directory\n")
        for command in [
            "path", f"path {regular_file}", f"path {self.root / 'missing'}",
            f"path {self.repository} extra",
        ]:
            with self.subTest(command=command):
                self.assert_result(
                    self.run_shell(f"{command}\nprobe\nexit\n"),
                    PROMPT * 2 + "original\n" + PROMPT,
                    ERROR,
                )

    def test_missing_game_reports_once_then_next_game_runs(self):
        self.create_game("probe", "printf 'recovered\\n'\n")
        self.assert_result(
            self.run_shell("missing\nprobe\nexit\n"),
            PROMPT * 2 + "recovered\n" + PROMPT,
            ERROR,
        )

    def test_non_executable_game_reports_once_then_next_game_runs(self):
        game = self.create_game("blocked", "printf 'must not run\\n'\n")
        game.chmod(0o644)
        self.create_game("probe", "printf 'recovered\\n'\n")
        self.assert_result(
            self.run_shell("blocked\nprobe\nexit\n"),
            PROMPT * 2 + "recovered\n" + PROMPT,
            ERROR,
        )

    def test_directory_cannot_be_executed_as_game(self):
        (self.repository / "directory").mkdir()
        self.assert_result(self.run_shell("directory\nexit\n"), PROMPT * 2, ERROR)

    def test_missing_repository_game_does_not_use_system_path(self):
        self.assert_result(self.run_shell("true\nexit\n"), PROMPT * 2, ERROR)

    def test_waits_for_game_before_next_prompt_and_command(self):
        self.create_game("slow", "sleep 0.15\nprintf 'finished\\n'\n")
        self.create_game("probe", "printf 'next\\n'\n")
        self.assert_result(
            self.run_shell("slow\nprobe\nexit\n"),
            PROMPT + "finished\n" + PROMPT + "next\n" + PROMPT,
        )

    def test_game_error_is_preserved_without_additional_shell_error(self):
        self.create_game("badmove", "printf 'bad move\\n' >&2\nexit 7\n")
        self.create_game("probe", "printf 'next\\n'\n")
        self.assert_result(
            self.run_shell("badmove\nprobe\nexit\n"),
            PROMPT * 2 + "next\n" + PROMPT,
            "bad move\n",
        )

    def test_shell_continues_after_game_terminates_by_signal(self):
        self.create_game("crash", "kill -TERM $$\n")
        self.create_game("probe", "printf 'next\\n'\n")
        self.assert_result(
            self.run_shell("crash\nprobe\nexit\n"),
            PROMPT * 2 + "next\n" + PROMPT,
        )

    def test_game_can_read_queued_input_without_shell_read_ahead(self):
        self.create_game("replay", "IFS= read -r move\nprintf 'move:%s\\n' \"$move\"\n")
        self.create_game("probe", "printf 'next\\n'\n")
        self.assert_result(
            self.run_shell("replay\n4\nprobe\nexit\n"),
            PROMPT + "move:4\n" + PROMPT + "next\n" + PROMPT,
        )

    def test_game_can_read_interactive_input_and_shell_resumes(self):
        self.create_game(
            "replay", "printf 'ready\\n'\nIFS= read -r move\nprintf 'move:%s\\n' \"$move\"\n"
        )
        with subprocess.Popen(
            [str(BINARY), str(self.repository)], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        ) as process:
            try:
                self.assertEqual(self.read_until(process, b"gsh> "), b"gsh> ")
                process.stdin.write(b"replay\n")
                process.stdin.flush()
                self.assertEqual(self.read_until(process, b"ready\n"), b"ready\n")
                process.stdin.write(b"4\n")
                process.stdin.flush()
                self.assertEqual(self.read_until(process, b"gsh> "), b"move:4\ngsh> ")
                stdout, stderr = process.communicate(b"exit\n", timeout=5)
                self.assertEqual(process.returncode, 0)
                self.assertEqual(stdout, b"")
                self.assertEqual(stderr, b"")
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate(timeout=5)

    def read_until(self, process, ending):
        output = b""
        deadline = time.monotonic() + 3
        while not output.endswith(ending):
            remaining = deadline - time.monotonic()
            self.assertGreater(remaining, 0, f"Timed out after output: {output!r}")
            readable, _, _ = select.select([process.stdout], [], [], remaining)
            self.assertTrue(readable, f"Timed out after output: {output!r}")
            chunk = os.read(process.stdout.fileno(), 1)
            self.assertTrue(chunk, f"Unexpected EOF after output: {output!r}")
            output += chunk
        return output


if __name__ == "__main__":
    unittest.main()
