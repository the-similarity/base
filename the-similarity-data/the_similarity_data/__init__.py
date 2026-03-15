"""Data fetching and manifest utilities for The Similarity."""

from the_similarity_data.config import load_dataset_specs


def refresh_dataset(*args, **kwargs):
    from the_similarity_data.refresh import refresh_dataset as _rd
    return _rd(*args, **kwargs)


def refresh_all_datasets(*args, **kwargs):
    from the_similarity_data.refresh import refresh_all_datasets as _ra
    return _ra(*args, **kwargs)


__all__ = ["load_dataset_specs", "refresh_all_datasets", "refresh_dataset"]
