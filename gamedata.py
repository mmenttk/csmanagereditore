"""Static game constants, enums, and localization mappings for CS Manager."""

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

PLAYER_MENTALITIES = {
    0: "Strict",
    1: "Balanced",
    2: "Loose",
}

STAFF_MENTALITIES = {
    0: "Strict",
    1: "Balanced",
    2: "Loose",
    3: "None / Flexible",
}

PLAYER_STATUS = {
    0: "Star",
    1: "Regular",
    2: "Support",
    3: "Expendable",
}

ROLE_STATUS = {
    0: "Primary",
    1: "Secondary",
    2: "None",
}

TRANSFER_STATUS = {
    0: "Not Listed",
    1: "Listed",
    2: "Reject All Offers",
}

CONTRACT_TYPE = {
    0: "Own",
    1: "Loan",
}

STAFF_ROLES = {
    0: "Head Coach",
    1: "Assistant Coach",
    2: "Analyst",
    3: "Performance Coach",
    4: "Scout",
    5: "Head of Academy",
}

# Player.mapPositionAttributes.positionType (0..8)
PLAYER_POSITIONS = {
    0: "Entry",
    1: "Lurker",
    2: "Closer",
    3: "Midrounder",
    4: "Roamer (Attack)",
    5: "Anchor",
    6: "Rotator",
    7: "Mid",
    8: "Roamer (Defense)",
}

# MapPosition.positionType inside Team.mapTactics (0..10)
MAP_TACTIC_POSITIONS = {
    0: "Closer (T)",
    1: "Lurker (T)",
    2: "Midrounder (T)",
    3: "Roamer (T)",
    4: "Entry (T)",
    5: "A Anchor (CT)",
    6: "A Rotator (CT)",
    7: "B Anchor (CT)",
    8: "B Rotator (CT)",
    9: "Mid (CT)",
    10: "Roamer (CT)",
}

# Mapping from MapPosition.positionType (0..10) -> Player.mapPositionAttributes.positionType (0..8)
MAP_POS_TO_PLAYER_ATTR = {
    0: 2,   # closer -> closer
    1: 1,   # lurker -> lurker
    2: 3,   # midrounder -> midrounder
    3: 4,   # roamerAttack -> roamerAttack
    4: 0,   # entry -> entry
    5: 5,   # aAnchor -> anchor
    6: 6,   # aRotator -> rotator
    7: 5,   # bAnchor -> anchor
    8: 6,   # bRotator -> rotator
    9: 7,   # mid -> mid
    10: 8,  # roamerDefense -> roamerDefense
}

PROFESSIONAL_STATUS = {
    0: "Amateur",
    1: "Semi-Pro",
    2: "Pro",
}

HIRING_BIAS = {
    0: "Only National",
    1: "Only National Language",
    2: "Partly National",
    3: "Weakly National",
    4: "Only Regional",
    5: "Partly Regional",
    6: "Weakly Regional",
    7: "International",
}

ACADEMY_FOCUS = {
    0: "National",
    1: "Regional",
    2: "International",
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
