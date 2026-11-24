# fl-studio-mcp

A bidirectional **Model Context Protocol (MCP)** server for controlling **FL Studio** from AI assistants. It combines a custom **MIDI SysEx RPC bridge** inside FL Studio's Python Scripting API, **Windows Win32 GUI automation** for actions not exposed by the scripting API, and built-in **Hard Techno MIDI & WAV sample generators**.

---

## Architecture

```
┌──────────────────┐   stdio (MCP)   ┌─────────────────────┐
│  AI / MCP Client │ ◄─────────────► │     server.py       │
└──────────────────┘                 │  (27 MCP tools)     │
                                     └──────┬───────┬──────┘
                                            │       │
                     SysEx JSON RPC         │       │ Win32 SendInput
                 (bridge.py via mido)       │       │ (win_auto.py)
                                            ▼       ▼
                          ┌──────────────────────────────┐
                          │   loopMIDI Virtual Ports     │
                          │  • FL_MCP_IN  (PC -> FL)     │
                          │  • FL_MCP_OUT (FL -> PC)     │
                          └──────────────┬───────────────┘
                                         │
                                         ▼
                          ┌──────────────────────────────┐
                          │  FL Studio MIDI Controller   │
                          │  fl_script/device_FLStudioMCP│
                          └──────────────────────────────┘
```

### How the SysEx RPC Bridge Works

FL Studio's MIDI Scripting API runs inside an embedded Python environment with no direct network/socket access in older builds and strict thread boundaries. `fl-studio-mcp` solves this with a lightweight, thread-safe **chunked MIDI SysEx RPC protocol**:

- Requests and responses are serialized as JSON, UTF-8 encoded, hex-encoded (7-bit MIDI safe), and split into 512-char chunks.
- Each SysEx frame carries header `F0 7D 46 4D` (`7D 'F' 'M'`), a 14-bit request ID, chunk index, and total chunk count.
- `device_FLStudioMCP.py` reassembles incoming chunks in `OnSysEx`, executes the command against FL Studio's `transport`, `channels`, `patterns`, `mixer`, `playlist`, `plugins`, `ui`, and `general` modules, and streams the JSON response back over `FL_MCP_OUT`.

---

## Features & MCP Tools (27 tools)

### Connection & Transport
| Tool | Description |
| --- | --- |
| `fl_list_midi_ports` | List available MIDI input/output ports to verify loopMIDI setup |
| `fl_ping` | Check connection and read FL version, BPM, transport state, pattern, and counts |
| `fl_transport` | Control `play`, `stop`, `pause`, `record`, `set_loop_mode`, `set_bpm`, `set_song_pos` |
| `fl_undo` | Undo (`up`) or redo (`down`) the last action |

### Channel Rack & Step Sequencer
| Tool | Description |
| --- | --- |
| `fl_channels_list` | List all channels with plugin name, volume, pan, mute/solo, and mixer routing |
| `fl_channel_set` | Update channel name, volume (`0..1`), pan (`-1..1`), mute, solo, mixer track, or selection |
| `fl_step_sequencer` | Program the Step Sequencer grid (`indices` or `bits` mode) |
| `fl_step_sequencer_get` | Read the current Step Sequencer grid for a channel |
| `fl_channel_editor` | Show or hide a channel's plugin/settings window |
| `fl_midi_note` | Trigger live MIDI notes on a channel (with optional auto-release `duration`) |

### Patterns & Playlist
| Tool | Description |
| --- | --- |
| `fl_patterns` | `list`, `select`, `rename`, or `find_or_create` patterns |
| `fl_playlist_list` | List Playlist tracks (1-based) with name, mute, and solo state |
| `fl_playlist_set` | Rename, mute, or solo a Playlist track |

### Mixer, EQ & Plugins
| Tool | Description |
| --- | --- |
| `fl_mixer_list` | List Mixer tracks with peak levels, volumes, mute/solo, and loaded FX plugins |
| `fl_mixer_set` | Update Mixer track name, volume, pan, mute, solo, or bus routing |
| `fl_mixer_eq` | Adjust a Mixer track's built-in 3-band EQ (`low=0`, `mid=1`, `high=2`) |
| `fl_plugin_params` | Inspect parameters of a Channel generator (`slot=-1`) or Mixer FX (`slot=0..9`) |
| `fl_plugin_set` | Set plugin parameter values (`0..1`) or step through presets (`next_preset` / `prev_preset`) |

### Windows GUI Automation & Sample Browser
| Tool | Description |
| --- | --- |
| `fl_ui_focus` | Focus `channel_rack`, `mixer`, `playlist`, `piano_roll`, or `browser` |
| `fl_add_plugin` | Load any generator or FX plugin via FL Studio's Plugin Picker (`F8`) |
| `fl_search_samples` | Search FL Studio's `Packs` directories and `output/` for audio samples |
| `fl_load_sample` | Locate a sample in FL Studio's Browser (`Ctrl+F`) and load it into the Channel Rack |
| `fl_import_midi` | Import a `.mid` file into a channel's Piano Roll (`Ctrl+M`) |
| `fl_new_project` | Start a new FL Studio project (`Ctrl+N`), optionally dismissing unsaved prompts |
| `fl_delete_channel` | Delete a Channel Rack channel (`Alt+Delete`) |

### Hard Techno MIDI & WAV Synthesis
| Tool | Description |
| --- | --- |
| `ht_generate_midi` | Generate `.mid` files for `rumble_bass`, `acid_303`, `rave_stab`, or `schranz_perc` in `phrygian`, `minor`, `harmonic_minor`, or `locrian` |
| `ht_generate_kick_sample` | Synthesize a BPM-synced 1-bar distorted Hard Techno kick + optional sidechained rumble `.wav` |

---

## Requirements

- **Windows 10/11** (required for FL Studio + `win_auto.py` GUI automation)
- **FL Studio 21 / 2024+**
- **loopMIDI** (or another virtual MIDI loopback driver)
- **Python 3.10+** and **[uv](https://docs.astral.sh/uv/)**

---

## Setup

### 1. Create Virtual MIDI Ports (`loopMIDI`)

Install and open [loopMIDI](https://www.tobias-erichsen.de/software/loopmidi.html), then create two virtual ports with these exact names:

- `FL_MCP_IN`
- `FL_MCP_OUT`

> You can override these port names with the `FL_MCP_IN_PORT` and `FL_MCP_OUT_PORT` environment variables.

### 2. Install Python Dependencies

```powershell
git clone https://github.com/Arnau10a/fl-studio-mcp.git
cd fl-studio-mcp
uv sync
```

### 3. Install the FL Studio Controller Script

Run the included installer script (copies `fl_script/device_FLStudioMCP.py` into `~/Documents/Image-Line/FL Studio/Settings/Hardware/FLStudioMCP/`):

```powershell
uv run python scripts/install_fl_script.py
```

### 4. Configure FL Studio MIDI Settings

Open FL Studio and go to **Options -> MIDI Settings**:

1. Under **Output**, select `FL_MCP_OUT` and assign a **Port** number (for example, `10`).
2. Under **Input**, select `FL_MCP_IN`:
   - Enable it (**Enable** toggle ON).
   - Set **Controller type** to **`FLStudioMCP`**.
   - Set **Port** to the **same Port number** (`10`).

> Verify the script loaded cleanly by checking **View -> Script output** in FL Studio (`FLStudioMCP controller initialized.`).

### 5. Register the MCP Server in Your Client

Add `fl-studio` to your MCP client configuration (e.g., Claude Desktop, Cursor, or Antigravity `mcp_config.json`):

```json
{
  "mcpServers": {
    "fl-studio": {
      "command": "C:\\path\\to\\fl-studio-mcp\\.venv\\Scripts\\python.exe",
      "args": [
        "C:\\path\\to\\fl-studio-mcp\\server.py"
      ]
    }
  }
}
```

Or using `uv`:

```json
{
  "mcpServers": {
    "fl-studio": {
      "command": "uv",
      "args": [
        "--directory",
        "C:\\path\\to\\fl-studio-mcp",
        "run",
        "server.py"
      ]
    }
  }
}
```

---

## Standalone Example: 190 BPM Uptempo Arrangement

An example standalone generator is included in [`examples/uptempo_190bpm.py`](examples/uptempo_190bpm.py). It synthesizes a 48-bar Xtra Raw / Uptempo structure (Intro, Break, Build-Up, Fake Drop, Drop 1, Drop 2) in F Phrygian at 190 BPM (5 MIDI tracks + kloenk kick, zaag kick, and 8-bar riser WAVs into `output/`):

```powershell
uv run python examples/uptempo_190bpm.py
```

---

## Project Structure

```text
fl-studio-mcp/
├── server.py                      # FastMCP server & 27 tool definitions
├── bridge.py                      # Thread-safe bidirectional SysEx RPC client
├── win_auto.py                    # Win32 SendInput GUI automation & sample search
├── hard_techno.py                 # Hard Techno MIDI & kick/rumble WAV synthesis
├── fl_script/
│   └── device_FLStudioMCP.py      # FL Studio MIDI Controller script (OnSysEx RPC)
├── scripts/
│   └── install_fl_script.py       # Installer for FL Studio Hardware scripts folder
├── examples/
│   └── uptempo_190bpm.py          # Standalone 48-bar 190 BPM MIDI + WAV generator
├── tests/
│   ├── test_bridge.py             # SysEx chunking, reassembly & error tests
│   ├── test_generators.py         # MIDI & WAV synthesis tests
│   └── test_server.py             # Tool registration & platform guard tests
├── pyproject.toml
├── uv.lock
└── LICENSE
```

---

## Development & Tests

Run the unit test suite (no live FL Studio instance required — MIDI ports are mocked):

```powershell
uv run python -m unittest discover -s tests -v
```

---

## License

[MIT](LICENSE)
