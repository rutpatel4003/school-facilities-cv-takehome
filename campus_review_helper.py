"""Generate links for reviewing campus coordinates."""

from pathlib import Path
import csv
import sys

DATA_DIR = Path(__file__).resolve().parent / "data"
REVIEW_CSV = DATA_DIR / "campus_review.csv"


def maps_satellite_link(lat, lon, zoom=18):
    return (
        f"https://www.google.com/maps?"
        f"q={lat},{lon}&z={zoom}&t=k"
    )


def suggest_decision(row):
    distance = row.get("candidate_distance_m")
    similarity = row.get("candidate_name_similarity")

    if distance is None or distance == "":
        return "CHECK", "No geocoder candidate found; visually verify the CCD point."

    distance = float(distance)
    similarity = float(similarity) if similarity else 0

    if distance < 80 and similarity > 70:
        reason = (
            f"Sources agree ({distance:.0f}m apart, {similarity:.0f}% name match). "
            "Quick visual confirm."
        )
        return "LIKELY_OK", reason
    if distance < 200 and similarity > 85:
        reason = (
            f"Close match ({distance:.0f}m, {similarity:.0f}% name). "
            "Quick visual confirm."
        )
        return "LIKELY_OK", reason
    if distance > 500:
        return "CHECK", f"⚠ {distance:.0f}m apart — check both locations."
    if similarity < 50:
        return "CHECK", f"⚠ Low name match ({similarity:.0f}%) — check candidate."
    return "CHECK", f"Moderate gap ({distance:.0f}m, {similarity:.0f}%). Worth a quick look."


def print_review_table():
    if not REVIEW_CSV.exists():
        print(f"ERROR: {REVIEW_CSV} not found.")
        print("Run 'python run.py prepare-campus' first.")
        sys.exit(1)

    with open(REVIEW_CSV) as f:
        rows = list(csv.DictReader(f))

    auto_ok = 0
    needs_check = 0

    print(f"\n{'='*100}")
    print(f"CAMPUS REVIEW HELPER — {len(rows)} schools")
    print(f"{'='*100}\n")

    for i, row in enumerate(rows, 1):
        sid = row["school_id"]
        name = row["school_name"]
        existing_decision = row.get("decision", "").strip()

        ccd_lat = row["ccd_latitude"]
        ccd_lon = row["ccd_longitude"]
        cand_lat = row.get("candidate_latitude", "")
        cand_lon = row.get("candidate_longitude", "")
        distance = row.get("candidate_distance_m", "")

        suggestion, reason = suggest_decision(row)

        status = "✓ DONE" if existing_decision else suggestion

        if not existing_decision:
            if suggestion == "LIKELY_OK":
                auto_ok += 1
            else:
                needs_check += 1

        print(f"[{i:2d}] {name}")
        print(f"     ID: {sid}")
        print(f"     Status: {status}  |  {reason}")
        print(f"     CCD link:       {maps_satellite_link(ccd_lat, ccd_lon)}")
        if cand_lat and cand_lon:
            print(f"     Candidate link: {maps_satellite_link(cand_lat, cand_lon)}")
            cand_name = row.get("candidate_display_name", "")
            if cand_name:
                print(f"     Candidate name: {cand_name[:80]}")
        print()

    print(f"{'='*100}")
    print(
        f"SUMMARY: {auto_ok} sources broadly agree (still verify), "
        f"{needs_check} need careful checking"
    )
    print(f"{'='*100}")
    print()
    print("HOW TO FILL campus_review.csv:")
    print("  1. Open the CSV in Excel/Google Sheets/any editor")
    print("  2. For EVERY school, click the CCD satellite link and confirm the point")
    print("     is visually on the school campus. Then set the 'decision' column:")
    print("     - 'ccd'       → the federal coordinate is on the campus")
    print("     - 'candidate' → the Nominatim geocoder point is better")
    print("     - 'manual'    → neither is right; fill manual_latitude/manual_longitude")
    print("  3. For large campuses, increase chip_half_size_m (default 350m)")
    print("  4. Optionally add notes explaining corrections")
    print()
    print("TIPS:")
    print("  - LIKELY_OK schools still need a visual check — agreement is not proof")
    print("  - If the CCD point is on a house/office/road, try the candidate link")
    print("  - For urban schools (Bronx, Pittsburgh, Dallas): campus = the building itself")
    print("  - For rural schools: campus might be spread out, consider larger chip_half_size_m")


def write_html():
    if not REVIEW_CSV.exists():
        print(f"ERROR: {REVIEW_CSV} not found. Run 'python run.py prepare-campus' first.")
        sys.exit(1)

    with open(REVIEW_CSV) as f:
        rows = list(csv.DictReader(f))

    html_path = DATA_DIR / "campus_review.html"
    with open(html_path, "w") as out:
        out.write("<!DOCTYPE html><html><head><title>Campus Review</title>")
        out.write("<style>body{font-family:monospace;margin:20px}table{border-collapse:collapse}")
        out.write("td,th{border:1px solid #ccc;padding:6px 10px;text-align:left}")
        out.write("tr:nth-child(even){background:#f5f5f5}")
        out.write(".warn{background:#fff3cd}.ok{background:#d4edda}</style></head><body>")
        out.write(f"<h2>Campus Review — {len(rows)} schools</h2>")
        out.write("<table><tr><th>#</th><th>School</th><th>Distance</th>")
        out.write("<th>Suggestion</th><th>CCD Map</th><th>Candidate Map</th></tr>")

        for i, row in enumerate(rows, 1):
            suggestion, reason = suggest_decision(row)
            cls = "warn" if suggestion == "CHECK" else "ok"
            ccd_link = maps_satellite_link(row["ccd_latitude"], row["ccd_longitude"])
            cand_lat = row.get("candidate_latitude", "")
            cand_lon = row.get("candidate_longitude", "")
            cand_link = maps_satellite_link(cand_lat, cand_lon) if cand_lat and cand_lon else "—"
            dist = row.get("candidate_distance_m", "")
            dist_str = f"{float(dist):.0f}m" if dist and dist != "" else "—"

            out.write(f'<tr class="{cls}"><td>{i}</td>')
            out.write(f'<td><b>{row["school_name"]}</b><br>{row["school_id"]}</td>')
            out.write(f'<td>{dist_str}</td>')
            out.write(f'<td>{reason}</td>')
            out.write(f'<td><a href="{ccd_link}" target="_blank">CCD ↗</a></td>')
            link_html = (
                f'<a href="{cand_link}" target="_blank">Candidate ↗</a>'
                if cand_lat
                else "—"
            )
            out.write(f'<td>{link_html}</td></tr>')

        out.write("</table></body></html>")

    print(f"Wrote {html_path}")
    print("Open it in your browser, click links, then fill campus_review.csv decisions.")


if __name__ == "__main__":
    if "--html" in sys.argv:
        write_html()
    else:
        print_review_table()
