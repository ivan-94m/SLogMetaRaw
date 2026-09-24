// SPDX-License-Identifier: GPL-3.0-or-later
// S-Log MetaRaw - Copyright (C) 2026 Ivan Mazzone
// Free software under the GNU General Public License v3 or later; no warranty.
// See the LICENSE file or https://www.gnu.org/licenses/gpl-3.0.html
// S-Log MetaRaw - Camera Raw style controls for Sony clips that Resolve does not
// decode as raw (XAVC S / S-I / HS MP4). When applied, the node reads the clip's
// camera metadata (written by the S-Log MetaRaw script) and sets itself to the
// as-shot ISO/EI, white balance, tint and colour space.

#include "SLogMetaRaw.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <map>
#include <memory>
#include <set>
#include <sstream>
#include <string>
#include <vector>

#include <CoreFoundation/CoreFoundation.h>

#include <fcntl.h>

#include <signal.h>
#include <spawn.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>

#include "ofxsImageEffect.h"
#include "ofxsMultiThread.h"
#include "ofxsProcessing.h"
#include "ofxsLog.h"
#include "ofxImageEffectExt.h"
#include "ofxColour.h"

#include "DevelopMath.h"

extern char** environ;

#define kPluginName "S-Log MetaRaw"
#define kPluginGrouping "S-Log MetaRaw"
#define kPluginDescription "Controlli Camera Raw (Sony Video) per clip Sony MP4: si imposta da solo con i metadata di camera registrati da S-Log MetaRaw. Ivan Mazzone + Claude (@Ivan_94m)."
#define kPluginIcon "com.slogmetaraw.SLogMetaRaw.png"
#define kPluginIdentifier "com.slogmetaraw.SLogMetaRaw"
#define kPluginVersionMajor 1
#define kPluginVersionMinor 3

#define kOfxNativeConfig "ofx-native-v1.5_aces-v1.3_ocio-v2.3"

static const int kSettingsVersion = 4;   // bump when the meaning of a saved parameter changes
static const double kToneScale = 100.0;  // panel units per unit of DevelopParams
// data level codes, shared with slogmetaraw/datalevel.py: index = code
static const char* kLevelNames[] = { "Video (64-940)", "Full (0-1023)" };
// sizes of the gamut and transfer tables of DevelopMath.h (kSpaceNames / kGammaNames):
// every code read from the cache file is checked against them before it indexes one
static const int kSpaceCount = 11, kGammaCount = 11;
static const int kWBCustom = 7;
static const double kPresetKelvin[] = { 0.0, 5600.0, 6500.0, 7500.0, 3200.0, 4000.0, 5500.0 };  // index = WB choice

// ============================================================================ metadata bridge

static std::string homeDir()
{
    const char* h = getenv("HOME");
    return h ? h : "";
}

static std::string supportDir() { return homeDir() + "/Library/Application Support/SLogMetaRaw"; }

static std::string fnv1a64(const std::string& text)
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

// Normalise a path to NFC so the cache-key hash matches the one the Python
// script computes (macOS filesystems and hosts can hand out NFD or NFC strings).
static std::string normalizeNFC(const std::string& s)
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
    if (CFStringGetCString(norm, buf.data(), max, kCFStringEncodingUTF8)) {
        CFRelease(norm);
        return std::string(buf.data());
    }
    CFRelease(norm);
    return s;
}

static bool readFile(const std::string& path, std::string& out)
{
    std::ifstream f(path, std::ios::binary);
    if (!f) return false;
    std::stringstream ss;
    ss << f.rdbuf();
    out = ss.str();
    return true;
}

static std::string trim(const std::string& s)
{
    size_t a = s.find_first_not_of(" \t\r\n");
    size_t b = s.find_last_not_of(" \t\r\n");
    return a == std::string::npos ? "" : s.substr(a, b - a + 1);
}

static void appendUtf8(std::string& out, unsigned cp)
{
    if (cp >= 0xD800 && cp <= 0xDFFF) cp = 0xFFFD;  // lone surrogate -> replacement char
    if (cp < 0x80) out += (char)cp;
    else if (cp < 0x800) { out += (char)(0xC0 | (cp >> 6)); out += (char)(0x80 | (cp & 0x3F)); }
    else if (cp < 0x10000) { out += (char)(0xE0 | (cp >> 12)); out += (char)(0x80 | ((cp >> 6) & 0x3F)); out += (char)(0x80 | (cp & 0x3F)); }
    else { out += (char)(0xF0 | (cp >> 18)); out += (char)(0x80 | ((cp >> 12) & 0x3F)); out += (char)(0x80 | ((cp >> 6) & 0x3F)); out += (char)(0x80 | (cp & 0x3F)); }
}

// Minimal parser for the flat JSON objects written by slogmetaraw/plugin_cache.py.
static std::map<std::string, std::string> parseFlatJson(const std::string& s)
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
                    i += 4;  // i now points at the last hex digit of this escape
                    // combine a surrogate pair (\uD83D\uDE00) into one code point
                    if (cp >= 0xD800 && cp <= 0xDBFF && i + 6 < n && s[i + 1] == '\\' && s[i + 2] == 'u') {
                        unsigned lo = (unsigned)strtoul(s.substr(i + 3, 4).c_str(), nullptr, 16);
                        if (lo >= 0xDC00 && lo <= 0xDFFF) {
                            cp = 0x10000u + ((cp - 0xD800u) << 10) + (lo - 0xDC00u);
                            i += 6;
                        }
                    }
                    appendUtf8(v, cp);
                }
                else v += e;
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

// Shared bootstrap for the Python children: find a Python executable (the one
// bundled with Resolve first), the SLogMetaRaw library folder and a clean
// environment. Isolated mode ignores PYTHONPATH/PYTHONHOME anyway; dropping them
// avoids surprises on developer machines.
static bool preparePython(std::string& python, std::string& lib,
                          std::vector<std::string>& envStore, std::vector<char*>& envp,
                          std::string& error)
{
    // library location: developer install (lib_path), per-user copy, or the installer's system copy
    struct stat st;
    if (readFile(supportDir() + "/lib_path", lib)) lib = trim(lib);
    if (lib.empty() && stat((supportDir() + "/lib/slogmetaraw").c_str(), &st) == 0) lib = supportDir() + "/lib";
    if (lib.empty()) lib = "/Library/Application Support/SLogMetaRaw/lib";
    const char* candidates[] = {
        "/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Applications/ResolvePython",
        "/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Resources/ResolvePython/ResolvePython",
        "/usr/bin/python3", "/opt/homebrew/bin/python3", "/usr/local/bin/python3" };
    for (const char* c : candidates) {
        if (access(c, X_OK) == 0) { python = c; break; }
    }
    if (python.empty()) { error = "Python non trovato"; return false; }

    envStore.clear();
    for (char** e = environ; e && *e; ++e)
        if (strncmp(*e, "PYTHONPATH=", 11) != 0 && strncmp(*e, "PYTHONHOME=", 11) != 0) envStore.push_back(*e);
    envp.clear();
    for (auto& e : envStore) envp.push_back(const_cast<char*>(e.c_str()));
    envp.push_back(nullptr);
    return true;
}

// ResolvePython._pth enables isolated mode: PYTHONPATH and cwd are ignored.
// Pass paths as arguments, never as Python source, so spaces/quotes are safe.
static const char* kPythonBootstrap = "import runpy, sys; sys.path.insert(0, sys.argv.pop(1)); "
                                      "runpy.run_module('slogmetaraw', run_name='__main__')";

// Run slogmetaraw --cache in a Python child (pure file reading, no Resolve API calls).
static bool runExtractor(const std::string& clipPath, std::string& error)
{
    std::string python, lib;
    std::vector<std::string> envStore;
    std::vector<char*> envp;
    if (!preparePython(python, lib, envStore, envp, error)) return false;

    const char* argv[] = { python.c_str(), "-c", kPythonBootstrap, lib.c_str(), "--cache", clipPath.c_str(), nullptr };
    posix_spawn_file_actions_t fa;
    posix_spawn_file_actions_init(&fa);
    posix_spawn_file_actions_addopen(&fa, 1, "/dev/null", O_WRONLY, 0);
    posix_spawn_file_actions_addopen(&fa, 2, "/dev/null", O_WRONLY, 0);
    pid_t pid;
    int rc = posix_spawn(&pid, python.c_str(), &fa, nullptr, const_cast<char* const*>(argv), envp.data());
    posix_spawn_file_actions_destroy(&fa);
    if (rc != 0) { error = "avvio lettura metadata fallito"; return false; }
    for (int waited = 0; waited < 160; ++waited) {  // up to 8 s: this runs on the UI thread
        int status = 0;
        pid_t r = waitpid(pid, &status, WNOHANG);
        if (r == pid) {
            if (WIFEXITED(status) && WEXITSTATUS(status) == 0) return true;
            error = "lettura metadata non riuscita (file non Sony?)";
            return false;
        }
        usleep(50000);
    }
    kill(pid, SIGKILL);
    waitpid(pid, nullptr, 0);
    error = "lettura metadata troppo lenta (disco lento o file su unita di rete?)";
    return false;
}

// "Rileggi metadata" pressed on the node: one child that reads the clip, refreshes
// the plugin cache record and writes the metadata into the Resolve Media Pool,
// like the script's "Scrivi in Resolve" but for this single clip. The child prints
// one flat JSON line on stdout; the watchdog is longer because connecting to
// Resolve's scripting server adds a few seconds.
static bool runResolverWriter(const std::string& clipPath, std::string& error,
                              std::map<std::string, std::string>& result)
{
    std::string python, lib;
    std::vector<std::string> envStore;
    std::vector<char*> envp;
    if (!preparePython(python, lib, envStore, envp, error)) return false;

    const char* argv[] = { python.c_str(), "-c", kPythonBootstrap, lib.c_str(), "--to-resolve", clipPath.c_str(), nullptr };
    int pipefd[2];
    if (pipe(pipefd) != 0) { error = "pipe non disponibile"; return false; }
    posix_spawn_file_actions_t fa;
    posix_spawn_file_actions_init(&fa);
    posix_spawn_file_actions_adddup2(&fa, pipefd[1], 1);   // capture the JSON result
    posix_spawn_file_actions_addopen(&fa, 2, "/dev/null", O_WRONLY, 0);
    pid_t pid;
    int rc = posix_spawn(&pid, python.c_str(), &fa, nullptr, const_cast<char* const*>(argv), envp.data());
    close(pipefd[1]);   // the child has its own copy; the parent only reads
    posix_spawn_file_actions_destroy(&fa);
    if (rc != 0) { close(pipefd[0]); error = "avvio scrittura metadata fallito"; return false; }

    bool exited = false;
    int status = 0;
    for (int waited = 0; waited < 400; ++waited) {  // up to 20 s: this runs on the UI thread
        pid_t r = waitpid(pid, &status, WNOHANG);
        if (r == pid) { exited = true; break; }
        usleep(50000);
    }
    std::string out;
    if (exited) {
        char buf[4096];
        ssize_t n;
        while ((n = read(pipefd[0], buf, sizeof(buf))) > 0) {
            out.append(buf, n);
            if (out.size() > 65536) break;   // never trust the child's output size
        }
    }
    close(pipefd[0]);
    if (!exited) {
        kill(pid, SIGKILL);
        waitpid(pid, nullptr, 0);
        error = "scrittura metadata troppo lenta (Resolve non raggiungibile?)";
        return false;
    }
    result = parseFlatJson(out);
    if (result.empty() || !result.count("ok")) {
        error = "risposta del lettore non valida (file non Sony?)";
        return false;
    }
    return true;
}

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
    std::map<std::string, std::string> fields;  // everything in the record, for the read-only fields
    std::string resolveNote;                    // outcome of the "Rileggi metadata" Resolve write
};

// read-only fields: JSON key -> parameter name -> label (group "Dati di ripresa").
// Parameter names must stay unique across the whole plugin and must never change:
// DaVinci Resolve saves a node's settings by parameter name.
struct DetailField { const char* key; const char* param; const char* label; };
static const DetailField kDetails[] = {
    { "lens", "infoLens", "Obiettivo" }, { "focal", "infoFocal", "Focale" },
    { "iris", "infoIris", "Diaframma" }, { "focus", "infoFocus", "Fuoco" },
    { "shutter", "infoShutter", "Shutter" }, { "exposure", "infoExposure", "ISO / EI" },
    { "white_balance", "infoWhiteBalance", "Bilanciamento" }, { "color", "infoColor", "Colore" },
    { "fps", "infoFps", "Frame rate" }, { "nd_stab", "infoNdStab", "ND / Stabilizzatore" },
    { "lut", "infoLut", "LUT camera" }, { "file", "infoFile", "File" } };
static const int kDetailCount = sizeof(kDetails) / sizeof(kDetails[0]);

// macOS marks a file whose content is not on the disk (cloud storage that keeps only a
// placeholder). Reading one downloads it: minutes of frozen UI, and gigabytes. The script
// leaves those alone, and so does the node.
static bool clipIsReadable(const std::string& path, std::string& why)
{
    struct stat st;
    if (stat(path.c_str(), &st) != 0) { why = "file non trovato"; return false; }
    if (st.st_flags & 0x40000000 /* SF_DATALESS */) { why = "il file non e in locale (non scaricato)"; return false; }
    return true;
}

// Clips already tried and failed: without this, every click on such a clip would spawn
// the reader again and freeze the panel for as long as the watchdog allows.
static bool alreadyTried(const std::string& path, bool p_Forget)
{
    static OFX::MultiThread::Mutex mutex;
    static std::set<std::string> tried;
    OFX::MultiThread::AutoMutex lock(mutex);
    if (p_Forget) { tried.erase(path); return false; }
    if (tried.size() > 500) tried.clear();
    return !tried.insert(path).second;
}

static bool fillClipMeta(const std::string& text, ClipMeta& m)
{
    std::map<std::string, std::string> j = parseFlatJson(text);
    if (j.empty()) return false;
    m.ok = true;
    m.supported = atoi(j["supported"].c_str()) != 0;
    m.wbEstimated = atoi(j["wb_estimated"].c_str()) != 0;
    m.shotTemp = atof(j["shot_temp"].c_str());
    m.shotTint = atof(j["shot_tint"].c_str());
    m.shotEI = atof(j["shot_ei"].c_str());
    m.camSpace = j.count("cam_space") ? atoi(j["cam_space"].c_str()) : -1;
    m.camGamma = j.count("cam_gamma") ? atoi(j["cam_gamma"].c_str()) : -1;
    m.levelRequired = j.count("level_required") ? atoi(j["level_required"].c_str()) : -1;
    m.levelHost = j.count("level_host") ? atoi(j["level_host"].c_str()) : -1;
    // the record is a file on disk: a stale or hand-edited one must not index a table
    if (m.camSpace < 0 || m.camSpace >= kSpaceCount) m.camSpace = -1;
    if (m.camGamma < 0 || m.camGamma >= kGammaCount) m.camGamma = -1;
    if (m.levelRequired < 0 || m.levelRequired > 1) m.levelRequired = -1;
    if (m.levelHost < 0 || m.levelHost > 1) m.levelHost = -1;
    m.colorSpace = j["color_space"];
    m.fields = j;
    if (m.shotTemp <= 0.0) m.shotTemp = 5600.0;
    if (m.shotEI <= 0.0) m.shotEI = 800.0;
    return true;
}

static bool loadMeta(const std::string& clipPath, ClipMeta& m, std::string& status, bool p_Force)
{
    const std::string cachePath = supportDir() + "/cache/" + fnv1a64(normalizeNFC(clipPath)) + ".json";
    std::string text;
    if (p_Force) {
        // The button re-reads the file and also writes the metadata into this
        // clip inside Resolve, like the script's "Scrivi in Resolve" but for a
        // single clip. One child does both, so the file is parsed only once.
        alreadyTried(clipPath, true);
        std::string err;
        std::map<std::string, std::string> result;
        const bool ran = runResolverWriter(clipPath, err, result);
        if (!readFile(cachePath, text) || !fillClipMeta(text, m)) {
            const std::string why = ran && result.count("error") ? result["error"] : err;
            status = "Metadata non disponibili: " + (why.empty() ? std::string("clip non Sony?") : why);
            return false;
        }
        if (ran && atoi(result["ok"].c_str()) == 1) {
            m.resolveNote = "scritti in Resolve su questa clip (" + result["written"] + " campi"
                          + (atoi(result["failed"].c_str()) > 0 ? ", " + result["failed"] + " rifiutati" : "") + ")";
            if (!result["level_host"].empty())
                m.resolveNote += " · Data Level della clip: " + result["level_host"];
        } else {
            const std::string why = ran ? (result.count("error") ? result["error"] : std::string("sconosciuto")) : err;
            m.resolveNote = "scrittura in Resolve non riuscita: " + why;
        }
        status = "Metadata letti dal file";
        return true;
    }
    bool fromScript = readFile(cachePath, text);
    if (!fromScript) {
        std::string why;
        if (!clipIsReadable(clipPath, why)) {
            status = "Metadata non letti: " + why;
            return false;
        }
        if (alreadyTried(clipPath, false)) {
            status = "Metadata non disponibili per questa clip: lancia lo script, poi premi Rileggi metadata";
            return false;
        }
        std::string err;
        if (!runExtractor(clipPath, err) || !readFile(cachePath, text)) {
            status = "Metadata non disponibili: " + (err.empty() ? std::string("clip non Sony?") : err);
            return false;
        }
    }
    if (!fillClipMeta(text, m)) {
        status = "Metadata non disponibili: cache non valida";
        return false;
    }
    status = fromScript ? "Metadata letti (registrati da S-Log MetaRaw)"
                        : "Metadata letti dal file: lancia lo script S-Log MetaRaw per registrarli in Resolve";
    return true;
}

// OFX native colourspace name -> (gamut code, transfer code) of DevelopMath.h
static bool mapColourspace(const std::string& cs, int& space, int& gamma)
{
    struct Entry { const char* name; int space; int gamma; };
    static const Entry table[] = {
        { "davinci_intermediate_widegamut", 0, 0 }, { "lin_davinci_widegamut", 0, 1 },
        { "slog3_sgamut3cine", 8, 9 }, { "slog3_sgamut3", 7, 9 },
        { "slog3_venice_sgamut3cine", 8, 9 }, { "slog3_venice_sgamut3", 7, 9 },
        { "lin_sgamut3cine", 8, 1 }, { "lin_sgamut3", 7, 1 },
        { "ACEScct", 10, 10 }, { "ACEScg", 10, 1 }, { "ACES2065-1", 9, 1 },
        { "lin_rec709_srgb", 1, 1 }, { "lin_rec2020", 2, 1 }, { "lin_p3d65", 3, 1 },
        { "g24_rec709_tx", 1, 3 }, { "g22_rec709_tx", 1, 2 }, { "srgb_tx", 1, 6 },
        { "rec1886_rec709_display", 1, 3 }, { "camera_rec709", 1, 5 },
    };
    for (const Entry& e : table) {
        if (cs == e.name) { space = e.space; gamma = e.gamma; return true; }
    }
    return false;
}

// Where a neutral pixel ends up, in CIE 1960 uv, after the white balance for this
// pair of settings. A neutral pixel is the working space white, and the matrices of
// DevelopMath.h are adapted to D65, so it starts from there. Measuring how far it
// moves for a known nudge of each slider, and inverting that, is what lets the two
// white-balance false colours read in Kelvin and in tint units instead of in
// arbitrary distance.
static void neutralUV(double shotK, double shotT, double k, double t, double& u, double& v)
{
    DevelopParams q = DevelopParams();
    sm_set_white_balance(&q, shotK, shotT, k, t);
    const double d65[3] = { 0.95046, 1.0, 1.08906 };
    double lms[3], xyz[3];
    sm_bradford(d65, lms, 0);
    lms[0] *= q.ratioL;
    lms[1] *= q.ratioM;
    lms[2] *= q.ratioS;
    sm_bradford(lms, xyz, 1);
    const double X = xyz[0] * q.norm, Y = xyz[1] * q.norm, Z = xyz[2] * q.norm;
    const double d = X + 15.0 * Y + 3.0 * Z;
    u = d > 1e-9 ? 4.0 * X / d : 0.0;
    v = d > 1e-9 ? 6.0 * Y / d : 0.0;
}

// Advanced "Ingresso nodo" choice: 0 = auto, then fixed pairs.
static const int kNodeInputPairs[][2] = { { 0, 0 }, { 0, 0 }, { 8, 9 }, { 7, 9 }, { 6, 8 }, { 10, 10 } };
static const char* kSpaceNames[] = { "DaVinci WG", "Rec.709", "Rec.2020", "P3 D65", "P3 D60", "P3 DCI", "S-Gamut",
                                     "S-Gamut3", "S-Gamut3.Cine", "ACES AP0", "ACES AP1" };
static const char* kGammaNames[] = { "DaVinci Intermediate", "Linear", "Gamma 2.2", "Gamma 2.4", "Gamma 2.6", "Rec.709",
                                     "sRGB", "SLog", "SLog2", "SLog3", "ACEScct" };
static_assert(sizeof(kSpaceNames) / sizeof(kSpaceNames[0]) == kSpaceCount, "kSpaceCount out of step");
static_assert(sizeof(kGammaNames) / sizeof(kGammaNames[0]) == kGammaCount, "kGammaCount out of step");

// ============================================================================ processor

#ifdef __APPLE__
extern bool RunMetalKernel(void* p_CmdQ, int p_Width, int p_Height, const DevelopParams& p_Params, const float* p_Input, float* p_Output);
#endif

class DevelopProcessor : public OFX::ImageProcessor
{
public:
    explicit DevelopProcessor(OFX::ImageEffect& p_Instance) : OFX::ImageProcessor(p_Instance) {}

    virtual void processImagesMetal()
    {
#ifdef __APPLE__
        const OfxRectI& bounds = _srcImg->getBounds();
        RunMetalKernel(_pMetalCmdQ, bounds.x2 - bounds.x1, bounds.y2 - bounds.y1, _params,
                       static_cast<float*>(_srcImg->getPixelData()), static_cast<float*>(_dstImg->getPixelData()));
#endif
    }

    virtual void multiThreadProcessImages(OfxRectI p_ProcWindow)
    {
        for (int y = p_ProcWindow.y1; y < p_ProcWindow.y2; ++y) {
            if (_effect.abort()) break;
            float* dst = static_cast<float*>(_dstImg->getPixelAddress(p_ProcWindow.x1, y));
            for (int x = p_ProcWindow.x1; x < p_ProcWindow.x2; ++x) {
                const float* src = static_cast<float*>(_srcImg ? _srcImg->getPixelAddress(x, y) : nullptr);
                if (src) {
                    SMf3 o = sm_develop(smf3(src[0], src[1], src[2]), _params);
                    dst[0] = o.x; dst[1] = o.y; dst[2] = o.z; dst[3] = src[3];
                } else {
                    dst[0] = dst[1] = dst[2] = dst[3] = 0.0f;
                }
                dst += 4;
            }
        }
    }

    void setSrcImg(OFX::Image* p_Src) { _srcImg = p_Src; }
    void setParams(const DevelopParams& p) { _params = p; }

private:
    OFX::Image* _srcImg = nullptr;
    DevelopParams _params = {};
};

// ============================================================================ effect

class SLogMetaRaw : public OFX::ImageEffect
{
public:
    explicit SLogMetaRaw(OfxImageEffectHandle p_Handle);

    virtual void render(const OFX::RenderArguments& p_Args);
    virtual bool isIdentity(const OFX::IsIdentityArguments& p_Args, OFX::Clip*& p_IdentityClip, double& p_IdentityTime);
    virtual void changedParam(const OFX::InstanceChangedArgs& p_Args, const std::string& p_ParamName);
    virtual void changedClip(const OFX::InstanceChangedArgs& p_Args, const std::string& p_ClipName);
    virtual void beginEdit();

private:
    std::string sourcePath() const;
    void migrateSettings();
    void syncMetadata(bool p_Force);
    void updateEnabledness();
    void refreshNodeInfo();
    bool buildParams(double p_Time, DevelopParams& p_Params, std::string* p_NodeInfo = nullptr,
                     std::string* p_LevelInfo = nullptr);

    bool m_Ready = false;   // false when a parameter is missing: the node then stays transparent
    OFX::Clip* m_DstClip = nullptr;
    OFX::Clip* m_SrcClip = nullptr;

    OFX::StringParam* m_Camera = nullptr;
    OFX::StringParam* m_Details[kDetailCount] = {};
    OFX::StringParam* m_Status = nullptr;
    OFX::ChoiceParam* m_DecodeUsing = nullptr;
    OFX::ChoiceParam* m_WBMode = nullptr;
    OFX::ChoiceParam* m_ColorSpace = nullptr;
    OFX::ChoiceParam* m_Gamma = nullptr;
    OFX::DoubleParam* m_Temp = nullptr;
    OFX::DoubleParam* m_Tint = nullptr;
    OFX::DoubleParam* m_EI = nullptr;
    OFX::DoubleParam* m_Shadows = nullptr;
    OFX::DoubleParam* m_Highlights = nullptr;
    OFX::DoubleParam* m_Boost = nullptr;
    OFX::DoubleParam* m_Saturation = nullptr;
    OFX::DoubleParam* m_Contrast = nullptr;
    OFX::DoubleParam* m_ColorRecovery = nullptr;
    OFX::BooleanParam* m_FcExposure = nullptr;
    OFX::BooleanParam* m_FcTemperature = nullptr;
    OFX::BooleanParam* m_FcTint = nullptr;
    OFX::ChoiceParam* m_NodeInput = nullptr;
    OFX::StringParam* m_NodeInfo = nullptr;
    OFX::ChoiceParam* m_DataLevel = nullptr;
    OFX::StringParam* m_LevelInfo = nullptr;
    // hidden, saved with the grade
    OFX::StringParam* m_BoundPath = nullptr;
    OFX::DoubleParam* m_ShotTemp = nullptr;
    OFX::DoubleParam* m_ShotTint = nullptr;
    OFX::DoubleParam* m_ShotEI = nullptr;
    OFX::IntParam* m_CamSpace = nullptr;
    OFX::IntParam* m_CamGamma = nullptr;
    OFX::IntParam* m_LevelRequired = nullptr;
    OFX::IntParam* m_LevelHost = nullptr;
    OFX::BooleanParam* m_MetaValid = nullptr;
    OFX::IntParam* m_SettingsVersion = nullptr;
};

SLogMetaRaw::SLogMetaRaw(OfxImageEffectHandle p_Handle)
    : ImageEffect(p_Handle)
{
    // A fetch throws when the host built this instance without that parameter. Rather
    // than let the exception travel back into the host, the node marks itself not ready
    // and behaves as a transparent pass-through: a broken install can slow you down,
    // never take DaVinci Resolve down with it.
    try {
        m_DstClip = fetchClip(kOfxImageEffectOutputClipName);
        m_SrcClip = fetchClip(kOfxImageEffectSimpleSourceClipName);
        m_Camera = fetchStringParam("camera");
        for (int i = 0; i < kDetailCount; ++i) m_Details[i] = fetchStringParam(kDetails[i].param);
        m_Status = fetchStringParam("status");
        m_DecodeUsing = fetchChoiceParam("decodeUsing");
        m_WBMode = fetchChoiceParam("whiteBalance");
        m_ColorSpace = fetchChoiceParam("colorSpace");
        m_Gamma = fetchChoiceParam("gamma");
        m_Temp = fetchDoubleParam("colorTemp");
        m_Tint = fetchDoubleParam("tint");
        m_EI = fetchDoubleParam("exposure");
        m_Shadows = fetchDoubleParam("shadows");
        m_Highlights = fetchDoubleParam("highlights");
        m_Boost = fetchDoubleParam("colorBoost");
        m_Saturation = fetchDoubleParam("saturation");
        m_Contrast = fetchDoubleParam("contrast");
        m_ColorRecovery = fetchDoubleParam("colorRecovery");
        m_FcExposure = fetchBooleanParam("fcExposure");
        m_FcTemperature = fetchBooleanParam("fcTemperature");
        m_FcTint = fetchBooleanParam("fcTint");
        m_NodeInput = fetchChoiceParam("nodeInput");
        m_NodeInfo = fetchStringParam("nodeInfo");
        m_DataLevel = fetchChoiceParam("dataLevel");
        m_LevelInfo = fetchStringParam("levelInfo");
        m_BoundPath = fetchStringParam("boundPath");
        m_ShotTemp = fetchDoubleParam("shotTemp");
        m_ShotTint = fetchDoubleParam("shotTint");
        m_ShotEI = fetchDoubleParam("shotEI");
        m_CamSpace = fetchIntParam("camSpace");
        m_CamGamma = fetchIntParam("camGamma");
        m_LevelRequired = fetchIntParam("levelRequired");
        m_LevelHost = fetchIntParam("levelHost");
        m_MetaValid = fetchBooleanParam("metaValid");
        m_SettingsVersion = fetchIntParam("settingsVersion");
        m_Ready = true;
    } catch (const std::exception& e) {
        fprintf(stderr, "S-Log MetaRaw: nodo disattivato, parametro mancante (%s)\n", e.what());
        return;
    } catch (...) {
        fprintf(stderr, "S-Log MetaRaw: nodo disattivato, parametro mancante\n");
        return;
    }

    // Some hosts refuse parameter changes while an instance is being created:
    // never fail the node for that, beginEdit() retries when the panel is opened.
    try {
        migrateSettings();
        syncMetadata(false);
        updateEnabledness();
    } catch (...) {
    }
}

std::string SLogMetaRaw::sourcePath() const
{
    return getPropertySet().propGetString(kOfxImageEffectPropSrcFilePath, false);
}

// A node saved by an older release keeps its parameters (the host restores them by
// name), and settingsVersion says which meaning those values had. Newer releases
// convert them here, so a grade made today still opens the same way years from now.
void SLogMetaRaw::migrateSettings()
{
    int saved = kSettingsVersion;
    m_SettingsVersion->getValue(saved);
    if (saved == kSettingsVersion) return;
    if (saved > kSettingsVersion) {   // project saved by a newer plugin: keep the values as they are
        fprintf(stderr, "S-Log MetaRaw: nodo salvato con impostazioni v%d, questo plugin arriva alla v%d\n",
                saved, kSettingsVersion);
        return;
    }
    if (saved <= 1) {
        // v2 added the data level correction. A grade made before it must keep
        // looking exactly as it did, so on an old node the correction starts off;
        // new nodes get "Automatico".
        m_DataLevel->setValue(3);   // Nessuna correzione
    }
    if (saved <= 2) {
        // v3 moved the tone trims from -1..1 to -100..+100. The stored numbers mean
        // a hundred times less than they used to, so scale them or an old grade
        // would open flat.
        OFX::DoubleParam* const tones[] = { m_Shadows, m_Highlights, m_Boost, m_Saturation, m_Contrast };
        for (OFX::DoubleParam* p : tones) p->setValue(p->getValue() * kToneScale);
    }
    // v4 replaced Highlights and Shadows: they were a shelf with a slope jump at
    // +-5 stops, they are now a filmic shoulder and a shadow bell. There is no
    // faithful conversion - the old curve had no shoulder to convert. A node that
    // left both at 0 opens identical; one that used them keeps its numbers and
    // renders differently, which is the point. Nothing is silently zeroed, so the
    // colourist's intent stays visible rather than being thrown away.
    m_SettingsVersion->setValue(kSettingsVersion);
}

static void setText(OFX::StringParam* p, const std::string& v)
{
    std::string cur;
    p->getValue(cur);
    if (cur != v) p->setValue(v);  // avoid touching the grade when nothing changed
}

// Load the camera values of the clip this node sits on. The read-only fields are
// always refreshed; the sliders are set to the camera values only for a new node,
// a node copied to another clip, or "Rileggi metadata" (p_Force), so the
// colourist's adjustments survive a project reload.
void SLogMetaRaw::syncMetadata(bool p_Force)
{
    const std::string path = sourcePath();
    if (path.empty()) {
        setText(m_Status, "Resolve non ha fornito il percorso della clip (compound clip?)");
        refreshNodeInfo();   // the Avanzate fields still say what the node is doing
        return;
    }
    std::string bound;
    m_BoundPath->getValue(bound);
    const bool sameClip = (bound == path);

    ClipMeta meta;
    std::string status;
    if (!loadMeta(path, meta, status, p_Force)) {
        m_MetaValid->setValue(false);
        setText(m_Camera, "Metadata non trovati");
        for (int i = 0; i < kDetailCount; ++i) setText(m_Details[i], "—");
        setText(m_Details[kDetailCount - 1], path.substr(path.find_last_of('/') + 1));
        setText(m_Status, status);
        m_BoundPath->setValue(path);
        updateEnabledness();
        return;
    }
    setText(m_Camera, meta.fields["camera_name"]);
    for (int i = 0; i < kDetailCount; ++i) {
        auto it = meta.fields.find(kDetails[i].key);
        setText(m_Details[i], it != meta.fields.end() && !it->second.empty() ? it->second : "—");
    }
    if (m_ShotTemp->getValue() != meta.shotTemp) m_ShotTemp->setValue(meta.shotTemp);
    if (m_ShotTint->getValue() != meta.shotTint) m_ShotTint->setValue(meta.shotTint);
    if (m_ShotEI->getValue() != meta.shotEI) m_ShotEI->setValue(meta.shotEI);
    if (m_CamSpace->getValue() != meta.camSpace) m_CamSpace->setValue(meta.camSpace);
    if (m_CamGamma->getValue() != meta.camGamma) m_CamGamma->setValue(meta.camGamma);
    if (m_LevelRequired->getValue() != meta.levelRequired) m_LevelRequired->setValue(meta.levelRequired);
    if (m_LevelHost->getValue() != meta.levelHost) m_LevelHost->setValue(meta.levelHost);
    const std::string note = meta.resolveNote.empty() ? "" : " · " + meta.resolveNote;
    if (!meta.supported) {
        if (m_MetaValid->getValue()) m_MetaValid->setValue(false);
        setText(m_Status, "Profilo " + meta.colorSpace + " non logaritmico: il nodo resta neutro" + note);
    } else {
        if (!m_MetaValid->getValue()) m_MetaValid->setValue(true);
        setText(m_Status, status + (meta.wbEstimated ? " · Kelvin stimato (la camera non lo registra)" : "") + note);
        if (!sameClip || p_Force) {
            m_WBMode->setValue(0);
            m_Temp->setValue(meta.shotTemp);
            m_Tint->setValue(meta.shotTint);
            m_EI->setValue(meta.shotEI);
        }
    }
    if (!sameClip) m_BoundPath->setValue(path);
    updateEnabledness();
    refreshNodeInfo();
}

void SLogMetaRaw::refreshNodeInfo()
{
    DevelopParams p;
    std::string info, level;
    buildParams(0.0, p, &info, &level);
    if (!info.empty()) setText(m_NodeInfo, info);
    if (!level.empty()) setText(m_LevelInfo, level);
}

void SLogMetaRaw::updateEnabledness()
{
    int decode = 1;
    m_DecodeUsing->getValue(decode);
    const bool on = (decode == 1) && m_MetaValid->getValue();
    m_WBMode->setEnabled(on);
    m_ColorSpace->setEnabled(on);
    m_Gamma->setEnabled(on);
    m_Temp->setEnabled(on);
    m_Tint->setEnabled(on);
    m_EI->setEnabled(on);
    m_Shadows->setEnabled(on);
    m_Highlights->setEnabled(on);
    m_Boost->setEnabled(on);
    m_Saturation->setEnabled(on);
    m_Contrast->setEnabled(on);
    m_ColorRecovery->setEnabled(on);
}

void SLogMetaRaw::beginEdit()
{
    if (!m_Ready) return;
    try {
        syncMetadata(false);
        refreshNodeInfo();
    } catch (...) {
    }
}

void SLogMetaRaw::changedClip(const OFX::InstanceChangedArgs& /*p_Args*/, const std::string& p_ClipName)
{
    if (!m_Ready) return;
    if (p_ClipName == kOfxImageEffectSimpleSourceClipName) syncMetadata(false);
}

void SLogMetaRaw::changedParam(const OFX::InstanceChangedArgs& p_Args, const std::string& p_ParamName)
{
    if (!m_Ready) return;
    const bool user = (p_Args.reason == OFX::eChangeUserEdit);
    if (p_ParamName == "reload") {
        syncMetadata(true);
    } else if (p_ParamName == "decodeUsing") {
        updateEnabledness();
    } else if (p_ParamName == "nodeInput" || p_ParamName == "dataLevel") {
        refreshNodeInfo();
    } else if (p_ParamName == "fcExposure" || p_ParamName == "fcTemperature" || p_ParamName == "fcTint") {
        if (user) {   // the views measure different things: only one can be on
            OFX::BooleanParam* const toggles[] = { m_FcExposure, m_FcTemperature, m_FcTint };
            static const char* const names[] = { "fcExposure", "fcTemperature", "fcTint" };
            for (int i = 0; i < 3; ++i)
                if (p_ParamName != names[i] && toggles[i]->getValue()) toggles[i]->setValue(false);
        }
        refreshNodeInfo();
    } else if (p_ParamName == "whiteBalance" && user) {
        int wb = 0;
        m_WBMode->getValue(wb);
        if (wb == 0) {  // As shot
            m_Temp->setValue(m_ShotTemp->getValue());
            m_Tint->setValue(m_ShotTint->getValue());
        } else if (wb > 0 && wb < kWBCustom) {
            m_Temp->setValue(kPresetKelvin[wb]);
            m_Tint->setValue(0.0);
        }
    } else if ((p_ParamName == "colorTemp" || p_ParamName == "tint") && user) {
        int wb = 0;
        m_WBMode->getValue(wb);
        if (wb != kWBCustom) m_WBMode->setValue(kWBCustom);  // like Camera Raw: moving the sliders means Custom
    }
}

bool SLogMetaRaw::buildParams(double p_Time, DevelopParams& p, std::string* p_NodeInfo,
                              std::string* p_LevelInfo)
{
    if (!m_Ready) { p.bypass = 1; return false; }
    p = DevelopParams();

    // colour space of the image entering the node
    int nodeSpace = 0, nodeGamma = 0, input = 0;
    m_NodeInput->getValue(input);
    std::string hostCs = m_SrcClip->getPropertySet().propGetString(kOfxImageClipPropColourspace, false);
    if (input > 0) {
        nodeSpace = kNodeInputPairs[input][0];
        nodeGamma = kNodeInputPairs[input][1];
    } else if (!mapColourspace(hostCs, nodeSpace, nodeGamma)) {
        // no colour management info: nodes receive the camera encoding (DaVinci YRGB)
        const int cs = m_CamSpace->getValue(), cg = m_CamGamma->getValue();
        if (cs >= 0 && cg >= 0) { nodeSpace = cs; nodeGamma = cg; }
    }
    if (p_NodeInfo) {
        *p_NodeInfo = std::string("Ingresso nodo: ") + kSpaceNames[nodeSpace] + " / " + kGammaNames[nodeGamma]
                    + (hostCs.empty() ? "" : " (Resolve: " + hostCs + ")");
    }

    p.nodeSpace = nodeSpace;
    p.nodeGamma = nodeGamma;

    // ---- data level (maths/why in sm_fix_levels, DevelopMath.h). Runs before the
    // bypass check: a wrong data level is a file decode error, not a look, so it's
    // worth fixing even with develop off, or with no Sony metadata at all (e.g. an
    // Atomos ProRes of the same S-Log, declared via "Ingresso nodo").
    int levelChoice = 0;
    m_DataLevel->getValue(levelChoice);
    const int camSpaceCode = m_CamSpace->getValue(), camGammaCode = m_CamGamma->getValue();
    const int domSpace = camSpaceCode >= 0 ? camSpaceCode : (input > 0 ? nodeSpace : -1);
    const int domGamma = camGammaCode >= 0 ? camGammaCode : (input > 0 ? nodeGamma : -1);
    int want = m_LevelRequired->getValue();                      // from the clip's metadata
    if (want < 0 && domGamma >= 7 && domGamma <= 9) want = 1;    // S-Log / S-Log2 / S-Log3
    int have = m_LevelHost->getValue();                          // what Resolve reports
    if (levelChoice == 1) have = 1;                              // Full, declared by hand
    else if (levelChoice == 2) have = 0;                         // Video, declared by hand
    std::string levelWhy;
    if (levelChoice == 3) {
        levelWhy = "disattivata";
    } else if (want < 0 || domGamma < 0 || domSpace < 0) {
        levelWhy = "curva della clip non nota: nessuna correzione";
    } else if (have < 0) {
        levelWhy = std::string("Resolve e su Auto, il valore effettivo non e leggibile · questa curva vuole ")
                 + kLevelNames[want] + " · imposta Data Level in Attributi clip (lo fa anche lo script) "
                   "oppure dichiaralo qui sopra";
    } else if (have != want) {
        p.levelFix = 1;
        p.levelSpace = domSpace;
        p.levelGamma = domGamma;
        if (have == 0) { p.levelGain = 876.0f / 1023.0f; p.levelOffset = 64.0f / 1023.0f; }
        else           { p.levelGain = 1023.0f / 876.0f; p.levelOffset = -64.0f / 876.0f; }
        char buf[320];
        snprintf(buf, sizeof(buf), "in ingresso %s, la curva vuole %s · correzione x%.6f %+.6f su %s / %s",
                 kLevelNames[have], kLevelNames[want], p.levelGain, p.levelOffset,
                 kSpaceNames[p.levelSpace], kGammaNames[p.levelGamma]);
        levelWhy = buf;
    } else {
        levelWhy = std::string("in ingresso ") + kLevelNames[have] + ": corretto, nessuna correzione";
    }
    if (p_LevelInfo) *p_LevelInfo = levelWhy;

    int decode = 1;
    m_DecodeUsing->getValueAtTime(p_Time, decode);
    if (decode == 0 || !m_MetaValid->getValue()) {
        p.bypass = 1;
        return false;
    }

    int cs = 0, gm = 0;
    m_ColorSpace->getValueAtTime(p_Time, cs);
    m_Gamma->getValueAtTime(p_Time, gm);
    p.outSpace = cs == 0 ? nodeSpace : cs - 1;
    p.outGamma = gm == 0 ? nodeGamma : gm - 1;
    p.convert = (p.outSpace != nodeSpace || p.outGamma != nodeGamma) ? 1 : 0;

    const double shotEI = m_ShotEI->getValue();
    const double ei = m_EI->getValueAtTime(p_Time);
    p.expo = (shotEI > 0.0 && ei > 0.0) ? (float)(ei / shotEI) : 1.0f;
    sm_set_white_balance(&p, m_ShotTemp->getValue(), m_ShotTint->getValue(), m_Temp->getValueAtTime(p_Time),
                         m_Tint->getValueAtTime(p_Time));

    // ---- false colour: a measuring view for one of the three controls -------
    int fc = 0;
    if (m_FcExposure->getValue()) fc = 1;
    else if (m_FcTemperature->getValue()) fc = 2;
    else if (m_FcTint->getValue()) fc = 3;
    p.fcMode = fc;
    if (fc >= 2) {
        // Measure how far a neutral pixel moves for a known nudge of each white
        // balance slider, at the setting in use, and invert it. The bands then read
        // in the units of the sliders themselves: the number behind a band is how
        // far that slider is from making the pixel neutral.
        const double k = m_Temp->getValueAtTime(p_Time), t = m_Tint->getValueAtTime(p_Time);
        double u0, v0, uk, vk, ut, vt;
        neutralUV(k, t, k, t, u0, v0);
        neutralUV(k, t, k + 100.0, t, uk, vk);
        neutralUV(k, t, k, t + 5.0, ut, vt);
        const double a = (uk - u0) / 100.0, c = (vk - v0) / 100.0;
        const double b = (ut - u0) / 5.0, e = (vt - v0) / 5.0;
        const double det = a * e - b * c;
        p.fcU = (float)u0;
        p.fcV = (float)v0;
        if (std::fabs(det) > 1e-12) {
            p.fcKu = (float)(e / det);
            p.fcKv = (float)(-b / det);
            p.fcTu = (float)(-c / det);
            p.fcTv = (float)(a / det);
        } else {
            p.fcMode = 0;   // degenerate basis: show the picture rather than a lie
        }
    }
    if (p_NodeInfo && p.fcMode != 0)
        *p_NodeInfo = std::string("FALSE COLOR ATTIVO (")
                    + (p.fcMode == 1 ? "esposizione" : p.fcMode == 2 ? "temperatura" : "tint")
                    + ") · " + *p_NodeInfo;

    // the panel works in hundredths, the maths in -1..1
    p.shadows = (float)(m_Shadows->getValueAtTime(p_Time) / kToneScale);
    p.highlights = (float)(m_Highlights->getValueAtTime(p_Time) / kToneScale);
    p.contrast = (float)(m_Contrast->getValueAtTime(p_Time) / kToneScale);
    p.saturation = (float)(m_Saturation->getValueAtTime(p_Time) / kToneScale);
    p.boost = (float)(m_Boost->getValueAtTime(p_Time) / kToneScale);
    p.chromaRecover = (float)(m_ColorRecovery->getValueAtTime(p_Time) / kToneScale);
    return true;
}

bool SLogMetaRaw::isIdentity(const OFX::IsIdentityArguments& p_Args, OFX::Clip*& p_IdentityClip, double& p_IdentityTime)
{
    if (!m_Ready) {   // no parameters: hand the image straight through
        p_IdentityClip = m_SrcClip;
        p_IdentityTime = p_Args.time;
        return true;
    }
    DevelopParams p;
    buildParams(p_Args.time, p);
    const bool neutral = p.levelFix == 0 && p.fcMode == 0
                         && (p.bypass || (p.convert == 0 && std::fabs(p.expo - 1.0f) < 1e-6f
                         && std::fabs(p.ratioL - 1.0f) < 1e-6f && std::fabs(p.ratioM - 1.0f) < 1e-6f
                         && std::fabs(p.ratioS - 1.0f) < 1e-6f && p.shadows == 0.0f && p.highlights == 0.0f
                         && p.contrast == 0.0f && p.saturation == 0.0f && p.boost == 0.0f
                         && p.chromaRecover == 0.0f));
    if (neutral) {
        p_IdentityClip = m_SrcClip;
        p_IdentityTime = p_Args.time;
        return true;
    }
    return false;
}

void SLogMetaRaw::render(const OFX::RenderArguments& p_Args)
{
    if (!m_Ready || !m_DstClip || !m_SrcClip) return;   // not initialised: leave the image alone
    if (m_DstClip->getPixelDepth() != OFX::eBitDepthFloat || m_DstClip->getPixelComponents() != OFX::ePixelComponentRGBA)
        OFX::throwSuiteStatusException(kOfxStatErrUnsupported);

    std::unique_ptr<OFX::Image> dst(m_DstClip->fetchImage(p_Args.time));
    std::unique_ptr<OFX::Image> src(m_SrcClip->fetchImage(p_Args.time));
    if (!dst || !src || src->getPixelDepth() != dst->getPixelDepth() || src->getPixelComponents() != dst->getPixelComponents())
        OFX::throwSuiteStatusException(kOfxStatErrValue);

    DevelopParams params;
    buildParams(p_Args.time, params);
    DevelopProcessor processor(*this);
    processor.setDstImg(dst.get());
    processor.setSrcImg(src.get());
    processor.setGPURenderArgs(p_Args);
    processor.setRenderWindow(p_Args.renderWindow);
    processor.setParams(params);
    processor.process();
}

// ============================================================================ factory

using namespace OFX;

SLogMetaRawFactory::SLogMetaRawFactory()
    : OFX::PluginFactoryHelper<SLogMetaRawFactory>(kPluginIdentifier, kPluginVersionMajor, kPluginVersionMinor)
{
}

void SLogMetaRawFactory::describe(OFX::ImageEffectDescriptor& p_Desc)
{
    p_Desc.setLabels(kPluginName, kPluginName, kPluginName);
    p_Desc.setPluginGrouping(kPluginGrouping);
    p_Desc.setPluginDescription(kPluginDescription);
    // icon in Contents/Resources: index 0 = SVG (none), index 1 = PNG
    p_Desc.getPropertySet().propSetString(kOfxPropIcon, "", 0, false);
    p_Desc.getPropertySet().propSetString(kOfxPropIcon, kPluginIcon, 1, false);
    p_Desc.addSupportedContext(eContextFilter);
    p_Desc.addSupportedContext(eContextGeneral);
    p_Desc.addSupportedBitDepth(eBitDepthFloat);
    p_Desc.setSingleInstance(false);
    p_Desc.setHostFrameThreading(false);
    p_Desc.setSupportsMultiResolution(false);
    p_Desc.setSupportsTiles(false);
    p_Desc.setTemporalClipAccess(false);
    p_Desc.setRenderTwiceAlways(false);
    p_Desc.setSupportsMultipleClipPARs(false);
#ifdef __APPLE__
    p_Desc.setSupportsMetalRender(true);
#endif
    // per-pixel only: Resolve can include the node in LUT generation (ExportLUT)
    p_Desc.setNoSpatialAwareness(true);
    // OFX 1.5 colour management: Resolve tells us the colour space entering the node
    p_Desc.getPropertySet().propSetString(kOfxImageEffectPropColourManagementStyle, kOfxImageEffectColourManagementFull, false);
    p_Desc.getPropertySet().propSetString(kOfxImageEffectPropColourManagementAvailableConfigs, kOfxNativeConfig, false);
}

// A duplicate parameter name crashes the host while it builds the panel: refuse it.
// The names are claimed per describeInContext() call: the host calls that action once
// for every supported context, and a set shared between calls would make the second
// context come out with no parameters at all (and the instance then fails to build).
static std::set<std::string>& usedNames()
{
    static thread_local std::set<std::string> names;
    return names;
}

static bool claimName(const std::string& name)
{
    if (!usedNames().insert(name).second) {
        fprintf(stderr, "S-Log MetaRaw: parametro duplicato \"%s\", ignorato\n", name.c_str());
        return false;
    }
    return true;
}

static StringParamDescriptor* defineInfo(ImageEffectDescriptor& d, PageParamDescriptor* page, GroupParamDescriptor* group,
                                         const std::string& name, const std::string& label,
                                         const std::string& def = "—")
{
    if (!claimName(name)) return nullptr;
    StringParamDescriptor* p = d.defineStringParam(name);
    p->setLabels(label, label, label);
    p->setStringType(eStringTypeSingleLine);
    p->setDefault(def);            // never show an empty box before the metadata is read
    p->setEnabled(false);          // read-only: these are camera values, not settings
    p->setAnimates(false);
    p->setEvaluateOnChange(false);
    if (group) p->setParent(*group);
    page->addChild(*p);
    return p;
}

static DoubleParamDescriptor* defineSlider(ImageEffectDescriptor& d, PageParamDescriptor* page, const std::string& name,
                                           const std::string& label, double def, double lo, double hi, double dlo, double dhi,
                                           double inc, const char* hint = nullptr)
{
    if (!claimName(name)) return nullptr;
    DoubleParamDescriptor* p = d.defineDoubleParam(name);
    p->setLabels(label, label, label);
    p->setScriptName(name);
    p->setDefault(def);
    p->setRange(lo, hi);
    p->setDisplayRange(dlo, dhi);
    p->setIncrement(inc);
    p->setDoubleType(eDoubleTypePlain);
    if (hint) p->setHint(hint);
    page->addChild(*p);
    return p;
}

// A false-colour toggle: a boolean carrying the icon of the axis it measures.
// OpenFX gives a host no way to put a control on the same row as another one, so
// each of these sits immediately above the slider it belongs to.
static BooleanParamDescriptor* defineToggle(ImageEffectDescriptor& d, PageParamDescriptor* page,
                                            const std::string& name, const std::string& label,
                                            const char* icon, const char* hint)
{
    if (!claimName(name)) return nullptr;
    BooleanParamDescriptor* p = d.defineBooleanParam(name);
    p->setLabels(label, label, label);
    p->setDefault(false);
    p->setHint(hint);
    p->setIcon(icon, true);        // PNG in Contents/Resources, as for the plugin icon
    p->setAnimates(false);
    page->addChild(*p);
    return p;
}

static ChoiceParamDescriptor* defineChoice(ImageEffectDescriptor& d, PageParamDescriptor* page, const std::string& name,
                                           const std::string& label, const char* const* options, int count, int def,
                                           const char* hint = nullptr)
{
    if (!claimName(name)) return nullptr;
    ChoiceParamDescriptor* p = d.defineChoiceParam(name);
    p->setLabels(label, label, label);
    for (int i = 0; i < count; ++i) p->appendOption(options[i]);
    p->setDefault(def);
    if (hint) p->setHint(hint);
    p->setAnimates(false);
    page->addChild(*p);
    return p;
}

template <typename T>
static void hide(T* p, PageParamDescriptor* page)
{
    p->setIsSecret(true);
    p->setAnimates(false);
    page->addChild(*p);
}

void SLogMetaRawFactory::describeInContext(OFX::ImageEffectDescriptor& p_Desc, OFX::ContextEnum /*p_Context*/)
{
    usedNames().clear();   // one fresh set of parameter names per context
    ClipDescriptor* srcClip = p_Desc.defineClip(kOfxImageEffectSimpleSourceClipName);
    srcClip->addSupportedComponent(ePixelComponentRGBA);
    srcClip->setTemporalClipAccess(false);
    srcClip->setSupportsTiles(false);
    srcClip->setIsMask(false);
    ClipDescriptor* dstClip = p_Desc.defineClip(kOfxImageEffectOutputClipName);
    dstClip->addSupportedComponent(ePixelComponentRGBA);
    dstClip->setSupportsTiles(false);

    PageParamDescriptor* page = p_Desc.definePageParam("Controls");

    // camera name and reload button at the top, not inside a group
    defineInfo(p_Desc, page, nullptr, "camera", "Camera", "— premi Rileggi metadata");
    PushButtonParamDescriptor* reload = p_Desc.definePushButtonParam("reload");
    reload->setLabels("Rileggi metadata", "Rileggi metadata", "Rileggi metadata");
    reload->setHint("Rilegge i metadata della clip dal file, li scrive nel Media Pool di Resolve "
                    "e riporta i controlli ai valori di camera");
    page->addChild(*reload);

    // same order as the native Camera Raw "Sony Video" panel
    static const char* decodeOpts[] = { "Camera metadata", "Clip" };
    defineChoice(p_Desc, page, "decodeUsing", "Decode Using", decodeOpts, 2, 1,
                 "Camera metadata: usa i valori di ripresa e blocca i controlli. Clip: puoi modificarli");
    static const char* wbOpts[] = { "As shot", "Daylight", "Cloudy", "Shade", "Tungsten", "Fluorescent", "Flash", "Custom" };
    defineChoice(p_Desc, page, "whiteBalance", "White Balance", wbOpts, 8, 0,
                 "As shot riporta ai Kelvin di ripresa; muovendo gli slider diventa Custom");
    defineToggle(p_Desc, page, "fcTemperature", "False color: temperatura", "fc_temperature.png",
                 "Mostra quanto ogni pixel e lontano dal neutro in Kelvin. Bianco = neutro, "
                 "blu = da scaldare, arancio = da raffreddare. Bande: 75, 200, 500 K");
    defineSlider(p_Desc, page, "colorTemp", "Color Temp", 5600, 2000, 15000, 2000, 15000, 10,
                 "Temperatura in Kelvin: adattamento cromatico Bradford in luce lineare");
    defineToggle(p_Desc, page, "fcTint", "False color: tint", "fc_tint.png",
                 "Mostra quanto ogni pixel e lontano dal neutro in unita di tint. Bianco = neutro, "
                 "verde = da togliere verde, magenta = da togliere magenta. Bande: 2, 5, 12");
    defineSlider(p_Desc, page, "tint", "Tint", 0, -100, 100, -100, 100, 0.1,
                 "Verde/magenta, perpendicolare al luogo di Planck");
    defineToggle(p_Desc, page, "fcExposure", "False color: esposizione", "fc_exposure.png",
                 "Mappa le fermate attorno al grigio 18%: verde = grigio medio, rosa = incarnato "
                 "(una fermata sopra), giallo = vicino al clip, rosso = clip, blu e viola = nero");
    defineSlider(p_Desc, page, "exposure", "Exposure", 800, 25, 409600, 50, 25600, 1,
                 "Exposure Index: il doppio dell'EI di ripresa = +1 stop");
    static const char* csOpts[] = { "Timeline", "DaVinci WG", "Rec.709", "Rec.2020", "P3 D65", "P3 D60", "P3 DCI",
                                    "S-Gamut", "S-Gamut3", "S-Gamut3.Cine", "ACES AP0", "ACES AP1" };
    defineChoice(p_Desc, page, "colorSpace", "Color Space", csOpts, 12, 0,
                 "Gamut in uscita, come un Color Space Transform. Timeline non converte");
    static const char* gmOpts[] = { "Timeline", "DaVinci Intermediate", "Linear", "Gamma 2.2", "Gamma 2.4", "Gamma 2.6",
                                    "Rec.709", "sRGB", "SLog", "SLog2", "SLog3", "ACEScct" };
    defineChoice(p_Desc, page, "gamma", "Gamma", gmOpts, 12, 0,
                 "Curva in uscita. Timeline non converte");

    GroupParamDescriptor* tones = p_Desc.defineGroupParam("tonesGroup");
    tones->setLabels("Toni", "Toni", "Toni");
    tones->setOpen(true);
    page->addChild(*tones);
    // Highlights and Shadows first, then the control that governs what their
    // recovery does to colour: the three belong together.
    const char* toneNames[][3] = {
        { "highlights", "Highlights", "Negativo: spalla filmica, ripiega le alte luci verso un asintoto che "
                                      "non raggiunge mai, senza toccare i mezzitoni. Positivo: le schiarisce" },
        { "shadows", "Shadows", "Apre o chiude il dettaglio in ombra attorno a -4 stop. Non tocca il grigio "
                                "ne il piede del nero: il nero assoluto resta nero a qualsiasi valore" },
        { "colorRecovery", "Color Recovery", "Verso destra restituisce colore alle alte luci recuperate e toglie "
                                             "croma alle ombre aperte, dove sta il rumore. Verso sinistra va "
                                             "verso la pellicola, che avvicinandosi al bianco desatura di piu" },
        { "colorBoost", "Color Boost", "Vibrance: pesa sulla saturazione gia presente nel pixel" },
        { "saturation", "Saturation", "Saturazione attorno alla luminanza, nel gamut del nodo" },
        { "contrast", "Contrast", "Legge di potenza attorno al grigio 18%" } };
    // -100..+100 with two decimals, the scale DaVinci Resolve itself uses for the
    // same kind of trim (Col Boost, Shad, High, Mid/Detail in the Color Wheels and
    // Camera Raw panels). DevelopParams keeps them as -1..1, buildParams divides.
    for (const auto& t : toneNames) {
        if (DoubleParamDescriptor* p = defineSlider(p_Desc, page, t[0], t[1], 0, -100, 100, -100, 100, 0.1, t[2])) {
            p->setDigits(2);
            p->setParent(*tones);
        }
    }

    GroupParamDescriptor* adv = p_Desc.defineGroupParam("advancedGroup");
    adv->setLabels("Avanzate", "Avanzate", "Avanzate");
    adv->setOpen(false);
    page->addChild(*adv);
    static const char* nodeOpts[] = { "Automatico", "DaVinci WG/Intermediate", "S-Gamut3.Cine/S-Log3", "S-Gamut3/S-Log3",
                                      "S-Gamut/S-Log2", "ACES AP1/ACEScct" };
    if (ChoiceParamDescriptor* node = defineChoice(p_Desc, page, "nodeInput", "Ingresso nodo", nodeOpts, 6, 0,
            "Spazio colore che entra nel nodo. Automatico lo chiede a Resolve: cambialo solo se sbagliato")) {
        node->setParent(*adv);
    }
    defineInfo(p_Desc, page, adv, "nodeInfo", "Rilevato");
    static const char* levelOpts[] = { "Automatico", "Full (0-1023)", "Video (64-940)", "Nessuna correzione" };
    if (ChoiceParamDescriptor* lev = defineChoice(p_Desc, page, "dataLevel", "Data level in ingresso", levelOpts, 4, 0,
            "Scala di code value su cui Resolve ha decodificato la clip. Automatico usa l'attributo "
            "Data Level della clip: se e su Auto non correggo niente. Full o Video lo dichiari tu, "
            "utile su un ProRes esterno che nessun NLE segnala")) {
        lev->setParent(*adv);
    }
    defineInfo(p_Desc, page, adv, "levelInfo", "Data level");
    defineInfo(p_Desc, page, adv, "status", "Stato");

    GroupParamDescriptor* details = p_Desc.defineGroupParam("detailsGroup");
    details->setLabels("Dati di ripresa", "Dati di ripresa", "Dati di ripresa");
    details->setHint("Valori letti dalla clip, in sola lettura");
    details->setOpen(false);
    page->addChild(*details);
    for (int i = 0; i < kDetailCount; ++i)
        defineInfo(p_Desc, page, details, kDetails[i].param, kDetails[i].label);

    StringParamDescriptor* bound = p_Desc.defineStringParam("boundPath");
    hide(bound, page);
    DoubleParamDescriptor* shotTemp = p_Desc.defineDoubleParam("shotTemp");
    shotTemp->setDefault(5600);
    hide(shotTemp, page);
    DoubleParamDescriptor* shotTint = p_Desc.defineDoubleParam("shotTint");
    hide(shotTint, page);
    DoubleParamDescriptor* shotEI = p_Desc.defineDoubleParam("shotEI");
    shotEI->setDefault(800);
    hide(shotEI, page);
    IntParamDescriptor* camSpace = p_Desc.defineIntParam("camSpace");
    camSpace->setDefault(-1);
    hide(camSpace, page);
    IntParamDescriptor* camGamma = p_Desc.defineIntParam("camGamma");
    camGamma->setDefault(-1);
    hide(camGamma, page);
    IntParamDescriptor* levelRequired = p_Desc.defineIntParam("levelRequired");
    levelRequired->setDefault(-1);
    hide(levelRequired, page);
    IntParamDescriptor* levelHost = p_Desc.defineIntParam("levelHost");
    levelHost->setDefault(-1);
    hide(levelHost, page);
    BooleanParamDescriptor* valid = p_Desc.defineBooleanParam("metaValid");
    valid->setDefault(false);
    hide(valid, page);
    // saved with every node: lets future versions recognise and migrate old settings
    IntParamDescriptor* settingsVersion = p_Desc.defineIntParam("settingsVersion");
    settingsVersion->setDefault(kSettingsVersion);
    hide(settingsVersion, page);
}

ImageEffect* SLogMetaRawFactory::createInstance(OfxImageEffectHandle p_Handle, ContextEnum /*p_Context*/)
{
    return new SLogMetaRaw(p_Handle);
}

void OFX::Plugin::getPluginIDs(PluginFactoryArray& p_FactoryArray)
{
    static SLogMetaRawFactory factory;
    p_FactoryArray.push_back(&factory);
}
