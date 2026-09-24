// SPDX-License-Identifier: GPL-3.0-or-later
#include "ClipMeta.h"

#include "../common/Child.h"
#include "../common/ClipCache.h"
#include "../common/ColourSpaces.h"
#include "../common/Files.h"
#include "../common/FlatJson.h"

#include <unistd.h>

#include <cctype>
#include <cstdlib>
#include <mutex>

const DetailField kDetails[] = {
    { "lens", "infoLens", "Obiettivo" }, { "focal", "infoFocal", "Focale" },
    { "iris", "infoIris", "Diaframma" }, { "focus", "infoFocus", "Fuoco" },
    { "shutter", "infoShutter", "Shutter" }, { "exposure", "infoExposure", "ISO / EI" },
    { "white_balance", "infoWhiteBalance", "Bilanciamento" }, { "color", "infoColor", "Colore" },
    { "fps", "infoFps", "Frame rate" }, { "nd_stab", "infoNdStab", "ND / Stabilizzatore" },
    { "lut", "infoLut", "LUT camera" }, { "file", "infoFile", "File" } };
const int kDetailCount = sizeof(kDetails) / sizeof(kDetails[0]);

// On the UI thread: past these the reader keeps going and the panel shows it is still reading.
const int kSyncWaitMs = 500;
const int kReloadWaitMs = 2000;
static const int kReadLimitMs = 18000;    // the reader stops itself at 15 s (--deadline)
static const int kRetryAfterMs = 60000;   // a failed clip is tried again after a minute, not on every click

bool parseClipRecord(const std::map<std::string, std::string>& record, ClipMeta& m)
{
    std::map<std::string, std::string> j = record;
    auto num = [&](const char* k, int def) { return j.count(k) ? atoi(j[k].c_str()) : def; };
    m.ok = true;
    m.supported = num("supported", 0) != 0;
    m.wbEstimated = num("wb_estimated", 0) != 0;
    m.shotTemp = atof(j["shot_temp"].c_str());
    m.shotTint = atof(j["shot_tint"].c_str());
    m.shotEI = atof(j["shot_ei"].c_str());
    // the record is a file on disk: a stale or hand-edited one must not index a table
    m.camSpace = num("cam_space", -1);
    m.camGamma = num("cam_gamma", -1);
    m.levelRequired = num("level_required", -1);
    m.levelHost = num("level_host", -1);
    if (m.camSpace < 0 || m.camSpace >= kSpaceCount) m.camSpace = -1;
    if (m.camGamma < 0 || m.camGamma >= kGammaCount) m.camGamma = -1;
    if (m.levelRequired < 0 || m.levelRequired > 1) m.levelRequired = -1;
    if (m.levelHost < 0 || m.levelHost > 1) m.levelHost = -1;
    m.colorSpace = j["color_space"];
    m.fields = j;
    if (!(m.shotTint >= -100.0 && m.shotTint <= 100.0)) m.shotTint = m.shotTint < -100.0 ? -100.0 : (m.shotTint > 100.0 ? 100.0 : 0.0);
    if (m.shotTemp <= 0.0) m.shotTemp = 5600.0;
    if (m.shotEI <= 0.0) m.shotEI = 800.0;
    return true;
}

static bool readRecord(const std::string& path, ClipMeta& m)
{
    std::map<std::string, std::string> record;
    return readClipRecord(path, record) && parseClipRecord(record, m);
}

// Only Sony XAVC files carry the metadata: anything else must not start Python at all.
static bool isSonyContainer(const std::string& path)
{
    const size_t dot = path.find_last_of('.');
    std::string ext = dot == std::string::npos ? "" : path.substr(dot + 1);
    for (char& c : ext) c = (char)tolower((unsigned char)c);
    return ext == "mp4" || ext == "mxf";
}

// The outcome of the Media Pool write, left by the detached writer of "Rileggi".
static std::string takeResolveNote(const std::string& path)
{
    const std::string file = cacheRecordPath(path).substr(0, cacheRecordPath(path).size() - 5) + ".resolve.json";
    std::string text;
    if (!readFile(file, text)) return "";
    unlink(file.c_str());
    std::map<std::string, std::string> r = parseFlatJson(text);
    if (atoi(r["ok"].c_str()) != 1)
        return "scrittura in Resolve non riuscita: " + (r["error"].empty() ? std::string("sconosciuto") : r["error"]);
    std::string note = "scritti in Resolve su questa clip (" + r["written"] + " campi"
                     + (atoi(r["failed"].c_str()) > 0 ? ", " + r["failed"] + " rifiutati" : "") + ")";
    if (!r["level_host"].empty()) note += " · Data Level della clip: " + r["level_host"];
    return note;
}

namespace {
struct Read
{
    Child child;
    bool running = false, reload = false;
    std::chrono::steady_clock::time_point failedAt;
    std::string failure;
};
std::mutex s_Mutex;
std::map<std::string, Read> s_Reads;
}

// A finished reader: the record decides. The old --to-resolve answer ({"ok":..}) is still accepted.
static MetaOutcome settle(const std::string& path, Read& r, ClipMeta& m, std::string& status)
{
    r.running = false;
    const std::map<std::string, std::string> out = parseFlatJson(r.child.out);
    if (readRecord(path, m)) {
        if (out.count("ok")) {
            std::map<std::string, std::string> j = out;
            m.resolveNote = atoi(j["ok"].c_str()) == 1
                ? "scritti in Resolve su questa clip (" + j["written"] + " campi)"
                : "scrittura in Resolve non riuscita: " + j["error"];
        }
        status = r.reload ? "Metadata letti dal file"
                          : "Metadata letti dal file: lancia lo script S-Log MetaRaw per registrarli in Resolve";
        r.failure.clear();
        return MetaOutcome::Found;
    }
    auto it = out.find("error");
    r.failure = it != out.end() && !it->second.empty() ? it->second : "clip non Sony?";
    r.failedAt = std::chrono::steady_clock::now();
    status = "Metadata non disponibili: " + r.failure;
    return MetaOutcome::Missing;
}

MetaOutcome acquireMeta(const std::string& path, MetaMode mode, ClipMeta& m, std::string& status)
{
    reapStrays();
    if (mode != MetaMode::Reload && readRecord(path, m)) {
        m.resolveNote = takeResolveNote(path);
        status = "Metadata letti (registrati da S-Log MetaRaw)";
        return MetaOutcome::Found;
    }
    if (mode == MetaMode::CacheOnly) {
        status = "Metadata non ancora letti: apri il pannello del nodo";
        return MetaOutcome::Missing;
    }
    if (!isSonyContainer(path)) {
        status = "Formato non Sony (" + path.substr(path.find_last_of('/') + 1) + "): nessun metadata di camera";
        return MetaOutcome::Missing;
    }
    std::string why;
    if (!clipIsReadable(path, why)) {
        status = "Metadata non letti: " + why;
        return MetaOutcome::Missing;
    }

    std::lock_guard<std::mutex> lock(s_Mutex);
    Read& r = s_Reads[path];
    if (r.running) {
        if (waitProcess(r.child, mode == MetaMode::Reload ? kReloadWaitMs : 0)) return settle(path, r, m, status);
        if (r.child.elapsedMs() < kReadLimitMs) {
            status = "Lettura metadata in corso… riapri il pannello tra poco";
            return MetaOutcome::Pending;
        }
        killProcess(r.child);
        r.running = false;
        r.failure = "metadata non letti entro 15 s (disco lento o in stand-by)";
        r.failedAt = std::chrono::steady_clock::now();
    }
    if (mode == MetaMode::Read && !r.failure.empty()
        && std::chrono::steady_clock::now() - r.failedAt < std::chrono::milliseconds(kRetryAfterMs)) {
        status = "Metadata non disponibili: " + r.failure + " · Rileggi metadata o Avanzate › Sblocca controlli";
        return MetaOutcome::Missing;
    }

    PythonCommand py;
    if (!findPython(py, why)) {
        status = "Metadata non disponibili: " + why;
        return MetaOutcome::Missing;
    }
    const std::vector<std::string> args = mode == MetaMode::Reload
        ? std::vector<std::string>{ "--to-resolve", path }
        : std::vector<std::string>{ "--cache", path, "--max-samples", "8", "--deadline", "15" };
    r = Read();
    r.reload = (mode == MetaMode::Reload);
    if (!spawnProcess(pythonArgv(py, args), EnvSnapshot::capture(), r.child, why, childLogPath())) {
        status = "Metadata non disponibili: " + why;
        return MetaOutcome::Missing;
    }
    r.running = true;
    if (waitProcess(r.child, mode == MetaMode::Reload ? kReloadWaitMs : kSyncWaitMs)) return settle(path, r, m, status);
    status = mode == MetaMode::Reload ? "Lettura lenta: i valori arrivano da soli, riapri il pannello"
                                      : "Lettura metadata in corso… riapri il pannello tra poco";
    return MetaOutcome::Pending;
}
