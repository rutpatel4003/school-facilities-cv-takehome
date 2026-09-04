# School Facilities from Aerial Imagery

**USC Economics take-home submission - Rut Patel**

This repository measures rooftop solar, portable classrooms, perimeter
fencing, and athletic facilities for 25 U.S. public schools. It is a
time-boxed, auditable prototype: dated imagery and model outputs are preserved,
uncertain cases are flagged, and accuracy and confidence are evaluated against
manual labels.

## Start here: choose what you want to reproduce

The final measurements, reviewed campus locations, manual validation labels,
and reported validation tables are already committed. A reviewer does **not**
need to repeat the campus review or call Gemini just to verify my reported
results.

**To inspect the submission:** open `measurements.csv`, `memo.pdf`, and the
tables in `outputs/`. No command or API key is required.

**To recalculate the reported validation and scale results:** run only the
following from the repository root, the directory containing `run.py` and the
committed `measurements.csv`. Do not create `.env`; this path makes no API
calls.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
python run.py check-data
python run.py validate \
  --predictions-csv measurements.csv \
  --development-school-id 060001909278 \
  --development-school-id 060483000471 \
  --development-school-id 061734009378
python run.py summarize --daily-request-limit 500
python -m pytest -q
```

The repeated `--development-school-id` option does **not** limit validation to
those three schools. It tags them as schools used while improving the method,
so the output can show them separately. Validation still scores all nine labeled
schools: three appear under `development`, the other six under `reporting`, and
the `all` row combines all nine. See
[`VALIDATION_GUIDE.md`](VALIDATION_GUIDE.md) for the labeling rules, exclusions,
metrics, and interpretation of these groups.

This path uses the committed `measurements.csv`, `data/campus_review.csv`, and
`data/validation_labels.csv`. It is deterministic, needs no Gemini key, and
does not download imagery. Skip `prepare-campus`, `fetch-imagery`, and
`extract`.

**To rerun the image-to-measurement experiment:** follow the complete workflow
under [Optional: rerun the full pipeline](#optional-rerun-the-full-pipeline). The
committed campus decisions can still be reused; run `prepare-campus` and the
HTML reviewer only if you deliberately want to repeat my manual campus-location
review. A fresh Gemini run reproduces the method but may not produce identical
answers, so the committed outputs remain the record of the submitted run.

## Submission files

- [`measurements.csv`](measurements.csv): final 25-school deliverable.
- [`memo.pdf`](memo.pdf): one-page methods, validation, failures, scale, and
  tooling memo.
- [`outputs/`](outputs): compact validation, calibration, runtime, and scale
  audit tables.
- [`data/campus_review.csv`](data/campus_review.csv): reviewed campus centers
  and crop sizes.
- [`data/validation_labels.csv`](data/validation_labels.csv): manual labels and
  ground-truth notes for eight seeded schools plus one solar challenge case.

Generated imagery, raw API responses, logs, caches, and model-comparison runs
are intentionally excluded from Git. They can be regenerated and are not
needed to review the submitted results.

## Final results

The final submitted run contains all 25 schools and used
`gemini-3.1-flash-lite` with prompt version
`2026-09-03-solar-roof-proof-v2`.

The original validation sample contains eight schools selected reproducibly by
school level. I later added Spring Lake Heights on purpose as a ninth,
solar-positive challenge case; it is reported separately so it is not mistaken
for a random draw.

| Validation group | Schools | Scored fields | Excluded fields | Exact accuracy | Mean confidence | Brier score (lower is better) |
|---|---:|---:|---:|---:|---:|---:|
| Seeded sample | 8 | 59 | 4 | 67.8% | 70.7% | 0.114 |
| Added solar challenge | 1 | 8 | 1 | 62.5% | 66.3% | 0.109 |
| All audited schools | 9 | 67 | 5 | 67.2% | 70.1% | 0.113 |

Accuracy is simply the number of exact matches divided by the number of fields
that could be judged: 45/67. The five excluded comparisons are still listed in
`outputs/validation_exclusions.csv`. Four compare current or undated Google
solar observations with older NAIP inputs at Bertha and Pittsburgh. Spring
Lake's solar presence is scored, but its rough 1,800 m2 area estimate is not
precise enough for a 25% error test.

Cerra Vista's seven portable buildings are visible in the same 2022 NAIP image
used by the model: five along the north edge and two near the center. Low
contrast makes the roof gaps easy to miss. The prediction of zero is therefore
counted as an error, not excluded. Portable count is now 8/9 overall, but the
only positive example is this missed case.

### What the confidence numbers say

A confidence of 0.9 is meant to say, “answers like this should be correct about
90% of the time.” I compared that promise with what actually happened:

- 0.9 confidence: 30/32 correct (93.8%);
- 0.7 confidence: 15/22 correct (68.2%);
- 0.4 or 0.1 confidence: 0/13 correct.

**Interpretation:** the 0.9 and 0.7 bands were close to their stated success
rates, while the 0.4 band was overconfident because none of its five answers
was correct. The bands rank risk usefully, but they are not yet fully calibrated
probabilities.

The bands generally put the riskiest answers at the bottom, but they were not
perfect: the 0.9 Cerra Vista portable answer and one 0.9 track answer were
wrong. Overall confidence was 70.1% while accuracy was 67.2%.

I also report two standard summaries because the overall averages can hide a
bad confidence band. Expected calibration error (ECE) is the average gap
between promised confidence and actual accuracy across the four bands; it is
6.6 percentage points. The Brier score averages the squared difference between
each confidence and whether that answer was right; it is 0.113, and lower is
better. The largest single-band gap is 40 points in the 0.4 band. These names
are useful shorthand, but the per-band counts above are the clearest result.

Fencing was the main failure. Fence extent was correct for 3/9 schools and type
for 2/9, accounting for 13 of 22 errors. All 13 fence errors had confidence 0.4
or 0.1, so the pipeline correctly recognized that overhead fence evidence was
weak. Without the two fence fields, accuracy was 40/49 (81.6%).

### What I would send to a person for review

If every field with confidence 0.7 or lower is reviewed, a person checks 35/67
fields and sees 20/22 errors. Of the 32 fields left automatic, 30 are correct
(93.8%). A smaller queue containing only 0.4/0.1 fields checks 13/67 fields;
all 13 are errors, but it misses nine other errors. The existing school-level
flag also catches 20/22 errors but sends 52/67 fields for review, so field-level
flags are more efficient.

These numbers explain the practical trade-off: a larger review queue catches
more mistakes. They were measured on the same small development audit, so they
are evidence about this submission, not guarantees for new schools.

## Method and design reasoning

1. **Confirm which campus is being measured.** The supplied CCD coordinate is a
   starting point, not a school boundary. I compared it with a geocoded option,
   opened both map links for every school, and selected the center and crop size.
   This reduces the chance of measuring a neighboring park or school.
2. **Use imagery with a known date.** I download NAIP imagery through Microsoft
   Planetary Computer and save its date, source item, crop, and pixel scale.
   NAIP is sometimes older than Google imagery, but its date lets another person
   understand exactly what the prediction refers to.
3. **Show both the whole campus and small details.** One request contains the
   full image, a centered close-up, and four overlapping sections. The full view
   gives boundary context; the closer views make small objects easier to see.
4. **Ask for structured answers.** Gemini must return the requested fields and
   short visual evidence instead of unrestricted prose. The prompt separates
   rooftop panels from solar carports and detached portables from permanent
   buildings. Code converts solar image boxes to square meters using the saved
   pixel scale.
5. **Turn uncertainty into a review decision.** Each field receives one of four
   confidence levels. Missing edges, unclear campus ownership, weak visibility,
   or contradictory answers lower confidence. Weak fields are sent to a person
   instead of being silently accepted.
6. **Check the claims against manual labels.** Eight schools were selected with
   a fixed seed across school levels, and Spring Lake was added as a clearly
   disclosed solar-positive challenge. I compare exact answers, count errors,
   whether confidence matched actual correctness, and how many mistakes each
   review rule caught.

Three seeded schools helped me improve the method, and I later inspected the
other five during model comparisons. I therefore describe this as a development
audit of the final submission, not an untouched test of future performance.

The model receives only the dated aerial views and school metadata. Web search
is not used during extraction because current web evidence can conflict with
the historical NAIP date.

## Repository layout

```text
.
|-- README.md
|-- memo.pdf
|-- measurements.csv
|-- requirements.txt
|-- run.py
|-- campus_review_helper.py
|-- data/
|   |-- schools_sample.csv
|   |-- campus_review.csv
|   `-- validation_labels.csv
|-- outputs/
|   |-- run_diagnostics.csv
|   |-- validation_observations.csv
|   |-- validation_summary.csv
|   |-- validation_overview.csv
|   |-- calibration_summary.csv
|   |-- validation_exclusions.csv
|   |-- validation_review_summary.csv
|   |-- validation_sample_summary.csv
|   `-- scale_summary.txt
|-- src/schoolfac/
|-- tests/test_core.py
`-- VALIDATION_GUIDE.md
```

## Optional: rerun the full pipeline

Python 3.11 is recommended. Network access is required to retrieve NAIP
imagery and call Gemini.

This numbered section is for rebuilding the experiment, not for checking the
committed results. For validation alone, use the short, no-API workflow at the
top of this README and skip the campus, imagery, mock, and Gemini steps below.

### 1. Create the environment

```bash
python -m venv .venv
source .venv/bin/activate          # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env`:

```text
GEMINI_API_KEY=YOUR_KEY
GEMINI_MODEL=gemini-3.1-flash-lite
SCHOOL_CV_USER_AGENT=SchoolFacilitiesCVTakeHome/0.1 (contact: YOUR_EMAIL)
```

For this 25-school sample, a qualifying Gemini free-tier key is sufficient: the
pipeline makes one model request per school, plus any retries. Sign in to
[Google AI Studio](https://aistudio.google.com/apikey) and create or copy an API
key; billing is not required for models available on the free tier. Quotas are
account- and model-specific, so check AI Studio's Usage page before rerunning
the entire sample.

If a USC-managed Google account says that AI Studio is unavailable, that access
is controlled by the university's Google Workspace administrator. Use a
personal Google account, or ask the administrator for access. 
This repository does not require a USC-owned
key. Keep the key only in `.env`; `.env` is ignored by Git.

The example file contains the Gemini 3.1 Flash-Lite standard paid token rates
available on 2026-09-03. Verify them against the
[current official pricing page](https://ai.google.dev/gemini-api/docs/pricing)
before quoting a new cost estimate.

### 2. Validate the input and reviewed campuses

```bash
python run.py check-data
```

`data/campus_review.csv` is intentionally committed. It records the human
location-review step required by the assignment: I opened map/aerial links for
all 25 schools, confirmed that 24 CCD points were on the intended campus,
manually corrected one campus center, adjusted crop sizes where necessary, and
recorded the reasoning in `notes`. The geocoder never silently replaces a CCD
coordinate.

To repeat that subjective review from scratch:

```bash
python run.py prepare-campus
python campus_review_helper.py --html
```

Open `data/campus_review.html`, inspect the CCD and candidate links, then fill
`decision` in `data/campus_review.csv` with `ccd`, `candidate`, or `manual`.
For `manual`, also fill the manual latitude/longitude. The committed file lets
the main run reproduce my adjudications without pretending they were automated
or claiming that a square crop is a legal campus boundary. Just use my committed data/campus_review.csv if it gets regenerated and is not filled.
Public Nominatim is used only to generate one cached candidate per school; it
is not an appropriate 130,000-school geocoder.

### 3. Fetch the dated imagery

```bash
python run.py fetch-imagery --limit 2   # optional to test if everything is working
python run.py fetch-imagery
```

Each school receives `overview.png` plus metadata containing the acquisition
date, source item, map coordinates, pixel scale, crop extent, and image coverage.
Files are written under `data/imagery/` and ignored by Git.

### 4. Test file flow without an API call

```bash
python run.py extract --provider mock --limit 1
```

The mock provider deliberately returns unmeasurable fields. It tests pipeline
mechanics, not model accuracy, and writes `outputs/mock_measurements.csv` and
`outputs/mock_run_diagnostics.csv` so it cannot replace the submitted results.

### 5. Run the final extraction

```bash
python run.py extract --provider gemini
```

This writes `outputs/measurements.csv`, `outputs/run_diagnostics.csv`, and one
raw evidence JSON per school. The committed root `measurements.csv` is a copy
of the final 25-school output. Raw JSON remains local because it is verbose and
may contain provider metadata; it preserves the original response, every
quality-control change, and the final measurement during development.

Gemini is a hosted generative model, so exact counts can vary across reruns and
the provider can revise a model behind an alias. The diagnostics record the
model ID, prompt version, token use, imagery date, and runtime. A fresh API run
therefore reproduces the **procedure**, not a bit-identical prediction file.

The client retries a transient Gemini failure up to four times with increasing
waits. A school that still fails is not dropped: it receives a low-confidence
`Pipeline error:` row. Find those rows with:

```bash
python -c "import pandas as pd; d=pd.read_csv('outputs/measurements.csv',dtype={'school_id':str}); f=d[d.failure_notes.fillna('').str.startswith('Pipeline error:')]; print(f[['school_id','school_name','failure_notes']].to_string(index=False))"
```

After a 503 clears (or after a 429 quota reset), rerun only the failed school:

```bash
python run.py extract --provider gemini --school-id SCHOOL_ID
```

The single-school command replaces that row in both output CSVs while retaining
the other 24. Repeat for each listed ID, confirm the failure query is empty,
then use the complete validation and scaling commands in Step 6 below. Do not
rerun successful schools merely to search for a better score.

### 6. Validate the new extraction and estimate scale

```bash
python run.py validate \
  --predictions-csv outputs/measurements.csv \
  --development-school-id 060001909278 \
  --development-school-id 060483000471 \
  --development-school-id 061734009378

python run.py summarize --daily-request-limit 500
python -m pytest -q
```

The path in this command is intentional: `outputs/measurements.csv` is the new
Gemini extraction created in Step 5. To audit the frozen submitted results
instead, stop and use the shorter command near the top of this README, which
selects the committed root `measurements.csv`. Do not mix one run's predictions
with the other run's diagnostics. A hosted-model rerun reproduces the procedure
but may produce different answers; production work should pin a dated model
release where available and preserve raw responses and checksums.

As above, `--development-school-id` tags the three method-development schools;
it does not filter out the other six labeled schools. See
[`VALIDATION_GUIDE.md`](VALIDATION_GUIDE.md) for the full interpretation.

`prepare-validation` recreates the eight seeded rows (three primary, two middle,
three high). The committed label file contains one additional row that I added
manually: school ID `341560004108`, Spring Lake Heights Elementary School. I
chose it after seeing visible rooftop solar, specifically to add a positive
challenge case. To rebuild the identical nine-row audit from scratch, run
`prepare-validation`, then append that school from `data/schools_sample.csv`
and set `sample_role=targeted_solar_challenge`; normally, simply keep the
committed `data/validation_labels.csv`.

I hand-labeled only fields with supporting evidence and left unresolved cells
blank. Counts and categories require exact agreement; positive solar area is
correct when it is within 25% of a reliable manual measurement. The evaluator
then answers three questions: how often was the model right, did its confidence
match that success rate, and how many mistakes would its review flags catch?

The eight seeded rows were selected before labeling and the initial predictions
were saved. Three schools were used directly while improving the pipeline. I
then examined mistakes across the other five during prompt/model testing, so
the final run is a transparent development audit, not an independent estimate
of nationwide accuracy. Once I opened those five predictions to understand
their failures, they were no longer unseen examples; the result audits this
artifact but does not estimate performance on future schools.

Google Maps/Street View helped with manual interpretation, but references that
could not be aligned to the NAIP date are not placed in the primary score.
Bertha and Pittsburgh current/undated solar observations, Spring Lake's rough
area estimate remain visible in `validation_exclusions.csv`. Cerra Vista is not
excluded: seven detached portable buildings are visible in its 2022 NAIP input,
although low contrast makes the roof gaps difficult to see. The model's zero
count is scored as a high-confidence error.

The manual audit is a careful reference set, not perfect truth. For fencing I counted
only visible physical fence, wall, or closable-gate segments; houses, vegetation,
roads, and open space may define an edge but are not fencing. Street View does
not cover every side of a campus, so an unseen segment cannot support a strong
`none` or `full` label. For portables, the unit is a distinct detached building,
not every classroom or roof bay. When aerial seams could mean either separate
buildings or joined modules, the label is provisional or blank rather than
treated as certain.

The optional two-date attribute is not claimed. Bertha and Pittsburgh suggest
solar changed after the dated NAIP acquisition, but the Google aerial dates are
not known precisely enough to satisfy the requirement to name both dates. A
defensible extension would compare two dated NAIP acquisitions or dated
historical Street View observations.

### How to read the validation output

First read the `Using predictions:` line. `measurements.csv` means the frozen
submitted run; `outputs/measurements.csv` means a newly generated Gemini run.

- In **Evaluation overview**, `all` summarizes all nine audited schools,
  `development` contains the three schools used directly while improving the
  method, and `reporting` contains the other six. The three development schools
  are not the only validation set and should not be reported alone: that would
  discard six labeled schools and emphasize examples already used for tuning.
  I report the reproducibly selected eight-school sample as the main sample,
  the added solar challenge separately, and all nine as the full audit. The
  development/reporting rows disclose how tuning affected the results; neither
  is presented as an untouched holdout.
- In **Field summary**, `n` is the number of usable manual comparisons for that
  attribute and `accuracy` is its exact-match rate. For count fields, `mae` is
  the average absolute counting error. Positive recall, negative specificity,
  and zero/nonzero accuracy appear only when the labels contain those cases.
- In **Calibration**, compare `confidence` with `observed_accuracy`. A positive
  gap means the model was more confident than its results justified; a negative
  gap means it was conservative. Smaller absolute gaps are better, but the
  counts and number of schools show how little evidence supports each rate.
- `NaN` means that a statistic does not apply or that the audit contains no
  example needed to calculate it. It does not mean zero accuracy.

### How validation, confidence, and review flags are calculated

- Boolean, category, and count fields are correct only when prediction and
  manual label match exactly. Counts also report mean absolute error.
- Solar area is evaluated only for a date-compatible positive label and counts
  as correct when relative error is at most 25%. No current positive area label
  is precise enough for that test, so the pipeline does not invent an area
  accuracy result.
- Each scored field becomes `correct=1` or `correct=0`. Accuracy is the number
  correct divided by the number scored. An `unmeasurable` prediction still
  counts as wrong when the manual reference contains an answer, so abstaining
  cannot make the score look better.
- Confidence is checked by group. If 0.9 is meaningful, roughly 90% of the
  0.9 answers should be correct. The per-band table is the main result because
  it shows directly where confidence was honest or misleading.
- ECE summarizes the average absolute gap between each confidence band and its
  actual accuracy. Brier score averages `(confidence - correct)^2`, so a highly
  confident mistake receives a larger penalty. I include both because mean
  confidence can look close to mean accuracy even when individual bands are
  wrong in opposite directions.
- A review flag is useful when it catches many errors without asking a person
  to check everything. The review summary therefore reports fields sent to
  review, errors caught, and accuracy among the fields left automatic.

## Outputs and confidence

`measurements.csv` contains every requested value, its confidence, the imagery
date, a `review_required` flag, and failure notes. The four confidence bands are
transparent evidence categories, not fitted probabilities.
Coverage defects are combined before applying a penalty so the same missing
image region is not counted several times.

Quality-control rules include:

- non-rooftop solar canopies and ground arrays do not contribute to rooftop
  presence or area;
- positive rooftop-solar detections are capped at 0.7 and flagged for review;
- positive solar-area estimates are capped at 0.4 until a precise,
  date-matched area reference exists;
- a `none` fence estimate is low-confidence because a thin fence may be below
  NAIP's useful resolution;
- fence type becomes `unknown` when material is not visible;
- court and field counts are capped at 0.7 because overlapping layouts and
  shared surfaces create counting ambiguity;
- ambiguous campus boundaries reduce ownership-dependent measurements.

The final run's school-level `review_required` rate is 88%. It is intentionally
conservative and shows that the prototype is not ready for unattended national
deployment. The validation table also evaluates field-level thresholds because
reviewing one weak fence should not force a reviewer to recheck an obvious pool.

## Runtime and cost at scale

The final 25-school run measured:

- median 8.76 seconds per school; mean 15.32 seconds because of API latency
  outliers and retries;
- 13.2 sequential days for 130,000 schools at the median;
- 6.3 hours under idealized 50-way parallelism, before rate limits, retries,
  storage, or manual review;
- 8,125 mean input tokens and 432 mean visible output tokens per school; the
  diagnostics also record thinking tokens separately when a model reports them;
- $0 cash inference cost for this 25-school run on the free tier, but at
  500 requests/day the national run would require at least 260 days before
  retries.

At the observed token volume, current published prices imply:

| Model / service tier | Input / output per 1M tokens | Per school | 130,000 schools |
|---|---:|---:|---:|
| Gemini 3.1 Flash-Lite, standard | $0.25 / $1.50 | $0.00268 | $348 |
| Gemini 3.1 Flash-Lite, batch | $0.125 / $0.75 | $0.00134 | $174 |
| Gemini 3.5 Flash, standard* | $1.50 / $9.00 | $0.04157 | $5,404 |
| Gemini 3.5 Flash, batch* | $0.75 / $4.50 | $0.02079 | $2,702 |
| Gemini 3.8 Flash, standard introductory | $0.75 / $3.75 | $0.00769 | $1,000 |
| Gemini 3.8 Flash, batch introductory | $0.375 / $1.875 | $0.00385 | $500 |

\*The 3.5 estimate uses the actual eight-school test's reported billable output,
including a mean 2,766 thinking tokens per school. The 3.8 estimate holds the
3.1 token load constant because repeated 503 responses prevented a completed
test.

Google describes Gemini 3.8 Flash as its most intelligent Flash model, but that
does not establish better performance on this imagery task. My attempted test
returned repeated 503 capacity errors, so I make no quality claim for it. It
should be benchmarked on the same locked, positive-containing audit when the
service is available. Its introductory prices are published through 2026-12-31
and double afterward. Thinking tokens, retries, storage, grounding, engineering
labor, and manual QA can increase the total. Free-tier quotas are not a national
scaling strategy.

### Exploratory model comparison

On the same earlier eight-school run, 3.1 Flash-Lite scored 34/58
date-compatible comparisons and 3.5 Flash scored 35/58. The single-cell
difference is too small to establish a quality improvement. The 3.5 run had a
worse Brier score (0.145 versus 0.136), a 93.7-second median versus 5.7 seconds,
repeated 503s, and about 15.5 times the estimated inference cost. I therefore
kept 3.1 Flash-Lite.

Repeated 3.1 runs ranged from 34/58 to 42/58 on the same seeded rows; the frozen
final run is 40/58. That variation is itself a limitation of hosted VLM
inference, not a reason to keep rerunning until the number looks good. The
submitted `measurements.csv` is frozen so `validate` reproduces the reported
result exactly; a fresh API run may differ even with the same model and prompt.

## Known failures and limitations

- **Campus attribution:** a center plus square crop is not a parcel polygon;
  nearby parks, schools, and shared athletic facilities can be misattributed.
- **Fencing:** extent and especially material are hard to judge from overhead
  imagery: fence lines can be too thin for the image resolution, trees and
  shadows interrupt them, and a
  top-down view often cannot distinguish chain-link from other metal fencing.
  Street View is incomplete around many campuses, and a house, hedge, road, or
  other natural/land-use boundary is not itself a fence. Even the manual labels
  may therefore contain boundary and visibility error rather than perfect truth.
  Fence extent was correct on 3/9 and fence type on 2/9 labeled schools. All 13
  fence errors fell in the 0.4/0.1 bands. The pipeline therefore lowers confidence
  for `none`/`unknown` and asks for review rather than treating non-detection as
  evidence of absence.
- **Portables and other counts:** a detached portable building can contain
  several classrooms or joined factory-built modules; roof seams do not prove
  separate buildings, and permanent annexes/storage can look similar. Cerra
  Vista is the audit's one positive case: the seven buildings appear in the
  2022 NAIP image, but the model reported zero with 0.9 confidence. The other
  eight portable labels are zero, so portable accuracy is 8/9 while positive
  detection is 0/1. More positive examples are needed. Small courts,
  overlapping markings, shared outfields, and tree cover also caused errors.
- **Solar:** canopies can resemble rooftop arrays. Area is a bounding-box and
  estimated panel-coverage calculation converted with the saved pixel scale,
  not a model-supplied square-meter guess. Manual ruler
  measurements are still rough when arrays are irregular, and no area result
  has earned calibrated confidence above the review band. On date-compatible presence
  labels the model was 7/7, including Spring Lake as the only positive. That is
  too small to show reliable detection of positive cases, and no positive area label
  was precise enough to score. The Bertha/Pittsburgh current-reference misses
  remain visible as temporal stress tests.
- **Imagery:** NAIP vintages vary; Ridgeview Elementary used a 2017 acquisition
  and is explicitly flagged as stale.
- **Hosted VLM:** observed failures included transient 503 responses, variable
  latency, occasional truncated structured output, run-to-run variation, and
  free-tier 429 quota exhaustion. Retries and per-school failure rows keep the
  batch auditable instead of silently dropping schools.

## What I would do with 100 hours

1. **Hours 1-20: learn and define the task.** Read work on solar mapping,
   building detection, facility counts, and confidence calibration. Compare
   imagery sources by date, resolution, license, and API limits. Tighten the
   label guide and have two people label a small pilot so I can see where humans
   disagree before treating labels as truth.
2. **Hours 21-40: build better campus boundaries.** Test school and building
   polygons from OSM/Overpass or OSMnx, Overture Maps, Microsoft Building
   Footprints, open parcel data, and school-district GIS layers. Combine them
   with roads and connected play areas, then show uncertain boundaries in a
   small QGIS or web-map review tool.
3. **Hours 41-65: create a meaningful benchmark.** Label 500-1,000 schools
   across regions, school levels, rural/urban settings, imagery years, and
   campus complexity. Deliberately include more schools with solar, portables,
   pools, and different fence types. Use two labelers and resolve disagreements;
   keep separate schools for method development, confidence adjustment, and a
   final untouched test.
4. **Hours 66-90: test methods for each attribute.** Compare the current VLM
   with building masks and specialized solar, portable, court, field, and track
   detectors (for example SAM 2, Grounding DINO, or YOLO after license checks).
   Treat fencing as its own problem using better aerial imagery and a legally
   usable street-level source. Use a stronger Gemini model only for cases where
   cheaper methods disagree or remain uncertain.
5. **Hours 91-100: set review rules and make the pipeline robust.** On the
   untouched labels, measure what 0.9/0.7/0.4/0.1 actually mean for each field
   and adjust them with a simple calibration method if enough examples exist.
   Choose the review cutoff based on how many errors staff need to catch and how
   much they can review. Add batching, caching, resumable jobs, data versions,
   and cost/latency monitoring.

## Time spent and AI use

Approximate elapsed working time was **5 hours 40 minutes**:

- 20 minutes understanding the task and measurement definitions;
- 50 minutes collaboratively designing the approach with ChatGPT, generating
  the initial code, and checking the design;
- 30 minutes opening the CCD/candidate links and adjudicating every campus;
- 60 minutes labeling and manually verifying eight schools, with ChatGPT and
  Claude used as second opinions for unfamiliar aerial features such as
  portable classrooms; uncertain/date-mismatched cases were left blank;
- 90 minutes adding reliability checks and confidence rules, fixing bugs, revising prompts,
  and manually cross-checking failure cases;
- 60 minutes across model/rate-limit tests, final Codex prompt changes, and the
  final model comparison/rerun; and
- 30 minutes writing and packaging the memo.

This is about 40 minutes above the requested five hours. I knew I was going
past the suggested limit, but chose to spend that time learning how unfamiliar
features such as portables and fences appear from above, resolving ambiguous
labels, investigating why failures occurred, and checking whether confidence
fell when the image evidence was weak. The purpose was not to rerun until the
accuracy looked better; it was to make the uncertainty and review decisions
more honest. AI accelerated design, implementation, debugging, and
second-opinion review; I remained responsible for definitions, campus choices,
labels, experiments, and what is reported.

## Tooling and authorship

- Microsoft Planetary Computer STAC and NAIP: dated aerial imagery.
- OpenStreetMap Nominatim: candidate campus locations for manual review only.
- Google Maps/Street View: manual campus and validation reference, not an
  automated extraction API.
- Gemini 3.1 Flash-Lite: one structured multimodal call per school.
- Python, pandas, rasterio, pyproj, Pillow, Pydantic, and pytest: pipeline,
  geospatial calculations, validation, and tests.
- ChatGPT: collaborative initial design, initial code generation, debugging,
  and second-opinion visual interpretation.
- Claude: second-opinion visual interpretation on unfamiliar validation cases.
- OpenAI Codex: final guardrails, prompt iteration, code review, testing, and
  documentation/packaging.

I selected the measurement definitions and validation protocol, manually
reviewed all campus locations, created the ground-truth labels and notes, ran
the experiments, inspected failure cases, and made the final model/scope
decisions. I also read and reviewed every AI-generated code or prompt change,
traced how it affected the data flow, ran the code, inspected the resulting
rows and diagnostics, and revised or rejected suggestions when they did not
match the task. I used AI side by side as an implementation and review tool;
it did not replace my coding judgment, manual adjudication, or responsibility
for the reported validation.
