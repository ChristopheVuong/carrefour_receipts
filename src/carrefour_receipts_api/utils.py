from itertools import product
from typing import List
import unicodedata

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
from rapidfuzz import process, fuzz


def check_keys(keys: List[str], required_keys: List[str]):
    """
    Checking keys in list for various use
    """
    for k in required_keys:
        if k not in keys:
            raise ValueError(f"Missing required {k}")

def unpack_dict_zip(input_dict):
    """
    Unpacks a dictionary with list values into all pairings.

    Args:
        input_dict (dict): A dictionary where some values may be lists.

    Returns:
        list: A list of dictionaries representing all combinations of the values.
    """
    # Separate keys and their corresponding values
    keys = input_dict.keys()
    normalized_values = [
        value if isinstance(value, list) else [value]  # Wrap non-list values in a list
        for value in input_dict.values()
    ]
    pairings = zip(*normalized_values)
    # Create a list of dictionaries for each combination
    return [dict(zip(keys, row)) for row in pairings]

def unpack_dict_with_combinations(input_dict):
    """
    Unpacks a dictionary with list values into all possible combinations of its values.

    Args:
        input_dict (dict): A dictionary where some values may be lists.

    Returns:
        list: A list of dictionaries representing all combinations of the values.
    """
    # Separate keys and their corresponding values
    keys = input_dict.keys()
    # values = input_dict.values()
    normalized_values = [
        value if isinstance(value, list) else [value]  # Wrap non-list values in a list
        for value in input_dict.values()
    ]

    # Generate all combinations using itertools.product
    combinations = product(*normalized_values)

    # Create a list of dictionaries for each combination
    return [dict(zip(keys, combination)) for combination in combinations]

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


def fuzzy_match(
    row: pd.Series, choices: List[str], scorer=fuzz.WRatio, processor=None, threshold=80
):
    """
    Perform fuzzy matching for a single row against a list of choices based on date criterion.
    Returns the best match and its score if above the threshold.
    """
    result = process.extractOne(
        row, choices, scorer=scorer, processor=processor, score_cutoff=threshold
    )
    return result[0] if result is not None else None


def display_amounts_month(
    df,
    col_amount: str = "totalPaidAmount",
    col_date: str = "dateKey",
    title: str = "Total Amounts by Month",
    show_avg=True,
):
    # df.plot(x='date', y=col_amount, kind='line', title='Total Paid Amount by Year and Month', marker='o')
    # Format the X-axis to show Month-Year
    plt.figure(figsize=(10, 6))
    plt.plot(
        df[col_date],
        df[col_amount],
        marker="o",
        linestyle="-",
        color="b",
        label=col_amount,
    )
    if show_avg:
        # Calculate the average total paid amount
        average_amount = df[col_amount].mean()
        # Add a horizontal line for the average
        plt.axhline(
            y=average_amount,
            color="r",
            linestyle="--",
            linewidth=2,
            label=f"Average {col_amount} ({average_amount:.2f})",
        )

    # Format the X-axis
    plt.gca().xaxis.set_major_formatter(
        mdates.DateFormatter("%b %Y")
    )  # Format as "Jan 2025"
    plt.gca().xaxis.set_major_locator(mdates.MonthLocator())  # Show one tick per month
    plt.xticks(rotation=45)  # Rotate labels for better readability

    # Add labels and title
    plt.title(title)
    plt.xlabel("Month-Year")
    plt.ylabel(col_amount)
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.show()
