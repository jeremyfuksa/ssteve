# A Technical Analysis of Spectrogram and Waterfall Visualizations in Slow-Scan Television Applications

## Section 1: Deconstruction of the Analog SSTV Signal Protocol

To comprehend the function of spectrogram and waterfall displays in
Slow-Scan Television (SSTV) applications, one must first deconstruct the
underlying signal protocol. SSTV is fundamentally a method for
transmitting static images over a narrow audio bandwidth, typically 3
kHz, making it suitable for amateur radio voice channels.^1^ Unlike
modern digital image formats, the SSTV signal is a structured,
time-domain analog audio stream where image information is directly
encoded as frequency. This protocol, conceived in the 1950s and refined
over decades, represents a fascinating hybrid of analog data
representation and digital metadata signaling, a structure that dictates
the entire software decoding process.^1^

### 1.1 The Anatomy of an SSTV Transmission

An SSTV transmission is not a monolithic audio stream but a precisely
framed packet of information. Each transmission begins with a
standardized header sequence designed to alert the receiving software,
facilitate synchronization, and identify the specific transmission
format being used. This structure ensures a degree of interoperability
and automation essential for modern software-based decoders.^1^

#### Calibration Header

The transmission commences with a calibration header. This sequence
serves as a preamble, signaling the start of an image and allowing the
receiver\'s automatic gain control (AGC) to stabilize. The standard
header consists of a 300-millisecond leader tone at 1,900 Hz, a brief
10-millisecond break at 1,200 Hz, and another 300-millisecond leader
tone at 1,900 Hz.^1^ This distinct pattern is the \"wake-up call\" that
prompts a listening application to begin its decoding process.

#### Vertical Interval Signaling (VIS) Code

Following the leader tones, the most critical piece of metadata is
transmitted: the Vertical Interval Signaling (VIS) code. The VIS code is
a digital packet embedded within the analog signal stream that
unambiguously identifies the SSTV mode being used.^1^ This is a crucial
innovation that allows a decoder to automatically configure itself for
the correct image dimensions, color encoding, and timing without user
intervention---a feature central to the user experience of modern SSTV
apps.^4^

The VIS code is an 8-bit digital word encoded using frequency-shift
keying (FSK). It begins with a 30-millisecond start bit at 1,200 Hz,
followed by seven data bits and one even parity bit, each 30
milliseconds long. A logic \'1\' is represented by a frequency of 1,100
Hz, and a logic \'0\' is represented by 1,300 Hz. The packet concludes
with a 30-millisecond stop bit at 1,200 Hz.^1^ For example, a VIS code
of 60 (decimal) identifies the Scottie S1 mode, while a code of 44
identifies Martin M1.^1^ This hybrid nature---a digital FSK packet
prepended to an analog FM transmission---necessitates that a modern
decoder possess two distinct demodulation capabilities: one for the
digital header and another for the analog image data.

#### Synchronization Pulses

The image itself is constructed line by line, from top to bottom. To
ensure proper alignment of each horizontal line, the transmission for
each line is preceded by a horizontal synchronization (sync) pulse. In
most common modes, this is a 1,200 Hz tone with a duration of 5
milliseconds.^1^ This pulse serves as the fundamental timing reference
for the image reconstruction. The decoder locks onto this repeating
pulse to determine the precise moment to begin sampling the frequency
data for a new scanline. Without reliable detection of these sync
pulses, the received image would appear slanted or completely garbled.

### 1.2 Frequency-Modulated Data Encoding

The core principle of SSTV is the direct and continuous mapping of image
brightness to audio frequency. This is a form of analog frequency
modulation (FM) operating within the constrained 3 kHz audio
passband.^1^

#### Luminance and Chrominance Mapping

The brightness, or luminance, of a given point in the image is
represented by a specific audio frequency. The standard frequency range
for this data is 1,500 Hz to 2,300 Hz. A tone of 1,500 Hz corresponds to
black (minimum intensity), while a tone of 2,300 Hz corresponds to white
(maximum intensity).^1^ Any frequency between these two points
represents an intermediate shade of gray. The modulation is analog,
meaning there is a theoretically infinite number of shades possible,
although in practice this is limited by the resolution of the frequency
analysis in the decoder.

#### Color Transmission

To transmit color images, SSTV modes send the brightness information for
each primary color component sequentially. Most modes, such as the
popular Martin and Scottie families, use an RGB (Red, Green, Blue) color
model. For a single horizontal scanline, the system transmits the
luminance data for the red component, followed by the green component,
and then the blue component.^1^ Some other modes utilize a YC color
model, where luminance (Y) and two chrominance channels (R-Y and B-Y)
are sent separately, a method more analogous to analog broadcast
television standards.^1^ The specific order and timing of these color
component scans are strictly defined by the SSTV mode specified in the
VIS code. This sequential transmission means that the audio signal is
effectively a one-dimensional, time-unrolled representation of the
two-dimensional, multi-channel color image. A spectrogram of this
signal, therefore, does not merely analyze the signal; it visually
presents the raw image data itself, laid out sequentially over time.

### 1.3 A Taxonomy of SSTV Modes

The term \"SSTV\" does not refer to a single protocol but rather a
family of over 50 distinct modes, each offering a different compromise
between image resolution, color depth, noise immunity, and transmission
time.^1^ This diversity is precisely why the VIS code is indispensable
for automated decoding. The most commonly encountered modes belong to
several key families.

- **Robot:** Developed by Robot Research Corporation, these modes are
  historically significant as they were associated with some of the
  first commercially available SSTV hardware. Robot 36 and Robot 72 are
  popular color modes still in wide use today.^5^

- **Martin:** Developed by Martin Emmerson (G3OQD), this family of modes
  is particularly popular in Europe. Martin M1 is a widely used
  standard, known for its good balance of quality and transmission
  time.^1^

- **Scottie:** Developed by Eddie Murphy (GM3BSC), the Scottie modes are
  prevalent in the USA and Japan. Scottie S1 is a direct counterpart to
  Martin M1.^1^

- **PD (Paskie Digital) Modes:** This family, developed by Paul Turner
  (G4IJE), offers higher resolutions and improved color performance but
  at the cost of significantly longer transmission times. The
  International Space Station (ISS) frequently uses the PD-120 mode for
  its image downlinks, making it a popular target for hobbyists.^5^

The choice of mode has a profound impact on the final image. A simple
black-and-white mode might transmit in as little as 8 seconds, while a
high-resolution PD mode can take several minutes.^1^ This wide variation
underscores the importance of the decoder\'s ability to first correctly
identify the mode via the VIS code before attempting to reconstruct the
image.

Table 1 provides a comparative analysis of several representative SSTV
modes, consolidating key parameters from various sources into a single
reference. This table highlights the quantitative differences that a
developer must account for when implementing a multi-mode decoder.

Table 1: Comparative Analysis of Common SSTV Modes

\| Mode Name \| Family \| Resolution \| Color Model \| Transmission Time
(s) \| VIS Code (Decimal) \|

\| :\-\-- \| :\-\-- \| :\-\-- \| :\-\-- \| :\-\-- \| :\-\-- \|

\| Robot 8 B&W \| Robot \| 160x120 \| Grayscale \| 8 \| 2 \|

\| Robot 36 \| Robot \| 320x240 \| YC \| 36 \| 8 \|

\| Robot 72 \| Robot \| 320x240 \| YC \| 72 \| 12 \|

\| Scottie S1 \| Scottie \| 320x256 \| RGB \| 110 \| 60 \|

\| Scottie S2 \| Scottie \| 320x256 \| RGB \| 71 \| 58 \|

\| Martin M1 \| Martin \| 320x256 \| RGB \| 114 \| 44 \|

\| Martin M2 \| Martin \| 320x256 \| RGB \| 58 \| 46 \|

\| PD120 \| PD \| 640x496 \| YC \| 125 \| 93 \|

Data compiled from.^1^

## Section 2: The Spectrogram and Waterfall: A Primer on Time-Frequency Representation

Having established the structure of the SSTV signal, the next step is to
understand the primary tool used to visualize it: the spectrogram. This
section transitions from the specific domain of amateur radio to the
general principles of Digital Signal Processing (DSP), providing the
conceptual and mathematical foundation required to understand how a
time-varying audio signal is transformed into a rich, two-dimensional
visualization.

### 2.1 Defining the Visualizations: Spectrogram vs. Waterfall

A **spectrogram** is a powerful visualization that displays the spectral
content of a signal as it evolves over time. It is a two-dimensional
graph where the horizontal axis typically represents time, the vertical
axis represents frequency, and a third dimension---the amplitude or
power of the signal at each time-frequency point---is represented by
color or intensity.^9^ In this representation, silence appears as a dark
background, while loud sounds at specific frequencies appear as bright
regions. This allows an analyst to \"see\" sound, identifying components
like harmonics, noise, and transient events that are difficult to
discern in a simple waveform view.^9^

A **waterfall display** is a specific and dynamic presentation style of
a spectrogram, commonly used in real-time signal analysis applications
like radio receivers and audio analyzers.^13^ Its defining
characteristic is the continuous, scrolling motion. New spectral data
appears at one edge of the display (e.g., the top) and progressively
scrolls towards the opposite edge, with older data eventually
disappearing.^15^ This creates a flowing visual effect reminiscent of a
waterfall, providing an intuitive view of how the frequency spectrum is
changing in the present moment. While the terms are sometimes used
interchangeably, \"waterfall\" specifically implies this real-time,
scrolling behavior.^16^ Some waterfall plots also employ a pseudo-3D
perspective, where amplitude is shown as the height of peaks rather than
by color, creating a \"mountain range\" effect.^16^

Both spectrograms and waterfalls belong to a broader class of analytical
tools known as **Time-Frequency Representations (TFRs)** or
**Time-Frequency Distributions (TFDs)**. These methods aim to overcome
the primary limitation of the standard Fourier Transform by analyzing a
signal in both the time and frequency domains simultaneously.^20^

### 2.2 The Mathematical Engine: The Short-Time Fourier Transform (STFT)

The mathematical engine that powers nearly all modern spectrograms is
the **Short-Time Fourier Transform (STFT)**.^22^ A standard Fourier
Transform provides a comprehensive view of a signal\'s frequency content
but in doing so, it discards all information about

*when* those frequencies occurred. The STFT resolves this by analyzing
the frequency content of small, localized sections of the signal over
time.^22^

The STFT process can be broken down into three main steps:

1.  **Windowing:** The long input signal is segmented into shorter,
    often overlapping, chunks. Each chunk is then multiplied by a
    \"window function\" (such as a Hann, Hamming, or Blackman window).
    This function tapers the signal to zero at the beginning and end of
    the segment, a critical step that minimizes a form of digital
    artifact known as spectral leakage, where energy from a strong
    frequency bin \"leaks\" into adjacent bins.^25^

2.  **FFT Computation:** The **Fast Fourier Transform (FFT)**---an
    algorithm that computes the Discrete Fourier Transform (DFT) with
    high efficiency---is applied to each windowed segment.^24^ The
    output of the FFT for each segment is a set of complex numbers,
    representing the magnitude and phase of the various frequency
    components present within that short time slice.

3.  **Aggregation:** The resulting spectra from all the time segments
    are collected and arranged side-by-side to form a two-dimensional
    matrix. The magnitude (or more commonly, the magnitude squared) of
    this complex matrix is then plotted. This final plot of power versus
    frequency and time is the spectrogram.^22^ The squared magnitude of
    the STFT is formally known as the\
    **Power Spectral Density (PSD)** of the signal.^11^

### 2.3 The Time-Frequency Resolution Trade-off

A fundamental property of the STFT, derived from the Heisenberg
Uncertainty Principle as it applies to signals, is that one cannot
achieve arbitrarily high resolution in both the time and frequency
domains simultaneously.^22^ The choice of STFT parameters forces a
trade-off, making the spectrogram a configurable \"microscope\" that can
be tuned to focus on either temporal or spectral details, but not both
at once.

- **FFT Size / Window Length (NFFT):** This parameter defines the
  duration of the time slice analyzed in each FFT.

  - A **wide window** (a large NFFT value) analyzes a longer portion of
    the signal. This provides excellent **frequency resolution**,
    allowing the spectrogram to distinguish between frequencies that are
    very close together. However, it comes at the cost of poor **time
    resolution**, as any event happening within that long window gets
    \"smeared\" out in time.^9^

  - A **narrow window** (a small NFFT value) analyzes a very short time
    slice. This provides excellent **time resolution**, making it
    possible to pinpoint the exact moment an event occurs. The trade-off
    is poor **frequency resolution**, where distinct but nearby
    frequencies are blurred together into a single, wider peak.^9^

- **Window Function:** The mathematical shape of the window function
  (e.g., Rectangular, Hann, Blackman) influences the trade-off between
  the width of a frequency peak and the amount of spectral leakage. A
  simple rectangular window provides the narrowest possible peak but
  suffers from high leakage. Tapered windows like Hann or Blackman
  produce a slightly wider main peak but significantly reduce leakage,
  generally resulting in a cleaner and more accurate spectrum for
  real-world signals.^25^

- **Hop Size / Overlap:** This parameter determines how far the window
  is shifted forward for each subsequent FFT calculation. A smaller hop
  size results in greater overlap between adjacent windows. This
  increases the temporal density of the spectrogram (i.e., more columns
  in the final image), which can produce a smoother, more detailed
  visual appearance. However, this comes at the cost of increased
  computational load, as more FFTs must be calculated for the same
  duration of audio.^24^

This inherent trade-off has direct consequences for SSTV decoding. The
need to precisely measure frequency to determine pixel brightness
suggests a wide window is optimal. Conversely, the need to precisely
time the arrival of sync pulses suggests a narrow window is best. This
conflict implies that a sophisticated decoder cannot rely on a single,
fixed STFT configuration for all tasks. It must either use different
parameters for different stages of decoding or employ entirely different
algorithms for tasks like synchronization.

The challenge of creating a real-time waterfall display further
compounds this issue. The developer must manage a three-way tension
between the desired frequency resolution (which dictates a longer FFT
window), the perceived time latency (a longer window requires more time
to fill with audio samples before processing can begin), and the overall
computational load (more FFTs per second are needed for a smooth
display).^26^ This is a classic real-time systems engineering problem
that developers of modern SSTV applications must solve to provide a
responsive user experience.

The following table summarizes the impact of these key STFT parameters,
providing a practical guide to their effects and intended use cases.

Table 2: The Impact of STFT Parameters on Spectrogram Characteristics

\| Parameter \| Effect on Time Resolution \| Effect on Frequency
Resolution \| Effect on Computational Load \| Primary Use Case/Goal \|

\| :\-\-- \| :\-\-- \| :\-\-- \| :\-\-- \| :\-\-- \|

\| Window Size (NFFT) \| Inverse (Larger NFFT = Poorer Time Res) \|
Direct (Larger NFFT = Finer Freq Res) \| Direct (Larger NFFT = Higher
Load) \| Tune for desired spectral detail vs. temporal precision. \|

\| Hop Size / Overlap \| Direct (Smaller Hop = Finer Time Res) \| None
\| Inverse (Smaller Hop = Higher Load) \| Increase temporal density and
visual smoothness. \|

\| Window Function \| Minor \| Affects spectral leakage and peak width
\| Minor \| Reduce artifacts and improve accuracy of amplitude
measurements. \|

## Section 3: Functional Analysis of Visualizations in SSTV Applications

By synthesizing the specifics of the SSTV protocol with the general
theory of spectral analysis, we can now dissect how spectrogram and
waterfall displays function within a typical SSTV decoder application.
These visualizations are not merely passive displays; they serve active
roles in both manual operation and the automated decoding pipeline.

### 3.1 The Dual Role of the Spectrogram in SSTV

In the context of SSTV, the spectrogram/waterfall display serves two
distinct but equally important purposes: it is both a diagnostic tool
for the operator and a raw data canvas for the underlying image.

#### Diagnostic Tool

For the amateur radio operator, the real-time waterfall display is an
indispensable diagnostic instrument. Before any automated decoding can
begin, the operator uses the waterfall to:

- **Tune the Radio:** The operator visually identifies the SSTV signal,
  which appears as a set of bright, parallel horizontal lines within a
  specific frequency block on the waterfall. They can then carefully
  adjust the receiver\'s tuning dial to center the signal perfectly. The
  goal is to align the signal\'s frequency components with the expected
  audio passband, ensuring the sync pulse is at 1,200 Hz and the data
  tones fall between 1,500 and 2,300 Hz. Proper tuning is critical for
  achieving a high-quality decode.^4^

- **Identify the Signal:** The characteristic \"warble\" and structured
  nature of an SSTV transmission create a unique visual signature on the
  spectrogram. An experienced operator can immediately distinguish an
  SSTV signal from voice, data, or noise, allowing them to quickly
  identify a transmission of interest on a crowded band.^30^

#### Raw Data Canvas

As established previously, the SSTV signal is a time-unrolled
representation of the image, with brightness mapped to frequency.
Consequently, the spectrogram becomes a direct, albeit skewed,
visualization of the image data itself. An operator watching the
waterfall can see:

- **Synchronization Structure:** The repeating 1,200 Hz horizontal sync
  pulses appear as a strong, regular vertical line or \"fence\" on the
  left side of the signal block on the spectrogram.^31^

- **Image Content:** The image data appears as varying horizontal
  patterns between 1,500 Hz and 2,300 Hz. Bright areas of the image
  correspond to higher frequencies (closer to 2,300 Hz), while dark
  areas correspond to lower frequencies (closer to 1,500 Hz). An
  experienced user can often discern the basic shapes and structure of
  the image directly from the waterfall display, even before the
  software has finished assembling the final picture.

### 3.2 The Digital Decoding Pipeline

The era of specialized hardware modems and long-persistence cathode-ray
tubes for SSTV is long past.^2^ Modern decoding is accomplished entirely
in software on personal computers and mobile devices.^2^ Applications
like MMSSTV for Windows,

slowrx for Linux, and various mobile apps all follow a similar digital
signal processing pipeline.^4^

1.  **Signal Acquisition:** The process begins by capturing the audio
    output from the radio receiver. This can be done via a direct audio
    cable connection to the computer\'s line-in port, a dedicated data
    interface that isolates the signals and handles radio keying ^4^,
    or, in the simplest case, by placing the smartphone\'s microphone
    next to the radio\'s speaker.^4^ The captured audio is then
    digitized by the device\'s sound card or an external
    Analog-to-Digital Converter (ADC).

2.  **Mode Detection:** The software continuously analyzes the incoming
    audio stream, searching for the signature of the VIS code header.^1^
    Upon detecting the leader tones, it switches to an FSK demodulation
    algorithm to decode the 8-bit value that follows. This value is used
    to look up the parameters for the incoming SSTV mode (e.g., Martin
    M1, Scottie S1) from an internal database.^3^ Advanced applications
    like Black Cat SSTV pride themselves on having extremely sensitive
    and robust VIS detectors that can function even under weak signal
    conditions.^3^

3.  **Synchronization Lock:** Once the mode is known, the decoder begins
    searching for the 1,200 Hz horizontal sync pulses. This is typically
    achieved using a highly selective digital band-pass filter centered
    at 1,200 Hz or a similar matched filtering technique.^31^ The
    successful detection of a sync pulse triggers the start of a new
    scanline and resets the line\'s timing counter.

4.  **Frequency-to-Pixel Conversion:** Between each sync pulse, the
    software processes the audio corresponding to one scanline. For each
    \"pixel\" duration (a time interval determined by the mode\'s
    specifications), the decoder must measure the instantaneous
    frequency of the signal. This is a task for which a frequency-domain
    approach is ideal. A slice of the STFT (i.e., a single FFT of a
    short window of audio) is a common method used to determine the
    dominant frequency.^34^ This measured frequency is then linearly
    scaled from the 1,500-2,300 Hz range to a pixel intensity value
    (e.g., an 8-bit integer from 0 to 255).

5.  **Image Assembly:** The calculated pixel values are written into a
    memory buffer that represents the final image. The software writes
    the values row by row, carefully following the color component
    sequence (e.g., R, then G, then B for a Scottie S1 line) dictated by
    the detected mode. Once all lines have been received and processed,
    the buffer contains the complete, decoded image.

### 3.3 Advanced Slant and Skew Correction

A frequent artifact in SSTV reception is \"slant,\" where the entire
image appears tilted. This is caused by minute, cumulative timing errors
resulting from slight mismatches between the sampling rate clocks of the
transmitting and receiving sound cards.^32^

While basic decoders may require the user to manually adjust a \"slant\"
parameter to correct the image, advanced decoders perform this
correction automatically. A powerful and elegant technique for this is
the **Hough Transform**, an algorithm borrowed from the field of
computer vision.^34^ The process works as follows:

1.  The decoder logs the precise time at which each horizontal sync
    pulse is detected.

2.  These detections are treated as points on a 2D plane, with the line
    number on the y-axis and the detection time on the x-axis.

3.  In a perfect reception, these points would form a perfectly vertical
    line. With clock drift, they form a slanted line.

4.  The Hough Transform is applied to this set of points. It is an
    extremely robust algorithm for detecting lines within a noisy set of
    points. It finds the dominant line that best fits the detected sync
    pulse locations.

5.  The slope of this detected line directly corresponds to the timing
    drift per scanline. The decoder can then use this calculated slope
    to apply a corrective time shift to each scanline as it is written
    to the image buffer, resulting in a perfectly vertical,
    slant-corrected image.

The use of sophisticated algorithms like the Hough Transform exemplifies
a key trend: modern software does not just replicate the functions of
older analog hardware but actively enhances the process, achieving a
level of perfection and automation that was previously unattainable.
This represents a shift from simple software implementation to true
software-enhanced decoding.

## Section 4: A Modern Implementation Blueprint for SSTV Spectral Analysis

This section provides a practical blueprint for developing the core
spectral visualization components of an SSTV application. It leverages
the modern scientific Python ecosystem, demonstrating how high-level
libraries can be used to implement these complex DSP tasks with
remarkable efficiency and clarity.

### 4.1 Reference Architecture using Python

A robust and maintainable system can be built using a modular
architecture that separates the distinct tasks of audio input, numerical
processing, and visualization. The recommended Python libraries for this
architecture are:

- **Audio Input/Output (I/O):** For processing pre-recorded signals, the
  soundfile library provides a simple and efficient way to read and
  write various audio formats, particularly WAV files.^35^ For real-time
  applications that require capturing audio from a microphone or
  line-in, the\
  pyaudio library offers cross-platform access to audio streams.^35^

- **Numerical Processing:** The NumPy library is the cornerstone of
  scientific computing in Python. It provides the fundamental ndarray
  object for representing audio data as efficient numerical arrays and a
  vast collection of mathematical functions for manipulating them.^35^

- **Digital Signal Processing (DSP):** The SciPy library, built upon
  NumPy, contains a comprehensive signal module. This module includes a
  highly optimized spectrogram function that encapsulates the entire
  STFT process, from windowing to FFT computation.^35^

- **Visualization:** The Matplotlib library is the de facto standard for
  plotting in Python. It provides the tools necessary to render the
  spectrogram data as a high-quality image.^37^ For interactive,
  real-time displays, Matplotlib can be integrated into GUI frameworks
  such as PyQt or Tkinter.

An important consideration for this specific application is the choice
of spectrogram type. Many audio analysis tutorials, particularly in the
machine learning domain, default to using a **Mel spectrogram**.^39^ The
Mel scale is a perceptual scale of pitch designed to mimic human
hearing, which gives more resolution to lower frequencies and compresses
higher frequencies.^41^ While excellent for music or speech analysis,
this is fundamentally incorrect for SSTV. The SSTV protocol uses a
strictly

**linear** mapping of frequency to brightness.^1^ Applying a Mel scale
would warp this linear relationship, destroying the integrity of the
data and making the spectrogram an invalid representation of the image.
Therefore, it is critical to use a spectrogram with a linear frequency
scale for SSTV analysis. This highlights the necessity of understanding
the underlying signal protocol before applying generic processing tools.

### 4.2 From Audio Stream to Spectral Matrix

The first step in the pipeline is to convert the raw audio waveform into
the 2D matrix of power spectral density values that represents the
spectrogram. The following Python code demonstrates this process using
soundfile and scipy.signal.

Python

import soundfile as sf\
import numpy as np\
from scipy import signal\
import matplotlib.pyplot as plt\
\
\# Step 1: Load the audio file\
\# An example SSTV audio file in WAV format is loaded.\
\# \'soundfile.read\' returns the waveform as a NumPy array and the
sampling rate.\
try:\
waveform, sample_rate = sf.read(\'sstv_signal.wav\')\
except FileNotFoundError:\
print(\"Error: \'sstv_signal.wav\' not found. Please provide a valid
SSTV audio file.\")\
exit()\
\
\# Ensure the signal is mono for simplicity\
if waveform.ndim \> 1:\
waveform = waveform.mean(axis=1)\
\
\# Step 2: Compute the Short-Time Fourier Transform (STFT)\
\# The scipy.signal.spectrogram function handles the entire STFT
process.\
\# Parameters:\
\# - waveform: The 1D NumPy array containing the audio data.\
\# - sample_rate: The sampling frequency of the audio signal.\
\# - window: The window function to apply to each segment. \'hann\' is a
good general choice.\
\# - nperseg: The number of samples per FFT segment (window length).
This controls frequency resolution.\
\# A value of 1024 provides a good balance for a typical 44.1kHz audio
signal.\
\# - noverlap: The number of samples to overlap between segments.
nperseg // 2 is a common choice.\
\# - scaling: \'density\' computes the Power Spectral Density (PSD) in
V\^2/Hz.\
frequencies, times, Sxx = signal.spectrogram(\
waveform,\
fs=sample_rate,\
window=\'hann\',\
nperseg=1024,\
noverlap=512,\
scaling=\'density\'\
)\
\
\# The output \'Sxx\' is the 2D NumPy array containing the power
values.\
\# This matrix is the core data structure for our visualization.

The power of modern libraries is evident here. The complexity of
implementing windowing, overlapping segmentation, and FFT computation is
abstracted away into a single, highly optimized function call. This
dramatically lowers the barrier to entry, allowing developers to focus
on the application logic rather than the low-level DSP mathematics.

### 4.3 Rendering the Visualizations

With the spectral data computed and stored in the Sxx matrix, the final
step is to render it as a visual plot.

#### Static Spectrogram

Matplotlib can be used to create a high-quality static spectrogram from
the STFT data. The pcolormesh function is ideal for this, as it
efficiently plots a 2D array with colored quadrilaterals.

Python

\# Step 3: Render the spectrogram\
fig, ax = plt.subplots(figsize=(12, 6))\
\
\# Use pcolormesh to plot the spectrogram.\
\# The power values in Sxx are typically very small, so we convert them
to a logarithmic scale (decibels).\
\# A small epsilon is added to avoid taking the log of zero.\
im = ax.pcolormesh(\
times,\
frequencies,\
10 \* np.log10(Sxx + 1e-9),\
shading=\'gouraud\',\
cmap=\'viridis\' \# A perceptually uniform colormap is crucial (see
Section 5)\
)\
\
\# Set plot labels and limits for clarity.\
\# For SSTV, we are interested in the 0-3000 Hz range.\
ax.set_ylabel(\'Frequency \[Hz\]\')\
ax.set_xlabel(\'Time \[s\]\')\
ax.set_title(\'SSTV Signal Spectrogram\')\
ax.set_ylim(0, 3000)\
\
\# Add a color bar to show the mapping of color to power (in dB).\
fig.colorbar(im, ax=ax, label=\'Power Spectral Density\')\
\
plt.show()

#### Real-Time Waterfall

Implementing a real-time waterfall display is a more advanced task that
requires a different architecture, typically involving multithreading to
prevent the user interface from freezing during processing. The
conceptual architecture is as follows:

1.  **Audio Acquisition Thread:** A dedicated thread runs continuously,
    reading chunks of audio data from the input device (using a library
    like pyaudio) and placing them into a shared, thread-safe buffer
    (like a collections.deque in Python).

2.  **Processing and Rendering Loop:** The main application or GUI
    thread runs a periodic timer. On each tick of the timer, it performs
    the following actions:

    - It retrieves the most recent audio samples from the shared buffer
      to form a new analysis window.

    - It computes a single FFT of this window to generate one new
      vertical slice of the waterfall.

    - It updates a large 2D NumPy array that holds the entire waterfall
      image. This is done by \"scrolling\" the existing data down by one
      row and inserting the new spectral slice at the top.

    - Finally, it re-draws this updated 2D array onto the screen.

This separation of concerns---keeping the blocking audio I/O and heavy
computation off the main GUI thread---is essential for creating a smooth
and responsive real-time visualization, as seen in professional tools
like SpectrumView and Fosphor.^42^

## Section 5: Advanced Topics and Best Practices in Spectral Visualization

Creating a functional spectrogram is one thing; creating a
scientifically valid, high-performance, and insightful one is another.
This section explores advanced topics and best practices that
distinguish a professional-grade visualization tool from a rudimentary
one.

### 5.1 The Imperative of Perceptually Uniform Colormaps

The choice of colormap is not a mere aesthetic decision; it is a
critical part of the data visualization pipeline that directly impacts
the integrity of the interpretation. For decades, the default colormap
in many scientific tools has been a \"jet\" or rainbow spectrum.
However, extensive research in data visualization has shown these maps
to be deeply flawed.^44^

The fundamental problem with rainbow colormaps is that they are not
**perceptually uniform**. The human visual system does not perceive
changes in hue linearly; it is far more sensitive to changes in
lightness (brightness). Rainbow maps have highly non-linear lightness
gradients. They contain \"flat spots\"---such as the broad green and
cyan regions in jet---where large changes in the underlying data result
in very little change in perceived color. Conversely, they have sharp,
artificial boundaries---like the transition from yellow to green---where
small changes in data produce a dramatic shift in color. This can cause
an analyst to miss significant features that fall within the flat spots
or to perceive false features and boundaries where none exist.^44^

The solution is to use modern, **perceptually uniform colormaps**. These
colormaps, such as **Viridis**, **Plasma**, **Inferno**, **Magma**, and
**Cividis**, are mathematically designed so that a given step in the
data value corresponds to an equivalent perceptual step in brightness
and color.^45^ This ensures that the visualization is an accurate and
faithful representation of the data. Cividis has the additional benefit
of being robust for viewers with common forms of color vision
deficiency.^47^ In

Matplotlib, adopting this best practice is as simple as specifying the
cmap parameter (e.g., cmap=\'viridis\') in the plotting function.^48^
For any serious scientific or technical visualization, the use of
perceptually uniform colormaps should be considered mandatory.

### 5.2 Real-Time Performance and GPU Acceleration

As outlined in Section 4, real-time waterfall displays are
computationally demanding. For high-resolution displays with fast update
rates (e.g., 30-60 frames per second), performing repeated FFTs on a CPU
can quickly become a performance bottleneck, leading to a sluggish or
choppy display.

The modern solution to this challenge is to leverage the massively
parallel processing power of **Graphics Processing Units (GPUs)**. GPUs
are designed to perform thousands of simple mathematical operations
simultaneously, a characteristic that makes them exceptionally
well-suited for algorithms like the FFT.

State-of-the-art real-time spectrum analysis tools, such as **Fosphor**
for Software-Defined Radio (SDR), are built on this principle.^43^
Fosphor offloads both the FFT calculations and the final rendering to
the GPU. This allows it to generate extremely smooth, high-resolution,
low-latency waterfall displays that can visualize wide bandwidths in
real time---a feat that would be impossible to achieve on a CPU alone.
The name \"Fosphor\" itself is a nod to the long-persistence phosphors
used in old radar screens, which created a similar visual effect of
decaying traces.^43^

While direct GPU programming with frameworks like NVIDIA\'s CUDA can be
complex, developers can access this power through more accessible
high-level libraries. Deep learning frameworks like **PyTorch** and
**TensorFlow** include GPU-accelerated FFT implementations, providing a
viable path for Python developers to build high-performance spectral
analysis applications without needing to write low-level GPU code.^35^

### 5.3 Beyond Analog: The Future of Radio Imaging

While analog SSTV remains popular due to its simplicity and
accessibility, it is a legacy protocol. From a technical standpoint,
modern digital transmission modes offer vastly superior performance. The
amateur radio community has developed digital protocols that represent
the future of narrowband image transmission over radio.

A prime example is **HamDRM**, a system based on the principles of
Digital Radio Mondiale (DRM).^49^ Instead of the simple analog FM used
by SSTV, HamDRM employs advanced digital modulation schemes like

**Quadrature Amplitude Modulation (QAM)** in conjunction with
**Orthogonal Frequency-Division Multiplexing (OFDM)**. OFDM divides the
3 kHz channel into many narrow, orthogonal subcarriers, with each
subcarrier modulated using QAM to carry a piece of the digital data
stream.^49^

This digital approach provides two transformative advantages:

1.  **Robustness:** Digital modes incorporate **Forward Error Correction
    (FEC)**. Redundant data is added to the transmission, allowing the
    receiver to detect and correct errors caused by noise or fading.
    This makes digital modes far more resilient to poor channel
    conditions than analog SSTV, which degrades gracefully but has no
    inherent error correction.^49^

2.  **Efficiency:** Advanced modulation like 64-QAM can pack
    significantly more bits per second into the same bandwidth compared
    to analog FM, enabling higher-resolution images to be sent in less
    time.^49^

For these modern digital modes, the role of the spectrogram
fundamentally changes. It is no longer a direct, raw canvas of the image
data. Instead, it becomes a diagnostic tool for analyzing the complex
multi-carrier OFDM signal. The image itself can only be recovered after
a full digital demodulation, de-interleaving, and error-correction
process. This marks a paradigm shift from the direct, \"human-readable\"
nature of the analog SSTV signal to the abstract, computationally
intensive world of modern digital communications. The enduring appeal of
analog SSTV, despite its technical inferiority, lies in its simplicity,
accessibility (it can be decoded by holding a phone to a speaker), and
graceful degradation, qualities that the amateur radio community
continues to value.^4^

## Section 6: Conclusion and Recommendations

The journey from the analog tones of a Slow-Scan Television transmission
to the vibrant, detailed spectrogram on a modern display is a microcosm
of the evolution of signal processing itself. It begins with a simple,
robust protocol where image brightness is directly mapped to audio
frequency, a system born from the constraints of mid-20th-century analog
technology. The analysis of this signal in the modern era relies on the
Short-Time Fourier Transform, a powerful mathematical tool that allows
us to view the signal\'s frequency content as it changes over time.

The spectrogram serves as the unifying bridge between these two worlds.
For the operator, it is a real-time diagnostic tool for tuning and
identifying signals. For the analyst, it is a direct, if skewed, canvas
of the raw image data embedded in the audio. For the developer, it is
the tangible output of the fundamental DSP pipeline. Modern software
applications have not only replicated the functions of the original
hardware but have significantly enhanced them, introducing capabilities
like automatic mode detection and sophisticated slant correction that
were impractical in the analog era. This evolution demonstrates a
powerful trend where software transforms legacy protocols, imbuing them
with new levels of performance and usability.

### 6.1 Recommendations for Developers

For developers seeking to create or analyze SSTV applications, the
following best practices are recommended:

- **Prioritize Protocol Understanding:** Before writing a single line of
  code, invest time in understanding the precise timings, frequency
  mappings, and structural components (VIS code, sync pulses) of the
  specific SSTV modes to be supported. The protocol specification is the
  ultimate ground truth.

- **Adopt a Modular Architecture:** Design the application by separating
  distinct concerns. Audio acquisition, the core signal processing
  engine (including sync detection and data decoding), and the user
  interface rendering should be treated as independent, interacting
  modules. This approach greatly improves maintainability and
  testability.

- **Leverage High-Level Libraries:** Utilize established scientific
  libraries like SciPy and Librosa for core DSP tasks such as the STFT.
  These libraries are highly optimized and rigorously tested, allowing
  developers to avoid reinventing fundamental algorithms and to focus on
  the unique aspects of the SSTV application.

- **Choose the Right Tool for Each Task:** Recognize that a single STFT
  configuration is not optimal for all decoding tasks. Employ
  time-domain techniques, such as narrow band-pass filtering, for
  precise synchronization pulse detection. Use frequency-domain
  techniques, namely the FFT, for accurate pixel data decoding across
  the signal\'s passband.

- **Embrace Perceptually Uniform Colormaps:** Make Viridis, Cividis, or
  another perceptually uniform colormap the default for all spectral
  visualizations. Explicitly reject rainbow-based maps like jet to
  ensure an accurate and scientifically valid representation of the
  signal data.

- **Design for Real-Time Performance:** For applications featuring a
  live waterfall display, performance must be a primary design
  consideration. Implement a multi-threaded architecture that separates
  the blocking audio I/O and computationally intensive processing from
  the main UI thread to ensure a responsive user experience. For
  ultimate performance and high-resolution displays, investigate the use
  of GPU-accelerated FFTs.

#### Works cited

1.  Slow-scan television - Wikipedia, accessed June 16, 2025,
    [[https://en.wikipedia.org/wiki/Slow-scan_television]{.underline}](https://en.wikipedia.org/wiki/Slow-scan_television)

2.  GUIDE - SSTV - NORAC, accessed June 16, 2025,
    [[https://norac.bc.ca/index.php/instruction-guides/730-guide-sstv]{.underline}](https://norac.bc.ca/index.php/instruction-guides/730-guide-sstv)

3.  What\'s the best way to identify the mode of an SSTV broadcast? :
    r/amateurradio - Reddit, accessed June 16, 2025,
    [[https://www.reddit.com/r/amateurradio/comments/bapq7x/whats_the_best_way_to_identify_the_mode_of_an/]{.underline}](https://www.reddit.com/r/amateurradio/comments/bapq7x/whats_the_best_way_to_identify_the_mode_of_an/)

4.  SSTV -- The Basics Explained - Essex Ham, accessed June 16, 2025,
    [[https://www.essexham.co.uk/sstv-the-basics]{.underline}](https://www.essexham.co.uk/sstv-the-basics)

5.  Best SSTV mode to use for transmitting QR codes on UHF/VHF ? :
    r/amateurradio - Reddit, accessed June 16, 2025,
    [[https://www.reddit.com/r/amateurradio/comments/ee74ia/best_sstv_mode_to_use_for_transmitting_qr_codes/]{.underline}](https://www.reddit.com/r/amateurradio/comments/ee74ia/best_sstv_mode_to_use_for_transmitting_qr_codes/)

6.  Slow-Scan Television (SSTV) - Signal Identification Wiki, accessed
    June 16, 2025,
    [[https://www.sigidwiki.com/wiki/Slow-Scan_Television\_(SSTV)]{.underline}](https://www.sigidwiki.com/wiki/Slow-Scan_Television_(SSTV))

7.  Slow-scan television - Simple English Wikipedia, the free
    encyclopedia, accessed June 16, 2025,
    [[https://simple.wikipedia.org/wiki/Slow-scan_television]{.underline}](https://simple.wikipedia.org/wiki/Slow-scan_television)

8.  SSTV Encoder - Apps on Google Play, accessed June 16, 2025,
    [[https://play.google.com/store/apps/details?id=om.sstvencoder]{.underline}](https://play.google.com/store/apps/details?id=om.sstvencoder)

9.  Understanding spectrograms - iZotope, accessed June 16, 2025,
    [[https://www.izotope.com/en/learn/understanding-spectrograms]{.underline}](https://www.izotope.com/en/learn/understanding-spectrograms)

10. What is a Spectrogram? A 101 Guide to Reading Spectrograms - Blog \|
    Splice, accessed June 16, 2025,
    [[https://splice.com/blog/what-is-a-spectrogram/]{.underline}](https://splice.com/blog/what-is-a-spectrogram/)

11. A NEW PARADIGM FOR PLOTTING SPECTROGRAM - Bioinfo Publications,
    accessed June 16, 2025,
    [[https://bioinfopublication.org/files/articles/3_1_31_JISC.pdf]{.underline}](https://bioinfopublication.org/files/articles/3_1_31_JISC.pdf)

12. Understanding spectrograms - iZotope, accessed June 16, 2025,
    [[https://www.izotope.com/en/learn/understanding-spectrograms.html]{.underline}](https://www.izotope.com/en/learn/understanding-spectrograms.html)

13. What is a Waterfall Display and what does it show me? (040) -
    YouTube, accessed June 16, 2025,
    [[https://www.youtube.com/watch?v=lrAKDYx2fTg]{.underline}](https://www.youtube.com/watch?v=lrAKDYx2fTg)

14. Spectrogram Types The Many Faces of the Spectrogram \| Tektronix,
    accessed June 16, 2025,
    [[https://www.tek.com/en/blog/spectrogram-types-the-many-faces-of-the-spectrogram]{.underline}](https://www.tek.com/en/blog/spectrogram-types-the-many-faces-of-the-spectrogram)

15. Spectrogram in JavaScript - arc .id.au, accessed June 16, 2025,
    [[https://www.arc.id.au/Spectrogram.html]{.underline}](https://www.arc.id.au/Spectrogram.html)

16. Spectrogram - Wikipedia, accessed June 16, 2025,
    [[https://en.wikipedia.org/wiki/Spectrogram]{.underline}](https://en.wikipedia.org/wiki/Spectrogram)

17. The difference between histograms and spectrograms - EE World
    Online, accessed June 16, 2025,
    [[https://www.eeworldonline.com/the-difference-between-histograms-and-spectrograms/]{.underline}](https://www.eeworldonline.com/the-difference-between-histograms-and-spectrograms/)

18. homepage.ntu.edu.tw, accessed June 16, 2025,
    [[https://homepage.ntu.edu.tw/\~karchung/Phonetics%20II%20page%20twentyone.htm#:\~:text=The%20waterfall%20spectrogram%20contains%20the,a%20very%20knobby%20mountain%20range.]{.underline}](https://homepage.ntu.edu.tw/~karchung/Phonetics%20II%20page%20twentyone.htm#:~:text=The%20waterfall%20spectrogram%20contains%20the,a%20very%20knobby%20mountain%20range.)

19. Waterfall plot - Wikipedia, accessed June 16, 2025,
    [[https://en.wikipedia.org/wiki/Waterfall_plot]{.underline}](https://en.wikipedia.org/wiki/Waterfall_plot)

20. Time--frequency analysis - Wikipedia, accessed June 16, 2025,
    [[https://en.wikipedia.org/wiki/Time%E2%80%93frequency_analysis]{.underline}](https://en.wikipedia.org/wiki/Time%E2%80%93frequency_analysis)

21. Time--frequency representation - Wikipedia, accessed June 16, 2025,
    [[https://en.wikipedia.org/wiki/Time%E2%80%93frequency_representation]{.underline}](https://en.wikipedia.org/wiki/Time%E2%80%93frequency_representation)

22. Short-time Fourier transform - Wikipedia, accessed June 16, 2025,
    [[https://en.wikipedia.org/wiki/Short-time_Fourier_transform]{.underline}](https://en.wikipedia.org/wiki/Short-time_Fourier_transform)

23. Audio Short-Time Fourier Transform (STFT): New in Wolfram Language
    12, accessed June 16, 2025,
    [[https://www.wolfram.com/language/12/new-in-audio-processing/audio-short-time-fourier-transform-stft.html]{.underline}](https://www.wolfram.com/language/12/new-in-audio-processing/audio-short-time-fourier-transform-stft.html)

24. Short-Time Fourier Transform and Chroma Features - International
    \..., accessed June 16, 2025,
    [[https://www.audiolabs-erlangen.de/content/05_fau/professor/00_mueller/02_teaching/2017s_apl/LabCourse_STFT.pdf]{.underline}](https://www.audiolabs-erlangen.de/content/05_fau/professor/00_mueller/02_teaching/2017s_apl/LabCourse_STFT.pdf)

25. Waterfall Graph - REW, accessed June 16, 2025,
    [[https://www.roomeqwizard.com/help/help_en-GB/html/graph_waterfall.html]{.underline}](https://www.roomeqwizard.com/help/help_en-GB/html/graph_waterfall.html)

26. Waterfall Configuration - Fldigi Users Manual - W1HKJ, accessed June
    16, 2025,
    [[http://www.w1hkj.com/FldigiHelp/ui_configuration_waterfall_page.html]{.underline}](http://www.w1hkj.com/FldigiHelp/ui_configuration_waterfall_page.html)

27. The Short-Time Fourier Transform \| Spectral Audio Signal
    Processing - DSPRelated.com, accessed June 16, 2025,
    [[https://www.dsprelated.com/freebooks/sasp/Short_Time_Fourier_Transform.html]{.underline}](https://www.dsprelated.com/freebooks/sasp/Short_Time_Fourier_Transform.html)

28. Spectral density - Wikipedia, accessed June 16, 2025,
    [[https://en.wikipedia.org/wiki/Spectral_density]{.underline}](https://en.wikipedia.org/wiki/Spectral_density)

29. SSTV Reports Using the P Scale - WA9TT, accessed June 16, 2025,
    [[https://www.wa9tt.com/CQ_magazine/CQ_P_reporting_article.pdf]{.underline}](https://www.wa9tt.com/CQ_magazine/CQ_P_reporting_article.pdf)

30. Images on an Audio Cassette : 5 Steps (with Pictures) -
    Instructables, accessed June 16, 2025,
    [[https://www.instructables.com/Images-On-An-Audio-Cassette/]{.underline}](https://www.instructables.com/Images-On-An-Audio-Cassette/)

31. Narrow-Bandwidth Television Association • View topic - SSTV
    Demodulation., accessed June 16, 2025,
    [[https://www.taswegian.com/NBTV/forum/viewtopic.php?f=23&t=3038&start=15]{.underline}](https://www.taswegian.com/NBTV/forum/viewtopic.php?f=23&t=3038&start=15)

32. windytan/slowrx: A decoder for Slow-Scanning Television \... -
    GitHub, accessed June 16, 2025,
    [[https://github.com/windytan/slowrx]{.underline}](https://github.com/windytan/slowrx)

33. Black Cat SSTV, accessed June 16, 2025,
    [[https://www.blackcatsystems.com/software/sstv.html]{.underline}](https://www.blackcatsystems.com/software/sstv.html)

34. lionel.cordesses - SSTV digital demodulator, accessed June 16, 2025,
    [[http://lionel.cordesses.free.fr/gpages/sstv.html]{.underline}](http://lionel.cordesses.free.fr/gpages/sstv.html)

35. 10 Python Libraries for Audio Processing - Cloud Devs, accessed June
    16, 2025,
    [[https://clouddevs.com/python/libraries-for-audio-processing/]{.underline}](https://clouddevs.com/python/libraries-for-audio-processing/)

36. Audio Processing Basics in Python - It-Jim, accessed June 16, 2025,
    [[https://www.it-jim.com/blog/audio-processing-basics-in-python/]{.underline}](https://www.it-jim.com/blog/audio-processing-basics-in-python/)

37. spectrogram-tutorial/spectrogram.ipynb at main ·
    drammock/spectrogram-tutorial - GitHub, accessed June 16, 2025,
    [[https://github.com/drammock/spectrogram-tutorial/blob/master/spectrogram.ipynb]{.underline}](https://github.com/drammock/spectrogram-tutorial/blob/master/spectrogram.ipynb)

38. Plotting a Spectrogram using Python and Matplotlib - GeeksforGeeks,
    accessed June 16, 2025,
    [[https://www.geeksforgeeks.org/plotting-a-spectrogram-using-python-and-matplotlib/]{.underline}](https://www.geeksforgeeks.org/plotting-a-spectrogram-using-python-and-matplotlib/)

39. Spectrogram Analysis using Python - GaussianWaves, accessed June 16,
    2025,
    [[https://www.gaussianwaves.com/2022/03/spectrogram-analysis-using-python/]{.underline}](https://www.gaussianwaves.com/2022/03/spectrogram-analysis-using-python/)

40. Audio classification using spectrograms - GeeksforGeeks, accessed
    June 16, 2025,
    [[https://www.geeksforgeeks.org/audio-classification-using-spectrograms/]{.underline}](https://www.geeksforgeeks.org/audio-classification-using-spectrograms/)

41. Visualizing sound as an audio spectrogram \| Apple Developer
    Documentation, accessed June 16, 2025,
    [[https://developer.apple.com/documentation/accelerate/visualizing-sound-as-an-audio-spectrogram]{.underline}](https://developer.apple.com/documentation/accelerate/visualizing-sound-as-an-audio-spectrogram)

42. SpectrumView - Oxford Wave Research, accessed June 16, 2025,
    [[https://oxfordwaveresearch.com/products/spectrumviewapp/]{.underline}](https://oxfordwaveresearch.com/products/spectrumviewapp/)

43. Khanfar Spectrum Analyzer, accessed June 16, 2025,
    [[https://khanfar-spectrum-analyzer.web.app/]{.underline}](https://khanfar-spectrum-analyzer.web.app/)

44. CET Perceptually Uniform Colour Maps, accessed June 16, 2025,
    [[https://colorcet.com/]{.underline}](https://colorcet.com/)

45. Collection of perceptually accurate colormaps --- colorcet v3.1.0,
    accessed June 16, 2025,
    [[https://colorcet.holoviz.org/]{.underline}](https://colorcet.holoviz.org/)

46. perceptual colormaps - MyCarta, accessed June 16, 2025,
    [[https://mycartablog.com/tag/perceptual-colormaps/]{.underline}](https://mycartablog.com/tag/perceptual-colormaps/)

47. Color Map Advice for Scientific Visualization - Kenneth Moreland,
    accessed June 16, 2025,
    [[https://www.kennethmoreland.com/color-advice/]{.underline}](https://www.kennethmoreland.com/color-advice/)

48. matplotlib.pyplot.specgram, accessed June 16, 2025,
    [[https://matplotlib.org/stable/api/\_as_gen/matplotlib.pyplot.specgram.html]{.underline}](https://matplotlib.org/stable/api/_as_gen/matplotlib.pyplot.specgram.html)

49. DSSTV transmission systems - SSTV handbook, accessed June 16, 2025,
    [[https://www.sstv-handbook.com/download/sstv_10.pdf]{.underline}](https://www.sstv-handbook.com/download/sstv_10.pdf)

50. Why don\'t most if not all SSTV protocols mix different frequencies
    but just transmit a single frequency at any given time? :
    r/amateurradio - Reddit, accessed June 16, 2025,
    [[https://www.reddit.com/r/amateurradio/comments/18j9h0w/why_dont_most_if_not_all_sstv_protocols_mix/]{.underline}](https://www.reddit.com/r/amateurradio/comments/18j9h0w/why_dont_most_if_not_all_sstv_protocols_mix/)
