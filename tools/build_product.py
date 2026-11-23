#!/usr/bin/env python3
"""Builds a product's help centre page from the app's help articles and the
screenshots made by the app's help_shots test.

  python3 tools/build_product.py products/<slug> --app <app folder> \
      --phone <folder of phone shots> --ipad <folder of iPad shots>

Reads products/<slug>/product.json, writes products/<slug>/help.html (English)
and help-<lang>.html for every language the app has, and copies the
screenshots into products/<slug>/img/{phone,ipad}/*.webp.
Every {label:key} in an article is replaced by the on-screen text from the
app's app_<lang>.arb, and each label that appears on the article's
screenshot (found through its English text, the pictures are English) gets
a numbered marker on the picture. The articles are grouped by the app's own
help areas (lib/domain/help.dart). Interface texts: tools/help_ui.json.
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
labels_en = json.loads((APP / 'lib/l10n/app_en.arb').read_text())
labels = labels_en
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
UI = json.loads(pathlib.Path(__file__).with_name('help_ui.json').read_text())
LANGS = list(UI)  # en first
helpsrc = (APP / 'lib/domain/help.dart').read_text()
AREAS = re.findall(r"^\s+'([a-z]+)',\s*$", helpsrc.split('const helpAreas = [')[1].split('];')[0], re.M)
TOPICS = re.findall(r"HelpTopic\('(\w+)', '(\w+)'\)", helpsrc)
AREA_KEY = {a: 'helpArea' + a.capitalize() for a in AREAS}

REPORT_KEYS = {'salesperf': 'repSalesPerf', 'paymentsperf': 'repPaymentsPerf', 'touches': 'repTouches',
               'targetpace': 'repTargetPace', 'forecast': 'repForecast', 'recovery': 'repRecovery',
               'dealflow': 'repDealFlow', 'whatworks': 'repWhatWorks', 'activity': 'repActivity',
               'results': 'repResults', 'campaigns': 'repCampaigns', 'besttime': 'repBestTime',
               'weekday': 'repWeekday', 'pipeline': 'repPipeline', 'wonlost': 'repWonLost',
               'attempts': 'repAttempts', 'nevercalled': 'repNeverCalled', 'aging': 'repAging',
               'promises': 'repPromises', 'payments': 'repPayments', 'followups': 'repFollowUps',
               'statement': 'repStatement'}

LANG = 'en'
titles, docs = {}, {}

def label(m):
    v = labels.get(m.group(1))
    return v if isinstance(v, str) else m.group(1)

def report_name(rid):
    name = labels.get(REPORT_KEYS.get(rid, ''), rid)
    return name + (' report' if LANG == 'en' else '')

def inline(t):
    t = html.escape(t, quote=False)
    t = re.sub(r'\{label:(\w+)\}', label, t)
    t = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', t)
    t = re.sub(r'\[\[help:(\w+)\]\]', lambda m: f'<a href="#{m.group(1)}">{titles.get(m.group(1), m.group(1))}</a>', t)
    t = re.sub(r'\[\[report:(\w+)\]\]', lambda m: f'<em>{report_name(m.group(1))}</em>', t)
    return re.sub(r'\s*\[\[open:\w+\]\]', '', t)

def md_to_html(text):
    out, para, i = [], [], 0
    lines = [re.sub(r'\s*\[\[open:\w+\]\]', '', l.rstrip()) for l in text.splitlines()]
    lines = [l for l in lines if not re.fullmatch(r'\s*(\[\[report:\w+\]\]\s*)+', l)]
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
    """The labels an article names, in order, without repeats: (key, this language's text)."""
    seen, out = set(), []
    for m in re.finditer(r'\{label:(\w+)\}', text):
        k = m.group(1)
        v = labels.get(k)
        if isinstance(v, str) and k not in seen and isinstance(labels_en.get(k), str):
            seen.add(k); out.append((k, v))
    return out

def norm(s): return re.sub(r'\s+', ' ', s).strip().casefold()

def find_box(text, m):
    """The smallest box on the screen whose label is this (English) text."""
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
    t = re.sub(r'\[\[report:(\w+)\]\]', lambda m: report_name(m.group(1)), t)
    t = re.sub(r'\s*\[\[open:\w+\]\]', '', t)
    return re.sub(r'\s+', ' ', t).strip()

def context(stem, key, text):
    """The sentence of the article where this label is named."""
    for line in docs[stem].splitlines()[1:]:
        if f'{{label:{key}}}' in line:
            t = plain(line)
            parts = re.split(r'(?<=[.!?。！？])\s+', t)
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
    for k, text in article_labels(docs[stem]):
        b = find_box(labels_en[k], m)
        if not b or len(legend) >= 6: continue
        n = len(legend) + 1
        pad = 3
        x0, y0 = max(b['x'] - pad, 0), max(b['y'] - pad, 0)
        x1, y1 = min(b['x'] + b['w'] + pad, W), min(b['y'] + b['h'] + pad, H)
        marks.append(f'<span class="mark-box" style="left:{x0/W*100:.1f}%;top:{y0/H*100:.1f}%;'
                     f'width:{(x1-x0)/W*100:.1f}%;height:{(y1-y0)/H*100:.1f}%" title="{html.escape(text)}">'
                     f'<span class="mark">{n}</span></span>')
        ctx = context(stem, k, text)
        legend.append(f'<li><span class="mark-n">{n}</span><span><b>{html.escape(text)}</b>'
                      + (f'<br><small>{html.escape(ctx)}</small>' if ctx and ctx != text else '') + '</span></li>')
    cap = cfg.get('screen_captions', {}).get(key, '') if LANG == 'en' else ''
    frame = 'tablet' if kind == 'ipad' else 'phone phone-sm'
    img = f'img/{kind}/{name}.webp'
    fig = (f'<figure class="shot kind-{kind}" dir="ltr"><div class="{frame}"><div class="shot-img">'
           f'<img src="{img}" alt="{html.escape(cap or titles.get(stem, name))}" loading="lazy">{"".join(marks)}</div></div>'
           + (f'<figcaption>{html.escape(cap)}</figcaption>' if cap else '')
           + (f'<ol class="legend" dir="auto">{"".join(legend)}</ol>' if legend else '')
           + '</figure>')
    return fig, legend

def load_lang(lang):
    global LANG, labels, titles, docs
    LANG = lang
    f = APP / f'lib/l10n/app_{lang}.arb'
    labels = {**labels_en, **json.loads(f.read_text())} if lang != 'en' and f.exists() else labels_en
    titles, docs = {}, {}
    for p in sorted((APP / 'assets/help/en').glob('*.md')):
        lp = APP / 'assets/help' / lang / p.name
        t = (lp if lp.exists() else p).read_text()
        titles[p.stem] = re.sub(r'\{label:(\w+)\}', label, t.splitlines()[0].lstrip('# ').strip())
        docs[p.stem] = t

def page_name(lang): return 'help.html' if lang == 'en' else f'help-{lang}.html'

def build(lang):
    load_lang(lang)
    ui = UI[lang]
    toc, body = [], []
    for area in AREAS:
        keys = [k for k, a in TOPICS if a == area and k in docs]
        if not keys: continue
        aname = labels.get(AREA_KEY[area], area)
        toc.append(f'<div class="toc-group"><div class="toc-title">{html.escape(aname)}</div><ul>' +
                   ''.join(f'<li><a href="#{k}">{html.escape(titles[k])}</a></li>' for k in keys) + '</ul></div>')
        body.append(f'<section class="group" id="g-{area}"><h2 class="serif">{html.escape(aname)}</h2>')
        for k in keys:
            fig, legend = figure(k)
            body.append(f'<article id="{k}" class="article card static{" has-shot" if fig else ""}">'
                        f'<div class="art-text"><h3>{html.escape(titles[k])}</h3>{md_to_html(docs[k])}</div>{fig}</article>')
        body.append('</section>')
    options = ''.join(f'<option value="{page_name(l)}" data-lang="{l}"{" selected" if l == lang else ""}>{html.escape(UI[l]["name"])}</option>' for l in LANGS)
    alternates = ''.join(f'<link rel="alternate" hreflang="{l}" href="{page_name(l)}">' for l in LANGS)
    note = f'<p class="shots-note">{html.escape(ui["shots_note"])}</p>' if ui.get('shots_note') else ''
    rep = {
        'TOC': '\n'.join(toc), 'BODY': '\n'.join(body), 'NAME': cfg['name'], 'EMAIL': cfg['support_email'],
        'LANG': lang, 'DIR': ui.get('dir', 'ltr'), 'LANG_OPTIONS': options, 'ALTERNATES': alternates,
        'T_HELP': ui['help'], 'T_H1A': ui['h1a'], 'T_H1B': ui['h1b'], 'T_INTRO': ui['intro'],
        'T_SEARCH': ui['search'], 'T_STILL': ui['still'], 'T_STILL_TEXT': ui['still_text'],
        'T_EMAIL': ui['email'], 'T_PRIVACY': ui['privacy'], 'T_LANGUAGE': ui['language'],
        'T_PRODUCT_OF': ui['product_of'].replace('{name}', cfg['name']), 'SHOTS_NOTE': note,
        'T_MATCH_JSON': json.dumps(ui['match'], ensure_ascii=False),
        'PAGES_JSON': json.dumps({l: page_name(l) for l in LANGS}),
    }
    out = TEMPLATE
    for k, v in rep.items():
        out = out.replace('{{' + k + '}}', v)
    (P / page_name(lang)).write_text(out)
    return len(docs)

for lang in LANGS:
    n = build(lang)
print(f"{n} articles x {len(LANGS)} languages, {len(meta)} screens -> {P}/help*.html")
