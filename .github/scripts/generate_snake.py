#!/usr/bin/env python3
"""
Generate a snake game SVG animation from GitHub contributions.

- More contributions  => faster snake speed + more growth per food eaten
- Snake self-collides, flashes red, then resets
- Animation loops indefinitely
"""

import os, sys, json, math, random, urllib.request
from collections import deque

COLS, ROWS = 52, 7
CELL, GAP = 11, 2
STEP = CELL + GAP
PAD = 5
SVG_W = COLS * STEP - GAP + 2 * PAD
SVG_H = ROWS * STEP - GAP + 2 * PAD

MAX_FRAMES = 500   # caps total animation length


# ── colours ─────────────────────────────────────────────────────────────────

SNAKE_BODY   = ['#39d353', '#26a641', '#006d32', '#0e4429']
HEAD_ALIVE   = '#56d364'
HEAD_DEAD    = '#f85149'

SNAKE_BODY_L  = ['#216e39', '#1a5c2d', '#145221', '#0e4429']
HEAD_ALIVE_L  = '#2ea043'
HEAD_DEAD_L   = '#cf222e'

FOOD_LEVELS  = ['#0e4429', '#006d32', '#26a641', '#39d353']
FOOD_LEVELS_L = ['#9be9a8', '#40c463', '#30a14e', '#216e39']

BG_DARK, EMPTY_DARK = '#0d1117', '#161b22'
BG_LIGHT, EMPTY_LIGHT = '#ffffff', '#ebedf0'


# ── GitHub data ──────────────────────────────────────────────────────────────

def fetch_contributions(username: str, token: str):
    query = (
        'query($u:String!){user(login:$u){contributionsCollection{'
        'contributionCalendar{totalContributions weeks{contributionDays{'
        'contributionCount}}}}}}'  
    )
    payload = json.dumps({'query': query, 'variables': {'u': username}}).encode()
    req = urllib.request.Request(
        'https://api.github.com/graphql', data=payload,
        headers={'Authorization': f'bearer {token}',
                 'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read())
    cal = data['data']['user']['contributionsCollection']['contributionCalendar']
    grid = [[0] * ROWS for _ in range(COLS)]
    for ci, week in enumerate(cal['weeks'][:COLS]):
        for ri, day in enumerate(week['contributionDays'][:ROWS]):
            grid[ci][ri] = day['contributionCount']
    return cal['totalContributions'], grid


# ── snake simulation ─────────────────────────────────────────────────────────

def simulate(grid, total: int):
    """
    Returns (frames, interval_ms).

    Each frame is {'snake': [(col,row), ...], 'food': {(col,row): count}, 'dead': bool}.
    Head is frames[i]['snake'][0].

    Speed: 300 ms/step at 0 contributions -> 80 ms/step at >=500 contributions.
    Growth: max(1, total // 50) cells per food eaten.
    """
    random.seed(42)

    interval_ms = max(80, 300 - int(total * 220 / 500))
    growth_per_food = max(1, total // 50)

    all_frames: list = []

    for _game in range(12):
        sc = random.randint(1, 5)
        sr = random.randint(1, ROWS - 2)
        snake: deque = deque([(sc + 2 - i, sr) for i in range(3)])
        direction = (1, 0)
        pending = 0

        food: dict = {}
        for c in range(COLS):
            for r in range(ROWS):
                if grid[c][r] > 0:
                    food[(c, r)] = grid[c][r]
        if not food:
            for _ in range(40):
                food[(random.randint(0, COLS - 1), random.randint(0, ROWS - 1))] = 1
        for pos in list(snake):
            food.pop(pos, None)

        for _step in range(900):
            if len(all_frames) >= MAX_FRAMES:
                break

            head = snake[0]
            snake_list = list(snake)
            all_frames.append({
                'snake': snake_list,
                'food': dict(food),
                'dead': False,
            })

            new_dir = direction
            if food:
                target = min(food, key=lambda p: abs(p[0]-head[0]) + abs(p[1]-head[1]))
                dx = target[0] - head[0]
                dy = target[1] - head[1]
                preferred: list = []
                if dx != 0:
                    preferred.append((1 if dx > 0 else -1, 0))
                if dy != 0:
                    preferred.append((0, 1 if dy > 0 else -1))
                for d in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
                    if d not in preferred:
                        preferred.append(d)

                opp = (-direction[0], -direction[1])
                snake_set = set(snake)
                for d in preferred:
                    if d == opp:
                        continue
                    nh = (head[0] + d[0], head[1] + d[1])
                    if 0 <= nh[0] < COLS and 0 <= nh[1] < ROWS and nh not in snake_set:
                        new_dir = d
                        break
            direction = new_dir

            new_head = (head[0] + direction[0], head[1] + direction[1])
            snake_set = set(snake)

            if (new_head[0] < 0 or new_head[0] >= COLS or
                    new_head[1] < 0 or new_head[1] >= ROWS or
                    new_head in snake_set):
                for _ in range(max(2, 12 - interval_ms // 25)):
                    all_frames.append({
                        'snake': snake_list,
                        'food': dict(food),
                        'dead': True,
                    })
                break

            snake.appendleft(new_head)
            if pending > 0:
                pending -= 1
            else:
                snake.pop()

            if new_head in food:
                food.pop(new_head)
                pending += growth_per_food

        if len(all_frames) >= MAX_FRAMES:
            break

    return all_frames, interval_ms


# ── SVG generation ───────────────────────────────────────────────────────────

def _cell_color(pos, snake_index: dict, food: dict, is_dead: bool, dark: bool):
    body   = SNAKE_BODY   if dark else SNAKE_BODY_L
    h_live = HEAD_ALIVE   if dark else HEAD_ALIVE_L
    h_dead = HEAD_DEAD    if dark else HEAD_DEAD_L
    foods  = FOOD_LEVELS  if dark else FOOD_LEVELS_L
    empty  = EMPTY_DARK   if dark else EMPTY_LIGHT

    if pos in snake_index:
        idx = snake_index[pos]
        if idx == 0:
            return h_dead if is_dead else h_live
        frac = idx / max(snake_index['__len__'] - 1, 1)
        return body[min(3, int(frac * 4))]
    if pos in food:
        level = min(3, max(0, math.ceil(food[pos] / 3) - 1))
        return foods[level]
    return empty


def generate_svg(frames: list, interval_ms: int, dark: bool = False) -> str:
    bg    = BG_DARK    if dark else BG_LIGHT
    empty = EMPTY_DARK if dark else EMPTY_LIGHT

    n = len(frames)
    if n == 0:
        return (f'<svg xmlns="http://www.w3.org/2000/svg" '
                f'width="{SVG_W}" height="{SVG_H}">'
                f'<rect width="100%" height="100%" fill="{bg}"/></svg>')

    dur = f'{n * interval_ms / 1000:.2f}s'

    frame_maps: list = []
    for f in frames:
        m: dict = {}
        for idx, pos in enumerate(f['snake']):
            m[pos] = idx
        m['__len__'] = len(f['snake'])
        frame_maps.append(m)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{SVG_W}" height="{SVG_H}" viewBox="0 0 {SVG_W} {SVG_H}">',
        f'<rect width="{SVG_W}" height="{SVG_H}" fill="{bg}"/>',
    ]

    for col in range(COLS):
        for row in range(ROWS):
            x = PAD + col * STEP
            y = PAD + row * STEP
            pos = (col, row)

            colors = [
                _cell_color(pos, frame_maps[i], frames[i]['food'],
                            frames[i]['dead'], dark)
                for i in range(n)
            ]

            transitions: list = []
            prev = None
            for i, c in enumerate(colors):
                if c != prev:
                    transitions.append((i, c))
                    prev = c

            first_color = transitions[0][1] if transitions else empty

            if len(transitions) <= 1:
                parts.append(
                    f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" '
                    f'rx="2" fill="{first_color}"/>'
                )
            else:
                key_times: list = []
                values: list = []
                for fi, color in transitions:
                    t = fi / (n - 1) if n > 1 else 0.0
                    key_times.append(f'{t:.4f}')
                    values.append(color)
                if key_times[-1] != '1.0000':
                    key_times.append('1.0000')
                    values.append(values[-1])

                kt = ';'.join(key_times)
                v  = ';'.join(values)
                parts.append(
                    f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="2" '
                    f'fill="{first_color}">'
                    f'<animate attributeName="fill" dur="{dur}" repeatCount="indefinite" '
                    f'calcMode="discrete" keyTimes="{kt}" values="{v}"/>'
                    f'</rect>'
                )

    parts.append('</svg>')
    return '\n'.join(parts)


# ── entry point ──────────────────────────────────────────────────────────────

def main():
    username = os.environ.get('GITHUB_USER') or (sys.argv[1] if len(sys.argv) > 1 else 'arjunvenkatraman')
    token    = os.environ.get('GITHUB_TOKEN', '')
    out_dir  = sys.argv[2] if len(sys.argv) > 2 else 'dist'

    print(f'Fetching contributions for {username}...')
    total, grid = fetch_contributions(username, token)
    print(f'Total contributions: {total}')
    print(f'Speed: {max(80, 300 - int(total * 220 / 500))} ms/step  |  '
          f'Growth: {max(1, total // 50)} cells/food')

    frames, interval_ms = simulate(grid, total)
    print(f'Simulated {len(frames)} frames')

    os.makedirs(out_dir, exist_ok=True)

    for dark in (False, True):
        svg  = generate_svg(frames, interval_ms, dark=dark)
        name = 'github-snake-dark.svg' if dark else 'github-snake.svg'
        path = os.path.join(out_dir, name)
        with open(path, 'w') as fh:
            fh.write(svg)
        print(f'Wrote {path}  ({len(svg)/1024:.1f} KB)')


if __name__ == '__main__':
    main()
