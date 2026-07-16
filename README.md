# LED Doom

A Doom-like first-person shooter rendered on a **32x64 Beckhoff LED panel** driven by a TwinCAT 3 PLC.

Python runs a raycasting engine and pushes each frame to the PLC in real time via [PyADS](https://pypi.org/project/pyads/). The PLC transforms the pixel matrix and outputs it to four EL2574 LED terminals. An Xbox controller connected to the PLC provides player input.

> **"Can it play Doom?"** — Yes. Yes it can.

## How It Works

```
┌──────────────┐      ADS write       ┌──────────────┐      EL2574 I/O     ┌──────────┐
│  Python Doom  │ ──── mMatrix ──────▶ │  TwinCAT PLC  │ ────────────────▶  │ LED Panel │
│  Raycaster    │ ◀── controller ──── │  (transform)   │ ◀── Xbox via USB  │  32 x 64  │
└──────────────┘      ADS read        └──────────────┘                     └──────────┘
```

1. **Python** renders a frame (raycasting + sprites) into a 32x64 UDINT array
2. **PyADS** writes the array to `m2048.mMatrix` on the PLC
3. **PLC** runs `fb_MatrixTransform` to convert the matrix into the serpentine `tMatrix` wiring order
4. **PLC** outputs `tMatrix` to the four EL2574 LED terminal slots via the existing LED state machine
5. **Python** reads Xbox controller state from the `DOOM` GVL via ADS
6. Repeat at ~15-20 fps

## Requirements

- Python 3.10+
- A Beckhoff TwinCAT 3 PLC with the LED SoCal Demo project (or equivalent)
- Beckhoff EL2574 LED terminals (4 slots wired to a 32x64 panel)
- Xbox controller connected to the PLC target via USB
- Network connectivity between the Python host and the PLC target

### Python dependencies

```
pip install pyads pygame-ce
```

- `pyads` — required for PLC communication
- `pygame-ce` — required for the preview window (local testing). Community edition of pygame with broader Python version support.

## Setup

### 1. PLC Setup

Add two things to your TwinCAT project:

**a) New GVL: `DOOM`**

Create a new Global Variable List and paste the contents of [`plc_code/GVL_Doom.txt`](plc_code/GVL_Doom.txt).

**b) New Function Block: `fb_Doom`**

Create a new Function Block and paste the contents of [`plc_code/fb_Doom.txt`](plc_code/fb_Doom.txt). This handles the matrix transform and LED output state machine for Doom mode.

**c) Modify MAIN**

Follow the instructions in [`plc_code/MAIN_DoomAdditions.txt`](plc_code/MAIN_DoomAdditions.txt):
1. Add `doom : fb_Doom;` to the VAR block
2. Add the right shoulder button trigger before the CASE statement
3. Add state `40` (Doom Mode) to the CASE block

Build and deploy the modified project to your PLC.

### 2. ADS Route

Ensure an ADS route exists between the Python host and the PLC target. You can set this up in TwinCAT via the ADS Router.

### 3. Install Python packages

```
pip install -r requirements.txt
```

## Running

### Preview mode (no PLC needed — test locally)

```
python main.py --preview
```

Opens a scaled-up pygame window. Use keyboard controls to play.

### PLC mode (push to LED panel)

```
python main.py --plc 5.80.192.2.1.1
```

Replace `5.80.192.2.1.1` with your PLC's AMS Net ID. Xbox controller input is read from the PLC.

### Both (preview window + LED panel)

```
python main.py --preview --plc 5.80.192.2.1.1
```

Useful for debugging — you see the game on your monitor while it plays on the panel.

### Options

| Flag | Description |
|---|---|
| `--preview` | Show pygame preview window |
| `--plc AMS_NET_ID` | Connect to PLC and push frames |
| `--port PORT` | AMS port (default: 851) |
| `--fps FPS` | Target frame rate (default: 20) |
| `--auto-exit` | Exit when the PLC leaves Doom mode (for PLC-launched runs) |

### Self-contained launch (PLC starts Python)

If Python is installed on the same IPC as the PLC runtime, the PLC can launch
the game itself — no manual start needed:

1. Clone this repo onto the IPC (e.g. `C:\LED_Doom`) and `pip install pyads`
2. `MAIN_DoomAdditions.txt` includes an `NT_StartProcess` call (from the
   `Tc2_System` library) that runs [`run_doom.bat`](run_doom.bat) on entry to
   state 40 — adjust `PATHSTR`/`DIRNAME` if you cloned somewhere else
3. Press the right shoulder button → PLC enters Doom mode and spawns Python
4. Hold Y for 3 seconds → PLC leaves state 40, `DOOM.bActive` goes FALSE, and
   Python shuts itself down

The process runs in the TwinCAT service session, so there's no visible
console window — output is redirected to `doom_log.txt` for debugging.

## Controls

### Xbox Controller (PLC mode)

| Input | Action |
|---|---|
| Left stick Y | Move forward / backward |
| Left stick X | Strafe left / right |
| Right stick X | Turn left / right |
| A button | Shoot |
| Start | Restart (on game over) |

### Keyboard (Preview mode)

| Key | Action |
|---|---|
| W / Up | Move forward |
| S / Down | Move backward |
| A | Strafe left |
| D | Strafe right |
| Left / Right | Turn |
| Space | Shoot |
| Enter | Restart (on game over) |
| Esc | Quit |

## Game

- Navigate a maze and eliminate all enemies
- **Imps** (red) — slower, less health
- **Demons** (purple) — faster, tougher
- Pick up green items for health, yellow items for ammo
- Bottom-left HUD bar = health, bottom-right = ammo
- Screen flashes red when you take damage
- Kill all enemies to win

## Technical Notes

- **Resolution**: 32 rows x 64 columns = 2,048 pixels
- **Color format**: UDINT = `(Blue << 16) | (Green << 8) | Red`
- **Rendering**: DDA raycasting algorithm with distance-based shading
- **ADS bandwidth**: ~8 KB per frame (2048 x 4 bytes) — negligible on a local network
- **Frame rate**: Limited by PLC LED output cycle (~65 PLC cycles per LED refresh). At 2ms cycle time = ~7.7 fps, at 1ms = ~15 fps
- **The Python raycaster renders frames in <1ms** — the PLC's LED I/O state machine is the bottleneck

## Project Structure

```
LED_Doom/
├── main.py            # Entry point — game loop, preview, CLI
├── doom_engine.py     # Raycaster engine, game logic, rendering
├── plc_bridge.py      # PyADS communication layer
├── run_doom.bat       # Launched by the PLC via NT_StartProcess
├── requirements.txt
├── README.md
└── plc_code/
    ├── GVL_Doom.txt              # New GVL to add to TwinCAT project
    ├── fb_Doom.txt               # New function block — LED output state machine
    └── MAIN_DoomAdditions.txt    # Modifications for MAIN program
```

## License

MIT
