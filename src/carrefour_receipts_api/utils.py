from itertools import product

# import numpy as np
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

# Matching primitives live in `matching` (no matplotlib) so the dbt Python model
# can reuse them; re-exported here for backward compatibility.
from carrefour_receipts_api.matching import (  # noqa: F401
    find_best_pairings_one_by_one,
    find_maximum_similarity_matching,
    fuzzy_match,
    match_loyalty_to_receipts,
    preprocess,
)


def check_keys(keys: list[str], required_keys: list[str]):
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


def input_from_csv(
    df: pd.DataFrame,
    filepath: str,
    column_name: str,
):
    """
    Input categories from external csv in `column_name`.
    Args:
        df: the dataframe where to input
        filepath: the path to the file containing data to input
        column_name: the column_name for input
    """
    input_df = pd.read_csv(filepath)
    if isinstance(column_name, str):
        merged_df = pd.merge(
            df, input_df, on=column_name, how="left", suffixes=("_original", "_imputed")
        )
    else:
        raise ValueError("column_name should be a string")
    return merged_df


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
