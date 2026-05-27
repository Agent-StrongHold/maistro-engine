"""Author selector — picks the right examples based on audience and length.

The user never picks authors. They say:
  - "bedtime story for my 3-year-old"
  - "my 8-year-old loves funny books"
  - "chapter book for a kid who likes Percy Jackson"

The system maps (age, length, purpose) → best author examples automatically.
"""

from __future__ import annotations
from dags.author_examples import (
    SEUSS, ERIC_CARLE, MO_WILLEMS, JULIA_DONALDSON, DRAGONS_LOVE_TACOS, PETE_THE_CAT,
    JUNIE_B_JONES, FROG_AND_TOAD, ELEPHANT_AND_PIGGIE,
    ROALD_DAHL, DIARY_OF_A_WIMPY_KID, PERCY_JACKSON, DOG_MAN, CAPTAIN_UNDERPANTS, THE_BAD_GUYS,
    GOODNIGHT_MOON, GUESS_HOW_MUCH,
    HARRY_POTTER, MAGIC_TREE_HOUSE, HUNGER_GAMES_YA,
    ENGAGEMENT_PRINCIPLES,
)


def select_authors(age: int, word_count: int, purpose: str = "", tone: str = "") -> list[dict]:
    """Pick 2-3 author examples based on audience and format.
    
    Args:
        age: target reader age (2-14)
        word_count: target length
        purpose: "bedtime", "educational", "entertainment", "adventure", "funny", "series"
        tone: "calm", "silly", "exciting", "scary", "warm"
    """
    candidates = []

    # --- BEDTIME (any age under 7, calm tone, or explicit purpose) ---
    if purpose == "bedtime" or (tone == "calm" and age <= 6):
        candidates = [GOODNIGHT_MOON, GUESS_HOW_MUCH]
        if age <= 3:
            candidates.insert(0, GOODNIGHT_MOON)  # weight Brown higher for youngest
        return candidates[:2]

    # --- PICTURE BOOKS (ages 2-5, under 500 words) ---
    if age <= 5 and word_count <= 500:
        if tone == "silly" or purpose == "funny":
            candidates = [DRAGONS_LOVE_TACOS, MO_WILLEMS, PETE_THE_CAT]
        elif purpose == "educational":
            candidates = [ERIC_CARLE, PETE_THE_CAT, SEUSS]
        elif "rhyme" in tone or "sing" in tone:
            candidates = [JULIA_DONALDSON, SEUSS, PETE_THE_CAT]
        elif "interactive" in purpose:
            candidates = [MO_WILLEMS, PETE_THE_CAT, DRAGONS_LOVE_TACOS]
        else:
            candidates = [ERIC_CARLE, MO_WILLEMS, JULIA_DONALDSON]
        return candidates[:3]

    # --- EARLY READERS (ages 5-7, 300-1000 words) ---
    if age <= 7 and word_count <= 1000:
        if tone == "silly" or purpose == "funny":
            candidates = [ELEPHANT_AND_PIGGIE, JUNIE_B_JONES, PETE_THE_CAT]
        elif tone == "warm" or purpose == "friendship":
            candidates = [FROG_AND_TOAD, ELEPHANT_AND_PIGGIE]
        elif purpose == "series":
            candidates = [JUNIE_B_JONES, ELEPHANT_AND_PIGGIE, FROG_AND_TOAD]
        else:
            candidates = [JUNIE_B_JONES, FROG_AND_TOAD, ELEPHANT_AND_PIGGIE]
        return candidates[:3]

    # --- CHAPTER BOOKS (ages 7-10, 1000-5000 words) ---
    if age <= 10:
        if tone == "silly" or purpose == "funny" or "reluctant reader" in purpose:
            candidates = [DOG_MAN, CAPTAIN_UNDERPANTS, DIARY_OF_A_WIMPY_KID]
        elif purpose == "adventure" or tone == "exciting":
            candidates = [MAGIC_TREE_HOUSE, PERCY_JACKSON, ROALD_DAHL]
        elif purpose == "series":
            candidates = [MAGIC_TREE_HOUSE, DOG_MAN, DIARY_OF_A_WIMPY_KID]
        elif "villain" in tone or "dark" in tone:
            candidates = [ROALD_DAHL, THE_BAD_GUYS, PERCY_JACKSON]
        elif purpose == "educational":
            candidates = [MAGIC_TREE_HOUSE, ROALD_DAHL]
        else:
            candidates = [ROALD_DAHL, MAGIC_TREE_HOUSE, DOG_MAN]
        return candidates[:3]

    # --- MIDDLE GRADE / YA (ages 10-14) ---
    if age <= 14:
        if purpose == "adventure" or tone == "exciting":
            candidates = [PERCY_JACKSON, HUNGER_GAMES_YA, HARRY_POTTER]
        elif purpose == "funny" or tone == "silly":
            candidates = [DIARY_OF_A_WIMPY_KID, CAPTAIN_UNDERPANTS, THE_BAD_GUYS]
        elif purpose == "series" or "fantasy" in purpose:
            candidates = [HARRY_POTTER, PERCY_JACKSON, HUNGER_GAMES_YA]
        else:
            candidates = [HARRY_POTTER, PERCY_JACKSON, DIARY_OF_A_WIMPY_KID]
        return candidates[:3]

    # Fallback
    return [ROALD_DAHL, HARRY_POTTER, PERCY_JACKSON][:2]


def format_examples_for_prompt(authors: list[dict]) -> str:
    """Format selected author examples into a prompt-ready string."""
    parts = []
    for a in authors:
        example = a.get("example", "")
        rules = a.get("rules", [])
        parts.append(
            f"**{a['author']}** ({a['books'][0]}):\n"
            f'"{example[:200]}"\n'
            f"Rules: {'; '.join(rules[:3])}"
        )
    # Add engagement principles
    parts.append(
        "\n**Why kids stay hooked:**\n" +
        "\n".join(f"- {v}" for v in list(ENGAGEMENT_PRINCIPLES.values())[:4])
    )
    return "\n\n".join(parts)
