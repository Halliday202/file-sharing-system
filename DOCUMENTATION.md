# Distributed File-Sharing System -- Project Documentation

**Topic:** Data Consistency and Replication Strategies in Distributed Systems  
**Project:** A basic file-sharing system that allows users to upload and download files from a central server.  
**Stack:** C++ (client), Python (manager/gateway + GUI), Java (storage daemons)  
**Transport:** Raw TCP sockets (no HTTP frameworks)

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Architecture](#2-architecture)
3. [Wire Protocol (NetworkPacket)](#3-wire-protocol-networkpacket)
4. [Security Layer (AES Encryption)](#4-security-layer-aes-encryption)
5. [Backend: Java Storage Daemons](#5-backend-java-storage-daemons)
6. [Backend: Python Manager Server](#6-backend-python-manager-server)
7. [Backend: Replication & Consistency](#7-backend-replication--consistency)
8. [Client: C++ Upload Engine](#8-client-c-upload-engine)
9. [Frontend: Python GUI](#9-frontend-python-gui)
10. [File-by-File Reference](#10-file-by-file-reference)
11. [How to Build & Run](#11-how-to-build--run)
12. [Data Flow Walkthroughs](#12-data-flow-walkthroughs)

---

## 1. System Overview

This project is a distributed file-sharing system that demonstrates:

- **Data replication** -- every uploaded file is stored on 3 independent storage nodes.
- **Consistency strategies** -- configurable toggle between *strong consistency* (wait for all nodes) and *eventual consistency* (respond immediately, replicate in background).
- **Application-layer encryption** -- all file payloads are AES-256-CBC encrypted in transit.
- **Path sanitization** -- storage nodes defend against directory traversal attacks.
- **Multi-language integration** -- C++ handles encryption and upload, Python orchestrates everything, Java stores files.

The system runs entirely on `localhost` for local testing. The user interacts with a single Python GUI window that manages all backend services automatically.

---

## 2. Architecture

```
+-------------------+         +------------------------+         +-------------------+
|   C++ Client      |  TCP    |   Python Manager       |  TCP    | Java Storage      |
|   (Encryption &   |-------->|   (Gateway on :9000)   |-------->| Daemon :8001      |
|    Upload Engine)  |         |                        |-------->| Daemon :8002      |
+-------------------+         |   - Receives uploads   |-------->| Daemon :8003      |
                               |   - Replicates to      |         +-------------------+
+-------------------+         |     all 3 nodes         |         | Each node:        |
|   Python GUI      |  TCP    |   - Handles downloads   |         |  - Decrypts file  |
|   (Upload/Download |-------->|   - Tracks metadata     |         |  - Sanitizes name |
|    + Monitor)      |         |   - Writes state.json   |         |  - Saves to disk  |
+-------------------+         +------------------------+         +-------------------+
        |                              |
        |  reads state.json            |  writes state.json
        +------------------------------+
```

**Component roles:**

| Component | Language | Role | Port |
|-----------|----------|------|------|
| GUI | Python (customtkinter) | user interface, service launcher, download decryption | -- |
| Manager | Python (asyncio) | TCP gateway, replication engine, metadata tracker | 9000 |
| Storage Node 1 | Java | receive, decrypt, store files | 8001 |
| Storage Node 2 | Java | receive, decrypt, store files | 8002 |
| Storage Node 3 | Java | receive, decrypt, store files | 8003 |
| Upload Client | C++ (OpenSSL) | encrypt files, build packets, send to manager | -- |

---

## 3. Wire Protocol (NetworkPacket)

All TCP communication in the system follows the same binary packet format. This is used for:
- C++ client --> Python manager (uploads)
- Python manager --> Java nodes (replication)
- Java nodes --> Python manager (download responses)
- Python GUI --> Python manager (list/download requests)

### Packet Structure

```
+--------------------------------------------------+
| JSON Header (UTF-8 text, cleartext)              |
| Example:                                          |
| {"id":"123","type":"upload",                      |
|  "filename":"report.pdf","payloadSize":4096}      |
+--------------------------------------------------+
| Delimiter: \n\n (two newline bytes, 0x0A 0x0A)   |
+--------------------------------------------------+
| Payload (binary, encrypted)                       |
| [16-byte IV][AES-256-CBC ciphertext...]           |
+--------------------------------------------------+
```

### How the receiver parses it

1. Read bytes one at a time until the sequence `\n\n` is found.
2. Everything before `\n\n` is the JSON header. Parse it as UTF-8 JSON.
3. Extract the `payloadSize` field from the JSON.
4. Read exactly `payloadSize` bytes from the stream. This is the encrypted binary payload.
5. The connection can then be used for a response, or closed.

### Header fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | unique identifier for the upload (timestamp + random) |
| `type` | string | `"upload"`, `"download"`, `"list"`, or `"download_response"` |
| `filename` | string | original name of the file |
| `payloadSize` | integer | exact byte count of the payload after the delimiter |

For requests that have no payload (like `"list"` or `"download"`), `payloadSize` is set to `0` and there are no bytes after the `\n\n` delimiter.

---

## 4. Security Layer (AES Encryption)

### Shared parameters (identical across all 3 languages)

| Parameter | Value |
|-----------|-------|
| Algorithm | AES-256-CBC |
| Key (hex) | `00112233445566778899AABBCCDDEEFF00112233445566778899AABBCCDDEEFF` |
| Key size | 256 bits (32 bytes) |
| IV size | 16 bytes (generated randomly per encryption) |
| Padding | PKCS7 (called PKCS5Padding in Java -- equivalent for AES block size) |

### Payload format

The encrypted payload is structured as:

```
[16 bytes: random IV][N bytes: AES-256-CBC ciphertext with PKCS7 padding]
```

So `payloadSize = 16 + ciphertext_length`.

### Who encrypts and decrypts

| Operation | Encryptor | Decryptor |
|-----------|-----------|-----------|
| Upload | C++ client (OpenSSL) | Java storage node (javax.crypto) |
| Download | Java storage node (javax.crypto) | Python GUI (cryptography library) |

The Python manager never decrypts -- it forwards encrypted payloads as-is during uploads. For downloads, the Java node re-encrypts the stored file with a fresh random IV before sending it back.

### Implementation locations

- **C++ encryption:** `client/src/crypto.cpp` -- uses OpenSSL's `EVP_EncryptInit_ex`, `EVP_EncryptUpdate`, `EVP_EncryptFinal_ex` with `EVP_aes_256_cbc()`. IV generated via `RAND_bytes`.
- **Java decryption:** `storage/src/CryptoUtil.java` -- `decrypt()` method uses `Cipher.getInstance("AES/CBC/PKCS5Padding")` in `DECRYPT_MODE`.
- **Java encryption:** `storage/src/CryptoUtil.java` -- `encrypt()` method uses the same cipher in `ENCRYPT_MODE` with `SecureRandom` for IV.
- **Python decryption:** `manager/gui.py` -- `aes_decrypt()` function uses the `cryptography` library's `Cipher(AES, CBC)`.

### Path sanitization (directory traversal defense)

The Java storage nodes sanitize every incoming filename in `PathSanitizer.java`:

1. Strip null bytes.
2. Normalize path separators to `/`.
3. Remove all `../` and `./` sequences.
4. Extract only the basename (last path component).
5. Strip leading dots.
6. Replace any character that isn't alphanumeric, `.`, `-`, or `_` with an underscore.
7. Final check: resolve the filename against the storage directory and verify it doesn't escape.

---

## 5. Backend: Java Storage Daemons

The Java layer is the "dumb muscle" of the system. Each daemon is a standalone process that listens on a TCP port, accepts connections, and either stores or retrieves files.

### Files

| File | Purpose |
|------|---------|
| `StorageDaemon.java` | entry point -- opens a `ServerSocket`, accepts connections, spawns threads |
| `ConnectionHandler.java` | per-connection logic -- parses the packet, routes to upload or download handler |
| `PacketParser.java` | reads the TCP stream following the NetworkPacket protocol |
| `CryptoUtil.java` | AES-256-CBC encrypt and decrypt using `javax.crypto` |
| `PathSanitizer.java` | strips directory traversal attacks from filenames |

### How it works

1. `StorageDaemon` takes a port number as a command-line argument (e.g., `java StorageDaemon 8001`).
2. It opens a `ServerSocket` on that port and enters an infinite accept loop.
3. Each accepted connection spawns a new `Thread` running `ConnectionHandler`.
4. `ConnectionHandler.run()` reads the packet via `PacketParser.readFrom(inputStream)`.
5. Based on the `"type"` field in the JSON header:
   - **`"upload"`**: decrypt the payload, sanitize the filename, write to `stored_files/<port>/<filename>`, send back `{"status":"saved","node":<port>}`.
   - **`"download"`**: sanitize the filename, read the file from disk, encrypt it, send back a response packet with the encrypted payload.

### Storage layout

```
storage/
  stored_files/
    8001/           <-- files saved by node on port 8001
      report.pdf
      image.png
    8002/           <-- files saved by node on port 8002
      report.pdf
      image.png
    8003/           <-- files saved by node on port 8003
      report.pdf
      image.png
```

Each node stores an independent copy. All 3 directories should contain identical files after a successful upload with strong consistency.

---

## 6. Backend: Python Manager Server

The Python manager (`manager/server.py`) is the central hub. It is the only component that both the client and the storage nodes talk to. It runs an asyncio TCP server on port 9000.

### Files

| File | Purpose |
|------|---------|
| `config.py` | shared configuration (ports, AES key, consistency mode) |
| `server.py` | asyncio TCP server, request routing |
| `replicator.py` | replication logic, state management, file list/download proxying |

### Request handling

When a TCP connection comes in, `server.py` reads the JSON header and dispatches based on the `"type"` field:

| Type | Handler | What it does |
|------|---------|-------------|
| `"upload"` | `handle_upload()` | reads the encrypted payload, forwards the full packet to all 3 Java nodes via the replicator, sends success/failure response back to client |
| `"list"` | `handle_list()` | returns a JSON array of all uploaded files with their IDs, filenames, timestamps, and which nodes have them |
| `"download"` | `handle_download()` | asks the replicator to fetch the file from an available Java node, forwards the encrypted payload back to the requester |

### State tracking

The replicator maintains an in-memory dictionary with 3 sections:

- **`node_health`**: tracks whether each Java node is `"up"`, `"down"`, or `"unknown"` based on the most recent TCP interaction.
- **`metadata`**: maps each file ID to its filename, upload timestamp, and per-node replication status (`"saved"`, `"error"`, `"failed"`).
- **`replication_log`**: rolling log of the last 100 replication events.

This state is persisted to `state.json` on every update so the GUI and Streamlit dashboard can read it.

---

## 7. Backend: Replication & Consistency

This is the core distributed systems concept the project demonstrates.

### Strong Consistency (default)

```
Client sends file --> Manager receives it
  |
  +--> Manager sends to Node 8001 --|
  +--> Manager sends to Node 8002 --|-- all 3 in parallel (asyncio.gather)
  +--> Manager sends to Node 8003 --|
  |
  Manager waits for ALL 3 ACKs
  |
  Manager sends response to Client: {"replicas": 3}
```

- The client is **blocked** until all 3 nodes confirm they saved the file.
- If any node fails, the response shows `"status":"partial"` with the count of successful replicas.
- **Guarantees**: after the client receives a success response, the file is on all 3 nodes.
- **Tradeoff**: higher latency (limited by the slowest node).

### Eventual Consistency

```
Client sends file --> Manager receives it
  |
  Manager immediately responds: {"status":"ok","mode":"eventual"}
  |
  (in background, asynchronously)
  +--> Manager sends to Node 8001
  +--> Manager sends to Node 8002
  +--> Manager sends to Node 8003
```

- The client gets an **immediate** response.
- Replication happens in background `asyncio.create_task` calls.
- **Guarantees**: the file will *eventually* be on all nodes, but may not be there yet when the client receives the response.
- **Tradeoff**: lower latency, but temporary inconsistency.

### How to toggle

Edit `manager/config.py` and change:

```python
CONSISTENCY_MODE = "strong"   # or "eventual"
```

---

## 8. Client: C++ Upload Engine

The C++ client is a command-line tool that encrypts a file and sends it to the Python manager.

### Files

| File | Purpose |
|------|---------|
| `main.cpp` | CLI entry point -- reads file, orchestrates encrypt/send |
| `crypto.cpp` / `crypto.h` | AES-256-CBC encryption using OpenSSL EVP API |
| `packet.cpp` / `packet.h` | builds the NetworkPacket (JSON header + delimiter + payload) |
| `network.cpp` / `network.h` | TCP socket connection and data transfer (Winsock2) |
| `build.bat` | compile script using MinGW-w64 + OpenSSL |
| `CMakeLists.txt` | alternative CMake build configuration |

### Flow

1. **Read file**: `main.cpp` reads the file into a byte buffer. Accepts path as `argv[1]` (from GUI) or via interactive stdin prompt.
2. **Encrypt**: `crypto.cpp` generates a random 16-byte IV using `RAND_bytes`, encrypts the buffer with AES-256-CBC via `EVP_EncryptInit_ex`/`Update`/`Final_ex`, returns `[IV || ciphertext]`.
3. **Build packet**: `packet.cpp` constructs the JSON header with a unique ID, the filename (basename only), and the `payloadSize`. Concatenates `header + "\n\n" + encrypted_payload`.
4. **Send**: `network.cpp` opens a TCP socket to `127.0.0.1:9000`, sends the full packet, reads the JSON response line, prints it.

### Build requirements

- MinGW-w64 (g++ 16.x, installed via `scoop install mingw`)
- OpenSSL 4.x (installed via `scoop install openssl`)
- Run `client\build.bat` to compile. It also copies the OpenSSL DLLs next to `client.exe`.

---

## 9. Frontend: Python GUI

The GUI (`manager/gui.py`) is the single entry point for the entire system. It replaces all the batch scripts and the CLI workflow.

### Framework

- **customtkinter** -- modern dark-themed wrapper around tkinter
- **tkinterdnd2** -- adds drag-and-drop support for file uploads

### What happens on launch

1. The GUI window opens.
2. A background thread compiles the Java code (if needed) and starts all 4 services (3 Java daemons + Python manager) as hidden subprocesses.
3. The status bar shows "All services running" when ready.
4. On window close, all child processes are terminated.

### Tab: Upload

- **Browse button**: opens the native Windows file picker dialog (`tkinter.filedialog.askopenfilename`).
- **Drag-and-drop zone**: drop a file from Windows Explorer onto the zone (uses `tkinterdnd2`).
- When a file is selected, the GUI spawns `client.exe <filepath>` as a hidden subprocess. The C++ client encrypts the file and sends it to the manager. The result is shown in the upload log.
- The upload runs in a background thread so the GUI stays responsive.

### Tab: Download

- **Refresh List**: sends a `{"type":"list"}` TCP request to the manager. The manager returns all uploaded files with their metadata. Displayed as a selectable list.
- **Download Selected**: sends a `{"type":"download"}` TCP request. The manager fetches the encrypted file from a Java node and forwards it. The GUI decrypts it using the `cryptography` library and saves it to the user's chosen location via a "Save As" dialog.

### Tab: Monitor

- Reads `state.json` every 3 seconds.
- Shows: consistency mode, total upload count, number of online nodes.
- Per-node health indicators (UP/DOWN/unknown).
- Scrollable replication log showing the last 30 events.

---

## 10. File-by-File Reference

### Project structure

```
file-sharing-system/
|
+-- client/                     [C++ Upload Client]
|   +-- src/
|   |   +-- main.cpp            CLI entry point, file reader
|   |   +-- crypto.h            encryption function declaration
|   |   +-- crypto.cpp          AES-256-CBC encrypt (OpenSSL EVP)
|   |   +-- packet.h            packet builder declarations
|   |   +-- packet.cpp          JSON header + binary packet assembly
|   |   +-- network.h           TCP sender declaration
|   |   +-- network.cpp         Winsock2 TCP connect/send/recv
|   +-- build.bat               MinGW-w64 compile script
|   +-- CMakeLists.txt          alternative CMake build
|   +-- client.exe              compiled binary (after build)
|   +-- libcrypto-4-x64.dll     OpenSSL runtime (copied by build.bat)
|   +-- libssl-4-x64.dll        OpenSSL runtime (copied by build.bat)
|
+-- manager/                    [Python Manager + GUI]
|   +-- config.py               shared config (ports, AES key, consistency mode)
|   +-- server.py               asyncio TCP server (upload/list/download routing)
|   +-- replicator.py           replication engine + state + download proxy
|   +-- gui.py                  customtkinter GUI (main entry point)
|   +-- dashboard.py            Streamlit web dashboard (optional alternative)
|   +-- requirements.txt        pip dependencies
|   +-- state.json              runtime state file (auto-generated)
|
+-- storage/                    [Java Storage Daemons]
|   +-- src/
|   |   +-- StorageDaemon.java      TCP listener, thread spawner
|   |   +-- ConnectionHandler.java  upload/download handler per connection
|   |   +-- PacketParser.java       NetworkPacket stream parser
|   |   +-- CryptoUtil.java         AES-256-CBC encrypt + decrypt
|   |   +-- PathSanitizer.java      filename sanitization
|   +-- build.bat               javac compile script
|   +-- out/                    compiled .class files (after build)
|   +-- stored_files/           saved files organized by node port
|
+-- scripts/                    [Batch Launchers (optional, GUI replaces these)]
|   +-- start_all.bat           launch everything
|   +-- start_storage.bat       launch 3 Java daemons
|   +-- start_manager.bat       launch Python manager
|   +-- start_dashboard.bat     launch Streamlit dashboard
```

---

## 11. How to Build & Run

### Prerequisites

- **Python 3.10+** with pip
- **Java JDK 17+** (javac and java on PATH)
- **MinGW-w64** (for compiling the C++ client) -- `scoop install mingw`
- **OpenSSL** (for C++ encryption) -- `scoop install openssl`

### Step 1: Install Python dependencies

```
cd manager
pip install -r requirements.txt
```

### Step 2: Build the C++ client

```
cd client
build.bat
```

This compiles `client.exe` and copies the OpenSSL DLLs.

### Step 3: Run

```
cd manager
python gui.py
```

That's it. The GUI automatically:
- Compiles the Java storage daemons (if not already compiled).
- Starts 3 Java nodes on ports 8001, 8002, 8003.
- Starts the Python manager on port 9000.
- Opens the GUI window for upload, download, and monitoring.

When you close the GUI, all background services are stopped.

---

## 12. Data Flow Walkthroughs

### Upload Flow (step by step)

```
1. User clicks "Browse" in GUI, selects "report.pdf"

2. GUI spawns: client.exe "C:\Users\...\report.pdf"

3. C++ client:
   a. Reads report.pdf into memory (e.g., 50,000 bytes)
   b. Generates random 16-byte IV
   c. Encrypts with AES-256-CBC --> ciphertext (50,016 bytes with padding)
   d. Payload = [IV (16 bytes)] + [ciphertext] = 50,032 bytes
   e. Builds JSON header:
      {"id":"1780413929-3766","type":"upload","filename":"report.pdf","payloadSize":50032}
   f. Assembles packet: [header bytes] + [\n\n] + [50,032 encrypted bytes]
   g. Opens TCP to 127.0.0.1:9000, sends full packet

4. Python manager (server.py):
   a. Reads header up to \n\n, parses JSON
   b. Reads exactly 50,032 bytes of encrypted payload
   c. Reconstructs the full packet (header + \n\n + payload)

5. Replication (strong mode):
   a. Opens 3 TCP connections in parallel to ports 8001, 8002, 8003
   b. Sends the same packet to each Java node
   c. Waits for all 3 ACKs

6. Java node (e.g., port 8001):
   a. Reads the packet via PacketParser
   b. Sanitizes filename: "report.pdf" --> "report.pdf" (already clean)
   c. Extracts IV from first 16 bytes, decrypts ciphertext with AES-256-CBC
   d. Writes plaintext to stored_files/8001/report.pdf
   e. Sends back: {"status":"saved","node":8001}

7. Manager collects all 3 ACKs, sends response to C++ client:
   {"status":"ok","mode":"strong","replicas":3,"total_nodes":3}

8. GUI reads the client.exe output, shows "success" in the upload log
```

### Download Flow (step by step)

```
1. User clicks "Refresh List" in the Download tab

2. GUI sends TCP to manager:
   {"type":"list","payloadSize":0}\n\n

3. Manager returns:
   {"status":"ok","files":[{"id":"...","filename":"report.pdf","timestamp":"...","nodes":["8001","8002","8003"]}]}

4. GUI displays the file list. User selects "report.pdf", clicks "Download"

5. GUI opens "Save As" dialog. User picks a save location.

6. GUI sends TCP to manager:
   {"type":"download","filename":"report.pdf","id":"...","payloadSize":0}\n\n

7. Manager (replicator.py):
   a. Picks an available Java node (checks node_health, picks first "up" node)
   b. Sends download request to that Java node

8. Java node:
   a. Reads report.pdf from stored_files/8001/report.pdf (plaintext on disk)
   b. Generates a new random IV
   c. Encrypts with AES-256-CBC
   d. Sends response packet:
      {"type":"download_response","filename":"report.pdf","payloadSize":50032,"node":8001}\n\n
      [50,032 encrypted bytes]

9. Manager forwards the encrypted payload to the GUI

10. GUI (gui.py):
    a. Receives the encrypted payload
    b. Extracts IV (first 16 bytes), decrypts with AES-256-CBC
    c. Removes PKCS7 padding
    d. Writes plaintext to the user's chosen save path
    e. Shows "saved: report.pdf (50000 bytes)" in the status
```
