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

# Username Clean
def validate_clean_username(value):
    """
    Validates that a username doesn't contain banned words.
    Only checks for exact matches of whole words.
    """
    # Convert to lowercase for case-insensitive matching
    username_lower = value.lower()
    
    # Split the username into words
    words = re.findall(r'\b\w+\b', username_lower)
    
    # Check if any word in the username exactly matches a banned word
    for word in words:
        if word in BANNED_WORDS:
            raise ValidationError(
                "Username contains inappropriate language. Please choose another username.",
                code="inappropriate_language"
            )
    
    return value

# Bio Clean
def validate_clean_content(value):
    """Validates that content doesn't contain banned words."""
    if not value:
        return value
        
    # Convert to lowercase for case-insensitive matching
    content_lower = value.lower()
    
    # Split the content into words
    words = re.findall(r'\b\w+\b', content_lower)
    
    # Check if any word in the content exactly matches a banned word
    for word in words:
        if word in BANNED_WORDS:
            raise ValidationError(
                "Content contains inappropriate language.",
                code="inappropriate_language"
            )
    
    return value