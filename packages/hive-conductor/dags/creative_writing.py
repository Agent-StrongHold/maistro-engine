"""Creative Writing — Children's Books DAGs — 5 multi-node pipelines."""

DAGS = [
    {
        "id": "cw_picture_book",
        "name": "Picture Book",
        "department": "creative_writing",
        "description": "100-300 words, ages 2-5, with illustration notes",
        "nodes": [
            {"id": "concept", "prompt": "Create a picture book concept for ages 2-5 about: {input}. Include theme, main character, and emotional arc. Keep it simple and joyful.", "model": "gemini-2.5-flash", "role": "author"},
            {"id": "story", "prompt": "Write the picture book text: 100-300 words, simple sentences, repetition for rhythm, one idea per page spread (12-16 spreads). Concept: {concept}", "model": "gemini-2.5-pro", "role": "author"},
            {"id": "illustrations", "prompt": "Write illustration notes for each page spread: what to show, mood, colors, character expressions. Story: {story}", "model": "gemini-2.5-flash", "role": "illustrator"},
        ],
        "edges": [{"from_node": "concept", "to_node": "story"}, {"from_node": "story", "to_node": "illustrations"}],
        "evals": ["AgeAppropriateness", "StoryArc", "WordCount", "ReadAloudQuality"],
    },
    {
        "id": "cw_early_reader",
        "name": "Early Reader",
        "department": "creative_writing",
        "description": "300-800 words, ages 5-7, simple chapters",
        "nodes": [
            {"id": "outline", "prompt": "Outline an early reader (ages 5-7) about: {input}. 4-6 short chapters, clear problem/solution, relatable character. 300-800 words total.", "model": "gemini-2.5-flash", "role": "author"},
            {"id": "draft", "prompt": "Write the full early reader story. Short sentences, familiar words, dialogue, and humor. Include chapter breaks. Outline: {outline}", "model": "gemini-2.5-pro", "role": "author"},
            {"id": "polish", "prompt": "Polish for read-aloud quality: vary sentence length, add sensory details, ensure vocabulary is age-appropriate (Flesch-Kincaid grade 1-2). Draft: {draft}", "model": "gemini-2.5-flash", "role": "editor"},
        ],
        "edges": [{"from_node": "outline", "to_node": "draft"}, {"from_node": "draft", "to_node": "polish"}],
        "evals": ["AgeAppropriateness", "StoryArc", "CharacterConsistency", "WordCount", "ReadAloudQuality"],
    },
    {
        "id": "cw_chapter_book",
        "name": "Chapter Book Outline",
        "department": "creative_writing",
        "description": "1000-3000 words, ages 7-10, full outline with sample chapter",
        "nodes": [
            {"id": "world", "prompt": "Create the world and characters for a chapter book (ages 7-10) about: {input}. Include setting, 3 characters with distinct traits, and central conflict.", "model": "gemini-2.5-pro", "role": "author"},
            {"id": "structure", "prompt": "Outline 8-12 chapters with: chapter title, key events, character development, and cliffhangers. World: {world}", "model": "gemini-2.5-pro", "role": "author"},
            {"id": "sample", "prompt": "Write Chapter 1 in full (500-800 words). Hook the reader, introduce the protagonist, and end with a question. Structure: {structure}", "model": "gemini-2.5-pro", "role": "author"},
            {"id": "review", "prompt": "Review for age-appropriateness, pacing, and engagement. Suggest improvements. Sample chapter: {sample}", "model": "gemini-2.5-flash", "role": "editor"},
        ],
        "edges": [{"from_node": "world", "to_node": "structure"}, {"from_node": "structure", "to_node": "sample"}, {"from_node": "sample", "to_node": "review"}],
        "evals": ["CharacterConsistency", "StoryArc", "AgeAppropriateness", "WordCount"],
    },
    {
        "id": "cw_bedtime_story",
        "name": "Bedtime Story",
        "department": "creative_writing",
        "description": "200-500 words, calming tone, gentle resolution",
        "nodes": [
            {"id": "theme", "prompt": "Choose a calming bedtime theme for: {input}. Should involve gentle adventure, cozy settings, and a sleepy resolution. Ages 3-7.", "model": "gemini-2.5-flash", "role": "author"},
            {"id": "write", "prompt": "Write a bedtime story (200-500 words). Slow pacing, soft language, repetitive soothing phrases, ends with character falling asleep. Theme: {theme}", "model": "gemini-2.5-pro", "role": "author"},
            {"id": "calm", "prompt": "Review and adjust for maximum calming effect: slow the pace, soften any excitement, add sensory details (warm, soft, quiet). Story: {write}", "model": "gemini-2.5-flash", "role": "editor"},
        ],
        "edges": [{"from_node": "theme", "to_node": "write"}, {"from_node": "write", "to_node": "calm"}],
        "evals": ["AgeAppropriateness", "ReadAloudQuality", "WordCount"],
    },
    {
        "id": "cw_educational",
        "name": "Educational Story",
        "department": "creative_writing",
        "description": "500-1500 words, teaches a concept through narrative",
        "nodes": [
            {"id": "concept", "prompt": "Design an educational story that teaches: {input}. Define the concept, age target (5-10), and how the story will naturally embed the lesson.", "model": "gemini-2.5-flash", "role": "educator"},
            {"id": "narrative", "prompt": "Write the story (500-1500 words). The concept should emerge through character actions and discoveries, NOT through lecturing. Concept plan: {concept}", "model": "gemini-2.5-pro", "role": "author"},
            {"id": "verify", "prompt": "Verify: Is the educational content accurate? Is it naturally woven in? Would a child absorb the concept? Suggest fixes. Story: {narrative}", "model": "gemini-2.5-flash", "role": "editor"},
            {"id": "activities", "prompt": "Create 3 follow-up activities that reinforce the concept: a question, a hands-on activity, and a creative prompt. Story: {narrative}", "model": "gemini-2.5-flash", "role": "educator"},
        ],
        "edges": [{"from_node": "concept", "to_node": "narrative"}, {"from_node": "narrative", "to_node": "verify"}, {"from_node": "narrative", "to_node": "activities"}],
        "evals": ["AgeAppropriateness", "StoryArc", "CharacterConsistency", "WordCount", "ReadAloudQuality"],
    },
]
