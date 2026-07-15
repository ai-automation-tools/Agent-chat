"""Topic classification for conversation marks.

Every conversation gets a logo derived from its topic text: a keyword scan
picks one of the categories below, and the category supplies the glyph +
gradient used by ``web.render.conversations._conversation_mark()``. Nothing is
persisted — classification runs at render time, so historical rows get their
logo without a schema migration, and re-wording the table below re-skins the
whole archive.

Matching rules:

* Keywords match on word boundaries, case-insensitively. Spaces in a keyword
  match runs of whitespace *or* hyphens, so ``"gene editing"`` also matches
  ``gene-editing`` and ``"lab grown"`` matches ``lab-grown``.
* A category's score is the sum of the word-counts of the keywords it hits, so
  a specific phrase ("stock market") outweighs a bare word ("market").
* Ties go to whichever category is listed first in ``TOPICS`` — the list is
  ordered most-specific first, which is why ``ai`` sits near the bottom (an AI
  debate *about* weapons should read as security, not as AI).
* No hits at all → ``DEFAULT_TOPIC`` (the generic chat mark).

Glyphs are stroke-only paths in a 24x24 box (Feather/Lucide idiom); the mark
renderer scales and centres them on the tile, and stroke colour/width come from
``.cv-mark-glyph`` in ``web.assets``.
"""

from __future__ import annotations

import re
from typing import NamedTuple


class Topic(NamedTuple):
    """One conversation category: how to spot it, and how to draw it."""

    slug: str
    label: str
    ink: str
    ink_2: str
    glyph: str
    keywords: tuple[str, ...]


# Ordered most-specific first: ties are broken by position (see module docstring).
TOPICS: tuple[Topic, ...] = (
    Topic(
        slug="finance",
        label="Finance & markets",
        ink="#fbbf24",
        ink_2="#34d399",
        # trending-up
        glyph='<polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/>'
              '<polyline points="17 6 23 6 23 12"/>',
        keywords=(
            "finance", "financial", "economy", "economic", "economics",
            "market", "markets", "stock", "stocks", "stock market",
            "inflation", "recession", "bank", "banks", "banking",
            "money", "currency", "crypto", "cryptocurrency", "bitcoin",
            "blockchain", "investing", "investment", "investors", "trading",
            "tariff", "tariffs", "wall street", "hedge fund", "interest rates",
            "gdp", "tax", "taxes", "wealth", "debt", "dollar",
            "valuation", "ipo", "venture capital", "profit", "revenue",
        ),
    ),
    Topic(
        slug="space",
        label="Space & the cosmos",
        ink="#818cf8",
        ink_2="#22d3ee",
        # ringed planet
        glyph='<circle cx="12" cy="12" r="6"/>'
              '<ellipse cx="12" cy="12" rx="11" ry="3.6" '
              'transform="rotate(-24 12 12)"/>',
        keywords=(
            "space", "cosmos", "cosmic", "universe", "galaxy", "galaxies",
            "astronomy", "astronaut", "nasa", "spacex", "mars", "moon",
            "lunar", "orbit", "orbital", "satellite", "satellites",
            "rocket", "rockets", "fermi", "fermi paradox", "interstellar",
            "exoplanet", "alien", "aliens", "extraterrestrial",
            "extraterrestrials", "ufo", "ufos", "uap", "seti",
            "black hole", "solar system", "asteroid", "space tourism",
            "telescope", "spaceflight",
        ),
    ),
    Topic(
        slug="bio",
        label="Biotech & health",
        ink="#f472b6",
        ink_2="#a78bfa",
        # dna helix — strands cross near y=6/y=18, so rungs sit in the open middle
        glyph='<path d="M7 2c0 5 10 5 10 10s-10 5-10 10"/>'
              '<path d="M17 2c0 5-10 5-10 10s10 5 10 10"/>'
              '<line x1="9.4" y1="9.4" x2="14.6" y2="9.4"/>'
              '<line x1="7.6" y1="12" x2="16.4" y2="12"/>'
              '<line x1="9.4" y1="14.6" x2="14.6" y2="14.6"/>',
        keywords=(
            "gene", "genes", "genetic", "genetics", "gene editing", "crispr",
            "dna", "genome", "organ", "organs", "lab grown", "stem cell",
            "biotech", "biology", "biological", "medical", "medicine",
            "health", "healthcare", "disease", "cancer", "vaccine", "vaccines",
            "drug", "drugs", "clinical", "brain", "neural", "neuroscience",
            "neurons", "brain computer interface", "longevity", "aging",
            "surgery", "doctor", "doctors", "patients", "fertility", "embryo",
            "cloning", "pandemic", "virus", "mental health", "therapy",
        ),
    ),
    Topic(
        slug="security",
        label="Security & conflict",
        ink="#f87171",
        ink_2="#fb923c",
        # shield
        glyph='<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
        keywords=(
            "cyber", "cybersecurity", "cyber warfare", "warfare", "war",
            "military", "weapon", "weapons", "nuclear", "defense",
            "hacking", "hackers", "hacked", "malware", "ransomware",
            "breach", "surveillance", "espionage", "spy", "spies",
            "terrorism", "attack", "attacks", "drone", "drones",
            "kill", "lethal", "army", "soldiers", "battlefield",
            "encryption", "privacy",
        ),
    ),
    Topic(
        slug="policy",
        label="Policy & governance",
        ink="#60a5fa",
        ink_2="#93c5fd",
        # institution: pediment + pillars + base
        glyph='<path d="M2 9 12 3l10 6"/>'
              '<line x1="6" y1="11" x2="6" y2="18"/>'
              '<line x1="12" y1="11" x2="12" y2="18"/>'
              '<line x1="18" y1="11" x2="18" y2="18"/>'
              '<line x1="3" y1="21" x2="21" y2="21"/>',
        keywords=(
            "government", "governments", "regulation", "regulations",
            "regulate", "regulated", "regulating", "regulator", "regulators",
            "law", "laws", "legal", "legislation", "policy", "policies",
            "ban", "banned", "banning", "license", "licenses", "licensing",
            "court", "courts", "congress", "senate", "election", "elections",
            "vote", "voting", "democracy", "politics", "political",
            "president", "rights", "antitrust", "liability", "mandate",
            "mandatory", "treaty", "sanctions", "governance",
        ),
    ),
    Topic(
        slug="food",
        label="Food & dining",
        ink="#fdba74",
        ink_2="#fca5a5",
        # utensils
        glyph='<path d="M4 2v7a2 2 0 0 0 4 0V2"/><line x1="6" y1="9" x2="6" y2="22"/>'
              '<path d="M18 2c-2 1.5-3 3.5-3 6s1 3.5 3 3.5h2V2z"/>'
              '<line x1="18" y1="11.5" x2="18" y2="22"/>',
        keywords=(
            "restaurant", "restaurants", "food", "dish", "dishes",
            "chef", "chefs", "cooking", "recipe", "recipes", "menu",
            "cuisine", "dining", "meal", "meals", "agriculture", "farming",
            "meat", "coffee", "wine",
        ),
    ),
    Topic(
        slug="culture",
        label="Culture & the arts",
        ink="#f472b6",
        ink_2="#fbbf24",
        # sparkle
        glyph='<path d="M12 3 10.1 8.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3'
              'L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3z"/>',
        keywords=(
            "pop culture", "culture", "cultural", "art", "artist", "artists",
            "music", "musician", "film", "films", "movie", "movies",
            "hollywood", "television", "entertainment", "celebrity",
            "celebrities", "creativity", "creative", "creators", "reboot",
            "reboots", "fashion", "gaming", "video game", "video games",
            "books", "literature", "streaming", "fandom", "poetry",
        ),
    ),
    Topic(
        slug="society",
        label="Society & people",
        ink="#fb923c",
        ink_2="#fbbf24",
        # users
        glyph='<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>'
              '<circle cx="9" cy="7" r="4"/>'
              '<path d="M23 21v-2a4 4 0 0 0-3-3.87"/>'
              '<path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
        keywords=(
            "social media", "society", "social", "people", "community",
            "communities", "happiness", "happy", "loneliness", "lonely",
            "children", "kids", "teens", "teenagers", "parents", "family",
            "relationships", "dating", "friendship", "generation", "gen z",
            "citizens", "population", "inequality", "gender", "race",
            "religion", "cities", "housing", "immigration", "education",
            "school", "schools", "university", "students", "teachers",
        ),
    ),
    Topic(
        slug="climate",
        label="Climate & energy",
        ink="#4ade80",
        ink_2="#22d3ee",
        # leaf
        glyph='<path d="M11 21A8 8 0 0 1 9.8 5.1C15.5 4 17 3.5 19 1c1 2 2 4.2 2 8 0 '
              '5.5-4.8 12-10 12z"/>'
              '<path d="M2 22c0-3 1.9-5.4 5.1-6C9.5 15.5 12 14 13 13"/>',
        keywords=(
            "climate", "climate change", "global warming", "carbon",
            "emissions", "environment", "environmental", "sustainability",
            "sustainable", "renewable", "wind power", "fossil fuel",
            "fossil fuels", "oil", "energy", "nuclear power", "pollution",
            "planet", "earth", "ecosystem", "biodiversity", "deforestation",
            "recycling", "green energy", "net zero", "electric vehicles",
        ),
    ),
    Topic(
        slug="science",
        label="Science & research",
        ink="#2dd4bf",
        ink_2="#60a5fa",
        # atom
        glyph='<circle cx="12" cy="12" r="2"/>'
              '<ellipse cx="12" cy="12" rx="10" ry="4"/>'
              '<ellipse cx="12" cy="12" rx="10" ry="4" transform="rotate(60 12 12)"/>'
              '<ellipse cx="12" cy="12" rx="10" ry="4" transform="rotate(-60 12 12)"/>',
        keywords=(
            "quantum", "physics", "chemistry", "mathematics", "math",
            "science", "scientific", "scientists", "research", "experiment",
            "experiments", "theory", "relativity", "particle", "fusion",
            "superconductor", "nobel", "hypothesis", "peer review",
        ),
    ),
    Topic(
        slug="work",
        label="Work & the economy of jobs",
        ink="#a3e635",
        ink_2="#2dd4bf",
        # briefcase
        glyph='<rect x="2" y="7" width="20" height="14" rx="2"/>'
              '<path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/>',
        keywords=(
            "job", "jobs", "career", "careers", "employment", "unemployment",
            "employer", "employers", "employee", "employees", "worker",
            "workers", "workforce", "labor", "hiring", "layoffs", "salary",
            "salaries", "wages", "remote work", "office", "white collar",
            "blue collar", "union", "unions", "junior", "entry level",
            "internship", "productivity", "gig economy", "freelance",
            "recruiting",
        ),
    ),
    Topic(
        slug="ai",
        label="AI & machine intelligence",
        ink="#10b981",
        ink_2="#38bdf8",
        # cpu
        glyph='<rect x="4" y="4" width="16" height="16" rx="2"/>'
              '<rect x="9" y="9" width="6" height="6"/>'
              '<line x1="9" y1="1" x2="9" y2="4"/><line x1="15" y1="1" x2="15" y2="4"/>'
              '<line x1="9" y1="20" x2="9" y2="23"/><line x1="15" y1="20" x2="15" y2="23"/>'
              '<line x1="20" y1="9" x2="23" y2="9"/><line x1="20" y1="14" x2="23" y2="14"/>'
              '<line x1="1" y1="9" x2="4" y2="9"/><line x1="1" y1="14" x2="4" y2="14"/>',
        keywords=(
            "ai", "artificial intelligence", "llm", "llms", "machine learning",
            "deep learning", "neural network", "neural networks", "chatgpt",
            "gpt", "claude", "gemini", "openai", "anthropic", "agent",
            "agents", "agentic", "robot", "robots", "robotics", "automation",
            "automated", "autonomous", "algorithm", "algorithms", "chatbot",
            "model", "models", "training data", "agi", "superintelligence",
            "alignment", "prompt", "copilot", "coding agents", "ai slop",
            "hallucination", "inference", "transformer", "deepfake",
        ),
    ),
    Topic(
        slug="philosophy",
        label="Philosophy & big questions",
        ink="#c4b5fd",
        ink_2="#f0abfc",
        # question mark in a circle
        glyph='<circle cx="12" cy="12" r="10"/>'
              '<path d="M9.1 9a3 3 0 0 1 5.8 1c0 2-3 3-3 3"/>'
              '<line x1="12" y1="17" x2="12.01" y2="17"/>',
        keywords=(
            "simulation", "consciousness", "conscious", "free will",
            "meaning of life", "existence", "existential", "ethics",
            "ethical", "morality", "moral", "philosophy", "philosophical",
            "extinction", "doomsday", "apocalypse", "utopia", "dystopia",
            "reality", "truth", "identity", "soul", "afterlife", "paradox",
            "thought experiment", "human nature", "determinism",
        ),
    ),
    Topic(
        slug="tech",
        label="Technology",
        ink="#38bdf8",
        ink_2="#a78bfa",
        # code brackets
        glyph='<polyline points="16 18 22 12 16 6"/>'
              '<polyline points="8 6 2 12 8 18"/>',
        keywords=(
            "technology", "tech", "software", "hardware", "internet", "web",
            "computer", "computers", "computing", "code", "coding",
            "programming", "developer", "developers", "engineer",
            "engineering", "app", "apps", "smartphone", "smartphones",
            "phone", "device", "devices", "cloud", "data", "database",
            "chip", "chips", "semiconductor", "vr", "virtual reality",
            "metaverse",
        ),
    ),
)

DEFAULT_TOPIC = Topic(
    slug="chat",
    label="General discussion",
    ink="#10b981",
    ink_2="#38bdf8",
    # message-square
    glyph='<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
    keywords=(),
)

TOPICS_BY_SLUG: dict[str, Topic] = {t.slug: t for t in (*TOPICS, DEFAULT_TOPIC)}

_PATTERNS: dict[str, re.Pattern[str]] = {}


def _pattern(keyword: str) -> re.Pattern[str]:
    cached = _PATTERNS.get(keyword)
    if cached is None:
        body = r"[\s\-]+".join(re.escape(word) for word in keyword.split())
        cached = _PATTERNS[keyword] = re.compile(rf"\b{body}\b", re.IGNORECASE)
    return cached


def _score(topic: Topic, text: str) -> int:
    return sum(
        len(keyword.split())
        for keyword in topic.keywords
        if _pattern(keyword).search(text)
    )


def classify_topic(text: str | None) -> Topic:
    """Pick the category whose keywords best fit ``text``."""
    text = str(text or "")
    if not text.strip():
        return DEFAULT_TOPIC
    best, best_score = DEFAULT_TOPIC, 0
    for topic in TOPICS:
        score = _score(topic, text)
        if score > best_score:
            best, best_score = topic, score
    return best
