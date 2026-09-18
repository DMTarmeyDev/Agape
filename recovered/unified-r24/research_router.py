from __future__ import annotations

import base64
import importlib.util
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

SECRET_SERVICE = "AgapeUnified-R2.4-ResearchSources"

# A deliberately broader catalogue than ten sources. Agape scores the catalogue
# per project and exposes only the best ten for that subject.
SOURCE_CATALOG: list[dict[str, Any]] = [
    {
        "id": "companies_house", "name": "Companies House", "kind": "official_registry", "country": "UK",
        "authority": 10.0, "freshness": 10.0, "coverage": 8.8, "cost_efficiency": 10.0, "compliance": 10.0,
        "subjects": ["company", "business", "due_diligence", "competitor", "supplier", "investment", "director", "ownership", "finance", "uk"],
        "summary": "Official UK company records, officers, filings and legal entity information.",
        "auth_mode": "api_key", "secret_name": "companies_house_api_key", "env_var": "COMPANIES_HOUSE_API_KEY",
        "setup_url": "https://developer.company-information.service.gov.uk/", "official": True,
    },
    {
        "id": "ons", "name": "Office for National Statistics", "kind": "official_statistics", "country": "UK",
        "authority": 10.0, "freshness": 9.5, "coverage": 9.2, "cost_efficiency": 10.0, "compliance": 10.0,
        "subjects": ["market", "economy", "employment", "population", "demographic", "industry", "inflation", "wages", "construction", "housing", "uk"],
        "summary": "Official UK economic, population, labour-market and industry statistics.",
        "auth_mode": "public", "setup_url": "https://developer.ons.gov.uk/", "official": True,
    },
    {
        "id": "fca", "name": "FCA Register + Handbook", "kind": "official_regulator", "country": "UK",
        "authority": 10.0, "freshness": 9.8, "coverage": 8.0, "cost_efficiency": 10.0, "compliance": 10.0,
        "subjects": ["finance", "financial", "insurance", "investment", "payments", "fintech", "compliance", "regulation", "risk", "uk"],
        "summary": "UK financial-firm register, regulatory status and FCA Handbook rules.",
        "auth_mode": "api_key", "secret_name": "fca_api_key", "env_var": "FCA_REGISTER_API_KEY",
        "setup_url": "https://register.fca.org.uk/Developer/s/", "official": True,
    },
    {
        "id": "uk_procurement", "name": "Contracts Finder + Find a Tender", "kind": "official_procurement", "country": "UK",
        "authority": 10.0, "freshness": 9.7, "coverage": 9.0, "cost_efficiency": 10.0, "compliance": 10.0,
        "subjects": ["tender", "procurement", "government", "public_sector", "supplier", "contract", "construction", "facilities", "flooring", "uk"],
        "summary": "UK public-sector contract opportunities, notices, awards and buyer information.",
        "auth_mode": "public", "setup_url": "https://www.gov.uk/contracts-finder", "official": True,
    },
    {
        "id": "opencorporates", "name": "OpenCorporates", "kind": "company_intelligence", "country": "Global",
        "authority": 9.0, "freshness": 8.8, "coverage": 10.0, "cost_efficiency": 8.0, "compliance": 9.2,
        "subjects": ["company", "business", "due_diligence", "competitor", "supplier", "ownership", "director", "international"],
        "summary": "Global company registry aggregation with provenance back to public sources.",
        "auth_mode": "api_key", "secret_name": "opencorporates_api_token", "env_var": "OPENCORPORATES_API_TOKEN",
        "setup_url": "https://api.opencorporates.com/", "official": False,
    },
    {
        "id": "crunchbase", "name": "Crunchbase", "kind": "private_market", "country": "Global",
        "authority": 8.8, "freshness": 9.2, "coverage": 9.4, "cost_efficiency": 5.5, "compliance": 9.0,
        "subjects": ["startup", "investment", "funding", "competitor", "technology", "private_market", "company", "venture"],
        "summary": "Private-company, startup, funding, investor and market intelligence.",
        "auth_mode": "api_key", "secret_name": "crunchbase_api_key", "env_var": "CRUNCHBASE_API_KEY",
        "setup_url": "https://data.crunchbase.com/", "official": False,
    },
    {
        "id": "dealroom", "name": "Dealroom", "kind": "startup_intelligence", "country": "Global",
        "authority": 8.8, "freshness": 9.4, "coverage": 9.1, "cost_efficiency": 5.5, "compliance": 9.0,
        "subjects": ["startup", "investment", "funding", "technology", "ecosystem", "venture", "competitor", "innovation"],
        "summary": "Startup ecosystems, companies, funding rounds, investors, jobs and accelerators.",
        "auth_mode": "api_key", "secret_name": "dealroom_api_key", "env_var": "DEALROOM_API_KEY",
        "setup_url": "https://knowledge.dealroom.co/knowledge/dealroom-api-1", "official": False,
    },
    {
        "id": "apollo", "name": "Apollo", "kind": "b2b_data_provider", "country": "Global",
        "authority": 7.8, "freshness": 9.0, "coverage": 9.0, "cost_efficiency": 6.2, "compliance": 7.8,
        "subjects": ["b2b", "sales", "company", "market", "prospect", "supplier", "customer", "commercial", "competitor"],
        "summary": "Licensed B2B company/contact enrichment for professional commercial research.",
        "auth_mode": "api_key", "secret_name": "apollo_api_key", "env_var": "APOLLO_API_KEY",
        "setup_url": "https://docs.apollo.io/", "official": False,
        "privacy_note": "Use only for legitimate B2B/professional research; do not use for sensitive personal profiling.",
    },
    {
        "id": "gdelt", "name": "GDELT", "kind": "news_intelligence", "country": "Global",
        "authority": 7.8, "freshness": 10.0, "coverage": 10.0, "cost_efficiency": 10.0, "compliance": 9.5,
        "subjects": ["news", "market", "reputation", "risk", "competitor", "international", "trend", "public_sentiment", "politics", "technology"],
        "summary": "Global news monitoring and event/media trend signals across many languages.",
        "auth_mode": "public", "setup_url": "https://www.gdeltproject.org/", "official": False,
    },
    {
        "id": "google_trends", "name": "Google Trends API", "kind": "search_trends", "country": "Global",
        "authority": 8.5, "freshness": 9.8, "coverage": 9.5, "cost_efficiency": 9.0, "compliance": 9.5,
        "subjects": ["market", "consumer", "demand", "trend", "brand", "product", "search", "seasonality", "location"],
        "summary": "Search-interest and demand trend evidence. Official API access is currently limited/alpha.",
        "auth_mode": "limited_access", "env_var": "GOOGLE_TRENDS_API_ACCESS", "setup_url": "https://developers.google.com/search/apis/trends", "official": True,
    },
    {
        "id": "x", "name": "X", "kind": "social_listening", "country": "Global",
        "authority": 6.8, "freshness": 10.0, "coverage": 9.0, "cost_efficiency": 6.5, "compliance": 8.5,
        "subjects": ["social", "sentiment", "brand", "trend", "news", "customer", "technology", "public_sentiment", "reputation"],
        "summary": "Recent public conversation, brand mentions, hashtags and real-time topic signals.",
        "auth_mode": "token", "secret_name": "x_bearer_token", "env_var": "X_BEARER_TOKEN",
        "setup_url": "https://developer.x.com/", "official": True,
    },
    {
        "id": "youtube", "name": "YouTube", "kind": "video_social", "country": "Global",
        "authority": 7.0, "freshness": 9.5, "coverage": 9.5, "cost_efficiency": 8.5, "compliance": 9.0,
        "subjects": ["consumer", "product", "how_to", "reviews", "sentiment", "brand", "technology", "training", "trend", "social"],
        "summary": "Video/channel/search metadata for product research, customer language and topic discovery.",
        "auth_mode": "api_key", "secret_name": "youtube_api_key", "env_var": "YOUTUBE_API_KEY",
        "setup_url": "https://developers.google.com/youtube/v3", "official": True,
    },
    {
        "id": "linkedin", "name": "LinkedIn", "kind": "professional_social", "country": "Global",
        "authority": 7.5, "freshness": 9.0, "coverage": 8.5, "cost_efficiency": 6.0, "compliance": 9.0,
        "subjects": ["b2b", "company", "employment", "industry", "professional", "brand", "social", "talent", "commercial"],
        "summary": "User-authorized company-page posts, engagement and organization analytics where API access is approved.",
        "auth_mode": "oauth_token", "secret_name": "linkedin_access_token", "env_var": "LINKEDIN_ACCESS_TOKEN",
        "setup_url": "https://learn.microsoft.com/linkedin/", "official": True,
    },
    {
        "id": "reddit", "name": "Reddit", "kind": "community_social", "country": "Global",
        "authority": 6.2, "freshness": 9.5, "coverage": 8.7, "cost_efficiency": 7.0, "compliance": 8.2,
        "subjects": ["community", "sentiment", "customer", "problem", "product", "technology", "reviews", "social", "discovery"],
        "summary": "Community discussions and recurring user problems; best treated as qualitative discovery, not hard factual evidence.",
        "auth_mode": "developer_access", "secret_name": "reddit_access_token", "env_var": "REDDIT_ACCESS_TOKEN",
        "setup_url": "https://developers.reddit.com/", "official": True,
    },
]

TOKEN_PATTERNS: dict[str, list[str]] = {
    "company": [r"compan(?:y|ies)", r"business", r"supplier", r"competitor", r"director", r"ownership", r"due diligence"],
    "startup": [r"startup", r"venture", r"funding", r"seed", r"series [a-z]", r"investor"],
    "investment": [r"invest", r"funding", r"valuation", r"pitch", r"business plan", r"investor"],
    "market": [r"market", r"tam", r"sam", r"som", r"demand", r"growth", r"opportunity"],
    "finance": [r"finance", r"financial", r"bank", r"fintech", r"insurance", r"payment", r"fca"],
    "procurement": [r"procurement", r"tender", r"contract", r"public sector", r"government", r"framework"],
    "construction": [r"construction", r"floor(?:ing)?", r"fit[- ]?out", r"interior", r"facilities", r"building"],
    "technology": [r"technology", r"software", r"saas", r"ai\b", r"artificial intelligence", r"developer", r"platform"],
    "consumer": [r"consumer", r"customer", r"brand", r"product", r"retail", r"review", r"sentiment"],
    "employment": [r"employment", r"workforce", r"salary", r"wage", r"job", r"talent", r"recruit"],
    "news": [r"news", r"reputation", r"risk", r"controvers", r"media", r"current"],
    "social": [r"social", r"sentiment", r"community", r"reddit", r"youtube", r"linkedin", r"\bx\b", r"twitter"],
    "uk": [r"\buk\b", r"united kingdom", r"england", r"scotland", r"wales", r"britain", r"british"],
}

SUBJECT_TO_TAGS = {
    "company": ["company", "due_diligence", "supplier", "competitor", "ownership"],
    "startup": ["startup", "funding", "venture", "technology", "company"],
    "investment": ["investment", "funding", "company", "market", "finance"],
    "market": ["market", "consumer", "trend", "industry", "demand"],
    "finance": ["finance", "financial", "compliance", "regulation", "investment"],
    "procurement": ["procurement", "tender", "contract", "supplier", "government"],
    "construction": ["construction", "supplier", "procurement", "industry", "uk"],
    "technology": ["technology", "startup", "competitor", "trend", "industry"],
    "consumer": ["consumer", "brand", "product", "sentiment", "trend"],
    "employment": ["employment", "wages", "talent", "industry", "professional"],
    "news": ["news", "reputation", "risk", "trend", "public_sentiment"],
    "social": ["social", "sentiment", "community", "brand", "public_sentiment"],
    "uk": ["uk", "company", "economy", "procurement", "regulation"],
}


def _keyring_module():
    try:
        import keyring  # type: ignore
        return keyring
    except Exception:
        return None


def credential_support_status() -> dict[str, Any]:
    return {"installed": importlib.util.find_spec("keyring") is not None, "service": SECRET_SERVICE}


def install_credential_support() -> dict[str, Any]:
    if importlib.util.find_spec("keyring") is not None:
        return {"ok": True, "already_installed": True, **credential_support_status()}
    proc = subprocess.run([sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "keyring"], capture_output=True, text=True, timeout=300)
    if proc.returncode != 0:
        raise RuntimeError("KEYRING_INSTALL_FAILED: " + (proc.stderr or proc.stdout or "unknown error")[-1500:])
    return {"ok": True, "already_installed": False, **credential_support_status()}


def source_by_id(source_id: str) -> dict[str, Any] | None:
    sid = str(source_id or "").strip().lower()
    for row in SOURCE_CATALOG:
        if row["id"] == sid:
            return dict(row)
    return None


def _secret_get(source: dict[str, Any]) -> str:
    env_var = str(source.get("env_var") or "")
    if env_var:
        value = str(os.environ.get(env_var) or "").strip()
        if value:
            return value
    secret_name = str(source.get("secret_name") or "")
    if not secret_name:
        return ""
    kr = _keyring_module()
    if kr is None:
        return ""
    try:
        return str(kr.get_password(SECRET_SERVICE, secret_name) or "").strip()
    except Exception:
        return ""


def save_secret(source_id: str, secret: str) -> dict[str, Any]:
    source = source_by_id(source_id)
    if not source:
        raise ValueError("UNKNOWN_RESEARCH_SOURCE")
    if source.get("auth_mode") in {"public", "limited_access"}:
        raise ValueError("SOURCE_DOES_NOT_ACCEPT_SAVED_SECRET")
    secret = str(secret or "").strip()
    if not secret:
        raise ValueError("SECRET_REQUIRED")
    kr = _keyring_module()
    if kr is None:
        raise RuntimeError("WINDOWS_CREDENTIAL_STORE_SUPPORT_NOT_INSTALLED")
    kr.set_password(SECRET_SERVICE, str(source["secret_name"]), secret)
    return {"ok": True, "source_id": source_id, "saved": True}


def delete_secret(source_id: str) -> dict[str, Any]:
    source = source_by_id(source_id)
    if not source:
        raise ValueError("UNKNOWN_RESEARCH_SOURCE")
    kr = _keyring_module()
    if kr is not None and source.get("secret_name"):
        try:
            kr.delete_password(SECRET_SERVICE, str(source["secret_name"]))
        except Exception:
            pass
    return {"ok": True, "source_id": source_id, "forgotten": True}


def _http(method: str, url: str, headers: dict[str, str] | None = None, timeout: int = 10) -> tuple[int, str]:
    req = urllib.request.Request(url, method=method, headers=headers or {"User-Agent": "Agape-Unified-R2.4/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return int(response.status), response.read(2000).decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read(2000).decode("utf-8", errors="replace")
    except Exception as exc:
        return 0, str(exc)


def connector_test(source_id: str) -> dict[str, Any]:
    source = source_by_id(source_id)
    if not source:
        raise ValueError("UNKNOWN_RESEARCH_SOURCE")
    sid = source["id"]
    secret = _secret_get(source)
    if source.get("auth_mode") not in {"public", "limited_access"} and not secret:
        return {"ok": False, "source_id": sid, "error": "CREDENTIAL_REQUIRED"}
    if sid == "ons":
        status, text = _http("GET", "https://api.beta.ons.gov.uk/v1/datasets?limit=1")
        return {"ok": status == 200, "source_id": sid, "http_status": status, "detail": text[:240]}
    if sid == "gdelt":
        url = "https://api.gdeltproject.org/api/v2/doc/doc?query=technology&mode=ArtList&maxrecords=1&format=json"
        status, text = _http("GET", url)
        return {"ok": status == 200, "source_id": sid, "http_status": status, "detail": text[:240]}
    if sid == "companies_house":
        token = base64.b64encode((secret + ":").encode("utf-8")).decode("ascii")
        status, text = _http("GET", "https://api.company-information.service.gov.uk/search/companies?q=OpenAI", {"Authorization": "Basic " + token, "User-Agent": "Agape-Unified-R2.4/1.0"})
        return {"ok": status == 200, "source_id": sid, "http_status": status, "detail": text[:240]}
    if sid == "opencorporates":
        url = "https://api.opencorporates.com/v0.4/companies/search?q=OpenAI&api_token=" + urllib.parse.quote(secret)
        status, text = _http("GET", url)
        return {"ok": status == 200, "source_id": sid, "http_status": status, "detail": text[:240]}
    if sid == "apollo":
        status, text = _http("GET", "https://api.apollo.io/api/v1/auth/health", {"x-api-key": secret, "Accept": "application/json", "User-Agent": "Agape-Unified-R2.4/1.0"})
        return {"ok": status == 200, "source_id": sid, "http_status": status, "detail": text[:240]}
    if sid == "x":
        url = "https://api.x.com/2/tweets/search/recent?query=technology&max_results=10"
        status, text = _http("GET", url, {"Authorization": "Bearer " + secret, "User-Agent": "Agape-Unified-R2.4/1.0"})
        return {"ok": status == 200, "source_id": sid, "http_status": status, "detail": text[:240]}
    if sid == "youtube":
        url = "https://www.googleapis.com/youtube/v3/search?part=snippet&type=video&maxResults=1&q=technology&key=" + urllib.parse.quote(secret)
        status, text = _http("GET", url)
        return {"ok": status == 200, "source_id": sid, "http_status": status, "detail": text[:240]}
    if sid == "google_trends":
        ready = bool(str(os.environ.get("GOOGLE_TRENDS_API_ACCESS") or "").strip())
        return {"ok": ready, "source_id": sid, "limited_access": True, "detail": "Google Trends API alpha access flag present" if ready else "Google Trends API access is limited; apply for alpha access."}
    # Some commercial/OAuth sources require customer-specific API hosts/scopes or app approval.
    return {"ok": bool(secret) or source.get("auth_mode") == "public", "source_id": sid, "credential_present": bool(secret), "detail": "Credential is present. Full live test depends on your provider plan/app scopes."}


def connector_status(source: dict[str, Any]) -> dict[str, Any]:
    auth_mode = str(source.get("auth_mode") or "public")
    secret_present = bool(_secret_get(source))
    if auth_mode == "public":
        ready = True
        state = "READY"
    elif auth_mode == "limited_access":
        ready = bool(str(os.environ.get(str(source.get("env_var") or "")) or "").strip())
        state = "READY" if ready else "LIMITED ACCESS"
    else:
        ready = secret_present
        state = "CONNECTED" if ready else "NOT CONNECTED"
    return {
        "id": source["id"], "name": source["name"], "kind": source["kind"], "country": source.get("country"),
        "summary": source["summary"], "official": bool(source.get("official")), "auth_mode": auth_mode,
        "ready": ready, "state": state, "setup_url": source.get("setup_url"), "secret_present": secret_present,
        "env_var": source.get("env_var"), "privacy_note": source.get("privacy_note", ""),
        "authority": source["authority"], "freshness": source["freshness"], "coverage": source["coverage"],
    }


def all_source_status() -> dict[str, Any]:
    return {
        "ok": True,
        "credential_support": credential_support_status(),
        "sources": [connector_status(x) for x in SOURCE_CATALOG],
        "policy": "Only public data or explicitly connected/licensed accounts are used. Passwords, MFA codes and browser cookies are never requested or stored.",
    }


def classify_subject(text: str) -> dict[str, Any]:
    t = " ".join(str(text or "").lower().split())
    matched: list[dict[str, Any]] = []
    for subject, patterns in TOKEN_PATTERNS.items():
        hits = sum(1 for p in patterns if re.search(p, t, flags=re.I))
        if hits:
            matched.append({"subject": subject, "hits": hits})
    matched.sort(key=lambda x: (-x["hits"], x["subject"]))
    primary = matched[0]["subject"] if matched else "general"
    tags: list[str] = []
    for row in matched[:6]:
        for tag in SUBJECT_TO_TAGS.get(row["subject"], []):
            if tag not in tags:
                tags.append(tag)
    if not tags:
        tags = ["company", "market", "trend", "business"]
    return {"primary": primary, "subjects": matched, "tags": tags}


def recommend_sources(text: str, limit: int = 10) -> dict[str, Any]:
    subject = classify_subject(text)
    tags = set(subject["tags"])
    rows = []
    for src in SOURCE_CATALOG:
        src_tags = set(src.get("subjects") or [])
        overlap = len(tags & src_tags)
        relevance = min(10.0, 2.5 + overlap * 2.1)
        if subject["primary"] in src_tags:
            relevance = min(10.0, relevance + 1.4)
        status = connector_status(src)
        availability = 10.0 if status["ready"] else (4.0 if src.get("auth_mode") != "limited_access" else 2.0)
        score = (
            relevance * 0.34 + float(src["authority"]) * 0.20 + float(src["freshness"]) * 0.14 +
            float(src["coverage"]) * 0.11 + availability * 0.09 + float(src["compliance"]) * 0.07 +
            float(src["cost_efficiency"]) * 0.05
        )
        reasons = []
        if overlap:
            reasons.append("matches " + ", ".join(sorted(tags & src_tags)[:4]))
        if src.get("official"):
            reasons.append("official source")
        if status["ready"]:
            reasons.append("available now")
        else:
            reasons.append("connection/access required")
        rows.append({
            **status,
            "score": round(score, 2), "relevance": round(relevance, 2),
            "reason": "; ".join(reasons),
            "rank_inputs": {"authority": src["authority"], "freshness": src["freshness"], "coverage": src["coverage"], "availability": availability, "cost_efficiency": src["cost_efficiency"], "compliance": src["compliance"]},
        })
    rows.sort(key=lambda x: (-float(x["score"]), not bool(x["ready"]), x["name"]))
    selected = rows[:max(1, min(10, int(limit)))]
    return {
        "ok": True, "subject": subject, "selected_count": len(selected), "sources": selected,
        "ready_count": sum(1 for x in selected if x["ready"]),
        "method": "relevance 34% + authority 20% + freshness 14% + coverage 11% + availability 9% + compliance 7% + cost efficiency 5%",
    }
