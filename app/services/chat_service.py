import json
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from flask import current_app
from sqlalchemy import func
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models.alert import Alert
from app.models.reading import Reading
from app.models.river import River
from app.services.local_analysis_service import CHANNELS, analyze_monitoring_data


CHANNEL_ALIASES = {
    "turbidity": "turbidity_ntu",
    "ntu": "turbidity_ntu",
    "tss": "tss",
    "particle": "particle_level",
    "particles": "particle_level",
    "particle level": "particle_level",
    "clarity": "clarity",
    "tds": "tds_ppm",
    "conductivity": "conductivity",
    "ionic": "ionic_content",
    "ionic content": "ionic_content",
    "salinity": "salinity",
    "ph": "ph_value",
    "acidity": "acidity",
    "alkalinity": "alkalinity",
    "stability": "ph_stability",
    "temperature": "temperature_c",
    "ambient temperature": "ambient_temperature",
    "change rate": "change_rate",
    "thermal anomaly": "thermal_anomaly",
    "wqi": "water_quality_index",
    "water quality index": "water_quality_index",
}


def _local_ollama_url():
    configured_url = current_app.config.get(
        "OLLAMA_BASE_URL",
        "http://127.0.0.1:11434",
    ).rstrip("/")
    parsed_url = urlsplit(configured_url)
    if parsed_url.scheme != "http" or parsed_url.hostname not in {
        "localhost", "127.0.0.1", "::1",
    }:
        return None
    return configured_url


def local_model_status():
    """Return local Ollama readiness without contacting an external service."""
    base_url = _local_ollama_url()
    configured_model = current_app.config.get("OLLAMA_MODEL", "qwen2.5:3b")
    if base_url is None:
        return {
            "available": False,
            "model": None,
            "models": [],
            "message": "Ollama must use a loopback URL to keep data local",
        }

    request = Request(f"{base_url}/api/tags", method="GET")
    try:
        with urlopen(request, timeout=1) as response:
            payload = json.loads(response.read().decode("utf-8"))
        models = [model.get("name", "") for model in payload.get("models", [])]
        selected = configured_model if configured_model in models else (models[0] if models else None)
        return {
            "available": selected is not None,
            "model": selected,
            "models": models,
            "message": "Local model ready" if selected else "Ollama is running but no model is installed",
        }
    except (HTTPError, URLError, TimeoutError, OSError, ValueError):
        return {
            "available": False,
            "model": None,
            "models": [],
            "message": "Local language model is not running",
        }


def chat_model_status():
    """Report the preferred chat provider without exposing credentials."""
    model = current_app.config.get("GROQ_MODEL", "openai/gpt-oss-20b")
    if current_app.config.get("GROQ_API_KEY"):
        return {
            "available": True,
            "model": model,
            "provider": "online",
            "message": "Online AI ready",
        }

    status = local_model_status()
    status["provider"] = "local"
    return status


_DATASET_CONTEXT_CACHE = {"expires_at": 0.0, "signature": None, "value": None}


def _dataset_signature():
    reading_count = Reading.query.count()
    latest_reading = (
        Reading.query.order_by(Reading.recorded_at.desc(), Reading.id.desc()).first()
    )
    latest_alert = Alert.query.order_by(Alert.created_at.desc(), Alert.id.desc()).first()
    latest_reading_stamp = (
        latest_reading.recorded_at.isoformat() if latest_reading and latest_reading.recorded_at else None
    )
    latest_alert_stamp = (
        latest_alert.created_at.isoformat() if latest_alert and latest_alert.created_at else None
    )
    return (
        reading_count,
        latest_reading.id if latest_reading else None,
        latest_reading_stamp,
        Alert.query.count(),
        latest_alert.id if latest_alert else None,
        latest_alert_stamp,
    )


def _dataset_context():
    now = time.monotonic()
    signature = _dataset_signature()
    if (
        now < _DATASET_CONTEXT_CACHE["expires_at"]
        and _DATASET_CONTEXT_CACHE["value"] is not None
        and _DATASET_CONTEXT_CACHE["signature"] == signature
    ):
        return _DATASET_CONTEXT_CACHE["value"]

    analysis = analyze_monitoring_data()
    fields = [channel["field"] for channel in CHANNELS]
    river_summaries = []
    for river in River.query.order_by(River.name.asc()).all():
        row = db.session.query(
            func.count(Reading.id),
            *(func.avg(getattr(Reading, field)) for field in fields),
        ).filter(Reading.river_id == river.id).one()
        river_summaries.append({
            "river": river.name,
            "reading_count": row[0],
            "averages": {
                field: round(float(value), 2) if value is not None else None
                for field, value in zip(fields, row[1:])
            },
        })

    latest_alerts = (
        Alert.query
        .options(joinedload(Alert.river))
        .order_by(Alert.created_at.desc(), Alert.id.desc())
        .limit(20)
        .all()
    )
    alert_details = [
        {
            "id": alert.id,
            "river": alert.river.name if alert.river else f"River {alert.river_id}",
            "severity": alert.severity,
            "status": alert.status,
            "message": alert.message,
            "created_at": alert.created_at.isoformat() if alert.created_at else None,
        }
        for alert in latest_alerts
    ]
    alert_counts = {
        status: Alert.query.filter(func.lower(Alert.status) == status).count()
        for status in ("open", "monitoring", "resolved")
    }

    value = {
        "scope": f"Channel aggregates and per-river averages cover all {analysis['reading_count']} saved readings. Alert counts cover all alerts; alert_details lists up to the newest 20.",
        "analysis": {
            "reading_count": analysis["reading_count"],
            "river_count": analysis["river_count"],
            "date_range": [analysis["start_at"], analysis["end_at"]],
            "status_counts": analysis["status_counts"],
            "channels": analysis["channels"],
            "configured_threshold_findings": analysis["threshold_findings"],
            "statistical_outlier_count": len(analysis["outliers"]),
        },
        "per_river_averages": river_summaries,
        "alerts": alert_counts,
        "alert_details": alert_details,
    }

    _DATASET_CONTEXT_CACHE["value"] = value
    _DATASET_CONTEXT_CACHE["signature"] = signature
    _DATASET_CONTEXT_CACHE["expires_at"] = now + 15.0
    return value


def _risk_summary(context):
    rivers = context["per_river_averages"]
    if not rivers:
        return "There are no saved river readings yet, so there is no current risk ranking."

    river_rows = [
        item for item in rivers
        if item["averages"].get("turbidity_ntu") is not None
    ]
    if not river_rows:
        return "No turbidity readings are saved yet, so I cannot rank rivers by risk from the current dataset."

    top = max(river_rows, key=lambda item: item["averages"]["turbidity_ntu"])
    return (
        f"The river with the highest average turbidity is {top['river']} at "
        f"{top['averages']['turbidity_ntu']:g} NTU across {top['reading_count']} readings. "
        "This is the most at-risk river in the current dataset."
    )


def _overall_status_summary(context):
    analysis = context["analysis"]
    total = analysis["reading_count"]
    if total == 0:
        return "There are no saved readings yet, so there is no dataset-wide water quality status."

    status_counts = analysis["status_counts"]
    if not status_counts:
        return "No quality status has been assigned yet; the dataset needs at least one assessment to summarize overall status."

    dominant_status, dominant_count = max(status_counts.items(), key=lambda item: item[1])
    other_parts = ", ".join(
        f"{count} {name.lower()}"
        for name, count in sorted(status_counts.items())
    )
    return (
        f"The overall dataset status is {dominant_status} based on {dominant_count} of {total} readings. "
        f"Stored assessments: {other_parts}."
    )


def _offline_answer(question, context):
    """Answer supported analytical questions from exact local aggregates."""
    normalized = question.casefold()
    analysis = context["analysis"]
    channels = {channel["field"]: channel for channel in analysis["channels"]}

    if any(word in normalized for word in ("overall", "dataset", "system", "board")) and any(
        word in normalized for word in ("water quality", "quality status", "health", "status")
    ):
        return _overall_status_summary(context)

    if any(word in normalized for word in ("most at risk", "highest risk", "worst river", "risk ranking", "river is most at risk")):
        return _risk_summary(context)

    for alias in sorted(CHANNEL_ALIASES, key=len, reverse=True):
        if alias in normalized:
            channel = channels[CHANNEL_ALIASES[alias]]
            if any(word in normalized for word in ("average", "avg", "mean")):
                if channel["mean"] is None:
                    return f"There are no saved {channel['label']} measurements in the dataset."
                return (
                    f"Across all {channel['count']} readings containing {channel['label']}, "
                    f"the average is {channel['mean']:g}. The recorded range is "
                    f"{channel['minimum']:g} to {channel['maximum']:g}; values are shown as received."
                )
            if any(word in normalized for word in ("highest", "maximum", "max")):
                return (
                    f"The highest recorded {channel['label']} value is "
                    f"{channel['maximum']:g}. This is a measured maximum, not by itself a safety judgment."
                    if channel["maximum"] is not None
                    else f"There are no saved {channel['label']} measurements."
                )
            if any(word in normalized for word in ("lowest", "minimum", "min")):
                return (
                    f"The lowest recorded {channel['label']} value is "
                    f"{channel['minimum']:g}. This is a measured minimum."
                    if channel["minimum"] is not None
                    else f"There are no saved {channel['label']} measurements."
                )
            if any(word in normalized for word in ("latest", "most recent", "current")):
                if channel["latest_value"] is None:
                    return f"There are no saved {channel['label']} measurements."
                timestamp = channel["latest_at"] or "timestamp unavailable"
                return (
                    f"The latest saved {channel['label']} value is "
                    f"{channel['latest_value']:g}, recorded at {timestamp}."
                )
            trend = channel["trend"]
            if trend:
                return (
                    f"Across the dataset chronology, {channel['label']} is "
                    f"{trend['direction']}: first {trend['first']:g}, latest "
                    f"{trend['latest']:g}, change {trend['change']:+g}."
                )
            return f"There are {channel['count']} saved {channel['label']} measurements; at least two are needed to describe a trend."

    if "alert" in normalized:
        return (
            f"There are {context['alerts']['open']} open, "
            f"{context['alerts']['monitoring']} under monitoring, and "
            f"{context['alerts']['resolved']} resolved alerts."
        )

    if any(phrase in normalized for phrase in (
        "compare", "comparison", "which river", "rivers by", "across the rivers",
    )):
        turbidity_rivers = [
            item for item in context["per_river_averages"]
            if item["averages"]["turbidity_ntu"] is not None
        ]
        highest = max(
            turbidity_rivers,
            key=lambda item: item["averages"]["turbidity_ntu"],
            default=None,
        )
        comparisons = [
            f"{item['river']}: {item['reading_count']} readings"
            + (
                f", average turbidity {item['averages']['turbidity_ntu']:g} NTU"
                if item["averages"]["turbidity_ntu"] is not None else ""
            )
            for item in context["per_river_averages"]
        ]
        summary = "Per-river summary: " + ("; ".join(comparisons) if comparisons else "no rivers have saved readings") + "."
        if highest:
            summary += (
                f" Highest average turbidity is {highest['river']} at "
                f"{highest['averages']['turbidity_ntu']:g} NTU."
            )
        return summary

    if any(word in normalized for word in ("missing", "coverage", "incomplete")):
        incomplete = [
            channel for channel in analysis["channels"]
            if channel["count"] < analysis["reading_count"]
        ]
        if not incomplete:
            return f"All {len(analysis['channels'])} tracked channels have values in every saved reading."
        details = "; ".join(
            f"{channel['label']}: {channel['count']} of {analysis['reading_count']} readings"
            for channel in incomplete
        )
        return "Channel coverage: " + details + "."

    if any(word in normalized for word in ("summarize", "summary", "overview", "dataset")):
        statuses = ", ".join(
            f"{count} {name.lower()}"
            for name, count in sorted(analysis["status_counts"].items())
        ) or "no assessed readings"
        date_range = analysis["date_range"]
        period = f" from {date_range[0]} through {date_range[1]}" if all(date_range) else ""
        return (
            f"The dataset contains {analysis['reading_count']} readings across "
            f"{analysis['river_count']} rivers{period}. Stored assessments: {statuses}. "
            f"There are {context['alerts']['open']} open alerts."
        )

    return None


def _online_answer(question, conversation, context, status):
    api_key = current_app.config.get("GROQ_API_KEY")
    if not api_key:
        return None

    system_message = (
        "You are AquaSense, a water-monitoring assistant. Answer using only the supplied "
        "AquaSense data context. The context contains locally calculated channel summaries, "
        "per-river averages, alert counts, and up to 20 recent alerts. Never invent readings, "
        "units, calibration, thresholds, or causes. Distinguish stored quality status, "
        "configured limits, and statistical outliers. Values are stored as received. "
        "For numeric questions, cite the supplied measurement count and state when channel "
        "coverage is incomplete. Be concise and useful."
    )
    messages = [{
        "role": "system",
        "content": system_message + "\n\nDATA CONTEXT:\n" + json.dumps(context, ensure_ascii=True),
    }]
    for item in (conversation or [])[-8:]:
        role = item.get("role")
        content = item.get("content")
        if role in {"user", "assistant"} and isinstance(content, str):
            messages.append({"role": role, "content": content[:2000]})
    messages.append({"role": "user", "content": question})
    payload = json.dumps({
        "model": status["model"],
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": 220,
    }).encode("utf-8")
    request = Request(
        current_app.config.get(
            "GROQ_API_URL",
            "https://api.groq.com/openai/v1/chat/completions",
        ),
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(
            request,
            timeout=current_app.config.get("GROQ_TIMEOUT_SECONDS", 20),
        ) as response:
            result = json.loads(response.read().decode("utf-8"))
        answer = result["choices"][0]["message"]["content"].strip()
        if answer:
            return {
                "answer": answer,
                "mode": "online-model",
                "model": status["model"],
                "model_status": status,
            }
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, KeyError, IndexError, TypeError):
        return None
    return None


def _unavailable_answer(question, context):
    prompt = question.strip()
    if len(prompt) > 240:
        prompt = prompt[:237].rstrip() + "..."

    analysis = context["analysis"]
    if analysis["reading_count"]:
        statuses = ", ".join(
            f"{count} {name.lower()}"
            for name, count in sorted(analysis["status_counts"].items())
        ) or "no assessed readings"
        snapshot = (
            f"AquaSense currently has {analysis['reading_count']} readings across "
            f"{analysis['river_count']} rivers, with {context['alerts']['open']} open alerts "
            f"and {statuses} stored assessments."
        )
    else:
        snapshot = "AquaSense has no saved monitoring readings yet."

    if current_app.config.get("GROQ_API_KEY"):
        setup_message = (
            "The online AI did not return a reply, and the local model is unavailable. "
            "Please try again shortly."
        )
    else:
        setup_message = (
            "A full free-form AI reply needs GROQ_API_KEY configured or the local Ollama "
            "model running."
        )

    return (
        f'I received your message: "{prompt}". {snapshot} '
        f"{setup_message} I can still calculate saved sensor averages, ranges, trends, "
        "river comparisons, coverage gaps, and alert counts directly from the database."
    )


def answer_local_question(question, conversation=None):
    """Use exact local data, then online AI, then local Ollama as a fallback."""
    context = _dataset_context()
    verified_answer = _offline_answer(question, context)
    status = chat_model_status()
    if verified_answer is not None:
        return {
            "answer": verified_answer,
            "mode": "local-data",
            "model": None,
            "model_status": status,
        }

    online_answer = _online_answer(question, conversation, context, status)
    if online_answer is not None:
        return online_answer

    status = local_model_status()
    base_url = _local_ollama_url()

    if status["available"]:
        system_message = (
            "You are AquaSense, a private local water-monitoring assistant. "
            "Answer only from the supplied AquaSense data context. Channel aggregates and "
            "per-river averages use every saved reading. Alert counts use every alert; alert "
            "details include only the newest 20. "
            "Never invent values, units, calibration, thresholds, or causes. Sensor values "
            "are stored as received. Distinguish stored quality status, configured limits, "
            "and statistical outliers. Every channel summary includes its count and coverage_percent. "
            "Before making a dataset-wide claim about a channel, check that channel's count: "
            "when it is lower than analysis.reading_count, explicitly say the evidence is partial "
            "and do not describe the whole dataset based on the subset. A zero does not prove "
            "absence when coverage is incomplete. Never recalculate totals or averages; quote "
            "the supplied aggregate values exactly. If evidence is insufficient, say so. Be concise "
            "and cite counts, ranges, rivers, or timestamps when useful."
        )
        messages = [{"role": "system", "content": system_message + "\n\nDATA CONTEXT:\n" + json.dumps(context, ensure_ascii=True)}]
        for item in (conversation or [])[-8:]:
            role = item.get("role")
            content = item.get("content")
            if role in {"user", "assistant"} and isinstance(content, str):
                messages.append({"role": role, "content": content[:2000]})
        messages.append({"role": "user", "content": question})
        payload = json.dumps({
            "model": status["model"],
            "messages": messages,
            "stream": False,
            "keep_alive": "10m",
            "options": {"temperature": 0.1, "num_predict": 160},
        }).encode("utf-8")
        request = Request(
            f"{base_url}/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=120) as response:
                result = json.loads(response.read().decode("utf-8"))
            answer = result.get("message", {}).get("content", "").strip()
            if answer:
                return {
                    "answer": answer,
                    "mode": "local-model",
                    "model": status["model"],
                    "model_status": status,
                }
        except (HTTPError, URLError, TimeoutError, OSError, ValueError):
            pass

    return {
        "answer": _unavailable_answer(question, context),
        "mode": "local-data",
        "model": None,
        "model_status": status,
    }