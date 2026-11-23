"""Scoring for list fields: identifiers, pressure tactics, information requested."""

from typing import Any

from natter.schema import Dossier
from natter.scoring import unwrap


def precision_recall(expected: set[Any], got: set[Any]) -> tuple[float, float]:
    """precision = hits / got, recall = hits / expected. An empty set scores 1.0."""
    both = len(expected & got)
    precision = both / len(got) if got else 1.0
    recall = both / len(expected) if expected else 1.0
    return precision, recall


def letters_digits(value: str) -> str:
    """Lowercase letters and digits only: "07700-900 482" -> "07700900482"."""
    return "".join(c for c in value.casefold() if c.isalnum())


def same_identifier(a: tuple[str, str], b: tuple[str, str]) -> bool:
    """Same kind, both values at least 4 characters, and one value contains the other."""
    (kind_a, value_a), (kind_b, value_b) = a, b
    if kind_a != kind_b or len(value_a) < 4 or len(value_b) < 4:
        return False
    return value_a in value_b or value_b in value_a


def score_identifiers(raw: dict[str, Any], dossier: Dossier) -> tuple[float, float]:
    """Precision and recall over (kind, value) pairs, matched by same_identifier.

    So "99001122" matches "sort code 11-22-33, account number 99001122". Sort codes are
    not scored on their own (there is no sort_code kind). Matching is not set equality:
    precision = got items matching some expected item / all got items,
    recall = expected items matching some got item / all expected items.
    Empty lists score 1.0.
    """
    # Identifier items are NOT unwrapped: their "value" is the identifier text itself
    expected = [(i["kind"], letters_digits(i["value"])) for i in raw.get("identifiers", [])]
    got = [(i.kind.value, letters_digits(i.value)) for i in dossier.identifiers]
    hit_got = sum(1 for g in got if any(same_identifier(e, g) for e in expected))
    hit_expected = sum(1 for e in expected if any(same_identifier(e, g) for g in got))
    precision = hit_got / len(got) if got else 1.0
    recall = hit_expected / len(expected) if expected else 1.0
    return precision, recall


def score_string_list(raw: dict[str, Any], dossier: Dossier, name: str) -> tuple[float, float]:
    """Precision and recall for pressure_tactics or information_requested."""
    expected = {str(unwrap(item)) for item in raw.get(name, [])}
    got = {str(item.value.value) for item in getattr(dossier, name)}
    return precision_recall(expected, got)
