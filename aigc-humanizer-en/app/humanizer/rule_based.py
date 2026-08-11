#!/usr/bin/env python3
"""
Rule-based humanizer - transform AI-generated text with local rules.
Preserves academic tone while introducing natural variation.

Note: Uses deterministic transformations based on word position to ensure
consistent results across multiple runs.
"""

import re
import hashlib
import sys
from typing import List, Dict

def _get_deterministic_seed(text: str) -> int:
    """Generate deterministic seed from text hash for reproducible transformations."""
    return int(hashlib.md5(text.encode()).hexdigest()[:8], 16)

def _pseudo_random(seed: int, index: int) -> float:
    """Generate pseudo-random value from seed and index (deterministic)."""
    return ((seed * 1103515245 + index + 12345) % (2**31)) / (2**31)

def _random_choice(options: list, seed: int, index: int) -> any:
    """Deterministically choose from options."""
    idx = int(_pseudo_random(seed, index) * len(options))
    return options[idx]

# ========== Replacement Mappings ==========

# Core formal-to-casual replacements (always applied)
FORMAL_TO_CASUAL = {
    # Common formal words
    "utilization": "use",
    "utilize": "use",
    "utilizes": "uses",
    "utilized": "used",
    "utilizing": "using",
    "demonstrate": "show",
    "demonstrates": "shows",
    "demonstrated": "showed",
    "demonstrating": "showing",
    "indicate": "show",
    "indicates": "shows",
    "indicated": "showed",
    "indicating": "showing",
    "furthermore": "plus",
    "moreover": "what's more",
    "consequently": "so",
    "therefore": "so",
    "thus": "so",
    "hence": "so",
    "in order to": "to",
    "due to the fact that": "because",
    "in spite of": "despite",
    "with regard to": "about",
    "in terms of": "in",
    "at this point in time": "now",
    "in the event that": "if",
    "for the purpose of": "for",
    "in the near future": "soon",
    "a large number of": "many",
    "a significant number of": "many",
    "a considerable amount of": "much",
    "it is important to note": "worth noting",
    "it should be noted": "note that",
    "it is worth mentioning": "interestingly",
    "it is essential to understand": "understand that",
    "it is crucial to recognize": "recognize that",
    # Additional AI-common formal phrases
    "in addition to": "besides",
    "in addition": "also",
    "as a result": "so",
    "on the contrary": "but",
    "in contrast": "but",
    "by contrast": "but",
    "as well as": "and",
    "in the context of": "for",
    "with respect to": "about",
    "in relation to": "about",
    "a wide range of": "many",
    "a variety of": "various",
    "a multitude of": "many",
    "the majority of": "most",
    "a great deal of": "much",
    "in the absence of": "without",
    "in the presence of": "with",
    "as a consequence": "so",
    "it is evident that": "clearly",
    "it is clear that": "clearly",
    "it is possible that": "maybe",
    "it is likely that": "likely",
    "it is necessary to": "you need to",
    "it is recommended that": "I recommend",
    "in order to ensure": "to make sure",
    "for the purpose of ensuring": "to make sure",
    "has the ability to": "can",
    "has the potential to": "could",
    "is able to": "can",
    "are able to": "can",
    "is capable of": "can",
    "are capable of": "can",
    "plays a role in": "affects",
    "plays a key role": "is key",
    "plays an important role": "matters for",
    "serves as a": "is a",
    "serves to": "helps",
    "contributes to": "adds to",
    "facilitates": "makes easier",
    "enables": "lets",
    "subsequently": "then",
    "additionally": "also",
    "notably": "notably,",
    "significantly": "a lot",
    "approximately": "about",
    "sufficiently": "enough",
    "particularly": "really",
    "extremely": "very",
    "regarding": "about",
    "concerning": "about",
    "pertaining to": "about",
    "amongst": "among",
    "amidst": "amid",
    "whilst": "while",
}

# Transition replacements with alternatives
TRANSITION_REPLACEMENTS = {
    "in conclusion": ["to wrap up", "so", "all in all", "looking back"],
    "to summarize": ["to sum up", "in short", "basically"],
    "to conclude": ["to wrap up", "so", "all in all"],
    "in summary": ["to sum up", "in short", "basically"],
    "for example": ["for instance", "like", "take"],
    "for instance": ["for example", "like", "say"],
    "in other words": ["put another way", "basically", "meaning"],
    "to put it simply": ["simply put", "basically", "in simple terms"],
    "on the other hand": ["but then", "conversely", "at the same time"],
    "however": ["but", "yet", "still", "though"],
    "nevertheless": ["even so", "still", "yet"],
    "nonetheless": ["even so", "still", "yet"],
    "although": ["even though", "while"],
    "even though": ["although", "while"],
}

# Sentence starters that AI overuses — replace with varied alternatives
SENTENCE_STARTER_REPLACEMENTS = [
    (r'^\s*It is (\w+) that\b', r"It's \1 that"),
    (r'^\s*There is (\w+)', r"There's \1"),
    (r'^\s*This is (\w+)', r"This is \1"),  # Keep as-is, but vary next time
    (r'^\s*These are (\w+)', r"These're \1"),
    (r'^\s*It can be seen that\b', r"We can see that"),
    (r'^\s*One might argue that\b', r"You could argue that"),
]

# Common academic/theoretical words ripe for synonym replacement
SYNONYM_MAP = {
    "important": ["key", "crucial", "vital", "central", "essential", "critical"],
    "significant": ["notable", "meaningful", "important", "major", "substantial"],
    "however": ["but", "yet", "though", "still", "that said"],
    "therefore": ["so", "as a result", "because of this", "hence"],
    "additionally": ["also", "plus", "on top of that", "what's more"],
    "furthermore": ["also", "plus", "what's more", "beyond that"],
    "consequently": ["so", "as a result", "because of this"],
    "regarding": ["about", "on", "as for", "when it comes to"],
    "particular": ["specific", "certain", "given", "individual"],
    "particularly": ["especially", "specifically", "notably", "above all"],
    "demonstrate": ["show", "display", "reveal", "point to", "highlight"],
    "indicate": ["show", "suggest", "point to", "signal", "hint at"],
    "establish": ["set up", "build", "create", "form", "lay out"],
    "determine": ["find", "figure out", "pin down", "settle", "work out"],
    "obtain": ["get", "gain", "find", "secure", "reach"],
    "require": ["need", "call for", "demand", "take"],
    "provide": ["give", "offer", "deliver", "bring"],
    "conduct": ["run", "do", "carry out", "perform"],
    "implement": ["put in place", "use", "apply", "carry out", "roll out"],
    "facilitate": ["help", "enable", "make easier", "support", "assist"],
    "enhance": ["boost", "improve", "build on", "strengthen", "add to"],
    "ensure": ["make sure", "guarantee", "see to it that"],
    "utilize": ["use", "apply", "tap into", "make use of"],
    "analyze": ["look at", "study", "examine", "dig into", "break down"],
    "evaluate": ["assess", "judge", "size up", "check", "weigh up"],
    "identify": ["spot", "find", "pick out", "pinpoint", "detect"],
    "achieve": ["reach", "get", "pull off", "hit", "attain"],
    "develop": ["build", "create", "shape", "put together", "form"],
    "involve": ["include", "cover", "take in", "mean", "entail"],
    "represent": ["stand for", "show", "reflect", "capture", "embody"],
    "address": ["deal with", "tackle", "handle", "speak to", "take on"],
    "potential": ["possible", "likely", "future", "prospective", "would-be"],
    "benefit": ["gain", "plus", "upside", "strength", "edge"],
    "challenge": ["hurdle", "problem", "tough spot", "difficulty", "obstacle"],
    "opportunity": ["chance", "opening", "possibility", "way forward", "window"],
    "strategy": ["plan", "approach", "tactic", "game plan", "way"],
    "perspective": ["view", "angle", "take", "outlook", "lens"],
    "fundamental": ["basic", "key", "core", "central", "underlying"],
    "comprehensive": ["broad", "wide", "full", "complete", "thorough"],
    "substantial": ["large", "big", "sizable", "considerable", "major"],
    "extensive": ["wide", "broad", "far-reaching", "large-scale", "deep"],
    "considerable": ["large", "big", "serious", "good", "fair"],
    "sufficient": ["enough", "plenty", "adequate", "ample"],
    "appropriate": ["right", "fitting", "proper", "suitable", "good"],
    "effective": ["workable", "useful", "good", "powerful", "strong"],
    "efficient": ["quick", "fast", "lean", "streamlined", "smooth"],
    "consistent": ["steady", "stable", "reliable", "regular", "even"],
    "necessary": ["needed", "required", "must-have", "key", "essential"],
    "various": ["different", "many", "several", "all sorts of", "diverse"],
    "numerous": ["many", "countless", "lots of", "plenty of", "tons of"],
    "additional": ["extra", "more", "added", "further", "new"],
    "initial": ["first", "early", "opening", "starting", "original"],
    "subsequent": ["later", "next", "following", "after", "resulting"],
    "previous": ["earlier", "past", "prior", "former", "old"],
    "overall": ["in general", "by and large", "on the whole", "all in all"],
    "primarily": ["mainly", "mostly", "chiefly", "first and foremost"],
    "typically": ["usually", "normally", "most often", "generally"],
    "frequently": ["often", "a lot", "commonly", "regularly", "time after time"],
    "currently": ["now", "right now", "today", "at present"],
    "previously": ["before", "earlier", "in the past", "once"],
    "ultimately": ["in the end", "finally", "at the end of the day", "when all's said and done"],
    "accordingly": ["so", "as such", "because of that", "in turn"],
    "conversely": ["on the other hand", "in contrast", "but then", "whereas"],
    "alternatively": ["instead", "on the other hand", "another way", "or"],
}


def vary_sentence_length(sentences: List[str], seed: int = None) -> List[str]:
    """Vary sentence lengths by combining or splitting sentences."""
    if seed is None:
        seed = _get_deterministic_seed(' '.join(sentences))

    varied = []
    i = 0

    while i < len(sentences):
        sentence = sentences[i]
        word_count = len(sentence.split())

        # Combine short sentences — increased probability from 0.3 to 0.5
        if word_count < 10 and i < len(sentences) - 1 and _pseudo_random(seed, i) < 0.5:
            next_sentence = sentences[i + 1]
            if next_sentence and len(next_sentence) > 0 and len(next_sentence.split()) < 18:
                # Use varied connectors
                connectors = [', and ', ', while ', ', but ', ', so ']
                connector = _random_choice(connectors, seed, i)
                combined = sentence.rstrip('.') + connector + next_sentence[0].lower() + next_sentence[1:]
                varied.append(combined)
                i += 2
                continue

        # Split long sentences — increased probability from 0.3 to 0.4
        if word_count > 20 and ', ' in sentence and _pseudo_random(seed, i + 100) < 0.4:
            # Try to split at clause boundary
            parts = sentence.rsplit(', ', 1)
            if len(parts) == 2 and len(parts[1].split()) >= 5:
                varied.append(parts[0] + '.')
                varied.append(parts[1][0].upper() + parts[1][1:])
                i += 1
                continue

        varied.append(sentence)
        i += 1

    return varied


def add_contractions(text: str, seed: int = None) -> str:
    """Add contractions to make text more natural."""
    if seed is None:
        seed = _get_deterministic_seed(text)

    contractions = [
        ("it is", "it's"),
        ("that is", "that's"),
        ("there is", "there's"),
        ("they are", "they're"),
        ("we are", "we're"),
        ("you are", "you're"),
        ("I am", "I'm"),
        ("do not", "don't"),
        ("does not", "doesn't"),
        ("did not", "didn't"),
        ("will not", "won't"),
        ("would not", "wouldn't"),
        ("could not", "couldn't"),
        ("should not", "shouldn't"),
        ("cannot", "can't"),
        ("is not", "isn't"),
        ("are not", "aren't"),
        ("was not", "wasn't"),
        ("were not", "weren't"),
        ("has not", "hasn't"),
        ("have not", "haven't"),
        ("had not", "hadn't"),
    ]

    match_index = [0]

    for formal, contraction in contractions:
        pattern = re.compile(r'\b' + formal + r'\b', re.IGNORECASE)

        def replace_with_chance(match, f=formal, c=contraction, idx_ref=match_index):
            idx_ref[0] += 1
            # Always contract in casual mode; 70% chance in academic mode
            if _pseudo_random(seed, idx_ref[0]) < 0.7:
                matched = match.group()
                if matched[0].isupper():
                    return c.capitalize()
                return c
            return match.group()

        text = pattern.sub(replace_with_chance, text)

    return text


def replace_formal_phrases(text: str, seed: int = None) -> str:
    """Replace formal phrases with more natural alternatives."""
    if seed is None:
        seed = _get_deterministic_seed(text)

    # Phase 1: Replace formal words (always applied)
    for formal, casual in FORMAL_TO_CASUAL.items():
        pattern = re.compile(r'\b' + re.escape(formal) + r'\b', re.IGNORECASE)

        def replace_with_casual(match, c=casual):
            matched = match.group()
            if matched[0].isupper():
                return c.capitalize()
            return c

        text = pattern.sub(replace_with_casual, text)

    # Phase 2: Replace transitions with varied alternatives
    match_index = [0]
    for formal, alternatives in TRANSITION_REPLACEMENTS.items():
        pattern = re.compile(r'\b' + re.escape(formal) + r'\b', re.IGNORECASE)

        def replace_with_alternative(match, alts=alternatives, idx_ref=match_index):
            idx_ref[0] += 1
            chosen = _random_choice(alts, seed, idx_ref[0])
            matched = match.group()
            if matched[0].isupper():
                return chosen.capitalize()
            return chosen

        text = pattern.sub(replace_with_alternative, text)

    # Phase 3: Synonym replacement for common academic words
    # Replace a subset of occurrences to add variety while preserving meaning
    for word, synonyms in SYNONYM_MAP.items():
        pattern = re.compile(r'\b' + re.escape(word) + r'\b', re.IGNORECASE)

        def replace_synonym(match, syns=synonyms, idx_ref=match_index):
            idx_ref[0] += 1
            # Replace ~40% of occurrences to maintain readability
            if _pseudo_random(seed, idx_ref[0] + 1000) < 0.4:
                chosen = _random_choice(syns, seed, idx_ref[0] + 1000)
                matched = match.group()
                if matched[0].isupper():
                    return chosen.capitalize()
                return chosen
            return match.group()

        text = pattern.sub(replace_synonym, text)

    return text


def add_personal_voice(text: str, seed: int = None) -> str:
    """Add personal voice elements where appropriate."""
    if seed is None:
        seed = _get_deterministic_seed(text)

    sentences = re.split(r'(?<=[.!?])\s+', text)
    modified = []

    personal_starters = [
        "I think ",
        "In my view, ",
        "From my perspective, ",
        "I believe ",
        "It seems to me that ",
    ]

    for i, sentence in enumerate(sentences):
        if not sentence or len(sentence) == 0:
            modified.append(sentence)
            continue
        # Add personal voice to declarative statements (every 4th sentence)
        if (i > 0 and i % 4 == 0 and
            not sentence.lower().startswith(("the", "this", "these", "those", "it", "a ", "an ")) and
            _pseudo_random(seed, i + 200) < 0.4):
            if not any(p in sentence.lower() for p in ["i think", "i believe", "my view"]):
                starter = _random_choice(personal_starters, seed, i + 200)
                sentence = starter + sentence[0].lower() + sentence[1:]

        modified.append(sentence)

    return ' '.join(modified)


def add_rhetorical_elements(text: str, seed: int = None) -> str:
    """Add rhetorical questions and natural speech patterns."""
    if seed is None:
        seed = _get_deterministic_seed(text)

    sentences = re.split(r'(?<=[.!?])\s+', text)
    modified = []

    rhetorical_starters = [
        "So, ",
        "Now, ",
        "Well, ",
        "You see, ",
        "Look, ",
    ]

    for i, sentence in enumerate(sentences):
        # Add rhetorical starters more aggressively (every 3rd sentence)
        if i > 0 and i % 3 == 0 and _pseudo_random(seed, i + 300) < 0.3:
            if not sentence.startswith(("But", "And", "Or", "So", "However", "Yet")):
                starter = _random_choice(rhetorical_starters, seed, i + 300)
                sentence = starter + sentence[0].lower() + sentence[1:]

        modified.append(sentence)

    return ' '.join(modified)


def vary_punctuation(text: str) -> str:
    """Vary punctuation usage to feel more natural."""
    # Reduce semicolons
    text = re.sub(r';\s*', '. ', text)
    return text


def break_structured_lists(text: str) -> str:
    """Break up overly structured list patterns."""
    text = re.sub(r'\bFirst(?:ly)?,?\s*', 'To start with, ', text, flags=re.IGNORECASE)
    text = re.sub(r'\bSecond(?:ly)?,?\s*', 'Next, ', text, flags=re.IGNORECASE)
    text = re.sub(r'\bThird(?:ly)?,?\s*', 'Then, ', text, flags=re.IGNORECASE)
    text = re.sub(r'\bFinally,?\s*', 'Lastly, ', text, flags=re.IGNORECASE)
    return text


def _insert_hedges(text: str, seed: int = None) -> str:
    """Insert hedging language to sound more human (less assertive like AI)."""
    if seed is None:
        seed = _get_deterministic_seed(text)

    sentences = re.split(r'(?<=[.!?])\s+', text)
    modified = []

    hedges = [
        (r'^\s*This shows\b', 'This tends to show'),
        (r'^\s*This suggests\b', 'This seems to suggest'),
        (r'^\s*This proves\b', 'This points to'),
        (r'^\s*It is clear\b', 'It seems clear'),
        (r'^\s*It is obvious\b', 'It looks fairly obvious'),
        (r'^\s*Research shows\b', 'Research tends to show'),
        (r'^\s*Studies show\b', 'Studies often show'),
        (r'^\s*Data shows\b', 'Data generally shows'),
        (r'^\s*The results show\b', 'The results seem to show'),
        (r'^\s*This means\b', 'This generally means'),
        (r'^\s*This implies\b', 'This tends to imply'),
    ]

    for i, sentence in enumerate(sentences):
        if not sentence:
            modified.append(sentence)
            continue

        # Apply hedge replacements (every other qualifying sentence)
        if i % 2 == 0 and _pseudo_random(seed, i + 500) < 0.35:
            for pattern_str, replacement in hedges:
                pattern = re.compile(pattern_str, re.IGNORECASE)
                if pattern.search(sentence):
                    sentence = pattern.sub(replacement, sentence)
                    break

        modified.append(sentence)

    return ' '.join(modified)


def _humanize_single_paragraph(text: str, academic_mode: bool, seed: int) -> str:
    """Humanize a single paragraph, preserving its internal structure."""
    # Split into sentences
    sentences = re.split(r'(?<=[.!?])\s+', text)

    # Apply transformations (order matters: structural first, then word-level)
    sentences = vary_sentence_length(sentences, seed)
    text = ' '.join(sentences)

    text = replace_formal_phrases(text, seed)
    text = add_contractions(text, seed)
    text = break_structured_lists(text)
    text = _insert_hedges(text, seed)

    if not academic_mode:
        text = add_personal_voice(text, seed)
        text = add_rhetorical_elements(text, seed)
    else:
        # Light touches for academic mode
        text = add_rhetorical_elements(text, seed)

    text = vary_punctuation(text)

    # Clean up any double spaces
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'\s+([.,;!?])', r'\1', text)

    return text.strip()


def humanize_text(text: str, academic_mode: bool = True) -> str:
    """
    Main humanization function.

    Args:
        text: The text to humanize
        academic_mode: If True, preserve academic tone; if False, more casual

    Returns:
        Humanized text (deterministic based on input text)
    """
    seed = _get_deterministic_seed(text)

    # Split into paragraphs first to preserve structure
    paragraphs = text.split('\n\n')
    humanized_paragraphs = []

    for i, para in enumerate(paragraphs):
        para = para.strip()
        if not para:
            humanized_paragraphs.append('')
            continue
        # Use paragraph-level seed for variety between paragraphs
        para_seed = seed + i * 7919
        humanized = _humanize_single_paragraph(para, academic_mode, para_seed)
        humanized_paragraphs.append(humanized)

    return '\n\n'.join(humanized_paragraphs).strip()


from app.humanizer.adapter import HumanizerAdapter, _cfg


class RuleBasedHumanizer(HumanizerAdapter):
    """Deterministic local-rule humanizer."""

    def humanize(self, text, mode=None, paragraphs=None):
        return self.humanize_structured(text, mode=mode, paragraphs=paragraphs)[0]

    def humanize_structured(self, text, mode=None, paragraphs=None, progress_cb=None):
        if mode is None:
            mode = _cfg('REWRITE_MODE_DEFAULT', 'median')

        if paragraphs is not None:
            def block_rewriter(body_text):
                return humanize_text(body_text, academic_mode=True)

            return self._humanize_segmented_structured(
                mode, paragraphs, block_rewriter, progress_cb=progress_cb)

        return humanize_text(text, academic_mode=True), []


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m app.humanizer.rule_based '<text>' [academic|casual]")
        print("   or: python -m app.humanizer.rule_based --file <path> [academic|casual]")
        sys.exit(1)
    
    mode = "academic"
    if len(sys.argv) > 2:
        mode = sys.argv[2] if sys.argv[2] in ["academic", "casual"] else "academic"
    
    if sys.argv[1] == "--file":
        file_path = sys.argv[2]
        if len(sys.argv) > 3:
            mode = sys.argv[3] if sys.argv[3] in ["academic", "casual"] else "academic"
        with open(file_path, 'r', encoding='utf-8') as f:
            text = f.read()
    else:
        text = sys.argv[1]
    
    academic_mode = (mode == "academic")
    result = humanize_text(text, academic_mode=academic_mode)
    print(result)
