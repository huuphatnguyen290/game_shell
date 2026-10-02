# Game Shell

Incremental POSIX C implementation of the project specification, kept locally
in `game_shell_specification.md` and excluded from Git.

## Build and Run

Build on Linux with GCC and Make:

```sh
make -C src
./src/gsh /path/to/games
```

The shell prints `gsh> ` and accepts `exit` and `path`. Exactly one existing directory
is required at startup. Empty lines are ignored, and `exit` with arguments
prints the specified error and allows another command. EOF also exits cleanly.

Use `path /new/path/to/games` to replace the game repository. It requires exactly
one existing directory; invalid arguments print the specified error and preserve
the current repository. Spaces and tabs around the command are accepted.

## Tests

Development tests require Python 3 on Linux; the shell itself requires only C.

```sh
make -C src test
```

For a build that treats compiler warnings as errors:

```sh
make -C src clean
make -C src CFLAGS='-std=c11 -Wall -Wextra -Wpedantic -Werror'
make -C src test
```

## Task Branches

Each task uses a separate branch, inheriting the previous task's implementation.
Work pauses after each task for review. The implementation plan is kept locally
under `docs/`, which is excluded from Git.

| Task | Branch | Scope | Status |
| --- | --- | --- | --- |
| 1 | `task/01-shell-foundation` | Startup checks, prompt, parsing, `exit`, EOF | Complete |
| 2 | `task/02-repository-path` | `path` built-in | Complete; awaiting review |
| 3 | `task/03-game-execution` | Run games and wait for completion | Pending |
| 4 | `task/04-game-listing` | Sorted `ls` with captured help descriptions | Pending |
| 5 | `task/05-input-redirection` | `<` parsing and game stdin redirection | Pending |
| 6 | `task/06-submission-packaging` | Final verification, author header, `gsh.zip` | Pending |

At Task 2, all commands besides `exit` and `path` report `An error has occurred`.
The author's Name and NetID will be added to the source header before submission.

Task 1 verification: all 16 integration tests passed in an Ubuntu 22.04
container using GCC 11.4.0 with `-Wall -Wextra -Wpedantic -Werror`.

Task 2 verification: all 26 tests passed in the same Linux environment, including
a C test of repository ownership and preservation after invalid path changes.
