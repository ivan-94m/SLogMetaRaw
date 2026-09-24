// SPDX-License-Identifier: GPL-3.0-or-later
#include "Update.h"

#include <atomic>
#include <condition_variable>
#include <cstdio>
#include <cstdlib>
#include <mutex>
#include <thread>
#include <unistd.h>

#include "Child.h"
#include "Files.h"
#include "FlatJson.h"
#include "Version.h"

#ifndef SLOGMETARAW_RELEASE
#error "SLOGMETARAW_RELEASE comes from slogmetaraw/__init__.py through the Makefile"
#endif

namespace Update {

static const int kCheckMs = 40000;   // urlopen's timeout does not bound DNS: ~30 s on a dead name

// Never destroyed: a detached worker may still hold it when the host unloads the bundle.
struct State
{
    std::mutex mutex;
    std::condition_variable done;
    Snapshot snap;
    bool running = false;
    std::atomic<bool> cancel{ false };
};
static State& state()
{
    static State* s = new State();
    return *s;
}

const char* release() { return SLOGMETARAW_RELEASE; }

static bool optedOut()
{
    if (getenv("SLOGMETARAW_NO_UPDATE_CHECK")) return true;
    return access((supportDir() + "/no_update_check").c_str(), F_OK) == 0;
}

static void finish(const ChildResult& r)
{
    const std::map<std::string, std::string> j = parseFlatJson(r.out);
    auto get = [&](const char* k) { auto it = j.find(k); return it == j.end() ? std::string() : it->second; };
    State& s = state();
    std::lock_guard<std::mutex> lock(s.mutex);
    Snapshot& n = s.snap;
    n.latest = get("latest");
    n.url = get("dmg_url");
    n.title = get("title");
    n.error = get("error");
    // The decision is taken here, not from the JSON's "newer": update.json is shared with the script,
    // which may have written it for another installed version.
    if (!r.finished || j.empty()) {
        n.kind = Failed;
        if (n.error.empty()) n.error = r.timedOut ? "GitHub non ha risposto in tempo" : "controllo non riuscito";
    } else if (isNewer(release(), n.latest) && isTrustedDmgUrl(n.url)) {
        // the installer already ran but Resolve still has the old binary loaded
        const std::string lib = get("lib_version");
        int v[3];
        n.kind = (parseSemver(lib, v) && !isNewer(lib, n.latest)) ? Installed : Available;
    } else {
        n.kind = n.error.empty() ? Current : Failed;
    }
    ++n.serial;
    s.running = false;
    s.done.notify_all();
}

void start(bool manual, bool hostIsBackground)
{
    State& s = state();
    {
        std::lock_guard<std::mutex> lock(s.mutex);
        if (s.running) {
            if (manual) s.snap.manual = true;
            return;
        }
        if (!manual && (s.snap.kind != Idle || hostIsBackground || optedOut())) {
            if (s.snap.kind == Idle) { s.snap.kind = Disabled; ++s.snap.serial; }
            return;
        }
        s.running = true;
        s.cancel = false;
        s.snap.kind = Checking;
        s.snap.manual = manual;
        ++s.snap.serial;
    }
    PythonCommand py;
    std::string error;
    if (!findPython(py, error)) {
        ChildResult r;
        finish(r);
        return;
    }
    std::vector<std::string> args = { "--update-check", "--current", release() };
    if (manual) args.push_back("--force");
    const std::vector<std::string> argv = pythonArgv(py, args);
    const EnvSnapshot env = EnvSnapshot::capture();   // on the UI thread: environ races with the host
    const std::string log = childLogPath();
    std::thread([argv, env, log]() {
        ChildResult r = runProcess(argv, env, kCheckMs, &state().cancel, log);
        finish(r);
    }).detach();
}

Snapshot snapshot()
{
    State& s = state();
    std::lock_guard<std::mutex> lock(s.mutex);
    return s.snap;
}

bool waitManual(int ms)
{
    State& s = state();
    std::unique_lock<std::mutex> lock(s.mutex);
    return s.done.wait_for(lock, std::chrono::milliseconds(ms), [&] { return !s.running; });
}

bool openInstaller(std::string& error)
{
    const Snapshot n = snapshot();
    if (n.kind != Available || !isTrustedDmgUrl(n.url)) {
        error = "nessun installer da aprire";
        return false;
    }
    if (getenv("SLOGMETARAW_TEST_NO_OPEN")) {
        fprintf(stderr, "[open] %s\n", n.url.c_str());
    } else {
        ChildResult r = runProcess({ "/usr/bin/open", "-u", n.url }, EnvSnapshot::capture(), 3000);
        if (!r.finished || r.exitCode != 0) {
            error = "il browser non si e aperto";
            return false;
        }
    }
    State& s = state();
    std::lock_guard<std::mutex> lock(s.mutex);
    s.snap.opened = true;
    ++s.snap.serial;
    return true;
}

void shutdown()
{
    State& s = state();
    s.cancel = true;
}

}
