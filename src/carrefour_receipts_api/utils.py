from typing import List
import pandas as pd
import unicodedata
from rapidfuzz import process, fuzz

def preprocess(text: str):
    """
    Preprocess the text by removing diacritics and converting to lowercase.
    """
    text = text.lower()
    # Normalize to decomposed form (split base characters and diacritics)
    nfkd_form = unicodedata.normalize("NFKD", text)
    text = "".join([c for c in nfkd_form if not unicodedata.combining(c)])

    # Use regex to remove diacritics (Mn = Mark, Nonspacing)
    # text = re.sub(r'\p{Mn}', '', text, flags=re.UNICODE)
    # text = re.sub(r'[^a-zA-Z0-9\s]', ' ', text)
    return text.strip()


def fuzzy_match(row: pd.Series, choices: List[str], scorer=fuzz.WRatio, processor=None, threshold=80):
    """
    Perform fuzzy matching for a single row against a list of choices based on date criterion.
    Returns the best match and its score if above the threshold.
    """
    result = process.extractOne(
        row, choices, scorer=scorer, processor=processor, score_cutoff=threshold
    )
    return result[0] if result is not None else None