// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <string>

// Sizes of the gamut and transfer tables of DevelopMath.h: codes read from files are checked against them.
const int kSpaceCount = 11, kGammaCount = 11;
extern const char* const kSpaceNames[kSpaceCount];
extern const char* const kGammaNames[kGammaCount];
extern const char* const kLevelNames[2];          // index = data level code, shared with datalevel.py
// "Ingresso nodo" choice: 0 = automatic, then fixed (gamut, transfer) pairs.
const int kNodeInputCount = 6;
extern const int kNodeInputPairs[kNodeInputCount][2];
extern const char* const kNodeInputNames[kNodeInputCount];

// OFX native colourspace name -> codes of DevelopMath.h. False when the name is unknown.
bool mapColourspace(const std::string& cs, int& space, int& gamma);
