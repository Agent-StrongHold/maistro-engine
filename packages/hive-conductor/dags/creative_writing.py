"""Creative Writing — Children's Books DAGs — grounded in REAL authors.

Every story uses real published authors as the quality benchmark.
The clarify node asks which authors to emulate. The writing nodes
reference specific techniques from those authors.
"""

DAGS = [
    {
        "id": "cw_picture_book",
        "name": "Picture Book",
        "department": "creative_writing",
        "description": "100-300 words, ages 2-5, in the style of real picture book masters",
        "nodes": [
            {
                "id": "clarify",
                "prompt": "TOOL_NODE",
                "model": "none",
                "role": "interviewer",
                "tool": "clarify",
                "tool_config": {
                    "questions": [
                        "Which picture book authors should we emulate? Pick 2-3 from: Eric Carle (bold collage, repetition), Mo Willems (humor, minimal text), Oliver Jeffers (whimsy, emotional depth), Julia Donaldson (rhyme, rhythm), Hervé Tullet (interactive, playful). What specifically do you love about their style?",
                        "What is the main character? (animal, child, object) Describe their appearance and one defining personality trait.",
                        "What is the emotional journey? (e.g., scared→brave, lonely→connected, confused→understanding)",
                        "What is the setting? Describe the world in sensory detail — colors, sounds, textures.",
                        "What is the single concept or lesson? (e.g., sharing, bedtime routine, counting, colors)",
                        "What repetitive phrase or rhythm should anchor the story? (Think 'Brown Bear, Brown Bear' or 'We're Going on a Bear Hunt')"
                    ]
                },
            },
            {
                "id": "research",
                "prompt": "TOOL_NODE",
                "model": "none",
                "role": "researcher",
                "tool": "web_search",
                "tool_config": {"queries_from_input": True, "query_template": "{input} picture book writing techniques craft", "max_results": 3},
            },
            {
                "id": "structure",
                "prompt": "Plan a 12-page picture book spread-by-spread. Study these real author techniques:\n\nAuthor reference from brief:\n{clarify}\n\nReal craft research:\n{research}\n\nApply their specific techniques:\n- Eric Carle: one bold image per spread, cumulative structure\n- Mo Willems: dialogue-driven, white space, facial expressions carry emotion\n- Oliver Jeffers: simple text hiding deep feeling, unexpected endings\n- Julia Donaldson: AABB rhyme, repeated refrains, satisfying resolution\n- Hervé Tullet: direct address to reader, 'press here' interactivity\n\nOutput: 12 spreads, each with 'Text:' and 'Illustration note:'",
                "model": "gemini-2.5-pro",
                "role": "author",
            },
            {
                "id": "write",
                "prompt": "Write the final picture book text. ONLY the read-aloud words.\n\nSpread plan:\n{structure}\nAuthor style targets:\n{clarify}\n\nRules:\n- Match the rhythm/style of the referenced authors\n- 100-300 words total\n- If emulating Donaldson: rhyme must scan perfectly\n- If emulating Willems: max 6 words per page\n- If emulating Carle: cumulative 'and then' structure\n- Must work as pure audio (parent reading aloud, no pictures needed to understand)",
                "model": "gemini-2.5-pro",
                "role": "author",
            },
        ],
        "edges": [
            {"from_node": "clarify", "to_node": "research"},
            {"from_node": "clarify", "to_node": "structure"},
            {"from_node": "research", "to_node": "structure"},
            {"from_node": "structure", "to_node": "write"},
            {"from_node": "clarify", "to_node": "write"},
        ],
        "evals": ["AgeAppropriateness", "StoryArc", "WordCount", "ReadAloudQuality"],
    },
    {
        "id": "cw_early_reader",
        "name": "Early Reader",
        "department": "creative_writing",
        "description": "300-800 words, ages 5-7, studying real early reader masters",
        "nodes": [
            {
                "id": "clarify",
                "prompt": "TOOL_NODE",
                "model": "none",
                "role": "interviewer",
                "tool": "clarify",
                "tool_config": {
                    "questions": [
                        "Which early reader authors should we study? Pick 2-3 from: Arnold Lobel (Frog and Toad — gentle friendship, quiet humor), Cynthia Rylant (Henry and Mudge — sensory detail, warmth), Mo Willems (Elephant & Piggie — pure dialogue, physical comedy), James Dean (Pete the Cat — repetition, positivity), Dav Pilkey (Dog Man — visual humor, energy). What do you love about them?",
                        "Who is the protagonist? Name, age, 2-3 personality traits, and what makes them relatable to a 5-7 year old.",
                        "What is the central problem? (lost toy, new school, making a friend, learning something hard)",
                        "What are 3 attempts the character makes to solve the problem? (try-fail-try-fail-succeed pattern like Frog and Toad)",
                        "What does the character LEARN by the end? How do they grow?",
                        "What is the tone? (Arnold Lobel gentle, Mo Willems silly, Cynthia Rylant warm, Dav Pilkey wild)"
                    ]
                },
            },
            {
                "id": "research",
                "prompt": "TOOL_NODE",
                "model": "none",
                "role": "researcher",
                "tool": "web_search",
                "tool_config": {"queries_from_input": True, "query_template": "{input} early reader writing craft techniques leveled reading", "max_results": 3},
            },
            {
                "id": "outline",
                "prompt": "Create a 4-chapter outline studying these masters:\n\nAuthor targets:\n{clarify}\n\nCraft research:\n{research}\n\nApply their techniques:\n- Lobel: each chapter is a complete mini-story, gentle pacing, dialogue reveals character\n- Rylant: sensory details in every paragraph, warmth without sentimentality\n- Willems: 90% dialogue, physical comedy, emotional honesty\n- Pilkey: visual gags, breaking the fourth wall, relentless energy\n\nEach chapter: title, 3-4 beats, emotional state, one moment that matches the target author's signature move.",
                "model": "gemini-2.5-pro",
                "role": "author",
            },
            {
                "id": "draft",
                "prompt": "Write the full early reader from this outline.\n\nOutline:\n{outline}\nAuthor style:\n{clarify}\n\nRules:\n- 300-800 words total\n- If Lobel style: short sentences, gentle humor, friendship at center\n- If Willems style: mostly dialogue, exclamation points, physical reactions\n- If Rylant style: sensory language, 'the sun felt warm on his fur'\n- Flesch-Kincaid grade 1-2\n- Show don't tell emotions",
                "model": "gemini-2.5-pro",
                "role": "author",
            },
        ],
        "edges": [
            {"from_node": "clarify", "to_node": "research"},
            {"from_node": "clarify", "to_node": "outline"},
            {"from_node": "research", "to_node": "outline"},
            {"from_node": "outline", "to_node": "draft"},
            {"from_node": "clarify", "to_node": "draft"},
        ],
        "evals": ["AgeAppropriateness", "StoryArc", "CharacterConsistency", "WordCount", "ReadAloudQuality"],
    },
    {
        "id": "cw_chapter_book",
        "name": "Chapter Book Outline",
        "department": "creative_writing",
        "description": "1000-3000 words, ages 7-10, studying real chapter book authors",
        "nodes": [
            {
                "id": "clarify",
                "prompt": "TOOL_NODE",
                "model": "none",
                "role": "interviewer",
                "tool": "clarify",
                "tool_config": {
                    "questions": [
                        "Which chapter book authors define the quality bar? Pick 2-3 from: Roald Dahl (subversive humor, vivid villains), Kate DiCamillo (spare prose, emotional depth), Rick Riordan (action pacing, mythology), Jeff Kinney (diary format, visual humor), Katherine Applegate (empathy, animal POV), Beverly Cleary (realistic kids, everyday adventures). What specifically makes their writing great?",
                        "What genre? (fantasy, mystery, adventure, realistic fiction, humor) Name 2 specific books in this genre the reader already loves.",
                        "Describe the protagonist: name, age, appearance, 3 traits, biggest fear, secret talent, deepest want.",
                        "What is the central conflict? What's at stake if the protagonist fails?",
                        "Who is the antagonist? What makes them compelling (Dahl's grotesque adults, Riordan's sympathetic monsters, DiCamillo's internal struggles)?",
                        "What is the theme without being preachy? (Dahl: justice for the powerless. DiCamillo: love persists. Riordan: found family.)"
                    ]
                },
            },
            {
                "id": "research",
                "prompt": "TOOL_NODE",
                "model": "none",
                "role": "researcher",
                "tool": "web_search",
                "tool_config": {"queries_from_input": True, "query_template": "{input} middle grade writing craft chapter book structure", "max_results": 3},
            },
            {
                "id": "world",
                "prompt": "Build the story world studying these masters:\n\nAuthor targets:\n{clarify}\n\nCraft research:\n{research}\n\nApply their worldbuilding:\n- Dahl: exaggerate one detail to absurdity, ground everything else in reality\n- DiCamillo: world revealed through character's emotional experience of it\n- Riordan: familiar world with hidden layer, rules explained through action\n- Cleary: hyper-specific real neighborhood, universal through specificity\n\nCreate: setting (500 words), 3 character profiles with distinct VOICES, world rules, tone guide.",
                "model": "gemini-2.5-pro",
                "role": "worldbuilder",
            },
            {
                "id": "structure",
                "prompt": "Outline 10 chapters using three-act structure.\n\nWorld:\n{world}\nAuthor style:\n{clarify}\n\nPacing reference:\n- Dahl: short chapters, cliffhangers, escalating absurdity\n- DiCamillo: alternating POV, slow build, devastating climax\n- Riordan: action-rest-action, chapter ends mid-sentence\n- Kinney: episodic, each chapter a complete embarrassment\n\nFor each chapter: title, 4-5 beats, emotional arc, chapter-ending hook.",
                "model": "gemini-2.5-pro",
                "role": "author",
            },
            {
                "id": "sample",
                "prompt": "Write Chapter 1 in full (600-900 words).\n\nOutline:\n{structure}\nWorld:\n{world}\nAuthor voice targets:\n{clarify}\n\nVoice checklist:\n- Dahl: sardonic narrator, invented words, adults are ridiculous\n- DiCamillo: lyrical, short sentences, emotional precision\n- Riordan: first-person snark, action verbs, humor under pressure\n- Cleary: third-person close, kid logic, small stakes feel enormous\n\nThe first paragraph must hook like your target author hooks.",
                "model": "gemini-2.5-pro",
                "role": "author",
            },
        ],
        "edges": [
            {"from_node": "clarify", "to_node": "research"},
            {"from_node": "clarify", "to_node": "world"},
            {"from_node": "research", "to_node": "world"},
            {"from_node": "world", "to_node": "structure"},
            {"from_node": "clarify", "to_node": "structure"},
            {"from_node": "structure", "to_node": "sample"},
            {"from_node": "world", "to_node": "sample"},
            {"from_node": "clarify", "to_node": "sample"},
        ],
        "evals": ["CharacterConsistency", "StoryArc", "AgeAppropriateness", "WordCount"],
    },
    {
        "id": "cw_bedtime_story",
        "name": "Bedtime Story",
        "department": "creative_writing",
        "description": "200-500 words, calming tone, studying real bedtime story masters",
        "nodes": [
            {
                "id": "clarify",
                "prompt": "TOOL_NODE",
                "model": "none",
                "role": "interviewer",
                "tool": "clarify",
                "tool_config": {
                    "questions": [
                        "Which bedtime story authors set the bar? Pick from: Margaret Wise Brown (Goodnight Moon — ritual, repetition, slowing rhythm), Sam McBratney (Guess How Much I Love You — parent-child warmth), Mem Fox (Time for Bed — gentle animals, lullaby cadence), Eric Litwin (Pete the Cat: Bedtime Blues — reassurance through humor). What makes their bedtime stories work?",
                        "What creature or character will the child follow to sleep? Describe them as soft, warm, and safe.",
                        "What is the gentle 'adventure' before sleep? (Margaret Wise Brown: saying goodnight to everything. Mem Fox: animals tucking in one by one.)",
                        "What sensory details should repeat? (Brown: 'goodnight ___'. McBratney: 'I love you to ___ and back'.)",
                        "What soothing phrase should repeat like a lullaby throughout? (Must have the same syllable count each time for rhythm.)"
                    ]
                },
            },
            {
                "id": "write",
                "prompt": "Write a bedtime story (200-500 words) studying these masters:\n\nBrief:\n{clarify}\n\nTechnique reference:\n- Margaret Wise Brown: catalog structure (goodnight room, goodnight moon...), pacing SLOWS as list grows\n- Sam McBratney: escalating metaphors of love, parent gets last word\n- Mem Fox: 'It's time for bed, little ___' repeated with different animals\n- The rhythm must physically slow the reader's breathing\n\nRules:\n- Sentences get shorter toward the end (Brown technique)\n- Repeat the soothing phrase 3-4 times at natural breathing pauses\n- Final 3 sentences: 5 words, 4 words, 3 words (decrescendo)\n- NO excitement, NO conflict after the first paragraph\n- End with eyes closing, breathing slowing",
                "model": "gemini-2.5-pro",
                "role": "author",
            },
            {
                "id": "rhythm",
                "prompt": "Review for sleep-inducing rhythm. Compare against Goodnight Moon's pacing:\n\n- Are sentences getting shorter toward the end?\n- Does the repetitive phrase land at natural exhale points?\n- Count syllables in the last 5 sentences — they should decrease\n- Is there any word that's sharp or energizing? Replace with soft alternative\n- Read it aloud in your head — does your breathing slow?\n\nStory:\n{write}",
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
        "description": "500-1500 words, teaches a concept, studying real educational story authors",
        "nodes": [
            {
                "id": "clarify",
                "prompt": "TOOL_NODE",
                "model": "none",
                "role": "interviewer",
                "tool": "clarify",
                "tool_config": {
                    "questions": [
                        "Which educational story authors should we study? Pick from: Joanna Cole (Magic School Bus — adventure IS the lesson), Andrea Beaty (Rosie Revere/Ada Twist — growth mindset through failure), Oliver Jeffers (Here We Are — big concepts made intimate), Jason Chin (Grand Canyon — narrative nonfiction, time travel through layers). How do they teach without lecturing?",
                        "What specific concept should the child learn? (Not vague — e.g., 'how seeds grow' not 'nature')",
                        "What age range? What's the ONE new thing they should understand after reading?",
                        "What character will discover this concept? How does learning it solve their personal problem? (Beaty technique: character NEEDS the knowledge)",
                        "What are 3 concrete scenes where the concept is demonstrated through action? (Cole technique: characters physically experience the science)",
                        "What common misconception should the story gently correct? (Chin technique: show the real thing being more amazing than the misconception)"
                    ]
                },
            },
            {
                "id": "research",
                "prompt": "TOOL_NODE",
                "model": "none",
                "role": "researcher",
                "tool": "web_search",
                "tool_config": {"queries_from_input": True, "query_template": "{input} children educational accurate facts", "max_results": 3},
            },
            {
                "id": "plan",
                "prompt": "Plan the educational story using real author techniques:\n\nBrief:\n{clarify}\nFact research:\n{research}\n\nStructure options (pick based on target author):\n- Cole/Magic School Bus: shrink characters INTO the concept, experience it physically\n- Beaty/Rosie Revere: character fails, fails, fails, then the concept clicks and they succeed\n- Jeffers/Here We Are: zoom out from personal to cosmic, concept as wonder\n- Chin/Grand Canyon: time layers, same place different era, concept revealed through change\n\nThe concept must emerge through CHARACTER ACTION. No character ever says 'did you know...'",
                "model": "gemini-2.5-pro",
                "role": "educator",
            },
            {
                "id": "write",
                "prompt": "Write the educational story (500-1500 words).\n\nPlan:\n{plan}\nFacts from research:\n{research}\nAuthor style:\n{clarify}\n\nRules:\n- Every fact must be ACCURATE (use the research)\n- Show, don't tell the concept\n- The story works as entertainment FIRST\n- A child who misses the lesson still enjoys the narrative\n- Include one 'wow' moment where reality is more amazing than fiction",
                "model": "gemini-2.5-pro",
                "role": "author",
            },
        ],
        "edges": [
            {"from_node": "clarify", "to_node": "research"},
            {"from_node": "clarify", "to_node": "plan"},
            {"from_node": "research", "to_node": "plan"},
            {"from_node": "plan", "to_node": "write"},
            {"from_node": "research", "to_node": "write"},
            {"from_node": "clarify", "to_node": "write"},
        ],
        "evals": ["AgeAppropriateness", "StoryArc", "CharacterConsistency", "WordCount", "ReadAloudQuality"],
    },
]
