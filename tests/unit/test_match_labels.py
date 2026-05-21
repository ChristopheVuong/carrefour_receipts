"""
TODO: Test benchmark timing for matching labels
TODO: Use timing here as well in order to assess the gain in speed doing batch computation and eventually ship it to GPU for true gains.
TODO: Compute for all the the items available in database? Integration unit set the boundaries
"""
import pytest
# perf_counter timing, etc

@pytest.mark.fast
# @pytest.mark.parametrize
def test_match_labels():
    """
    List of matching labels in pandas dataframe columns itemLabel, productLabel and matchedLabels expected coming from productLabel
    """
    pass

@pytest.mark.fast
def test_batch_cosine_similarity():
    pass

@pytest.mark.slow
def test_embeddings_computation():
    """
    Test with batch and torch ultimately
    """
    pass