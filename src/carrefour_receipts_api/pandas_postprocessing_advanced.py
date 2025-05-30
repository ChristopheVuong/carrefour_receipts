from typing import Dict, Any

import pandas as pd
import numpy as np
import torch
# import re
from rapidfuzz import fuzz

from utils import preprocess, fuzzy_match

DATA_DIRECTORY = "data"



def batch_cosine_similarity(df1: pd.DataFrame, df2: pd.DataFrame, params: Dict[str, Any]) -> pd.DataFrame:
    """
    Perform batch cosine similarity between groups in df1 and df2.
    Args:
        df1: DataFrame with labels to match.
        df2: DataFrame with labels to match against.
        params: Dictionary containing column names and grouping keys.
    Returns:
        df1: Updated DataFrame with matched labels and similarity scores.
    """
    # Group rows by date
    grouped_df1 = df1[df1[params["newCol"]].notna()].groupby(params["groupby1"])
    grouped_df2 = df2[df2[params["newCol"]].notna()].groupby(params["groupby2"])

    # Collect embeddings and group indices
    embeddings1_list, embeddings2_list = [], []
    group_indices1, group_indices2 = [], []

    for date, group1 in grouped_df1:
        if date not in grouped_df2.groups:
            continue  # Skip if no matching date in df2
        

        group2 = grouped_df2.get_group(date)
        # Fuzzy matching (optional, can be parallelized if needed)
        df1.loc[group1.index, "matchedLabelFuzzy"] = group1[params["col1"]].apply(
            lambda x: fuzzy_match(
                x,
                choices=group2[params["col2"]].unique(),
                scorer=fuzz.WRatio,
                processor=preprocess,
            )
        )
        # Extract embeddings
        embeddings1 = np.vstack(group1[params["newCol"]])
        embeddings2 = np.vstack(group2[params["newCol"]])

        # Append embeddings and group indices
        embeddings1_list.append(embeddings1)
        embeddings2_list.append(embeddings2)
        group_indices1.extend(group1.index)
        group_indices2.extend(group2.index)

    # Convert embeddings to PyTorch tensors
    embeddings1_tensor = torch.tensor(np.vstack(embeddings1_list), dtype=torch.float32)
    embeddings2_tensor = torch.tensor(np.vstack(embeddings2_list), dtype=torch.float32)

    # Normalize embeddings for cosine similarity
    embeddings1_tensor = embeddings1_tensor / embeddings1_tensor.norm(dim=1, keepdim=True)
    embeddings2_tensor = embeddings2_tensor / embeddings2_tensor.norm(dim=1, keepdim=True)

    # Compute batch cosine similarity
    similarity_matrix = torch.mm(embeddings1_tensor, embeddings2_tensor.T)  # Shape: (N, M)

    # Find top matches
    top_values, top_indices = torch.topk(similarity_matrix, k=2, dim=1)  # Top 2 matches

    # Assign best matches
    best_match_indices = top_indices[:, 0].cpu().numpy()
    second_best_match_indices = top_indices[:, 1].cpu().numpy()

    # Map group indices back to original DataFrames
    df1.loc[group_indices1, "matchedLabel1"] = df2.iloc[best_match_indices][params["col2"]].values
    df1.loc[group_indices1, "similarity_score1"] = top_values[:, 0].cpu().numpy()

    # Assign second-best matches
    df1.loc[group_indices1, "matchedLabel2"] = df2.iloc[second_best_match_indices][params["col2"]].values
    df1.loc[group_indices1, "similarity_score2"] = top_values[:, 1].cpu().numpy()

    return df1