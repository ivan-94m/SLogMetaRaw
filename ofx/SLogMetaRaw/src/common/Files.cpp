// SPDX-License-Identifier: GPL-3.0-or-later
#include "Files.h"

#include <CoreFoundation/CoreFoundation.h>
#include <limits.h>
#include <sys/stat.h>

#include <cerrno>

#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <sstream>
#include <vector>

std::string homeDir()
{
    const char* h = getenv("HOME");
    return h ? h : "";
}

std::string supportDir() { return homeDir() + "/Library/Application Support/SLogMetaRaw"; }

bool readFile(const std::string& path, std::string& out)
{
    std::ifstream f(path, std::ios::binary);
    if (!f) return false;
    std::stringstream ss;
    ss << f.rdbuf();
    out = ss.str();
    return true;
}

// Hosts hand out NFD or NFC spellings of the same path; the cache key must not depend on it.
std::string normalizeNFC(const std::string& s)
{
    if (s.empty()) return s;
    CFStringRef cf = CFStringCreateWithCString(kCFAllocatorDefault, s.c_str(), kCFStringEncodingUTF8);
    if (!cf) return s;
    CFMutableStringRef norm = CFStringCreateMutableCopy(kCFAllocatorDefault, 0, cf);
    CFRelease(cf);
    if (!norm) return s;
    CFStringNormalize(norm, kCFStringNormalizationFormC);
    CFIndex max = CFStringGetMaximumSizeForEncoding(CFStringGetLength(norm), kCFStringEncodingUTF8) + 1;
    std::vector<char> buf(max);
    std::string out = CFStringGetCString(norm, buf.data(), max, kCFStringEncodingUTF8) ? buf.data() : s;
    CFRelease(norm);
    return out;
}

// Resolve may hand over a symlinked path while the script records the physical one.
std::string canonicalPath(const std::string& path)
{
    char buf[PATH_MAX];
    return normalizeNFC(realpath(path.c_str(), buf) ? std::string(buf) : path);
}

std::string fnv1a64(const std::string& text)
{
    unsigned long long h = 0xcbf29ce484222325ULL;
    for (unsigned char c : text) {
        h ^= c;
        h *= 0x100000001b3ULL;
    }
    char buf[17];
    snprintf(buf, sizeof(buf), "%016llx", h);
    return buf;
}

std::string cacheRecordPath(const std::string& clipPath)
{
    return supportDir() + "/cache/" + fnv1a64(canonicalPath(clipPath)) + ".json";
}

// A cloud placeholder (SF_DATALESS) downloads when read: minutes of frozen UI and gigabytes.
bool clipIsReadable(const std::string& path, std::string& why)
{
    struct stat st;
    if (stat(path.c_str(), &st) != 0) { why = "file non trovato"; return false; }
    if (st.st_flags & 0x40000000 /* SF_DATALESS */) { why = "il file non e in locale (non scaricato)"; return false; }
    return true;
}

bool makeDirs(const std::string& path)
{
    for (size_t i = 1; i <= path.size(); ++i) {
        if (i == path.size() || path[i] == '/') {
            const std::string part = path.substr(0, i);
            if (mkdir(part.c_str(), 0755) != 0 && errno != EEXIST) return false;
        }
    }
    return true;
}
