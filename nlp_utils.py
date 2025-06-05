import spacy
from datetime import datetime, timedelta
import re
from typing import Tuple, Optional

# Load Russian language model
try:
    nlp = spacy.load("ru_core_news_sm")
except OSError:
    print("Russian model not found. Please install it using: python -m spacy download ru_core_news_sm")
    raise

def extract_task_info(text: str) -> Tuple[str, str, Optional[datetime], str]:
    """
    Extract task information from natural language text.
    Returns: (title, description, due_date, priority)
    """
    doc = nlp(text)
    
    # Extract title (first sentence)
    title = text.split('.')[0].strip()
    
    # Extract description (rest of the text)
    description = '.'.join(text.split('.')[1:]).strip() if len(text.split('.')) > 1 else ""
    
    # Extract due date
    due_date = None
    date_patterns = [
        r'к (\d{1,2}(?:ому|ому|ому|ому)? [А-Яа-я]+)',
        r'до (\d{1,2}(?:ого|ого|ого|ого)? [А-Яа-я]+)',
        r'завтра',
        r'на следующей неделе',
        r'через (\d+) (?:день|дня|дней)',
        r'через (\d+) (?:неделю|недели|недель)'
    ]
    
    for pattern in date_patterns:
        match = re.search(pattern, text.lower())
        if match:
            if pattern == r'завтра':
                due_date = datetime.now() + timedelta(days=1)
            elif pattern == r'на следующей неделе':
                due_date = datetime.now() + timedelta(days=7)
            elif pattern == r'через (\d+) (?:день|дня|дней)':
                days = int(match.group(1))
                due_date = datetime.now() + timedelta(days=days)
            elif pattern == r'через (\d+) (?:неделю|недели|недель)':
                weeks = int(match.group(1))
                due_date = datetime.now() + timedelta(weeks=weeks)
            break
    
    # Extract priority
    priority = "medium"
    priority_indicators = {
        "high": ["срочно", "срочная", "важно", "важная", "высокий приоритет", "приоритетная"],
        "low": ["низкий приоритет", "не срочно", "когда будет время", "не приоритетная"]
    }
    
    text_lower = text.lower()
    for p, indicators in priority_indicators.items():
        if any(indicator in text_lower for indicator in indicators):
            priority = p
            break
    
    return title, description, due_date, priority

def extract_user_mention(text: str) -> Optional[str]:
    """Extract username from text if mentioned."""
    mention_pattern = r'@(\w+)'
    match = re.search(mention_pattern, text)
    return match.group(1) if match else None 