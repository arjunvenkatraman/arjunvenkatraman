#!/usr/bin/env python3
"""
Generate a Game of Life SVG animation from GitHub contributions.

- Contribution cells seed the initial live population
- A glider is planted to ensure motion even on sparse grids
- Standard B3/S23 rules, toroidal wrapping
- Generates light + dark SVGs with discrete SMIL keyframe animation
"""

import os, sys, json, math, random, urllib.request

# total grid the GoL runs on — bigger than the contribution footprint
COLS, ROWS = 72, 18

# contribution data occupies a centred 52×7 window inside the grid
CONTRIB_COLS, CONTRIB_ROWS = 52, 7
CONTRIB_COL0 = (COLS - CONTRIB_COLS) // 2   # = 10
CONTRIB_ROW0 = (ROWS - CONTRIB_ROWS) // 2   # = 5

CELL, GAP = 9, 2
STEP = CELL + GAP
PAD = 8
SVG_W = PAD * 2 + COLS * STEP - GAP
SVG_H = PAD * 2 + ROWS * STEP - GAP

MAX_FRAMES   = 400
INTERVAL_MS  = 160   # ms per generation


# ── colours ─────────────────────────────────────────────────────────────────

# dark theme
EMPTY_D  = '#161b22'
HEAT_D   = ['#1f1a00', '#2a2200', '#342b00', '#3e3300']   # idx 0..3 = heat 1..4
ALIVE_D  = ['#665200', '#8a6e00', '#b38f00', '#d4a900', '#f5c400', '#ffe566']

# light theme
EMPTY_L  = '#ebedf0'
HEAT_L   = ['#fffde0', '#fff9b0', '#fff480', '#ffee44']
ALIVE_L  = ['#b38f00', '#c9a200', '#d4a900', '#e6be00', '#f5c400', '#ffe566']

BG_D, BG_L = '#0d1117', '#ffffff'


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
    grid = [[0] * CONTRIB_ROWS for _ in range(CONTRIB_COLS)]
    for ci, week in enumerate(cal['weeks'][:CONTRIB_COLS]):
        for ri, day in enumerate(week['contributionDays'][:CONTRIB_ROWS]):
            grid[ci][ri] = day['contributionCount']
    return cal['totalContributions'], grid


# ── Game of Life simulation ──────────────────────────────────────────────────────

def _idx(c, r): return r * COLS + c

def plant_glider(grid, age, col, row):
    """Standard glider:  .O. / ..O / OOO  — moves SE on toroidal grid."""
    for dr, dc in [(0,1),(1,2),(2,0),(2,1),(2,2)]:
        i = _idx((col+dc)%COLS, (row+dr)%ROWS)
        grid[i] = 1
        age[i]  = 1

def simulate(contrib_grid):
    random.seed(42)

    N    = COLS * ROWS
    grid = [0] * N
    age  = [0] * N   # consecutive gens alive (capped at 5)
    heat = [0] * N   # contribution intensity 1–4 (static, never changes)

    # seed from contributions into the centred window
    for cc in range(CONTRIB_COLS):
        for cr in range(CONTRIB_ROWS):
            v = contrib_grid[cc][cr]
            if v > 0:
                i = _idx(CONTRIB_COL0 + cc, CONTRIB_ROW0 + cr)
                grid[i] = 1
                age[i]  = 1
                heat[i] = min(4, max(1, math.ceil(v / 3)))

    # plant gliders in the empty border — one top-left, one bottom-right
    plant_glider(grid, age, 1, 1)
    plant_glider(grid, age, COLS - 6, ROWS - 5)

    frames   = []   # list of (grid_snapshot, age_snapshot)
    cooldown = 0

    for _ in range(MAX_FRAMES):
        frames.append((list(grid), list(age)))

        # GoL step (toroidal B3/S23)
        nxt     = [0] * N
        nxt_age = [0] * N
        for r in range(ROWS):
            for c in range(COLS):
                n = sum(
                    grid[_idx((c+dc)%COLS, (r+dr)%ROWS)]
                    for dr in (-1,0,1) for dc in (-1,0,1)
                    if dr or dc
                )
                alive = grid[_idx(c, r)]
                if alive:
                    nxt[_idx(c,r)]     = 1 if n in (2,3) else 0
                    nxt_age[_idx(c,r)] = min(age[_idx(c,r)]+1, 5) if n in (2,3) else 0
                else:
                    nxt[_idx(c,r)]     = 1 if n == 3 else 0
                    nxt_age[_idx(c,r)] = 1 if n == 3 else 0
        grid, nxt     = nxt, grid
        age,  nxt_age = nxt_age, age

        # re-seed if population collapses
        cooldown = max(0, cooldown - 1)
        if sum(grid) < 6 and cooldown == 0:
            col = random.randint(0, COLS - 5)
            row = random.randint(0, ROWS - 4)
            plant_glider(grid, age, col, row)
            cooldown = 25

    return frames, heat


# ── SVG generation ───────────────────────────────────────────────────────────

def _color(alive, a, h, dark):
    if alive:
        return (ALIVE_D if dark else ALIVE_L)[min(a, 5)]
    if h:
        return (HEAT_D if dark else HEAT_L)[min(h, 4) - 1]
    return EMPTY_D if dark else EMPTY_L


def generate_svg(frames, heat, dark=False):
    bg    = BG_D if dark else BG_L
    empty = EMPTY_D if dark else EMPTY_L
    n     = len(frames)
    dur   = f'{n * INTERVAL_MS / 1000:.2f}s'

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{SVG_W}" height="{SVG_H}" viewBox="0 0 {SVG_W} {SVG_H}">',
        f'<rect width="{SVG_W}" height="{SVG_H}" fill="{bg}"/>',
    ]

    for r in range(ROWS):
        for c in range(COLS):
            x   = PAD + c * STEP
            y   = PAD + r * STEP
            idx = _idx(c, r)
            h   = heat[idx]

            colors = [
                _color(frames[fi][0][idx], frames[fi][1][idx], h, dark)
                for fi in range(n)
            ]

            # compress to transition points only
            transitions = []
            prev = None
            for fi, col_val in enumerate(colors):
                if col_val != prev:
                    transitions.append((fi, col_val))
                    prev = col_val

            first = transitions[0][1] if transitions else empty

            if len(transitions) <= 1:
                parts.append(
                    f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" '
                    f'rx="2" fill="{first}"/>'
                )
            else:
                kts, vals = [], []
                for fi, cv in transitions:
                    kts.append(f'{fi/(n-1):.4f}')
                    vals.append(cv)
                if kts[-1] != '1.0000':
                    kts.append('1.0000')
                    vals.append(vals[-1])

                parts.append(
                    f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="2" '
                    f'fill="{first}">'
                    f'<animate attributeName="fill" dur="{dur}" repeatCount="indefinite" '
                    f'calcMode="discrete" keyTimes="{";".join(kts)}" values="{";".join(vals)}"/>'
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
    total, contrib = fetch_contributions(username, token)
    print(f'Total contributions: {total}')

    print('Simulating Game of Life...')
    frames, heat = simulate(contrib)
    print(f'Simulated {len(frames)} generations')

    os.makedirs(out_dir, exist_ok=True)

    for dark in (False, True):
        svg  = generate_svg(frames, heat, dark=dark)
        name = 'github-gol-dark.svg' if dark else 'github-gol.svg'
        path = os.path.join(out_dir, name)
        with open(path, 'w') as f:
            f.write(svg)
        print(f'Wrote {path}  ({len(svg)/1024:.1f} KB)')


if __name__ == '__main__':
    main()
