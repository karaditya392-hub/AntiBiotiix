# -*- coding: utf-8 -*-
"""
Derive the console markup for the React port from the ORIGINAL index.html.

The console body is extracted verbatim and then has exactly the presentational
changes Manus made applied to it -- emoji to typographic glyph, the logo image,
and the brand name. Nothing else is touched.

Deriving it this way rather than retyping 600 lines of JSX means an element id,
a form field, or a data-preset attribute cannot be silently lost, which is what
would break app.js.
"""
import io
import re

REPO = r"C:/Users/iraba/OneDrive/Desktop/Microbe"
SRC = REPO + "/frontend-legacy/index.html"
OUT = REPO + "/frontend-src/src/legacy/console.html"

html = io.open(SRC, encoding="utf-8").read()

# --- extract the body, minus the <script> tag (React boots app.js itself) ----
start = html.find(">", html.find("<body")) + 1
end = html.find('<script src="/static/js/app.js')
body = html[start:end].rstrip()

# --- the exact presentational substitutions Manus applied ------------------
# (old, new) -- every one is a glyph/label swap; no id, class, or attribute
# that app.js depends on appears on either side.
SUBS = [
    ('<span class="logo-icon">\U0001f9ec</span>',
     '<span class="logo-icon"><img src="/static/brand/antibiotix-logo.jpg" alt="AntiBioTix pharmacology logo"></span>'),
    ('<span class="logo-title">S11 Microbe Assistant</span>',
     '<span class="logo-title">AntiBioTix</span>'),
    ('<span id="themeIcon">\u2600\ufe0f</span>',
     '<span id="themeIcon" aria-hidden="true">\u25d0</span>'),
    ('<span class="tab-icon">\U0001f4cb</span>', '<span class="tab-icon" aria-hidden="true">\u25a6</span>'),
    ('<span class="tab-icon">\U0001f4d6</span>', '<span class="tab-icon" aria-hidden="true">\u2263</span>'),
    ('<span class="tab-icon">\U0001f512</span>', '<span class="tab-icon" aria-hidden="true">\u2311</span>'),
    ('<span class="tab-icon">\U0001f9ea</span>', '<span class="tab-icon" aria-hidden="true">\u25c7</span>'),
    ('<h3><span class="icon">\U0001f464</span> Synthetic Patient Profile</h3>',
     '<h3><span class="icon" aria-hidden="true">\u25c9</span> Synthetic Patient Profile</h3>'),
    ('<h3><span class="icon">\u270d\ufe0f</span> Enter Prescription Order</h3>',
     '<h3><span class="icon" aria-hidden="true">\u2301</span> Enter Prescription Order</h3>'),
    ('<span class="btn-icon">\U0001f50d</span> Parse & Extract Entities',
     '<span class="btn-icon" aria-hidden="true">\u2315</span> Parse & Extract Entities'),
    ('<span class="btn-icon">\u26a1</span> Analyze Prescription Safety',
     '<span class="btn-icon" aria-hidden="true">\u25b6</span> Analyze Prescription Safety'),
    ('<h3><span class="icon">\U0001f6e1\ufe0f</span> Prescription Safety & Stewardship Results</h3>',
     '<h3><span class="icon" aria-hidden="true">\u25c7</span> Prescription Safety & Stewardship Results</h3>'),
    ('<h4><span class="icon">\U0001f4ac</span> Clinical Decision-Support Summary</h4>',
     '<h4><span class="icon" aria-hidden="true">\u2261</span> Clinical Decision-Support Summary</h4>'),
    ('<span class="empty-icon">\U0001f4dd</span>', '<span class="empty-icon" aria-hidden="true">\u25a1</span>'),
    ('<h4><span class="icon">\U0001f4da</span> ICMR National Treatment Guideline Reference</h4>',
     '<h4><span class="icon" aria-hidden="true">\u2263</span> ICMR National Treatment Guideline Reference</h4>'),
    ('<h4><span class="icon">\U0001f4ca</span> Local Antimicrobial Resistance Context (ICMR Surveillance)</h4>',
     '<h4><span class="icon" aria-hidden="true">\u25a5</span> Local Antimicrobial Resistance Context (ICMR Surveillance)</h4>'),
    ('<h3><span class="icon">\u2696\ufe0f</span> Guideline Precedence Hierarchy (Section 8A)</h3>',
     '<h3><span class="icon" aria-hidden="true">\u229c</span> Guideline Precedence Hierarchy (Section 8A)</h3>'),
    ('<h3><span class="icon">\U0001f4c9</span> Alert Fatigue & Override-Rate Monitoring (Section 16A)</h3>',
     '<h3><span class="icon" aria-hidden="true">\u2301</span> Alert Fatigue & Override-Rate Monitoring (Section 16A)</h3>'),
    ('<h3><span class="icon">\u26a0\ufe0f</span> Clinician Override Confirmation</h3>',
     '<h3><span class="icon" aria-hidden="true">!</span> Clinician Override Confirmation</h3>'),
]


# --- section 18: no emoji anywhere in the UI --------------------------------
# Manus left these three; they are replaced with the same typographic glyphs the
# rest of its redesign uses. Purely the contents of a decorative <span>.
SUBS += [
    ('<h3><span class="icon">🔒</span> Cryptographically Chained Audit Trail (SHA-256)</h3>',
     '<h3><span class="icon" aria-hidden="true">⌑</span> Cryptographically Chained Audit Trail (SHA-256)</h3>'),
    ('<h3><span class="icon">🧪</span> Automated Clinical Safety & Adversarial Test Suite</h3>',
     '<h3><span class="icon" aria-hidden="true">◇</span> Automated Clinical Safety & Adversarial Test Suite</h3>'),
    ('<h3><span class="icon">📖</span> Clinical Evidence & Guideline Provenance</h3>',
     '<h3><span class="icon" aria-hidden="true">≣</span> Clinical Evidence & Guideline Provenance</h3>'),
]


# Emoji written as numeric HTML entities. Same section 18 rule; these render as
# emoji in the browser even though they are ASCII in the source, so a plain
# character scan of the file misses them.
SUBS += [
    ('<span class="tab-icon">&#128269;</span>', '<span class="tab-icon" aria-hidden="true">⌕</span>'),
    ('<h3><span class="icon">&#128269;</span> Ask the Evidence</h3>',
     '<h3><span class="icon" aria-hidden="true">⌕</span> Ask the Evidence</h3>'),
    ('<h3><span class="icon">&#128203;</span> Register New Patient</h3>',
     '<h3><span class="icon" aria-hidden="true">◉</span> Register New Patient</h3>'),
    ('<h3><span class="icon">&#128138;</span> Current Medications</h3>',
     '<h3><span class="icon" aria-hidden="true">◈</span> Current Medications</h3>'),
    ('<h3><span class="icon">&#9888;</span> Report an Allergy</h3>',
     '<h3><span class="icon" aria-hidden="true">!</span> Report an Allergy</h3>'),
    ('<strong style="display:block; margin-bottom:0.25rem;">&#9888; Adversarial input detected and neutralised</strong>',
     '<strong style="display:block; margin-bottom:0.25rem;">Adversarial input detected and neutralised</strong>'),
]

applied, missed = 0, []
for old, new in SUBS:
    if old in body:
        body = body.replace(old, new)
        applied += 1
    else:
        missed.append(old[:70])

# --- integrity check: every id app.js queries must survive -------------------
appjs = io.open(REPO + "/frontend-legacy/js/app.js", encoding="utf-8").read()
needed = sorted(set(re.findall(r'getElementById\(["\']([^"\']+)["\']\)', appjs)))
present = set(re.findall(r'id="([^"]+)"', body))
missing_ids = [i for i in needed if i not in present]

# ids app.js creates at runtime rather than reading from the page
RUNTIME_IDS = {"toastContainer"}
missing_ids = [i for i in missing_ids if i not in RUNTIME_IDS or i not in present]

io.open(OUT, "w", encoding="utf-8").write(body + "\n")

print("substitutions applied: %d/%d" % (applied, len(SUBS)))
if missed:
    print("NOT FOUND (investigate):")
    for m in missed:
        print("   ", m)
print()
print("ids app.js queries: %d" % len(needed))
print("ids missing from markup: %s" % (missing_ids or "NONE"))
print()
print("querySelector/All targets in app.js:")
for q in sorted(set(re.findall(r'querySelectorAll?\((["\'])(.+?)\1', appjs)))[:20]:
    print("   ", q[1])
print()
print("written:", OUT, "(%d chars)" % len(body))

import unicodedata
def emoji_codepoints(text):
    hits = []
    for m in re.finditer(r"&#(\d+);", text):
        cp = int(m.group(1))
        if 0x1F000 <= cp <= 0x1FAFF or cp in (0x26A0, 0x2600, 0x2728):
            hits.append("&#%d;" % cp)
    for ch in text:
        cp = ord(ch)
        if 0x1F000 <= cp <= 0x1FAFF or cp == 0xFE0F:
            hits.append(repr(ch))
    return hits

left = emoji_codepoints(body)
print()
print("section 18 -- emoji remaining in markup:", left or "NONE")
