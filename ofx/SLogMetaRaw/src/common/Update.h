// SPDX-License-Identifier: GPL-3.0-or-later
// Release check shared by every instance of both plugins. A detached worker runs
// `slogmetaraw --update-check`; labels are applied on the UI thread only (UpdateBadge).
#pragma once
#include <string>

namespace Update {

enum Kind { Idle, Disabled, Checking, Current, Available, Installed, Failed };

struct Snapshot
{
    Kind kind = Idle;
    std::string latest, url, title, error;
    bool manual = false;      // the last check came from a click
    bool opened = false;      // the installer was handed to the browser
    unsigned serial = 0;      // bumps on every change
};

const char* release();
// UI thread. Automatic starts honour the opt-outs; a click (manual) is explicit consent.
void start(bool manual, bool hostIsBackground);
Snapshot snapshot();
// Waits up to ms for the check started by a click; true when it finished.
bool waitManual(int ms);
bool openInstaller(std::string& error);
void shutdown();

}
