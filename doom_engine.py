"""
LED Doom — A Doom-like raycaster for 32x64 LED panels.

Renders to a 32x64 UDINT pixel buffer suitable for Beckhoff EL2574
LED terminals. Color format: UDINT = (B << 16) | (G << 8) | R.

Flow: title screen (fade in + Doom-style melt) -> 5 levels, each with
a key and an EXIT door -> boss on level 5 drops the final key ->
YOU WIN with fireworks, or YOU DIED -> restart after 10 seconds.
"""

import math
import random

# ---------------------------------------------------------------------------
# Display constants
# ---------------------------------------------------------------------------
SCREEN_W = 64
SCREEN_H = 32
HALF_H = SCREEN_H // 2

# ---------------------------------------------------------------------------
# Color helpers  (UDINT = 0x00BBGGRR, little-endian on PLC)
# ---------------------------------------------------------------------------
def rgb(r, g, b):
    return (min(255, max(0, b)) << 16) | (min(255, max(0, g)) << 8) | min(255, max(0, r))

def shade_color(color, factor):
    factor = max(0.0, min(1.0, factor))
    r = int((color & 0xFF) * factor)
    g = int(((color >> 8) & 0xFF) * factor)
    b = int(((color >> 16) & 0xFF) * factor)
    return (b << 16) | (g << 8) | r

def blend_color(base, overlay, alpha):
    br, bg, bb = base & 0xFF, (base >> 8) & 0xFF, (base >> 16) & 0xFF
    or_, og, ob = overlay & 0xFF, (overlay >> 8) & 0xFF, (overlay >> 16) & 0xFF
    r = int(br * (1 - alpha) + or_ * alpha)
    g = int(bg * (1 - alpha) + og * alpha)
    b = int(bb * (1 - alpha) + ob * alpha)
    return rgb(r, g, b)

# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------
C_BLACK = rgb(0, 0, 0)
C_CEIL  = rgb(25, 25, 35)
C_FLOOR = rgb(55, 55, 50)
C_FLASH = rgb(255, 220, 80)
C_WHITE = rgb(255, 255, 255)

WALL_COLORS = {
    1: rgb(150, 150, 155),   # gray stone
    2: rgb(165, 50, 45),     # red brick
    3: rgb(135, 95, 45),     # brown wood
    4: rgb(45, 65, 155),     # blue tech
    9: rgb(140, 30, 190),    # purple EXIT door
}
DOOR_TILE = 9

C_ENEMY_IMP   = rgb(195, 40, 25)     # red
C_ENEMY_DEMON = rgb(235, 120, 20)    # orange
C_ENEMY_BOSS  = rgb(190, 140, 70)    # tan — cyberdemon-ish
C_EYE         = rgb(255, 210, 0)

C_ITEM_HEALTH = rgb(25, 210, 25)     # green cross
C_ITEM_AMMO   = rgb(40, 120, 255)    # blue bullet
C_ITEM_KEY    = rgb(255, 210, 40)    # yellow key

C_GUN         = rgb(115, 115, 120)
C_GUN_DARK    = rgb(65, 65, 70)
C_HUD_HP      = rgb(0, 195, 0)
C_HUD_HP_BG   = rgb(55, 0, 0)
C_HUD_AM      = rgb(40, 120, 255)
C_HUD_AM_BG   = rgb(0, 10, 45)
C_TITLE_TOP   = rgb(200, 200, 210)
C_TITLE_DOOM  = rgb(210, 30, 20)
C_TEXT_WIN    = rgb(255, 220, 60)
C_TEXT_DIED   = rgb(230, 30, 20)

FIREWORK_COLORS = [
    rgb(255, 60, 60), rgb(60, 255, 60), rgb(80, 120, 255),
    rgb(255, 230, 60), rgb(255, 80, 255), rgb(80, 255, 255),
    rgb(255, 255, 255),
]

# ---------------------------------------------------------------------------
# Sprite stencils — 'X' = body pixel, 'E' = eye pixel, '.' = transparent.
# Stretched to the sprite's on-screen rectangle with nearest-neighbor
# sampling, so the silhouette holds up close and far away.
# ---------------------------------------------------------------------------
IMP_SHAPE = [
    '...XX...',
    '..EXXE..',
    '..EXXE..',
    '...XX...',
    '.XXXXXX.',
    'XXXXXXXX',
    'X.XXXX.X',
    'X.XXXX.X',
    '..XXXX..',
    '..X..X..',
    '..X..X..',
    '.XX..XX.',
]

DEMON_SHAPE = [
    'X......X',
    'X.XXXX.X',
    '..EXXE..',
    '..EXXE..',
    '.XXXXXX.',
    'XXXXXXXX',
    'XXXXXXXX',
    'X.XXXX.X',
    '..XXXX..',
    '.XX..XX.',
    '.XX..XX.',
]

BOSS_SHAPE = [
    'X........X',
    'XX......XX',
    '.X.XXXX.X.',
    '..EXXXXE..',
    '..EXXXXE..',
    '..XXXXXX..',
    '.XXXXXXXX.',
    'XXXXXXXXXX',
    'XX.XXXX.XX',
    'XX.XXXX.XX',
    '..XXXXXX..',
    '..XX..XX..',
    '..XX..XX..',
    '.XXX..XXX.',
]

HEALTH_SHAPE = [
    '..XX..',
    '..XX..',
    'XXXXXX',
    'XXXXXX',
    '..XX..',
    '..XX..',
]

AMMO_SHAPE = [
    '..XX..',
    '.XXXX.',
    '.XXXX.',
    '.XXXX.',
    '.XXXX.',
    '.XXXX.',
    'XXXXXX',
]

KEY_SHAPE = [
    '.XXX..',
    'X...X.',
    'X...X.',
    '.XXX..',
    '..X...',
    '..X...',
    '..XX..',
    '..X...',
    '..XX..',
]

# ---------------------------------------------------------------------------
# Tiny bitmap font (3-5 px wide, 5 tall)
# ---------------------------------------------------------------------------
FONT = {
    'A': ['XXX', 'X.X', 'XXX', 'X.X', 'X.X'],
    'C': ['XXX', 'X..', 'X..', 'X..', 'XXX'],
    'D': ['XX.', 'X.X', 'X.X', 'X.X', 'XX.'],
    'E': ['XXX', 'X..', 'XXX', 'X..', 'XXX'],
    'I': ['XXX', '.X.', '.X.', '.X.', 'XXX'],
    'L': ['X..', 'X..', 'X..', 'X..', 'XXX'],
    'M': ['X...X', 'XX.XX', 'X.X.X', 'X...X', 'X...X'],
    'N': ['X..X', 'XX.X', 'X.XX', 'X..X', 'X..X'],
    'O': ['XXX', 'X.X', 'X.X', 'X.X', 'XXX'],
    'T': ['XXX', '.X.', '.X.', '.X.', '.X.'],
    'U': ['X.X', 'X.X', 'X.X', 'X.X', 'XXX'],
    'V': ['X.X', 'X.X', 'X.X', 'X.X', '.X.'],
    'W': ['X...X', 'X...X', 'X.X.X', 'XX.XX', 'X...X'],
    'X': ['X.X', 'X.X', '.X.', 'X.X', 'X.X'],
    'Y': ['X.X', 'X.X', '.X.', '.X.', '.X.'],
    '1': ['.X.', 'XX.', '.X.', '.X.', 'XXX'],
    '2': ['XX.', '..X', '.X.', 'X..', 'XXX'],
    '3': ['XX.', '..X', '.X.', '..X', 'XX.'],
    '4': ['X.X', 'X.X', 'XXX', '..X', '..X'],
    '5': ['XXX', 'X..', 'XX.', '..X', 'XX.'],
    ' ': ['..', '..', '..', '..', '..'],
}

def text_width(text, scale=1):
    w = 0
    for ch in text:
        glyph = FONT.get(ch.upper())
        w += (len(glyph[0]) if glyph else 1) * scale + scale
    return w - scale if w else 0

def draw_text(fb, x0, y0, text, color, scale=1):
    x = x0
    for ch in text:
        glyph = FONT.get(ch.upper())
        if glyph is None:
            x += 2 * scale
            continue
        for gy, row in enumerate(glyph):
            for gx, c in enumerate(row):
                if c != 'X':
                    continue
                for sy in range(scale):
                    for sx in range(scale):
                        px = x + gx * scale + sx
                        py = y0 + gy * scale + sy
                        if 0 <= px < SCREEN_W and 0 <= py < SCREEN_H:
                            fb[py][px] = color
        x += (len(glyph[0]) + 1) * scale

# EXIT texture painted on door walls when the player is close: 16x16,
# 1 = white text pixel, 0 = door color.
EXIT_TEX = [[0] * 16 for _ in range(16)]
def _build_exit_tex():
    rows = [[0] * 16 for _ in range(16)]
    x = 0
    for ch in 'EXIT':
        glyph = FONT[ch]
        for gy, row in enumerate(glyph):
            for gx, c in enumerate(row):
                if c == 'X':
                    rows[5 + gy][x + gx] = 1
        x += len(glyph[0]) + 1
    return rows
EXIT_TEX = _build_exit_tex()

# ---------------------------------------------------------------------------
# Level data — ASCII maps.
#   # 2 3 4 = wall types    D = EXIT door    . = floor    P = player start
#   i = imp   d = demon   B = boss (drops the key)
#   k = key   h = health  a = ammo
# ---------------------------------------------------------------------------
LEVEL_MAPS = [
    # Level 1 — 4 enemies
    [
        '####################',
        '#P.................#',
        '#........33........#',
        '#...a....33....h...#',
        '#..................#',
        '####..####..####...#',
        '#.........i........#',
        '#..i............d..#',
        '#..................#',
        '#...###....###.....#',
        '#...#..........h...#',
        '#...#..i...........#',
        '#...###....###..a..#',
        '#..........#k......#',
        '#..........#.......#',
        '#########D##########',
    ],
    # Level 2 — 6 enemies
    [
        '22222222222222222222',
        '2P.....2.........a.2',
        '2......2...........2',
        '2..h...2....i......2',
        '2......2222....22222',
        '2..........i.......2',
        '2222..2............2',
        '2.....2............D',
        '2....222....22..d..2',
        '2....2.2....22.....2',
        '2.i..222...........2',
        '2..........i.....h.2',
        '2.....a............2',
        '2.d.......222......2',
        '2.........2k.......2',
        '22222222222222222222',
    ],
    # Level 3 — 8 enemies
    [
        '33333333333333333333',
        '3..................3',
        '3.P....3....i....a.3',
        '3......3...........3',
        '3..33333....33333..3',
        '3..3.............h.3',
        '3..3..i......d.....3',
        '3..3.....i.........3',
        'D..................3',
        '3....333....333....3',
        '3.h..3........3..i.3',
        '3....3...id...3....3',
        '3....3........3....3',
        '3....333..333.3..d.3',
        '3.a.......k...3....3',
        '33333333333333333333',
    ],
    # Level 4 — 10 enemies
    [
        '44444444444444444444',
        '4........4.......P.4',
        '4..i.....4.........4',
        '4..k.....4....444..4',
        '4..444...4....4....4',
        '4....4........4..i.4',
        '4.d..4...44...4....4',
        '4..................4',
        '4..44444....44444..4',
        '4..4..i......d..4..4',
        '4..4............4..4',
        '4...........i......4',
        '4.h..44....44...a..4',
        '4.....d........d...4',
        '4...i..........i...4',
        '4444444444D444444444',
    ],
    # Level 5 — 8 enemies + BOSS (boss drops the key)
    [
        '22222222222222222222',
        '2P.......22........2',
        '2........22....i...2',
        '2..i.....22........2',
        '2..................2',
        '2..222........222..2',
        '2..2..........2....2',
        '2..2....d.....2..i.2',
        '2..................2',
        '2......2...2.......2',
        '2..d...............2',
        '2........B.....d...2',
        '2..................2',
        '2......2...2.......2',
        '2..................2',
        '2...i........i.....2',
        '2..................2',
        '2..h............a..2',
        '2..................2',
        '2222222222D222222222',
    ],
]

WALL_CHARS = {'#': 1, '2': 2, '3': 3, '4': 4, 'D': DOOR_TILE}

def parse_level(ascii_map):
    grid, enemies, items = [], [], []
    player = None
    door = None
    for y, row in enumerate(ascii_map):
        grid_row = []
        for x, ch in enumerate(row):
            tile = WALL_CHARS.get(ch, 0)
            grid_row.append(tile)
            cx, cy = x + 0.5, y + 0.5
            if ch == 'P':
                player = (cx, cy)
            elif ch == 'D':
                door = (x, y)
            elif ch == 'i':
                enemies.append((cx, cy, 'imp'))
            elif ch == 'd':
                enemies.append((cx, cy, 'demon'))
            elif ch == 'B':
                enemies.append((cx, cy, 'boss'))
            elif ch == 'k':
                items.append((cx, cy, 'key'))
            elif ch == 'h':
                items.append((cx, cy, 'health'))
            elif ch == 'a':
                items.append((cx, cy, 'ammo'))
        grid.append(grid_row)
    return {'grid': grid, 'player': player, 'door': door,
            'enemies': enemies, 'items': items}

def _validate_levels():
    for i, m in enumerate(LEVEL_MAPS):
        widths = {len(r) for r in m}
        assert len(widths) == 1, f'level {i+1}: ragged rows {widths}'
        lv = parse_level(m)
        assert lv['player'], f'level {i+1}: no player start'
        assert lv['door'], f'level {i+1}: no exit door'
        has_key = any(k == 'key' for _, _, k in lv['items'])
        has_boss = any(k == 'boss' for _, _, k in lv['enemies'])
        assert has_key or has_boss, f'level {i+1}: no key and no boss'
_validate_levels()

# ---------------------------------------------------------------------------
# Entities
# ---------------------------------------------------------------------------
class Player:
    def __init__(self, x, y, angle):
        self.x = x
        self.y = y
        self.angle = angle
        self.health = 100
        self.ammo = 50
        self.shoot_timer = 0.0
        self.is_shooting = False
        self.muzzle_timer = 0.0
        self.bob_phase = 0.0
        self.has_key = False
        self.kills = 0
        self.dead = False


class Enemy:
    TYPES = {
        'imp':   {'hp': 100, 'color': C_ENEMY_IMP,   'speed': 1.5, 'damage': 8,
                  'shape': IMP_SHAPE,   'scale': 1.0},
        'demon': {'hp': 150, 'color': C_ENEMY_DEMON, 'speed': 2.2, 'damage': 14,
                  'shape': DEMON_SHAPE, 'scale': 1.0},
        'boss':  {'hp': 500, 'color': C_ENEMY_BOSS,  'speed': 1.1, 'damage': 20,
                  'shape': BOSS_SHAPE,  'scale': 1.55},
    }

    def __init__(self, x, y, kind='imp'):
        t = self.TYPES[kind]
        self.x = x
        self.y = y
        self.kind = kind
        self.hp = t['hp']
        self.color = t['color']
        self.shape = t['shape']
        self.speed = t['speed']
        self.damage = t['damage']
        self.scale = t['scale']
        self.alive = True
        self.alert = False
        self.attack_cd = 0.0
        self.hurt_timer = 0.0
        # Wander/strafe personality
        self.phase = random.uniform(0, 2 * math.pi)
        self.wander_t = 0.0
        self.wander_dir = random.uniform(0, 2 * math.pi)


class Item:
    TYPES = {
        'health': {'color': C_ITEM_HEALTH, 'value': 25, 'shape': HEALTH_SHAPE, 'scale': 0.45},
        'ammo':   {'color': C_ITEM_AMMO,   'value': 15, 'shape': AMMO_SHAPE,   'scale': 0.45},
        'key':    {'color': C_ITEM_KEY,    'value': 0,  'shape': KEY_SHAPE,    'scale': 0.55},
    }

    def __init__(self, x, y, kind='health'):
        t = self.TYPES[kind]
        self.x = x
        self.y = y
        self.kind = kind
        self.color = t['color']
        self.value = t['value']
        self.shape = t['shape']
        self.scale = t['scale']
        self.picked_up = False


# ---------------------------------------------------------------------------
# Game
# ---------------------------------------------------------------------------
TITLE_FADE = 1.6    # seconds fading in
TITLE_HOLD = 1.4    # seconds fully visible
TITLE_MELT = 1.6    # seconds melting away
END_RESTART_TIME = 10.0

class DoomGame:
    def __init__(self):
        self.fb = [[C_BLACK] * SCREEN_W for _ in range(SCREEN_H)]
        self.zbuf = [0.0] * SCREEN_W
        self.time = 0.0
        self.damage_flash = 0.0

        self.mode = 'title'    # title -> play -> win / dead
        self.title_t = 0.0
        self.title_fb = self._build_title_fb()
        # Doom-style melt: per-column start delays, neighbors similar.
        delays = [random.uniform(0, 0.5)]
        for _ in range(SCREEN_W - 1):
            delays.append(min(0.6, max(0.0, delays[-1] + random.uniform(-0.12, 0.12))))
        self.melt_delays = delays

        self.level_index = 0
        self.player = None
        self.end_timer = 0.0
        self.level_flash = 0.0
        self.fireworks = []
        self.fw_spawn_t = 0.0

        self._load_level(0, fresh_player=True)

    def restart(self):
        self.__init__()

    # -------------------------------------------------------------------
    # Levels
    # -------------------------------------------------------------------
    def _load_level(self, index, fresh_player=False):
        self.level_index = index
        lv = parse_level(LEVEL_MAPS[index])
        self.level = lv['grid']
        self.map_w = len(self.level[0])
        self.map_h = len(self.level)
        self.door_tile = lv['door']

        px, py = lv['player']
        angle = 0.0 if px < self.map_w / 2 else math.pi
        if fresh_player or self.player is None:
            self.player = Player(px, py, angle)
        else:
            # Carry health/ammo between levels, Doom-style.
            self.player.x, self.player.y, self.player.angle = px, py, angle
            self.player.has_key = False

        self.enemies = [Enemy(x, y, k) for x, y, k in lv['enemies']]
        self.items = [Item(x, y, k) for x, y, k in lv['items']]
        self.level_flash = 1.4

    # -------------------------------------------------------------------
    # Update
    # -------------------------------------------------------------------
    def update(self, dt, controls):
        self.time += dt

        if self.mode == 'title':
            self.title_t += dt
            if controls.get('start') or controls.get('shoot'):
                self.title_t = TITLE_FADE + TITLE_HOLD + TITLE_MELT
            if self.title_t >= TITLE_FADE + TITLE_HOLD + TITLE_MELT:
                self.mode = 'play'
            return

        if self.mode in ('win', 'dead'):
            self.end_timer -= dt
            if self.mode == 'win':
                self._update_fireworks(dt)
            if self.end_timer <= 0 or controls.get('start'):
                self.restart()
            return

        # ------------------------- play -------------------------------
        p = self.player
        self.level_flash = max(0.0, self.level_flash - dt)

        # Turn
        p.angle += controls.get('turn', 0) * 3.0 * dt

        # Move
        fwd = controls.get('forward', 0)
        strafe = controls.get('strafe', 0)
        speed = 3.5 * dt

        dx = math.cos(p.angle) * fwd + math.cos(p.angle + math.pi / 2) * strafe
        dy = math.sin(p.angle) * fwd + math.sin(p.angle + math.pi / 2) * strafe
        mag = math.hypot(dx, dy)
        if mag > 0:
            p.bob_phase += dt * 7.0     # weapon sway while moving
            dx, dy = dx / mag * speed, dy / mag * speed
            margin = 0.25
            nx = p.x + dx
            if self._passable(nx, p.y, margin):
                p.x = nx
            ny = p.y + dy
            if self._passable(p.x, ny, margin):
                p.y = ny

        # Shoot
        p.shoot_timer -= dt
        p.muzzle_timer = max(0.0, p.muzzle_timer - dt)
        if controls.get('shoot') and p.shoot_timer <= 0 and p.ammo > 0:
            p.shoot_timer = 0.35
            p.ammo -= 1
            p.is_shooting = True
            p.muzzle_timer = 0.12
            self._fire_weapon()

        # Enemies
        for e in self.enemies:
            if not e.alive:
                continue
            e.hurt_timer = max(0, e.hurt_timer - dt)
            e.attack_cd = max(0, e.attack_cd - dt)
            dist = math.hypot(e.x - p.x, e.y - p.y)

            if dist < 8 or p.is_shooting:
                e.alert = True

            if e.alert and dist > 1.2:
                # Chase with a sideways weave so they feel alive.
                angle = math.atan2(p.y - e.y, p.x - e.x)
                angle += math.sin(self.time * 3.0 + e.phase) * 0.55
                self._move_enemy(e, angle, e.speed, dt)
            elif not e.alert:
                # Idle wander: amble in a random direction, re-roll
                # every few seconds or when bumping a wall.
                e.wander_t -= dt
                if e.wander_t <= 0:
                    e.wander_t = random.uniform(1.5, 3.5)
                    e.wander_dir = random.uniform(0, 2 * math.pi)
                if not self._move_enemy(e, e.wander_dir, e.speed * 0.45, dt):
                    e.wander_t = 0.0

            if e.alert and dist < 1.5 and e.attack_cd <= 0:
                p.health -= e.damage
                e.attack_cd = 1.0
                self.damage_flash = 0.15
                if p.health <= 0:
                    p.health = 0
                    p.dead = True
                    self.mode = 'dead'
                    self.end_timer = END_RESTART_TIME
                    return

        # Pickups
        for item in self.items:
            if item.picked_up:
                continue
            if math.hypot(item.x - p.x, item.y - p.y) < 0.7:
                if item.kind == 'health' and p.health < 100:
                    p.health = min(100, p.health + item.value)
                    item.picked_up = True
                elif item.kind == 'ammo':
                    p.ammo += item.value
                    item.picked_up = True
                elif item.kind == 'key':
                    p.has_key = True
                    item.picked_up = True

        # Exit door: needs the key, walk up to it to leave the level.
        if p.has_key and self.door_tile:
            dx_, dy_ = self.door_tile
            if math.hypot(dx_ + 0.5 - p.x, dy_ + 0.5 - p.y) < 1.3:
                if self.level_index + 1 >= len(LEVEL_MAPS):
                    self.mode = 'win'
                    self.end_timer = END_RESTART_TIME
                    self.fireworks = []
                    self.fw_spawn_t = 0.0
                else:
                    self._load_level(self.level_index + 1)

        self.damage_flash = max(0, self.damage_flash - dt)
        p.is_shooting = False

    def _move_enemy(self, e, angle, speed, dt):
        enx = e.x + math.cos(angle) * speed * dt
        eny = e.y + math.sin(angle) * speed * dt
        if self._passable(enx, eny, 0.3):
            e.x, e.y = enx, eny
            return True
        return False

    def _passable(self, x, y, margin):
        for cx in [x - margin, x + margin]:
            for cy in [y - margin, y + margin]:
                ix, iy = int(cx), int(cy)
                if ix < 0 or iy < 0 or ix >= self.map_w or iy >= self.map_h:
                    return False
                if self.level[iy][ix] > 0:
                    return False
        return True

    def _fire_weapon(self):
        p = self.player
        best, best_dist = None, float('inf')
        for e in self.enemies:
            if not e.alive:
                continue
            diff = math.atan2(e.y - p.y, e.x - p.x) - p.angle
            diff = (diff + math.pi) % (2 * math.pi) - math.pi
            aim = 0.12 + (0.10 if e.kind == 'boss' else 0.0)
            if abs(diff) < aim:
                d = math.hypot(e.x - p.x, e.y - p.y)
                if d < best_dist and d < 15 and not self._blocked(p.x, p.y, e.x, e.y):
                    best, best_dist = e, d
        if best:
            best.hp -= 35
            best.hurt_timer = 0.1
            if best.hp <= 0:
                self._on_enemy_killed(best)

    def _on_enemy_killed(self, e):
        e.alive = False
        self.player.kills += 1
        if e.kind == 'boss':
            # The boss carries the final key.
            self.items.append(Item(e.x, e.y, 'key'))

    def _blocked(self, x1, y1, x2, y2):
        steps = int(math.hypot(x2 - x1, y2 - y1) * 5)
        for i in range(1, steps):
            t = i / steps
            ix, iy = int(x1 + (x2 - x1) * t), int(y1 + (y2 - y1) * t)
            if 0 <= ix < self.map_w and 0 <= iy < self.map_h:
                if self.level[iy][ix] > 0:
                    return True
            else:
                return True
        return False

    def _update_fireworks(self, dt):
        self.fw_spawn_t -= dt
        if self.fw_spawn_t <= 0:
            self.fw_spawn_t = random.uniform(0.35, 0.7)
            bx = random.uniform(8, SCREEN_W - 8)
            by = random.uniform(4, SCREEN_H * 0.6)
            color = random.choice(FIREWORK_COLORS)
            n = 14
            for i in range(n):
                a = 2 * math.pi * i / n + random.uniform(-0.15, 0.15)
                v = random.uniform(6, 13)
                self.fireworks.append({
                    'x': bx, 'y': by,
                    'vx': math.cos(a) * v, 'vy': math.sin(a) * v,
                    'life': random.uniform(0.8, 1.3), 'color': color,
                })
        alive = []
        for fw in self.fireworks:
            fw['life'] -= dt
            if fw['life'] <= 0:
                continue
            fw['vy'] += 9.0 * dt       # gravity
            fw['x'] += fw['vx'] * dt
            fw['y'] += fw['vy'] * dt
            alive.append(fw)
        self.fireworks = alive

    # -------------------------------------------------------------------
    # Render
    # -------------------------------------------------------------------
    def render(self):
        if self.mode == 'title':
            self._render_title()
            return self.fb

        self._render_walls()
        self._render_sprites()
        self._render_weapon()
        self._render_hud()

        if self.damage_flash > 0:
            alpha = min(1.0, self.damage_flash / 0.15) * 0.5
            red_tint = rgb(200, 0, 0)
            for y in range(SCREEN_H - 1):
                for x in range(SCREEN_W):
                    self.fb[y][x] = blend_color(self.fb[y][x], red_tint, alpha)

        if self.mode == 'play' and self.level_flash > 0:
            label = f'LEVEL {self.level_index + 1}'
            w = text_width(label)
            draw_text(self.fb, (SCREEN_W - w) // 2, 3, label, C_WHITE)

        if self.mode == 'dead':
            for y in range(SCREEN_H):
                for x in range(SCREEN_W):
                    self.fb[y][x] = shade_color(self.fb[y][x], 0.3)
            w = text_width('YOU DIED')
            draw_text(self.fb, (SCREEN_W - w) // 2, HALF_H - 3, 'YOU DIED', C_TEXT_DIED)

        if self.mode == 'win':
            for y in range(SCREEN_H):
                for x in range(SCREEN_W):
                    self.fb[y][x] = shade_color(self.fb[y][x], 0.25)
            for fw in self.fireworks:
                px, py = int(fw['x']), int(fw['y'])
                if 0 <= px < SCREEN_W and 0 <= py < SCREEN_H:
                    c = fw['color']
                    if fw['life'] < 0.4:
                        c = shade_color(c, fw['life'] / 0.4)
                    self.fb[py][px] = c
            w = text_width('YOU WIN')
            draw_text(self.fb, (SCREEN_W - w) // 2, HALF_H - 3, 'YOU WIN', C_TEXT_WIN)

        return self.fb

    # ----------------------- title screen ------------------------------
    def _build_title_fb(self):
        fb = [[C_BLACK] * SCREEN_W for _ in range(SCREEN_H)]
        w1 = text_width('TWINCAT')
        draw_text(fb, (SCREEN_W - w1) // 2, 5, 'TWINCAT', C_TITLE_TOP)
        w2 = text_width('DOOM', scale=2)
        draw_text(fb, (SCREEN_W - w2) // 2, 14, 'DOOM', C_TITLE_DOOM, scale=2)
        return fb

    def _render_title(self):
        t = self.title_t
        if t < TITLE_FADE + TITLE_HOLD:
            # Fade in, then hold.
            alpha = min(1.0, t / TITLE_FADE)
            for y in range(SCREEN_H):
                for x in range(SCREEN_W):
                    self.fb[y][x] = shade_color(self.title_fb[y][x], alpha)
        else:
            # Melt: render the level-1 view underneath, slide the title
            # screen down per-column (classic Doom screen melt).
            self._render_walls()
            self._render_sprites()
            self._render_weapon()
            self._render_hud()
            mt = t - TITLE_FADE - TITLE_HOLD
            for x in range(SCREEN_W):
                active = mt - self.melt_delays[x]
                if active <= 0:
                    shift = 0
                else:
                    shift = int(active * active * 55)
                if shift >= SCREEN_H:
                    continue
                for y in range(SCREEN_H - 1, -1, -1):
                    src = y - shift
                    if src >= 0:
                        self.fb[y][x] = self.title_fb[src][x]

    # ----------------------- world ------------------------------------
    def _render_walls(self):
        p = self.player
        dir_x = math.cos(p.angle)
        dir_y = math.sin(p.angle)
        plane_x = -dir_y * 0.66
        plane_y = dir_x * 0.66

        for x in range(SCREEN_W):
            cam_x = 2.0 * x / SCREEN_W - 1.0
            rdx = dir_x + plane_x * cam_x
            rdy = dir_y + plane_y * cam_x

            mx, my = int(p.x), int(p.y)

            ddx = abs(1.0 / rdx) if rdx != 0 else 1e30
            ddy = abs(1.0 / rdy) if rdy != 0 else 1e30

            if rdx < 0:
                step_x, sx = -1, (p.x - mx) * ddx
            else:
                step_x, sx = 1, (mx + 1.0 - p.x) * ddx

            if rdy < 0:
                step_y, sy = -1, (p.y - my) * ddy
            else:
                step_y, sy = 1, (my + 1.0 - p.y) * ddy

            side = 0
            for _ in range(64):
                if sx < sy:
                    sx += ddx
                    mx += step_x
                    side = 0
                else:
                    sy += ddy
                    my += step_y
                    side = 1
                if 0 <= mx < self.map_w and 0 <= my < self.map_h:
                    if self.level[my][mx] > 0:
                        break
                else:
                    break

            if side == 0:
                perp = (mx - p.x + (1 - step_x) / 2) / rdx if rdx != 0 else 1e30
            else:
                perp = (my - p.y + (1 - step_y) / 2) / rdy if rdy != 0 else 1e30
            perp = max(perp, 0.001)
            self.zbuf[x] = perp

            line_h = int(SCREEN_H / perp)
            ds = max(0, HALF_H - line_h // 2)
            de = min(SCREEN_H - 1, HALF_H + line_h // 2)

            wt = self.level[my][mx] if 0 <= mx < self.map_w and 0 <= my < self.map_h else 1
            base = WALL_COLORS.get(wt, WALL_COLORS[1])
            sf = max(0.12, 1.0 - perp * 0.07)
            if side == 1:
                sf *= 0.7
            wc = shade_color(base, sf)

            # Door texture: white 'EXIT' lettering when close enough.
            door_tex_x = -1
            if wt == DOOR_TILE and perp < 5.0 and de > ds:
                if side == 0:
                    wall_x = p.y + perp * rdy
                else:
                    wall_x = p.x + perp * rdx
                wall_x -= math.floor(wall_x)
                door_tex_x = min(15, int(wall_x * 16))
                # Keep the lettering reading left-to-right regardless of
                # which face of the door wall we're looking at.
                if (side == 0 and rdx < 0) or (side == 1 and rdy > 0):
                    door_tex_x = 15 - door_tex_x
            exit_white = shade_color(C_WHITE, max(0.4, 1.0 - perp * 0.07))

            for y in range(SCREEN_H):
                if y < ds:
                    self.fb[y][x] = C_CEIL
                elif y <= de:
                    if door_tex_x >= 0:
                        ty_ = (y - ds) * 16 // (de - ds + 1)
                        if EXIT_TEX[ty_][door_tex_x]:
                            self.fb[y][x] = exit_white
                            continue
                    self.fb[y][x] = wc
                else:
                    ff = max(0.15, 1.0 - (y - HALF_H) * 0.04)
                    self.fb[y][x] = shade_color(C_FLOOR, ff)

    def _render_sprites(self):
        p = self.player
        dir_x = math.cos(p.angle)
        dir_y = math.sin(p.angle)
        plane_x = -dir_y * 0.66
        plane_y = dir_x * 0.66

        det = plane_x * dir_y - dir_x * plane_y
        if abs(det) < 1e-10:
            return
        inv_det = 1.0 / det

        sprites = []
        for e in self.enemies:
            if e.alive:
                c = rgb(255, 120, 120) if e.hurt_timer > 0 else e.color
                sprites.append((e.x, e.y, c, e.scale, e.shape))
        for item in self.items:
            if not item.picked_up:
                pulse = 0.65 + 0.35 * math.sin(self.time * 5)
                sprites.append((item.x, item.y, shade_color(item.color, pulse),
                                item.scale, item.shape))

        sprites.sort(
            key=lambda s: (s[0] - p.x) ** 2 + (s[1] - p.y) ** 2, reverse=True
        )

        for sx, sy, color, height_scale, shape in sprites:
            rx, ry = sx - p.x, sy - p.y
            tx = inv_det * (dir_y * rx - dir_x * ry)
            ty = inv_det * (-plane_y * rx + plane_x * ry)
            if ty <= 0.1:
                continue

            scr_x = int((SCREEN_W / 2) * (1 + tx / ty))
            spr_h = abs(int(SCREEN_H * height_scale / ty))
            spr_w = max(1, spr_h // 2)

            ds_y = max(0, HALF_H - spr_h // 2)
            de_y = min(SCREEN_H - 2, HALF_H + spr_h // 2)

            sf = max(0.15, 1.0 - ty * 0.08)
            sc = shade_color(color, sf)

            # Unclamped sprite rect origin — needed to map screen pixels
            # back to stencil coordinates even when partially off-screen.
            top = HALF_H - spr_h // 2
            left = scr_x - spr_w // 2

            x_start = max(0, left)
            x_end = min(SCREEN_W, scr_x + spr_w // 2 + 1)
            for dx in range(x_start, x_end):
                if ty >= self.zbuf[dx]:
                    continue
                if shape:
                    # Sample the pixel center so 1-2 px wide sprites hit
                    # the middle of the stencil instead of a blank edge.
                    mu = ((dx - left) * 2 + 1) * len(shape[0]) // (2 * spr_w)
                    mu = min(max(mu, 0), len(shape[0]) - 1)
                for dy in range(ds_y, de_y + 1):
                    if shape:
                        mv = ((dy - top) * 2 + 1) * len(shape) // (2 * max(spr_h, 1))
                        mv = min(max(mv, 0), len(shape) - 1)
                        cell = shape[mv][mu]
                        if cell == '.':
                            continue
                        self.fb[dy][dx] = C_EYE if cell == 'E' else sc
                    else:
                        self.fb[dy][dx] = sc

    def _render_weapon(self):
        # Side-to-side sway while moving.
        sway = int(round(math.sin(self.player.bob_phase) * 2))
        bob = int(abs(math.cos(self.player.bob_phase)) * 1.2)
        cx = SCREEN_W // 2 + sway
        bottom = SCREEN_H - 2 + bob

        # Muzzle flash: bright white burst at the barrel tip so shots
        # are unmistakable.
        if self.player.muzzle_timer > 0:
            tip_y = bottom - 8
            flash = [
                (0, -2, C_FLASH), (0, -1, C_WHITE),
                (-1, 0, C_WHITE), (0, 0, C_WHITE), (1, 0, C_WHITE), (2, 0, C_WHITE),
                (-2, 0, C_FLASH), (3, 0, C_FLASH),
                (0, 1, C_WHITE), (1, 1, C_WHITE),
                (-1, -1, C_FLASH), (2, -1, C_FLASH),
                (0, 2, C_FLASH), (1, -2, C_FLASH),
            ]
            for fx, fy, c in flash:
                nx, ny = cx + fx, tip_y + fy
                if 0 <= nx < SCREEN_W and 0 <= ny < SCREEN_H:
                    self.fb[ny][nx] = c

        for dy in range(5):
            y = bottom - dy
            w = 3 if dy < 3 else 1
            for dx in range(-w, w + 1):
                nx = cx + dx
                if 0 <= nx < SCREEN_W and 0 <= y < SCREEN_H:
                    c = C_GUN if abs(dx) < w else C_GUN_DARK
                    self.fb[y][nx] = c

        for dy in range(3):
            y = bottom - 5 - dy
            for dx in [0, 1]:
                nx = cx + dx
                if 0 <= nx < SCREEN_W and 0 <= y < SCREEN_H:
                    self.fb[y][nx] = C_GUN_DARK

    def _render_hud(self):
        y = SCREEN_H - 1

        hp_px = max(0, int(self.player.health / 100 * 20))
        for x in range(20):
            self.fb[y][x] = C_HUD_HP if x < hp_px else C_HUD_HP_BG

        ammo_px = min(20, max(0, int(self.player.ammo / 50 * 20)))
        for x in range(20):
            self.fb[y][SCREEN_W - 20 + x] = C_HUD_AM if x < ammo_px else C_HUD_AM_BG

        for x in range(20, SCREEN_W - 20):
            self.fb[y][x] = C_BLACK

        # Carrying the key: small yellow marker top-right.
        if self.player.has_key:
            self.fb[0][SCREEN_W - 1] = C_ITEM_KEY
            self.fb[0][SCREEN_W - 2] = C_ITEM_KEY
            self.fb[1][SCREEN_W - 1] = C_ITEM_KEY

    # -------------------------------------------------------------------
    # PLC output
    # -------------------------------------------------------------------
    def get_matrix_flat(self):
        """Return list of 2048 UDINTs matching PLC mMatrix memory layout.

        mMatrix[row][col] where row 0 = panel bottom, row 31 = panel top.
        Screen y=0 is top of the rendered view, so we flip Y.
        """
        flat = [0] * (SCREEN_H * SCREEN_W)
        for sy in range(SCREEN_H):
            row = SCREEN_H - 1 - sy
            for col in range(SCREEN_W):
                flat[row * SCREEN_W + col] = self.fb[sy][col]
        return flat
