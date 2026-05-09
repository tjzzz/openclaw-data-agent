#!/usr/bin/env python3
"""
Text Humanizer - Transform AI-generated text to appear more human-written.
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

# Replacement mappings
FORMAL_TO_CASUAL = {
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
    "therefore": "that's why",
    "thus": "so",
    "hence": "so",
    "in order to": "to",
    "due to the fact that": "because",
    "in spite of": "despite",
    "with regard to": "about",
    "in terms of": "when it comes to",
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
}

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


def vary_sentence_length(sentences: List[str], seed: int = None) -> List[str]:
    """Vary sentence lengths by combining or splitting sentences."""
    if seed is None:
        seed = _get_deterministic_seed(' '.join(sentences))
    
    varied = []
    i = 0
    
    while i < len(sentences):
        sentence = sentences[i]
        word_count = len(sentence.split())
        
        # Occasionally combine short sentences
        if word_count < 8 and i < len(sentences) - 1 and _pseudo_random(seed, i) < 0.3:
            next_sentence = sentences[i + 1]
            if next_sentence and len(next_sentence) > 0 and len(next_sentence.split()) < 15:
                combined = sentence.rstrip('.') + ', and ' + next_sentence[0].lower() + next_sentence[1:]
                varied.append(combined)
                i += 2
                continue
        
        # Occasionally split long sentences
        if word_count > 25 and ', ' in sentence and _pseudo_random(seed, i + 100) < 0.3:
            parts = sentence.rsplit(', ', 1)
            if len(parts) == 2:
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
    
    match_index = [0]  # Use list to allow modification in nested function
    
    for formal, contraction in contractions:
        pattern = re.compile(r'\b' + formal + r'\b', re.IGNORECASE)
        
        def replace_with_chance(match, f=formal, c=contraction, idx_ref=match_index):
            idx_ref[0] += 1
            if _pseudo_random(seed, idx_ref[0]) < 0.6:
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
    
    # Replace formal words
    for formal, casual in FORMAL_TO_CASUAL.items():
        pattern = re.compile(r'\b' + re.escape(formal) + r'\b', re.IGNORECASE)
        
        def replace_with_casual(match, c=casual):
            matched = match.group()
            if matched[0].isupper():
                return c.capitalize()
            return c
        
        text = pattern.sub(replace_with_casual, text)
    
    # Replace transitions with varied alternatives
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
        # Skip empty sentences
        if not sentence or len(sentence) == 0:
            modified.append(sentence)
            continue
        # Occasionally add personal voice to statements
        if (i > 0 and i % 5 == 0 and 
            not sentence.lower().startswith(("the", "this", "these", "those", "it")) and
            _pseudo_random(seed, i + 200) < 0.3):
            # Don't modify if already has personal voice
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
        # Occasionally add rhetorical starters
        if i > 0 and i % 4 == 0 and _pseudo_random(seed, i + 300) < 0.2:
            if not sentence.startswith(("But", "And", "Or", "So", "However")):
                starter = _random_choice(rhetorical_starters, seed, i + 300)
                sentence = starter + sentence[0].lower() + sentence[1:]
        
        modified.append(sentence)
    
    return ' '.join(modified)


def vary_punctuation(text: str) -> str:
    """Vary punctuation usage to feel more natural."""
    # Light punctuation variation - only reduce semicolons, don't破坏原文结构
    # 标点变化要轻柔 - 只减少分号使用，不要替换括号（会破坏原文结构）
    text = re.sub(r';\s*', '. ', text)
    
    return text


def break_structured_lists(text: str) -> str:
    """Break up overly structured list patterns."""
    # Replace "First... Second... Third..." patterns
    text = re.sub(r'\bFirst(?:ly)?,?\s*', 'To start with, ', text, flags=re.IGNORECASE)
    text = re.sub(r'\bSecond(?:ly)?,?\s*', 'Next, ', text, flags=re.IGNORECASE)
    text = re.sub(r'\bThird(?:ly)?,?\s*', 'Then, ', text, flags=re.IGNORECASE)
    text = re.sub(r'\bFinally,?\s*', 'Lastly, ', text, flags=re.IGNORECASE)
    
    return text


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
    
    # Split into sentences
    sentences = re.split(r'(?<=[.!?])\s+', text)
    
    # Apply transformations
    sentences = vary_sentence_length(sentences, seed)
    text = ' '.join(sentences)
    
    text = replace_formal_phrases(text, seed)
    text = add_contractions(text, seed)
    text = break_structured_lists(text)
    
    if not academic_mode:
        text = add_personal_voice(text, seed)
        text = add_rhetorical_elements(text, seed)
    else:
        # Light personal touches for academic mode
        text = add_rhetorical_elements(text, seed)
    
    text = vary_punctuation(text)
    
    # Clean up any double spaces
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'\s+([.,;!?])', r'\1', text)
    
    return text.strip()


def humanize_by_sections(text: str, high_ai_sections: List[Dict] = None) -> str:
    """
    Humanize specific sections that have high AI scores.
    If no sections specified, humanize entire text.
    """
    if not high_ai_sections:
        return humanize_text(text)
    
    paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
    modified_paragraphs = []
    
    for i, paragraph in enumerate(paragraphs, 1):
        # Check if this paragraph should be humanized
        should_humanize = any(
            s.get("paragraph") == i and s.get("ai_score", 0) > 30
            for s in high_ai_sections
        )
        
        if should_humanize:
            modified_paragraphs.append(humanize_text(paragraph))
        else:
            modified_paragraphs.append(paragraph)
    
    return '\n\n'.join(modified_paragraphs)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python humanize.py '<text>' [academic|casual]")
        print("   or: python humanize.py --file <path> [academic|casual]")
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
