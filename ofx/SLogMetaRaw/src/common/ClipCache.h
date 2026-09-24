// SPDX-License-Identifier: GPL-3.0-or-later
// The per-clip record written by slogmetaraw/plugin_cache.py. Never starts a reader.
#pragma once
#include <map>
#include <string>

// Records older than this are read again: 5 fixed long MXF files, 6 the FX6 tint scale.
const int kRecordVersion = 6;

// False when there is no record, it is older than kRecordVersion, or it belongs to another file
// that used to live at that path.
bool readClipRecord(const std::string& clipPath, std::map<std::string, std::string>& record);
// Camera gamut and transfer codes of the record, both checked against the tables; false if unknown.
bool cameraEncoding(const std::map<std::string, std::string>& record, int& space, int& gamma);
