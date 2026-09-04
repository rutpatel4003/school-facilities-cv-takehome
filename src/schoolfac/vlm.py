from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import time
from typing import Any

from .schema import SchoolVisualAssessment


@dataclass
class VLMUsage:
    prompt_tokens: int | None = None
    output_tokens: int | None = None
    thinking_tokens: int | None = None
    total_tokens: int | None = None

    @property
    def billable_output_tokens(self) -> int | None:
        if self.output_tokens is None and self.thinking_tokens is None:
            return None
        return int(self.output_tokens or 0) + int(self.thinking_tokens or 0)


@dataclass
class ExtractionResult:
    assessment: SchoolVisualAssessment
    usage: VLMUsage
    model: str


PROMPT_VERSION = "2026-09-03-solar-roof-proof-v2"


PROMPT_TEMPLATE = """
You are measuring physical facilities on ONE U.S. public-school campus from
one dated aerial image, one centered campus-detail crop, and four enlarged
quadrants of that same image.

School: {school_name}
District: {district}
City/state: {city}, {state}
School level: {level}
Enrollment: {enrollment}
Imagery date: {imagery_date}
Approximate pixel area: {pixel_area_m2:.4f} square meters per overview pixel

Use ONLY visible evidence. Do not infer a feature merely because a school of
this type would normally have one. Do not count clearly off-campus facilities.
If the campus boundary itself is uncertain, reflect that in observability and
explain it in evidence/global notes.

First assess campus-boundary observability separately from crop coverage.
campus_coverage_visible is the fraction of the apparent candidate campus inside
the image; it is NOT proof that the campus perimeter or ownership is known.
Set campus_boundary_observability high only when the target-school parcel or
compound can be distinguished around most edges. Shared campuses, adjoining
parks, and facilities separated by public roads should trigger boundary
ambiguity unless attribution is visually well supported.

The reviewed target-school coordinate is at the center of the FULL_OVERVIEW.
Use the school compound around that anchor to establish campus context.
Use FULL_OVERVIEW for campus-boundary and ownership context. CENTER_DETAIL is
an enlarged central crop from the same acquisition, not a different date; use
it to inspect mounting context, court markings, buildings, and visible fence
segments without losing the central campus as a whole.

Attribute a facility to the target school only when the imagery reasonably
supports that it belongs to the same campus. Nearby parks, residences,
businesses, other schools, district facilities, or unrelated parcels should
not be counted merely because they fall inside the crop.

Spatial continuity, internal roads/walkways, and apparent integration with
the school compound are useful evidence, but are not proof of ownership.
If attribution remains uncertain, mark ambiguity and reduce observability
rather than guessing.

Operational definitions for consistency:
- Rooftop solar: photovoltaic panels visibly mounted on school-building roofs.
  Do NOT count ground-mounted arrays, parking-lot solar canopies, solar
  carports, or covered play/drop-off structures.

  Apply this proof-gated procedure separately to EVERY visible solar candidate
  before deciding solar.present:
  1. Locate the candidate in FULL_OVERVIEW and inspect it again in
     CENTER_DETAIL or the relevant quadrant. Do not count the same array twice.
  2. Trace the boundary of the surface supporting the panels. A rooftop claim
     requires a coherent building-roof footprint, not merely a candidate that
     touches, overlaps, aligns with, or runs parallel to a building in a nadir
     view.
  3. Set mounting_context to rooftop ONLY when the entire panel footprint is
     visibly contained inside one coherent building-roof polygon and roof
     surface or roof edges can be followed around the candidate in at least two
     views. A dark rectangular grid by itself is not proof of rooftop mounting.
  4. Long or narrow panel strips beside a building or along pavement, a
     courtyard, a play area, a drop-off lane, or parking are common canopy
     geometry. If any view shows pavement, parking markings, vehicles,
     playground surface, open space, or support columns below or immediately
     around such a strip, classify it as canopy even if it appears attached to
     the building.
  5. If the roof boundary cannot be traced around the candidate in at least two
     views, or the views conflict about its supporting surface, use uncertain,
     never rooftop. Prefer an honest unresolved result to unsupported rooftop
     evidence.

  After classifying every candidate, set solar.present to true ONLY if at least
  one candidate passes the rooftop proof above. Set it to false when all visible
  candidates are confidently canopy/ground and the observable school roofs
  contain no supported rooftop candidate. Set it to null when a plausible
  candidate remains unresolved or the relevant roof area is not observable.
  In solar.evidence, enumerate every candidate and state the roof-boundary and
  support-surface evidence used for its mounting_context. For every candidate,
  including excluded candidates, return mounting_context
  (rooftop/canopy/ground/uncertain), its observability, and a non-overlapping
  bounding box on the FULL_OVERVIEW coordinate system, normalized 0..1000 in
  x/y. Estimate the fraction of that rectangle truly occupied by panels. The
  code will exclude non-rooftop candidates and convert only supported rooftop
  boxes to square meters.
- Portable/modular classrooms: distinct detached modular classroom-type
  buildings. Do not count an obvious storage shed. Construction trailers,
  temporary site offices, material/equipment containers, and repeated white
  objects inside an active construction or staging area are NOT portable
  classrooms. A counted portable should look like a detached classroom module
  and be integrated with campus pedestrian circulation rather than construction
  staging. If use is ambiguous, count only when the classroom interpretation is
  more plausible than storage/construction and mark ambiguity; otherwise use
  null rather than inflating the count.
- Fence extent (prototype convention): full means roughly >=80% of the apparent
  campus perimeter is controlled by fence/wall/gates; partial means meaningful
  sections but <80%; none means little/no perimeter barrier. Use unmeasurable
  when the perimeter cannot be judged. A value of none requires high campus-
  boundary observability and direct visibility of most perimeter segments;
  failure to see a thin fence at this scale is not evidence of absence. A
  continuous narrow line, repeated posts, gate breaks, or a consistent linear
  shadow can support fence EXTENT when it traces the apparent campus edge. A
  visibly wide solid barrier with thickness or a solid shadow can support a
  wall classification. A thin line alone does NOT establish chain-link versus
  wrought iron. Fence TYPE is stricter: return unknown unless material/form is
  genuinely visible.
- Running track: recognizable running oval/track.
- Full-size sports field: a field large enough for organized school field sport;
  do not count tiny practice lawns. Count independently usable physical field
  surfaces, not every sport layout. Do not double-count one multi-use surface
  because soccer/football markings overlap or baseball outfields share it.
- Hard courts: count physical courts that could host simultaneous games. Use
  complete playable markings and layout, not individual hoops, faded fragments,
  or every overlapping game stencil. Do not count one fenced complex as one
  court when several distinct playable courts are clearly marked.
- Pool: identifiable swimming pool.

Observability means how clearly the IMAGE supports the field, not how confident
language sounds: high=clear direct evidence; medium=visible with some ambiguity;
low=weak/partial/occluded; none=not measurable.

For absence claims, require that the relevant campus area is actually visible.
A missing feature outside the frame or under heavy occlusion is not evidence of
absence.
""".strip()


class GeminiExtractor:
    """One-call, multi-image Gemini extractor with typed structured output."""

    prompt_version = PROMPT_VERSION

    def __init__(self, api_key: str, model: str):
        if not api_key:
            raise ValueError("GEMINI_API_KEY is missing.")
        from google import genai
        self._genai = genai
        self.client = genai.Client(api_key=api_key)
        self.model = model

    @staticmethod
    def _part_from_file(types, path: Path):
        suffix = path.suffix.lower()
        mime = "image/png" if suffix == ".png" else "image/jpeg"
        return types.Part.from_bytes(data=path.read_bytes(), mime_type=mime)

    def extract(
        self,
        school: dict,
        views: list[tuple[str, Path]],
        imagery_meta: dict,
        retries: int = 4,
    ) -> ExtractionResult:
        from google.genai import types

        prompt = PROMPT_TEMPLATE.format(
            school_name=school["school_name"],
            district=school["district"],
            city=school["city"],
            state=school["state"],
            level=school["level"],
            enrollment=school["enrollment_2024"],
            imagery_date=imagery_meta["acquisition_date"],
            pixel_area_m2=float(imagery_meta["pixel_area_m2"]),
        )

        contents: list[Any] = [prompt]
        for label, path in views:
            contents.append(f"IMAGE VIEW: {label}")
            contents.append(self._part_from_file(types, Path(path)))

        last_error: Exception | None = None

        for attempt in range(1, retries + 1):

            print(
                f"    Gemini attempt {attempt}/{retries}...",
                flush=True,
            )

            attempt_start = time.perf_counter()

            try:
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=SchoolVisualAssessment,
                        max_output_tokens=5000,
                    ),
                )

                attempt_seconds = time.perf_counter() - attempt_start

                print(
                    f"    Gemini attempt {attempt}/{retries}: "
                    f"response received in {attempt_seconds:.1f}s",
                    flush=True,
                )

                parsed = response.parsed

                if isinstance(parsed, SchoolVisualAssessment):
                    assessment = parsed

                elif parsed is not None:
                    assessment = SchoolVisualAssessment.model_validate(
                        parsed
                    )

                else:
                    assessment = (
                        SchoolVisualAssessment.model_validate_json(
                            response.text
                        )
                    )

                usage_meta = getattr(
                    response,
                    "usage_metadata",
                    None,
                )

                usage = VLMUsage(
                    prompt_tokens=getattr(
                        usage_meta,
                        "prompt_token_count",
                        None,
                    ),
                    output_tokens=getattr(
                        usage_meta,
                        "candidates_token_count",
                        None,
                    ),
                    thinking_tokens=getattr(
                        usage_meta,
                        "thoughts_token_count",
                        None,
                    ),
                    total_tokens=getattr(
                        usage_meta,
                        "total_token_count",
                        None,
                    ),
                )

                return ExtractionResult(
                    assessment=assessment,
                    usage=usage,
                    model=self.model,
                )

            except Exception as exc:

                attempt_seconds = time.perf_counter() - attempt_start
                last_error = exc

                print(
                    f"    Gemini attempt {attempt}/{retries}: "
                    f"failed after {attempt_seconds:.1f}s",
                    flush=True,
                )

                error_text = str(exc)

                if len(error_text) > 500:
                    error_text = error_text[:500] + "..."

                print(
                    f"      {type(exc).__name__}: {error_text}",
                    flush=True,
                )

                if attempt < retries:
                    wait_seconds = 6 * (2 ** (attempt - 1))

                    print(
                        f"    Retrying in {wait_seconds}s...",
                        flush=True,
                    )

                    time.sleep(wait_seconds)


        raise RuntimeError(
            f"VLM extraction failed after {retries} attempts: "
            f"{last_error}"
        )


class MockExtractor:
    """Dry-run provider that proves the pipeline mechanics without pretending accuracy."""

    model = "mock-no-vision"
    prompt_version = "mock-no-vision-v1"

    def extract(self, school: dict, views, imagery_meta, retries: int = 1) -> ExtractionResult:
        assessment = SchoolVisualAssessment.model_validate(
            {
                "campus_coverage_visible": 0.0,
                "campus_boundary_observability": "none",
                "campus_boundary_ambiguity": True,
                "overall_image_quality": "poor",
                "tree_occlusion": "high",
                "solar": {
                    "present": None,
                    "present_observability": "none",
                    "area_observability": "none",
                    "arrays": [],
                    "ambiguity": True,
                    "evidence": "Mock provider: no visual inference performed.",
                },
                "portables": {
                    "count": None,
                    "observability": "none",
                    "ambiguity": True,
                    "evidence": "Mock provider: no visual inference performed.",
                },
                "fence": {
                    "extent": "unmeasurable",
                    "extent_observability": "none",
                    "dominant_type": "unknown",
                    "type_observability": "none",
                    "ambiguity": True,
                    "evidence": "Mock provider: no visual inference performed.",
                },
                "athletics": {
                    "track_present": None,
                    "track_observability": "none",
                    "sports_fields_count": None,
                    "fields_observability": "none",
                    "hard_courts_count": None,
                    "courts_observability": "none",
                    "pool_present": None,
                    "pool_observability": "none",
                    "ambiguity": True,
                    "evidence": "Mock provider: no visual inference performed.",
                },
                "global_notes": "Dry-run only.",
            }
        )
        return ExtractionResult(assessment=assessment, usage=VLMUsage(), model=self.model)
