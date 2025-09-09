import SwiftUI

struct ContentView: View {
    @StateObject private var audioManager = AudioManager()
    @StateObject private var sstv = SSTVProcessor()
    @StateObject private var settings = AppSettings()
    
    var body: some View {
        HSplitView {
            // Left Column - 468pt width (65%)
            VStack(spacing: 16) {
                FunctionButtonBank(selection: $sstv.currentMode)
                    .frame(height: 52)
                
                VFDDisplay(
                    spectrumData: audioManager.spectrumData,
                    imageData: sstv.imageData,
                    theme: settings.displayTheme,
                    mode: sstv.currentMode
                )
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                
                ManualAdjustmentPanel(
                    skew: $sstv.skewAdjustment,
                    offset: $sstv.offsetAdjustment
                )
                .frame(height: 64)
            }
            .frame(width: 468)
            
            // Right Column - 234pt width (35%)
            VStack(spacing: 16) {
                AudioLevelMeter(level: audioManager.audioLevel)
                    .frame(height: 48)
                
                SpectrumAnalyzer(data: audioManager.spectrumData)
                    .frame(height: 80)
                
                ModeSelector(
                    selectedMode: $sstv.selectedMode,
                    autoMode: $sstv.autoMode
                )
                .frame(height: 120)
                
                StatusPanel(
                    status: sstv.status,
                    device: audioManager.currentDevice
                )
                .frame(maxHeight: .infinity)
            }
            .frame(width: 234)
        }
        .frame(width: 720, height: 480)
        .background(ChassisBackground(theme: settings.chassisTheme))
        .disabled(false) // Prevent window resizing
        .onAppear {
            setupApplication()
        }
    }
    
    private func setupApplication() {
        // Initialize audio system
        audioManager.startAudioCapture()
        
        // Start Python bridge
        sstv.initializePythonBridge()
        
        // Connect audio to SSTV processor
        audioManager.dataHandler = { audioData in
            sstv.processAudioData(audioData)
        }
    }
}

// MARK: - Placeholder Components
// These will be implemented in separate files

struct FunctionButtonBank: View {
    @Binding var selection: SSTVMode
    
    var body: some View {
        HStack(spacing: 4) {
            ForEach(SSTVMode.allCases, id: \.self) { mode in
                FunctionButton(
                    title: mode.displayName,
                    isActive: selection == mode,
                    action: { selection = mode }
                )
            }
        }
        .padding(8)
        .background(Color.black.opacity(0.8))
        .cornerRadius(4)
    }
}

struct FunctionButton: View {
    let title: String
    let isActive: Bool
    let action: () -> Void
    
    var body: some View {
        Button(action: action) {
            VStack(spacing: 2) {
                Text(title)
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundColor(isActive ? .green : .gray)
                
                Circle()
                    .fill(isActive ? Color.green : Color.gray)
                    .frame(width: 6, height: 6)
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, 8)
            .background(
                RoundedRectangle(cornerRadius: 4)
                    .fill(isActive ? Color.black : Color.gray.opacity(0.3))
                    .shadow(color: .black, radius: isActive ? 0 : 2, x: 0, y: isActive ? 0 : 2)
            )
        }
        .buttonStyle(.plain)
    }
}

struct VFDDisplay: View {
    let spectrumData: [Float]
    let imageData: Data?
    let theme: DisplayTheme
    let mode: SSTVMode
    
    var body: some View {
        ZStack {
            // VFD Background
            Rectangle()
                .fill(Color.black)
                .overlay(
                    // Scan lines effect
                    VStack(spacing: 0) {
                        ForEach(0..<120, id: \.self) { _ in
                            Rectangle()
                                .fill(Color.green.opacity(0.05))
                                .frame(height: 1)
                            Rectangle()
                                .fill(Color.clear)
                                .frame(height: 3)
                        }
                    }
                )
            
            if let imageData = imageData {
                // Display decoded image
                Image(data: imageData)?
                    .resizable()
                    .aspectRatio(contentMode: .fit)
            } else {
                // Spectrum analyzer
                SpectrumVisualization(data: spectrumData, theme: theme)
            }
            
            // Status overlay
            VStack {
                Spacer()
                HStack {
                    Text("LISTENING - \(mode.displayName)")
                        .font(.system(size: 12, family: .monospaced))
                        .foregroundColor(theme.color)
                    Spacer()
                }
                .padding()
            }
        }
        .border(Color.gray, width: 2)
    }
}

struct SpectrumVisualization: View {
    let data: [Float]
    let theme: DisplayTheme
    
    var body: some View {
        GeometryReader { geometry in
            Path { path in
                guard !data.isEmpty else { return }
                
                let width = geometry.size.width
                let height = geometry.size.height
                let stepX = width / CGFloat(data.count)
                
                path.move(to: CGPoint(x: 0, y: height))
                
                for (index, value) in data.enumerated() {
                    let x = CGFloat(index) * stepX
                    let y = height - (CGFloat(value) * height)
                    path.addLine(to: CGPoint(x: x, y: y))
                }
                
                path.addLine(to: CGPoint(x: width, y: height))
                path.closeSubpath()
            }
            .fill(
                LinearGradient(
                    colors: [theme.color.opacity(0.8), theme.color.opacity(0.2)],
                    startPoint: .top,
                    endPoint: .bottom
                )
            )
        }
    }
}

struct AudioLevelMeter: View {
    let level: Float
    
    var body: some View {
        HStack(spacing: 2) {
            ForEach(0..<20, id: \.self) { index in
                Rectangle()
                    .fill(meterColor(for: index, level: level))
                    .frame(width: 8)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color.black)
        .border(Color.gray, width: 1)
    }
    
    private func meterColor(for index: Int, level: Float) -> Color {
        let threshold = Float(index) / 20.0
        
        if level > threshold {
            switch index {
            case 0..<14: return .green
            case 14..<18: return .yellow
            default: return .red
            }
        }
        return Color.black
    }
}

struct SpectrumAnalyzer: View {
    let data: [Float]
    
    var body: some View {
        // Simplified spectrum display
        Text("SPECTRUM")
            .font(.system(size: 12, family: .monospaced))
            .foregroundColor(.green)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(Color.black)
            .border(Color.gray, width: 1)
    }
}

struct ModeSelector: View {
    @Binding var selectedMode: String
    @Binding var autoMode: Bool
    
    var body: some View {
        VStack {
            Toggle("Auto Mode", isOn: $autoMode)
                .toggleStyle(.switch)
            
            Picker("Mode", selection: $selectedMode) {
                Text("Scottie S1").tag("ScottieS1")
                Text("Scottie S2").tag("ScottieS2")
                Text("Martin M1").tag("MartinM1")
                Text("Martin M2").tag("MartinM2")
                Text("Robot 36").tag("Robot36")
            }
            .pickerStyle(.menu)
            .disabled(autoMode)
        }
        .padding()
        .background(Color.gray.opacity(0.2))
        .cornerRadius(8)
    }
}

struct ManualAdjustmentPanel: View {
    @Binding var skew: Double
    @Binding var offset: Double
    
    var body: some View {
        HStack {
            VStack {
                Text("SKEW")
                    .font(.system(size: 10, family: .monospaced))
                Slider(value: $skew, in: -10...10)
                    .frame(width: 100)
            }
            
            Spacer()
            
            VStack {
                Text("OFFSET")
                    .font(.system(size: 10, family: .monospaced))
                Slider(value: $offset, in: -100...100)
                    .frame(width: 100)
            }
        }
        .padding()
        .background(Color.black.opacity(0.8))
        .cornerRadius(4)
    }
}

struct StatusPanel: View {
    let status: String
    let device: String
    
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("STATUS")
                    .font(.system(size: 10, family: .monospaced, weight: .bold))
                    .foregroundColor(.green)
                Spacer()
            }
            
            Text(status)
                .font(.system(size: 12, family: .monospaced))
                .foregroundColor(.green)
                .lineLimit(nil)
            
            Spacer()
            
            Text("DEVICE: \(device)")
                .font(.system(size: 10, family: .monospaced))
                .foregroundColor(.gray)
        }
        .padding()
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .background(Color.black.opacity(0.8))
        .cornerRadius(4)
    }
}

struct ChassisBackground: View {
    let theme: ChassisTheme
    
    var body: some View {
        Rectangle()
            .fill(
                LinearGradient(
                    colors: theme.gradientColors,
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                )
            )
    }
}

// MARK: - Preview
#Preview {
    ContentView()
        .frame(width: 720, height: 480)
}