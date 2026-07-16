"""
LED Doom — Entry point.

Usage:
  python main.py --preview          # Test locally with pygame (keyboard controls)
  python main.py --plc 5.80.192.2.1.1  # Push frames to PLC via ADS (Xbox controls)
  python main.py --preview --plc 5.80.192.2.1.1  # Both: preview window + PLC output
"""

import argparse
import time
import sys

from doom_engine import DoomGame, SCREEN_W, SCREEN_H


def run_preview_only(game, target_fps=20):
    """Run with pygame preview window and keyboard controls."""
    import pygame
    SCALE = 12
    win_w, win_h = SCREEN_W * SCALE, SCREEN_H * SCALE

    pygame.init()
    screen = pygame.display.set_mode((win_w, win_h))
    pygame.display.set_caption('LED Doom — Preview (32x64)')
    clock = pygame.time.Clock()

    running = True
    while running:
        dt = clock.tick(target_fps) / 1000.0
        dt = min(dt, 0.1)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False

        controls = _keyboard_controls(pygame)
        game.update(dt, controls)
        fb = game.render()
        _draw_pygame(screen, fb, SCALE)
        pygame.display.flip()

    pygame.quit()


def run_plc_only(game, bridge, target_fps=20, auto_exit=False):
    """Run with PLC output and Xbox controller (no preview window)."""
    bridge.connect()
    try:
        last = time.time()
        started = last
        seen_active = False
        next_check = 0.0
        while True:
            now = time.time()
            dt = min(now - last, 0.1)
            last = now

            # When launched by the PLC (NT_StartProcess), exit once the
            # PLC leaves Doom mode. Grace period covers the gap between
            # process launch and the first bActive read.
            if auto_exit and now >= next_check:
                next_check = now + 0.25
                if bridge.read_active():
                    seen_active = True
                elif seen_active or now - started > 10.0:
                    print('PLC left Doom mode — shutting down.')
                    break

            controls = bridge.read_controls()
            game.update(dt, controls)
            game.render()
            bridge.write_frame(game.get_matrix_flat())

            elapsed = time.time() - now
            sleep = max(0, 1.0 / target_fps - elapsed)
            if sleep > 0:
                time.sleep(sleep)
    except KeyboardInterrupt:
        print('\nStopping...')
    finally:
        bridge.disconnect()


def run_both(game, bridge, target_fps=20):
    """Run with both pygame preview and PLC output."""
    import pygame
    SCALE = 12
    win_w, win_h = SCREEN_W * SCALE, SCREEN_H * SCALE

    pygame.init()
    screen = pygame.display.set_mode((win_w, win_h))
    pygame.display.set_caption('LED Doom — Preview + PLC')
    clock = pygame.time.Clock()

    bridge.connect()
    try:
        running = True
        while running:
            dt = clock.tick(target_fps) / 1000.0
            dt = min(dt, 0.1)

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    running = False

            plc_ctrl = bridge.read_controls()
            kb_ctrl = _keyboard_controls(pygame)
            controls = _merge_controls(kb_ctrl, plc_ctrl)

            game.update(dt, controls)
            fb = game.render()

            bridge.write_frame(game.get_matrix_flat())
            _draw_pygame(screen, fb, SCALE)
            pygame.display.flip()
    except KeyboardInterrupt:
        print('\nStopping...')
    finally:
        bridge.disconnect()
        pygame.quit()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _keyboard_controls(pygame):
    keys = pygame.key.get_pressed()
    fwd = (1.0 if keys[pygame.K_w] or keys[pygame.K_UP] else 0) \
        - (1.0 if keys[pygame.K_s] or keys[pygame.K_DOWN] else 0)
    strafe = (1.0 if keys[pygame.K_d] else 0) \
           - (1.0 if keys[pygame.K_a] else 0)
    turn = (1.0 if keys[pygame.K_RIGHT] else 0) \
         - (1.0 if keys[pygame.K_LEFT] else 0)
    return {
        'forward': fwd,
        'strafe': strafe,
        'turn': turn,
        'shoot': keys[pygame.K_SPACE],
        'start': keys[pygame.K_RETURN],
    }


def _merge_controls(a, b):
    """Combine keyboard and PLC controls (either source can drive)."""
    return {
        'forward': a['forward'] if a['forward'] else b.get('forward', 0),
        'strafe':  a['strafe']  if a['strafe']  else b.get('strafe', 0),
        'turn':    a['turn']    if a['turn']    else b.get('turn', 0),
        'shoot':   a['shoot']   or b.get('shoot', False),
        'start':   a['start']   or b.get('start', False),
    }


def _draw_pygame(surface, fb, scale):
    """Render the 32x64 frame buffer to a scaled pygame surface."""
    import pygame
    for y in range(SCREEN_H):
        for x in range(SCREEN_W):
            udint = fb[y][x]
            r = udint & 0xFF
            g = (udint >> 8) & 0xFF
            b = (udint >> 16) & 0xFF
            rect = (x * scale, y * scale, scale, scale)
            pygame.draw.rect(surface, (r, g, b), rect)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description='LED Doom — Doom on a 32x64 LED panel')
    parser.add_argument('--preview', action='store_true',
                        help='Show a scaled pygame preview window')
    parser.add_argument('--plc', metavar='AMS_NET_ID',
                        help='Push frames to PLC via ADS (e.g. 5.80.192.2.1.1, '
                             'or "local" when running on the PLC itself)')
    parser.add_argument('--gvl', default='DOOMgvl',
                        help='Name of the DOOM GVL in the TwinCAT project '
                             '(default: DOOMgvl)')
    parser.add_argument('--port', type=int, default=851,
                        help='AMS port (default: 851)')
    parser.add_argument('--fps', type=int, default=20,
                        help='Target frame rate (default: 20)')
    parser.add_argument('--auto-exit', action='store_true',
                        help='Exit when the PLC leaves Doom mode (DOOM.bActive '
                             'goes FALSE). Used when the PLC launches this '
                             'script via NT_StartProcess. PLC-only mode.')
    args = parser.parse_args()

    if not args.preview and not args.plc:
        print('No mode selected. Use --preview for local testing or --plc for PLC output.')
        print('Run with --help for full usage.')
        sys.exit(1)

    game = DoomGame()
    bridge = None

    if args.plc:
        from plc_bridge import PLCBridge
        bridge = PLCBridge(args.plc, args.port, gvl=args.gvl)

    print('=== LED DOOM ===')
    print(f'Resolution: {SCREEN_W}x{SCREEN_H}')
    print(f'Target FPS: {args.fps}')
    if args.preview:
        print('Preview: ON (WASD + arrows + space)')
    if args.plc:
        print(f'PLC: {args.plc}:{args.port}')
    print()

    if args.preview and args.plc:
        run_both(game, bridge, args.fps)
    elif args.preview:
        run_preview_only(game, args.fps)
    else:
        run_plc_only(game, bridge, args.fps, auto_exit=args.auto_exit)


if __name__ == '__main__':
    main()
