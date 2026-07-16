"""
Probe the TwinCAT router to find where the PLC runtime actually lives.

Run this on the machine where run_doom.bat fails:

    python probe_ads.py               # probe the local AMS Net ID
    python probe_ads.py 5.1.2.3.1.1   # probe a specific Net ID (e.g. a
                                      # user-mode runtime's own Net ID)

It checks the system service (port 10000) to confirm the router is alive
and whether TwinCAT is in RUN or CONFIG mode, then scans the common PLC
runtime ports looking for the m2048.mMatrix symbol. Whatever combination
it reports as FOUND is what belongs in run_doom.bat (TARGET/PORT).
"""

import sys

import pyads

PLC_PORTS = [851, 852, 853, 854]
SYMBOLS = ['m2048.mMatrix', 'MAIN.nState']


def probe(netid):
    print(f'--- probing {netid} ---')

    # System service first: proves the Net ID is routable at all.
    try:
        plc = pyads.Connection(netid, 10000)
        plc.open()
        ads_state, dev_state = plc.read_state()
        mode = {5: 'RUN', 15: 'CONFIG', 16: 'CONFIG'}.get(ads_state, f'state {ads_state}')
        print(f'port 10000 (system service): reachable, TwinCAT mode = {mode}')
        plc.close()
    except Exception as ex:
        print(f'port 10000 (system service): UNREACHABLE — {ex}')
        print('  -> this Net ID is not routed; wrong target.')
        return

    for port in PLC_PORTS:
        try:
            plc = pyads.Connection(netid, port)
            plc.open()
            try:
                ads_state, _ = plc.read_state()
                print(f'port {port}: PLC runtime answering (ADS state {ads_state})')
                for sym in SYMBOLS:
                    try:
                        h = plc.get_handle(sym)
                        plc.release_handle(h)
                        print(f'  port {port}: FOUND symbol {sym}  <== use this port')
                    except Exception as ex:
                        print(f'  port {port}: no symbol {sym} ({ex})')
            finally:
                plc.close()
        except Exception as ex:
            print(f'port {port}: no ADS server ({ex})')


if __name__ == '__main__':
    pyads.open_port()
    local = pyads.get_local_address().netid
    pyads.close_port()
    print(f'local AMS Net ID: {local}')

    targets = sys.argv[1:] or [local]
    for t in targets:
        probe(t)
