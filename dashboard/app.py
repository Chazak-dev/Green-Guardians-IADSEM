"""Green Guardians - Person 4 Streamlit dashboard.

This dashboard is intentionally read-only and requires NO changes to the
existing Green Guardians source code.

It reads only artifacts that the current repository already produces:
  - config/Green_Guardians_settings.yaml
  - results/mission_log.jsonl
  - results/images/**

Important limitation of the current architecture:
main.py and MissionController keep the live DashboardStatusOutput in memory.
Because the project is currently a single Python application with in-process
calls, a separately launched Streamlit process cannot access that in-memory
object without changing the existing code. This dashboard therefore presents
the persisted mission/audit data that the current code already writes.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import streamlit as st
import yaml


# -----------------------------------------------------------------------------
# Paths: resolve from the repository root, not from the current working dir.
# dashboard/app.py -> repo root is parent.parent
# -----------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "Green_Guardians_settings.yaml"
LOG_PATH = PROJECT_ROOT / "results" / "mission_log.jsonl"
EVIDENCE_DIR = PROJECT_ROOT / "results" / "images"

REFRESH_SECONDS = 1


# -----------------------------------------------------------------------------
# Styling
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Green Guardians Dashboard",
    page_icon="🌿",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .main-title { font-size: 2.1rem; font-weight: 700; margin-bottom: 0.1rem; }
    .subtitle { color: #6b7280; margin-bottom: 1rem; }
    .card { padding: 1rem 1.1rem; border: 1px solid #e5e7eb; border-radius: 0.8rem; }
    .small { color: #6b7280; font-size: 0.85rem; }
    </style>
    """,
    unsafe_allow_html=True,
)


# -----------------------------------------------------------------------------
# Data loading helpers
# -----------------------------------------------------------------------------
@st.cache_data(ttl=1, show_spinner=False)
def load_config() -> Dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {}
    try:
        with CONFIG_PATH.open("r", encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except Exception:
        return {}


@st.cache_data(ttl=1, show_spinner=False)
def load_log_events(log_path: str, mtime_ns: int, size: int) -> List[Dict[str, Any]]:
    """Read JSONL safely; one malformed line does not break the dashboard."""
    del mtime_ns, size  # only used as cache keys
    path = Path(log_path)
    if not path.exists():
        return []

    events: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line_number, raw in enumerate(fh, start=1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                item = json.loads(raw)
                if isinstance(item, dict):
                    events.append(item)
            except json.JSONDecodeError:
                # Keep going so a partially-written last line cannot crash UI.
                continue
    return events


@st.cache_data(ttl=1, show_spinner=False)
def list_evidence_images(directory: str, newest_first: bool = True) -> List[str]:
    root = Path(directory)
    if not root.exists():
        return []
    candidates = [
        p for p in root.rglob("*")
        if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
    ]
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=newest_first)
    return [str(p) for p in candidates]


def get_log_signature() -> tuple[int, int]:
    if not LOG_PATH.exists():
        return (0, 0)
    stat = LOG_PATH.stat()
    return (stat.st_mtime_ns, stat.st_size)


def parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def pretty_time(value: Optional[str]) -> str:
    parsed = parse_iso(value)
    if parsed is None:
        return value or "—"
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def event_type_count(events: Iterable[Dict[str, Any]], event_type: str) -> int:
    return sum(1 for event in events if event.get("event_type") == event_type)


def latest_event(events: Iterable[Dict[str, Any]], event_type: Optional[str] = None) -> Optional[Dict[str, Any]]:
    filtered = [e for e in events if event_type is None or e.get("event_type") == event_type]
    if not filtered:
        return None
    filtered.sort(key=lambda e: e.get("timestamp", ""))
    return filtered[-1]


def extract_hazard(message: str) -> Optional[str]:
    match = re.search(r"hazard=(fire|smoke)\b", message or "", re.IGNORECASE)
    if match:
        return match.group(1).lower()
    match = re.search(r"Confirmed\s+(fire|smoke)\s+alert", message or "", re.IGNORECASE)
    if match:
        return match.group(1).lower()
    return None


def read_image_as_bytes(path: str) -> Optional[bytes]:
    try:
        return Path(path).read_bytes()
    except OSError:
        return None


def repo_relative(path: str) -> str:
    try:
        return str(Path(path).resolve().relative_to(PROJECT_ROOT)).replace("\\", "/")
    except ValueError:
        return path


# -----------------------------------------------------------------------------
# Refresh handling
# -----------------------------------------------------------------------------
def render_body() -> None:
    config = load_config()
    mtime_ns, size = get_log_signature()
    events = load_log_events(str(LOG_PATH), mtime_ns, size)
    images = list_evidence_images(str(EVIDENCE_DIR))

    project = config.get("project", {}) if isinstance(config, dict) else {}
    shared_policy = config.get("shared_policy", {}) if isinstance(config, dict) else {}
    dashboard_cfg = config.get("dashboard", {}) if isinstance(config, dict) else {}

    title = project.get("name", "Green Guardians")
    hazards = project.get("hazards", ["fire", "smoke"])
    refresh_seconds = dashboard_cfg.get("refresh_seconds", REFRESH_SECONDS)

    st.markdown(f'<div class="main-title">🌿 {title} Dashboard</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="subtitle">Person 4 • Read-only visualization of the current project outputs</div>',
        unsafe_allow_html=True,
    )

    # -------------------------------------------------------------------------
    # Sidebar: project/config summary
    # -------------------------------------------------------------------------
    with st.sidebar:
        st.header("Project")
        st.write("Hazards:", ", ".join(str(h) for h in hazards))
        st.write("Input size:", f"{config.get('camera', {}).get('width', 640)} × {config.get('camera', {}).get('height', 480)}")
        st.write("Evidence:", repo_relative(str(EVIDENCE_DIR)))
        st.write("Log:", repo_relative(str(LOG_PATH)))

        candidate = shared_policy.get("candidate_trigger", {})
        confirmation = shared_policy.get("confirmation", {})
        st.divider()
        st.header("AI / Mission policy")
        st.metric("Candidate threshold", f"{float(candidate.get('threshold', 0.60)):.2f}")
        st.metric("Confirmation threshold", f"{float(confirmation.get('confidence_threshold', 0.65)):.2f}")
        st.write(
            f"Confirmation: {confirmation.get('required_positive_frames', 3)} of "
            f"{confirmation.get('fresh_frames_to_check', 5)} frames"
        )
        st.caption(f"Configured refresh: {refresh_seconds}s")

        if st.button("🔄 Refresh now", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    # -------------------------------------------------------------------------
    # Empty state
    # -------------------------------------------------------------------------
    if not events and not images:
        st.info(
            "No mission outputs have been written yet. Start the existing "
            "Green Guardians mission with `python main.py`; this dashboard "
            "will read the resulting mission log and evidence images."
        )
        st.caption(f"Watching {repo_relative(str(LOG_PATH))} and {repo_relative(str(EVIDENCE_DIR))}")
        return

    # -------------------------------------------------------------------------
    # Mission overview
    # -------------------------------------------------------------------------
    latest = latest_event(events)
    current_state = latest.get("mission_state", "UNKNOWN") if latest else "UNKNOWN"
    last_time = latest.get("timestamp") if latest else None
    alert_count = event_type_count(events, "ALERT_CREATED")
    investigation_count = event_type_count(events, "INVESTIGATION_RESULT")
    error_count = event_type_count(events, "ERROR")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Mission state", current_state)
    c2.metric("Confirmed alerts", alert_count)
    c3.metric("Investigations resolved", investigation_count)
    c4.metric("Errors", error_count)
    st.caption(f"Last persisted backend event: {pretty_time(last_time)}")

    # -------------------------------------------------------------------------
    # Latest activity + latest alert
    # -------------------------------------------------------------------------
    left, right = st.columns([1.25, 0.75])

    with left:
        st.subheader("Latest mission activity")
        recent = sorted(events, key=lambda e: e.get("timestamp", ""), reverse=True)[:12]
        rows = []
        for event in recent:
            rows.append(
                {
                    "Time (UTC)": pretty_time(event.get("timestamp")),
                    "Type": event.get("event_type", "—"),
                    "State": event.get("mission_state", "—"),
                    "Message": event.get("message", "—"),
                    "Detection": event.get("detection_id") or "—",
                    "Alert": event.get("alert_id") or "—",
                }
            )
        st.dataframe(rows, use_container_width=True, hide_index=True)

    with right:
        st.subheader("Latest confirmed alert")
        alert = latest_event(events, "ALERT_CREATED")
        if alert is None:
            st.success("No confirmed alerts have been logged yet.")
        else:
            hazard = extract_hazard(alert.get("message", "")) or "unknown"
            st.write(f"**Hazard:** {hazard.upper()}")
            st.write(f"**Alert ID:** {alert.get('alert_id') or '—'}")
            st.write(f"**Detection ID:** {alert.get('detection_id') or '—'}")
            st.write(f"**Confirmed at:** {pretty_time(alert.get('timestamp'))}")
            st.write(f"**Investigation:** {alert.get('investigation_id') or '—'}")
            st.info(
                "The current backend log stores the alert event and IDs, but it does not persist the full "
                "AlertOutput object (confidence / observed_position / evidence path). "
                "Those values remain in the MissionController's in-memory object, so this read-only dashboard "
                "does not invent them."
            )

    # -------------------------------------------------------------------------
    # Evidence gallery
    # -------------------------------------------------------------------------
    st.subheader("Evidence / captured images")
    if not images:
        st.info("No images have been written to results/images yet.")
    else:
        gallery = images[:6]
        cols = st.columns(min(3, len(gallery)))
        for index, image_path in enumerate(gallery):
            col = cols[index % len(cols)]
            with col:
                data = read_image_as_bytes(image_path)
                if data:
                    st.image(data, caption=repo_relative(image_path), use_container_width=True)
                else:
                    st.warning(f"Could not read {repo_relative(image_path)}")

    # -------------------------------------------------------------------------
    # Configuration + route information
    # -------------------------------------------------------------------------
    st.subheader("Configured mission information")
    mission = config.get("drone", {}) if isinstance(config, dict) else {}
    route = mission.get("patrol_route", []) if isinstance(mission, dict) else []
    if route:
        route_rows = []
        for item in route:
            route_rows.append(
                {
                    "Waypoint": item.get("name", "—"),
                    "X (m)": item.get("position", [None, None, None])[0],
                    "Y (m)": item.get("position", [None, None, None])[1],
                    "Z / altitude (m)": item.get("position", [None, None, None])[2],
                }
            )
        st.dataframe(route_rows, use_container_width=True, hide_index=True)
        st.caption("Coordinates are Webots world coordinates in metres, not GPS latitude/longitude.")

    # -------------------------------------------------------------------------
    # Recent raw events for debugging/demo purposes
    # -------------------------------------------------------------------------
    with st.expander("Raw mission log (latest 20 records)"):
        for event in sorted(events, key=lambda e: e.get("timestamp", ""), reverse=True)[:20]:
            st.json(event)


# -----------------------------------------------------------------------------
# Top-level execution + optional auto-refresh support.
# Streamlit versions with st.fragment can refresh this section without adding
# any extra dependency. Older Streamlit versions still work via the button.
# -----------------------------------------------------------------------------
if hasattr(st, "fragment"):
    try:
        refresh_value = st.fragment(run_every=REFRESH_SECONDS)
    except TypeError:
        refresh_value = st.fragment
    with refresh_value():
        render_body()
else:
    render_body()
