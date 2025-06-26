from itertools import product
import unicodedata

# import numpy as np
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
from rapidfuzz import process, fuzz
from scipy.optimize import linear_sum_assignment


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
    row: pd.Series, choices: list[str], scorer=fuzz.WRatio, processor=None, threshold=80
):
    """
    Perform fuzzy matching for a single row against a list of choices based on date criterion.
    Returns the best match and its score if above the threshold.
    """
    result = process.extractOne(
        row, choices, scorer=scorer, processor=processor, score_cutoff=threshold
    )
    return result[0] if result is not None else None


def find_best_pairings_one_by_one(similarity_matrix) -> tuple[list[int], list[int], list[int], list[int], list[int], list[int]]:
    """
    Naive implementation that try to find the best and second best pairings between group1 and group2 based on the maximum similarity scores globally.
    Note: This is based on the heuristics of selecting the best pair one after and other will give us the best maximum similarity matching.
    Parameters:
        similarity_matrix (np.ndarray): A 2D array where rows are group1 and columns are group2.

    Returns:
        List of tuples: [(group1_index, group2_index), ...] representing the best pairings.
    """
    # Get the dimensions of the similarity matrix
    num_rows, num_cols = similarity_matrix.shape

    # Flatten the similarity matrix into a list of (similarity_score, group1_idx, group2_idx) tuples
    similarity_list = [
        (similarity_matrix[i, j], i, j)
        for i in range(num_rows)
        for j in range(num_cols)
    ]

    # Sort the list by similarity score in descending order
    similarity_list.sort(reverse=True, key=lambda x: x[0])

    # Initialize variables
    row_ind = []
    col_ind = []
    best_similarity_scores = []
    row_ind2 = []
    col_ind2 = []
    second_best_similarity_scores = []
    used_group1_indices = {}  # To track which group1 items have been paired
    used_group2_indices = {}  # To track which group2 items have been paired

    # Iterate over the sorted similarity list
    for similarity_score, group1_idx, group2_idx in similarity_list:
        # Check if both group1_idx and group2_idx are available for best pairing
        if (
            used_group1_indices.get(group1_idx, 0) == 0
            and used_group2_indices.get(group2_idx, 0) == 0
        ):
            row_ind.append(group1_idx)
            col_ind.append(group2_idx)
            best_similarity_scores.append(similarity_score)
            used_group1_indices[group1_idx] = 1 + used_group1_indices.get(group1_idx, 0)
            used_group2_indices[group2_idx] = 1 + used_group2_indices.get(group2_idx, 0)
        else:
            # check if both group1_idx and group2_idx are available for second best pairing
            if (
                used_group1_indices.get(group1_idx, 0) < 2
                and used_group2_indices.get(group2_idx, 0) < 2
            ):
                # Pair group1_idx with group2_idx
                row_ind2.append(group1_idx)
                col_ind2.append(group2_idx)
                second_best_similarity_scores.append(similarity_score)
                used_group1_indices[group1_idx] = 2 + used_group1_indices.get(
                    group1_idx, 0
                )
                used_group2_indices[group2_idx] = 2 + used_group2_indices.get(
                    group2_idx, 0
                )

            # Stop early if all items in either group1 or group2 are paired in the best way
            if len(row_ind) == num_rows:
                break

    return (
        row_ind,
        col_ind, 
        row_ind2,
        col_ind2,
        best_similarity_scores,
        second_best_similarity_scores,
    )


def find_maximum_similarity_matching(similarity_matrix):
    """
    Use of Hungarian Algorithm to find the optimal matching that maximizes the average similarity score.
    Note: This is an instance of the linear sum assignment problem where - similarity_matrix is the cost matrix (minimization instead of maximization).
    If the similarity matrix has more rows than columns, then not every row needs to be assigned to a column, and vice versa
    Parameters:
        similarity_matrix (np.ndarray): A 2D array where rows are group1 and columns are group2.

    Returns:
        List of tuples: [(group1_index, group2_index), ...] representing the best pairing, and the similarity score.
    """
    cost_matrix = -similarity_matrix
    # Solve the assignment problem
    row_ind, col_ind = linear_sum_assignment(cost_matrix)

    # Step 2: Modify the cost matrix to penalize the optimal assignment
    penalty = 1e9  # Large penalty to avoid reusing the same edges
    for i, j in zip(row_ind, col_ind):
        cost_matrix[i][j] += penalty

    # Step 3: Find the second-best assignment
    row_ind2, col_ind2 = linear_sum_assignment(cost_matrix)

    # Calculate the total similarity score for all the assignments
    best_similarity_scores = [similarity_matrix[i][j] for i, j in zip(row_ind, col_ind)]
    second_best_similarity_scores = [similarity_matrix[i][j] for i, j in zip(row_ind2, col_ind2)]

    return (
        row_ind, 
        col_ind,
        row_ind2, 
        col_ind2,
        best_similarity_scores,
        second_best_similarity_scores

    )


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
