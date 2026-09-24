// SPDX-License-Identifier: GPL-3.0-or-later
#include "ClipCache.h"

#include <sys/stat.h>

#include <cstdlib>

#include "ColourSpaces.h"
#include "Files.h"
#include "FlatJson.h"

static bool recordMatchesFile(const std::map<std::string, std::string>& j, const std::string& path)
{
    auto num = [&](const char* k) { auto it = j.find(k); return it == j.end() ? 0LL : atoll(it->second.c_str()); };
    const long long size = num("file_size"), mtime = num("file_mtime_ns");
    if (size == 0 && mtime == 0) return true;   // records of synthetic test inputs
    struct stat st;
    if (stat(path.c_str(), &st) != 0) return false;
    const long long ns = (long long)st.st_mtimespec.tv_sec * 1000000000LL + st.st_mtimespec.tv_nsec;
    return (long long)st.st_size == size && ns == mtime;
}

bool readClipRecord(const std::string& clipPath, std::map<std::string, std::string>& record)
{
    std::string text;
    if (!readFile(cacheRecordPath(clipPath), text)) return false;
    record = parseFlatJson(text);
    auto v = record.find("version");
    if (v == record.end() || atoi(v->second.c_str()) < kRecordVersion) return false;
    return recordMatchesFile(record, canonicalPath(clipPath));
}

bool cameraEncoding(const std::map<std::string, std::string>& record, int& space, int& gamma)
{
    auto s = record.find("cam_space"), g = record.find("cam_gamma");
    if (s == record.end() || g == record.end()) return false;
    space = atoi(s->second.c_str());
    gamma = atoi(g->second.c_str());
    return space >= 0 && space < kSpaceCount && gamma >= 0 && gamma < kGammaCount;
}
