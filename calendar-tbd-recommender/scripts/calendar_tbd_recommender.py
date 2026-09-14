#!/usr/bin/env python3
"""
Calendar TBD Venue Recommender
Generic core engine for scanning Google Calendar events with placeholder locations,
resolving travel/transit context, matching against a curated taste graph,
and patching confirmed venues back to Google Calendar.
"""

import os
import sys
import json
import re
import argparse
import datetime
from typing import List, Dict, Any, Optional, Tuple

# Optional YAML support with JSON fallback
try:
    import yaml
    HAVE_YAML = True
except ImportError:
    HAVE_YAML = False


def load_taste_graph(config_path: str) -> Dict[str, Any]:
    """Loads taste graph from YAML or JSON."""
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Venues config not found: {config_path}")
    
    with open(config_path, "r", encoding="utf-8") as f:
        content = f.read()

    if config_path.endswith(".json"):
        return json.loads(content)
    
    if HAVE_YAML:
        return yaml.safe_load(content)
    
    # Minimal fallback parser for simple key-value/json if yaml not installed
    try:
        return json.loads(content)
    except Exception:
        raise RuntimeError("PyYAML is required to parse .yaml config files. Install with: pip install pyyaml")


def get_calendar_service(credentials_path: Optional[str] = None):
    """Authenticates and returns Google Calendar v3 service object."""
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    creds_path = credentials_path or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not creds_path or not os.path.exists(creds_path):
        raise FileNotFoundError(f"Valid Google credentials required. Specify --credentials or $GOOGLE_APPLICATION_CREDENTIALS.")

    scopes = ["https://www.googleapis.com/auth/calendar"]
    creds = service_account.Credentials.from_service_account_file(creds_path, scopes=scopes)
    return build("calendar", "v3", credentials=creds)


class TravelContextResolver:
    """Detects flight and transit events to build a daily city presence map."""

    # Airport / city keyword mapping
    CITY_PATTERNS = [
        (r"\b(KUL|Kuala Lumpur|KL)\b", "Kuala Lumpur"),
        (r"\b(SIN|Singapore)\b", "Singapore"),
        (r"\b(PEN|Penang)\b", "Penang"),
        (r"\b(MEL|Melbourne)\b", "Melbourne"),
        (r"\b(SYD|Sydney)\b", "Sydney"),
        (r"\b(NRT|HND|Tokyo)\b", "Tokyo"),
        (r"\b(LHR|London)\b", "London"),
        (r"\b(SFO|San Francisco)\b", "San Francisco"),
        (r"\b(AMS|Amsterdam)\b", "Amsterdam"),
    ]

    def __init__(self, default_city: str = "Singapore"):
        self.default_city = default_city
        self.city_ranges: List[Tuple[datetime.date, datetime.date, str]] = []

    def ingest_events(self, events: List[Dict[str, Any]]):
        """Scans flight and travel events to establish date ranges in foreign cities."""
        flight_regex = re.compile(r"(Flight to|Airport transit|taking off|\b[A-Z0-9]{2,3}\s*\d{2,4}\b|→|->)", re.IGNORECASE)

        for ev in events:
            summary = ev.get("summary", "")
            loc = ev.get("location", "")
            full_text = f"{summary} {loc}"

            # Check if this is a flight or transit event
            if flight_regex.search(full_text):
                # Detect arrival destination
                dest_city = None
                # Check arrow transit patterns: e.g. SIN → KUL or SIN -> KUL
                arrow_match = re.search(r"[A-Z]{3}\s*(?:→|->)\s*([A-Z]{3})", full_text, re.IGNORECASE)
                if arrow_match:
                    arr_code = arrow_match.group(1).upper()
                    for pat, city in self.CITY_PATTERNS:
                        if re.search(pat, arr_code, re.IGNORECASE):
                            dest_city = city
                            break

                if not dest_city:
                    # Check "Flight to <City>"
                    to_match = re.search(r"Flight to\s+([A-Za-z\s]+)", full_text, re.IGNORECASE)
                    if to_match:
                        target = to_match.group(1).strip()
                        for pat, city in self.CITY_PATTERNS:
                            if re.search(pat, target, re.IGNORECASE):
                                dest_city = city
                                break

                if dest_city:
                    ev_date = self._extract_date(ev)
                    if ev_date:
                        # Record a provisional destination window of 7 days (or until next return flight)
                        self.city_ranges.append((ev_date, ev_date + datetime.timedelta(days=7), dest_city))

            # Check all-day location blocks like "SK CK in Penang" or "KMS in KL"
            in_city_match = re.search(r"\bin\s+([A-Za-z\s]+)", summary, re.IGNORECASE)
            if in_city_match:
                target = in_city_match.group(1).strip()
                for pat, city in self.CITY_PATTERNS:
                    if re.search(pat, target, re.IGNORECASE):
                        ev_date = self._extract_date(ev)
                        if ev_date:
                            self.city_ranges.append((ev_date, ev_date + datetime.timedelta(days=3), city))

    def resolve_city_for_date(self, target_date: datetime.date) -> str:
        """Finds matching active city for a specific date, fallback to default_city."""
        for start, end, city in sorted(self.city_ranges, key=lambda x: x[0]):
            if start <= target_date <= end:
                return city
        return self.default_city

    @staticmethod
    def _extract_date(ev: Dict[str, Any]) -> Optional[datetime.date]:
        start_raw = ev.get("start", {}).get("dateTime") or ev.get("start", {}).get("date")
        if not start_raw:
            return None
        try:
            return datetime.date.fromisoformat(start_raw[:10])
        except Exception:
            return None


class ContextClassifier:
    """Analyzes event format, time-of-day, and emoji intent cues."""

    @staticmethod
    def classify(ev: Dict[str, Any]) -> Dict[str, Any]:
        summary = ev.get("summary", "")
        desc = ev.get("description", "")
        attendees = ev.get("attendees", [])
        
        # 1. Attendee format
        is_1v1 = False
        attendee_count = len(attendees)
        if attendee_count <= 2:
            is_1v1 = True
        if re.search(r"(1:1|1v1|×|<>|\bx\b)", summary, re.IGNORECASE):
            is_1v1 = True

        # 2. Time of day
        start_raw = ev.get("start", {}).get("dateTime")
        hour = 12
        if start_raw and "T" in start_raw:
            try:
                time_str = start_raw.split("T")[1][:5]
                hour = int(time_str.split(":")[0])
            except Exception:
                pass

        if hour < 12:
            time_slot = "morning_coffee"
        elif 12 <= hour < 15:
            time_slot = "lunch"
        elif 15 <= hour < 17:
            time_slot = "afternoon_tea"
        elif 17 <= hour < 21:
            time_slot = "evening_drinks_dinner"
        else:
            time_slot = "late_night"

        # 3. Intent & Emoji cues
        intents = []
        combined_text = f"{summary} {desc}"
        if "🍷" in combined_text or re.search(r"\b(wine|bistro|vino)\b", combined_text, re.IGNORECASE):
            intents.append("wine")
        if "🍸" in combined_text or re.search(r"\b(cocktail|bar|speakeasy|drinks)\b", combined_text, re.IGNORECASE):
            intents.append("cocktails")
        if "☕" in combined_text or re.search(r"\b(coffee|cafe|brunch|roaster)\b", combined_text, re.IGNORECASE):
            intents.append("coffee")
        if "🍽️" in combined_text or re.search(r"\b(dinner|dining|restaurant)\b", combined_text, re.IGNORECASE):
            intents.append("dinner")

        return {
            "is_1v1": is_1v1,
            "attendee_count": attendee_count,
            "time_slot": time_slot,
            "hour": hour,
            "intents": intents
        }


def is_placeholder_location(ev: Dict[str, Any]) -> bool:
    """Returns True if summary or location indicates an unresolved venue."""
    summary = ev.get("summary", "").strip()
    loc = ev.get("location", "").strip()

    # Explicit TBD keywords
    tbd_pattern = re.compile(r"\b(TBD|TBC|\?\?\?|Location TBD|Venue TBD)\b", re.IGNORECASE)
    if tbd_pattern.search(summary) or tbd_pattern.search(loc):
        return True

    # Empty location with catchup / social dinner cues
    if not loc:
        social_cue = re.compile(r"(dinner|lunch|coffee|drinks|catch[\s-]*up|1:1|×|<>|🍷|🍸|☕)", re.IGNORECASE)
        if social_cue.search(summary):
            return True

    return False


def match_venues(
    city: str,
    context: Dict[str, Any],
    venues_data: Dict[str, Any],
    limit: int = 3
) -> List[Dict[str, Any]]:
    """Scores and returns top recommended venues for the given context and city."""
    city_data = venues_data.get("cities", {}).get(city, {})
    all_venues = city_data.get("venues", [])
    if not all_venues:
        return []

    scored_venues = []
    intents = set(context.get("intents", []))
    time_slot = context.get("time_slot", "")
    is_1v1 = context.get("is_1v1", False)

    for v in all_venues:
        score = 0
        tags = set(v.get("tags", []))
        cat = v.get("category", "").lower()

        # Intent scoring
        for intent in intents:
            if intent in tags or intent in cat:
                score += 15
            elif intent == "wine" and "dinner_and_wine" in cat:
                score += 12

        # Time slot scoring
        if time_slot in ("morning_coffee", "afternoon_tea") and ("coffee" in tags or cat == "coffee"):
            score += 10
        elif time_slot in ("evening_drinks_dinner", "late_night") and ("cocktails" in tags or "wine" in tags or "dinner" in tags):
            score += 10

        # 1v1 acoustic score
        if is_1v1 and ("1v1" in tags or "quiet" in tags):
            score += 8

        scored_venues.append((score, v))

    # Sort descending by score
    scored_venues.sort(key=lambda x: x[0], reverse=True)
    return [v for _, v in scored_venues[:limit]]


def patch_calendar_event(service, calendar_id: str, event_id: str, location: str, note: Optional[str] = None):
    """Updates an existing Google Calendar event location and description."""
    event = service.events().get(calendarId=calendar_id, eventId=event_id).execute()
    
    # Update location
    event["location"] = location

    # Clean TBD from summary if present
    cleaned_summary = re.sub(r"[\s:—–-]*\b(TBD|TBC|\?\?\?)\b[\s:—–-]*", " ", event.get("summary", ""), flags=re.IGNORECASE).strip()
    event["summary"] = cleaned_summary

    # Append note to description
    if note:
        existing_desc = event.get("description", "").strip()
        new_desc = f"{existing_desc}\n\n[Venue Confirmed]: {note}".strip() if existing_desc else f"[Venue Confirmed]: {note}"
        event["description"] = new_desc

    updated = service.events().patch(calendarId=calendar_id, eventId=event_id, body=event).execute()
    print(f"[SUCCESS] Event updated: '{updated.get('summary')}'")
    print(f"Location:    {updated.get('location')}")
    print(f"Calendar ID: {calendar_id}")
    return updated


def main():
    parser = argparse.ArgumentParser(description="Scan Google Calendar for TBD venues and recommend spots.")
    parser.add_argument("--credentials", help="Path to Google service account JSON or OAuth client secret.")
    parser.add_argument("--calendar-id", default="primary", help="Target Google Calendar ID (default: primary).")
    parser.add_argument("--venues-config", default="venues.yaml", help="Path to venues configuration (YAML/JSON).")
    parser.add_argument("--days-ahead", type=int, default=21, help="Number of days ahead to scan (default: 21).")
    parser.add_argument("--format", choices=["text", "markdown", "json"], default="text", help="Output format.")
    parser.add_argument("--patch-event", help="Google Calendar Event ID to update.")
    parser.add_argument("--location", help="New venue location to patch into the event.")
    parser.add_argument("--note", help="Optional confirmation note or booking details.")
    args = parser.parse_args()

    service = get_calendar_service(args.credentials)

    # 1. Interactive Patch Action
    if args.patch_event:
        if not args.location:
            print("Error: --location is required when --patch-event is specified.", file=sys.stderr)
            sys.exit(1)
        patch_calendar_event(service, args.calendar_id, args.patch_event, args.location, args.note)
        return

    # 2. Normal Scan Action
    venues_data = load_taste_graph(args.venues_config)
    default_city = venues_data.get("default_city", "Singapore")

    now = datetime.datetime.now(datetime.timezone.utc)
    time_min = now.isoformat()
    time_max = (now + datetime.timedelta(days=args.days_ahead)).isoformat()

    events_result = service.events().list(
        calendarId=args.calendar_id,
        timeMin=time_min,
        timeMax=time_max,
        singleEvents=True,
        orderBy="startTime"
    ).execute()

    raw_events = events_result.get("items", [])

    # Step 1: Ingest travel context
    travel_resolver = TravelContextResolver(default_city=default_city)
    travel_resolver.ingest_events(raw_events)

    # Step 2: Filter and match TBD events
    findings = []
    for ev in raw_events:
        if not is_placeholder_location(ev):
            continue

        start_raw = ev.get("start", {}).get("dateTime") or ev.get("start", {}).get("date")
        ev_date = datetime.date.fromisoformat(start_raw[:10]) if start_raw else datetime.date.today()
        
        active_city = travel_resolver.resolve_city_for_date(ev_date)
        context = ContextClassifier.classify(ev)
        recs = match_venues(active_city, context, venues_data)

        attendee_emails = [a.get("displayName") or a.get("email") for a in ev.get("attendees", []) if a.get("email") != args.calendar_id]

        findings.append({
            "id": ev.get("id"),
            "summary": ev.get("summary"),
            "start": start_raw,
            "city": active_city,
            "attendees": attendee_emails,
            "context": context,
            "recommendations": recs
        })

    # Step 3: Render Output
    if args.format == "json":
        print(json.dumps(findings, indent=2))
        return

    if not findings:
        print(f"No upcoming TBD events found in the next {args.days_ahead} days.")
        return

    print(f"\n🔍 Found {len(findings)} upcoming event(s) requiring venue confirmation:\n")
    for i, item in enumerate(findings, 1):
        print(f"{i}. [{item['city']}] {item['summary']}")
        print(f"   Time:      {item['start']}")
        if item['attendees']:
            print(f"   Guests:    {', '.join(item['attendees'])}")
        print(f"   Event ID:  {item['id']}")
        print(f"   Curated Recommendations:")
        for r in item["recommendations"]:
            print(f"    • {r['name']} ({r.get('neighborhood', '')}) — {r.get('vibe', '')}")
            if r.get("url"):
                print(f"      Link: {r['url']}")
        print()


if __name__ == "__main__":
    main()
