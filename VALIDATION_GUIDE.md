# Validation guide

Leave a ground-truth cell blank when the available evidence cannot support an
answer. Finish a school's labels before viewing its predictions so the model
does not influence the manual judgment.

Every scored label must describe the facilities visible on the prediction
row's `imagery_date`. Newer or undated Google imagery may show that a facility
changed, but it should not be used to mark an older NAIP prediction wrong. Keep
such comparisons in `excluded_fields` and explain the date mismatch; the
evaluator reports them separately.

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

Cerra Vista has seven detached portable buildings in the dated 2022 NAIP image:
five along the north edge and two near the center. Low contrast makes the roof
gaps difficult to see, but the seven footprints are visible; current Google
imagery shows the same arrangement. The label is therefore scored. The model's
prediction of zero is a high-confidence error and is important evidence that
portable detection needs more positive examples.

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

The output files answer different questions:

- `validation_observations.csv`: every prediction-label comparison and whether
  it was correct;
- `validation_summary.csv`: accuracy and count error for each field;
- `calibration_summary.csv`: whether answers labeled 0.9, 0.7, 0.4, or 0.1 were
  actually correct at about those rates;
- `validation_overview.csv`: overall accuracy plus ECE and Brier score. ECE
  summarizes confidence-band gaps; Brier score penalizes confident mistakes;
- `validation_review_summary.csv`: how many fields a rule sends to a person,
  how many errors it catches, and accuracy among fields left automatic;
- `validation_sample_summary.csv`: seeded rows versus the added solar case;
- `validation_exclusions.csv`: date-mismatched or insufficiently precise
  references that are disclosed but not scored.

The per-band counts are the easiest calibration result to interpret. ECE and
Brier score are included as compact standard summaries, not as replacements for
those counts.
