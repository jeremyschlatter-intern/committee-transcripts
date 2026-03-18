"""Congress.gov API client for discovering committee hearings and meetings."""

import requests
import json
import os
from datetime import datetime, timedelta

API_KEY = "CONGRESS_API_KEY"
BASE_URL = "https://api.congress.gov/v3"


def get_recent_committee_meetings(congress=119, chamber=None, limit=20, offset=0):
    """Fetch recent committee meetings from Congress.gov API."""
    if chamber:
        url = f"{BASE_URL}/committee-meeting/{congress}/{chamber}"
    else:
        url = f"{BASE_URL}/committee-meeting/{congress}"

    params = {
        "api_key": API_KEY,
        "limit": limit,
        "offset": offset,
        "format": "json",
    }

    resp = requests.get(url, params=params)
    resp.raise_for_status()
    return resp.json()


def get_committee_meeting_detail(congress, chamber, event_id):
    """Get detailed info about a specific committee meeting."""
    url = f"{BASE_URL}/committee-meeting/{congress}/{chamber}/{event_id}"
    params = {"api_key": API_KEY, "format": "json"}
    resp = requests.get(url, params=params)
    resp.raise_for_status()
    return resp.json()


def get_hearings(congress=119, chamber=None, limit=20, offset=0):
    """Fetch hearing records."""
    if chamber:
        url = f"{BASE_URL}/hearing/{congress}/{chamber}"
    else:
        url = f"{BASE_URL}/hearing/{congress}"

    params = {
        "api_key": API_KEY,
        "limit": limit,
        "offset": offset,
        "format": "json",
    }

    resp = requests.get(url, params=params)
    resp.raise_for_status()
    return resp.json()


def get_hearing_detail(congress, chamber, jacket_number):
    """Get detailed info about a specific hearing."""
    url = f"{BASE_URL}/hearing/{congress}/{chamber}/{jacket_number}"
    params = {"api_key": API_KEY, "format": "json"}
    resp = requests.get(url, params=params)
    resp.raise_for_status()
    return resp.json()


def extract_video_urls(meeting_detail):
    """Extract video URLs from a committee meeting detail response."""
    videos = []
    meeting = meeting_detail.get("committeeMeeting", {})

    for video in meeting.get("videos", []):
        url = video.get("url", "")
        title = video.get("title", "")
        videos.append({"url": url, "title": title})

    return videos


def extract_meeting_info(meeting_detail):
    """Extract key meeting information into a clean dict."""
    m = meeting_detail.get("committeeMeeting", {})

    committees = []
    for c in m.get("committees", []):
        committees.append({
            "name": c.get("name", ""),
            "systemCode": c.get("systemCode", ""),
            "chamber": c.get("chamber", ""),
        })

    witnesses = []
    for w in m.get("witnesses", []):
        witnesses.append({
            "name": w.get("name", ""),
            "position": w.get("position", ""),
            "organization": w.get("organization", ""),
        })

    return {
        "eventId": m.get("eventId"),
        "title": m.get("title", ""),
        "date": m.get("date", ""),
        "chamber": m.get("chamber", ""),
        "congress": m.get("congress"),
        "type": m.get("type", ""),
        "meetingStatus": m.get("meetingStatus", ""),
        "location": m.get("location", {}),
        "committees": committees,
        "witnesses": witnesses,
        "videos": extract_video_urls(meeting_detail),
    }


def discover_recent_hearings(days_back=30, chamber=None):
    """Discover recent hearings with video available.

    Returns list of meeting info dicts that have video URLs.
    """
    meetings_with_video = []
    offset = 0
    limit = 50
    cutoff = datetime.now() - timedelta(days=days_back)

    while True:
        try:
            data = get_recent_committee_meetings(
                congress=119, chamber=chamber, limit=limit, offset=offset
            )
        except requests.HTTPError as e:
            print(f"API error at offset {offset}: {e}")
            break

        meetings = data.get("committeeMeetings", [])
        if not meetings:
            break

        for meeting_summary in meetings:
            event_id = meeting_summary.get("eventId")
            mchamber = meeting_summary.get("chamber", chamber or "")

            # Check date
            date_str = meeting_summary.get("date", "")
            if date_str:
                try:
                    meeting_date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                    if meeting_date.replace(tzinfo=None) < cutoff:
                        continue
                except (ValueError, TypeError):
                    pass

            if not event_id:
                continue

            try:
                detail = get_committee_meeting_detail(119, mchamber.lower(), event_id)
                info = extract_meeting_info(detail)
                if info["videos"]:
                    meetings_with_video.append(info)
                    print(f"  Found: {info['title'][:80]} ({len(info['videos'])} videos)")
            except requests.HTTPError:
                continue

        offset += limit
        if offset > 500:  # Safety limit
            break

    return meetings_with_video


if __name__ == "__main__":
    print("Discovering recent House committee meetings with video...")
    meetings = discover_recent_hearings(days_back=60, chamber="house")
    print(f"\nFound {len(meetings)} meetings with video")
    for m in meetings[:5]:
        print(f"  - {m['date']}: {m['title'][:80]}")
        for v in m['videos']:
            print(f"    Video: {v['url']}")
