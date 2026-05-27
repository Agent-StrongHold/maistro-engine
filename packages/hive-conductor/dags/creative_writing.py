"""Creative Writing — Children's Books DAGs — with REAL clarification.

Every story starts with 5-6 clarifying questions to build a detailed brief.
No one-sentence prompts that encourage hallucination.
The clarify node gathers: age, tone, length, themes, character details,
plot beats, moral, illustration style BEFORE any writing happens.
"""

DAGS = [
    {
        "id": "cw_picture_book",
        "name": "Picture Book",
        "department": "creative_writing",
        "description": "100-300 words, ages 2-5, with illustration notes",
        "nodes": [
            {
                "id": "clarify",
                "prompt": "TOOL_NODE",
                "model": "none",
                "role": "interviewer",
                "tool": "clarify",
                "tool_config": {
                    "questions": [
                        "What is the main character? (animal, child, object) Describe their appearance and one defining personality trait.",
                        "What is the emotional journey? (e.g., scared→brave, lonely→connected, confused→understanding)",
                        "What is the setting? Describe the world in sensory detail — colors, sounds, textures.",
                        "What is the single concept or lesson? (e.g., sharing, bedtime routine, counting, colors)",
                        "What illustration style? (e.g., watercolor, bold flat colors, collage, pencil sketch)",
                        "What repetitive phrase or rhythm should anchor the story? (e.g., 'And then... and then...' or 'One more step')"
                    ]
                },
            },
            {
                "id": "structure",
                "prompt": "Using these detailed answers, plan a 12-page picture book spread-by-spread. Each spread gets ONE sentence of text and ONE illustration note.\n\nBrief:\n{clarify}\n\nRules:\n- Target age: 2-5\n- Total words: 100-300\n- Use the repetitive phrase from the brief\n- Build emotional arc from the brief\n- End with resolution + warmth\n\nOutput: numbered list of 12 spreads, each with 'Text:' and 'Illustration:'",
                "model": "gemini-2.5-pro",
                "role": "author",
            },
            {
                "id": "write",
                "prompt": "Write the final picture book text from this spread plan. ONLY the words a parent would read aloud — no stage directions, no illustration notes in the text itself.\n\nSpread plan:\n{structure}\n\nRules:\n- Simple words (max 2 syllables preferred)\n- Repetition for rhythm\n- Each page: 1-2 short sentences\n- Total: 100-300 words\n- Must feel complete as a read-aloud experience",
                "model": "gemini-2.5-pro",
                "role": "author",
            },
            {
                "id": "illustrations",
                "prompt": "Write detailed illustration briefs for each spread. Include: composition, color palette, character expression, background details, mood lighting.\n\nStory text:\n{write}\nSpread plan:\n{structure}\nStyle direction from brief:\n{clarify}",
                "model": "gemini-2.5-flash",
                "role": "art_director",
            },
        ],
        "edges": [
            {"from_node": "clarify", "to_node": "structure"},
            {"from_node": "structure", "to_node": "write"},
            {"from_node": "structure", "to_node": "illustrations"},
            {"from_node": "write", "to_node": "illustrations"},
        ],
        "evals": ["AgeAppropriateness", "StoryArc", "WordCount", "ReadAloudQuality"],
    },
    {
        "id": "cw_early_reader",
        "name": "Early Reader",
        "department": "creative_writing",
        "description": "300-800 words, ages 5-7, simple chapters",
        "nodes": [
            {
                "id": "clarify",
                "prompt": "TOOL_NODE",
                "model": "none",
                "role": "interviewer",
                "tool": "clarify",
                "tool_config": {
                    "questions": [
                        "Who is the protagonist? Name, age, 2-3 personality traits, and what makes them relatable to a 5-7 year old.",
                        "What is the central problem/conflict? It should be age-appropriate (lost toy, new school, making a friend, learning something hard).",
                        "What are 3 attempts the character makes to solve the problem? (try-fail-try-fail-succeed pattern)",
                        "What does the character LEARN by the end? How do they grow?",
                        "What is the tone? (funny, adventurous, gentle, silly, suspenseful-but-safe)",
                        "Are there any supporting characters? Describe their role in helping or challenging the protagonist."
                    ]
                },
            },
            {
                "id": "outline",
                "prompt": "Create a 4-chapter outline for an early reader (ages 5-7). Use the detailed character and plot brief below.\n\nBrief:\n{clarify}\n\nEach chapter needs:\n- Chapter title (fun, hints at content)\n- 3-4 scene beats\n- Emotional state of protagonist\n- One moment of humor or surprise\n\nTotal target: 300-800 words across all chapters.",
                "model": "gemini-2.5-pro",
                "role": "author",
            },
            {
                "id": "draft",
                "prompt": "Write the full early reader from this outline. \n\nOutline:\n{outline}\nCharacter brief:\n{clarify}\n\nRules:\n- Short sentences (5-10 words average)\n- Familiar words only (Flesch-Kincaid grade 1-2)\n- Dialogue in every chapter\n- At least one funny moment per chapter\n- Show don't tell emotions (\"her tummy felt wiggly\" not \"she was nervous\")\n- 300-800 words total",
                "model": "gemini-2.5-pro",
                "role": "author",
            },
            {
                "id": "polish",
                "prompt": "Review and polish for read-aloud quality:\n- Vary sentence length (short-short-long pattern)\n- Add sensory details (sounds, textures, smells)\n- Check vocabulary is age-appropriate\n- Ensure the ending feels satisfying\n- Add one callback to an earlier moment (kids love that)\n\nDraft:\n{draft}",
                "model": "gemini-2.5-flash",
                "role": "editor",
            },
        ],
        "edges": [
            {"from_node": "clarify", "to_node": "outline"},
            {"from_node": "clarify", "to_node": "draft"},
            {"from_node": "outline", "to_node": "draft"},
            {"from_node": "draft", "to_node": "polish"},
        ],
        "evals": ["AgeAppropriateness", "StoryArc", "CharacterConsistency", "WordCount", "ReadAloudQuality"],
    },
    {
        "id": "cw_chapter_book",
        "name": "Chapter Book Outline",
        "department": "creative_writing",
        "description": "1000-3000 words, ages 7-10, full outline with sample chapter",
        "nodes": [
            {
                "id": "clarify",
                "prompt": "TOOL_NODE",
                "model": "none",
                "role": "interviewer",
                "tool": "clarify",
                "tool_config": {
                    "questions": [
                        "What genre? (fantasy, mystery, adventure, realistic fiction, sci-fi, humor) What are 2 books in this genre the reader might already love?",
                        "Describe the protagonist in detail: name, age, appearance, 3 personality traits, biggest fear, secret talent, what they want more than anything.",
                        "Describe the world/setting: time period, location, 3 specific sensory details that make it unique.",
                        "What is the central conflict? What's at stake if the protagonist fails?",
                        "Who is the antagonist or opposing force? What makes them compelling (not just 'evil')?",
                        "What is the theme/moral without being preachy? (friendship, courage, identity, belonging)"
                    ]
                },
            },
            {
                "id": "world",
                "prompt": "Build the story world from this brief. Create:\n- Setting description (500 words, vivid sensory detail)\n- Character profiles (protagonist + 2 supporting characters with distinct voices)\n- Rules of the world (what's possible, what's not)\n- Tone guide (how does this book FEEL to read?)\n\nBrief:\n{clarify}",
                "model": "gemini-2.5-pro",
                "role": "worldbuilder",
            },
            {
                "id": "structure",
                "prompt": "Outline 10 chapters using the three-act structure:\n- Act 1 (ch 1-3): Setup, inciting incident, first threshold\n- Act 2 (ch 4-7): Rising action, midpoint reversal, dark moment\n- Act 3 (ch 8-10): Climax, resolution, new normal\n\nFor each chapter: title, 4-5 scene beats, emotional arc, cliffhanger ending.\n\nWorld:\n{world}\nBrief:\n{clarify}",
                "model": "gemini-2.5-pro",
                "role": "author",
            },
            {
                "id": "sample",
                "prompt": "Write Chapter 1 in full (600-900 words). This must:\n- Hook the reader in the first paragraph\n- Introduce the protagonist through ACTION (not description)\n- Establish the world through the character's experience of it\n- End with a question or surprise that makes you turn the page\n- Use the character's distinct VOICE\n\nOutline:\n{structure}\nWorld:\n{world}",
                "model": "gemini-2.5-pro",
                "role": "author",
            },
        ],
        "edges": [
            {"from_node": "clarify", "to_node": "world"},
            {"from_node": "world", "to_node": "structure"},
            {"from_node": "clarify", "to_node": "structure"},
            {"from_node": "structure", "to_node": "sample"},
            {"from_node": "world", "to_node": "sample"},
        ],
        "evals": ["CharacterConsistency", "StoryArc", "AgeAppropriateness", "WordCount"],
    },
    {
        "id": "cw_bedtime_story",
        "name": "Bedtime Story",
        "department": "creative_writing",
        "description": "200-500 words, calming tone, gentle resolution",
        "nodes": [
            {
                "id": "clarify",
                "prompt": "TOOL_NODE",
                "model": "none",
                "role": "interviewer",
                "tool": "clarify",
                "tool_config": {
                    "questions": [
                        "What creature or character will the child follow to sleep? Describe them as soft, warm, and safe.",
                        "What is the gentle 'adventure' before sleep? (following moonbeams, counting stars, visiting dream animals)",
                        "What sensory details should repeat? (warm blanket, soft pillow, quiet sounds, dim light)",
                        "What is the child's current state? (too excited to sleep, scared of dark, missing someone, just had a big day)",
                        "What soothing phrase should repeat like a lullaby throughout?"
                    ]
                },
            },
            {
                "id": "write",
                "prompt": "Write a bedtime story (200-500 words) using this detailed brief.\n\nBrief:\n{clarify}\n\nRules:\n- Pacing gets SLOWER as the story progresses (shorter sentences toward end)\n- Repeat the soothing phrase 3-4 times\n- Use 'you' or character's name (child identifies with protagonist)\n- Sensory language: warm, soft, quiet, gentle, slow\n- NO excitement, NO conflict, NO surprises\n- End with eyes closing, breathing slowing, sleep arriving\n- Last line should be almost a whisper",
                "model": "gemini-2.5-pro",
                "role": "author",
            },
            {
                "id": "rhythm",
                "prompt": "Review for sleep-inducing rhythm:\n- Are sentences getting shorter toward the end?\n- Is the repetitive phrase placed at natural breathing pauses?\n- Remove any words that are sharp or energizing (replace with soft alternatives)\n- Add one more sensory detail per paragraph (warmth, softness, quiet)\n- Ensure the very last sentence trails off...\n\nStory:\n{write}",
                "model": "gemini-2.5-flash",
                "role": "editor",
            },
        ],
        "edges": [
            {"from_node": "clarify", "to_node": "write"},
            {"from_node": "write", "to_node": "rhythm"},
        ],
        "evals": ["AgeAppropriateness", "ReadAloudQuality", "WordCount"],
    },
    {
        "id": "cw_educational",
        "name": "Educational Story",
        "department": "creative_writing",
        "description": "500-1500 words, teaches a concept through narrative",
        "nodes": [
            {
                "id": "clarify",
                "prompt": "TOOL_NODE",
                "model": "none",
                "role": "interviewer",
                "tool": "clarify",
                "tool_config": {
                    "questions": [
                        "What specific concept should the child learn? (not vague — e.g., 'how seeds grow into plants' not 'nature')",
                        "What age range? What do they already know about this topic? What's the ONE new thing they should understand after reading?",
                        "What character will discover/learn this concept? How does the concept connect to their personal goal or problem?",
                        "What are 3 concrete scenes where the concept is demonstrated through action (not explained through dialogue)?",
                        "What common misconception about this topic should the story gently correct?",
                        "What hands-on activity could a parent do with the child after reading to reinforce the concept?"
                    ]
                },
            },
            {
                "id": "plan",
                "prompt": "Plan the educational story structure. The concept must emerge NATURALLY through the character's experience — never through a character 'explaining' it.\n\nBrief:\n{clarify}\n\nCreate:\n- Character arc (how learning the concept solves their problem)\n- 3 scenes showing the concept in action\n- The 'aha moment' (when character and reader both understand)\n- How to correct the misconception without being preachy",
                "model": "gemini-2.5-pro",
                "role": "educator",
            },
            {
                "id": "write",
                "prompt": "Write the educational story (500-1500 words).\n\nPlan:\n{plan}\nBrief:\n{clarify}\n\nRules:\n- Show, don't tell the concept\n- NO character says 'did you know...' or 'the reason is...'\n- The concept is discovered through DOING\n- Include sensory details that make the concept tangible\n- The story works as a story FIRST, education second\n- A child who doesn't catch the lesson still enjoys the narrative",
                "model": "gemini-2.5-pro",
                "role": "author",
            },
            {
                "id": "activities",
                "prompt": "Create 3 follow-up activities that reinforce the concept:\n1. A question that checks understanding (not yes/no — open-ended)\n2. A hands-on activity (uses household items, takes <10 min)\n3. A creative prompt (draw, build, or imagine something related)\n\nStory:\n{write}\nConcept from brief:\n{clarify}",
                "model": "gemini-2.5-flash",
                "role": "educator",
            },
        ],
        "edges": [
            {"from_node": "clarify", "to_node": "plan"},
            {"from_node": "plan", "to_node": "write"},
            {"from_node": "clarify", "to_node": "write"},
            {"from_node": "write", "to_node": "activities"},
            {"from_node": "clarify", "to_node": "activities"},
        ],
        "evals": ["AgeAppropriateness", "StoryArc", "CharacterConsistency", "WordCount", "ReadAloudQuality"],
    },
]
