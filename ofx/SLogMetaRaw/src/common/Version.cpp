// SPDX-License-Identifier: GPL-3.0-or-later
#include "Version.h"

bool parseSemver(const std::string& text, int out[3])
{
    size_t i = (!text.empty() && (text[0] == 'v' || text[0] == 'V')) ? 1 : 0;
    for (int part = 0; part < 3; ++part) {
        if (part > 0) {
            if (i >= text.size() || text[i] != '.') return false;
            ++i;
        }
        const size_t start = i;
        long value = 0;
        while (i < text.size() && text[i] >= '0' && text[i] <= '9' && i - start < 9) value = value * 10 + (text[i++] - '0');
        if (i == start || (i < text.size() && text[i] >= '0' && text[i] <= '9')) return false;
        out[part] = (int)value;
    }
    return i == text.size();
}

bool isNewer(const std::string& current, const std::string& latest)
{
    int a[3], b[3];
    if (!parseSemver(current, a) || !parseSemver(latest, b)) return false;
    for (int i = 0; i < 3; ++i)
        if (a[i] != b[i]) return b[i] > a[i];
    return false;
}

bool isTrustedDmgUrl(const std::string& url)
{
    static const std::string prefix = "https://github.com/ivan-94m/SLogMetaRaw/releases/download/";
    if (url.size() >= 512 || url.compare(0, prefix.size(), prefix) != 0 || url.find("..") != std::string::npos)
        return false;
    for (char c : url)
        if (!((c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '.' || c == '_'
              || c == '/' || c == '+' || c == '-' || c == ':'))
            return false;
    if (url.find(':', prefix.size()) != std::string::npos) return false;
    const std::string tail = url.size() >= 4 ? url.substr(url.size() - 4) : "";
    return tail == ".dmg" || tail == ".DMG" || tail == ".Dmg";
}
