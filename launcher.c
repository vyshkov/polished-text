#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <sys/wait.h>
#include <time.h>

#define RESTART_EXIT_CODE 42

#ifndef PYTHON_HOME_DIR
#define PYTHON_HOME_DIR "/opt/homebrew/opt/python@3.14/Frameworks/Python.framework/Versions/3.14"
#endif

static int run_child_python(int argc, char *argv[]) {
    const char *home = getenv("HOME");
    if (!home) home = "";

    char config_dir[1024];
    char main_py[1024];
    snprintf(config_dir, sizeof(config_dir), "%s/.config/dictation", home);
    snprintf(main_py, sizeof(main_py), "%s/main.py", config_dir);

    setenv("DICTATION_IS_CHILD", "1", 1);

    PyConfig config;
    PyConfig_InitPythonConfig(&config);

    // Set Python framework runtime & program name
    const char *py_home = getenv("PYTHONHOME");
    if (!py_home || strlen(py_home) == 0) {
        py_home = PYTHON_HOME_DIR;
    }
    PyConfig_SetBytesString(&config, &config.home, (char *)py_home);
    PyConfig_SetBytesString(&config, &config.program_name, "Gemini Assistant");

    int total_args = argc > 1 ? argc + 1 : 2;
    char **py_args = (char **)malloc((total_args) * sizeof(char *));
    py_args[0] = (char *)"Gemini Assistant";
    py_args[1] = main_py;
    for (int i = 1; i < argc; i++) {
        py_args[i + 1] = argv[i];
    }
    PyConfig_SetBytesArgv(&config, total_args, py_args);

    PyStatus status = Py_InitializeFromConfig(&config);
    PyConfig_Clear(&config);
    if (PyStatus_Exception(status)) {
        Py_ExitStatusException(status);
    }

    // Ensure virtualenv site-packages is in sys.path
    PyRun_SimpleString(
        "import sys, os\n"
        "script_dir = os.path.expanduser('~/.config/dictation')\n"
        "venv_site = os.path.join(script_dir, 'venv/lib/python3.14/site-packages')\n"
        "if venv_site not in sys.path:\n"
        "    sys.path.insert(0, venv_site)\n"
    );

    return Py_RunMain();
}

int main(int argc, char *argv[]) {
    const char *home = getenv("HOME");
    if (!home) home = "";

    char config_dir[1024];
    char log_file[1024];
    char path_env[2048];

    snprintf(config_dir, sizeof(config_dir), "%s/.config/dictation", home);
    snprintf(log_file, sizeof(log_file), "%s/app.log", config_dir);

    // Setup PATH and unbuffered output
    const char *old_path = getenv("PATH");
    snprintf(path_env, sizeof(path_env), "/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:%s", old_path ? old_path : "/usr/bin:/bin");
    setenv("PATH", path_env, 1);
    setenv("PYTHONUNBUFFERED", "1", 1);

    // Redirect stdout/stderr to app.log if running in GUI background mode
    if (!isatty(STDOUT_FILENO)) {
        FILE *log_fp = fopen(log_file, "a");
        if (log_fp) {
            int log_fd = fileno(log_fp);
            dup2(log_fd, STDOUT_FILENO);
            dup2(log_fd, STDERR_FILENO);
            fclose(log_fp);
        }
    }

    while (1) {
        time_t now = time(NULL);
        char time_buf[64];
        strftime(time_buf, sizeof(time_buf), "%Y-%m-%d %H:%M:%S", localtime(&now));
        printf("%s [INFO] [Launcher] Starting Gemini Assistant (supervisor PID: %d)\n", time_buf, getpid());
        fflush(stdout);

        pid_t pid = fork();
        if (pid < 0) {
            perror("fork failed");
            return 1;
        }

        if (pid == 0) {
            // Child process runs Python engine
            int code = run_child_python(argc, argv);
            exit(code);
        } else {
            // Parent supervisor monitors child
            int status = 0;
            waitpid(pid, &status, 0);

            time_t exit_now = time(NULL);
            char exit_time_buf[64];
            strftime(exit_time_buf, sizeof(exit_time_buf), "%Y-%m-%d %H:%M:%S", localtime(&exit_now));

            if (WIFEXITED(status)) {
                int exit_code = WEXITSTATUS(status);
                if (exit_code == RESTART_EXIT_CODE) {
                    printf("%s [INFO] [Supervisor] Seamless restart triggered (child PID %d)\n", exit_time_buf, pid);
                    fflush(stdout);
                    usleep(150000); // 150ms delay
                    continue;
                }
                printf("%s [INFO] [Supervisor] Gemini Assistant exited cleanly with code %d\n", exit_time_buf, exit_code);
                fflush(stdout);
                return exit_code;
            } else if (WIFSIGNALED(status)) {
                int sig = WTERMSIG(status);
                printf("%s [WARNING] [Supervisor] Gemini Assistant child PID %d terminated by signal %d\n", exit_time_buf, pid, sig);
                fflush(stdout);
                return 128 + sig;
            }
            return 0;
        }
    }
}
