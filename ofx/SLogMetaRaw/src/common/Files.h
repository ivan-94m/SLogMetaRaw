// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <string>

std::string homeDir();
std::string supportDir();                        // ~/Library/Application Support/SLogMetaRaw
bool readFile(const std::string& path, std::string& out);
std::string normalizeNFC(const std::string& s);
std::string canonicalPath(const std::string& path);   // realpath + NFC, as plugin_cache.canonical_path
std::string fnv1a64(const std::string& text);
std::string cacheRecordPath(const std::string& clipPath);
bool clipIsReadable(const std::string& path, std::string& why);
bool makeDirs(const std::string& path);   // mkdir -p
