/*
 * Date: 2026-10-02
 * Name and NetID: to be supplied by the author before submission.
 * Description: An interactive shell for a user-selected game repository.
 * Supports command input, exit, and repository path changes.
 */

#define _POSIX_C_SOURCE 200809L

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

/* Enough slots for every token in a specified 255-character command and NULL. */
#define MAX_ARGUMENTS 256

/* Keep shell errors identical regardless of the operation that failed. */
static void report_error(void)
{
    const char error_message[] = "An error has occurred\n";

    (void)write(STDERR_FILENO, error_message, strlen(error_message));
    fflush(stderr);
}

/* stat() accepts both directories and symbolic links resolving to directories. */
static int is_directory(const char *path)
{
    struct stat information;

    return stat(path, &information) == 0 && S_ISDIR(information.st_mode);
}

/* Preserve the current repository unless validation and allocation succeed. */
static int change_repository(char **repository_path, const char *new_path)
{
    char *replacement;

    if (!is_directory(new_path)) {
        return -1;
    }
    replacement = strdup(new_path);
    if (replacement == NULL) {
        return -1;
    }

    free(*repository_path);
    *repository_path = replacement;
    return 0;
}

/* Tokens borrow storage from line; the resulting array can later feed execvp(). */
static size_t parse_arguments(char *line, char **arguments)
{
    const char *whitespace = " \t\r\n\v\f";
    char *save_pointer = NULL;
    char *token = strtok_r(line, whitespace, &save_pointer);
    size_t count = 0;

    while (token != NULL) {
        /* Reject oversized input instead of writing beyond the argument array. */
        if (count == MAX_ARGUMENTS - 1) {
            arguments[count] = NULL;
            return MAX_ARGUMENTS;
        }
        arguments[count++] = token;
        token = strtok_r(NULL, whitespace, &save_pointer);
    }
    arguments[count] = NULL;
    return count;
}

int main(int argc, char **argv)
{
    char *repository_path;
    char *line = NULL;
    size_t capacity = 0;
    int result = EXIT_SUCCESS;

    /* Invalid invocation must fail before the first prompt appears. */
    if (argc != 2 || !is_directory(argv[1])) {
        report_error();
        exit(EXIT_FAILURE);
    }

    /* Own the path separately from argv and the reusable command-line buffer. */
    repository_path = strdup(argv[1]);
    if (repository_path == NULL) {
        report_error();
        exit(EXIT_FAILURE);
    }

    for (;;) {
        char *arguments[MAX_ARGUMENTS];
        size_t argument_count;

        /* Flush the prompt before blocking for input, including when piped. */
        if (fputs("gsh> ", stdout) == EOF || fflush(stdout) == EOF) {
            report_error();
            result = EXIT_FAILURE;
            break;
        }

        if (getline(&line, &capacity, stdin) == -1) {
            /* EOF is normal; a stream read failure is a shell error. */
            if (!feof(stdin)) {
                report_error();
                result = EXIT_FAILURE;
            }
            break;
        }

        argument_count = parse_arguments(line, arguments);
        if (argument_count == 0) {
            continue;
        }
        if (argument_count == MAX_ARGUMENTS) {
            report_error();
            continue;
        }

        if (strcmp(arguments[0], "exit") == 0) {
            if (argument_count != 1) {
                report_error();
                continue;
            }
            free(line);
            free(repository_path);
            exit(EXIT_SUCCESS);
        }

        if (strcmp(arguments[0], "path") == 0) {
            if (argument_count != 2 ||
                change_repository(&repository_path, arguments[1]) != 0) {
                report_error();
            }
            continue;
        }

        /* Later tasks add repository listing and game execution here. */
        report_error();
    }

    free(line);
    free(repository_path);
    return result;
}
