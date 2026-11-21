#!/usr/bin/env python3
"""Builds a product's help centre page from the app's help articles and the
screenshots made by the app's help_shots test.

  python3 tools/build_product.py products/<slug> --app <app folder> \
      --phone <folder of phone shots> --ipad <folder of iPad shots>

Reads products/<slug>/product.json, writes products/<slug>/help.html and
copies the screenshots into products/<slug>/img/{phone,ipad}/*.webp.
Every {label:key} in an article is replaced by the on-screen text from the
app's app_en.arb, and each label that appears on the article's screenshot
gets a numbered marker on the picture.
"""
import argparse, json, re, html, pathlib, sys

ap = argparse.ArgumentParser()
ap.add_argument('product')
ap.add_argument('--app', required=True)
ap.add_argument('--phone')
ap.add_argument('--ipad')
ap.add_argument('--phone-width', type=int, default=720)
ap.add_argument('--ipad-width', type=int, default=1600)
a = ap.parse_args()

P = pathlib.Path(a.product)
cfg = json.loads((P / 'product.json').read_text())
APP = pathlib.Path(a.app)
labels = json.loads((APP / 'lib/l10n/app_en.arb').read_text())
TEMPLATE = pathlib.Path(__file__).with_name('help_template.html').read_text()

# ---------- screenshots ----------
meta = {}  # 'home' or 'ipad:home' -> {'size':..., 'labels': [...]}
def copy_shots(src, kind, width):
    if not src: return
    from PIL import Image
    src = pathlib.Path(src)
    out = P / 'img' / kind
    out.mkdir(parents=True, exist_ok=True)
    for png in sorted(src.glob('*.png')):
        im = Image.open(png).convert('RGB')
        if im.width > width:
            im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
        im.save(out / (png.stem + '.webp'), 'WEBP', quality=84, method=6)
        j = png.with_suffix('.json')
        if j.exists():
            key = png.stem if kind == 'phone' else f'{kind}:{png.stem}'
            meta[key] = json.loads(j.read_text())
copy_shots(a.phone, 'phone', a.phone_width)
copy_shots(a.ipad, 'ipad', a.ipad_width)
if not meta:
    # No fresh shots: reuse what is already in img/ (markers need the json).
    for kind in ('phone', 'ipad'):
        d = P / 'img' / kind
        for j in d.glob('*.json') if d.exists() else []:
            key = j.stem if kind == 'phone' else f'{kind}:{j.stem}'
            meta[key] = json.loads(j.read_text())
# Keep the label boxes next to the pictures for the next build.
for key, m in meta.items():
    kind, _, name = key.rpartition(':')
    kind = kind or 'phone'
    (P / 'img' / kind / f'{name}.json').write_text(json.dumps(m))

# ---------- articles ----------
def label(m):
    v = labels.get(m.group(1))
    return v if isinstance(v, str) else m.group(1)

titles, docs = {}, {}
for p in sorted((APP / 'assets/help/en').glob('*.md')):
    t = p.read_text()
    titles[p.stem] = re.sub(r'\{label:(\w+)\}', label, t.splitlines()[0].lstrip('# ').strip())
    docs[p.stem] = t

REPORTS = {"salesperf": "Sales performance", "paymentsperf": "Payments performance", "touches": "Touches",
           "targetpace": "Target pace", "forecast": "Collections forecast", "recovery": "Recovery by age",
           "dealflow": "Deal flow", "whatworks": "What works"}

def inline(t):
    t = html.escape(t, quote=False)
    t = re.sub(r'\{label:(\w+)\}', label, t)
    t = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', t)
    t = re.sub(r'\[\[help:(\w+)\]\]', lambda m: f'<a href="#{m.group(1)}">{titles.get(m.group(1), m.group(1))}</a>', t)
    t = re.sub(r'\[\[report:(\w+)\]\]', lambda m: f'<em>{REPORTS.get(m.group(1), m.group(1))} report</em>', t)
    return re.sub(r'\s*\[\[open:\w+\]\]', '', t)

def md_to_html(text):
    out, para, i = [], [], 0
    lines = [re.sub(r'\s*\[\[open:\w+\]\]', '', l.rstrip()) for l in text.splitlines()]
    def flush():
        nonlocal para
        if para: out.append('<p>' + inline(' '.join(para)) + '</p>'); para = []
    while i < len(lines):
        l = lines[i]
        if not l.strip() or l.startswith('# '):
            flush(); i += 1; continue
        if re.match(r'^\d+\.\s+', l):
            flush(); items = []
            while i < len(lines) and re.match(r'^\d+\.\s+', lines[i]):
                items.append(re.sub(r'^\d+\.\s+', '', lines[i])); i += 1
            out.append('<ol>' + ''.join(f'<li>{inline(x)}</li>' for x in items) + '</ol>'); continue
        if l.startswith('- '):
            flush(); items = []
            while i < len(lines) and lines[i].startswith('- '):
                items.append(lines[i][2:]); i += 1
            out.append('<ul>' + ''.join(f'<li>{inline(x)}</li>' for x in items) + '</ul>'); continue
        para.append(l.strip()); i += 1
    flush()
    return '\n'.join(out)

def article_labels(text):
    """The on-screen labels an article names, in order, without repeats."""
    seen, out = set(), []
    for m in re.finditer(r'\{label:(\w+)\}', text):
        v = labels.get(m.group(1))
        if isinstance(v, str) and v not in seen:
            seen.add(v); out.append(v)
    return out

def norm(s): return re.sub(r'\s+', ' ', s).strip().casefold()

def find_box(text, m):
    """The smallest box on the screen whose label is this text."""
    t = norm(text)
    best = None
    for b in m['labels']:
        lb = norm(b['label'])
        area = b['w'] * b['h']
        exact = lb == t or lb.split(' · ')[0] == t
        # Loose: the box's label begins with the text as whole words, as a
        # row that also carries a subtitle does ("Sales Call prospects…").
        loose = (not exact) and b['h'] < 120 and lb.startswith(t) and \
            (len(lb) == len(t) or not lb[len(t)].isalnum())
        if not (exact or loose): continue
        if b['h'] > 260 or area > m['size']['w'] * m['size']['h'] * 0.35: continue
        if b['y'] < 44: continue  # the page title in the top bar
        score = (0 if exact else 1, 0 if b['tap'] else 1, area)
        if best is None or score < best[0]: best = (score, b)
    return best[1] if best else None

def plain(line):
    """A line of an article as plain text."""
    t = re.sub(r'^\s*(\d+\.|-|\*)\s+', '', line)
    t = re.sub(r'\{label:(\w+)\}', label, t)
    t = t.replace('**', '')
    t = re.sub(r'\[\[help:(\w+)\]\]', lambda m: titles.get(m.group(1), m.group(1)), t)
    t = re.sub(r'\[\[report:(\w+)\]\]', lambda m: REPORTS.get(m.group(1), m.group(1)) + ' report', t)
    t = re.sub(r'\s*\[\[open:\w+\]\]', '', t)
    return re.sub(r'\s+', ' ', t).strip()

def context(stem, text):
    """The sentence of the article where this label is named."""
    keys = {k for k, v in labels.items() if v == text}
    for line in docs[stem].splitlines()[1:]:
        if any(f'{{label:{k}}}' in line for k in keys):
            t = plain(line)
            # One sentence, if the line holds several.
            parts = re.split(r'(?<=[.!?])\s+', t)
            for part in parts:
                if text in part: t = part; break
            if len(t) > 120:
                t = t[:117].rsplit(' ', 1)[0] + '…'
            return t
    return ''

def figure(stem):
    key = cfg['article_screens'].get(stem)
    if not key:
        om = re.search(r'\[\[open:(\w+)\]\]', docs[stem])
        key = om.group(1) if om else None
    if not key or key not in meta: return '', []
    kind, _, name = key.rpartition(':'); kind = kind or 'phone'
    m = meta[key]
    W, H = m['size']['w'], m['size']['h']
    marks, legend = [], []
    for text in article_labels(docs[stem]):
        b = find_box(text, m)
        if not b or len(legend) >= 6: continue
        n = len(legend) + 1
        pad = 3
        x0, y0 = max(b['x'] - pad, 0), max(b['y'] - pad, 0)
        x1, y1 = min(b['x'] + b['w'] + pad, W), min(b['y'] + b['h'] + pad, H)
        marks.append(f'<span class="mark-box" style="left:{x0/W*100:.1f}%;top:{y0/H*100:.1f}%;'
                     f'width:{(x1-x0)/W*100:.1f}%;height:{(y1-y0)/H*100:.1f}%" title="{html.escape(text)}">'
                     f'<span class="mark">{n}</span></span>')
        ctx = context(stem, text)
        legend.append(f'<li><span class="mark-n">{n}</span><span><b>{html.escape(text)}</b>'
                      + (f'<br><small>{html.escape(ctx)}</small>' if ctx and ctx != text else '') + '</span></li>')
    cap = cfg.get('screen_captions', {}).get(key, '')
    frame = 'tablet' if kind == 'ipad' else 'phone phone-sm'
    img = f'img/{kind}/{name}.webp'
    fig = (f'<figure class="shot kind-{kind}"><div class="{frame}"><div class="shot-img">'
           f'<img src="{img}" alt="{html.escape(cap or name)}" loading="lazy">{"".join(marks)}</div></div>'
           + (f'<figcaption>{html.escape(cap)}</figcaption>' if cap else '')
           + (f'<ol class="legend">{"".join(legend)}</ol>' if legend else '')
           + '</figure>')
    return fig, legend

groups = cfg['help_groups']
seen = {k for _, ks in groups for k in ks}
missing = [k for k in docs if k not in seen]
if missing: groups.append(['More', missing])

toc, body = [], []
for gname, keys in groups:
    gid = re.sub(r'[^a-z]+', '-', gname.lower()).strip('-')
    keys = [k for k in keys if k in docs]
    toc.append(f'<div class="toc-group"><div class="toc-title">{gname}</div><ul>' +
               ''.join(f'<li><a href="#{k}">{html.escape(titles[k])}</a></li>' for k in keys) + '</ul></div>')
    body.append(f'<section class="group" id="g-{gid}"><h2 class="serif">{gname}</h2>')
    for k in keys:
        fig, legend = figure(k)
        body.append(f'<article id="{k}" class="article card static{" has-shot" if fig else ""}">'
                    f'<div class="art-text"><h3>{html.escape(titles[k])}</h3>{md_to_html(docs[k])}</div>{fig}</article>')
    body.append('</section>')

out = (TEMPLATE.replace('{{TOC}}', '\n'.join(toc)).replace('{{BODY}}', '\n'.join(body))
       .replace('{{NAME}}', cfg['name']).replace('{{EMAIL}}', cfg['support_email']))
(P / 'help.html').write_text(out)
print(f"{len(docs)} articles, {len(meta)} screens -> {P / 'help.html'}")
