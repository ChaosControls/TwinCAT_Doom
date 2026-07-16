"""
PyADS bridge for pushing frames to the Beckhoff PLC and reading Xbox controller state.

Writes the 32x64 UDINT pixel array to m2048.mMatrix via ADS.
Reads Xbox controller state from the DOOM GVL variables.
"""

import struct
import time

try:
    import pyads
    HAS_PYADS = True
except ImportError:
    HAS_PYADS = False


class PLCBridge:
    """Manages the ADS connection to the TwinCAT PLC."""

    AMS_PORT = 851  # PLC runtime 1

    # DOOM GVL symbol names for controller state
    CTRL_SYMBOLS = [
        'DOOM.jsLeftX',
        'DOOM.jsLeftY',
        'DOOM.jsRightX',
        'DOOM.jsRightY',
        'DOOM.btnA',
        'DOOM.btnB',
        'DOOM.btnX',
        'DOOM.btnStart',
    ]

    def __init__(self, ams_net_id, ams_port=None):
        if not HAS_PYADS:
            raise RuntimeError('pyads is not installed — run: pip install pyads')
        self.ams_net_id = ams_net_id
        self.ams_port = ams_port or self.AMS_PORT
        self.plc = None
        self._matrix_handle = None

    def connect(self):
        self.plc = pyads.Connection(self.ams_net_id, self.ams_port)
        self.plc.open()
        self._matrix_handle = self.plc.get_handle('m2048.mMatrix')
        self.set_doom_mode(True)
        print(f'Connected to PLC at {self.ams_net_id}:{self.ams_port}')

    def disconnect(self):
        if self.plc:
            try:
                self.set_doom_mode(False)
            except Exception:
                pass
            if self._matrix_handle is not None:
                try:
                    self.plc.release_handle(self._matrix_handle)
                except Exception:
                    pass
            self.plc.close()
            self.plc = None
        print('Disconnected from PLC')

    def set_doom_mode(self, enabled):
        self.plc.write_by_name('DOOM.bDoomMode', enabled, pyads.PLCTYPE_BOOL)

    def write_frame(self, flat_array):
        """Write 2048 UDINTs to m2048.mMatrix."""
        data = struct.pack(f'<{len(flat_array)}I', *flat_array)
        self.plc.write(
            pyads.INDEXGROUP_SYM_VALBYHND,
            self._matrix_handle,
            data,
            pyads.PLCTYPE_BYTE * len(data),
        )

    def read_controls(self):
        """Read Xbox controller state from DOOM GVL. Returns a controls dict."""
        try:
            vals = self.plc.read_list_by_name({
                'DOOM.jsLeftX':  pyads.PLCTYPE_REAL,
                'DOOM.jsLeftY':  pyads.PLCTYPE_REAL,
                'DOOM.jsRightX': pyads.PLCTYPE_REAL,
                'DOOM.jsRightY': pyads.PLCTYPE_REAL,
                'DOOM.btnA':     pyads.PLCTYPE_BOOL,
                'DOOM.btnB':     pyads.PLCTYPE_BOOL,
                'DOOM.btnX':     pyads.PLCTYPE_BOOL,
                'DOOM.btnStart': pyads.PLCTYPE_BOOL,
            })
        except Exception:
            return {'forward': 0, 'strafe': 0, 'turn': 0, 'shoot': False, 'start': False}

        dead_zone = 15.0
        lx = vals.get('DOOM.jsLeftX', 0)
        ly = vals.get('DOOM.jsLeftY', 0)
        rx = vals.get('DOOM.jsRightX', 0)

        def apply_dz(v):
            return (v / 100.0) if abs(v) > dead_zone else 0.0

        return {
            'forward': apply_dz(ly),
            'strafe':  apply_dz(lx),
            'turn':    apply_dz(rx),
            'shoot':   bool(vals.get('DOOM.btnA', False)),
            'start':   bool(vals.get('DOOM.btnStart', False)),
        }
