"""Exercise replay files, redirection syntax, and parent stdin preservation."""

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


class InputRedirectionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.repository = self.root / "games"
        self.repository.mkdir()
        self.started = self.root / "started"
        self.moves = self.root / "moves.txt"
        self.moves.write_text("4\n7\n1\n")
        self.create_game(
            "replay", f"printf 'started\\n' > '{self.started}'\n"
            "for argument in \"$@\"; do printf 'arg:%s\\n' \"$argument\"; done\ncat\n",
        )
        self.create_game("probe", "printf 'next\\n'\n")

    def create_game(self, name, body, repository=None):
        if repository is None:
            repository = self.repository
        game = repository / name
        game.write_text("#!/bin/sh\n" + body, encoding="utf-8")
        game.chmod(0o755)
        return game

    def run_shell(self, commands, cwd=None, **options):
        return subprocess.run(
            [str(BINARY), str(self.repository)], input=commands,
            capture_output=True, text=True, cwd=cwd, timeout=5, **options,
        )

    def assert_result(self, result, stdout, stderr=""):
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, stdout)
        self.assertEqual(result.stderr, stderr)

    def test_redirects_replay_file_and_forwards_only_game_arguments(self):
        self.assert_result(
            self.run_shell(f"replay --seed 0 < {self.moves}\nexit\n"),
            PROMPT + "arg:--seed\narg:0\n4\n7\n1\n" + PROMPT,
        )
        self.assertTrue(self.started.exists())

    def test_redirection_accepts_spaces_tabs_and_relative_input_file(self):
        self.assert_result(
            self.run_shell(" \treplay \t<\t moves.txt \t\nexit\n", cwd=self.root),
            PROMPT + "4\n7\n1\n" + PROMPT,
        )

    def test_empty_file_is_valid_input_and_game_still_runs(self):
        self.moves.write_text("")
        self.assert_result(self.run_shell(f"replay < {self.moves}\nexit\n"), PROMPT * 2)
        self.assertTrue(self.started.exists())

    def test_replay_preserves_input_without_final_newline(self):
        self.moves.write_text("4")
        self.assert_result(
            self.run_shell(f"replay < {self.moves}\nexit\n"), PROMPT + "4" + PROMPT
        )

    def test_malformed_redirection_never_executes_game_and_shell_recovers(self):
        self.create_game("<", f"printf 'started\\n' > '{self.started}'\n")
        cases = [
            "replay <", f"replay < {self.moves} extra",
            f"replay < {self.moves} < {self.moves}", "replay < <",
            f"replay < < {self.moves}", f"< {self.moves}", "<",
        ]
        for command in cases:
            with self.subTest(command=command):
                if self.started.exists():
                    self.started.unlink()
                self.assert_result(
                    self.run_shell(f"{command}\nprobe\nexit\n"),
                    PROMPT * 2 + "next\n" + PROMPT,
                    ERROR,
                )
                self.assertFalse(self.started.exists(), "Invalid syntax must not start the game")

    def test_missing_input_file_prevents_execution_and_allows_next_command(self):
        self.assert_result(
            self.run_shell(f"replay < {self.root / 'missing'}\nprobe\nexit\n"),
            PROMPT * 2 + "next\n" + PROMPT,
            ERROR,
        )
        self.assertFalse(self.started.exists())

    def test_unreadable_input_file_prevents_execution(self):
        self.moves.chmod(0o000)
        options = {}
        if os.geteuid() == 0:
            # Root bypasses file permissions; use an unprivileged child instead.
            self.root.chmod(0o777)
            self.repository.chmod(0o755)
            options = {"user": 65534, "group": 65534, "extra_groups": []}
        self.assert_result(
            self.run_shell(f"replay < {self.moves}\nprobe\nexit\n", **options),
            PROMPT * 2 + "next\n" + PROMPT,
            ERROR,
        )
        self.assertFalse(self.started.exists())

    def test_redirection_preserves_shell_input_and_later_interactive_game(self):
        self.create_game("interactive", "IFS= read -r move\nprintf 'move:%s\\n' \"$move\"\n")
        self.assert_result(
            self.run_shell(f"replay < {self.moves}\ninteractive\n9\nprobe\nexit\n"),
            PROMPT + "4\n7\n1\n" + PROMPT + "move:9\n" + PROMPT + "next\n" + PROMPT,
        )

    def test_missing_game_after_opening_input_reports_once_and_recovers(self):
        self.assert_result(
            self.run_shell(f"missing < {self.moves}\nprobe\nexit\n"),
            PROMPT * 2 + "next\n" + PROMPT,
            ERROR,
        )

    def test_non_executable_game_after_opening_input_reports_once_and_recovers(self):
        self.create_game("blocked", "printf 'must not run\\n'\n").chmod(0o644)
        self.assert_result(
            self.run_shell(f"blocked < {self.moves}\nprobe\nexit\n"),
            PROMPT * 2 + "next\n" + PROMPT,
            ERROR,
        )

    def test_attached_operator_text_is_a_literal_argument(self):
        self.create_game("arguments", "printf 'arg:%s\\n' \"$@\"\n")
        for argument in ["value<file", "<file"]:
            with self.subTest(argument=argument):
                self.assert_result(
                    self.run_shell(f"arguments {argument}\nexit\n"),
                    PROMPT + f"arg:{argument}\n" + PROMPT,
                )

    def test_input_filename_can_contain_an_attached_less_than_character(self):
        moves = self.root / "moves<one.txt"
        moves.write_text("4\n")
        self.assert_result(
            self.run_shell(f"replay < {moves}\nexit\n"), PROMPT + "4\n" + PROMPT
        )

    def test_redirection_uses_repository_selected_by_path(self):
        replacement = self.root / "replacement"
        replacement.mkdir()
        self.create_game("replay", "printf 'new repository\\n'\ncat\n", replacement)
        self.assert_result(
            self.run_shell(f"path {replacement}\nreplay < {self.moves}\nexit\n"),
            PROMPT * 2 + "new repository\n4\n7\n1\n" + PROMPT,
        )
        self.assertFalse(self.started.exists())

    def test_repeated_redirection_closes_parent_descriptors_on_success_and_failure(self):
        self.create_game("noop", "printf 'done\\n'\n")
        with subprocess.Popen(
            [str(BINARY), str(self.repository)], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        ) as process:
            try:
                self.assertEqual(self.read_prompt(process), b"gsh> ")
                descriptor_directory = Path(f"/proc/{process.pid}/fd")
                descriptors_before = len(list(descriptor_directory.iterdir()))
                for _ in range(8):
                    for command, output in [
                        (f"noop < {self.moves}\n", b"done\ngsh> "),
                        (f"missing < {self.moves}\n", b"gsh> "),
                    ]:
                        process.stdin.write(command.encode())
                        process.stdin.flush()
                        self.assertEqual(self.read_prompt(process), output)
                        self.assertEqual(len(list(descriptor_directory.iterdir())), descriptors_before)
                stdout, stderr = process.communicate(b"exit\n", timeout=5)
                self.assertEqual(process.returncode, 0)
                self.assertEqual(stdout, b"")
                self.assertEqual(stderr, ERROR.encode() * 8)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate(timeout=5)

    def read_prompt(self, process):
        output = b""
        deadline = time.monotonic() + 3
        while not output.endswith(b"gsh> "):
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
