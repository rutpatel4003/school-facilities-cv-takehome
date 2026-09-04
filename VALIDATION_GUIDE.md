# Validation guide

This protocol is intentionally conservative. A blank ground-truth cell is a
valid result when the saved imagery cannot support a label; it is better than a
guess. Use the model predictions only after you finish a school's labels so the
model does not anchor your judgment.

Every scored label must describe the facilities visible on the prediction
row's `imagery_date`. Current or undated web/Google Maps imagery may document a
later change, but it must not overwrite a historical NAIP label. If such a
comparison is useful as a stress test, retain its value, list the field in
`excluded_fields` (semicolon-separated), and explain why in
`evaluation_exclusion_reason`. The evaluator saves these rows separately rather
than silently discarding them.

## 1. Define the campus before labeling facilities

Use the target coordinate at the image center as an anchor, not as a boundary.
Sketch or describe the **apparent campus** using visible evidence:

- include the school buildings, internal walkways, drop-off/parking areas, and
  contiguous play or athletic areas that appear integrated with the compound;
- do not automatically include a neighboring park, another school, district
  office, or facility across a public road;
- where ownership is unresolved, name the feature in `ground_truth_notes` and
  leave any affected count blank.

Record one of these boundary judgments in the note:

- `boundary high`: most campus edges and feature ownership are clear;
- `boundary medium`: the main compound is clear but one shared edge/facility is
  uncertain;
- `boundary low`: the target extent cannot be separated defensibly.

The pipeline crop is a center plus a square radius; it is not a parcel polygon.
That is an explicit prototype limitation, not something the labels should hide.

## 2. Label perimeter fencing

Use the assignment convention consistently:

- `full`: roughly 80% or more of the apparent perimeter has fencing, wall, or
  controlled gates;
- `partial`: meaningful controlled sections, but less than roughly 80%;
- `none`: most perimeter segments are visible and clearly lack a barrier;
- blank: the perimeter or thin fence line cannot be judged from available
  imagery.

Do not turn “I cannot see a fence” into `none` when image resolution, trees,
shadows, or an uncertain boundary could hide it. Fence material is a separate
label: leave `fence_type` blank unless chain-link, ornamental/wrought metal, wall,
or another dominant type is genuinely identifiable. Use `wrought-iron` as the
canonical ornamental-metal label. A house, hedge, tree line, road, slope, or
other natural/land-use edge may help locate the campus boundary, but it is not
fencing. A playground or ball-field backstop also does not prove the campus
perimeter is fenced. Street View is optional, not required; inaccessible
coverage weakens the reference label and is a documented limitation.

## 3. Label the other fields

- Rooftop solar excludes parking canopies/carports and ground arrays. If panel
  mounting is uncertain, leave presence/area blank.
- Count distinct detached portable buildings, not classrooms, roof bays, or
  factory-built modules within one joined building. Count only when a modular
  classroom interpretation is more plausible than a permanent annex, storage,
  or construction structure. If seams/shadows do not clearly separate physical
  footprints, record the ambiguity and leave the primary label blank.
- Count a hard court as a physical surface that could host a simultaneous game;
  do not count every hoop, faded fragment, or overlapping game stencil.
- Count only facilities attributable to the apparent target campus.

## 4. Record how each school entered the audit

`prepare-validation` creates eight `seeded_random` rows using a fixed seed and
a 3-primary/2-middle/3-high mix. The submitted label file also contains Spring
Lake Heights (`341560004108`) with
`sample_role=targeted_solar_challenge`. I added it deliberately after seeing
visible rooftop panels so the audit would contain a positive case. It is useful
for testing solar recall, but it is not part of the random sample.

Spring Lake's solar presence is scored. Its 1,800 m2 area is retained but
excluded because it is a rough visual estimate without a ruler or polygon and
cannot fairly support a 25% error tolerance.

Cerra Vista has a provisional value of seven portable structures based on five
roof-separated rectangles along the north edge and two near the center in
current/undated Google imagery. It is retained in the label file but excluded
from the primary score: the source is not date-matched to the 2022 NAIP input,
and the visible seams may divide modules rather than distinct buildings. This
keeps the possible model miss visible without presenting uncertain evidence as
ground truth.

## 5. Keep the validation claim modest

The original sample has eight schools and the submitted audit has nine. Wells,
Beverly Hills, and Cerra Vista were used directly while improving the method.
The other five seeded predictions were later opened during failure analysis and
model comparison. Therefore this is a transparent development audit, not an
unseen test set or an unbiased estimate for all U.S. schools. Do not call
unresolved cells errors or silently drop them: evaluation is conditional on
observable, date-compatible labels.

After labeling, run:

```bash
python run.py validate --development-school-id 060001909278 --development-school-id 060483000471 --development-school-id 061734009378
```

Use `validation_overview.csv` for accuracy, Brier score, fixed-band expected
and maximum calibration error; `calibration_summary.csv` for each confidence
band and its contributing-school count;
`validation_sample_summary.csv` for seeded versus targeted results,
`validation_summary.csv` for field results and positive/negative or
zero/nonzero label support; `validation_review_summary.csv` for flag recall,
workload, and accuracy among unflagged fields; and
`validation_exclusions.csv` for every retained but unscored comparison.
