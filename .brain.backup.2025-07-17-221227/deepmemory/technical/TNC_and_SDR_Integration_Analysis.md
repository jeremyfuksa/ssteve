# A Foundational Analysis of TNC and SDR Integration Protocols for Cross-Platform Amateur Radio Applications

Prepared for: Amateur Radio Software Development Team

Document Version: 1.0

Date: October 12, 2023

**Executive Summary:** This report provides a comprehensive technical
analysis intended to serve as the foundational reference for the
development of a next-generation, cross-platform amateur radio software
application. It is divided into two parts. Part I delivers a strategic
framework for the integration of Terminal Node Controllers (TNCs) using
the KISS protocol. It includes a detailed deconstruction of the protocol
and its common extensions, a comparative analysis of the Mobilinkd and
TinyTrak hardware, and best practices for robust implementation. Part II
presents an analysis of Software-Defined Radio (SDR) integration
methods, focusing on local integration with SDRUno and a detailed
breakdown of network protocols for remote SDR servers, including
Spyserver, WebSDR, and KiwiSDR. It concludes with an analysis of the
Receiverbook.de public stream directory. The objective is to equip the
development team with the necessary architectural insights and
actionable data to ensure a robust, feature-rich, and well-informed
implementation across Windows, macOS, and Linux platforms.

# Part I: A Strategic Framework for KISS TNC Integration

This part of the report deconstructs the KISS protocol, analyzes key
hardware implementations, and outlines best practices for creating a
robust and reliable TNC integration layer for the application.

## Section 1: Deconstruction of the KISS Protocol

A thorough understanding of the KISS protocol, from its design
philosophy to its modern fragmented state, is essential for any
successful implementation. The protocol\'s apparent simplicity belies a
significant degree of variation in the wild, which a modern application
must be prepared to handle.

### 1.1 Core Principles and Architecture

The KISS (Keep It Simple, Stupid) protocol was developed by Mike
Cheponis (K3MC) and Phil Karn (KA9Q) with a singular, elegant goal: to
simplify the hardware TNC by offloading protocol complexity to the host
computer.^1^ Early TNCs were complex devices that often contained the
entire AX.25 protocol stack, up to and including application-layer
functions.^2^ This made them expensive, difficult to update, and
inflexible.

The KISS philosophy reverses this paradigm. It removes the AX.25
protocol entirely from the TNC, turning the TNC into a simple modem. The
TNC\'s sole responsibilities are to handle the physical layer (e.g.,
modulating and demodulating audio tones) and the data link layer framing
(e.g., converting between asynchronous serial data and synchronous HDLC
frames for radio transmission).^3^ All higher-level logic, including the
construction and parsing of AX.25 packets, connection management, and
state tracking, becomes the responsibility of the host software.^3^ This
architectural decision is the primary reason for the protocol\'s lack of
features like flow control or error correction on the host-TNC link;
these functions are expected to be handled by higher-level protocols
operating end-to-end over the radio link.^3^

#### 1.1.1 Data Encapsulation (SLIP Framing)

To achieve its goal, the KISS protocol adopts the framing mechanism from
the Serial Line Internet Protocol (SLIP).^1^ This provides a simple
method for delimiting data frames over an asynchronous serial
connection. Each frame is encapsulated by special characters, and a
byte-stuffing mechanism ensures that these special characters can be
transmitted as part of the data payload without being misinterpreted.

The special characters are ^1^:

- **FEND (Frame End):** The byte \$0xC0\$. This character marks both the
  beginning and the end of every KISS frame. A receiver can synchronize
  by discarding bytes until it sees a FEND, after which it begins
  accumulating the frame.

- **FESC (Frame Escape):** The byte \$0xDB\$. This is the escape
  character, used to signal that the following byte has a special
  meaning.

- **TFEND (Transposed FEND):** The byte \$0xDC\$. If a literal \$0xC0\$
  (FEND) byte needs to be transmitted within the data payload, it is
  replaced by the two-byte sequence \$0xDB, 0xDC\$ (FESC, TFEND).

- **TFESC (Transposed FESC):** The byte \$0xDD\$. Similarly, if a
  literal \$0xDB\$ (FESC) byte needs to be transmitted, it is replaced
  by the two-byte sequence \$0xDB, 0xDD\$ (FESC, TFESC).

The host application\'s parser must correctly handle this un-escaping on
received frames, and its frame generator must correctly perform the
escaping on transmitted frames.

#### 1.1.2 Serial Link Parameters

The standard asynchronous serial link for KISS communication is
configured with 8 data bits, 1 stop bit, and no parity (8N1).^3^ A
critical implementation detail is that software flow control (XON/XOFF)
must be disabled. The XON (

0x11) and XOFF (0x13) characters could appear in the binary data stream
of an AX.25 packet, and if software flow control is enabled, the serial
driver would intercept these bytes, corrupting the data and causing the
communication to fail. Hardware flow control (RTS/CTS) can be used if
the hardware and cable support it, but often the most reliable
configuration is no flow control at all, with the host application
managing data flow through its own buffering.^4^

### 1.2 Standard KISS Frame Structure

A standard KISS frame is elegantly simple, consisting of only a few
components. The structure is as follows:

FEND \| Type Indicator \| Data Payload \| FEND

- **FEND:** As described above, the \$0xC0\$ byte marks the start and
  end of the frame.

- **Type Indicator:** This is the first byte following the initial FEND.
  It is a crucial byte that is divided into two 4-bit nibbles, each with
  a distinct purpose.^3^

  - **High-Order Nibble (Bits 4-7): Port Identifier.** This nibble
    specifies a logical TNC port, from 0 to 15. For a TNC connected to a
    single radio, this value is always 0. For multi-port TNCs, this
    allows the host to direct commands and data to a specific radio
    interface.^2^ Port\
    \$0xF\$ is reserved.

  - **Low-Order Nibble (Bits 0-3): Command Code.** This nibble specifies
    the command, indicating how the TNC should interpret the data
    payload that follows.^2^

- **Data Payload:** The content of this field is determined by the
  Command Code. For the most common command, Data Frame (0x0), this
  payload consists of the raw data to be transmitted, typically a fully
  formed AX.25 frame.^1^ The maximum size of this payload is limited
  only by the TNC\'s available buffer memory.^1^

- **Frame Directionality:** An important rule in the KISS specification
  is the directionality of commands. The host computer can send any
  valid command to the TNC. However, the TNC should only ever send Data
  Frame commands (command code 0x0) to the host, containing data
  received from the radio channel.^1^ While this is the standard, some
  TNCs violate this rule with their own extensions.^6^

### 1.3 Standard Command Set Analysis

The KISS protocol defines a small set of commands for configuring the
TNC\'s medium access parameters. These commands are sent from the host
to the TNC. The command code is placed in the low nibble of the Type
Indicator byte, and the port is specified in the high nibble. For a
single-port TNC, the Type Indicator for TXDELAY would be \$0x01\$, for P
would be \$0x02\$, and so on.

The standard commands are as follows ^3^:

- **Command 0: Data Frame.** The payload is raw data (e.g., an AX.25
  frame) to be transmitted on the specified port.

- **Command 1: TXDELAY.** The single byte of data following the Type
  Indicator is the transmitter key-up delay in 10 ms units. A value of
  50 corresponds to a 500 ms delay. This allows the transmitter to
  stabilize before data is sent.

- **Command 2: P.** The next byte is the persistence parameter, used for
  the p-persistent CSMA/CD (Carrier Sense Multiple Access with Collision
  Detection) algorithm. The value p (a probability from 0 to 1) is
  scaled to a byte value P using the formula P=p×256−1. The default
  value is typically 63, which corresponds to p≈0.25.

- **Command 3: SlotTime.** The next byte is the slot time for the CSMA
  algorithm, in 10 ms units. The default is 10, for a 100 ms slot time.

- **Command 4: TXtail.** The next byte specifies the time to keep the
  transmitter keyed up after the final frame check sequence (FCS) has
  been sent, in 10 ms units. This command is considered obsolete but is
  included for compatibility with older implementations.

- **Command 5: FullDuplex.** The next byte specifies the duplex mode. A
  value of 0 indicates half-duplex (the default), where the TNC will use
  CSMA. A non-zero value indicates full-duplex, where CSMA is disabled
  and the TNC transmits immediately.

- **Command 6: SetHardware.** This command code is a gateway for
  vendor-specific functionality. The format and meaning of the data
  payload are defined by the TNC manufacturer.

- **Command 255 (0xFF): Exit KISS Mode.** This is a special command, not
  a standard configuration parameter. A frame consisting of \$0xC0,
  0xFF, 0xC0\$ is sent to the TNC to instruct it to leave KISS mode and
  return to its native command-line interface.^4^

### 1.4 Analysis of Common Non-Standard Extensions

The simplicity of the KISS protocol is both its greatest strength and
its most significant weakness. The lack of features like multi-device
management, error checking, and support for new digital modes created a
functional vacuum that the amateur radio community has filled with a
variety of powerful but incompatible extensions. A modern, robust
application must be aware of these \"dialects\" of KISS.

- **G8BPQ Multi-Drop and Extended KISS:** Developed by John Wiseman,
  G8BPQ, these extensions are designed to overcome several of the
  original protocol\'s limitations, particularly for building complex
  packet radio nodes.^5^

  - **Multi-Drop Addressing:** This extension re-purposes the port
    nibble of the Type Indicator byte as a unique TNC address (0-15).
    This allows multiple TNCs to be connected to a single host serial
    port in a \"multi-drop\" configuration, with each TNC only
    responding to frames containing its specific address.^5^

  - **Polled Mode (Command \$0xE\$):** In this mode, TNCs remain silent
    and do not send received data to the host until they are explicitly
    polled by the master with a poll frame (\$C0, xE, C0\$, where x is
    the TNC address). This prevents data collisions on the shared serial
    line from multiple TNCs trying to talk at once.^5^

  - **Acknowledgement Mode (Command \$0xC\$):** Primarily for use on
    unreliable HF links, this mode provides a confirmation from the TNC
    to the host that a packet has been successfully transmitted over the
    air. This allows the host software to manage retransmissions and
    timeouts more accurately.^5^

  - **Checksum Mode:** This adds a simple 8-bit XOR checksum byte to the
    frame, placed just before the final FEND. This provides a layer of
    error detection for the serial link itself, which is absent in the
    original specification.^5^

- **M17 Protocol Extensions:** The M17 project, a new open-source
  digital voice and data protocol, has defined its own extensions to
  KISS to transport M17 frames. In this model, the host computer is
  responsible for all Codec2 voice encoding, and the TNC is responsible
  for M17 frame construction, FEC, interleaving, and 4-FSK baseband
  modulation.^2^ This demonstrates how the KISS framework is being
  adapted to serve as a transport layer for entirely new digital modes
  beyond traditional AX.25.

- **Fldigi Software TNC Extensions:** The popular digital modem software
  Fldigi can act as a software-based KISS TNC. It implements a vast,
  non-standard command set tunneled through the SetHardware (Command 6)
  and RAW (Command 7, another non-standard assignment) commands. These
  are not single-byte parameters but rather human-readable ASCII strings
  like MODEM:PSK63RC32 or SQLS:50. This allows a host application to
  query and configure nearly every aspect of Fldigi\'s DSP engine,
  including modem type, waterfall frequency, squelch levels, and RSID
  settings.^7^ This represents the most significant departure from the
  original KISS philosophy, turning the simple protocol into a rich
  remote-procedure-call mechanism.

- **Bluetooth LE (BLE) KISS API:** This is not an extension to the KISS
  frame format itself, but rather a transport-layer specification for
  sending KISS frames over Bluetooth Low Energy. It defines specific
  GATT Service and Characteristic UUIDs for transmitting
  (KTS_TX_CHAR_UUID) and receiving (KTS_RX_CHAR_UUID) KISS data. The
  application\'s Bluetooth stack is responsible for discovering these
  services and writing/reading the raw, KISS-framed byte arrays to/from
  these characteristics. The TNC and host must still handle the standard
  KISS framing and byte-stuffing as if the data were coming over a
  serial line.^6^

The existence of these varied and incompatible extensions means that an
application cannot simply claim to \"support KISS.\" It must be
architected to support specific profiles or dialects of KISS. For
example, to function as a network node controller, it would need to
support the G8BPQ extensions. To interface with modern digital voice
systems, it might need to support the M17 extensions. And to deeply
integrate with a software modem like Fldigi, it would need to implement
the Fldigi-specific ASCII command set. This reality dictates a modular
TNC interface within the application, capable of loading different
protocol handlers based on the connected TNC\'s capabilities.

  -------------------------------------------------------------------------
  Command (Hex)     Port Nibble (Hex) Command Name      Description and
                                                        Payload Format
  ----------------- ----------------- ----------------- -------------------
  0x0               0x0 - 0xE         **Data Frame**    The most common
                                                        command. The
                                                        payload is a
                                                        complete data
                                                        packet (e.g., AX.25
                                                        frame) to be
                                                        transmitted. From
                                                        TNC to host, this
                                                        is the only
                                                        standard command,
                                                        carrying a received
                                                        packet. ^1^

  0x1               0x0 - 0xE         **TXDELAY**       Sets transmitter
                                                        key-up delay.
                                                        Payload is 1 byte
                                                        representing delay
                                                        in 10 ms units
                                                        (e.g., 50 for 500
                                                        ms). ^3^

  0x2               0x0 - 0xE         **P**             Sets the CSMA
                                                        persistence
                                                        parameter p.
                                                        Payload is 1 byte,
                                                        P, where P=p×256−1.
                                                        ^3^

  0x3               0x0 - 0xE         **SlotTime**      Sets the CSMA slot
                                                        time. Payload is 1
                                                        byte representing
                                                        time in 10 ms units
                                                        (e.g., 10 for 100
                                                        ms). ^3^

  0x4               0x0 - 0xE         **TXtail**        Obsolete. Sets
                                                        post-transmission
                                                        key-up time.
                                                        Payload is 1 byte
                                                        in 10 ms units. ^3^

  0x5               0x0 - 0xE         **FullDuplex**    Sets duplex mode.
                                                        Payload is 1 byte:
                                                        0 for half-duplex
                                                        (CSMA enabled),
                                                        non-zero for
                                                        full-duplex (CSMA
                                                        disabled). ^3^

  0x6               0x0 - 0xE         **SetHardware**   Vendor-specific
                                                        command. Payload
                                                        format is defined
                                                        by the TNC
                                                        manufacturer. Used
                                                        by Fldigi for
                                                        extensive ASCII
                                                        commands. ^3^

  0x7               0x0 - 0xE         **RAW** (Fldigi)  Non-standard Fldigi
                                                        extension to pass
                                                        non-HDLC encoded
                                                        data. ^7^

  0xC               0x0 - 0xE         **ACK Mode**      Non-standard G8BPQ
                                      (G8BPQ)           extension. TNC
                                                        sends an
                                                        acknowledgment back
                                                        to the host after
                                                        successful
                                                        transmission over
                                                        the air. ^5^

  0xE               0x0 - 0xE         **Poll** (G8BPQ)  Non-standard G8BPQ
                                                        extension. Master
                                                        polls a specific
                                                        TNC (addressed by
                                                        port nibble) for
                                                        data. ^5^

  0xFF              0xF               **Exit KISS**     Special command
                                                        frame (C0 FF C0) to
                                                        exit KISS mode and
                                                        return the TNC to
                                                        its native command
                                                        interface. ^4^
  -------------------------------------------------------------------------

## Section 2: Comparative Analysis of Target TNC Hardware

The choice of TNC hardware has significant implications for the software
architecture. The two devices under analysis, the Mobilinkd TNC3/4 and
the Byonics TinyTrak4, represent fundamentally different design
philosophies that necessitate different integration strategies.

### 2.1 Mobilinkd TNC3/4 Technical Profile

The Mobilinkd TNC3 and its successor, the TNC4, are modern, compact,
battery-powered devices designed primarily for portable and mobile
packet radio operations, especially APRS.^9^ They function as pure KISS
modems, offloading all protocol logic to the host device and possessing
no standalone intelligence such as digipeating or mail-forwarding
capabilities.^10^

#### 2.1.1 Hardware and Capabilities

The TNC3 and TNC4 are capable of standard 1200 baud AFSK packet radio,
which is the workhorse for APRS on VHF/UHF. They also support 9600 baud
GFSK/GMSK operation, though this requires a radio specifically designed
for high-speed data and careful audio level calibration.^10^ The TNC3
uses a Micro-USB connector for charging and data, while the TNC4
upgrades this to a more modern USB-C connector.^10^ Both devices are
built around an STM32 microcontroller.^12^

#### 2.1.2 Connection Interface Analysis

The Mobilinkd TNCs offer modern, flexible connectivity options that are
central to their design:

- **Bluetooth:** This is the primary intended connection method. The
  TNCs support two Bluetooth modes:

  1.  **Bluetooth SPP (Serial Port Profile):** This mode provides a
      virtual serial port over Bluetooth, ensuring broad compatibility
      with Android, Windows, macOS, and Linux systems that have
      Bluetooth capabilities.^10^ This is the most common connection
      method for desktop and Android applications.

  2.  **Bluetooth LE (Low Energy):** The TNCs also implement a custom
      GATT service for KISS over BLE. This is particularly important for
      iOS devices, which have more streamlined support for BLE than for
      SPP.^9^ The implementation follows the \"KISS over BLE\"
      specification, which defines specific UUIDs for transmit and
      receive characteristics.^6^

- **USB:** The USB port on both devices is not just for charging; it
  also presents itself to the host operating system as a **USB CDC
  (Communications Device Class)** device. This means that when plugged
  in, the TNC appears as a standard virtual serial/COM port, requiring
  no special drivers on modern versions of Windows, macOS, or Linux.^10^
  This provides a highly reliable, wired connection option for desktop
  use.

#### 2.1.3 KISS Protocol Implementation and Configuration

The Mobilinkd TNCs adhere to a strict interpretation of the KISS
philosophy. They operate as a transparent data pipe. Critically, their
operational parameters are **not** configured using the standard in-band
KISS commands (e.g., TXDELAY, P).

Instead, all configuration is performed out-of-band using a dedicated
graphical application provided by Mobilinkd for Android and iOS.^9^ This
app connects to the TNC (likely via a proprietary BLE service or using
the

SetHardware command space) and allows the user to set parameters such
as:

- **Audio Levels:** Input and output volume.

- **PTT Style:** Simplex (separate PTT line) or Multiplex (PTT signal on
  the mic line).

- **KISS Parameters:** TX Delay, Persistence, Slot Time, etc.

These settings are then saved to the TNC\'s internal non-volatile
memory.^10^ From the perspective of the amateur radio application being
developed, the Mobilinkd TNC is a pre-configured device. The
application\'s responsibility is not to configure it, but simply to
connect to its serial interface (be it over USB or Bluetooth) and start
sending and receiving KISS frames. Firmware updates are also handled
externally, via a USB connection in DFU (Device Firmware Update) mode
using standard STMicroelectronics programmer software.^10^

### 2.2 Byonics TinyTrak4 Technical Profile

The Byonics TinyTrak4 (TT4) is a product from a different era and with a
different philosophy. It is a highly versatile and configurable device
aimed at the hobbyist and experimenter market. It is available both as a
through-hole kit for self-assembly and as a pre-built surface-mount
unit.^15^

#### 2.2.1 Hardware and Operational Modes

Unlike the single-purpose Mobilinkd TNC, the TinyTrak4 can be configured
to operate in several distinct modes, including ^17^:

- **APRS Tracker:** Its primary function, where it can take NMEA data
  from a GPS and automatically transmit position beacons.

- **UI TNC:** A simple terminal mode for sending and receiving text
  messages.

- **KISS TNC:** The mode of interest for this project, where it
  functions as a standard KISS-compliant TNC.

It is crucial that the host application ensures the TT4 is in the
correct mode before attempting to use it.

#### 2.2.2 Connection Interface Analysis

The TT4\'s connection methods reflect its more traditional, wired-first
design:

- **Serial (DB-9):** The primary data interface is a standard male DB-9
  connector (J2) providing an RS-232 serial port.^17^ To connect this to
  any modern computer, a USB-to-Serial adapter is required. Byonics
  sells a branded \"TT USB cable\" which integrates this adapter.^18^

- **Bluetooth:** Wireless connectivity is not built-in. It is available
  via an optional **TT4BT Bluetooth adapter** module, which plugs
  directly into the TT4\'s DB-9 serial port. This add-on module then
  provides a standard Bluetooth SPP (Serial Port Profile)
  connection.^19^

#### 2.2.3 KISS Protocol Implementation and Configuration

The TinyTrak4\'s configuration method is fundamentally different from
the Mobilinkd\'s.

- **KISS Implementation:** When the TT4\'s firmware is set to AMODE
  KISS, it behaves as a standard KISS TNC, sending and receiving
  KISS-framed data over its serial port.^17^

- **Configuration Method:** All configuration is performed via a
  **text-based command-line interface** over the serial connection. To
  enter configuration mode, a user (or an application) must connect to
  the serial port at 19200 baud and send the ESC key three times in
  quick succession.^18^ This brings up a command prompt (\
  :). From there, text commands are used to set all parameters, such as
  CALLSIGN N0CALL, TXDELAY 30, or, most importantly, AMODE KISS to put
  the device into KISS mode.^17^ To exit configuration mode and begin
  operation, the\
  QUIT command is used.^18^

This command-line interface presents both a challenge and an
opportunity. The challenge is that the device must be correctly
configured before use. The opportunity is that the application can
provide a significant value-add by creating a graphical configuration
panel that abstracts this CLI away from the user, programmatically
sending the necessary text commands over the serial port to configure
the device on the fly.

### 2.3 Synthesis and Implementation Recommendations

The architectural approaches required to support these two devices are
distinct due to their differing product philosophies.

- **For the Mobilinkd TNC3/4:** The primary development effort lies in
  creating a robust, cross-platform ConnectionManager. This module must
  be capable of discovering and managing serial port connections over
  both physical USB (as a USB CDC device) and wireless Bluetooth (as an
  SPP device). The application does not need to handle TNC
  configuration; its role is to treat the TNC as a simple,
  pre-configured KISS data pipe. The user documentation should instruct
  users to configure their TNC using the official Mobilinkd mobile app.

- **For the Byonics TinyTrak4:** The development effort is twofold. It
  requires the same robust ConnectionManager to handle physical and
  virtual serial ports. However, to provide a seamless user experience,
  it also requires a ConfigurationManager. This module would be
  responsible for scripting the text-based command interface. Upon
  connecting, it would first query the current mode and, if necessary,
  send the commands to enter configuration mode, set AMODE KISS,
  configure other parameters like TXDELAY based on user settings in the
  application\'s GUI, and then issue the QUIT command to begin KISS
  operation. A basic implementation could skip this and require the user
  to configure the TT4 manually, but an advanced implementation with a
  built-in configuration GUI would be far superior.

This distinction is critical for project planning. Supporting the
Mobilinkd TNC is primarily a connectivity and I/O challenge. Supporting
the TinyTrak4 is a connectivity, I/O, *and* protocol-scripting
challenge.

  -----------------------------------------------------------------------
  Feature                 Mobilinkd TNC3/4        Byonics TinyTrak4
  ----------------------- ----------------------- -----------------------
  **Primary Function**    Pure KISS Modem         Multi-mode (Tracker, UI
                                                  TNC, KISS TNC)

  **Connection Methods**  **Built-in:** Bluetooth **Built-in:** DB-9
                          SPP, Bluetooth LE, USB  Serial (RS-232).
                          CDC (Serial) ^10^       **Requires adapter:**
                                                  USB-to-Serial,
                                                  Bluetooth Module
                                                  (TT4BT) ^18^

  **Configuration         Out-of-band via         In-band via serial
  Interface**             dedicated iOS/Android   terminal command-line
                          App ^11^                interface (19200 baud,
                                                  ESCx3) ^17^

  **Application\'s Role** Connect to serial       Connect to serial
                          interface and use as a  interface. Optionally,
                          data pipe.              script commands to
                                                  configure the TNC. Must
                                                  ensure AMODE KISS is
                                                  set.

  **Power Source**        Internal rechargeable   External 6-18V DC power
                          battery, USB power ^10^ source ^16^

  **Form Factor**         Small, self-contained,  PCB, available as a kit
                          portable unit ^9^       or built, often placed
                                                  in a project box ^15^

  **Firmware Updates**    USB DFU mode with       Serial port bootloader
                          STM32CubeProgrammer     ^17^
                          ^11^                    
  -----------------------------------------------------------------------

## Section 3: Cross-Platform Implementation and Management

Developing a software module that can reliably communicate with TNCs
across Windows, macOS, and Linux requires careful architectural
planning. The greatest challenge is not in parsing the KISS protocol
itself, but in robustly managing the fragile, stateful, and error-prone
serial connection that underlies it.

### 3.1 Strategies for Serial Port Discovery and Enumeration

Before a connection can be established, the application must discover
which serial ports are available on the system. This process is highly
dependent on the operating system.

- **Windows:** Serial ports are identified as COMx (e.g., COM3).
  Enumeration can be achieved through various methods in the Win32 API,
  such as querying the registry under
  HKEY_LOCAL_MACHINE\\HARDWARE\\DEVICEMAP\\SERIALCOMM or using the more
  modern SetupDiGetClassDevs function. Both physical RS-232 ports and
  virtual ports created by USB-to-Serial adapters (like FTDI or Prolific
  chips) and Bluetooth SPP connections will appear in this list.

- **macOS & Linux (POSIX):** On POSIX-compliant systems, serial ports
  are represented as device files in the /dev/ directory. The
  application must enumerate the contents of this directory and filter
  for common naming conventions.

  - **Linux:** USB serial devices typically appear as /dev/ttyUSBx or
    /dev/ttyACMx. Bluetooth SPP connections, if configured manually with
    rfcomm, appear as /dev/rfcommx.

  - **macOS:** USB serial devices follow a more descriptive naming
    scheme, such as /dev/tty.usbserial-A50285BI or
    /dev/tty.usbmodem1411. Bluetooth devices appear as
    /dev/tty.DeviceName-SPP.

Given these significant platform differences, writing platform-specific
code for enumeration is tedious and error-prone. It is strongly
recommended to use a well-vetted, cross-platform serial library.
Libraries such as **Boost.Asio** provide a powerful, asynchronous I/O
framework that includes serial port support.^21^ Another excellent, more
lightweight option is

**wjwwood/serial**, a C++ library specifically designed for
cross-platform serial communication with an API modeled after
PySerial.^24^ These libraries provide a unified function (e.g.,

serial::list_ports()) that abstracts away the OS-specific details of
enumeration.

### 3.2 Designing a Robust Connection State Machine

A simple \"open port, read/write, close port\" model is insufficient for
a real-world application where connections can be unstable. A formal
connection state machine is essential for managing the TNC\'s lifecycle
robustly. This state machine should, at a minimum, include the following
states:

- DISCONNECTED: The initial and final state. No active connection.

- CONNECTING: The application is attempting to open the serial port and
  establish communication.

- CONNECTED: The serial port is open, and the application is actively
  sending/receiving data.

- DISCONNECTING: The application is in the process of gracefully closing
  the connection.

- RECONNECTING: A previously established connection was lost
  unexpectedly (e.g., USB unplugged), and the application is
  periodically attempting to re-establish it without user intervention.

The application logic must correctly manage transitions between these
states. For example, a user clicking \"Connect\" transitions from
DISCONNECTED to CONNECTING. A successful port open transitions to
CONNECTED. An unexpected read error or device removal event transitions
from CONNECTED to RECONNECTING. This approach ensures that the
application\'s UI and internal logic always have a clear and accurate
understanding of the TNC\'s status, preventing crashes and providing a
smooth user experience. This model aligns with the principles of
reliable transport connection management, where maintaining a consistent
view of the connection state is paramount.^25^

### 3.3 Advanced Error Handling and Recovery

The base KISS protocol provides no checksums or error detection for the
serial link.^3^ Therefore, the host application must be defensively
programmed to handle a wide range of potential errors.

- **Connection Errors:** The application must gracefully handle failures
  when opening a port. Common errors include the port not existing, or
  the port being in use by another application (\"Access Denied\"). The
  user should be presented with a clear, informative error message.

- **I/O Timeouts:** All read and write operations on the serial port
  must have timeouts. A blocking read with no timeout can cause the
  entire application to hang if the TNC stops sending data. On POSIX
  systems, timeouts can be controlled at a low level using the VMIN and
  VTIME settings in the termios struct.^26^ However, modern C++ serial
  libraries provide much simpler, higher-level mechanisms for specifying
  read/write timeouts as part of the function call.^24^

- **Framing and Data Corruption Errors:** The serial link can be noisy,
  especially with poor cabling or RF interference. The application\'s
  KISS frame parser must be resilient. It should not crash upon
  receiving malformed data. If it receives bytes that do not conform to
  the FEND-delimited, byte-stuffed structure, it should discard the
  corrupted data, log an error, and attempt to re-synchronize by
  scanning for the next valid FEND byte.

- **Physical Disconnection:** This is the most common and disruptive
  error. USB cables can be unplugged, and Bluetooth devices can go out
  of range or lose power. The application must detect this. This is
  typically done in a dedicated monitoring thread or through the
  asynchronous error-handling mechanisms of a library like Boost.Asio.
  When a disconnection is detected, the state machine should transition
  to RECONNECTING. In this state, the application should periodically
  re-run the port enumeration logic. If the device reappears (e.g., the
  USB cable is plugged back in), the application can automatically
  re-establish the connection, restoring functionality without requiring
  the user to restart the program.

### 3.4 Data Buffering and Flow Control Emulation

The original KISS specification makes a dangerous assumption: that the
TNC has sufficient buffer memory to handle whatever the host sends
it.^3^ This is often not true, especially with older hardware or when
the host can generate data far faster than the slow radio channel can
transmit it.

- **Transmit Buffering:** The application must implement its own
  transmit queue (e.g., a thread-safe FIFO queue). When the user or
  application logic generates a packet to be sent, it should be placed
  in this queue. A separate worker thread should be responsible for
  dequeuing packets one at a time and writing them to the serial port.
  This decouples the UI/logic threads from the slow I/O operations,
  ensuring the application remains responsive. It also naturally
  throttles the data flow to the TNC, as a new packet will not be sent
  until the previous one has been fully written to the serial port.

- **Receive Buffering:** While the operating system\'s serial driver
  provides some level of input buffering, it is best practice for the
  application to have its own internal circular buffer. A dedicated
  reading thread should do nothing but read data from the serial port as
  it arrives and place it into this buffer. A separate processing thread
  can then consume data from the circular buffer, parse it for KISS
  frames, and dispatch the data to the rest of the application. This
  architecture ensures that even if the main application is busy
  processing a complex packet or updating the UI, incoming serial data
  is not lost due to an OS buffer overrun.

This robust, multi-threaded, and state-aware approach to serial port
management is the true foundation of a stable TNC integration. The
investment in this infrastructure will pay significant dividends in
application reliability and user satisfaction.

# Part II: An Analysis of SDR Integration Methods and Remote Protocols

This part of the report provides a technical overview of strategies for
integrating with local Software-Defined Radios, with a focus on SDRUno,
and analyzes the network protocols required to connect to popular remote
SDR servers and public audio streams.

## Section 4: Local SDR Integration Strategy with SDRUno

SDRUno is a popular, high-performance SDR application platform developed
by SDRplay, primarily optimized for their line of RSP (Radio Spectrum
Processor) devices.^27^ While powerful as a standalone application,
integrating it with third-party software presents unique challenges, as
it was not designed as an open backend for other programs.

### 4.1 Overview of SDRUno Architecture and Inter-Process Communication (IPC)

SDRUno is a closed-source, modular Windows application.^27^ Unlike
platforms like GNU Radio, it does not expose a public, documented API
for developers to directly link against or to access the raw I/Q data
stream programmatically from another process. Consequently, integration
must rely on indirect Inter-Process Communication (IPC) mechanisms that
treat SDRUno as a \"black box\" device. The primary methods for this are
Virtual Audio Cables for audio transport and CAT emulation for receiver
control.

### 4.2 Audio Integration via Virtual Audio Cable (VAC)

This is the most common, reliable, and vendor-sanctioned method for
extracting demodulated audio from SDRUno and feeding it into an external
application, such as a digital mode decoder.

- **Mechanism:** The process relies on a third-party VAC driver, such as
  VB-CABLE (donationware) or Virtual Audio Cable (paid). These drivers
  create a pair of virtual audio devices in the Windows sound system: a
  virtual output (playback) device and a virtual input (recording)
  device. Audio sent to the playback device is internally routed
  directly to the recording device with no physical hardware
  involved.^29^

- **SDRUno Configuration:** Within the SDRUno software, the user
  navigates to the RX CONTROL panel, clicks the SETTINGS button, and
  selects the OUT tab. In the WME dropdown menu, they select the
  playback device corresponding to the installed VAC (e.g., \"CABLE
  Input (VB-Audio Virtual Cable)\").^29^ SDRUno will now send all of its
  demodulated audio output to this virtual device instead of the system
  speakers.

- **Application Configuration:** The target application, in turn, is
  configured to use the corresponding VAC recording device (e.g.,
  \"CABLE Output (VB-Audio Virtual Cable)\") as its audio input source.
  This allows the application to receive the high-quality, digital audio
  stream from SDRUno for processing.

- **Limitations and Trade-offs:** While effective, this method has
  drawbacks. It only provides access to the final, demodulated audio
  stream, not the wideband I/Q data. This precludes any custom DSP or
  the ability to decode multiple signals within the passband
  simultaneously. The process is also subject to the latencies and
  potential sample-rate conversion issues of the Windows audio subsystem
  and requires the user to install and configure multiple pieces of
  software correctly.

### 4.3 Remote Control via CAT Emulation

To allow external applications to control its receiver functions
(frequency, mode, etc.), SDRUno can emulate a physical hardware
transceiver using the Computer Aided Transceiver (CAT) protocol.

- **Mechanism:** SDRUno specifically emulates a Kenwood TS-480
  transceiver. This communication occurs over a serial port. For IPC on
  a single machine, a virtual serial port driver (e.g., com0com) is
  required to create a linked pair of virtual COM ports.^29^

- **SDRUno Configuration:** In the RX CONTROL panel\'s SETTINGS window,
  the user selects the CAT tab. Here, they can enable CAT control and
  select one of the virtual COM ports from the pair (e.g., COM10) and
  set the baud rate (e.g., 4800).^30^

- **Application Configuration:** The target application then connects to
  the other port in the virtual pair (e.g., COM11). By sending standard
  Kenwood TS-480 command sequences to this port, the application can
  control SDRUno\'s tuning frequency, change modulation mode (AM, FM,
  SSB), and query the current status, just as if it were controlling a
  physical radio.

- **Benefit:** This provides a standardized, well-documented, and stable
  method for receiver control, enabling features like automated scanning
  or integration with logging software. The combination of CAT control
  and VAC audio piping effectively allows a third-party application to
  use SDRUno as a high-performance, software-based receiver.

### 4.4 Analysis of the SDRUno Plugin System

SDRUno features a plugin system that allows for the loading of external
DLLs to extend its functionality.^28^ This presents the most powerful
but also the most problematic path for deep integration.

- **Official Status and Documentation:** There is no officially
  published or supported Software Development Kit (SDK) or API
  documentation for the SDRUno plugin system.^32^ SDRplay provides
  source code for ExtIO plugins, but this is a legacy standard for other
  applications to use SDRplay hardware; it is not the native SDRUno
  plugin API.^33^

- **Community-Driven Reverse Engineering:** All public knowledge about
  the plugin architecture comes from the efforts of community developers
  who have reverse-engineered the interface by analyzing the SDRUno
  executable and existing plugins. The most prominent source of example
  code is the GitHub repository of Jan van Katwijk
  (JvanKatwijk/unoPlugins-jan), which contains plugins for various
  digital modes like FT8, WSPR, and RTTY.^34^

- **Implementation Details:** Plugins are standard Windows DLLs written
  in C++. To create a plugin, a developer would need to study the source
  code of existing community plugins to replicate the necessary exported
  functions, data structures, and message-passing conventions that
  SDRUno expects. This would allow for direct access to the audio stream
  within the SDRUno process, eliminating the need for a VAC.

- **Recommendation and Risk Assessment:** Attempting to build a custom
  plugin for integration is a high-risk, high-reward endeavor. The
  primary benefit would be a seamless user experience with no external
  software or configuration required. The significant risk is that the
  plugin API is undocumented and subject to change without notice. Any
  update to SDRUno could break the plugin, requiring a new
  reverse-engineering effort. Therefore, this path should be considered
  an advanced research and development task, not a core requirement for
  the initial product release.

### 4.5 Network Streaming Capabilities

A common requirement for modern SDR applications is the ability to
stream data over a network.

- **SDRUno Native Capabilities:** The SDRUno platform itself does
  **not** include a built-in network server for streaming I/Q or audio
  data to remote clients.^35^ Its architecture is focused on local
  operation.

- **SDRplay\'s Strategic Direction: SDRconnect:** SDRplay\'s newer
  software platform, **SDRconnect**, is their strategic solution for
  network streaming. SDRconnect is designed from the ground up with a
  client-server architecture, including a headless server component that
  can run on various platforms (including Raspberry Pi) and stream data
  over a LAN or WAN to a client on Windows, macOS, or Linux.^37^ SDRplay
  has also indicated that a plugin API for SDRconnect will be
  forthcoming.^39^

- **Workarounds:** For LAN-only use, it is possible to use third-party
  USB-over-IP software like VirtualHere to share an SDRplay device
  across a network. The remote computer sees the SDR as if it were
  physically plugged in. However, this method streams the raw
  high-bandwidth USB data and is not efficient, not suitable for WAN
  use, and is not a true client-server streaming solution.^40^

For the development team, this information leads to a clear conclusion:
the most stable and supportable method for integrating with the
*current* SDRUno platform is the combination of Virtual Audio Cable and
CAT emulation. This approach is indirect and requires user setup but
relies on stable, well-understood mechanisms. For future development and
true network capability, efforts should be directed towards integrating
with the newer SDRconnect platform and its eventual plugin API, as this
is the clear strategic path endorsed by the hardware vendor.

## Section 5: Remote SDR Server Protocol Analysis

Connecting to remote SDRs shared over the internet is a key feature for
a modern amateur radio application. This requires implementing
client-side support for several popular but distinct network protocols.
This section deconstructs the protocols for Spyserver, WebSDR, and
KiwiSDR.

### 5.1 Spyserver Protocol Deep Dive

Spyserver is the network streaming protocol developed for the Airspy
family of SDRs and is integrated into the popular SDR# software.^41^ It
is designed to be highly efficient, making it well-suited for use over
standard internet connections.

- **Architecture:** Spyserver employs a client-server architecture where
  the server is connected to the SDR hardware (e.g., Airspy or
  RTL-SDR).^41^ A key design principle is that the server performs the
  initial high-rate sampling and digital signal processing. It does not
  stream the raw, wideband I/Q data from the SDR. Instead, it streams
  only the data relevant to the client\'s tuned frequency, dramatically
  reducing bandwidth requirements compared to simpler protocols like\
  rtl_tcp.^41^

- **Connection and Handshake:** A client establishes a standard TCP
  connection to the Spyserver\'s IP address and port, which defaults to
  5555.^42^ The initial handshake involves the exchange of protocol
  information and device capabilities. The protocol itself does not
  appear to have a mandatory authentication layer, though server owners
  can restrict access by IP address.

- **Commands and Control:** The protocol allows a client to control the
  remote SDR. When a single client is connected, it has full control
  over the device\'s center frequency and gain settings. However, when
  multiple clients are connected simultaneously, these controls become
  locked to prevent conflicts. All connected clients then share the same
  slice of the spectrum determined by the first client.^43^ Commands for
  changing frequency and gain are sent as specific messages from the
  client to the server over the TCP connection.

- **Data Stream Format:** The efficiency of Spyserver comes from its
  intelligent data streaming. The server sends two main types of data to
  the client:

  1.  **Tuned I/Q Data:** This is a narrow-band stream of I/Q samples
      corresponding only to the specific frequency and bandwidth the
      client has requested (e.g., a 10 kHz wide SSB signal). The server
      performs the necessary digital down-conversion (DDC) from the full
      spectrum. This data can be optionally compressed and is often sent
      as 8-bit PCM samples to further reduce bandwidth.^41^

  2.  **Compressed Waterfall Data:** To provide a wideband spectral
      display, the server calculates the FFT on the full bandwidth of
      the SDR, but sends only the resulting FFT bins to the client in a
      compressed format. This allows the client to display a full
      waterfall without receiving the full I/Q data stream.^41^

- **Implementation:** Implementing a Spyserver client would require
  reverse-engineering the protocol by analyzing the network traffic of
  an existing client like SDR# or by examining the source code of
  open-source clients if available. The server itself is configured via
  a simple text file, spyserver.conf.^44^

### 5.2 WebSDR Protocol Deep Dive

WebSDR, pioneered by PA3FWM, was one of the first systems to allow
multiple users to independently tune a single SDR over the internet
using only a web browser.^45^ Its protocol is designed around web-native
technologies.

- **Architecture:** A central server runs the WebSDR software, which is
  connected to the SDR hardware. This server hosts a website that users
  access with their browsers. The server handles all the DSP and streams
  demodulated audio and waterfall data to each connected client.^46^

- **Connection and Handshake:** The client (browser) establishes a
  **WebSocket** connection to the server. This provides a persistent,
  bidirectional communication channel for both control commands and data
  streaming.^47^

- **Commands and Control:** Control messages are sent from the client to
  the server over the WebSocket. Analysis of client-side JavaScript from
  WebSDR sites suggests that commands are sent as simple text strings,
  formatted similarly to an HTTP GET request query string (e.g., GET
  /\~\~param?f=7100&mode=lsb\...).^48^ Some open-source
  reimplementations of the concept use JSON-formatted objects for
  control messages over the WebSocket.^46^

- **Data Stream Format:** The server streams demodulated audio and
  waterfall data directly to the client over the WebSocket. The
  browser\'s JavaScript then uses the Web Audio API to play the audio
  and a Canvas element to render the waterfall.^49^

- **API Status and Development Risk:** This is the most critical point
  for developers. There is **no official, public API** for WebSDR.
  Furthermore, the author has explicitly stated that they do not wish
  for third-party clients to connect to their servers and that
  reverse-engineering is not permitted.^47^ While the legal
  enforceability of such a statement is debatable, it signals a clear
  intent. Any attempt to integrate with public WebSDR servers carries a
  high risk of being technically blocked by future server software
  updates or the application\'s IP being banned by server operators.
  This makes WebSDR a high-risk and unstable target for integration.

### 5.3 KiwiSDR Protocol Deep Dive

KiwiSDR is a popular open-hardware SDR platform consisting of a custom
cape for a BeagleBone single-board computer.^50^ It runs its own web
server and provides a multi-user, web-based interface similar in concept
to WebSDR. Its open nature has made its protocol a de-facto standard.

- **Architecture:** The KiwiSDR is a self-contained network appliance.
  It connects to a local network via Ethernet and serves a web interface
  on port 8073.^51^ It supports up to four simultaneous, independent
  user connections, each with its own audio and waterfall stream.^53^

- **Connection and Handshake:** Like WebSDR, the KiwiSDR protocol is
  based on **WebSockets**. A client connects to the device at
  ws://\<ip_address\>:8073. Each connection receives a unique session
  ID. The protocol uses multiple WebSocket streams per user; for
  example, one for audio (\.../SND) and another for waterfall data
  (\.../W/F).^54^

- **Authentication:** The server owner can set a password. The protocol
  includes an authentication step in the handshake where the client
  sends a SET auth t=kiwi p=\<password\> command.^54^

- **Commands and Control:** The protocol is command-based and uses
  simple, human-readable ASCII text messages sent over the WebSocket.
  All control commands start with SET.

  - **Examples:** SET freq=7074.000 sets the frequency. SET mod=usb sets
    the mode. SET agc=on enables the AGC. SET zoom=6 sets the waterfall
    zoom level.^54^

  - **Keep-Alive:** The client must periodically send a SET keepalive
    message to the server. If the server does not receive this message
    within 60 seconds, it will assume the client has disconnected and
    will close the connection.^54^

- **Data Stream Format:** The server sends three main types of messages
  to the client:

  1.  **MSG:** These are text-based metadata and status messages,
      providing information like the server version, number of connected
      users, and configuration details.

  2.  **SND:** These messages contain the binary, compressed audio data
      for the tuned channel.

  3.  **W/F:** These messages contain the binary, compressed waterfall
      data.

- **API Status and Development Risk:** While there is no formal,
  published API specification document from the creators, the protocol
  has been thoroughly reverse-engineered by the community. Open-source
  projects like the Python kiwiclient provide a complete, working
  implementation that serves as an excellent reference.^55^ The use of
  third-party clients is common and generally accepted within the
  KiwiSDR community.^56^ This makes KiwiSDR a\
  **low-risk, highly viable target** for integration.

The clear difference in design philosophy and \"openness\" among these
three protocols has direct consequences for development planning.
Spyserver is efficient but proprietary. WebSDR is web-native but
actively hostile to third-party clients. KiwiSDR is also web-native but
has a de-facto open protocol due to its open-hardware roots and active
community. For building a reliable, long-term feature, prioritizing
KiwiSDR support is the most logical engineering decision.

  -------------------------------------------------------------------------------
  Feature           Spyserver             WebSDR (PA3FWM)   KiwiSDR
                    (Airspy/SDR#)                           
  ----------------- --------------------- ----------------- ---------------------
  **Transport       TCP                   WebSocket         WebSocket
  Protocol**                                                

  **Data Format**   Tuned I/Q (e.g.,      Demodulated       Demodulated Audio
                    8-bit PCM),           Audio, Waterfall  (compressed),
                    Compressed FFT        Data              Waterfall Data
                                                            (compressed)

  **Control         Proprietary binary    GET-like text     SET text commands
  Method**          commands              commands over     over WebSocket
                                          WebSocket         

  **Official API    None, proprietary     None, author      None, but a de-facto
  Status**                                discourages       standard exists via
                                          third-party       reverse-engineering
                                          clients ^47^      ^54^

  **Development     **Medium.** Protocol  **High.**         **Low.** Protocol is
  Risk**            is stable but         Protocol is       well-understood,
                    requires              undocumented and  stable, and used by
                    reverse-engineering   its use is        multiple third-party
                    the SDR# client.      discouraged,      clients.
                                          risking technical 
                                          blocks.           
  -------------------------------------------------------------------------------

## Section 6: Public Audio Stream Discovery and Integration

To simplify the process of finding and connecting to a remote receiver,
many users turn to aggregator websites. This section analyzes
Receiverbook.de, the most popular of these directories, and outlines a
practical strategy for integrating its listings into the application.

### 6.1 Analysis of the Receiverbook.de Platform

Receiverbook.de is a web-based directory that lists hundreds of publicly
accessible online SDR receivers from around the world.^58^ It is crucial
to understand that Receiverbook.de is

**not a streaming provider or a protocol**. It is an aggregator, a
phonebook for SDRs. It lists receivers running different software
platforms, including OpenWebRX, WebSDR, and KiwiSDR, and provides the
user with a name, description, and a direct URL to connect to the
receiver\'s own web interface.^59^

A thorough review of the platform and related documentation reveals that
there is **no public, documented REST API** for programmatically
querying the Receiverbook database.^60^ The site is designed exclusively
for human interaction through its web interface.

### 6.2 Reverse-Engineering Receiver Listing Data

Since a direct API is not available, programmatic access to the receiver
list must be achieved through other means. An analysis of the
Receiverbook open-source repository on GitHub (jketterl/receiverbook)
provides a clear picture of its architecture and points to a viable
strategy.^62^

The system consists of two main components:

1.  **crawler.js:** A Node.js script that acts as the data gatherer.
    This crawler periodically iterates through a list of known SDRs,
    connects to them, queries their status and configuration, and then
    populates a central database with the collected information.

2.  **web.js:** A Node.js web server application. When a user visits
    Receiverbook.de, this server queries the database and dynamically
    renders the HTML pages that are sent to the user\'s browser.

This architecture confirms that the receiver data is not exposed via a
public API endpoint. The only way for an external application to access
this data is to interact with the output of web.js. Therefore, the
application must engage in **web scraping**. This can be done by making
an HTTP GET request to the Receiverbook.de URL (e.g.,
https://www.receiverbook.de/?type=kiwisdr) and then parsing the returned
HTML content to extract the relevant information for each receiver: its
name, its direct URL (e.g., http://sdr.example.com:8073), and its type
(KiwiSDR, WebSDR, etc.). While functional, this method is brittle and
may break if the website\'s HTML structure changes.

### 6.3 A Proposed Strategy for Programmatic Receiver Discovery and Connection

A robust implementation of a \"receiver discovery\" feature requires a
multi-step, modular approach that separates the discovery process from
the connection process.

- **Step 1: Scrape Receiverbook.de.** The application should include a
  module responsible for scraping the Receiverbook website. This scraper
  should periodically (e.g., once per session or once per day) fetch the
  HTML for the receiver lists. It must then parse this HTML to build an
  internal list of receiver objects, each containing attributes for
  name, url, and type. This process should be run in a background thread
  to avoid blocking the UI.

- **Step 2: Filter and Present.** The scraped list of receivers should
  be presented to the user in a clean, filterable, and searchable
  interface. The user can then browse the list and select a receiver
  they wish to connect to.

- **Step 3: Instantiate the Correct Protocol Client.** This is the most
  critical architectural step. Based on the type attribute of the
  user-selected receiver, the application must use a factory or strategy
  pattern to instantiate the correct protocol-specific client module.

  - If the scraped type is \"KiwiSDR,\" the application should
    instantiate the KiwiSdrClient module (developed based on the
    analysis in Section 5.3).

  - If the scraped type is \"WebSDR,\" it should instantiate the
    WebSdrClient (from Section 5.2).

  - If the scraped type is \"OpenWebRX,\" it would require a client for
    that specific protocol.

- **Step 4: Establish Connection.** The instantiated client module then
  takes the url of the selected receiver and handles the entire process
  of establishing the connection, performing the protocol-specific
  handshake, sending control commands, and processing the incoming audio
  and waterfall data streams.

This architecture decouples the fragile scraping logic from the complex
but more stable protocol implementation logic. If the Receiverbook
website changes its layout, only the scraper module needs to be updated,
not the entire set of protocol clients. This approach transforms a
simple user request---\"let me connect to public SDRs\"---into a
well-defined and maintainable software architecture.

#### Works cited

1.  KISS (amateur radio protocol) - Wikipedia, accessed June 16, 2025,
    [[https://en.wikipedia.org/wiki/KISS\_(amateur_radio_protocol)]{.underline}](https://en.wikipedia.org/wiki/KISS_(amateur_radio_protocol))

2.  KISS Protocol --- M17 Protocol Specification documentation - Read
    the Docs, accessed June 16, 2025,
    [[https://m17-protocol-specification.readthedocs.io/en/latest/kiss_protocol.html]{.underline}](https://m17-protocol-specification.readthedocs.io/en/latest/kiss_protocol.html)

3.  KISS Protocol - AX.25, accessed June 16, 2025,
    [[https://www.ax25.net/kiss.aspx]{.underline}](https://www.ax25.net/kiss.aspx)

4.  KISS - XRPi Documentation - Ohio Packet, accessed June 16, 2025,
    [[https://ohiopacket.org/xrpi/docs/kiss.htm]{.underline}](https://ohiopacket.org/xrpi/docs/kiss.htm)

5.  Multi-Drop KISS operation - Packet-radio.net, accessed June 16,
    2025,
    [[https://packet-radio.net/wp-content/uploads/2017/04/multi-kiss.pdf]{.underline}](https://packet-radio.net/wp-content/uploads/2017/04/multi-kiss.pdf)

6.  aprs-specs/BLE-KISS-API.md at master - GitHub, accessed June 16,
    2025,
    [[https://github.com/hessu/aprs-specs/blob/master/BLE-KISS-API.md]{.underline}](https://github.com/hessu/aprs-specs/blob/master/BLE-KISS-API.md)

7.  Fldigi Users Manual: FLDIGI KISS Hardware Commands - W1HKJ, accessed
    June 16, 2025,
    [[https://www.w1hkj.org/FldigiHelp/kiss_command_page.html]{.underline}](https://www.w1hkj.org/FldigiHelp/kiss_command_page.html)

8.  Packet Mode - RadioMail, accessed June 16, 2025,
    [[https://radiomail.app/help/packet.html]{.underline}](https://radiomail.app/help/packet.html)

9.  Mobilinkd -- Highly mobile packet radio, accessed June 16, 2025,
    [[http://www.mobilinkd.com/]{.underline}](http://www.mobilinkd.com/)

10. Mobilinkd TNC3 User Guide - AWS, accessed June 16, 2025,
    [[https://mobilinkd.s3.amazonaws.com/TNC3/MobilinkdTNC3.pdf]{.underline}](https://mobilinkd.s3.amazonaws.com/TNC3/MobilinkdTNC3.pdf)

11. Mobilinkd TNC4 User Guide - AWS, accessed June 16, 2025,
    [[https://mobilinkd.s3.amazonaws.com/TNC4/MobilinkdTNC4.pdf]{.underline}](https://mobilinkd.s3.amazonaws.com/TNC4/MobilinkdTNC4.pdf)

12. mobilinkd/NucleoTNC: The Nucleo TNC is a breadboard implementation
    of the Mobilinkd TNC3 using a STM32L432KC Nucleo32 board. This TNC
    faithfully implements the audio section and EEPROM storage of the
    TNC3. It omits the battery charging and Bluetooth components of the
    TNC3. It presents as a KISS TNC over a USB serial port. This
    repository - GitHub, accessed June 16, 2025,
    [[https://github.com/mobilinkd/NucleoTNC]{.underline}](https://github.com/mobilinkd/NucleoTNC)

13. Mobilinkd TNC4, accessed June 16, 2025,
    [[https://store.mobilinkd.com/products/mobilinkd-tnc4]{.underline}](https://store.mobilinkd.com/products/mobilinkd-tnc4)

14. MOBILINKD - TNC4 - FIRMWARE INSTRUCTIONS - YouTube, accessed June
    16, 2025,
    [[https://www.youtube.com/watch?v=qeD8ZHJpN2Q]{.underline}](https://www.youtube.com/watch?v=qeD8ZHJpN2Q)

15. TinyTrak4 Kit Hardware Manual \| Byonics, accessed June 16, 2025,
    [[https://www.byonics.com/downloads/TinyTrak4%20Kit%20Hardware%20Manual%20v0.7.pdf]{.underline}](https://www.byonics.com/downloads/TinyTrak4%20Kit%20Hardware%20Manual%20v0.7.pdf)

16. BYONICS, accessed June 16, 2025,
    [[http://hammadeparts.jivetones.com/Amateur_Radio_Manuals_Schematics/TINY%20TRACKER/tinytrak4_sep_2013/tinytrak4_Sep_2013/TinyTrak4%20Built%20Hardware%20Manual%20v7.1.pdf]{.underline}](http://hammadeparts.jivetones.com/Amateur_Radio_Manuals_Schematics/TINY%20TRACKER/tinytrak4_sep_2013/tinytrak4_Sep_2013/TinyTrak4%20Built%20Hardware%20Manual%20v7.1.pdf)

17. TinyTrak4 Alpha Firmware Manual \| Byonics, accessed June 16, 2025,
    [[https://www.byonics.com/downloads/TinyTrak4%20Alpha%20Firmware%20Manual%20v0.72.pdf]{.underline}](https://www.byonics.com/downloads/TinyTrak4%20Alpha%20Firmware%20Manual%20v0.72.pdf)

18. TinyTrak4 Quick-Start Guide \| Byonics, accessed June 16, 2025,
    [[https://www.byonics.com/downloads/TinyTrak4%20Quick%20Start%20Guide%20v0.7.pdf]{.underline}](https://www.byonics.com/downloads/TinyTrak4%20Quick%20Start%20Guide%20v0.7.pdf)

19. Byonics TinyTrak4 Bluetooth Adapter (TT4BT) Manual, accessed June
    16, 2025,
    [[https://www.byonics.com/downloads/tt4bt.pdf]{.underline}](https://www.byonics.com/downloads/tt4bt.pdf)

20. BYONICS - AIAA OC Rocketry, accessed June 16, 2025,
    [[https://aiaaocrocketry.org/AIAAOCRocketryDocs/SLI2011-2012/Manuals/TinyTrak4%20Quick%20Start%20Guide%20v0.5.pdf]{.underline}](https://aiaaocrocketry.org/AIAAOCRocketryDocs/SLI2011-2012/Manuals/TinyTrak4%20Quick%20Start%20Guide%20v0.5.pdf)

21. C++ Serial Port Connection \| GeeksforGeeks, accessed June 16, 2025,
    [[https://www.geeksforgeeks.org/serial-port-connection-in-cpp/]{.underline}](https://www.geeksforgeeks.org/serial-port-connection-in-cpp/)

22. Best way to deal with COM ports for a cross-platform program? -
    Stack Overflow, accessed June 16, 2025,
    [[https://stackoverflow.com/questions/3234577/best-way-to-deal-with-com-ports-for-a-cross-platform-program]{.underline}](https://stackoverflow.com/questions/3234577/best-way-to-deal-with-com-ports-for-a-cross-platform-program)

23. Cross-Platform, Serial Port Library built on Boost.Asio in Modern
    C++ 17 - GitHub, accessed June 16, 2025,
    [[https://github.com/karthickai/serial]{.underline}](https://github.com/karthickai/serial)

24. wjwwood/serial: Cross-platform, Serial Port library written in
    \... - GitHub, accessed June 16, 2025,
    [[https://github.com/wjwwood/serial]{.underline}](https://github.com/wjwwood/serial)

25. On the Performance and Robustness of Managing Reliable Transport
    Connections, accessed June 16, 2025,
    [[https://www.cs.bu.edu/fac/matta/Papers/new-reliable-conn-mgmt.pdf]{.underline}](https://www.cs.bu.edu/fac/matta/Papers/new-reliable-conn-mgmt.pdf)

26. Linux Serial Ports Using C/C++ - mbedded.ninja, accessed June 16,
    2025,
    [[https://blog.mbedded.ninja/programming/operating-systems/linux/linux-serial-ports-using-c-cpp/]{.underline}](https://blog.mbedded.ninja/programming/operating-systems/linux/linux-serial-ports-using-c-cpp/)

27. SDRplay SDRuno User Manual \| PDF \| Frequency Modulation - Scribd,
    accessed June 16, 2025,
    [[https://www.scribd.com/document/555027054/SDRplay-SDRuno-User-Manual]{.underline}](https://www.scribd.com/document/555027054/SDRplay-SDRuno-User-Manual)

28. SDRuno - The SWLing Post, accessed June 16, 2025,
    [[https://swling.com/blog/tag/sdruno/]{.underline}](https://swling.com/blog/tag/sdruno/)

29. SDRuno -- Page 2 - The SWLing Post, accessed June 16, 2025,
    [[https://swling.com/blog/tag/sdruno/page/2/]{.underline}](https://swling.com/blog/tag/sdruno/page/2/)

30. SDRuno 1.3 - Reconnecting to 3rd party apps - YouTube, accessed June
    16, 2025,
    [[https://www.youtube.com/watch?v=QhsMNWM9tMA]{.underline}](https://www.youtube.com/watch?v=QhsMNWM9tMA)

31. Using ERGO with SDRuno and SDRPlay, accessed June 16, 2025,
    [[https://ergo.fallows.ca/wp/general/using-ergo-with-sdruno-sdrplay/]{.underline}](https://ergo.fallows.ca/wp/general/using-ergo-with-sdruno-sdrplay/)

32. Techminds: Testing out the new Plugins Feature on SDRuno V1.4 RC1 -
    RTL-SDR.com, accessed June 16, 2025,
    [[https://www.rtl-sdr.com/techminds-testing-out-the-new-plugins-feature-on-sdruno-v1-4-rc1/]{.underline}](https://www.rtl-sdr.com/techminds-testing-out-the-new-plugins-feature-on-sdruno-v1-4-rc1/)

33. SDRplay/ExtIO_SDRplay: ExtIO plugins for SDRplay RSPs - GitHub,
    accessed June 16, 2025,
    [[https://github.com/SDRplay/ExtIO_SDRplay]{.underline}](https://github.com/SDRplay/ExtIO_SDRplay)

34. JvanKatwijk/unoPlugins-jan: repostory for SDRuno plugins \... -
    GitHub, accessed June 16, 2025,
    [[https://github.com/JvanKatwijk/unoPlugins-jan]{.underline}](https://github.com/JvanKatwijk/unoPlugins-jan)

35. SDRuno Updated to Version 1.22 - RTL-SDR.com, accessed June 16,
    2025,
    [[https://www.rtl-sdr.com/sdruno-updated-to-version-1-22/comment-page-1/]{.underline}](https://www.rtl-sdr.com/sdruno-updated-to-version-1-22/comment-page-1/)

36. Tagged: sdruno - RTL-SDR.com, accessed June 16, 2025,
    [[https://www.rtl-sdr.com/tag/sdruno/page/2/]{.underline}](https://www.rtl-sdr.com/tag/sdruno/page/2/)

37. SDRUno & NEW SDRConnect Learning - YouTube, accessed June 16, 2025,
    [[https://www.youtube.com/watch?v=uzFsYYLQn3o]{.underline}](https://www.youtube.com/watch?v=uzFsYYLQn3o)

38. Getting started with SDRplay, accessed June 16, 2025,
    [[https://docs.rs-online.com/acc0/0900766b81707a26.pdf]{.underline}](https://docs.rs-online.com/acc0/0900766b81707a26.pdf)

39. Avoid the nRSP-ST - it will never have documentation : r/RTLSDR -
    Reddit, accessed June 16, 2025,
    [[https://www.reddit.com/r/RTLSDR/comments/1jhgjti/avoid_the_nrspst_it_will_never_have_documentation/]{.underline}](https://www.reddit.com/r/RTLSDR/comments/1jhgjti/avoid_the_nrspst_it_will_never_have_documentation/)

40. VirtualHere: Full version of SDRuno and a remote RSP - YouTube,
    accessed June 16, 2025,
    [[https://www.youtube.com/watch?v=KDbOFftyEww]{.underline}](https://www.youtube.com/watch?v=KDbOFftyEww)

41. RTL-SDR Tutorial: Setting up and using the SpyServer Remote
    Streaming Server with an RTL-SDR, accessed June 16, 2025,
    [[https://www.rtl-sdr.com/rtl-sdr-tutorial-setting-up-and-using-the-spyserver-remote-streaming-server-with-an-rtl-sdr/]{.underline}](https://www.rtl-sdr.com/rtl-sdr-tutorial-setting-up-and-using-the-spyserver-remote-streaming-server-with-an-rtl-sdr/)

42. Spyserver Setup Instructions · projecthorus/radiosonde_auto_rx
    Wiki - GitHub, accessed June 16, 2025,
    [[https://github.com/projecthorus/radiosonde_auto_rx/wiki/Spyserver-Setup-Instructions]{.underline}](https://github.com/projecthorus/radiosonde_auto_rx/wiki/Spyserver-Setup-Instructions)

43. Quick start guide - AIRSPY, accessed June 16, 2025,
    [[https://airspy.com/quickstart/]{.underline}](https://airspy.com/quickstart/)

44. spyserver.conf - GitHub Gist, accessed June 16, 2025,
    [[https://gist.github.com/Taubin/5d47d8c55bad45330f40bb4c7335739d]{.underline}](https://gist.github.com/Taubin/5d47d8c55bad45330f40bb4c7335739d)

45. WebSDR, accessed June 16, 2025,
    [[http://www.websdr.org/]{.underline}](http://www.websdr.org/)

46. Web SDR receiver - IS MUNI, accessed June 16, 2025,
    [[https://is.muni.cz/th/kp8qb/thesis.pdf]{.underline}](https://is.muni.cz/th/kp8qb/thesis.pdf)

47. What protocol or API does WebSDR use to stream audio? - Amateur
    Radio Stack Exchange, accessed June 16, 2025,
    [[https://ham.stackexchange.com/questions/2272/what-protocol-or-api-does-websdr-use-to-stream-audio]{.underline}](https://ham.stackexchange.com/questions/2272/what-protocol-or-api-does-websdr-use-to-stream-audio)

48. Effort to Reverse Engineer WebSDR @ Twente - GitHub Gist, accessed
    June 16, 2025,
    [[https://gist.github.com/kevinelliott/962ab6a7a5b8f43bfc0c979df4ffa609]{.underline}](https://gist.github.com/kevinelliott/962ab6a7a5b8f43bfc0c979df4ffa609)

49. Web-SDR implementation - possible? - Development - VCV Community,
    accessed June 16, 2025,
    [[https://community.vcvrack.com/t/web-sdr-implementation-possible/12406]{.underline}](https://community.vcvrack.com/t/web-sdr-implementation-possible/12406)

50. KiwiSDR design review, accessed June 16, 2025,
    [[http://kiwisdr.com/docs/KiwiSDR/KiwiSDR.design.review.pdf]{.underline}](http://kiwisdr.com/docs/KiwiSDR/KiwiSDR.design.review.pdf)

51. KiwiSDR Operating Information, accessed June 16, 2025,
    [[http://kiwisdr.com/info/]{.underline}](http://kiwisdr.com/info/)

52. KiwiSDR Build - Part One - Hardware (& Software Update), accessed
    June 16, 2025,
    [[https://midsussexars.org.uk/feature-articles/206-kiwisdr-build-part-one-hardware-software-update]{.underline}](https://midsussexars.org.uk/feature-articles/206-kiwisdr-build-part-one-hardware-software-update)

53. Introduction to using the KiwiSDR, accessed June 16, 2025,
    [[http://kiwisdr.com/ks/using_Kiwi.html]{.underline}](http://kiwisdr.com/ks/using_Kiwi.html)

54. About Python KiwiClient \[Kiwi API question\] - KiwiSDR Forum,
    accessed June 16, 2025,
    [[https://forum.kiwisdr.com/index.php?p=/discussion/2269/about-python-kiwiclient-kiwi-api-question]{.underline}](https://forum.kiwisdr.com/index.php?p=/discussion/2269/about-python-kiwiclient-kiwi-api-question)

55. REST API - KiwiSDR Forum, accessed June 16, 2025,
    [[https://forum.kiwisdr.com/index.php?p=/discussion/3557/rest-api]{.underline}](https://forum.kiwisdr.com/index.php?p=/discussion/3557/rest-api)

56. C# client to connect with an internet WikiSDR server - KiwiSDR
    Forum, accessed June 16, 2025,
    [[https://forum.kiwisdr.com/index.php?p=/discussion/2416/c-client-to-connect-with-an-internet-wikisdr-server]{.underline}](https://forum.kiwisdr.com/index.php?p=/discussion/2416/c-client-to-connect-with-an-internet-wikisdr-server)

57. Kiwiclientd Usage - KiwiSDR Forum, accessed June 16, 2025,
    [[https://forum.kiwisdr.com/index.php?p=/discussion/2531/kiwiclientd-usage]{.underline}](https://forum.kiwisdr.com/index.php?p=/discussion/2531/kiwiclientd-usage)

58. OpenWebRX web-based software defined radio \| Homepage, accessed
    June 16, 2025,
    [[https://www.openwebrx.de/]{.underline}](https://www.openwebrx.de/)

59. Receiverbook \| online receiver directory \| Home, accessed June 16,
    2025,
    [[https://www.receiverbook.de/]{.underline}](https://www.receiverbook.de/)

60. API Documentation - Storecove, accessed June 16, 2025,
    [[https://www.storecove.com/docs/with_deprecated]{.underline}](https://www.storecove.com/docs/with_deprecated)

61. API Documentation - Storecove, accessed June 16, 2025,
    [[https://www.storecove.com/docs/]{.underline}](https://www.storecove.com/docs/)

62. jketterl/receiverbook: Online receiver directory - GitHub, accessed
    June 16, 2025,
    [[https://github.com/jketterl/receiverbook]{.underline}](https://github.com/jketterl/receiverbook)
