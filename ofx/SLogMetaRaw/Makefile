# SLogMetaRaw OpenFX plugin for DaVinci Resolve (macOS, Metal + CPU).
#   make            build SLogMetaRaw.ofx.bundle (universal arm64 + x86_64, ad-hoc signed)
#   make install    copy it to /Library/OFX/Plugins (needs sudo)
SDK ?= /Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/OpenFX
# make cannot use paths with spaces in rules: build against a symlink to the SDK
SDKLINK = .ofxsdk
_ := $(shell ln -sfn "$(SDK)" $(SDKLINK))
SUPPORT = $(SDKLINK)/Support/Library
ARCH_FLAGS = -arch arm64 -arch x86_64 -mmacosx-version-min=12.0
CXXFLAGS = -std=c++17 -O2 -fvisibility=hidden $(ARCH_FLAGS) -I$(SDKLINK)/OpenFX-1.4/include -I$(SDKLINK)/Support/include -I.
LDFLAGS = -bundle -fvisibility=hidden $(ARCH_FLAGS) -framework Metal -framework Foundation
SUPPORT_OBJS = ofxsCore.o ofxsImageEffect.o ofxsInteract.o ofxsLog.o ofxsMultiThread.o ofxsParams.o ofxsProperty.o ofxsPropertyValidation.o
BUNDLE = SLogMetaRaw.ofx.bundle

all: $(BUNDLE)

DevelopMath.h: DevelopMath.h.in ../../tools/build_math.py ../../tools/gamut_matrices.py
	cd ../../tools && python3 build_math.py

DevelopMathSource.inc: DevelopMath.h embed_source.py
	python3 embed_source.py DevelopMath.h $@

SLogMetaRaw.o: SLogMetaRaw.cpp SLogMetaRaw.h DevelopMath.h
	$(CXX) -c $< $(CXXFLAGS)

MetalKernel.o: MetalKernel.mm DevelopMath.h DevelopMathSource.inc
	$(CXX) -c $< $(CXXFLAGS)

%.o: $(SUPPORT)/%.cpp
	$(CXX) -c $< $(CXXFLAGS)

SLogMetaRaw.ofx: SLogMetaRaw.o MetalKernel.o $(SUPPORT_OBJS)
	$(CXX) $^ -o $@ $(LDFLAGS)

$(BUNDLE): SLogMetaRaw.ofx Info.plist com.slogmetaraw.SLogMetaRaw.png
	rm -rf $(BUNDLE)
	mkdir -p $(BUNDLE)/Contents/MacOS $(BUNDLE)/Contents/Resources
	cp SLogMetaRaw.ofx $(BUNDLE)/Contents/MacOS/
	cp Info.plist $(BUNDLE)/Contents/
	cp com.slogmetaraw.SLogMetaRaw.png $(BUNDLE)/Contents/Resources/
	codesign --force --sign - $(BUNDLE)

install: $(BUNDLE)
	rm -rf "/Library/OFX/Plugins/$(BUNDLE)"
	cp -R $(BUNDLE) /Library/OFX/Plugins/

clean:
	rm -f *.o *.ofx DevelopMathSource.inc $(SDKLINK)
	rm -rf $(BUNDLE)

.PHONY: all install clean
