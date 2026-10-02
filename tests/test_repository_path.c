/* Exercise real repository state before game execution is available. */
#define main gsh_main
#include "../src/gsh.c"
#undef main

#define CHECK(condition) do { \
    if (!(condition)) { \
        fprintf(stderr, "Failed: %s\n", #condition); \
        return EXIT_FAILURE; \
    } \
} while (0)

int main(int argc, char **argv)
{
    char *repository_path;
    char *input_path;
    char *saved_path;

    CHECK(argc == 5);
    repository_path = strdup(argv[1]);
    input_path = strdup(argv[2]);
    CHECK(repository_path != NULL && input_path != NULL);

    CHECK(change_repository(&repository_path, input_path) == 0);
    CHECK(strcmp(repository_path, argv[2]) == 0);
    CHECK(repository_path != input_path);

    /* getline() storage will be overwritten by the next command. */
    input_path[0] = '!';
    free(input_path);
    CHECK(strcmp(repository_path, argv[2]) == 0);

    saved_path = repository_path;
    CHECK(change_repository(&repository_path, argv[3]) == -1);
    CHECK(repository_path == saved_path);
    CHECK(strcmp(repository_path, argv[2]) == 0);
    CHECK(change_repository(&repository_path, argv[4]) == -1);
    CHECK(repository_path == saved_path);
    CHECK(strcmp(repository_path, argv[2]) == 0);

    /* Even an alias of the current repository must be safe to replace. */
    CHECK(change_repository(&repository_path, repository_path) == 0);
    CHECK(strcmp(repository_path, argv[2]) == 0);
    CHECK(change_repository(&repository_path, argv[1]) == 0);
    CHECK(strcmp(repository_path, argv[1]) == 0);

    free(repository_path);
    return EXIT_SUCCESS;
}
