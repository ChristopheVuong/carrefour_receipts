"""
Utility functions for data analysis and manipulation with Pandas.
Note: We keep this system with Pandas that we can replace with Spark if needed.
TODO: Write classes for major join operations
"""

from functools import lru_cache
from typing import Dict, Any

import pandas as pd
import numpy as np
from rapidfuzz import fuzz
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

from carrefour_receipts_api.utils import preprocess, fuzzy_match

DATA_DIRECTORY = "data"


def embedding_to_df(
    model,
    df: pd.DataFrame,
    column_name: str,
    new_column_name: str = "embeddingLabel",
    filter_out: str | None = None,
    filter_in: str | None = None,
):
    """
    In-place computation of embedding for labels in a DataFrame.
    Args:
        model : SentenceTransformer model
        df : DataFrame with labels
        column_name : column with labels
        new_column_name : column to store embeddings
        filter_out : filter out rows containing this string
        filter_in : filter in rows containing this string
    """
    if filter_in:
        mask = (df[column_name].notna()) & (df[column_name].str.contains(filter_in))
        df.loc[mask, new_column_name] = df.loc[mask, column_name].apply(
            lambda x: get_cached_encode(model, x)
        )
    else:
        if filter_out:
            mask = (df[column_name].isna()) | (df[column_name].str.contains(filter_out))
        else:
            mask = df[column_name].isna()
        df.loc[~mask, new_column_name] = df.loc[~mask, column_name].apply(
            lambda x: get_cached_encode(model, x)
        )


# Define a cached version of the embedding function
def get_cached_encode(model, text):
    """
    Get the embedding for a given text using the specified model.
    Args:
        model : SentenceTransformer model
        text : input text
        Returns: embedding vector for the input text
    """

    @lru_cache(maxsize=None)  # Cache all results
    def cached_encode(text):
        return model.encode(preprocess(text))

    return cached_encode(text)


def embedding_batch_to_df(
    model,
    df: pd.DataFrame,
    column_name: str,
    new_column_name: str = "embeddingLabel",
    filter_out: str | None = None,
    filter_in: str | None = None,
    batch_size: int = 32,  # Batch size for encoding
):
    """
    In-place computation of embedding for labels in a DataFrame using batch processing.
    Args:
        model : SentenceTransformer model
        df : DataFrame with labels
        column_name : column with labels
        new_column_name : column to store embeddings
        filter_out : filter out rows containing this string
        filter_in : filter in rows containing this string
        batch_size : batch size for encoding
    TODO: unique embeddings and association
    """
    if filter_in:
        mask = (df[column_name].notna()) & (df[column_name].str.contains(filter_in))
        target_data = df.loc[mask, column_name]
    else:
        if filter_out:
            mask = (df[column_name].isna()) | (df[column_name].str.contains(filter_out))
        else:
            mask = df[column_name].isna()
        target_data = df.loc[~mask, column_name]

    # Compute embeddings in batches
    embeddings = model.encode(
        target_data.tolist(),
        batch_size=batch_size,
        show_progress_bar=True,
        convert_to_tensor=False,
    )

    # Assign embeddings back to the DataFrame
    df.loc[target_data.index, new_column_name] = list(embeddings)


from collections import defaultdict


def embedding_batch_unique_to_df(
    model,
    df: pd.DataFrame,
    column_name: str,
    new_column_name: str = "embeddingLabel",
    filter_out: str | None = None,
    filter_in: str | None = None,
    batch_size: int = 32,  # Batch size for encoding
):
    """
    In-place computation of embedding for labels in a DataFrame using unique items.
    Args:
        model : SentenceTransformer model
        df : DataFrame with labels
        column_name : column with labels
        new_column_name : column to store embeddings
        filter_out : filter out rows containing this string
        filter_in : filter in rows containing this string
    """
    # Apply filters
    if filter_in:
        mask = (df[column_name].notna()) & (df[column_name].str.contains(filter_in))
        target_data = df.loc[mask, column_name]
    else:
        if filter_out:
            mask = (df[column_name].isna()) | (df[column_name].str.contains(filter_out))
        else:
            mask = df[column_name].isna()
        target_data = df.loc[~mask, column_name]

    # Step 1: Identify unique items and their indices
    unique_items_dict = defaultdict(list)
    for idx, item in enumerate(target_data):
        unique_items_dict[item].append(idx)

    # Step 2: Compute embeddings for unique items
    unique_items = list(unique_items_dict.keys())
    embeddings = model.encode(
        unique_items, batch_size=batch_size, show_progress_bar=True
    )

    # Step 3: Map embeddings back to the original indices
    embedding_dict = dict(zip(unique_items, embeddings))
    result_embeddings = [embedding_dict[item] for item in target_data]

    # Step 4: Assign embeddings back to the DataFrame
    df.loc[target_data.index, new_column_name] = result_embeddings


def match_labels_df(
    df1: pd.DataFrame,
    df2: pd.DataFrame,
    params: Dict[str, Any],
    criterion: str | None = None,
) -> None:
    """Matching names in columns of DataFrames (by default the result is stored in the column matchedLabel)
    Args:
        df1 : DataFrame with labels to match
        df2 : DataFrame with labels to match against
        params : dictionary with keys being the column names and columns to group by
            - col1: column in df1 to match
            - col2: column in df2 to match against
            - newCol: column with embeddings
            - groupby1: column to group by in df1
            - groupby2: column to group by in df2
        params: dictionary with keys being the column names and columns to group by
        criterion: optional string to filter df2
    """
    required_params = ["col1", "col2", "newCol", "groupby1", "groupby2"]
    for param in params.keys():
        if param not in required_params:
            raise KeyError(f"Missing required parameter: {param}")
    # Group rows by date
    grouped_df1 = df1[df1[params["newCol"]].notna()].groupby(params["groupby1"])
    if criterion:
        grouped_df2 = df2[
            (df2[params["newCol"]].notna())
            & (df2[params["col2"]].str.contains(criterion))
        ].groupby(params["groupby2"])
    else:
        grouped_df2 = df2[df2[params["newCol"]].notna()].groupby(params["groupby2"])

    # Iterate over unique dates in df1
    for date, group1 in grouped_df1:
        # group1 = group1.reset_index(drop=True)

        if date in grouped_df2.groups:
            group2 = grouped_df2.get_group(date)
            group2 = group2.reset_index(drop=True)

            # Compute pairwise cosine similarity between embeddings
            similarity_matrix = cosine_similarity(
                np.vstack(group1[params["newCol"]]), np.vstack(group2[params["newCol"]])
            )
            idx = 0
            # Find the best match for each row in group1
            for i, row1 in group1.iterrows():
                # best_match_idx = np.argmax(similarity_matrix[i])

                sort_indices = np.argsort(similarity_matrix[idx])[::-1]
                best_match = group2.iloc[sort_indices[0]]
                similarity_score = similarity_matrix[idx][sort_indices[0]]
                df1.at[i, "matchedLabel1"] = best_match[params["col2"]]
                df1.at[i, "similarity_score1"] = similarity_score

                df1.at[i, "matchedLabelFuzzy"] = fuzzy_match(
                    row1[params["col1"]],
                    choices=group2[params["col2"]].unique(),
                    scorer=fuzz.WRatio,
                    processor=preprocess,
                )

                # Second-best match (if it exists)
                if len(sort_indices) > 1:
                    second_best_match = group2.iloc[sort_indices[1]]
                    df1.at[i, "matchedLabel2"] = second_best_match[params["col2"]]
                    df1.at[i, "similarity_score2"] = similarity_matrix[idx][
                        sort_indices[1]
                    ]
                idx += 1


def match_labels_df_vectorized(
    df1: pd.DataFrame,
    df2: pd.DataFrame,
    params: Dict[str, Any],
    criterion: str | None = None,
) -> None:
    """
    Vectorized version of matching names in columns of DataFrames.
    Matches labels using cosine similarity and stores results in `matchedLabel`.

    Note: We discard batch computation (torch) for simplicity.
    """
    required_params = ["col1", "col2", "newCol", "groupby1", "groupby2"]
    if not all(param in params for param in required_params):
        raise KeyError(
            f"Missing required parameters: {set(required_params) - set(params.keys())}"
        )

    # Group rows by date
    grouped_df1 = df1[df1[params["newCol"]].notna()].groupby(params["groupby1"])
    if criterion:
        grouped_df2 = df2[
            (df2[params["newCol"]].notna())
            & (df2[params["col2"]].str.contains(criterion))
        ].groupby(params["groupby2"])
    else:
        grouped_df2 = df2[df2[params["newCol"]].notna()].groupby(params["groupby2"])

    # Iterate over unique dates in df1
    for date, group1 in grouped_df1:
        if date not in grouped_df2.groups:
            continue  # Skip if no matching date in df2

        group2 = grouped_df2.get_group(date).reset_index(drop=True)

        # Extract embeddings as NumPy arrays
        embeddings1 = np.vstack(group1[params["newCol"]])
        embeddings2 = np.vstack(group2[params["newCol"]])

        # Compute pairwise cosine similarity (vectorized)
        similarity_matrix = cosine_similarity(embeddings1, embeddings2)

        # Find top matches for all rows in group1
        top_indices = np.argsort(similarity_matrix, axis=1)[:, ::-1]  # Sort descending
        best_match_indices = top_indices[:, 0]  # Best matches
        second_best_match_indices = top_indices[:, 1]  # Second-best matches

        # Assign best matches
        df1.loc[group1.index, "matchedLabel1"] = group2.iloc[best_match_indices][
            params["col2"]
        ].values
        df1.loc[group1.index, "similarity_score1"] = similarity_matrix[
            np.arange(similarity_matrix.shape[0]), best_match_indices
        ]

        # Assign second-best matches (if they exist)
        if top_indices.shape[1] > 1:
            df1.loc[group1.index, "matchedLabel2"] = group2.iloc[
                second_best_match_indices
            ][params["col2"]].values
            df1.loc[group1.index, "similarity_score2"] = similarity_matrix[
                np.arange(similarity_matrix.shape[0]), second_best_match_indices
            ]

        # Fuzzy matching (optional, can be parallelized if needed)
        df1.loc[group1.index, "matchedLabelFuzzy"] = group1[params["col1"]].apply(
            lambda x: fuzzy_match(
                x,
                choices=group2[params["col2"]].unique(),
                scorer=fuzz.WRatio,
                processor=preprocess,
            )
        )


def last_mode(row):
    """
    Compute the last mode, it is to say the most frequent element in the row if there is no tie, otherwise the last element.
    Args:
        row: row dataframe
    """
    modes = row.mode()
    if len(modes) > 1:
        return row.iloc[-1] if row.iloc[-1] else row.iloc[0]
    else:
        return modes.iloc[0]


def input_from_csv(
    df: pd.DataFrame,
    filepath: str,
    column_name: str,
):
    """
    Input categories from external csv
    """
    input_df = pd.read_csv(filepath)
    if isinstance(column_name, str):
        merged_df = pd.merge(
            df, input_df, on=column_name, how="left", suffixes=("_original", "_imputed")
        )
    else:
        raise ValueError("column_name should be a string")
    return merged_df


def join_on_dates_and_match(
    df1: pd.DataFrame, df2: pd.DataFrame, keys: Dict[str, Any]
) -> pd.DataFrame:
    """
    Join two DataFrames on their index (date) and match labels.
    """
    required_params = ["col1", "col2", "date1", "date2"]
    for param in keys.keys():
        if param not in required_params:
            raise KeyError(f"Missing required parameter: {param}")
    merged = pd.merge(
        df1,
        df2,
        how="left",
        left_on=[keys["date1"], keys["col1"]],
        right_on=[keys["date2"], keys["col2"]],
        suffixes=("", "_loyalty"),
    )

    return merged


def main_matching():
    # Load a pre-trained Sentence Transformer model
    # model = SentenceTransformer("all-MiniLM-L6-v2")
    df_prod = pd.read_csv(
        f"{DATA_DIRECTORY}/20250501-carrefour_prods.csv", parse_dates=["dateKey"]
    )
    df_loyalty = pd.read_csv(
        f"{DATA_DIRECTORY}/20250501-carrefour_loyalty.csv", parse_dates=["date"]
    )
    df_prod["totalPriceAfterDiscount"] = (
        df_prod["totalPrice"] + df_prod["totalImmediateDiscount"]
    )
    mapped_categories = {
        "Charcuterie": "food",
        "Laits et Boissons végétales": "food",
        "Jus de fruits et légumes": "food",
        "Toasts et Pains de mie": "food",
        "Yaourts et Fromages blancs": "food",
        "Conserves et Bocaux": "food",
        "Colas, Thés glacés, Sirops et Sodas": "food",
        "Légumes": "food",
        "Huiles, Vinaigres et Vinaigrettes": "food",
        "Nettoyants vaisselle": "other",
        "Accessoires de ménage": "other",
        "Matériel de bureau": "other",
        "Fromages": "food",
        "Epicerie salée": "food",
        "Cheveux": "other",
        "Pains Burger, Sandwich et Wraps": "food",
        "Eaux": "food",
        "Viandes": "food",
        "Lessives": "other",
        "Pizzas, Quiches et Tartes": "food",
        "Apéritifs et Chips": "food",
        "Fruits": "food",
        "Volaille et Rôtisserie": "food",
        "Glaces et Sorbets": "food",
        "Bio à Petit prix": "food",
        "Gâteaux moelleux": "food",
        "Apéritifs, Entrées et Snacking": "food",
        "Petit déjeuner": "food",
        "Hygiène dentaire": "other",
        "Cave à Vins": "food",
        "Boucherie": "food",
        "Poissons et Fruits de mer": "food",
        "Œufs": "food",
        "Poissonnerie": "food",
        "Essuie-tout, Papier toilette et Mouchoirs": "other",
        "Confiseries et Chocolats": "food",
        "RETURNABLE_BAG": "other",
        "Hygiène intime ": "other",
        "Désodorisants et Bougies": "other",
        "Toutes nos régions": "food",
        "Produits nettoyants": "other",
        "Riz, Purées et Féculents": "food",
        "Ingrédients pour cuisiner": "food",
        "Sauces froides": "food",
        "Pains frais": "food",
        "Bières et Cidres": "food",
        "Repas de Pâques": "food",
        "Le Marché": "food",
        "Beurres et Crèmes": "food",
        "Premiers soins et Préservatifs": "other",
        "Nintendo Switch": "other",
        "Sucres, Farines et Aide à la pâtisserie": "food",
        "Viennoiseries et Brioches fraîches": "food",
        "Corps": "other",
    }
    # Fill NaN categories with subCategory mapped to main category
    df_prod.loc[df_prod.category.isna(), "category"] = df_prod.loc[
        df_prod.category.isna(), "subCategory"
    ].map(mapped_categories)

    df_prod = input_from_csv(
        df_prod,
        filepath=f"{DATA_DIRECTORY}/20250502-carrefour_food_products_labels_most_2.csv",
        column_name="productLabel",
    )
    df_prod.to_csv(f"{DATA_DIRECTORY}/20250501-carrefour_products.csv", index=False)
    params = {
        "col1": "itemLabel",
        "col2": "productLabel",
        "newCol": "embeddingLabel",
        "groupby1": "date",
        "groupby2": "dateKey",
    }
    embedding_to_df(
        model,
        df_loyalty,
        params["col1"],
        new_column_name="embeddingLabel",
        filter_out="ART RAYON",
    )
    model = SentenceTransformer("all-distilroberta-v1")
    embedding_to_df(model, df_prod, params["col2"])

    match_labels_df(df_loyalty, df_prod, params)

    # better model slightly but longer to process

    df_loyalty.loc[df_loyalty.similarity_score1 > 0.5, "matchedLabel"] = df_loyalty.loc[
        df_loyalty.similarity_score1 > 0.5, "matchedLabel1"
    ]
    df_loyalty.loc[df_loyalty.similarity_score1 <= 0.5, "matchedLabel"] = (
        df_loyalty.loc[
            df_loyalty.similarity_score1 <= 0.5,
            ["matchedLabel1", "matchedLabel2", "matchedLabelFuzzy"],
        ].apply(last_mode, axis=1)
    )


if __name__ == "__main__":
    main_matching()
