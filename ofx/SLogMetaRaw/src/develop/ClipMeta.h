// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <map>
#include <string>

struct ClipMeta
{
    bool ok = false;
    bool supported = false;
    bool wbEstimated = false;
    double shotTemp = 5600.0, shotTint = 0.0, shotEI = 800.0;
    int camSpace = -1, camGamma = -1;
    int levelRequired = -1;   // scale the capture gamma needs: -1 unknown, 0 video, 1 full
    int levelHost = -1;       // scale Resolve decoded the clip on ('Auto' -> -1)
    std::string colorSpace;
    std::map<std::string, std::string> fields;   // the whole record, for the read-only fields
    std::string resolveNote;                     // outcome of the Media Pool write on "Rileggi"
};

// Read-only fields: JSON key -> parameter name -> label. Parameter names are permanent.
struct DetailField { const char* key; const char* param; const char* label; };
extern const DetailField kDetails[];
extern const int kDetailCount;

bool parseClipRecord(const std::map<std::string, std::string>& record, ClipMeta& m);

enum class MetaOutcome { Found, Pending, Missing };
enum class MetaMode { CacheOnly, Read, Reload };
// CacheOnly never starts a child (instance creation). Read starts or polls a background reader and
// waits at most kSyncWaitMs on the UI thread; Reload re-reads the file and writes into Resolve.
MetaOutcome acquireMeta(const std::string& clipPath, MetaMode mode, ClipMeta& m, std::string& status);
