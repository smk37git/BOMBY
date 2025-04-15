from django.core.exceptions import ValidationError
import csv
import os
from django.conf import settings
import re

def load_banned_words():
    """
    Load banned words from a CSV file
    """
    banned_words = []
    csv_path = os.path.join(settings.BASE_DIR, 'ACCOUNTS/static/validators/profanity.csv')
    
    try:
        with open(csv_path, 'r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            for row in reader:
                # Assuming 'text' is the column with the banned words
                word = row['text'].lower().strip()
                if word:
                    banned_words.append(word)
    except FileNotFoundError:
        print(f"Warning: Banned words file not found at {csv_path}")
    except KeyError:
        print("Error: 'text' column not found in CSV")
    
    return banned_words

# Cache the banned words list rather than loading it on every validation
BANNED_WORDS = load_banned_words()

# Common false positives to exclude
FALSE_POSITIVES = [
    # Words containing "ass"
    "assert", "assume", "assembly", "assign", "assist", "assignment", "association",
    "assassin", "assault", "asset", "assemble", "assurance", "assay", "assimilate",
    "assistant", "associate", "assertive", "assumption", "assembled", "assorted",
    "assessing", "assent", "passport", "bass", "class", "glass", "pass", "mass",
    "grasshopper", "classic", "classified", "classroom", "classification", "passage",
    "passion", "passive", "compassion", "compass", "embarrass", "harass",
    
    # Words containing "cock"
    "cockpit", "peacock", "hancock", "cockatoo", "cockatiel", "cocktail",
    
    # Words containing "cum"
    "accumulate", "cucumber", "document", "circumference", "circumstance",
    
    # Words containing "dick"
    "dictionary", "predict", "dictate", "verdict", "addiction", "benediction",
    
    # Words containing "fag"
    "fagaceae", "refagor",
    
    # Words containing "ho"
    "house", "home", "hour", "honest", "horizon", "honor", "hope", "host",
    "holiday", "hobby", "hotel", "hospital", "wholesale", "shoulder",
    
    # Words containing "jack"
    "jacket", "jackpot", "hijack",
    
    # Words containing "jerk"
    "jerkiness",
    
    # Words containing "piss"
    "mississippi",
    
    # Words containing "puss"
    "pushy",
    
    # Words containing "pussy"
    "pussycat",
    
    # Words containing "sex"
    "sextet", "sexagesimal", "sexennial", "sextant", "sexist", "sexism", "sexual",
    "sexuality", "sexology", "intersex", "middlesex", "essex", "sussex", "unisex",
    
    # Words containing "shit"
    "worship", "ownership", "leadership", "relationship", "friendship", "hardship",
    "scholarship", "citizenship", "township", "partnership", "dealership",
    
    # Words containing "tit"
    "institute", "institution", "title", "entitle", "titular", "titanic", "titration",
    "constitution", "substitute", "restitution", "petition", "competition", "nutrition",
    "intuition", "quantitative", "titillate", "attitude", "latitude", "gratitude",
    "altitude", "aptitude", "multitude", "platitude", "fortitude",
    
    # Words containing "wank"
    "swank", "swanky",
    
    # Words containing "whore"
    "whorehouse", "whorish",
    
    # Words containing "star"
    "start", "starting", "starter", "started", "restart", "star", "starry", "starvation",
    "starfish", "starboard", "starch", "stare", "staring", "stare", "starving",
    "stardom", "stargazer", "starlet", "starlight", "starship", "superstar", "startle",
    
    # Words containing "rat"
    "strategy", "congratulate", "separate", "elaborate", "celebrate", "accelerate", 
    "vibrate", "decorate", "narrate", "migrate", "quadrate", "moderate", "operate",
    
    # Words containing "scum"
    "scummy", "circumference", "circumstance", "circumvent", 
    "circumnavigate", "circumspect", "circumscribe",
    
    # Other potential false positives
    "analyze", "analytics", "analysis", "analytical", "analytic", "analyst",
    "specialty", "specialist", "special", "species", "specific", "specification",
    "grape", "grapefruit", "grapple", "rapeseed",
    "button", "buttonhole", "buttonhook", "unbuttoned",
    "skyscraper", "scrape", "scrap",
    "basement", "casement"
]

def contains_profanity(text):
    """
    Check for profanity in text while avoiding false positives
    """
    if not text:
        return False
        
    # Normalize text
    normalized = text.lower()
    
    # First check if the text exactly matches any bad word
    if normalized in BANNED_WORDS:
        return True
    
    # Next check for bad words surrounded by word boundaries
    for word in BANNED_WORDS:
        if not word or len(word) < 3:  # Skip empty or very short words
            continue
            
        if re.search(r'\b' + re.escape(word) + r'\b', normalized):
            return True
    
    # Check for obvious combinations with bad words (handles examples from screenshots)
    patterns = [
        r'i?love([a-z]{3,}?)you',  # Catches iloveassyou
        r'([a-z]{3,}?)youhi?',      # Catches assyouhi
        r'([a-z]{3,}?)hi',          # Catches bitchhi
        r'you([a-z]{3,}?)',         # Catches youbitch
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, normalized)
        for match in matches:
            if match in BANNED_WORDS:
                return True
    
    # Special case for assessing specific bad words embedded in text
    # Only check for certain bad words that are commonly embedded
    key_bad_words = [word for word in BANNED_WORDS if len(word) >= 3 and word not in ["ass", "star"]]
    for word in key_bad_words:
        if word in normalized:
            # Make sure it's not a false positive
            if any(fp in normalized for fp in FALSE_POSITIVES):
                # Extra check - only block if the word appears as a standalone segment
                if re.search(r'[^a-z]' + re.escape(word) + r'[^a-z]', ' ' + normalized + ' '):
                    return True
            else:
                return True
    
    # Special check just for 'ass' with stricter rules to avoid false positives
    if 'ass' in normalized:
        # Check if 'ass' is at the beginning, end, or surrounded by non-letters
        if (normalized.startswith('ass') or 
            normalized.endswith('ass') or 
            re.search(r'[^a-z]ass[^a-z]', ' ' + normalized + ' ')):
            return True
        # Also check common patterns like 'assyou'
        if 'assyou' in normalized:
            return True
    
    return False

def validate_clean_username(value):
    """
    Validates that a username doesn't contain banned words.
    """
    if contains_profanity(value):
        raise ValidationError(
            "Username contains inappropriate language. Please choose another username.",
            code="inappropriate_language"
        )
    
    return value

def validate_clean_content(value):
    """
    Validates that content doesn't contain banned words.
    """
    if contains_profanity(value):
        raise ValidationError(
            "Content contains inappropriate language.",
            code="inappropriate_language"
        )
    
    return value