"""
LED Doom — A Doom-like raycaster for 32x64 LED panels.

Renders to a 32x64 UDINT pixel buffer suitable for Beckhoff EL2574
LED terminals. Color format: UDINT = (B << 16) | (G << 8) | R.
"""

import math

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
}

C_ENEMY_IMP   = rgb(195, 40, 25)
C_ENEMY_DEMON = rgb(155, 25, 75)
C_EYE         = rgb(255, 210, 0)

# Enemy sprite stencils — 'X' = body pixel, 'E' = eye pixel, '.' = transparent.
# Stretched to the sprite's on-screen rectangle with nearest-neighbor sampling,
# so the silhouette holds up close and far away.
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
C_ITEM_HEALTH = rgb(25, 210, 25)
C_ITEM_AMMO   = rgb(210, 210, 25)
C_GUN         = rgb(115, 115, 120)
C_GUN_DARK    = rgb(65, 65, 70)
C_HUD_HP      = rgb(0, 195, 0)
C_HUD_HP_BG   = rgb(55, 0, 0)
C_HUD_AM      = rgb(195, 195, 0)
C_HUD_AM_BG   = rgb(35, 35, 0)
C_GAME_OVER   = rgb(145, 0, 0)

# ---------------------------------------------------------------------------
# Level data
# ---------------------------------------------------------------------------
LEVEL_1 = [
    [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],
    [1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1],
    [1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1],
    [1,0,0,1,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1,1,0,0,1],
    [1,0,0,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1,0,0,1],
    [1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1],
    [1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1],
    [1,0,0,0,0,0,3,3,0,0,0,0,0,0,0,0,3,3,0,0,0,0,0,1],
    [1,1,1,0,0,0,3,0,0,0,0,0,0,0,0,0,0,3,0,0,0,1,1,1],
    [2,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,2],
    [2,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,2],
    [2,0,0,0,0,0,0,0,0,4,4,4,4,4,0,0,0,0,0,0,0,0,0,2],
    [2,0,0,0,0,0,0,0,0,4,0,0,0,4,0,0,0,0,0,0,0,0,0,2],
    [2,0,0,0,0,0,0,0,0,4,0,0,0,4,0,0,0,0,0,0,0,0,0,2],
    [2,0,0,0,0,0,0,0,0,4,4,0,4,4,0,0,0,0,0,0,0,0,0,2],
    [2,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,2],
    [2,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,2],
    [1,1,1,0,0,0,3,0,0,0,0,0,0,0,0,0,0,3,0,0,0,1,1,1],
    [1,0,0,0,0,0,3,3,0,0,0,0,0,0,0,0,3,3,0,0,0,0,0,1],
    [1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1],
    [1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1],
    [1,0,0,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1,0,0,1],
    [1,0,0,1,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1,1,0,0,1],
    [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],
]

ENEMIES_1 = [
    (12, 5, 'imp'),
    (6, 10, 'imp'),
    (18, 10, 'imp'),
    (11.5, 12.5, 'demon'),
    (4, 16, 'imp'),
    (20, 16, 'imp'),
    (12, 21, 'demon'),
]

ITEMS_1 = [
    (4, 2, 'ammo'),
    (20, 2, 'health'),
    (12, 9, 'health'),
    (3, 15, 'health'),
    (21, 15, 'ammo'),
    (12, 19, 'ammo'),
]

PLAYER_START = (2.0, 2.0, 0.0)

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
        self.kills = 0
        self.dead = False


class Enemy:
    TYPES = {
        'imp':   {'hp': 100, 'color': C_ENEMY_IMP,   'speed': 1.5, 'damage': 8,
                  'shape': IMP_SHAPE},
        'demon': {'hp': 150, 'color': C_ENEMY_DEMON,  'speed': 2.2, 'damage': 14,
                  'shape': DEMON_SHAPE},
    }

    def __init__(self, x, y, kind='imp'):
        t = self.TYPES[kind]
        self.x = x
        self.y = y
        self.hp = t['hp']
        self.color = t['color']
        self.shape = t['shape']
        self.speed = t['speed']
        self.damage = t['damage']
        self.alive = True
        self.alert = False
        self.attack_cd = 0.0
        self.hurt_timer = 0.0


class Item:
    TYPES = {
        'health': {'color': C_ITEM_HEALTH, 'value': 25},
        'ammo':   {'color': C_ITEM_AMMO,   'value': 15},
    }

    def __init__(self, x, y, kind='health'):
        t = self.TYPES[kind]
        self.x = x
        self.y = y
        self.kind = kind
        self.color = t['color']
        self.value = t['value']
        self.picked_up = False


# ---------------------------------------------------------------------------
# Game
# ---------------------------------------------------------------------------
class DoomGame:
    def __init__(self):
        self.level = LEVEL_1
        self.map_w = len(self.level[0])
        self.map_h = len(self.level)

        sx, sy, sa = PLAYER_START
        self.player = Player(sx, sy, sa)
        self.enemies = [Enemy(x, y, k) for x, y, k in ENEMIES_1]
        self.items = [Item(x, y, k) for x, y, k in ITEMS_1]

        self.fb = [[C_BLACK] * SCREEN_W for _ in range(SCREEN_H)]
        self.zbuf = [0.0] * SCREEN_W

        self.game_over = False
        self.victory = False
        self.damage_flash = 0.0
        self.time = 0.0

    def restart(self):
        self.__init__()

    # -------------------------------------------------------------------
    # Update
    # -------------------------------------------------------------------
    def update(self, dt, controls):
        if self.game_over or self.victory:
            if controls.get('shoot') or controls.get('start'):
                self.restart()
            return

        self.time += dt
        p = self.player

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
        if controls.get('shoot') and p.shoot_timer <= 0 and p.ammo > 0:
            p.shoot_timer = 0.35
            p.ammo -= 1
            p.is_shooting = True
            self._fire_weapon()

        # Enemies
        for e in self.enemies:
            if not e.alive:
                continue
            e.hurt_timer = max(0, e.hurt_timer - dt)
            e.attack_cd = max(0, e.attack_cd - dt)
            dist = math.hypot(e.x - p.x, e.y - p.y)

            if dist < 10 or p.is_shooting:
                e.alert = True

            if e.alert and dist > 1.2:
                angle = math.atan2(p.y - e.y, p.x - e.x)
                enx = e.x + math.cos(angle) * e.speed * dt
                eny = e.y + math.sin(angle) * e.speed * dt
                if self._passable(enx, eny, 0.3):
                    e.x, e.y = enx, eny

            if e.alert and dist < 1.5 and e.attack_cd <= 0:
                p.health -= e.damage
                e.attack_cd = 1.0
                self.damage_flash = 0.15
                if p.health <= 0:
                    p.health = 0
                    p.dead = True
                    self.game_over = True

        # Pickups
        for item in self.items:
            if item.picked_up:
                continue
            if math.hypot(item.x - p.x, item.y - p.y) < 0.6:
                if item.kind == 'health' and p.health < 100:
                    p.health = min(100, p.health + item.value)
                    item.picked_up = True
                elif item.kind == 'ammo':
                    p.ammo += item.value
                    item.picked_up = True

        # Win
        if all(not e.alive for e in self.enemies):
            self.victory = True

        self.damage_flash = max(0, self.damage_flash - dt)
        p.is_shooting = False

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
            if abs(diff) < 0.12:
                d = math.hypot(e.x - p.x, e.y - p.y)
                if d < best_dist and d < 15 and not self._blocked(p.x, p.y, e.x, e.y):
                    best, best_dist = e, d
        if best:
            best.hp -= 35
            best.hurt_timer = 0.1
            if best.hp <= 0:
                best.alive = False
                self.player.kills += 1

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

    # -------------------------------------------------------------------
    # Render
    # -------------------------------------------------------------------
    def render(self):
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

        if self.game_over:
            for y in range(SCREEN_H):
                for x in range(SCREEN_W):
                    self.fb[y][x] = shade_color(self.fb[y][x], 0.3)
                    c = self.fb[y][x]
                    r = min(255, (c & 0xFF) + 70)
                    self.fb[y][x] = (c & 0xFFFF00) | r

        if self.victory:
            for y in range(SCREEN_H):
                for x in range(SCREEN_W):
                    c = self.fb[y][x]
                    g = min(255, ((c >> 8) & 0xFF) + 50)
                    self.fb[y][x] = (c & 0xFF00FF) | (g << 8)

        return self.fb

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

            for y in range(SCREEN_H):
                if y < ds:
                    self.fb[y][x] = C_CEIL
                elif y <= de:
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
                sprites.append((e.x, e.y, c, 1.0, e.shape))
        for item in self.items:
            if not item.picked_up:
                pulse = 0.6 + 0.4 * math.sin(self.time * 5)
                sprites.append((item.x, item.y, shade_color(item.color, pulse), 0.5, None))

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
        cx = SCREEN_W // 2
        bottom = SCREEN_H - 2

        if self.player.is_shooting:
            for dy in range(-3, 0):
                y = bottom - 5 + dy
                for dx in range(-2, 3):
                    nx = cx + dx
                    if 0 <= nx < SCREEN_W and 0 <= y < SCREEN_H:
                        self.fb[y][nx] = C_FLASH

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
