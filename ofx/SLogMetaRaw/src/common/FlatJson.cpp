// SPDX-License-Identifier: GPL-3.0-or-later
#include "FlatJson.h"

#include <cstdlib>

std::string trim(const std::string& s)
{
    size_t a = s.find_first_not_of(" \t\r\n");
    size_t b = s.find_last_not_of(" \t\r\n");
    return a == std::string::npos ? "" : s.substr(a, b - a + 1);
}

static void appendUtf8(std::string& out, unsigned cp)
{
    if (cp >= 0xD800 && cp <= 0xDFFF) cp = 0xFFFD;
    if (cp < 0x80) out += (char)cp;
    else if (cp < 0x800) { out += (char)(0xC0 | (cp >> 6)); out += (char)(0x80 | (cp & 0x3F)); }
    else if (cp < 0x10000) { out += (char)(0xE0 | (cp >> 12)); out += (char)(0x80 | ((cp >> 6) & 0x3F)); out += (char)(0x80 | (cp & 0x3F)); }
    else { out += (char)(0xF0 | (cp >> 18)); out += (char)(0x80 | ((cp >> 12) & 0x3F)); out += (char)(0x80 | ((cp >> 6) & 0x3F)); out += (char)(0x80 | (cp & 0x3F)); }
}

std::map<std::string, std::string> parseFlatJson(const std::string& s)
{
    std::map<std::string, std::string> out;
    size_t i = 0, n = s.size();
    auto skip = [&]() { while (i < n && (s[i] == ' ' || s[i] == '\n' || s[i] == '\r' || s[i] == '\t' || s[i] == ',' || s[i] == '{' || s[i] == '}')) ++i; };
    auto readString = [&](std::string& v) -> bool {
        if (i >= n || s[i] != '"') return false;
        ++i;
        while (i < n && s[i] != '"') {
            if (s[i] == '\\' && i + 1 < n) {
                char e = s[++i];
                if (e == 'n') v += '\n';
                else if (e == 't') v += '\t';
                else if (e == 'u' && i + 4 < n) {
                    unsigned cp = (unsigned)strtoul(s.substr(i + 1, 4).c_str(), nullptr, 16);
                    i += 4;   // now on the last hex digit of this escape
                    if (cp >= 0xD800 && cp <= 0xDBFF && i + 6 < n && s[i + 1] == '\\' && s[i + 2] == 'u') {
                        unsigned lo = (unsigned)strtoul(s.substr(i + 3, 4).c_str(), nullptr, 16);
                        if (lo >= 0xDC00 && lo <= 0xDFFF) {
                            cp = 0x10000u + ((cp - 0xD800u) << 10) + (lo - 0xDC00u);
                            i += 6;
                        }
                    }
                    appendUtf8(v, cp);
                } else v += e;
                ++i;
            } else {
                v += s[i++];
            }
        }
        ++i;
        return true;
    };
    while (true) {
        skip();
        std::string key, val;
        if (!readString(key)) break;
        while (i < n && (s[i] == ' ' || s[i] == ':')) ++i;
        if (i < n && s[i] == '"') readString(val);
        else { size_t j = i; while (j < n && s[j] != ',' && s[j] != '}') ++j; val = trim(s.substr(i, j - i)); i = j; }
        out[key] = val;
    }
    return out;
}
