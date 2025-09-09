### **Final Report: Black Cat SSTV Application Analysis**

Date: June 7, 2025

Location: Kansas City, Missouri, United States

### **1. Executive Summary**

This report provides a comprehensive analysis of the Black Cat SSTV
application, version 2.5.0. The primary goal was to conduct a functional
audit to establish a baseline for feature parity in a new application
and to evaluate its underlying technology.

The analysis confirms that Black Cat SSTV is a feature-rich application
for amateur radio operators, with a stated emphasis on high-performance
decoding of weak and noisy Slow-Scan Television (SSTV) signals. The
application is built using the **Xojo development environment**, a
cross-platform tool that enables it to run on both Windows and macOS
from a single codebase.

A comparative analysis was conducted between Xojo and **Electron**, a
popular alternative for modern cross-platform development. The
conclusion is that the choice between these frameworks is not about
superiority, but about aligning with development priorities. **Xojo
excels in creating applications with a native look and feel, low
resource usage, and rapid development cycles.** In contrast, **Electron
offers unparalleled UI flexibility and access to a vast open-source
ecosystem**, at the cost of higher resource consumption and a less
native user experience.

### **2. Functional Audit: Black Cat SSTV v2.5.0**

The application\'s functionality, as detailed in its user documentation,
is extensive. A complete feature-for-feature replacement would need to
address the following key areas:

- **Signal Reception & Decoding:**

  - **Core Method:** Real-time Fast Fourier Transform (FFT) to analyze
    the audio spectrum, identifying key SSTV frequencies (1200Hz sync,
    1500Hz black, 2300Hz white).

  - **Automatic Mode Detection:** Decodes the VIS (Vertical Interval
    Signal) with a user-adjustable \"VIS Quality\" threshold to balance
    sensitivity against false decodes.

  - **Manual Correction:** Robust tools for users to manually adjust
    image **skew** and **offset** to correct for timing and
    synchronization errors, critical for weak signal recovery.

  - **Noise Rejection:** Implements a specific algorithm (credited to
    AA7AS) to calculate an image\'s noise level and automatically
    discard or abort the reception of overly noisy images based on
    user-defined thresholds.

- **Transmission Capabilities:**

  - **Image Encoding:** Converts standard image files (JPG, PNG) into
    SSTV audio signals for various modes.

  - **CW & PTT Control:** Generates Morse code (CW) for station
    identification and provides serial port control for radio
    Push-to-Talk (PTT) functionality.

- **Image & Data Management:**

  - **Integrated Editor:** A basic, built-in editor allows for creating
    and modifying images with text and image overlays before
    transmission.

  - **Galleries:** Separate, manageable galleries for received images
    and images staged for transmission.

  - **File Handling:** Saves images as PNG or JPG with adjustable
    quality and can append timestamps and noise data to filenames.

  - **FTP Upload:** Integrated FTP/SFTP client (using the cURL library)
    to automatically upload received images to a web server, with
    multiple naming schemes available.

### **3. Technical Foundation: The Xojo Framework**

Analysis of the application package files confirms that Black Cat SSTV
is developed using **Xojo**.

- **Key Indicator:** The presence of the XojoFramework.framework
  directory within the application package is definitive proof of its
  origin.

- **Implication:** Xojo is a Rapid Application Development (RAD)
  environment that compiles code to native executables for each target
  platform. This explains the application\'s availability on both macOS
  and Windows with a consistent feature set. It prioritizes using native
  OS controls, which gives the application a familiar look and feel and
  generally results in better performance and lower resource usage
  compared to web-based frameworks.

### **4. Technology Comparison: Xojo vs. Electron**

The choice to build a new application requires a decision on the
development framework. The following table summarizes the key
differences between Xojo (the incumbent technology) and Electron (a
leading modern alternative).

  --------------------------------------------------------------------------------------
  **Feature**       **Xojo (e.g., Black    **Electron (e.g.,       **Recommendation
                    Cat SSTV)**            Slack, VS Code)**       Analysis**
  ----------------- ---------------------- ----------------------- ---------------------
  **Core            Proprietary,           HTML, CSS,              If the development
  Technology**      object-oriented BASIC  JavaScript/TypeScript   team\'s expertise
                    dialect in a dedicated built on Chromium and   lies in web
                    IDE.                   Node.js.                technologies,
                                                                   Electron is the clear
                                                                   choice. Otherwise,
                                                                   Xojo offers a gentler
                                                                   learning curve for
                                                                   traditional desktop
                                                                   development.

  **Performance**   **High.** Compiles to  **Moderate.** Bundles a For a utility
                    native code, resulting full web browser,       application like an
                    in lower RAM/CPU       leading to larger app   SSTV decoder where
                    usage.                 sizes and higher        efficiency is
                                           resource consumption.   important, a
                                                                   native-compiled
                                                                   solution like Xojo
                                                                   has a distinct
                                                                   advantage.

  **User            **Native.** Uses       **Highly Flexible.**    If a standard,
  Interface**       standard OS controls   Complete control over   platform-consistent
                    for an authentic look  UI with web             UI is desired, Xojo
                    and feel.              technologies, but can   is superior. If a
                                           feel non-native.        unique, branded, and
                                                                   highly custom UI is
                                                                   the goal, Electron is
                                                                   the better choice.

  **Ecosystem**     **Niche.** Relies on a **Massive.** Full       For access to the
                    smaller community and  access to the entire    latest libraries and
                    official/third-party   npm ecosystem of        a vast pool of
                    plugins.               open-source libraries.  developer resources,
                                                                   Electron\'s ecosystem
                                                                   is unmatched.

  **Development     **Very Fast** for      **Fast**, especially    Both are fast, but
  Speed**           traditional UI layouts when leveraging         Xojo excels at
                    due to its RAD         existing web components quickly building
                    environment.           and libraries.          standard desktop
                                                                   interfaces, while
                                                                   Electron excels at
                                                                   leveraging existing
                                                                   web assets.
  --------------------------------------------------------------------------------------

### **5. Conclusion & Recommendation**

Black Cat SSTV is a well-regarded, high-performance application built on
the Xojo framework, a technology that excels at creating efficient,
native-feeling desktop applications.

For the development of a new, competing application, the choice of
framework is critical:

- **To achieve direct feature and performance parity with a native
  feel,** a framework like **Xojo** or another native-compiling tool
  (e.g., SwiftUI for Apple platforms, .NET MAUI for broader
  cross-platform) would be the most direct path.

- **To create an application with a more modern, custom UI and leverage
  a wider array of open-source tools,** **Electron** is a powerful
  choice, but developers must be prepared to manage the trade-offs in
  performance and resource consumption.

Given the technical nature of SSTV and the importance of performance in
signal processing, a solution that compiles to native code is strongly
recommended to match or exceed the benchmark set by Black Cat SSTV.
