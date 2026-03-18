"""Add new hearings to expand coverage across committees and topics."""

import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from process_hearing import process_hearing

# Curated list of diverse, substantive hearings to add
# Picking high-interest topics across different committees and both chambers
NEW_HEARINGS = [
    # Senate - AI copyright hearing (very timely)
    {"event_id": "337816", "chamber": "senate",
     "desc": "AI industry's mass ingestion of copyrighted works"},

    # Senate - Judiciary: Big Tech
    {"event_id": "337921", "chamber": "senate",
     "desc": "Big Tech and silencing Americans part 2"},

    # Senate - Banking: digital assets
    {"event_id": "337855", "chamber": "senate",
     "desc": "Stakeholder perspectives on Federal oversight of digital commodities"},

    # Senate - Commerce: AI potential
    {"event_id": "337974", "chamber": "senate",
     "desc": "AI's potential to support patients, workers, children"},

    # House - AI hearing
    {"event_id": "119423", "chamber": "house",
     "desc": "Assessing America's AI Action Plan"},

    # House - Oversight of DOJ
    {"event_id": "119213", "chamber": "house",
     "desc": "Oversight of the Department of Justice"},

    # House - Education: Building an AI-Ready America
    {"event_id": "119193", "chamber": "house",
     "desc": "Building an AI-Ready America"},

    # House - Health insurance CEOs hearing
    {"event_id": "119548", "chamber": "house",
     "desc": "Full Committee Hearing with Health Insurance CEOs"},
]

if __name__ == "__main__":
    # First, re-process existing hearings that need base.en upgrade
    DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "hearings")
    existing_needs_upgrade = []

    for entry in os.listdir(DATA_DIR):
        hearing_dir = os.path.join(DATA_DIR, entry)
        if not os.path.isdir(hearing_dir):
            continue
        transcript_path = os.path.join(hearing_dir, "transcript.json")
        if not os.path.exists(transcript_path):
            continue
        with open(transcript_path) as f:
            t = json.load(f)
        source = t.get("source", "unknown")
        if "base" not in source:
            # Need to figure out chamber
            info_path = os.path.join(hearing_dir, "info.json")
            if os.path.exists(info_path):
                with open(info_path) as f:
                    info = json.load(f)
                chamber = info.get("chamber", "house").lower()
                existing_needs_upgrade.append({"event_id": entry, "chamber": chamber})

    total = len(existing_needs_upgrade) + len(NEW_HEARINGS)
    done = 0

    if existing_needs_upgrade:
        print(f"=== Re-processing {len(existing_needs_upgrade)} existing hearings with base.en ===\n")
        for h in existing_needs_upgrade:
            done += 1
            print(f"[{done}/{total}] Re-processing {h['event_id']} ({h['chamber']})...")
            try:
                process_hearing(h["event_id"], h["chamber"], force=True)
            except Exception as e:
                print(f"  ERROR: {e}")
            print()

    print(f"\n=== Adding {len(NEW_HEARINGS)} new hearings ===\n")
    for h in NEW_HEARINGS:
        done += 1
        print(f"[{done}/{total}] Processing {h['event_id']}: {h['desc'][:60]}...")
        try:
            process_hearing(h["event_id"], h["chamber"])
        except Exception as e:
            print(f"  ERROR: {e}")
        print()

    print(f"\nDone! Processed {done} hearings total.")
