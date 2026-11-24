# Architecture & Engineering Trade-Offs

This document explains the architectural choices behind `fl-studio-mcp`, its wire protocol, the boundary between API scripting and Win32 GUI automation, and how the project achieves deterministic cross-platform testing without a live DAW.

---

## 1. Why MIDI SysEx RPC Instead of Sockets or OSC?

FL Studio exposes a Python-based **MIDI Controller Scripting API** (`transport`, `channels`, `mixer`, `patterns`, `playlist`, `plugins`, `ui`, `general`, `device`). However, this runtime runs embedded inside FL Studio with strict sandboxing constraints:

- Standard networking libraries (`socket`, `http.server`, `asyncio`) are unavailable or restricted across FL Studio versions.
- External processes cannot invoke FL Studio's Python API directly.

**Chosen solution:** A bidirectional **chunked JSON-over-SysEx RPC protocol** carried over virtual MIDI loopback ports (`FL_MCP_IN` and `FL_MCP_OUT` via `loopMIDI`).

### Trade-offs
| Option | Pros | Cons |
| --- | --- | --- |
| **SysEx JSON RPC (chosen)** | Works natively in FL Studio's official MIDI Scripting sandbox; zero external plugins/DLLs; deterministic request/response IDs | 7-bit MIDI data constraint; requires `loopMIDI` virtual ports |
| **OSC / UDP / Localhost HTTP** | Higher throughput | Blocked/unsupported in FL Studio's sandboxed Python runtime |
| **Pure Win32 GUI automation** | Can click anything | Fragile, blind (no state readback), slow |

---

## 2. Wire Protocol Specification

All RPC messages share a custom non-commercial SysEx manufacturer prefix (`0x7D`, educational/development ID) followed by `'F'` `'M'` (`0x46 0x4D`):

```text
+------+------+------+------+-------+-------+-----------+--------------+-----------+------+
| 0xF0 | 0x7D | 0x46 | 0x4D | id_hi | id_lo | chunk_idx | total_chunks | ascii_hex | 0xF7 |
+------+------+------+------+-------+-------+-----------+--------------+-----------+------+
  SOX    Dev    'F'    'M'    7-bit   7-bit    0..127        1..127      <= 512B     EOX
```

- **7-bit safety:** JSON is UTF-8 encoded and converted to lowercase ASCII hex (`0-9`, `a-f`), guaranteeing every byte in the payload is `< 0x80` (MIDI-compliant).
- **Chunking:** Payloads exceeding `512` hex characters are split across numbered chunks (`chunk_idx` / `total_chunks`) and reassembled on both ends.
- **Request matching & hygiene:**
  - `FLBridge` assigns monotonically wrapping 14-bit IDs (`1..16000`), drains stale pending inputs before each call, and prunes incomplete RX buffers older than `max(timeout * 2, 10s)`.
  - `device_FLStudioMCP.py` caps `_rx_buffers` at `32` concurrent message IDs, evicting the oldest incomplete frame to bound memory inside FL Studio.

---

## 3. Hybrid Control Boundary (SysEx vs. Win32 `SendInput`)

FL Studio's MIDI Scripting API provides rich control over transport, mixer, channels, patterns, and plugin parameters, **but intentionally omits**:
- Loading new generator/FX plugins from the browser/picker
- Searching & loading audio samples into the Channel Rack
- Importing `.mid` files into the Piano Roll
- Creating a new project or deleting a channel

To cover the complete production workflow, `fl-studio-mcp` pairs SysEx RPC with a thin Win32 `user32.SendInput` layer ([`win_auto.py`](../src/fl_studio_mcp/win_auto.py)):
- Every Win32 operation first uses SysEx (`ui_focus`, `channel_set`, `ping`) to establish deterministic preconditions and read back state after the UI action.
- On non-Windows hosts, `win_auto.py` degrades cleanly via lazy `WinDLL` guards so the MCP server, DSP tools, and `FL_MCP_MOCK=1` simulator remain fully importable and testable on Linux/macOS.

---

## 4. Deterministic Simulator (`FL_MCP_MOCK=1`) & E2E Contract Testing

Evaluating or CI-testing a DAW integration is normally impossible without FL Studio installed. [`simulator.py`](../src/fl_studio_mcp/simulator.py) solves this by:

1. Providing an in-memory implementation (`MockFLRuntime`) of all 10 FL Studio scripting modules (`transport`, `mixer`, `channels`, `patterns`, `playlist`, `plugins`, `ui`, `general`, `device`, `midi`).
2. Dynamically loading the **actual** [`fl_script/device_FLStudioMCP.py`](../fl_script/device_FLStudioMCP.py) against those modules in an isolated namespace.
3. Routing real `mido.Message("sysex", ...)` frames from `FLBridge` directly into `device_FLStudioMCP.OnSysEx()` and reading `device.midiOutSysex()` frames back.

This guarantees that CI and `FL_MCP_MOCK=1` exercise the **exact production framing, chunking, and controller dispatch code** rather than bypassing the protocol.

---

## 5. Closed-Loop DSP Feedback

Rather than generating audio blindly, `fl-studio-mcp` closes the feedback loop between synthesis/mixing and verification:

- **Synthesis ([`hard_techno.py`](../src/fl_studio_mcp/hard_techno.py)):** Vectorized `numpy` kick + sidechained rumble synthesis (1-pole low-pass convolution kernel, `tanh` saturation, BPM-locked 1-bar framing) and multi-style MIDI generation.
- **Inspection ([`audio_analysis.py`](../src/fl_studio_mcp/audio_analysis.py)):** `fl_analyze_audio` measures `peak_dbfs`, `rms_dbfs`, `crest_factor_db`, `dc_offset`, `clipped_samples`, and 5-band spectral energy (`np.fft.rfft` with Hann windowing) so an AI agent can verify headroom and sub-bass balance before adjusting mixer faders or EQ.
