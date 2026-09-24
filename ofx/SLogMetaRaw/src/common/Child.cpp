// SPDX-License-Identifier: GPL-3.0-or-later
#include "Child.h"

#include "Files.h"
#include "FlatJson.h"

#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <signal.h>
#include <spawn.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>

#include <algorithm>
#include <cstring>
#include <mutex>

extern char** environ;

static const size_t kMaxOutput = 65536;

EnvSnapshot EnvSnapshot::capture()
{
    EnvSnapshot e;
    for (char** v = environ; v && *v; ++v)
        if (strncmp(*v, "PYTHONPATH=", 11) != 0 && strncmp(*v, "PYTHONHOME=", 11) != 0) e.vars.push_back(*v);
    return e;
}

int Child::elapsedMs() const
{
    return (int)std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now() - started).count();
}

bool spawnProcess(const std::vector<std::string>& argv, const EnvSnapshot& env, Child& c, std::string& error,
                  const std::string& stderrPath)
{
    int fds[2];
    if (pipe(fds) != 0) { error = "pipe non disponibile"; return false; }
    fcntl(fds[0], F_SETFD, FD_CLOEXEC);
    fcntl(fds[0], F_SETFL, fcntl(fds[0], F_GETFL) | O_NONBLOCK);

    posix_spawn_file_actions_t fa;
    posix_spawn_file_actions_init(&fa);
    posix_spawn_file_actions_addopen(&fa, 0, "/dev/null", O_RDONLY, 0);
    posix_spawn_file_actions_adddup2(&fa, fds[1], 1);
    std::string errPath = "/dev/null";
    if (!stderrPath.empty()) {   // an unopenable log would make the whole spawn fail
        int probe = open(stderrPath.c_str(), O_WRONLY | O_CREAT | O_APPEND | O_CLOEXEC, 0644);
        if (probe >= 0) { close(probe); errPath = stderrPath; }
    }
    posix_spawn_file_actions_addopen(&fa, 2, errPath.c_str(), O_WRONLY | O_CREAT | O_APPEND, 0644);
    posix_spawnattr_t at;
    posix_spawnattr_init(&at);
    // Only 0/1/2 reach the child; its own group, so a timeout also kills what it spawned.
    posix_spawnattr_setflags(&at, POSIX_SPAWN_CLOEXEC_DEFAULT | POSIX_SPAWN_SETPGROUP | POSIX_SPAWN_SETSIGMASK
                                      | POSIX_SPAWN_SETSIGDEF);
    posix_spawnattr_setpgroup(&at, 0);
    sigset_t none, defaults;
    sigemptyset(&none);
    sigemptyset(&defaults);
    sigaddset(&defaults, SIGPIPE);
    sigaddset(&defaults, SIGCHLD);
    sigaddset(&defaults, SIGTERM);
    posix_spawnattr_setsigmask(&at, &none);
    posix_spawnattr_setsigdefault(&at, &defaults);

    std::vector<char*> av, ev;
    for (const std::string& a : argv) av.push_back(const_cast<char*>(a.c_str()));
    av.push_back(nullptr);
    for (const std::string& e : env.vars) ev.push_back(const_cast<char*>(e.c_str()));
    ev.push_back(nullptr);

    pid_t pid = -1;
    int rc = posix_spawn(&pid, argv[0].c_str(), &fa, &at, av.data(), ev.data());
    posix_spawn_file_actions_destroy(&fa);
    posix_spawnattr_destroy(&at);
    close(fds[1]);
    if (rc != 0) {
        close(fds[0]);
        error = std::string("avvio non riuscito: ") + strerror(rc);
        return false;
    }
    c = Child();
    c.pid = pid;
    c.fd = fds[0];
    c.started = std::chrono::steady_clock::now();
    return true;
}

static void drain(Child& c)
{
    char buf[8192];
    while (c.fd >= 0) {
        ssize_t n = read(c.fd, buf, sizeof(buf));
        if (n > 0) {
            if (c.out.size() < kMaxOutput) c.out.append(buf, std::min((size_t)n, kMaxOutput - c.out.size()));
        } else if (n < 0 && (errno == EAGAIN || errno == EINTR)) {
            return;
        } else {                  // EOF or error
            close(c.fd);
            c.fd = -1;
        }
    }
}

static void checkExit(Child& c)
{
    if (c.exited || c.pid < 0) return;
    int status = 0;
    pid_t r = waitpid(c.pid, &status, WNOHANG);
    if (r == c.pid) {
        c.exited = true;
        if (WIFEXITED(status)) c.exitCode = WEXITSTATUS(status);
        if (WIFSIGNALED(status)) c.termSignal = WTERMSIG(status);
    } else if (r < 0 && errno == ECHILD) {
        c.exited = true;          // the host reaps children itself (SIGCHLD ignored)
    }
}

bool waitProcess(Child& c, int timeoutMs, const std::atomic<bool>* cancel)
{
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::milliseconds(std::max(timeoutMs, 0));
    while (true) {
        drain(c);
        checkExit(c);
        // Leave only on exit: EOF alone is not enough, a concurrent fork of the host can hold the pipe.
        if (c.exited) {
            drain(c);
            if (c.fd >= 0) { close(c.fd); c.fd = -1; }
            return true;
        }
        const int left = (int)std::chrono::duration_cast<std::chrono::milliseconds>(
            deadline - std::chrono::steady_clock::now()).count();
        if (left <= 0 || (cancel && cancel->load())) return false;
        const int slice = std::min(left, 50);
        if (c.fd >= 0) {
            struct pollfd p = { c.fd, POLLIN, 0 };
            poll(&p, 1, slice);
        } else {
            poll(nullptr, 0, std::min(slice, 10));
        }
    }
}

static std::mutex s_StrayMutex;
static std::vector<pid_t> s_Strays;

void reapStrays()
{
    std::lock_guard<std::mutex> lock(s_StrayMutex);
    s_Strays.erase(std::remove_if(s_Strays.begin(), s_Strays.end(), [](pid_t p) {
        pid_t r = waitpid(p, nullptr, WNOHANG);
        return r == p || (r < 0 && errno == ECHILD);
    }), s_Strays.end());
}

void killProcess(Child& c)
{
    if (c.pid > 0 && !c.exited) {
        kill(-c.pid, SIGKILL);
        kill(c.pid, SIGKILL);
        checkExit(c);
        if (!c.exited) {
            std::lock_guard<std::mutex> lock(s_StrayMutex);
            s_Strays.push_back(c.pid);
        }
        c.exited = true;
    }
    if (c.fd >= 0) { close(c.fd); c.fd = -1; }
    reapStrays();
}

ChildResult runProcess(const std::vector<std::string>& argv, const EnvSnapshot& env, int timeoutMs,
                       const std::atomic<bool>* cancel, const std::string& stderrPath)
{
    ChildResult r;
    Child c;
    if (!spawnProcess(argv, env, c, r.error, stderrPath)) return r;
    r.started = true;
    if (waitProcess(c, timeoutMs, cancel)) {
        r.finished = true;
        r.exitCode = c.exitCode;
        r.termSignal = c.termSignal;
    } else {
        r.timedOut = true;
        killProcess(c);
    }
    r.out = c.out;
    return r;
}

// ResolvePython runs in isolated mode (its ._pth): PYTHONPATH and cwd are ignored, so the library
// path travels as an argument, never inside the Python source.
static const char* kBootstrap = "import runpy, sys; sys.path.insert(0, sys.argv.pop(1)); "
                                "runpy.run_module('slogmetaraw', run_name='__main__')";

bool findPython(PythonCommand& cmd, std::string& error)
{
    struct stat st;
    std::string lib;
    if (readFile(supportDir() + "/lib_path", lib)) lib = trim(lib);
    if (lib.empty() && stat((supportDir() + "/lib/slogmetaraw").c_str(), &st) == 0) lib = supportDir() + "/lib";
    if (lib.empty()) lib = "/Library/Application Support/SLogMetaRaw/lib";
    static const char* candidates[] = {
        "/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Applications/ResolvePython",
        "/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Resources/ResolvePython/ResolvePython",
        "/usr/bin/python3", "/opt/homebrew/bin/python3", "/usr/local/bin/python3" };
    for (const char* c : candidates) {
        if (access(c, X_OK) == 0) {
            cmd.python = c;
            cmd.lib = lib;
            return true;
        }
    }
    error = "Python non trovato";
    return false;
}

std::vector<std::string> pythonArgv(const PythonCommand& cmd, const std::vector<std::string>& args)
{
    std::vector<std::string> a = { cmd.python, "-X", "pycache_prefix=" + supportDir() + "/pycache",
                                   "-c", kBootstrap, cmd.lib };
    a.insert(a.end(), args.begin(), args.end());
    return a;
}

std::string childLogPath()
{
    const std::string dir = homeDir() + "/Library/Logs/SLogMetaRaw";
    return makeDirs(dir) ? dir + "/plugin-child.log" : "";
}
