// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <map>
#include <string>

std::string trim(const std::string& s);
// The flat {"key": value} objects written by slogmetaraw (plugin_cache, --to-resolve, --update-check).
std::map<std::string, std::string> parseFlatJson(const std::string& s);
