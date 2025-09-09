# Testing & Validation - SSTV Project

## 🧪 TEST INFRASTRUCTURE

### Reference Test Files
**Location**: `core/shared/testing/reference/`

#### MMSSTV Reference (Gold Standard)
- **Files**: 5 audio files with corresponding expected images
- **Quality**: Perfect reference quality from MMSSTV software
- **Files**: 
  - `scottie_s1_bear_je3hht.wav` → `reference_mmsstv_scottie_s1_bear_je3hht_expected.jpg`
  - `scottie_s1_elk_forest.wav` → `reference_mmsstv_scottie_s1_elk_forest_expected.jpg`
  - `scottie_s1_operator_shack.wav` → `reference_mmsstv_scottie_s1_operator_shack_expected.jpg`
  - `scottie_s1_radio_desk.wav` → `reference_mmsstv_scottie_s1_radio_desk_expected.jpg`
  - `scottie_s1_winter_creek.wav` → `reference_mmsstv_scottie_s1_winter_creek_expected.jpg`

#### Essex Ham Test Signals
- **Files**: 4 real-world test signals
- **Modes**: Martin M2 and Scottie S2
- **Quality**: Real amateur radio transmissions
- **Files**:
  - `essexham_01_martin2.wav` / `essexham_02_martin2.wav`
  - `essexham_01_scottie2.wav` / `essexham_02_scottie2.wav`

#### ARISS ISS SSTV
- **Files**: 8 files from International Space Station
- **Quality**: Real space-to-ground SSTV transmissions
- **Use**: Real-world signal testing with noise/fading
- **Files**: `ariss-20201004-1445.wav`, `ariss-20201004-1620.wav`, etc.

#### Test Images for Encoding
- **Location**: `core/shared/testing/reference/new-images/`
- **Files**: `brr-brr-patapim.png`, `monkey-washing-cat.png`, `potatoes.png`
- **Use**: Round-trip testing (encode → decode validation)

## 🔬 TEST EXECUTION

### Test Scripts
**Location**: `core/shared/testing/scripts/`

#### Main Test Suite (`engine_test.js`)
- **Function**: Comprehensive decoder/encoder testing
- **Coverage**: All reference files, all SSTV modes
- **Output**: Results saved to `results/` directory
- **Validation**: Compare against expected reference images

#### Integration Testing (`integration_test.js`)
- **Function**: Full pipeline validation
- **Coverage**: End-to-end workflow testing
- **Components**: Audio → Decode → Enhancement → Gallery

#### Round-trip Testing (`roundtrip_test.js`)
- **Function**: Encode → Decode validation
- **Process**: Image → SSTV audio → Decoded image comparison
- **Modes**: All supported SSTV modes (Scottie, Martin, Robot)

### Test Results Storage
**Location**: `core/shared/testing/results/`

#### Decode Results (`decode/`)
- **Content**: Decoded images from test runs
- **Naming**: `{source_file}_decoded.png`
- **Validation**: Compare against reference images

#### Encode Results (`encode/`)
- **Content**: Generated SSTV audio files
- **Naming**: `{image}_{mode}.wav`
- **Validation**: Can be decoded back to original image

#### Round-trip Results (`roundtrip/`)
- **Structure**: Organized by SSTV mode (martin/, robot/, scottie/)
- **Content**: Full encode/decode cycle results
- **Validation**: Image quality comparison metrics

## ✅ VALIDATION CRITERIA

### Decoder Quality Standards
1. **Reference Match**: Near-perfect match to MMSSTV reference images
2. **Real Signal Handling**: Proper decode of Essex Ham/ARISS signals
3. **Progressive Rendering**: Image builds line by line during decode
4. **Mode Detection**: Automatic VIS code recognition

### Encoder Quality Standards  
1. **Mode Support**: All 6 modes (ScottieS1/S2/DX, MartinM1/M2, Robot36)
2. **Audio Quality**: Generated signals decode properly
3. **Timing Precision**: Correct timing for SSTV standards
4. **Progress Feedback**: Status updates during encoding

### Real-time Performance
1. **Audio Timing**: No dropouts during live capture
2. **Processing Speed**: Real-time decode without lag
3. **File Management**: Proper cleanup of temporary files
4. **UI Responsiveness**: Non-blocking long operations

### Cross-platform Validation
1. **macOS**: Primary development platform
2. **Windows**: Target deployment platform  
3. **Linux**: Community support platform
4. **Audio Devices**: Multiple input device compatibility

## 🐛 DEBUGGING APPROACHES

### Audio Pipeline Issues
- **Check**: CPAL permissions and device availability
- **Verify**: WAV file generation and format
- **Test**: Python subprocess argument passing

### Decode Quality Issues
- **Reference**: Compare against MMSSTV gold standard
- **Timing**: Verify audio sample rate precision
- **Mode**: Check VIS code detection accuracy

### Performance Issues
- **Profiling**: Monitor CPU usage during real-time processing
- **Memory**: Check for file cleanup and memory leaks
- **Threading**: Verify non-blocking audio capture

## 📊 TEST AUTOMATION

### Current Status
- **Manual Testing**: Run test scripts manually
- **Results Tracking**: JSON test reports generated
- **Reference Validation**: Visual comparison required

### Future Automation
- **CI Integration**: Automated test runs on commits
- **Image Comparison**: Automated quality metrics
- **Performance Benchmarks**: Timing and resource usage tracking