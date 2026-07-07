"""AI field report generator (spec Feature 13) — three-tier free fallback chain.

Groq (Llama 3.1 8B) → Gemini 1.5 Flash → Hugging Face (Mistral 7B). All three are
called over plain HTTP via ``requests`` so we don't drag in three vendor SDKs;
the chain advances on rate-limit or failure and records which tier served.

When *no* AI keys are configured (the default dev/demo state), a deterministic,
data-driven **template** composes a genuinely useful two-paragraph report in the
selected language directly from the numbers — so the feature, the PDF export, and
the whole UX work end-to-end with zero setup. Output is labelled with its source
(``groq`` | ``gemini`` | ``huggingface`` | ``template``).
"""
from __future__ import annotations

import logging

import requests

from .config_bridge import config
from .errors import ValidationError

log = logging.getLogger("cropwatch.report")
_TIMEOUT = 25


# --------------------------------------------------------------------------- #
# Prompt construction                                                          #
# --------------------------------------------------------------------------- #
def _system_prompt(language: str, audience: str) -> str:
    lang_name = {"en": "English", "fr": "French", "sw": "Swahili"}.get(language, "English")
    return (
        "You are a senior agricultural analyst writing a concise satellite-derived "
        f"crop condition report. Write entirely in {lang_name}. Target audience: "
        f"{audience}. Produce EXACTLY two paragraphs and nothing else. Paragraph 1: "
        "describe current vegetation conditions and their severity in historical "
        "context, citing the specific NDVI, anomaly, and rainfall figures provided. "
        "Paragraph 2: give a forward-looking interpretation and a concrete "
        "recommended action appropriate to the audience. Do not invent numbers; use "
        "only the data provided. Do not use headings, bullet points, or markdown."
    )


def _user_prompt(p: dict) -> str:
    lines = [f"Region: {p.get('region_name', 'the selected area')}"]
    if p.get("country"):
        lines.append(f"Country: {p['country']}")
    if p.get("date_label"):
        lines.append(f"Composite date: {p['date_label']}")
    if p.get("mean_ndvi") is not None:
        lines.append(f"Mean NDVI: {p['mean_ndvi']:.3f}")
    if p.get("severity"):
        s = p["severity"]
        lines.append(f"Severity score: {s.get('score')}/100 ({s.get('label')})")
    if p.get("mean_z") is not None:
        lines.append(f"Historical anomaly (z-score): {p['mean_z']:+.2f} standard deviations")
    if p.get("rainfall_anomaly_pct") is not None:
        lines.append(f"Rainfall vs long-term average: {p['rainfall_anomaly_pct']:.0f}%")
    if p.get("dominant_crop"):
        lines.append(f"Dominant crop: {p['dominant_crop']}")
    for a in (p.get("analogue_years") or [])[:3]:
        dev = a.get("yield_deviation_pct")
        dev_txt = f", yield {dev:+.0f}% vs average" if dev is not None else ""
        lines.append(f"Analogue year: {a.get('year')}{dev_txt}")
    return "Data:\n" + "\n".join(lines)


# --------------------------------------------------------------------------- #
# Provider calls (each raises on failure so the chain advances)               #
# --------------------------------------------------------------------------- #
def _call_groq(system: str, user: str) -> str:
    resp = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {config.GROQ_API_KEY}"},
        json={"model": "llama-3.1-8b-instant", "temperature": 0.5,
              "messages": [{"role": "system", "content": system},
                           {"role": "user", "content": user}]},
        timeout=_TIMEOUT)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


def _call_gemini(system: str, user: str) -> str:
    resp = requests.post(
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.5-flash:generateContent?key={config.GOOGLE_API_KEY}",
        json={"system_instruction": {"parts": [{"text": system}]},
              "contents": [{"parts": [{"text": user}]}]},
        timeout=_TIMEOUT)
    resp.raise_for_status()
    return resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()


def _call_hf(system: str, user: str) -> str:
    resp = requests.post(
        "https://api-inference.huggingface.co/models/mistralai/Mistral-7B-Instruct-v0.3",
        headers={"Authorization": f"Bearer {config.HF_API_KEY}"},
        json={"inputs": f"<s>[INST] {system}\n\n{user} [/INST]",
              "parameters": {"max_new_tokens": 400, "temperature": 0.5,
                             "return_full_text": False}},
        timeout=_TIMEOUT + 20)
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, list) and data:
        return data[0].get("generated_text", "").strip()
    raise ValueError("Unexpected Hugging Face response")


# --------------------------------------------------------------------------- #
# Deterministic template fallback (no keys needed)                            #
# --------------------------------------------------------------------------- #
def _template(p: dict, language: str, audience: str) -> str:
    region = p.get("region_name", "the monitored area")
    ndvi = p.get("mean_ndvi")
    sev = (p.get("severity") or {}).get("label", "").lower()
    z = p.get("mean_z")
    rain = p.get("rainfall_anomaly_pct")
    analogues = [str(a.get("year")) for a in (p.get("analogue_years") or [])[:2] if a.get("year")]

    z_ctx = ""
    if z is not None:
        band = ("well below" if z <= -1.5 else "below" if z <= -0.5
                else "near" if z < 0.5 else "above")
        z_ctx = f"{abs(z):.1f} standard deviations {band} the long-term average"
    rain_ctx = ""
    if rain is not None:
        rain_ctx = (f"Rainfall has been {rain:.0f}% of the long-term average, "
                    + ("pointing to drought as a likely driver. "
                       if rain < 85 else "broadly in line with normal. "))

    if language == "fr":
        p1 = (f"La santé de la végétation sur {region} présente un NDVI moyen de "
              f"{ndvi:.2f} " if ndvi is not None else f"La santé de la végétation sur {region} ")
        p1 += f"({sev}). " if sev else ". "
        if z_ctx:
            p1 += f"Les conditions actuelles se situent à {z_ctx.replace('standard deviations','écarts-types').replace('well below','nettement en dessous de').replace('below','en dessous de').replace('near','proches de').replace('above','au-dessus de')}. "
        if analogues:
            p1 += f"Les années les plus comparables sont {' et '.join(analogues)}. "
        p2 = rain_ctx.replace("Rainfall has been", "Les précipitations ont représenté").replace("of the long-term average", "de la moyenne").replace("pointing to drought as a likely driver.", "ce qui suggère une sécheresse.").replace("broadly in line with normal.", "globalement conformes à la normale.")
        p2 += _action_fr(audience)
        return p1 + "\n\n" + p2

    if language == "sw":
        p1 = (f"Afya ya mimea katika {region} ina wastani wa NDVI wa {ndvi:.2f}. "
              if ndvi is not None else f"Afya ya mimea katika {region}. ")
        if analogues:
            p1 += f"Miaka inayofanana zaidi ni {' na '.join(analogues)}. "
        p2 = _action_sw(audience)
        return p1 + "\n\n" + p2

    # English (default)
    p1 = (f"Vegetation health across {region} currently shows a mean NDVI of "
          f"{ndvi:.2f}" if ndvi is not None else f"Vegetation health across {region} is summarised below")
    p1 += f", consistent with {sev}. " if sev else ". "
    if z_ctx:
        p1 += f"Current conditions sit {z_ctx} for this time of year"
        if analogues:
            p1 += f", most closely resembling {' and '.join(analogues)}"
        p1 += ". "
    elif analogues:
        p1 += f"Conditions most closely resemble {' and '.join(analogues)}. "
    p1 += rain_ctx
    p2 = _action_en(audience, sev, z)
    return p1.strip() + "\n\n" + p2


def _action_en(audience: str, sev: str, z) -> str:
    stressed = (z is not None and z < -1) or ("severe" in sev or "significant" in sev)
    if audience == "Farmer":
        return ("Farmers with access to supplemental irrigation should consider applying "
                "water within the next two weeks; those without should assess whether an "
                "early partial harvest preserves more value than waiting."
                if stressed else
                "Conditions do not currently warrant emergency intervention; continue "
                "routine monitoring and maintain normal input schedules.")
    if audience == "Trader":
        return ("The signal supports anticipating a supply shortfall weeks ahead of official "
                "statistics; consider positioning accordingly and revisit as new composites arrive."
                if stressed else
                "No supply-side stress signal is evident; maintain current positioning and "
                "monitor for deterioration in coming composites.")
    if audience == "NGO/Government":
        return ("Early pre-positioning of assistance is warranted for the affected sub-areas; "
                "the lead time over official reporting is the difference between aid arriving "
                "before rather than during a crisis."
                if stressed else
                "No emergency response is indicated at present; continue systematic monitoring "
                "across the administrative area.")
    return ("These conditions merit closer field verification and comparison against the "
            "analogue years identified, alongside rainfall and soil-moisture records, to "
            "attribute the observed signal.")


def _action_fr(audience: str) -> str:
    return {"Farmer": "Les agriculteurs disposant d'irrigation devraient envisager un apport d'eau prochainement.",
            "Trader": "Le signal justifie d'anticiper un déficit d'offre avant les statistiques officielles.",
            "NGO/Government": "Un pré-positionnement anticipé de l'aide est justifié pour les zones touchées.",
            }.get(audience, "Ces conditions méritent une vérification de terrain approfondie.")


def _action_sw(audience: str) -> str:
    return {"Farmer": "Wakulima wenye umwagiliaji wanapaswa kuzingatia kuongeza maji hivi karibuni.",
            "Trader": "Ishara hii inapendekeza kutarajia upungufu wa usambazaji kabla ya takwimu rasmi.",
            "NGO/Government": "Maandalizi ya mapema ya misaada yanafaa kwa maeneo yaliyoathirika.",
            }.get(audience, "Hali hii inahitaji uthibitisho zaidi wa shambani.")


# --------------------------------------------------------------------------- #
# Orchestration                                                                #
# --------------------------------------------------------------------------- #
def generate(payload: dict) -> dict:
    language = payload.get("language", "en")
    if language not in config.REPORT_LANGUAGES:
        language = "en"
    audience = payload.get("audience", "Farmer")
    if audience not in config.REPORT_AUDIENCES:
        audience = "Farmer"

    if not isinstance(payload.get("region_name"), (str, type(None))):
        raise ValidationError("region_name must be a string.")

    system = _system_prompt(language, audience)
    user = _user_prompt(payload)

    tiers = []
    if config.GROQ_API_KEY:
        tiers.append(("groq", _call_groq))
    if config.GOOGLE_API_KEY:
        tiers.append(("gemini", _call_gemini))
    if config.HF_API_KEY:
        tiers.append(("huggingface", _call_hf))

    note = None
    for name, fn in tiers:
        try:
            text = fn(system, user)
            if text:
                if name == "huggingface" and language == "sw":
                    note = "Swahili quality is weaker on the fallback model; some English terms may appear."
                return _package(text, name, language, audience, note)
        except Exception as exc:  # try next tier
            log.warning("AI tier %s failed: %s", name, exc)
            continue

    # No keys, or all tiers failed → deterministic template.
    text = _template(payload, language, audience)
    note = ("Generated from the underlying data (no AI provider configured)."
            if not config.HAS_ANY_AI else
            "AI providers were unavailable; generated from the underlying data.")
    return _package(text, "template", language, audience, note)


def _package(text: str, source: str, language: str, audience: str, note) -> dict:
    paragraphs = [para.strip() for para in text.split("\n\n") if para.strip()]
    return {"report": text, "paragraphs": paragraphs, "source": source,
            "language": language, "audience": audience, "editable": True, "note": note}
