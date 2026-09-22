// SPDX-License-Identifier: GPL-3.0-or-later
// A throwaway OpenFX host, just complete enough to put the built plugin through the
// actions DaVinci Resolve performs when it loads it and builds the node panel:
//   load -> describe -> describeInContext(filter) -> describeInContext(general) -> unload
// It exists because those actions used to take Resolve down with them: a duplicate
// parameter name crashed the panel, and a set of claimed names shared between the two
// describeInContext calls left the second context with no parameters at all.
// Usage: host_test <path to SLogMetaRaw.ofx>   (prints one line per context, then OK)
#include <dlfcn.h>
#include <pthread.h>

#include <cstdarg>
#include <cstdio>
#include <cstring>
#include <map>
#include <set>
#include <string>
#include <vector>

#include "ofxCore.h"
#include "ofxImageEffect.h"
#include "ofxMemory.h"
#include "ofxMessage.h"
#include "ofxMultiThread.h"
#include "ofxParam.h"
#include "ofxProperty.h"

// ---------------------------------------------------------------- property sets

struct PropSet
{
    std::map<std::string, std::vector<std::string> > strings;
    std::map<std::string, std::vector<int> > ints;
    std::map<std::string, std::vector<double> > doubles;
    std::map<std::string, std::vector<void*> > pointers;
};

static std::vector<PropSet*> g_allProps;

static PropSet* newProps()
{
    PropSet* p = new PropSet();
    g_allProps.push_back(p);
    return p;
}

template <typename T>
static void setAt(std::vector<T>& v, int index, const T& value)
{
    if (index < 0) return;
    if ((int)v.size() <= index) v.resize(index + 1);
    v[index] = value;
}

static PropSet* ps(OfxPropertySetHandle h) { return reinterpret_cast<PropSet*>(h); }
static OfxPropertySetHandle handleOf(PropSet* p) { return reinterpret_cast<OfxPropertySetHandle>(p); }

static OfxStatus propSetString(OfxPropertySetHandle h, const char* prop, int i, const char* v)
{
    setAt(ps(h)->strings[prop], i, std::string(v ? v : ""));
    return kOfxStatOK;
}
static OfxStatus propSetInt(OfxPropertySetHandle h, const char* prop, int i, int v)
{
    setAt(ps(h)->ints[prop], i, v);
    return kOfxStatOK;
}
static OfxStatus propSetDouble(OfxPropertySetHandle h, const char* prop, int i, double v)
{
    setAt(ps(h)->doubles[prop], i, v);
    return kOfxStatOK;
}
static OfxStatus propSetPointer(OfxPropertySetHandle h, const char* prop, int i, void* v)
{
    setAt(ps(h)->pointers[prop], i, v);
    return kOfxStatOK;
}
static OfxStatus propSetStringN(OfxPropertySetHandle h, const char* prop, int n, const char* const* v)
{
    for (int i = 0; i < n; ++i) propSetString(h, prop, i, v[i]);
    return kOfxStatOK;
}
static OfxStatus propSetIntN(OfxPropertySetHandle h, const char* prop, int n, const int* v)
{
    for (int i = 0; i < n; ++i) propSetInt(h, prop, i, v[i]);
    return kOfxStatOK;
}
static OfxStatus propSetDoubleN(OfxPropertySetHandle h, const char* prop, int n, const double* v)
{
    for (int i = 0; i < n; ++i) propSetDouble(h, prop, i, v[i]);
    return kOfxStatOK;
}
static OfxStatus propSetPointerN(OfxPropertySetHandle h, const char* prop, int n, void* const* v)
{
    for (int i = 0; i < n; ++i) propSetPointer(h, prop, i, v[i]);
    return kOfxStatOK;
}

// A lenient host: an unset property reads back empty rather than failing, so the plugin
// is exercised instead of the host's own gaps.
static OfxStatus propGetString(OfxPropertySetHandle h, const char* prop, int i, char** v)
{
    static std::string empty;
    std::vector<std::string>& s = ps(h)->strings[prop];
    *v = const_cast<char*>((i >= 0 && i < (int)s.size()) ? s[i].c_str() : empty.c_str());
    return kOfxStatOK;
}
static OfxStatus propGetInt(OfxPropertySetHandle h, const char* prop, int i, int* v)
{
    std::vector<int>& s = ps(h)->ints[prop];
    *v = (i >= 0 && i < (int)s.size()) ? s[i] : 0;
    return kOfxStatOK;
}
static OfxStatus propGetDouble(OfxPropertySetHandle h, const char* prop, int i, double* v)
{
    std::vector<double>& s = ps(h)->doubles[prop];
    *v = (i >= 0 && i < (int)s.size()) ? s[i] : 0.0;
    return kOfxStatOK;
}
static OfxStatus propGetPointer(OfxPropertySetHandle h, const char* prop, int i, void** v)
{
    std::vector<void*>& s = ps(h)->pointers[prop];
    *v = (i >= 0 && i < (int)s.size()) ? s[i] : NULL;
    return kOfxStatOK;
}
static OfxStatus propGetStringN(OfxPropertySetHandle h, const char* prop, int n, char** v)
{
    for (int i = 0; i < n; ++i) propGetString(h, prop, i, &v[i]);
    return kOfxStatOK;
}
static OfxStatus propGetIntN(OfxPropertySetHandle h, const char* prop, int n, int* v)
{
    for (int i = 0; i < n; ++i) propGetInt(h, prop, i, &v[i]);
    return kOfxStatOK;
}
static OfxStatus propGetDoubleN(OfxPropertySetHandle h, const char* prop, int n, double* v)
{
    for (int i = 0; i < n; ++i) propGetDouble(h, prop, i, &v[i]);
    return kOfxStatOK;
}
static OfxStatus propGetPointerN(OfxPropertySetHandle h, const char* prop, int n, void** v)
{
    for (int i = 0; i < n; ++i) propGetPointer(h, prop, i, &v[i]);
    return kOfxStatOK;
}
static OfxStatus propReset(OfxPropertySetHandle h, const char* prop)
{
    ps(h)->strings.erase(prop);
    ps(h)->ints.erase(prop);
    ps(h)->doubles.erase(prop);
    ps(h)->pointers.erase(prop);
    return kOfxStatOK;
}
static OfxStatus propGetDimension(OfxPropertySetHandle h, const char* prop, int* n)
{
    PropSet* p = ps(h);
    size_t d = p->strings[prop].size();
    if (!d) d = p->ints[prop].size();
    if (!d) d = p->doubles[prop].size();
    if (!d) d = p->pointers[prop].size();
    *n = (int)d;
    return kOfxStatOK;
}

static OfxPropertySuiteV1 g_propSuite = {
    propSetPointer, propSetString, propSetDouble, propSetInt,
    propSetPointerN, propSetStringN, propSetDoubleN, propSetIntN,
    propGetPointer, propGetString, propGetDouble, propGetInt,
    propGetPointerN, propGetStringN, propGetDoubleN, propGetIntN,
    propReset, propGetDimension
};

// ---------------------------------------------------------------- parameters

struct Param
{
    std::string name, type;
    PropSet* props;
    std::string stringValue;
    double doubleValue = 0.0;
    int intValue = 0;
};

struct ParamSet
{
    std::vector<Param*> params;
    std::map<std::string, Param*> byName;
    PropSet* props;
};

static std::vector<ParamSet*> g_allParamSets;
static bool g_duplicate = false;

static OfxStatus paramDefine(OfxParamSetHandle set, const char* type, const char* name, OfxPropertySetHandle* out)
{
    ParamSet* s = reinterpret_cast<ParamSet*>(set);
    if (s->byName.count(name)) {   // exactly what crashed DaVinci Resolve
        g_duplicate = true;
        fprintf(stderr, "DUPLICATO: parametro \"%s\" definito due volte\n", name);
        return kOfxStatErrExists;
    }
    Param* p = new Param();
    p->name = name;
    p->type = type;
    p->props = newProps();
    propSetString(handleOf(p->props), kOfxPropName, 0, name);
    propSetString(handleOf(p->props), kOfxParamPropType, 0, type);
    s->params.push_back(p);
    s->byName[name] = p;
    if (out) *out = handleOf(p->props);
    return kOfxStatOK;
}

static OfxStatus paramGetHandle(OfxParamSetHandle set, const char* name, OfxParamHandle* param, OfxPropertySetHandle* props)
{
    ParamSet* s = reinterpret_cast<ParamSet*>(set);
    std::map<std::string, Param*>::iterator it = s->byName.find(name);
    if (it == s->byName.end()) return kOfxStatErrUnknown;
    if (param) *param = reinterpret_cast<OfxParamHandle>(it->second);
    if (props) *props = handleOf(it->second->props);
    return kOfxStatOK;
}

static bool isIntLike(const std::string& type)
{
    return type == kOfxParamTypeInteger || type == kOfxParamTypeBoolean || type == kOfxParamTypeChoice;
}

// The host gives a new instance the defaults the plugin declared while describing.
static void applyDefaults(ParamSet* s)
{
    for (size_t i = 0; i < s->params.size(); ++i) {
        Param* p = s->params[i];
        OfxPropertySetHandle h = handleOf(p->props);
        if (p->type == kOfxParamTypeString) {
            char* v = NULL;
            propGetString(h, kOfxParamPropDefault, 0, &v);
            p->stringValue = v ? v : "";
        } else if (p->type == kOfxParamTypeDouble) {
            propGetDouble(h, kOfxParamPropDefault, 0, &p->doubleValue);
        } else if (isIntLike(p->type)) {
            propGetInt(h, kOfxParamPropDefault, 0, &p->intValue);
        }
    }
}

static OfxStatus paramGetValue(OfxParamHandle handle, ...)
{
    Param* p = reinterpret_cast<Param*>(handle);
    va_list ap;
    va_start(ap, handle);
    if (p->type == kOfxParamTypeString) *va_arg(ap, char**) = const_cast<char*>(p->stringValue.c_str());
    else if (p->type == kOfxParamTypeDouble) *va_arg(ap, double*) = p->doubleValue;
    else if (isIntLike(p->type)) *va_arg(ap, int*) = p->intValue;
    va_end(ap);
    return kOfxStatOK;
}

static OfxStatus paramGetValueAtTime(OfxParamHandle handle, OfxTime time, ...)
{
    Param* p = reinterpret_cast<Param*>(handle);
    va_list ap;
    va_start(ap, time);   // nothing animates in this host: the time is ignored
    if (p->type == kOfxParamTypeString) *va_arg(ap, char**) = const_cast<char*>(p->stringValue.c_str());
    else if (p->type == kOfxParamTypeDouble) *va_arg(ap, double*) = p->doubleValue;
    else if (isIntLike(p->type)) *va_arg(ap, int*) = p->intValue;
    va_end(ap);
    return kOfxStatOK;
}

static OfxStatus paramSetValue(OfxParamHandle handle, ...)
{
    Param* p = reinterpret_cast<Param*>(handle);
    va_list ap;
    va_start(ap, handle);
    if (p->type == kOfxParamTypeString) { const char* v = va_arg(ap, const char*); p->stringValue = v ? v : ""; }
    else if (p->type == kOfxParamTypeDouble) p->doubleValue = va_arg(ap, double);
    else if (isIntLike(p->type)) p->intValue = va_arg(ap, int);
    va_end(ap);
    return kOfxStatOK;
}

static OfxStatus paramSetGetPropertySet(OfxParamSetHandle set, OfxPropertySetHandle* props)
{
    *props = handleOf(reinterpret_cast<ParamSet*>(set)->props);
    return kOfxStatOK;
}

static OfxStatus paramGetPropertySet(OfxParamHandle param, OfxPropertySetHandle* props)
{
    *props = handleOf(reinterpret_cast<Param*>(param)->props);
    return kOfxStatOK;
}

static OfxParameterSuiteV1 g_paramSuite = {};   // the rest stays null: describe never calls it

// ---------------------------------------------------------------- image effect

struct Effect
{
    PropSet* props;
    ParamSet* params;
};

static OfxStatus effectGetPropertySet(OfxImageEffectHandle effect, OfxPropertySetHandle* out)
{
    *out = handleOf(reinterpret_cast<Effect*>(effect)->props);
    return kOfxStatOK;
}

static OfxStatus effectGetParamSet(OfxImageEffectHandle effect, OfxParamSetHandle* out)
{
    *out = reinterpret_cast<OfxParamSetHandle>(reinterpret_cast<Effect*>(effect)->params);
    return kOfxStatOK;
}

static std::map<std::string, PropSet*> g_clips;   // one property set per clip name

static OfxStatus clipDefine(OfxImageEffectHandle, const char* name, OfxPropertySetHandle* out)
{
    PropSet*& p = g_clips[name];
    if (!p) {
        p = newProps();
        propSetString(handleOf(p), kOfxPropName, 0, name);
    }
    if (out) *out = handleOf(p);
    return kOfxStatOK;
}

static OfxStatus clipGetHandle(OfxImageEffectHandle effect, const char* name,
                               OfxImageClipHandle* clip, OfxPropertySetHandle* props)
{
    OfxPropertySetHandle h = NULL;
    clipDefine(effect, name, &h);
    if (clip) *clip = reinterpret_cast<OfxImageClipHandle>(h);
    if (props) *props = h;
    return kOfxStatOK;
}

static OfxStatus clipGetPropertySet(OfxImageClipHandle clip, OfxPropertySetHandle* props)
{
    *props = reinterpret_cast<OfxPropertySetHandle>(clip);
    return kOfxStatOK;
}

static OfxImageEffectSuiteV1 g_effectSuite = {};

// ---------------------------------------------------------------- other suites

static void* memAlloc(void*, size_t bytes) { return malloc(bytes); }
static OfxStatus memoryAlloc(void* handle, size_t bytes, void** out)
{
    *out = memAlloc(handle, bytes);
    return *out ? kOfxStatOK : kOfxStatErrMemory;
}
static OfxStatus memoryFree(void* p) { free(p); return kOfxStatOK; }
static OfxMemorySuiteV1 g_memSuite = { memoryAlloc, memoryFree };

static OfxStatus mtRun(OfxThreadFunctionV1 fn, unsigned int, void* args) { fn(0, 1, args); return kOfxStatOK; }
static OfxStatus mtNumCPUs(unsigned int* n) { *n = 1; return kOfxStatOK; }
static OfxStatus mtIndex(unsigned int* n) { *n = 0; return kOfxStatOK; }
static int mtIsSpawned() { return 0; }
static OfxStatus mutexCreate(OfxMutexHandle* h, int)
{
    pthread_mutex_t* m = new pthread_mutex_t;
    pthread_mutex_init(m, NULL);
    *h = reinterpret_cast<OfxMutexHandle>(m);
    return kOfxStatOK;
}
static OfxStatus mutexDestroy(const OfxMutexHandle h)
{
    pthread_mutex_t* m = reinterpret_cast<pthread_mutex_t*>(h);
    pthread_mutex_destroy(m);
    delete m;
    return kOfxStatOK;
}
static OfxStatus mutexLock(const OfxMutexHandle h)
{
    pthread_mutex_lock(reinterpret_cast<pthread_mutex_t*>(h));
    return kOfxStatOK;
}
static OfxStatus mutexUnLock(const OfxMutexHandle h)
{
    pthread_mutex_unlock(reinterpret_cast<pthread_mutex_t*>(h));
    return kOfxStatOK;
}
static OfxStatus mutexTryLock(const OfxMutexHandle h)
{
    return pthread_mutex_trylock(reinterpret_cast<pthread_mutex_t*>(h)) == 0 ? kOfxStatOK : kOfxStatFailed;
}
static OfxMultiThreadSuiteV1 g_mtSuite = { mtRun, mtNumCPUs, mtIndex, mtIsSpawned,
                                           mutexCreate, mutexDestroy, mutexLock, mutexUnLock, mutexTryLock };

static OfxStatus messageV(void*, const char*, const char*, const char* format, va_list args)
{
    fprintf(stderr, "[plugin] ");
    vfprintf(stderr, format, args);
    fprintf(stderr, "\n");
    return kOfxStatOK;
}
static OfxStatus message(void* handle, const char* type, const char* id, const char* format, ...)
{
    va_list args;
    va_start(args, format);
    messageV(handle, type, id, format, args);
    va_end(args);
    return kOfxStatOK;
}
static OfxMessageSuiteV1 g_msgSuite = { message };

// ---------------------------------------------------------------- the host

static PropSet* g_hostProps = NULL;

static const void* fetchSuite(OfxPropertySetHandle, const char* name, int)
{
    if (!strcmp(name, kOfxPropertySuite)) return &g_propSuite;
    if (!strcmp(name, kOfxParameterSuite)) return &g_paramSuite;
    if (!strcmp(name, kOfxImageEffectSuite)) return &g_effectSuite;
    if (!strcmp(name, kOfxMemorySuite)) return &g_memSuite;
    if (!strcmp(name, kOfxMultiThreadSuite)) return &g_mtSuite;
    if (!strcmp(name, kOfxMessageSuite)) return &g_msgSuite;
    return NULL;   // the plugin must cope with a host that has nothing else to offer
}

static OfxHost g_host;

static void buildHost()
{
    g_hostProps = newProps();
    OfxPropertySetHandle h = handleOf(g_hostProps);
    propSetString(h, kOfxPropName, 0, "fake.host.for.tests");
    propSetString(h, kOfxPropLabel, 0, "S-Log MetaRaw test host");
    propSetString(h, kOfxPropAPIVersion, 0, "1");
    propSetInt(h, kOfxPropAPIVersion, 1, 4);
    propSetString(h, kOfxPropVersion, 0, "1");
    propSetInt(h, kOfxImageEffectHostPropIsBackground, 0, 0);
    propSetInt(h, kOfxImageEffectPropSupportsMultipleClipDepths, 0, 0);
    propSetInt(h, kOfxImageEffectPropSupportsMultipleClipPARs, 0, 0);
    propSetInt(h, kOfxImageEffectPropSupportsTiles, 0, 0);
    propSetInt(h, kOfxImageEffectPropSetableFrameRate, 0, 0);
    propSetInt(h, kOfxImageEffectPropSetableFielding, 0, 0);
    propSetInt(h, kOfxParamHostPropSupportsCustomInteract, 0, 0);
    propSetInt(h, kOfxParamHostPropSupportsStringAnimation, 0, 0);
    propSetInt(h, kOfxParamHostPropSupportsChoiceAnimation, 0, 0);
    propSetInt(h, kOfxParamHostPropSupportsBooleanAnimation, 0, 0);
    propSetInt(h, kOfxParamHostPropSupportsCustomAnimation, 0, 0);
    propSetInt(h, kOfxParamHostPropMaxParameters, 0, -1);
    propSetInt(h, kOfxParamHostPropMaxPages, 0, 1);
    propSetInt(h, kOfxParamHostPropPageRowColumnCount, 0, 30);
    propSetInt(h, kOfxParamHostPropPageRowColumnCount, 1, 1);
    g_paramSuite.paramDefine = paramDefine;
    g_paramSuite.paramGetHandle = paramGetHandle;
    g_paramSuite.paramGetPropertySet = paramGetPropertySet;
    g_paramSuite.paramSetGetPropertySet = paramSetGetPropertySet;
    g_paramSuite.paramGetValue = paramGetValue;
    g_paramSuite.paramGetValueAtTime = paramGetValueAtTime;
    g_paramSuite.paramSetValue = paramSetValue;
    g_effectSuite.getPropertySet = effectGetPropertySet;
    g_effectSuite.getParamSet = effectGetParamSet;
    g_effectSuite.clipDefine = clipDefine;
    g_effectSuite.clipGetHandle = clipGetHandle;
    g_effectSuite.clipGetPropertySet = clipGetPropertySet;
    g_host.host = h;
    g_host.fetchSuite = fetchSuite;
}

// ---------------------------------------------------------------- the run

static int describeContext(OfxPlugin* plugin, const char* context, size_t* paramCount)
{
    Effect effect;
    effect.props = newProps();
    effect.params = new ParamSet();
    effect.params->props = newProps();
    g_allParamSets.push_back(effect.params);
    propSetString(handleOf(effect.props), kOfxImageEffectPropContext, 0, context);
    fprintf(stderr, "[host] describeInContext %s\n", context);
    OfxStatus st = plugin->mainEntry(kOfxImageEffectActionDescribeInContext,
                                     reinterpret_cast<OfxImageEffectHandle>(&effect),
                                     handleOf(effect.props), NULL);
    *paramCount = effect.params->params.size();
    if (st != kOfxStatOK) {
        fprintf(stderr, "describeInContext(%s) ha restituito %d\n", context, st);
        return 0;
    }
    return 1;
}

// Build an instance the way Resolve does: describe the context, hand the parameters
// their defaults, then create the instance and let the plugin configure itself.
static int createInstance(OfxPlugin* plugin, const char* clipPath, int* failed)
{
    Effect effect;
    effect.props = newProps();
    effect.params = new ParamSet();
    effect.params->props = newProps();
    g_allParamSets.push_back(effect.params);
    OfxPropertySetHandle eh = handleOf(effect.props);
    propSetString(eh, kOfxImageEffectPropContext, 0, kOfxImageEffectContextFilter);
    if (clipPath) propSetString(eh, "OfxImageEffectPropSrcFilePath", 0, clipPath);

    OfxImageEffectHandle handle = reinterpret_cast<OfxImageEffectHandle>(&effect);
    if (plugin->mainEntry(kOfxImageEffectActionDescribeInContext, handle, eh, NULL) != kOfxStatOK) {
        fprintf(stderr, "FALLITO: describeInContext prima dell'istanza\n");
        *failed = 1;
        return 0;
    }
    applyDefaults(effect.params);

    OfxStatus st = plugin->mainEntry(kOfxActionCreateInstance, handle, NULL, NULL);
    if (st != kOfxStatOK) {
        fprintf(stderr, "FALLITO: createInstance ha restituito %d\n", st);
        *failed = 1;
        return 0;
    }

    // "Rileggi metadata": the action Resolve sends when the button is pressed
    PropSet* changed = newProps();
    propSetString(handleOf(changed), kOfxPropChangeReason, 0, kOfxChangeUserEdited);
    propSetString(handleOf(changed), kOfxPropName, 0, "reload");
    propSetString(handleOf(changed), kOfxPropType, 0, kOfxTypeParameter);
    propSetDouble(handleOf(changed), kOfxPropTime, 0, 0.0);
    st = plugin->mainEntry(kOfxActionInstanceChanged, handle, handleOf(changed), NULL);
    if (st != kOfxStatOK && st != kOfxStatReplyDefault) {
        fprintf(stderr, "FALLITO: instanceChanged(reload) ha restituito %d\n", st);
        *failed = 1;
    }

    for (size_t i = 0; i < effect.params->params.size(); ++i) {
        Param* pa = effect.params->params[i];
        if (pa->name == "camera" || pa->name == "status")
            printf("%s=%s\n", pa->name.c_str(), pa->stringValue.c_str());
        else if (pa->name == "colorTemp" || pa->name == "exposure" || pa->name == "tint")
            printf("%s=%g\n", pa->name.c_str(), pa->doubleValue);
        else if (pa->name == "metaValid" || pa->name == "settingsVersion"
                 || pa->name == "dataLevel" || pa->name == "levelRequired" || pa->name == "levelHost")
            printf("%s=%d\n", pa->name.c_str(), pa->intValue);
        else if (pa->name == "levelInfo")
            printf("%s=%s\n", pa->name.c_str(), pa->stringValue.c_str());
    }

    plugin->mainEntry(kOfxActionDestroyInstance, handle, NULL, NULL);
    return 1;
}

int main(int argc, char** argv)
{
    setvbuf(stdout, NULL, _IONBF, 0);   // keep the trace when the run ends badly
    if (argc < 2) {
        fprintf(stderr, "uso: host_test <SLogMetaRaw.ofx>\n");
        return 2;
    }
    void* lib = dlopen(argv[1], RTLD_NOW | RTLD_LOCAL);
    if (!lib) {
        fprintf(stderr, "dlopen fallito: %s\n", dlerror());
        return 1;
    }
    typedef int (*GetNumberFn)(void);
    typedef OfxPlugin* (*GetPluginFn)(int);
    GetNumberFn getNumber = (GetNumberFn)dlsym(lib, "OfxGetNumberOfPlugins");
    GetPluginFn getPlugin = (GetPluginFn)dlsym(lib, "OfxGetPlugin");
    if (!getNumber || !getPlugin) {
        fprintf(stderr, "il bundle non esporta i simboli OpenFX\n");
        return 1;
    }
    if (getNumber() < 1) {
        fprintf(stderr, "nessun plugin nel bundle\n");
        return 1;
    }
    OfxPlugin* plugin = getPlugin(0);
    printf("plugin: %s v%d.%d\n", plugin->pluginIdentifier, plugin->pluginVersionMajor, plugin->pluginVersionMinor);

    fprintf(stderr, "[host] buildHost\n");
    buildHost();
    fprintf(stderr, "[host] setHost\n");
    plugin->setHost(&g_host);
    fprintf(stderr, "[host] load\n");
    if (plugin->mainEntry(kOfxActionLoad, NULL, NULL, NULL) != kOfxStatOK) {
        fprintf(stderr, "azione load fallita\n");
        return 1;
    }

    Effect described;
    described.props = newProps();
    described.params = new ParamSet();
    described.params->props = newProps();
    g_allParamSets.push_back(described.params);
    fprintf(stderr, "[host] describe\n");
    if (plugin->mainEntry(kOfxActionDescribe, reinterpret_cast<OfxImageEffectHandle>(&described),
                          NULL, NULL) != kOfxStatOK) {
        fprintf(stderr, "azione describe fallita\n");
        return 1;
    }

    // Resolve describes the plugin once per context it supports.
    size_t filterParams = 0, generalParams = 0;
    if (!describeContext(plugin, kOfxImageEffectContextFilter, &filterParams)) return 1;
    printf("contesto filter:  %zu parametri\n", filterParams);
    if (!describeContext(plugin, kOfxImageEffectContextGeneral, &generalParams)) return 1;
    printf("contesto general: %zu parametri\n", generalParams);

    // a live node, with the clip given on the command line when there is one
    int failed = 0;
    fprintf(stderr, "[host] createInstance\n");
    createInstance(plugin, argc > 2 ? argv[2] : NULL, &failed);

    plugin->mainEntry(kOfxActionUnload, NULL, NULL, NULL);
    if (failed) return 1;

    if (g_duplicate) {
        fprintf(stderr, "FALLITO: nomi di parametri duplicati\n");
        return 1;
    }
    if (filterParams < 20) {
        fprintf(stderr, "FALLITO: il contesto filter ha solo %zu parametri\n", filterParams);
        return 1;
    }
    if (filterParams != generalParams) {
        fprintf(stderr, "FALLITO: i due contesti hanno %zu e %zu parametri\n", filterParams, generalParams);
        return 1;
    }
    printf("OK\n");
    return 0;
}
