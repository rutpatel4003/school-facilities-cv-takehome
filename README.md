# School Facilities from Aerial Imagery

**USC Economics take-home submission - Rut Patel**

This repository measures rooftop solar, portable classrooms, perimeter
fencing, and athletic facilities for 25 U.S. public schools. It is a
time-boxed, auditable prototype: dated imagery and model outputs are preserved,
uncertain cases are flagged, and accuracy and confidence are evaluated against
manual labels.

Recommended GitHub repository name: `school-facilities-cv-takehome`.

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

| Validation group | Schools | Scored comparisons | Excluded references | Exact accuracy | Mean confidence | Confidence - accuracy | Brier score |
|---|---:|---:|---:|---:|---:|---:|---:|
| Seeded sample | 8 | 58 | 5 | 69.0% | 70.3% | +1.4 pp | 0.102 |
| Added solar challenge | 1 | 8 | 1 | 62.5% | 66.3% | +3.8 pp | 0.109 |
| All audited schools | 9 | 66 | 6 | 68.2% | 69.8% | +1.7 pp | 0.103 |

The six excluded comparisons are still written to
`outputs/validation_exclusions.csv`. Bertha and Pittsburgh each contribute a
solar-presence and solar-area comparison from newer or undated Google imagery
against 2023/2022 NAIP inputs. Spring Lake's presence is visible in the NAIP
input and is scored, but its rough 1,800 m2 visual area estimate is not precise
enough to judge with a 25% tolerance. Cerra Vista has a provisional count of
seven roof-separated portable structures in current/undated Google imagery,
but it is not date-matched to the 2022 NAIP input and the seams may separate
modules rather than buildings; that comparison is also retained only as a
stress test. Reporting both the scored audit and these observations avoids
either mixing dates or hiding difficult cases.

Calibration was much more informative than the pooled accuracy. The 0.9 band
was correct on 30/31 fields (96.8%), the 0.7 band on 15/22 (68.2%), and every
0.4/0.1 field was wrong (0/13). Thus the evidence bands correctly ranked risk,
and overall mean confidence was within 1.7 percentage points of accuracy. That
pooled gap can hide opposite errors across bands, so I also report fixed-band
expected calibration error (8.0 percentage points), maximum band error (40.0
points in the five-item 0.4 band), Brier score (0.103), and the number of
schools contributing to each band. The sample is small, several fields from one
school are related, and one 0.9 track prediction was wrong; these are evidence
bands, not certified probabilities.

Fencing was the main failure. Fence extent was correct on 3/9 schools and type
on 2/9; together they caused 13 of 21 scored errors. All 13 fence errors had
confidence 0.4 or 0.1, exactly where the pipeline said the imagery was weak.
Without the two fence fields, accuracy was 40/48 (83.3%). This does not justify
dropping fencing; it justifies returning it for higher-resolution or
street-level review instead of inventing certainty from thin overhead lines.

The revised school-level flag marks 7/9 audit schools and captures 20/21
errors while sending 52/66 fields to review; it now treats an unobservable
fence type as a reason for review. A field-level rule of reviewing confidence
<= 0.7 captures 20/21 errors while reviewing 35/66 fields (53.0%); the 31
fields left automatic are 30/31 correct (96.8%). The strict 0.4/0.1 queue
reviews only 13/66 fields, all 13 are errors, and the remaining 53 fields are
45/53 correct (84.9%). These trade-offs are saved in
`outputs/validation_review_summary.csv`; they make the amount of human review
explicit rather than reporting accuracy alone. These thresholds are described
on the same development audit and are not yet out-of-sample service guarantees.

## Method and design reasoning

1. **Resolve the campus before measuring it.** A CCD point is a useful seed,
   not a parcel boundary. I generated a second geocoded candidate, opened the
   map/aerial links for every school, and chose a center and crop radius. This
   prevents a plausible-looking extraction from silently measuring the wrong
   campus, although a reviewed square is still weaker than a true polygon.
2. **Use dated, reproducible imagery.** I query NAIP through the Microsoft
   Planetary Computer STAC catalog and retain the acquisition date, item ID,
   CRS, transform, pixel area, crop extent, and coverage diagnostics. NAIP is
   older than consumer maps in some places, but its date and provenance make
   temporal claims auditable.
3. **Give the model both context and detail within one request.** Each campus
   becomes a full overview, centered 70% crop, and four overlapping quadrants.
   The overview supports campus-level reasoning; detail crops help with small
   objects. Sending all six together avoids six independent answers and stays
   within the free-tier request budget.
4. **Constrain extraction rather than accepting free text.** Gemini returns a
   typed schema with evidence. The prompt distinguishes rooftop panels from
   canopies/ground arrays and permanent buildings from portables. Solar area is
   calculated from localized image boxes and georeferenced pixel area, not an
   unsupported verbal estimate.
5. **Make uncertainty operational.** Deterministic checks combine crop
   coverage, edge visibility, boundary ambiguity, attribute observability, and
   internal inconsistencies into four evidence bands (0.9/0.7/0.4/0.1).
   Ambiguous fields and any positive solar case are routed to review. These are
   transparent pre-validation bands, not learned probabilities.
6. **Evaluate without overstating independence.** A fixed seed selected eight
   schools by level (3 primary, 2 middle, 3 high). I saved the initial
   predictions, labeled observable fields, and used three schools while
   improving the method. I later inspected errors across the other five while
   comparing prompts and models, so none of the final eight-school results is
   claimed as an unseen test set. Spring Lake was then added deliberately to
   test a visible solar-positive case. The evaluator keeps that role explicit
   and reports accuracy, count error, binary-class coverage, calibration, and
   review burden.

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

## Reproduce from a clean checkout

Python 3.11 is recommended. Network access is required to retrieve NAIP
imagery and call Gemini.

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
or claiming that a square crop is a legal campus boundary.
Public Nominatim is used only to generate one cached candidate per school; it
is not an appropriate 130,000-school geocoder.

### 3. Fetch the dated imagery

```bash
python run.py fetch-imagery --limit 2   # optional smoke test
python run.py fetch-imagery
```

Each school receives `overview.png` plus metadata containing the acquisition
date, STAC item, CRS, affine transform, pixel area, crop extent, and coverage
diagnostics. Files are written under `data/imagery/` and ignored by Git.

### 4. Test file flow without an API call

```bash
python run.py extract --provider mock --limit 1
```

The mock provider deliberately returns unmeasurable fields. It tests pipeline
mechanics, not model accuracy.

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
then rerun `validate` and `summarize`. Do not rerun successful schools merely
to search for a better score.

### 6. Reproduce validation and scaling

```bash
python run.py validate \
  --development-school-id 060001909278 \
  --development-school-id 060483000471 \
  --development-school-id 061734009378

python run.py summarize --daily-request-limit 500
python -m pytest -q
```

There are two reproducibility paths:

- **Audit the submitted run exactly:** keep the committed `measurements.csv`,
  `outputs/run_diagnostics.csv`, campus decisions, and validation labels, then
  run `validate`, `summarize`, and the tests. These deterministic steps
  reproduce the reported tables without paying for or resampling Gemini. On a
  clean checkout, `validate` automatically uses the frozen root
  `measurements.csv` because the working `outputs/measurements.csv` is ignored.
- **Repeat the end-to-end experiment:** fetch imagery and run `extract` with
  the recorded model and prompt version. The data flow and audit fields should
  reproduce, but individual VLM predictions may differ. Production work should
  pin a dated model release where available and preserve immutable raw response
  artifacts/checksums; temperature alone would not guarantee identical hosted
  inference.

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
correct within 25% relative error. The evaluator reports correctness within
each confidence band, confidence minus accuracy, Brier score, and the error
recall/review burden of three flagging policies.

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
area estimate, and Cerra Vista's provisional seven-portable count remain
visible in `validation_exclusions.csv`. This exclusion rule was added after the
mismatch was noticed, so both the exclusions and their values are reported
rather than being silently removed.

The manual audit is a reference set, not perfect truth. For fencing I counted
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

### How validation and calibration are calculated

- Boolean, category, and count fields are correct only when prediction and
  manual label match exactly. Counts also report mean absolute error.
- Solar area is evaluated only for a date-compatible positive label and counts
  as correct when relative error is at most 25%. No current positive area label
  is precise enough for that test, so the pipeline does not invent an area
  accuracy result.
- Each scored field becomes `correct=1` or `correct=0`. Within a confidence
  band, observed accuracy is the mean of that indicator. An `unmeasurable`
  prediction is counted as incorrect against a filled reference; abstention is
  therefore not used to inflate accuracy.
- `confidence - accuracy` is positive when the model promises more than it
  delivers and negative when it is conservative. The Brier score is the mean
  of `(confidence - correct)^2`; lower is better and confident mistakes are
  penalized most. Fixed-band expected calibration error is the count-weighted
  absolute gap across the four predeclared bands; maximum calibration error is
  the largest band gap. These complement, rather than replace, the per-band
  table because a small pooled mean gap can cancel over- and under-confidence.
- A flagging policy is useful only if it catches errors without reviewing
  everything. `validation_review_summary.csv` therefore reports error recall
  (`caught errors / all errors`), review workload (`flagged / scored fields`),
  review precision (`caught errors / flagged fields`), and accuracy/coverage
  among the fields left automatic.

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
- **Fencing:** extent and especially material are poorly observed from nadir
  imagery: thin lines can be sub-pixel, trees and shadows interrupt them, and a
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
  separate buildings, and permanent annexes/storage can look similar. All eight
  date-compatible portable references in the scored audit are zero, so 8/8
  exact accuracy tests only absence and says nothing reliable about positive
  detection. Cerra Vista's provisional positive count is disclosed but excluded
  for date/definition uncertainty. Small courts, overlapping markings, shared
  outfields, and tree cover also caused under- and over-counts.
- **Solar:** canopies can resemble rooftop arrays. Area is a bounding-box and
  fill-fraction estimate multiplied by georeferenced overview-pixel area, not a
  random model-supplied square-meter number or panel segmentation. Manual ruler
  measurements are still rough when arrays are irregular, and no area result
  has earned calibrated confidence above the review band. On date-compatible presence
  labels the model was 7/7, including Spring Lake as the only positive. That is
  too small to establish reliable positive recall, and no positive area label
  was precise enough to score. The Bertha/Pittsburgh current-reference misses
  remain visible as temporal stress tests.
- **Imagery:** NAIP vintages vary; Ridgeview Elementary used a 2017 acquisition
  and is explicitly flagged as stale.
- **Hosted VLM:** observed failures included transient 503 responses, variable
  latency, occasional truncated structured output, run-to-run variation, and
  free-tier 429 quota exhaustion. Retries and per-school failure rows keep the
  batch auditable instead of silently dropping schools.

## What I would do with 100 hours

1. **Campus geometry and imagery registry - 25 hours.** Build candidate campus
   polygons by combining school points, OSM/Overture land-use and building
   features, roads, parcels where openly licensed, and local education GIS
   layers (Overpass/OSMnx, Overture Maps, Microsoft Building Footprints,
   PostGIS/QGIS). Score connected buildings and playing areas, then review only
   disagreements in a small map UI. Store imagery item IDs and requested years
   so every prediction has a spatial and temporal boundary.
2. **A real benchmark - 25 hours.** Label 500-1,000 schools stratified by
   region, school level, rurality, imagery vintage, and campus complexity;
   deliberately oversample positive solar, portables, pools, and each fence
   type. Use two annotators plus adjudication, date-match reference sources,
   draw building/solar polygons, court/field instances, and fence segments, and
   measure inter-rater agreement. Keep geographically separate development,
   calibration, and test sets.
3. **Attribute-specific extraction - 30 hours.** First segment buildings and
   the campus mask, then run specialized detectors/segmenters for panels,
   portables, courts, and fields (for example SAM 2/Grounding DINO/YOLO or a
   fine-tuned geospatial encoder after licensing and benchmark checks). Use
   geometry/line evidence for courts and tracks. Treat fencing as a separate
   perimeter problem using higher-resolution aerial imagery and a legally
   licensed street-level source where available, not scraped consumer imagery.
   Send only uncertain or cross-model-disagreement cases to Gemini 3.8 Flash.
4. **Calibration, operations, and decision policy - 20 hours.** Benchmark the
   current Lite model, 3.8 Flash, and specialized models on the locked test set;
   fit per-attribute isotonic/conformal calibration; choose review thresholds
   from error cost and staff capacity; and test drift by state and NAIP year.
   Add batched inference, caching, resumable jobs, artifact hashes, data-version
   manifests, and a reviewer queue (Parquet/PostGIS plus DVC/MLflow or
   equivalent). Report accuracy, positive recall, MAE, calibration, coverage,
   latency, cost, and review burden together.

## Time spent and AI use

Approximate elapsed working time was **5 hours 40 minutes**:

- 20 minutes understanding the task and measurement definitions;
- 50 minutes collaboratively designing the approach with ChatGPT, generating
  the initial code, and checking the design;
- 30 minutes opening the CCD/candidate links and adjudicating every campus;
- 60 minutes labeling and manually verifying eight schools, with ChatGPT and
  Claude used as second opinions for unfamiliar aerial features such as
  portable classrooms; uncertain/date-mismatched cases were left blank;
- 90 minutes adding guardrails and observability, fixing bugs, revising prompts,
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
