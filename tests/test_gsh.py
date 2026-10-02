"""Integration tests for the shell's observable startup and input behavior."""

from pathlib import Path
import subprocess
import tempfile
import unittest


BINARY = Path(__file__).resolve().parents[1] / "src" / "gsh"
ERROR = "An error has occurred\n"
PROMPT = "gsh> "


class ShellFoundationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.repository = self.root / "games"
        self.repository.mkdir()

    def run_shell(self, arguments=None, commands="exit\n"):
        if arguments is None:
            arguments = [str(self.repository)]
        # A timeout detects an EOF loop or a failure to recognize exit.
        return subprocess.run(
            [str(BINARY), *arguments],
            input=commands,
            capture_output=True,
            text=True,
            timeout=5,
        )

    def assert_result(self, result, status, stdout, stderr):
        self.assertEqual(result.returncode, status)
        self.assertEqual(result.stdout, stdout)
        self.assertEqual(result.stderr, stderr)

    def test_executable_was_built(self):
        self.assertTrue(BINARY.is_file(), "Build src/gsh before running tests")

    def test_rejects_invalid_startup_arguments_before_prompt(self):
        regular_file = self.root / "file.txt"
        regular_file.write_text("not a directory\n")
        cases = [
            [],
            [str(self.repository), "extra"],
            [str(self.root / "missing")],
            [str(regular_file)],
            [""],
        ]
        for arguments in cases:
            with self.subTest(arguments=arguments):
                self.assert_result(self.run_shell(arguments), 1, "", ERROR)

    def test_exit_accepts_a_valid_directory(self):
        self.assert_result(self.run_shell(), 0, PROMPT, "")

    def test_accepts_repository_path_containing_spaces(self):
        repository = self.root / "games with spaces"
        repository.mkdir()
        self.assert_result(self.run_shell([str(repository)]), 0, PROMPT, "")

    def test_exit_accepts_surrounding_spaces_and_tabs(self):
        self.assert_result(self.run_shell(commands=" \t exit \t \n"), 0, PROMPT, "")

    def test_blank_lines_are_not_errors(self):
        self.assert_result(
            self.run_shell(commands="\n \t \nexit\n"), 0, PROMPT * 3, ""
        )

    def test_eof_terminates_after_one_prompt(self):
        self.assert_result(self.run_shell(commands=""), 0, PROMPT, "")

    def test_exit_without_final_newline(self):
        self.assert_result(self.run_shell(commands="exit"), 0, PROMPT, "")

    def test_whitespace_without_final_newline(self):
        self.assert_result(self.run_shell(commands=" \t "), 0, PROMPT * 2, "")

    def test_exit_arguments_report_error_and_allow_next_command(self):
        self.assert_result(
            self.run_shell(commands="exit with arguments\nexit\n"),
            0,
            PROMPT * 2,
            ERROR,
        )

    def test_unsupported_command_reports_error_and_allows_next_command(self):
        self.assert_result(
            self.run_shell(commands="help\nexit\n"), 0, PROMPT * 2, ERROR
        )

    def test_multiple_errors_each_report_once(self):
        self.assert_result(
            self.run_shell(commands="exit\targument\nhelp\nexit\n"),
            0,
            PROMPT * 3,
            ERROR * 2,
        )

    def test_specification_length_command_is_handled(self):
        self.assert_result(
            self.run_shell(commands="x" * 255 + "\nexit\n"),
            0,
            PROMPT * 2,
            ERROR,
        )

    def test_many_whitespace_separated_arguments(self):
        self.assert_result(
            self.run_shell(commands="exit " + "x " * 120 + "\nexit\n"),
            0,
            PROMPT * 2,
            ERROR,
        )

    def test_exit_does_not_process_following_lines(self):
        self.assert_result(self.run_shell(commands="exit\nhelp\n"), 0, PROMPT, "")

    def test_prompt_is_flushed_before_input_is_available(self):
        import os
        import select

        with subprocess.Popen(
            [str(BINARY), str(self.repository)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ) as process:
            try:
                readable, _, _ = select.select([process.stdout], [], [], 5)
                self.assertTrue(readable, "Prompt must be flushed before getline")
                self.assertEqual(os.read(process.stdout.fileno(), 5), b"gsh> ")
                stdout, stderr = process.communicate(b"exit\n", timeout=5)
                self.assertEqual(process.returncode, 0)
                self.assertEqual(stdout, b"")
                self.assertEqual(stderr, b"")
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate()


if __name__ == "__main__":
    unittest.main()
