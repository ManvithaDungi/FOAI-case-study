"""Refresh the v4 deck with real-data-calibrated results (text/chart/table edits only; design untouched)."""
from pptx import Presentation
from pptx.chart.data import CategoryChartData

PATH = r'D:\Sem 7\FOAI\FOAI case study\Clinical_Trial_MAS_Case_Study_v4.pptx'
prs = Presentation(PATH)
slides = list(prs.slides)


def set_para(p, text):
    runs = p.runs
    runs[0].text = text
    for r in runs[1:]:
        r._r.getparent().remove(r._r)


def set_lines(slide, starts, lines):
    for sh in slide.shapes:
        if sh.has_text_frame and sh.text_frame.text.startswith(starts):
            paras = sh.text_frame.paragraphs
            assert len(paras) == len(lines), (starts, len(paras))
            for p, t in zip(paras, lines):
                set_para(p, t)
            return
    raise KeyError(starts)


# tools slide (index 6): dataset mention
s_tools = slides[6]
set_lines(s_tools, 'Protocol + PrivateState', ['Dataclasses; scenarios calibrated on ClinicalTrials.gov'])

# execution slide (index 7)
s = slides[7]
set_lines(s, 'IRB lowers dose', ['IRB lowers dose 100 to 75 mg (binding)',
                                 "Sponsor's cut to 150 patients blocked: underpowered",
                                 "Advocate's visit cut blocked by IRB: no remote monitoring"])
set_lines(s, 'Sponsor funds remote', ['Sponsor funds remote monitoring',
                                      'Biostatistician adds stratified randomisation',
                                      '6 visits accepted; cut to 150 blocked again'])
set_lines(s, 'IRB drops non-safety', ['Sponsor resizes sites to 9, budget $14.7M',
                                      'IRB trims exclusions to safety-only',
                                      '0 open issues remain'])
for old, new in [('320 to 180', '260 kept'), ('patients', 'patients (real P90)'), ('12 to 4', '12 to 6'),
                 ('0.79 to 0.85', '0.70 to 0.95'), ('$26M to $9M', '$21.9M to $14.0M')]:
    for sh in s.shapes:
        if sh.has_text_frame and sh.text_frame.text == old:
            set_para(sh.text_frame.paragraphs[0], new)
            break
s.notes_slide.notes_text_frame.text = (
    "Baseline re-run with starting values calibrated on 5,000 real completed Phase II trials from ClinicalTrials.gov "
    "(accessed 2026-10-14): Sponsor draft and cap = 90th percentile of enrolment (260), target = 80th percentile "
    "(150), 9 hospitals (median multi-site), 2 arms (median). Round 1: IRB lowers dose to 75 mg (binding); the "
    "Sponsor's cut to 150 is blocked by the Biostatistician (underpowered); the Advocate's visit cut is blocked by the "
    "IRB until remote monitoring exists. Round 2: Sponsor funds remote monitoring, stratified randomisation added, 6 "
    "visits accepted; 150 patients blocked again. Round 3: sites resized to 9 and budget aligned to $14.7M; IRB "
    "exclusions trimmed to safety-only. Round 4: all approve, v4, 0 violations. Final 260 patients, power 0.948.")

# results slide (index 8)
s = slides[8]
single = {'Interim AEs': 4, 'Multi-country': 7, 'Pandemic': 7, 'Pediatric': 9, 'Rare disease': 7,
          'High-risk drug': 9, 'Budget cut 40%': 8, 'Baseline': 6}
for sh in s.shapes:
    if sh.has_chart:
        cats = list(sh.chart.plots[0].categories)
        cd = CategoryChartData()
        cd.categories = cats
        cd.add_series('Single agent', [single[c] for c in cats])
        cd.add_series('Multi-agent (0 in every scenario)', [0] * len(cats))
        sh.chart.replace_data(cd)
    if sh.has_table:
        rounds = {'Baseline': 4, 'Budget cut 40%': 5, 'High-risk drug': 6, 'Rare disease': 6, 'Pediatric': 4,
                  'Pandemic': 4, 'Multi-country': 4, 'Interim AEs': 3}
        for row in list(sh.table.rows)[1:]:
            set_para(row.cells[1].text_frame.paragraphs[0], str(rounds[row.cells[0].text]))
s.notes_slide.notes_text_frame.text = (
    "From python main.py --mode compare --scenario all (mock mode, real-data calibrated), re-run and verified. "
    "Test levels: unit (tools, constraints, models), algorithm (authority order, partial acceptance, deadlock, max "
    "rounds), integration (private-state guard, no prompt leakage, LLM validation/fallback), scenario (all eight "
    "reach valid consensus). 96 passed. The single-agent baseline is intentionally naive; its violation count "
    "illustrates silent trade-offs without vetoes, not a claim that no single optimiser could satisfy the constraints.")

prs.save(PATH)
print('ok')
