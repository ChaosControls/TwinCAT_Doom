"""
PyADS bridge for pushing frames to the Beckhoff PLC and reading Xbox controller state.

Writes the 32x64 UDINT pixel array to m2048.mMatrix via ADS.
Reads Xbox controller state from the DOOMgvl GVL variables.
"""

try:
    import pyads
    HAS_PYADS = True
except ImportError:
    HAS_PYADS = False


class PLCBridge:
    """Manages the ADS connection to the TwinCAT PLC."""

    AMS_PORT = 851  # PLC runtime 1
    GVL = 'DOOMgvl'  # name of the DOOM GVL in the TwinCAT project

    def __init__(self, ams_net_id, ams_port=None, gvl=None):
        if not HAS_PYADS:
            raise RuntimeError('pyads is not installed — run: pip install pyads')
        self.ams_net_id = ams_net_id
        self.ams_port = ams_port or self.AMS_PORT
        self.gvl = gvl or self.GVL
        self.plc = None
        self._matrix_handle = None

    def connect(self):
        # 'local' (or empty) = resolve the machine's own AMS Net ID via the
        # TwinCAT router. '127.0.0.1.1.1' is NOT routed on Windows and fails
        # with ADS error 6 (target port not found).
        if not self.ams_net_id or self.ams_net_id.lower() == 'local':
            pyads.open_port()
            self.ams_net_id = pyads.get_local_address().netid
            pyads.close_port()
            print(f'Resolved local AMS Net ID: {self.ams_net_id}')
        self.plc = pyads.Connection(self.ams_net_id, self.ams_port)
        self.plc.open()
        self._matrix_handle = self.plc.get_handle('m2048.mMatrix')
        print(f'Connected to PLC at {self.ams_net_id}:{self.ams_port}')

    def disconnect(self):
        if self.plc:
            if self._matrix_handle is not None:
                try:
                    self.plc.release_handle(self._matrix_handle)
                except Exception:
                    pass
            self.plc.close()
            self.plc = None
        print('Disconnected from PLC')

    def read_active(self):
        """Read <gvl>.bActive — TRUE while the PLC is in Doom mode (state 40).

        Returns True on a transient read error so a comms hiccup doesn't
        kill the game mid-session.
        """
        try:
            return bool(self.plc.read_by_name(f'{self.gvl}.bActive',
                                              pyads.PLCTYPE_BOOL))
        except Exception:
            return True

    def write_frame(self, flat_array):
        """Write 2048 UDINTs to m2048.mMatrix via the cached symbol handle."""
        self.plc.write_by_name(
            '',
            list(flat_array),
            pyads.PLCTYPE_UDINT * len(flat_array),
            handle=self._matrix_handle,
        )

    def read_controls(self):
        """Read Xbox controller state from DOOM GVL. Returns a controls dict."""
        g = self.gvl
        try:
            vals = self.plc.read_list_by_name({
                f'{g}.jsLeftX':  pyads.PLCTYPE_REAL,
                f'{g}.jsLeftY':  pyads.PLCTYPE_REAL,
                f'{g}.jsRightX': pyads.PLCTYPE_REAL,
                f'{g}.jsRightY': pyads.PLCTYPE_REAL,
                f'{g}.btnA':     pyads.PLCTYPE_BOOL,
                f'{g}.btnB':     pyads.PLCTYPE_BOOL,
                f'{g}.btnX':     pyads.PLCTYPE_BOOL,
                f'{g}.btnStart': pyads.PLCTYPE_BOOL,
            })
        except Exception:
            return {'forward': 0, 'strafe': 0, 'turn': 0, 'shoot': False, 'start': False}

        dead_zone = 15.0
        lx = vals.get(f'{g}.jsLeftX', 0)
        ly = vals.get(f'{g}.jsLeftY', 0)
        rx = vals.get(f'{g}.jsRightX', 0)

        def apply_dz(v):
            return (v / 100.0) if abs(v) > dead_zone else 0.0

        return {
            'forward': apply_dz(ly),
            'strafe':  apply_dz(lx),
            'turn':    apply_dz(rx),
            'shoot':   bool(vals.get(f'{g}.btnA', False)),
            'start':   bool(vals.get(f'{g}.btnStart', False)),
        }
