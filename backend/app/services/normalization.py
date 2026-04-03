"""
Track normalization pipeline as per spec:
1. Strip diacritics via Unicode NFKD decomposition
2. Lowercase
3. Remove parenthetical and bracketed content (feat., Radio Edit, etc.)
4. Strip version tags (remaster, live, deluxe, acoustic, extended, radio edit)
5. Extract featured artists from title and merge into artist list
6. Sort artist list alphabetically
7. Collapse whitespace
"""

import re
import unicodedata
from dataclasses import dataclass

# Regex patterns
_FEAT_IN_TITLE = re.compile(
    r"[\(\[]\s*(?:feat\.?|ft\.?|featuring)\s+([^\)\]]+)[\)\]]",
    re.IGNORECASE,
)
_PARENS_AND_BRACKETS = re.compile(r"[\(\[][^\)\]]*[\)\]]")
_VERSION_TAGS = re.compile(
    r"\b(?:remaster(?:ed)?|remastered \d{4}|live|deluxe(?: edition)?|acoustic|"
    r"extended(?: version)?|radio edit|single version|album version|"
    r"bonus track|instrumental|explicit|clean)\b",
    re.IGNORECASE,
)
_WHITESPACE = re.compile(r"\s+")
_FEAT_IN_ARTIST = re.compile(
    r"\s*(?:feat\.?|ft\.?|featuring)\s+.+$",
    re.IGNORECASE,
)


def strip_diacritics(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _split_featured_from_title(title: str) -> tuple[str, list[str]]:
    """Extract featured artists from title parens and return (clean_title, featured_list)."""
    featured: list[str] = []
    for match in _FEAT_IN_TITLE.finditer(title):
        raw = match.group(1)
        # Split on commas or & to get individual artists
        parts = re.split(r",|&", raw)
        featured.extend(p.strip() for p in parts if p.strip())
    clean_title = _FEAT_IN_TITLE.sub("", title).strip()
    return clean_title, featured


def _clean_artist_name(artist: str) -> str:
    """Remove feat. suffixes from artist strings."""
    return _FEAT_IN_ARTIST.sub("", artist).strip()


def normalize_text(text: str) -> str:
    """Apply diacritic stripping, lowercase, whitespace collapse."""
    text = strip_diacritics(text)
    text = text.lower()
    text = _WHITESPACE.sub(" ", text).strip()
    return text


@dataclass
class NormalizedTrack:
    normalized_title: str
    normalized_artists: list[str]  # sorted, lowercase
    display_title: str             # cleaned display (feat. removed, but original casing)
    display_artists: list[str]     # merged + cleaned, original casing
    canonical_key: str             # normalized_title + "||" + ",".join(normalized_artists)


def normalize_track(title: str, artists: list[str]) -> NormalizedTrack:
    """
    Full normalization pipeline. Input: raw title + artist list.
    Returns a NormalizedTrack with all derived fields.
    """
    # Step 1 + 5: Extract featured artists from title
    clean_title, featured_from_title = _split_featured_from_title(title)

    # Step 2: Clean artist names (remove feat. suffixes)
    cleaned_artists = [_clean_artist_name(a) for a in artists]

    # Merge all artists (original + featured from title)
    all_display_artists = list(dict.fromkeys(
        a for a in cleaned_artists + featured_from_title if a
    ))

    # Step 3: Remove remaining parens/brackets from title
    clean_title = _PARENS_AND_BRACKETS.sub("", clean_title).strip()

    # Step 4: Strip version tags
    clean_title = _VERSION_TAGS.sub("", clean_title).strip()

    # Step 7: Collapse whitespace
    clean_title = _WHITESPACE.sub(" ", clean_title).strip()

    # Normalize for canonical comparison
    norm_title = normalize_text(clean_title)
    norm_artists = sorted(normalize_text(a) for a in all_display_artists if a)

    # Step 6: Sort artist list
    sorted_display_artists = sorted(all_display_artists, key=lambda a: a.lower())

    canonical_key = f"{norm_title}||{','.join(norm_artists)}"

    return NormalizedTrack(
        normalized_title=norm_title,
        normalized_artists=norm_artists,
        display_title=clean_title if clean_title else title,
        display_artists=sorted_display_artists if sorted_display_artists else artists,
        canonical_key=canonical_key,
    )
