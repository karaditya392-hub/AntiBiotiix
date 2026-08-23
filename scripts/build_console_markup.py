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


# ---------------------------------------------------------------------------
# Clinical Reference tab
# ---------------------------------------------------------------------------
# Replaces the Clinical Safety Test Suite tab. The suite is unchanged and still
# runs from the command line; POST /api/system/run-test-suite also still exists.
# What changes is that the slot now surfaces the ingested guideline corpus --
# 82 ICMR 2022-23 conditions and 29 ICMR STW 2022 workflows -- which the backend
# already served but nothing in the UI ever showed.
#
# Rendering is handled by src/legacy/clinicalReference.ts, NOT by app.js, so
# app.js keeps its four-line diff against the original.

# NOTE: matched AFTER the emoji substitutions above run, so the icon is already
# the typographic glyph rather than the original emoji.
_OLD_TAB_BUTTON = """<button class="nav-tab" data-tab="tab-test-lab">
      <span class="tab-icon" aria-hidden="true">◇</span> Clinical Safety Test Suite
    </button>"""

_NEW_TAB_BUTTON = """<button class="nav-tab" data-tab="tab-reference">
      <span class="tab-icon" aria-hidden="true">\u25a4</span> Clinical Reference
    </button>"""

_NEW_SECTION = """<section id="tab-reference" class="tab-pane">
      <div class="card">
        <div class="panel-header">
          <div>
            <h3><span class="icon" aria-hidden="true">\u25a4</span> Clinical Reference &mdash; Ingested Guideline Corpus</h3>
            <p class="sub-text">
              Conditions and antimicrobial regimens read directly from the guideline
              documents held by this system. Every entry carries its source document and,
              where the source is an official PDF, a real page number. Nothing here is
              generated: it is the ingested text.
            </p>
          </div>
          <span id="referenceCountBadge" class="badge badge-subtle">Loading&hellip;</span>
        </div>

        <div class="form-group">
          <label class="form-label" for="referenceSearchInput">Search conditions and medications</label>
          <input type="text" id="referenceSearchInput" class="form-input"
                 placeholder="e.g. cellulitis, pyelonephritis, meropenem, tuberculosis">
        </div>
        <div class="quick-presets">
          <span class="preset-label">Filter by source:</span>
          <button class="btn btn-chip" data-reference-filter="all">All</button>
          <button class="btn btn-chip" data-reference-filter="stg">ICMR Treatment Guidelines 2022-23</button>
          <button class="btn btn-chip" data-reference-filter="stw">ICMR Standard Treatment Workflows 2022</button>
        </div>

        <div id="referenceProvenanceNote" class="catalog-unavailable" style="display:none;"></div>

        <div class="reference-layout">
          <div class="reference-list" id="referenceList">
            <div class="empty-state"><p>Loading the ingested guideline corpus&hellip;</p></div>
          </div>
          <div class="reference-detail" id="referenceDetail">
            <div class="empty-state">
              <span class="empty-icon" aria-hidden="true">\u25a1</span>
              <p>Select a condition to read its presentation, regimens, and source.</p>
            </div>
          </div>
        </div>
      </div>
    </section>"""

start = body.find('<section id="tab-test-lab"')
end = body.find("</section>", start) + len("</section>")
if start == -1:
    raise SystemExit("test-lab section not found")

body = body[:start] + _NEW_SECTION + body[end:]

if _OLD_TAB_BUTTON not in body:
    raise SystemExit("test-lab nav button not found")
body = body.replace(_OLD_TAB_BUTTON, _NEW_TAB_BUTTON)

print()
print("Clinical Reference tab: swapped in")
print("  test-lab section removed:", '<section id="tab-test-lab"' not in body)
print("  reference section added :", 'id="tab-reference"' in body)
print("  testSuiteTableBody gone :", "testSuiteTableBody" not in body)

# app.js must not be left querying ids that no longer exist.
_gone = [i for i in ("runAllTestsBtn", "testSuiteTableBody")
         if i in appjs and 'id="%s"' % i not in body]
print("  ids app.js still queries but markup no longer has:", _gone or "NONE")

io.open(OUT, "w", encoding="utf-8").write(body + "\n")


# ---------------------------------------------------------------------------
# Comparative alternative-antibiotic analysis
# ---------------------------------------------------------------------------
# Lives in the prescription tab, directly beneath the safety results, because
# "what changes if I select an alternative?" is asked while looking at the
# warnings -- not on a separate screen.
#
# Rendering is handled by src/legacy/alternativeComparison.ts, NOT app.js.

_COMPARE_PANEL = """
            <!-- Comparative alternative analysis -->
            <div id="comparePanel" class="compare-panel hidden">
              <div class="panel-header">
                <div>
                  <h4><span class="icon" aria-hidden="true">\u21c4</span> Compare with an alternative</h4>
                  <p class="sub-text">
                    Runs the same deterministic safety engine against an alternative agent for
                    this patient, and shows the two side by side.
                  </p>
                </div>
              </div>

              <div class="form-group">
                <label class="form-label" for="compareInput">Alternative agent</label>
                <input type="text" id="compareInput" class="form-input"
                       placeholder="e.g. Azithromycin 500mg PO OD x 3 days">
              </div>
              <div class="quick-presets" id="compareSuggestions"></div>
              <button id="compareRunBtn" class="btn btn-secondary btn-sm">Run comparative analysis</button>

              <div id="compareResults" class="compare-results"></div>

              <p class="compare-disclaimer">
                This is a comparative analysis. Final medication selection remains the
                clinician's responsibility.
              </p>
            </div>
"""

_ANCHOR = """          </div>
        </div>

      </div>
    </section>

    <!-- TAB 2: Guidelines & Rules Explorer -->"""

if _ANCHOR not in body:
    raise SystemExit("prescription-tab anchor for the compare panel not found")
body = body.replace(_ANCHOR, _COMPARE_PANEL + _ANCHOR, 1)

# Alert-fatigue caveat: comparative runs increment the same trigger counters, so
# override rates read lower than clinical practice alone would produce.
_FATIGUE_ANCHOR = ('<p class="sub-text">Monitors trigger frequency vs. override rates per Rule ID '
                   'to identify over-alerting rules for clinical stewardship recalibration.</p>')
_FATIGUE_NOTE = _FATIGUE_ANCHOR + """
          <div class="catalog-unavailable" style="margin:0.75rem 0;">
            <strong>Counts include comparative what-if runs</strong>
            <p>
              Comparative alternative analyses execute the same rules and therefore increment
              <em>Total Triggered</em> without a clinician ever acting on the result. Override
              rates below will read lower than clinical practice alone would produce. Records
              created that way are marked as comparative in the audit trail.
            </p>
          </div>"""

if _FATIGUE_ANCHOR not in body:
    raise SystemExit("alert-fatigue anchor not found")
body = body.replace(_FATIGUE_ANCHOR, _FATIGUE_NOTE, 1)

print()
print("Comparative analysis panel: added")
print("  comparePanel present     :", 'id="comparePanel"' in body)
print("  in prescription tab      :", body.find('id="comparePanel"') < body.find('id="tab-guidelines"'))
print("  alert-fatigue caveat     :", "Counts include comparative what-if runs" in body)

_still_missing = [i for i in sorted(set(re.findall(r'getElementById\(["\']([^"\']+)["\']\)', appjs)))
                  if 'id="%s"' % i not in body]
print("  ids app.js queries but markup lacks:", _still_missing or "NONE")

io.open(OUT, "w", encoding="utf-8").write(body + "\n")


# ---------------------------------------------------------------------------
# Guidelines tab: cross-source comparison + rule governance
# ---------------------------------------------------------------------------
# Both are driven by src/legacy/guidelinesGovernance.ts, not app.js, so app.js
# keeps its four-line diff against the original. The existing rules catalog table
# is left exactly as it was.

_GUIDELINES_ADDITIONS = """
        <!-- Cross-source comparison -->
        <div class="card" id="crossSourceCard">
          <div class="panel-header">
            <div>
              <h3><span class="icon" aria-hidden="true">\u2261</span> Cross-Source Comparison</h3>
              <p class="sub-text">
                What every ingested guideline says about one topic, side by side and ordered by
                precedence. Sources that do not cover the topic are shown as silent rather than
                given a weak answer.
              </p>
            </div>
            <span id="crossSourceBadge" class="badge badge-subtle">11 documents held</span>
          </div>

          <div class="form-group">
            <label class="form-label" for="crossSourceInput">Syndrome or therapy topic</label>
            <input type="text" id="crossSourceInput" class="form-input"
                   placeholder="e.g. uncomplicated urinary tract infection empiric treatment">
          </div>
          <div class="quick-presets">
            <span class="preset-label">Try:</span>
            <button class="btn btn-chip" data-cross-topic="uncomplicated urinary tract infection empiric treatment">UTI</button>
            <button class="btn btn-chip" data-cross-topic="community acquired pneumonia treatment">CAP</button>
            <button class="btn btn-chip" data-cross-topic="skin and soft tissue infection cellulitis treatment">Cellulitis</button>
            <button class="btn btn-chip" data-cross-topic="tubercular meningitis regimen">TB meningitis</button>
          </div>
          <button id="crossSourceBtn" class="btn btn-primary btn-sm">Compare across sources</button>

          <div id="crossSourceResults" class="cross-source-results"></div>
        </div>

        <!-- Rule governance -->
        <div class="card" id="ruleGovernanceCard">
          <div class="panel-header">
            <div>
              <h3><span class="icon" aria-hidden="true">\u229c</span> Rule Governance &amp; Clinical Sign-Off</h3>
              <p class="sub-text">
                Rules ship as <code>PENDING_CLINICAL_REVIEW</code>. Review decisions are appended
                against the catalog rather than edited into it, so the shipped catalog stays
                reproducible and an approval cannot rewrite the rule it approved.
              </p>
            </div>
            <span id="governanceSummaryBadge" class="badge badge-subtle">Loading&hellip;</span>
          </div>

          <div id="governanceNotice" class="catalog-unavailable" style="margin-bottom:0.85rem;">
            <strong>Approval does not change how a rule behaves</strong>
            <p>
              Every rule fires identically before and after sign-off. Recording a review captures
              that a clinician accepted it, and writes that decision into the immutable audit trail.
              Only rule-authoring roles may sign off; the decision requires a written rationale.
            </p>
          </div>

          <div class="table-responsive">
            <table class="data-table" id="governanceTable">
              <thead>
                <tr>
                  <th>Rule ID</th>
                  <th>Severity</th>
                  <th>Catalog status</th>
                  <th>Effective status</th>
                  <th>Reviewed by</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody id="governanceTableBody">
                <tr><td colspan="6" class="text-center">Loading rule governance state&hellip;</td></tr>
              </tbody>
            </table>
          </div>
        </div>
"""

_RULES_CARD_ANCHOR = '        <!-- Rules Catalog Table -->'
if _RULES_CARD_ANCHOR not in body:
    raise SystemExit("rules catalog anchor not found")
body = body.replace(_RULES_CARD_ANCHOR, _GUIDELINES_ADDITIONS + "\n" + _RULES_CARD_ANCHOR, 1)

print()
print("Guidelines tab additions:")
print("  cross-source card   :", 'id="crossSourceCard"' in body)
print("  governance card     :", 'id="ruleGovernanceCard"' in body)
print("  inside guidelines   :", body.find('id="crossSourceCard"') > body.find('id="tab-guidelines"')
                                 and body.find('id="crossSourceCard"') < body.find('id="tab-audit"'))
print("  existing rules table intact:", 'id="rulesTableBody"' in body)

_gap = [i for i in sorted(set(re.findall(r'getElementById\(["\']([^"\']+)["\']\)', appjs)))
        if 'id="%s"' % i not in body]
print("  ids app.js queries but markup lacks:", _gap or "NONE")

io.open(OUT, "w", encoding="utf-8").write(body + "\n")
