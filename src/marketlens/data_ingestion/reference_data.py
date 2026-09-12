"""Reference data for interpreting the Olist dataset.

Olist ships state codes but not regions, and category names in Portuguese with
a translation file that misses two categories. Both gaps are filled here so
the fix is auditable in one place rather than buried in a transform.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Brazilian geography
# ---------------------------------------------------------------------------
# The five official IBGE macro-regions. Regional analysis matters here because
# Brazil is a continent-sized market: freight cost and delivery time from the
# Sao Paulo seller cluster to the North differ enormously from deliveries
# within the Southeast.

STATE_NAMES: dict[str, str] = {
    "AC": "Acre", "AL": "Alagoas", "AP": "Amapa", "AM": "Amazonas",
    "BA": "Bahia", "CE": "Ceara", "DF": "Distrito Federal",
    "ES": "Espirito Santo", "GO": "Goias", "MA": "Maranhao",
    "MT": "Mato Grosso", "MS": "Mato Grosso do Sul", "MG": "Minas Gerais",
    "PA": "Para", "PB": "Paraiba", "PR": "Parana", "PE": "Pernambuco",
    "PI": "Piaui", "RJ": "Rio de Janeiro", "RN": "Rio Grande do Norte",
    "RS": "Rio Grande do Sul", "RO": "Rondonia", "RR": "Roraima",
    "SC": "Santa Catarina", "SP": "Sao Paulo", "SE": "Sergipe",
    "TO": "Tocantins",
}

STATE_TO_REGION: dict[str, str] = {
    # North
    "AC": "North", "AP": "North", "AM": "North", "PA": "North",
    "RO": "North", "RR": "North", "TO": "North",
    # Northeast
    "AL": "Northeast", "BA": "Northeast", "CE": "Northeast", "MA": "Northeast",
    "PB": "Northeast", "PE": "Northeast", "PI": "Northeast",
    "RN": "Northeast", "SE": "Northeast",
    # Central-West
    "DF": "Central-West", "GO": "Central-West",
    "MT": "Central-West", "MS": "Central-West",
    # Southeast
    "ES": "Southeast", "MG": "Southeast", "RJ": "Southeast", "SP": "Southeast",
    # South
    "PR": "South", "RS": "South", "SC": "South",
}

REGIONS: tuple[str, ...] = ("North", "Northeast", "Central-West", "Southeast", "South")

#: Region ordered roughly by distance from the Sao Paulo seller cluster, which
#: is what drives freight cost and delivery time.
REGION_DISTANCE_RANK: dict[str, int] = {
    "Southeast": 1, "South": 2, "Central-West": 3, "Northeast": 4, "North": 5,
}


# ---------------------------------------------------------------------------
# Product categories
# ---------------------------------------------------------------------------
# Olist's product_category_name_translation.csv covers 71 of the 73 categories
# present in the product table. These two are missing from it; the English
# names follow the same conventions as the supplied file.

MISSING_CATEGORY_TRANSLATIONS: dict[str, str] = {
    "pc_gamer": "pc_gamer",
    "portateis_cozinha_e_preparadores_de_alimentos":
        "portable_kitchen_and_food_preparers",
}

#: Products with no category at all in the source (610 of 32,951).
UNKNOWN_CATEGORY = "unknown"

#: Grouping the 73 leaf categories into something a business conversation can
#: actually use. Olist's own taxonomy is very long-tailed, and a chart with 73
#: bars communicates nothing. Leaf categories remain available for drill-down.
CATEGORY_GROUPS: dict[str, str] = {
    # Home
    "bed_bath_table": "Home & Furniture",
    "furniture_decor": "Home & Furniture",
    "housewares": "Home & Furniture",
    "home_confort": "Home & Furniture",
    "home_comfort_2": "Home & Furniture",
    "furniture_living_room": "Home & Furniture",
    "furniture_bedroom": "Home & Furniture",
    "furniture_mattress_and_upholstery": "Home & Furniture",
    "kitchen_dining_laundry_garden_furniture": "Home & Furniture",
    "office_furniture": "Home & Furniture",
    "portable_kitchen_and_food_preparers": "Home & Furniture",
    "la_cuisine": "Home & Furniture",
    "flowers": "Home & Furniture",
    "christmas_supplies": "Home & Furniture",
    # Health & Beauty
    "health_beauty": "Health & Beauty",
    "perfumery": "Health & Beauty",
    "diapers_and_hygiene": "Health & Beauty",
    # Technology
    "computers_accessories": "Technology",
    "telephony": "Technology",
    "fixed_telephony": "Technology",
    "electronics": "Technology",
    "computers": "Technology",
    "pc_gamer": "Technology",
    "tablets_printing_image": "Technology",
    "audio": "Technology",
    "consoles_games": "Technology",
    "cine_photo": "Technology",
    "dvds_blu_ray": "Technology",
    "music": "Technology",
    "cds_dvds_musicals": "Technology",
    "musical_instruments": "Technology",
    "signaling_and_security": "Technology",
    "security_and_services": "Technology",
    # Appliances
    "small_appliances": "Appliances",
    "home_appliances": "Appliances",
    "home_appliances_2": "Appliances",
    "small_appliances_home_oven_and_coffee": "Appliances",
    "air_conditioning": "Appliances",
    # Fashion
    "watches_gifts": "Fashion & Accessories",
    "fashion_bags_accessories": "Fashion & Accessories",
    "fashion_shoes": "Fashion & Accessories",
    "fashion_male_clothing": "Fashion & Accessories",
    "fashion_underwear_beach": "Fashion & Accessories",
    "fashion_female_clothing": "Fashion & Accessories",
    "fashion_sport": "Fashion & Accessories",
    "fashion_childrens_clothes": "Fashion & Accessories",
    # Olist's own translation file contains this typo; kept verbatim so the
    # mapping matches the source rather than a corrected version of it.
    "fashio_female_clothing": "Fashion & Accessories",
    "luggage_accessories": "Fashion & Accessories",
    # Leisure
    "sports_leisure": "Sports & Leisure",
    "toys": "Sports & Leisure",
    "garden_tools": "Sports & Leisure",
    "cool_stuff": "Sports & Leisure",
    "party_supplies": "Sports & Leisure",
    "art": "Sports & Leisure",
    "arts_and_craftmanship": "Sports & Leisure",
    "books_general_interest": "Sports & Leisure",
    "books_technical": "Sports & Leisure",
    "books_imported": "Sports & Leisure",
    "stationery": "Sports & Leisure",
    "baby": "Sports & Leisure",
    "pet_shop": "Sports & Leisure",
    "food": "Sports & Leisure",
    "food_drink": "Sports & Leisure",
    "drinks": "Sports & Leisure",
    "market_place": "Sports & Leisure",
    # Industry & Construction
    "construction_tools_construction": "Industry & Construction",
    "construction_tools_safety": "Industry & Construction",
    "construction_tools_lights": "Industry & Construction",
    "construction_tools_garden": "Industry & Construction",
    "costruction_tools_garden": "Industry & Construction",
    "costruction_tools_tools": "Industry & Construction",
    "home_construction": "Industry & Construction",
    "industry_commerce_and_business": "Industry & Construction",
    "agro_industry_and_commerce": "Industry & Construction",
    "auto": "Industry & Construction",
    "office_furniture_2": "Industry & Construction",
    "insurance_and_services": "Industry & Construction",
}

DEFAULT_CATEGORY_GROUP = "Other"


def region_for_state(state: str | None) -> str:
    """Map a two-letter state code to its IBGE macro-region."""
    if not state:
        return "Unknown"
    return STATE_TO_REGION.get(str(state).strip().upper(), "Unknown")


def group_for_category(category_en: str | None) -> str:
    """Map a leaf category to its business grouping."""
    if not category_en:
        return DEFAULT_CATEGORY_GROUP
    return CATEGORY_GROUPS.get(str(category_en).strip().lower(), DEFAULT_CATEGORY_GROUP)
