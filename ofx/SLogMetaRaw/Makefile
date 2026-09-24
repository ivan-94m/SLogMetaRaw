# S-Log MetaRaw OpenFX plugins for DaVinci Resolve (macOS, Metal + CPU).
#   make            build SLogMetaRaw.ofx.bundle (universal arm64 + x86_64, ad-hoc signed)
#   make test-bins  build the test binaries with the same flags as the shipped plugin
#   make install    copy the bundle to /Library/OFX/Plugins (needs sudo)
SDK ?= /Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/OpenFX
# make cannot use paths with spaces in rules: build against a symlink to the SDK
SDKLINK = .ofxsdk
_ := $(shell ln -sfn "$(SDK)" $(SDKLINK))
SUPPORT = $(SDKLINK)/Support/Library

RELEASE := $(shell sed -n "s/^__version__ = '\([0-9]*\.[0-9]*\.[0-9]*\)'$$/\1/p" ../../slogmetaraw/__init__.py)
ifeq ($(RELEASE),)
$(error versione non trovata in slogmetaraw/__init__.py)
endif

ARCH_FLAGS = -arch arm64 -arch x86_64 -mmacosx-version-min=12.0
# -ffp-contract=off: the arm64 slice would fuse a*b+c and x86_64 would not; parity needs neither.
CXXFLAGS = -std=c++17 -O2 -fvisibility=hidden -ffp-contract=off $(ARCH_FLAGS) -MMD -MP \
           -I$(SDKLINK)/OpenFX-1.4/include -I$(SDKLINK)/Support/include -I.
OBJCFLAGS = $(CXXFLAGS) -fobjc-arc
LDFLAGS = -bundle -fvisibility=hidden $(ARCH_FLAGS) -framework Metal -framework Foundation -framework CoreFoundation

BUNDLE = SLogMetaRaw.ofx.bundle
BUILD = build
RESOURCES = com.slogmetaraw.SLogMetaRaw.png com.slogmetaraw.SLogMetaRawDetail.png fc_exposure.png fc_temperature.png fc_tint.png \
            fc_zones.png view_gain.png view_base.png
SUPPORT_SRCS = ofxsCore ofxsImageEffect ofxsInteract ofxsLog ofxsMultiThread ofxsParams ofxsProperty ofxsPropertyValidation
CPP_SRCS = $(wildcard src/*.cpp src/common/*.cpp src/develop/*.cpp src/detail/*.cpp)
MM_SRCS = $(wildcard metal/*.mm)
OBJS = $(CPP_SRCS:%.cpp=$(BUILD)/%.o) $(MM_SRCS:%.mm=$(BUILD)/%.o) $(SUPPORT_SRCS:%=$(BUILD)/support/%.o)
GEN = gen/DevelopMath.h gen/MetalSource.inc gen/GamutMatrices.h
MATH = $(wildcard math/*.h) $(wildcard metal/kernels/*.metal) ../../tools/build_math.py ../../tools/gamut_matrices.py

all: $(BUNDLE)

$(GEN): $(MATH)
	cd ../../tools && python3 build_math.py

# order-only: every object waits for the generated headers on a clean parallel build
$(BUILD)/%.o: %.cpp | $(GEN)
	@mkdir -p $(dir $@)
	$(CXX) -c $< -o $@ $(CXXFLAGS)

$(BUILD)/%.o: %.mm | $(GEN)
	@mkdir -p $(dir $@)
	$(CXX) -c $< -o $@ $(OBJCFLAGS)

$(BUILD)/support/%.o: $(SUPPORT)/%.cpp
	@mkdir -p $(dir $@)
	$(CXX) -c $< -o $@ $(CXXFLAGS)

$(BUILD)/src/common/Update.o: CXXFLAGS += -DSLOGMETARAW_RELEASE='"$(RELEASE)"'
$(BUILD)/src/common/Update.o: ../../slogmetaraw/__init__.py

$(BUILD)/SLogMetaRaw.ofx: $(OBJS)
	$(CXX) $^ -o $@ $(LDFLAGS)

$(BUILD)/Info.plist: Info.plist.in ../../slogmetaraw/__init__.py
	@mkdir -p $(BUILD)
	sed "s/@VERSION@/$(RELEASE)/g" $< > $@

$(BUNDLE): $(BUILD)/SLogMetaRaw.ofx $(BUILD)/Info.plist $(RESOURCES)
	rm -rf $(BUNDLE)
	mkdir -p $(BUNDLE)/Contents/MacOS $(BUNDLE)/Contents/Resources
	cp $(BUILD)/SLogMetaRaw.ofx $(BUNDLE)/Contents/MacOS/
	cp $(BUILD)/Info.plist $(BUNDLE)/Contents/
	cp $(RESOURCES) $(BUNDLE)/Contents/Resources/
	codesign --force --sign - $(BUNDLE)

# ---- test binaries (same flags; the tests run them, they never compile anything themselves)
TEST_BIN = $(BUILD)/tests
# the OFX-free part of src/common
TEST_OBJS_COMMON = $(filter $(addprefix $(BUILD)/src/common/,Files.o FlatJson.o Child.o Version.o),$(OBJS))
TESTS = $(TEST_BIN)/ofx_math_test $(TEST_BIN)/metal_test $(TEST_BIN)/host_test $(TEST_BIN)/common_test \
        $(TEST_BIN)/detail_test $(TEST_BIN)/detail_metal_test

test-bins: $(TESTS)

$(TEST_BIN)/ofx_math_test: ../../tests/ofx_math_test.cpp $(GEN)
	@mkdir -p $(TEST_BIN)
	$(CXX) $< -o $@ $(filter-out -MMD -MP,$(CXXFLAGS))

$(TEST_BIN)/metal_test: ../../tests/metal_test.mm $(BUILD)/metal/MetalContext.o $(BUILD)/metal/DevelopKernel.o $(GEN)
	@mkdir -p $(TEST_BIN)
	$(CXX) $< $(BUILD)/metal/MetalContext.o $(BUILD)/metal/DevelopKernel.o -o $@ \
	    $(filter-out -MMD -MP,$(OBJCFLAGS)) -framework Metal -framework Foundation

$(TEST_BIN)/host_test: ../../tests/host_test.cpp
	@mkdir -p $(TEST_BIN)
	$(CXX) $< -o $@ -std=c++17 -O1 -I$(SDKLINK)/OpenFX-1.4/include -I$(SDKLINK)/Support/include

$(TEST_BIN)/common_test: ../../tests/common_test.cpp $(TEST_OBJS_COMMON)
	@mkdir -p $(TEST_BIN)
	$(CXX) $< $(TEST_OBJS_COMMON) -o $@ $(filter-out -MMD -MP,$(CXXFLAGS)) -framework CoreFoundation

$(TEST_BIN)/detail_test: ../../tests/detail_test.cpp $(BUILD)/src/detail/DetailPasses.o
	@mkdir -p $(TEST_BIN)
	$(CXX) $< $(BUILD)/src/detail/DetailPasses.o -o $@ $(filter-out -MMD -MP,$(CXXFLAGS))

$(TEST_BIN)/detail_metal_test: ../../tests/detail_metal_test.mm $(BUILD)/src/detail/DetailPasses.o \
        $(BUILD)/metal/MetalContext.o $(BUILD)/metal/DetailKernels.o
	@mkdir -p $(TEST_BIN)
	$(CXX) $^ -o $@ $(filter-out -MMD -MP,$(OBJCFLAGS)) -framework Metal -framework Foundation

install: $(BUNDLE)
	rm -rf "/Library/OFX/Plugins/$(BUNDLE)"
	cp -R $(BUNDLE) /Library/OFX/Plugins/

clean:
	rm -rf $(BUILD) gen $(BUNDLE) $(SDKLINK)

.PHONY: all test-bins install clean

-include $(OBJS:.o=.d)
