"""Ayar dosyası (JSON) yükleme. Gizli anahtarlar ortam değişkenlerinden okunur."""
import json
import os

DEFAULTS = {
    "db_path": "data/radar.db",
    "price_list": "data/fiyat_listesi.json",
    "reports_dir": "reports",
    "owner": {"name": "Özer", "whatsapp": "", "email": ""},
    "price_band_min_ratio": 0.9,
    "critical_price_change_pct": 10,
    "instant_alert_price_drop_pct": 20,
    "pending_expire_days": 3,
    "max_obs_age_days": 7,
    "price_range_tl": [20, 50000],
    "new_entrant_days": 365,
    "candidate_reminder_days": 7,
    "passive_after_quiet_months": 3,
    "daily_top_n": 5,
    "growth_pct_30d": 30,
    "ad_intensity_min": 10,
    "leads": {"enabled": True, "api_key_env": "GOOGLE_PLACES_API_KEY", "daily_limit": 10,
              "queries": ["eczane Çankaya Ankara", "dermatoloji kliniği Ankara",
                          "güzellik merkezi Ankara", "estetik kliniği Ankara"]},
    "regulation": {"urls": ["https://www.titck.gov.tr/duyuru"]},
    "llm": {"base_url_env": "LLM_BASE_URL", "api_key_env": "LLM_API_KEY", "model_env": "LLM_MODEL"},
    "delivery": {"spool_dir": "outbox", "webhook_env": "JARVIS_WHATSAPP_WEBHOOK",
                 "smtp_host_env": "SMTP_HOST", "smtp_user_env": "SMTP_USER", "smtp_pass_env": "SMTP_PASS"},
    "backup": {"dir": "backups", "keep": 14},
}


def _merge(a, b):
    out = dict(a)
    for k, v in (b or {}).items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def load(path=None, base_dir=None):
    path = path or os.environ.get("RADAR_CONFIG", "config.json")
    user = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            user = json.load(f)
        base_dir = base_dir or os.path.dirname(os.path.abspath(path))
    cfg = _merge(DEFAULTS, user)
    base_dir = base_dir or os.getcwd()
    for k in ("db_path", "price_list", "reports_dir"):
        if cfg[k] != ":memory:" and not os.path.isabs(cfg[k]):
            cfg[k] = os.path.join(base_dir, cfg[k])
    for sect, k in (("delivery", "spool_dir"), ("backup", "dir")):
        if not os.path.isabs(cfg[sect][k]):
            cfg[sect][k] = os.path.join(base_dir, cfg[sect][k])
    return cfg
