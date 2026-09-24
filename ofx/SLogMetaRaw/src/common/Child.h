// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <sys/types.h>

#include <atomic>
#include <chrono>
#include <string>
#include <vector>

// Copied on the calling thread: reading environ from a worker races with the host's setenv.
struct EnvSnapshot
{
    std::vector<std::string> vars;
    static EnvSnapshot capture();
};

struct Child
{
    pid_t pid = -1;
    int fd = -1;                 // read end of the child's stdout
    std::string out;             // first 64 KB of it
    bool exited = false;
    int exitCode = -1;           // -1 also when the host reaps children itself (ECHILD)
    int termSignal = 0;
    std::chrono::steady_clock::time_point started;
    int elapsedMs() const;
};

bool spawnProcess(const std::vector<std::string>& argv, const EnvSnapshot& env, Child& c, std::string& error,
                  const std::string& stderrPath = "");
// True once the child has exited (output fully drained); false on timeout or cancel.
bool waitProcess(Child& c, int timeoutMs, const std::atomic<bool>* cancel = nullptr);
// SIGKILL to the whole process group. Never blocks: an unreaped pid is collected by reapStrays().
void killProcess(Child& c);
void reapStrays();

struct ChildResult
{
    bool started = false, finished = false, timedOut = false;
    int exitCode = -1, termSignal = 0;
    std::string out, error;
};
ChildResult runProcess(const std::vector<std::string>& argv, const EnvSnapshot& env, int timeoutMs,
                       const std::atomic<bool>* cancel = nullptr, const std::string& stderrPath = "");

// The slogmetaraw package run by ResolvePython (or a system python3) in a child.
struct PythonCommand
{
    std::string python, lib;
};
bool findPython(PythonCommand& cmd, std::string& error);
std::vector<std::string> pythonArgv(const PythonCommand& cmd, const std::vector<std::string>& args);
std::string childLogPath();      // ~/Library/Logs/SLogMetaRaw/plugin-child.log
