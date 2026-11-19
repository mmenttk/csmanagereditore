"""Static game constants, enums, and localization mappings for CS Manager Database, Balance & Weapons."""

NATIONS = {
    1: "Afghanistan", 2: "Albania", 3: "Algeria", 4: "Andorra", 5: "Argentina",
    6: "Armenia", 7: "Australia", 8: "Austria", 9: "Azerbaijan", 10: "Bahrain",
    11: "Bangladesh", 12: "Belarus", 13: "Belgium", 14: "Bolivia",
    15: "Bosnia and Herzegovina", 16: "Brazil", 17: "Bulgaria", 18: "Canada",
    19: "Chile", 20: "China", 21: "Colombia", 22: "Costa Rica", 23: "Croatia",
    24: "Cuba", 25: "Cyprus", 26: "Czechia", 27: "Denmark", 28: "Ecuador",
    29: "Egypt", 30: "Eritrea", 31: "Estonia", 32: "Ethiopia", 33: "Finland",
    34: "France", 35: "Georgia", 36: "Germany", 37: "Ghana", 38: "Greece",
    39: "Honduras", 40: "Hungary", 41: "Iceland", 42: "India", 43: "Indonesia",
    44: "Iran", 45: "Iraq", 46: "Ireland", 47: "Israel", 48: "Italy",
    49: "Japan", 50: "Jordan", 51: "Kazakhstan", 52: "Kenya", 53: "Latvia",
    54: "Liechtenstein", 55: "Lithuania", 56: "Luxembourg", 57: "Malaysia",
    58: "Malta", 59: "Mexico", 60: "Moldova", 61: "Monaco", 62: "Mongolia",
    63: "Montenegro", 64: "Morocco", 65: "Nepal", 66: "Netherlands",
    67: "New Zealand", 68: "Nigeria", 69: "North Macedonia", 70: "Norway",
    71: "Oman", 72: "Pakistan", 73: "Palestine", 74: "Panama", 75: "Paraguay",
    76: "Peru", 77: "Philippines", 78: "Poland", 79: "Portugal", 80: "Qatar",
    81: "Romania", 82: "Russia", 83: "Saudi Arabia", 84: "Serbia",
    85: "Singapore", 86: "Slovakia", 87: "Slovenia", 88: "Somalia",
    89: "South Africa", 90: "South Korea", 91: "Spain", 92: "Sri Lanka",
    93: "Sweden", 94: "Switzerland", 95: "Syria", 96: "Thailand", 97: "Tunisia",
    98: "Turkey", 99: "Ukraine", 100: "United Arab Emirates",
    101: "United Kingdom", 102: "United States", 103: "Uruguay",
    104: "Uzbekistan", 105: "Venezuela", 106: "Vietnam", 107: "Guatemala",
    108: "Kosovo", 109: "Lebanon",
}

NATION_REGIONS = {
    # 0 = Europe, 1 = Americas, 2 = Asia / Oceania / MENA-Asia
    1: 2, 2: 0, 3: 0, 4: 0, 5: 1, 6: 0, 7: 2, 8: 0, 9: 0, 10: 2,
    11: 2, 12: 0, 13: 0, 14: 1, 15: 0, 16: 1, 17: 0, 18: 1, 19: 1, 20: 2,
    21: 1, 22: 1, 23: 0, 24: 1, 25: 0, 26: 0, 27: 0, 28: 1, 29: 0, 30: 0,
    31: 0, 32: 0, 33: 0, 34: 0, 35: 0, 36: 0, 37: 0, 38: 0, 39: 1, 40: 0,
    41: 0, 42: 2, 43: 2, 44: 2, 45: 2, 46: 0, 47: 0, 48: 0, 49: 2, 50: 2,
    51: 2, 52: 0, 53: 0, 54: 0, 55: 0, 56: 0, 57: 2, 58: 0, 59: 1, 60: 0,
    61: 0, 62: 2, 63: 0, 64: 0, 65: 2, 66: 0, 67: 2, 68: 0, 69: 0, 70: 0,
    71: 2, 72: 2, 73: 2, 74: 1, 75: 1, 76: 1, 77: 2, 78: 0, 79: 0, 80: 2,
    81: 0, 82: 0, 83: 2, 84: 0, 85: 2, 86: 0, 87: 0, 88: 0, 89: 0, 90: 2,
    91: 0, 92: 2, 93: 0, 94: 0, 95: 2, 96: 2, 97: 0, 98: 0, 99: 0, 100: 2,
    101: 0, 102: 1, 103: 1, 104: 2, 105: 1, 106: 2, 107: 1, 108: 0, 109: 2,
}

LANGUAGES = {
    1: "Albanian", 2: "Arabic", 3: "Armenian", 4: "Belarusian", 5: "BCMS",
    6: "Bulgarian", 7: "Cantonese", 8: "Chinese", 9: "Catalan", 10: "Czech",
    11: "Danish", 12: "Dutch", 13: "English", 14: "Estonian", 15: "Finnish",
    16: "French", 17: "Georgian", 18: "German", 19: "Hebrew", 20: "Hindi",
    21: "Hungarian", 22: "Icelandic", 23: "Indonesian", 24: "Italian",
    25: "Japanese", 26: "Korean", 27: "Kurdish", 28: "Latvian",
    29: "Lithuanian", 30: "Macedonian", 31: "Maltese", 32: "Mongolian",
    33: "Norwegian", 34: "Persian", 35: "Polish", 36: "Portuguese",
    37: "Romanian", 38: "Russian", 39: "Spanish", 40: "Swedish", 41: "Thai",
    42: "Turkish", 43: "Ukrainian", 44: "Vietnamese", 45: "Greek",
    46: "Moldovan", 47: "Slovakian", 48: "Slovenian",
}

PLAYER_SKILLS = [
    {"id": 1, "key": "tracking", "label": "Tracking", "group": "Mechanics"},
    {"id": 2, "key": "sprayControl", "label": "Spray Control", "group": "Mechanics"},
    {"id": 3, "key": "reactions", "label": "Reactions", "group": "Mechanics"},
    {"id": 4, "key": "crosshairPlacement", "label": "Crosshair Placement", "group": "Mechanics"},
    {"id": 5, "key": "flicks", "label": "Flicks", "group": "Mechanics"},
    {"id": 6, "key": "movement", "label": "Movement", "group": "Mechanics"},
    {"id": 7, "key": "pistols", "label": "Pistols", "group": "Weapons"},
    {"id": 8, "key": "smgs", "label": "SMGs", "group": "Weapons"},
    {"id": 9, "key": "rifles", "label": "Rifles", "group": "Weapons"},
    {"id": 10, "key": "snipers", "label": "Snipers", "group": "Weapons"},
    {"id": 11, "key": "overview", "label": "Overview", "group": "Mental"},
    {"id": 12, "key": "decisions", "label": "Decisions", "group": "Mental"},
    {"id": 13, "key": "composure", "label": "Composure", "group": "Mental"},
    {"id": 14, "key": "teamwork", "label": "Teamwork", "group": "Mental"},
    {"id": 15, "key": "consistency", "label": "Consistency", "group": "Mental"},
    {"id": 16, "key": "aggression", "label": "Aggression", "group": "Mental"},
    {"id": 17, "key": "utility", "label": "Utility", "group": "Mental"},
    {"id": 18, "key": "leadership", "label": "Leadership", "group": "Mental"},
]

STAFF_SKILLS = [
    {"id": 1, "key": "tactical", "label": "Tactical"},
    {"id": 2, "key": "mental", "label": "Mental"},
    {"id": 3, "key": "youngsters", "label": "Youngsters"},
    {"id": 4, "key": "discipline", "label": "Discipline"},
    {"id": 5, "key": "motivation", "label": "Motivation"},
    {"id": 6, "key": "judgingAbility", "label": "Judging Ability"},
    {"id": 7, "key": "judgingPotential", "label": "Judging Potential"},
]

PLAYER_MENTALITIES = {0: "Strict", 1: "Balanced", 2: "Loose"}
STAFF_MENTALITIES = {0: "Strict", 1: "Balanced", 2: "Loose", 3: "None / Flexible"}
PLAYER_STATUS = {0: "Star", 1: "Regular", 2: "Support", 3: "Expendable"}
ROLE_STATUS = {0: "Primary", 1: "Secondary", 2: "None"}
TRANSFER_STATUS = {0: "Not Listed", 1: "Listed", 2: "Reject All Offers"}
CONTRACT_TYPE = {0: "Own", 1: "Loan"}
STAFF_ROLES = {
    0: "Head Coach", 1: "Assistant Coach", 2: "Analyst",
    3: "Performance Coach", 4: "Scout", 5: "Head of Academy",
}

PLAYER_POSITIONS = {
    0: "Entry", 1: "Lurker", 2: "Closer", 3: "Midrounder",
    4: "Roamer (Attack)", 5: "Anchor", 6: "Rotator", 7: "Mid", 8: "Roamer (Defense)",
}

PROFESSIONAL_STATUS = {0: "Amateur", 1: "Semi-Pro", 2: "Pro"}
HIRING_BIAS = {
    0: "Only National", 1: "Only National Language", 2: "Partly National",
    3: "Weakly National", 4: "Only Regional", 5: "Partly Regional",
    6: "Weakly Regional", 7: "International",
}
ACADEMY_FOCUS = {0: "National", 1: "Regional", 2: "International"}

RELATIONSHIP_TYPES = {
    0: "Rival",
    1: "Friend",
    2: "Mentor / Former Teammate",
    3: "Strong Bond",
    4: "Chemistry Link",
}

AWARD_TYPES = {
    0: "Tournament MVP",
    1: "Tournament EVP",
    2: "Honorable Mention",
    3: "Top-20 Player of the Year",
}

PERSONALITY_AXES = [
    {"key": "quietPassion", "label": "Temperament", "low": "Quiet", "high": "Passionate"},
    {"key": "kindMean", "label": "Demeanor", "low": "Kind", "high": "Mean"},
    {"key": "loyalMercenary", "label": "Loyalty", "low": "Loyal", "high": "Mercenary"},
    {"key": "contentAmbition", "label": "Ambition", "low": "Content", "high": "Ambitious"},
    {"key": "stressproneResillient", "label": "Composure Type", "low": "Stress-prone", "high": "Resilient"},
    {"key": "desireToIgl", "label": "Desire to IGL", "low": "Low", "high": "High"},
    {"key": "desireToAwp", "label": "Desire to AWP", "low": "Low", "high": "High"},
]

PORTRAIT_FIELDS = [
    {"key": "face", "label": "Face Shape", "min": 1, "max": 3, "group": "Head & Skin"},
    {"key": "neck", "label": "Neck", "min": 1, "max": 2, "group": "Head & Skin"},
    {"key": "skinColor", "label": "Skin Tone", "min": 1, "max": 5, "group": "Head & Skin"},
    {"key": "wrinkes", "label": "Wrinkles", "min": 0, "max": 4, "group": "Head & Skin"},
    {"key": "eyes", "label": "Eyes Style", "min": 1, "max": 12, "group": "Eyes & Brows"},
    {"key": "eyeballsColor", "label": "Eye Color", "min": 1, "max": 7, "group": "Eyes & Brows"},
    {"key": "eyebrows", "label": "Eyebrows Style", "min": 1, "max": 11, "group": "Eyes & Brows"},
    {"key": "eyebrowsColor", "label": "Eyebrows Color", "min": 1, "max": 7, "group": "Eyes & Brows"},
    {"key": "nose", "label": "Nose Style", "min": 1, "max": 11, "group": "Nose & Mouth"},
    {"key": "mouth", "label": "Mouth Style", "min": 1, "max": 13, "group": "Nose & Mouth"},
    {"key": "mouthColor", "label": "Lip / Mouth Color", "min": 1, "max": 6, "group": "Nose & Mouth"},
    {"key": "hair", "label": "Hair Style (0=Bald)", "min": 0, "max": 43, "group": "Hair & Beard"},
    {"key": "hairColor", "label": "Hair Color", "min": 1, "max": 9, "group": "Hair & Beard"},
    {"key": "beard", "label": "Beard Style (0=None)", "min": 0, "max": 15, "group": "Hair & Beard"},
    {"key": "beardColor", "label": "Beard Color", "min": 0, "max": 9, "group": "Hair & Beard"},
    {"key": "accessory", "label": "Glasses / Accessory (0=None)", "min": 0, "max": 5, "group": "Accessories"},
    {"key": "accessoryColor", "label": "Accessory Color", "min": 0, "max": 4, "group": "Accessories"},
]

# Tournament & Stage Enums (verified from Assembly-CSharp.dll)
FORMAT_TYPES = {
    0: "Single Elimination Bracket",
    1: "League / Round-Robin Groups",
    2: "Swiss System",
    3: "Double Elimination Bracket",
}
VENUES = {0: "Online", 1: "Studio LAN", 2: "Arena LAN"}
REGIONS = {0: "EU", 1: "Americas", 2: "Asia", 3: "World (Global)"}
DYNAMIC_LOCATIONS = {0: "Fixed", 1: "Inside Region", 2: "Worldwide Rotating"}
PROGRESS_TYPES = {
    0: "Final / Payout Only",
    1: "Advance to Next Stage",
    2: "League Relegation",
    3: "League Stay",
    4: "League Promotion",
}
SESSION_SLOTS = {1: "Slot 1 (10:00)", 2: "Slot 2 (13:00)", 3: "Slot 3 (16:00)"}
DAYS_OF_WEEK = {1: "Mon", 2: "Tue", 3: "Wed", 4: "Thu", 5: "Fri", 6: "Sat", 7: "Sun"}

STAGE_NAME_LABELS = {
    "OPEN_QUALIFIER__CONTEXT_TOURNAMENT_STAGE_NAME": "Open Qualifier",
    "CLOSED_QUALIFIER__CONTEXT_TOURNAMENT_STAGE_NAME": "Closed Qualifier",
    "QUALIFIERS__CONTEXT_TOURNAMENT_STAGE_NAME": "Qualifiers",
    "EUROPEAN_QUALIFIER__CONTEXT_TOURNAMENT_STAGE_NAME": "European Qualifier",
    "AMERICAS_QUALIFIER__CONTEXT_TOURNAMENT_STAGE_NAME": "Americas Qualifier",
    "ASIAN_QUALIFIER__CONTEXT_TOURNAMENT_STAGE_NAME": "Asian Qualifier",
    "PLAY_IN__CONTEXT_TOURNAMENT_STAGE_NAME": "Play-In",
    "STAGE_1__CONTEXT_TOURNAMENT_STAGE_NAME": "Stage 1",
    "STAGE_2__CONTEXT_TOURNAMENT_STAGE_NAME": "Stage 2",
    "STAGE_3__CONTEXT_TOURNAMENT_STAGE_NAME": "Stage 3",
    "GROUPS__CONTEXT_TOURNAMENT_STAGE_NAME": "Groups",
    "PLAYOFFS__CONTEXT_TOURNAMENT_STAGE_NAME": "Playoffs",
    "FINALS__CONTEXT_TOURNAMENT_STAGE_NAME": "Finals",
}

STAGE_NAME_KEYS = list(STAGE_NAME_LABELS.keys())


def format_stage_name(raw_name: str | None) -> str:
    if not raw_name:
        return "Stage"
    if raw_name in STAGE_NAME_LABELS:
        return STAGE_NAME_LABELS[raw_name]
    cleaned = str(raw_name).replace("__CONTEXT_TOURNAMENT_STAGE_NAME", "").replace("_", " ").strip()
    return cleaned.title() if cleaned else "Stage"


# Exact counts from Tournament.GetNumberOfAwards(Award) + Tournament.GetTier() + GetReputationStars()
def awards_for_reputation(reputation: int) -> dict:
    r = max(1, min(20, int(reputation or 1)))
    mvp = 1 if r >= 13 else 0
    if r == 20:
        evp = 7
    elif r == 19:
        evp = 6
    elif r >= 17:
        evp = 5
    elif r >= 14:
        evp = 4
    elif r >= 11:
        evp = 3
    elif r >= 9:
        evp = 2
    elif r == 8:
        evp = 1
    else:
        evp = 0

    if r >= 13:
        hm = 0
    elif r >= 11:
        hm = 2
    elif r >= 9:
        hm = 3
    elif r == 8:
        hm = 4
    else:
        hm = 5

    tier = classify_tournament_tier(r)
    return {
        "reputation": r,
        "engineTier": tier["engineTier"],
        "stars": (r + 1) // 2,
        "tierLabel": tier["label"],
        "subBand": tier["subCode"],
        "tierSubCode": tier["subCode"],
        "mvp": mvp,
        "evp": evp,
        "honorableMentions": hm,
        "totalAwards": mvp + evp + hm,
    }


# Exact thresholds from Tournament.GetTier() in Assembly-CSharp.dll
# Tier 5: rep >= 19 (Major / Flagship)
# Tier 4: rep >= 13 (S-Tier)
# Tier 3: rep >= 9  (A-Tier)
# Tier 2: rep >= 5  (B-Tier)
# Tier 1: rep < 5   (C-Tier / Regional)
def classify_tournament_tier(reputation: int) -> dict:
    r = int(reputation or 0)
    if r >= 19:
        return {"engineTier": 5, "code": "S", "subCode": "Major", "label": "S-Tier / Major (T5)", "color": "#f59e0b"}
    if r >= 13:
        return {"engineTier": 4, "code": "S", "subCode": "S-Tier", "label": "S-Tier (T4)", "color": "#a855f7"}
    if r >= 9:
        return {"engineTier": 3, "code": "A", "subCode": "A-Tier", "label": "A-Tier (T3)", "color": "#38bdf8"}
    if r >= 5:
        return {"engineTier": 2, "code": "B", "subCode": "B-Tier", "label": "B-Tier (T2)", "color": "#22c55e"}
    return {"engineTier": 1, "code": "C", "subCode": "C-Tier", "label": "C-Tier / Regional (T1)", "color": "#94a3b8"}


AWARD_BREAKDOWN_BY_REP = [awards_for_reputation(r) for r in range(20, 0, -1)]


WEAPON_TYPES = {0: "Pistol", 1: "SMG", 2: "Rifle", 3: "Sniper"}
WEAPON_AVAILABILITY = {0: "T-Side Only (Attack)", 1: "CT-Side Only (Defense)", 2: "Both Sides"}
WEAPON_TIERS = {1: "Starter / Tier 1", 2: "Sidearm / Tier 2", 3: "SMG / Tier 3", 4: "Budget Rifle / Scout (Tier 4)", 5: "Main Rifle / Auto (Tier 5)", 6: "AWP / Flagship (Tier 6)"}

MAP_IDS = [1, 2, 3, 4, 5, 6, 7]
MAP_NAMES = {
    1: "Mirage", 2: "Inferno", 3: "Nuke", 4: "Overpass",
    5: "Vertigo", 6: "Ancient", 7: "Anubis", 8: "Dust II", 9: "Train",
}
