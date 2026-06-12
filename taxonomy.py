"""Theme taxonomy for Aurel3 MVP."""

from __future__ import annotations


THEME_TAXONOMY = {
    "eu_defense_rearmament": {
        "theme_type": "geopolitics_policy",
        "label": "EU defense / rearmament",
        "match_labels": {"eu_policy"},
        "match_sectors": {"industrials"},
        "keywords": {"defense", "defence", "military", "rearmament", "security"},
        "default_horizon": "1-3 months",
    },
    "energy_geopolitical_supply_risk": {
        "theme_type": "geopolitics_policy",
        "label": "Energy / geopolitical supply risk",
        "match_labels": {"energy"},
        "match_sectors": {"energy", "utilities"},
        "keywords": {"oil", "gas", "energy", "shipping disruption", "geopolitical tensions"},
        "default_horizon": "1-3 months",
    },
    "ai_compute_infrastructure": {
        "theme_type": "structural_sector_narrative",
        "label": "AI / compute infrastructure",
        "match_labels": {"ai"},
        "match_sectors": {"technology"},
        "keywords": {"ai", "data center", "semiconductor", "compute"},
        "default_horizon": "1-3 months",
    },
    "commodities_resource_supply_shock": {
        "theme_type": "macro_policy",
        "label": "Commodities / resource supply shock",
        "match_labels": {"energy"},
        "match_sectors": {"basic materials", "energy"},
        "keywords": {"commodity", "copper", "uranium", "rare earth", "supply shock", "metal"},
        "default_horizon": "1-3 months",
    },
    "critical_materials_battery_inputs": {
        "theme_type": "structural_sector_narrative",
        "label": "Critical materials / battery inputs",
        "match_labels": set(),
        "match_sectors": {"basic materials"},
        "keywords": {"lithium", "nickel", "cobalt", "battery material", "rare earth"},
        "default_horizon": "1-3 months",
    },
    "battery_storage_commercialization": {
        "theme_type": "structural_sector_narrative",
        "label": "Battery / storage commercialization",
        "match_labels": {"ai"},
        "match_sectors": {"industrials", "technology", "consumer cyclical"},
        "keywords": {"battery", "solid-state", "storage", "cell technology", "electric vehicle"},
        "default_horizon": "1-3 months",
    },
    "healthcare_commercialization": {
        "theme_type": "structural_sector_narrative",
        "label": "Healthcare / commercialization",
        "match_labels": set(),
        "match_sectors": {"healthcare"},
        "keywords": {"approval", "commercialization", "drug", "device", "trial", "treatment"},
        "default_horizon": "1-3 months",
    },
    "banking_rates_credit": {
        "theme_type": "macro_policy",
        "label": "Banking / rates / credit",
        "match_labels": set(),
        "match_sectors": {"financial services"},
        "keywords": {"rates", "banking", "credit", "loan growth", "net interest margin"},
        "default_horizon": "1-3 months",
    },
    "agriculture_food_supply": {
        "theme_type": "macro_policy",
        "label": "Agriculture / food supply",
        "match_labels": set(),
        "match_sectors": {"consumer defensive", "basic materials"},
        "keywords": {"agriculture", "fertilizer", "grain", "food supply", "crop"},
        "default_horizon": "1-3 months",
    },
    "infrastructure_industrial_capex": {
        "theme_type": "macro_policy",
        "label": "Infrastructure / industrial capex",
        "match_labels": {"eu_policy"},
        "match_sectors": {"industrials", "utilities", "basic materials"},
        "keywords": {"infrastructure", "industrial capex", "grid", "construction", "public works"},
        "default_horizon": "1-3 months",
    },
    "earnings_guidance_momentum": {
        "theme_type": "earnings_guidance",
        "label": "Earnings / guidance momentum",
        "match_labels": {"earnings"},
        "match_sectors": set(),
        "keywords": {"earnings", "guidance"},
        "default_horizon": "1-2 weeks",
    },
    "m_and_a_corporate_action": {
        "theme_type": "m_and_a_corporate_action",
        "label": "M&A / corporate action",
        "match_labels": {"ma"},
        "match_sectors": set(),
        "keywords": {"merger", "acquisition", "takeover"},
        "default_horizon": "1-2 weeks",
    },
    "ipo_listing_momentum": {
        "theme_type": "ipo_listing",
        "label": "IPO / listing momentum",
        "match_labels": {"ipo"},
        "match_sectors": set(),
        "keywords": {"ipo", "listing"},
        "default_horizon": "1-2 weeks",
    },
    "romanian_bvb_local_catalyst": {
        "theme_type": "romanian_bvb_local_catalyst",
        "label": "Romanian / BVB local catalyst",
        "match_labels": {"romania_bvb"},
        "match_sectors": set(),
        "keywords": {"romania", "bucharest", "bvb", "ipo"},
        "default_horizon": "1-3 months",
    },
}


def infer_theme_taxonomy(
    sector: str | None,
    related_news: list[dict],
) -> dict:
    sector_key = (sector or "").lower()
    labels = {news.get("label", "") for news in related_news}
    joined_titles = " ".join(news.get("title", "").lower() for news in related_news)
    interpreted_theme_ids = [news.get("theme_id") for news in related_news if news.get("theme_id")]

    for theme_id in interpreted_theme_ids:
        if theme_id in THEME_TAXONOMY:
            return {"theme_id": theme_id, **THEME_TAXONOMY[theme_id]}

    for theme_id, meta in THEME_TAXONOMY.items():
        if labels & meta["match_labels"]:
            return {"theme_id": theme_id, **meta}
        if sector_key in meta["match_sectors"] and any(keyword in joined_titles for keyword in meta["keywords"]):
            return {"theme_id": theme_id, **meta}

    if sector_key == "technology":
        return {"theme_id": "ai_compute_infrastructure", **THEME_TAXONOMY["ai_compute_infrastructure"]}
    if sector_key == "energy":
        return {"theme_id": "energy_geopolitical_supply_risk", **THEME_TAXONOMY["energy_geopolitical_supply_risk"]}
    if sector_key == "industrials":
        return {"theme_id": "eu_defense_rearmament", **THEME_TAXONOMY["eu_defense_rearmament"]}
    if sector_key == "healthcare":
        return {"theme_id": "healthcare_commercialization", **THEME_TAXONOMY["healthcare_commercialization"]}
    if sector_key == "basic materials":
        return {"theme_id": "commodities_resource_supply_shock", **THEME_TAXONOMY["commodities_resource_supply_shock"]}
    if sector_key == "financial services":
        return {"theme_id": "banking_rates_credit", **THEME_TAXONOMY["banking_rates_credit"]}

    return {
        "theme_id": "generic_sector_momentum",
        "theme_type": "structural_sector_narrative",
        "label": f"{sector or 'Market'} momentum",
        "default_horizon": "1-2 weeks",
    }
