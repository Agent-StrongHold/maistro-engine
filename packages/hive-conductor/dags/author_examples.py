"""Real author examples — what GOOD children's writing looks like.

These are short excerpts and style descriptions from real published
children's books. DAG nodes reference these as the quality bar.
The hill-climber scores output AGAINST these examples.
"""

# --- PICTURE BOOKS (ages 2-5) ---

SEUSS = {
    "author": "Dr. Seuss",
    "books": ["The Cat in the Hat", "Green Eggs and Ham", "One Fish Two Fish"],
    "technique": "Anapestic tetrameter, invented words, absurd escalation, rhyme drives plot",
    "example": """I do not like green eggs and ham.
I do not like them, Sam-I-Am.
Would you like them here or there?
I would not like them anywhere.""",
    "rules": [
        "Rhyme scheme drives the entire narrative forward",
        "Limited vocabulary (Green Eggs uses only 50 words)",
        "Repetition with variation — same structure, new context",
        "Absurdity escalates but logic is internally consistent",
        "Every page turn reveals a new ridiculous scenario",
    ],
}

ERIC_CARLE = {
    "author": "Eric Carle",
    "books": ["The Very Hungry Caterpillar", "Brown Bear Brown Bear", "The Grouchy Ladybug"],
    "technique": "Cumulative structure, one concept per spread, bold repetition",
    "example": """On Monday he ate through one apple. But he was still hungry.
On Tuesday he ate through two pears. But he was still hungry.
On Wednesday he ate through three plums. But he was still hungry.""",
    "rules": [
        "Cumulative pattern — each page adds ONE thing",
        "Same sentence structure repeated with one variable changed",
        "Days/numbers/colors as organizing scaffold",
        "Child can 'read' by predicting the pattern",
        "Satisfying payoff when pattern breaks at the end",
    ],
}

MO_WILLEMS = {
    "author": "Mo Willems",
    "books": ["Don't Let the Pigeon Drive the Bus!", "Elephant & Piggie series", "Knuffle Bunny"],
    "technique": "Minimal text, maximum emotion through typography and punctuation",
    "example": """Gerald: I am sad.
Piggie: Why?
Gerald: I cannot fly.
Piggie: Oh.
Gerald: Birds can fly. Bees can fly. Butterflies can fly!
Piggie: That is true.
Gerald: BUT NOT ELEPHANTS!""",
    "rules": [
        "Max 6 words per speech bubble/line",
        "Emotion carried by CAPS, punctuation, font size",
        "Dialogue only — no narration needed",
        "Physical comedy described in fewest possible words",
        "Reader does the voices — text is a script",
    ],
}

JULIA_DONALDSON = {
    "author": "Julia Donaldson",
    "books": ["The Gruffalo", "Room on the Broom", "Stick Man"],
    "technique": "Perfect AABB rhyme, repeated refrains, three-part structure",
    "example": """A mouse took a stroll through the deep dark wood.
A fox saw the mouse, and the mouse looked good.
"Where are you going to, little brown mouse?
Come and have lunch in my underground house."
"It's terribly kind of you, Fox, but no—
I'm going to have lunch with a gruffalo." """,
    "rules": [
        "AABB rhyme that NEVER forces an unnatural word",
        "Three encounters before the climax (rule of three)",
        "Refrain repeated exactly, building anticipation",
        "Clever protagonist outwits bigger creatures",
        "Rhythm so strong you can clap along",
    ],
}

# --- EARLY READERS (ages 5-7) ---

JUNIE_B_JONES = {
    "author": "Barbara Park",
    "books": ["Junie B. Jones and the Stupid Smelly Bus", "Junie B. First Grader"],
    "technique": "First-person kid voice, grammar 'mistakes' that ARE the voice, raw honesty",
    "example": """My name is Junie B. Jones. The B stands for Beatrice. Except I don't like Beatrice. I just like B and that's all.
I'm almost six years old. Almost six is when you get to go to school. Except I don't want to go there. 'Cause what if I don't know where the bathroom is? And what if I get lost? And what if the bus smells bad?""",
    "rules": [
        "First person, present tense, stream of consciousness",
        "Grammar reflects how a 5-year-old ACTUALLY talks",
        "'Cause' not 'because', 'plus also' not 'additionally'",
        "Worries are specific and physical (not abstract)",
        "Humor comes from kid logic applied to adult situations",
    ],
}

FROG_AND_TOAD = {
    "author": "Arnold Lobel",
    "books": ["Frog and Toad Are Friends", "Frog and Toad Together"],
    "technique": "Gentle humor, philosophical depth in simple language, friendship as anchor",
    "example": """Toad sat on the front porch. Frog came along and said, "What is the matter, Toad? You are looking sad."
"Yes," said Toad. "This is my sad time of day. It is the time when I wait for the mail."
"Why is that a sad time?" asked Frog.
"Because I never get any mail," said Toad.""",
    "rules": [
        "Short declarative sentences",
        "Emotion named simply: 'I am sad'",
        "One friend has the problem, the other helps",
        "Resolution is quiet, not dramatic",
        "Each story is complete in 3-5 pages",
    ],
}

ELEPHANT_AND_PIGGIE = {
    "author": "Mo Willems",
    "books": ["I Am Invited to a Party!", "Should I Share My Ice Cream?", "We Are in a Book!"],
    "technique": "Pure dialogue, emotional extremes, meta-humor",
    "example": """Piggie: I have a ball!
Gerald: A ball!
Piggie: Let's throw it!
Gerald: Yes! Let's throw it!
(they throw it)
Gerald: That was fun.
Piggie: Let's do it again!
Gerald: Again! Again!""",
    "rules": [
        "ONLY dialogue — zero narration",
        "Emotions go from 0 to 100 instantly",
        "Exclamation points are the default",
        "Repetition = comedy (say it three times)",
        "The 'problem' is always tiny but feels enormous",
    ],
}

# --- CHAPTER BOOKS (ages 7-10) ---

ROALD_DAHL = {
    "author": "Roald Dahl",
    "books": ["Matilda", "Charlie and the Chocolate Factory", "The BFG"],
    "technique": "Subversive humor, grotesque adults, child heroes, invented language",
    "example": """The Trunchbull had a look about her of an infuriated bull that is about to charge. She was glaring at Matilda with those dangerous little eyes and Matilda looked right back at her. "I have not moved from my desk, Miss Trunchbull, since the lesson began," she said. "I can vouch for that," Miss Honey said.""",
    "rules": [
        "Adults are grotesque, exaggerated, physically described in disgusting detail",
        "Child protagonist is smarter than every adult",
        "Invented words (splendiferous, whizzpopping)",
        "Short chapters, each ending with a hook",
        "Justice: bad adults ALWAYS get punished spectacularly",
    ],
}

DIARY_OF_A_WIMPY_KID = {
    "author": "Jeff Kinney",
    "books": ["Diary of a Wimpy Kid", "Rodrick Rules", "The Last Straw"],
    "technique": "Diary format, unreliable narrator, social hierarchy as stakes",
    "example": """Let me just say for the record that I think middle school is the dumbest idea ever invented. You got kids like me who haven't hit their growth spurt yet mixed in with these gorillas who need to shave twice a day. And then they wonder why bullying is such a big problem in middle school.""",
    "rules": [
        "First person diary — 'let me just say'",
        "Narrator thinks he's the hero but reader sees he's not",
        "Social status is life-or-death stakes",
        "Every plan backfires in the most embarrassing way",
        "Short paragraphs, could be illustrated",
    ],
}

PERCY_JACKSON = {
    "author": "Rick Riordan",
    "books": ["The Lightning Thief", "The Sea of Monsters"],
    "technique": "First-person snark, action pacing, mythology made personal",
    "example": """Look, I didn't want to be a half-blood. If you're reading this because you think you might be one, my advice is: close this book right now. Believe whatever lie your mom or dad told you about your birth, and try to lead a normal life. Being a half-blood is dangerous. It's scary. Most of the time, it gets you killed in painful, nasty ways.""",
    "rules": [
        "First line hooks with direct address to reader",
        "Humor under life-threatening pressure",
        "Every chapter ends mid-action",
        "Mythology explained through character's sarcastic lens",
        "ADHD/dyslexia as superpowers, not disabilities",
    ],
}

# --- BEDTIME (ages 2-5) ---

GOODNIGHT_MOON = {
    "author": "Margaret Wise Brown",
    "books": ["Goodnight Moon", "The Runaway Bunny", "Big Red Barn"],
    "technique": "Catalog/ritual structure, rhythm slows breathing, repetition as comfort",
    "example": """Goodnight room. Goodnight moon.
Goodnight cow jumping over the moon.
Goodnight light and the red balloon.
Goodnight bears. Goodnight chairs.
Goodnight kittens. And goodnight mittens.""",
    "rules": [
        "List structure — saying goodnight to each thing",
        "Rhythm matches a slowing heartbeat",
        "Rhyme is soft (moon/balloon, chairs/bears)",
        "World gets smaller: room → objects → whisper",
        "Last line is almost silence: 'Goodnight noises everywhere'",
    ],
}

GUESS_HOW_MUCH = {
    "author": "Sam McBratney",
    "books": ["Guess How Much I Love You"],
    "technique": "Escalating metaphors, parent always wins, love as competition that's really comfort",
    "example": """'I love you as high as I can reach,' said Little Nutbrown Hare.
'I love you as high as I can reach,' said Big Nutbrown Hare.
That is quite high, thought Little Nutbrown Hare. I wish I had such long arms.""",
    "rules": [
        "Child tries to express big feeling with small body",
        "Parent matches and exceeds — but gently",
        "Physical metaphors (reach, hop, far as)",
        "Ends with child asleep, parent gets last word",
        "Love is the only subject — nothing else happens",
    ],
}

# --- Lookup by category ---
PICTURE_BOOK_EXAMPLES = [SEUSS, ERIC_CARLE, MO_WILLEMS, JULIA_DONALDSON]
EARLY_READER_EXAMPLES = [JUNIE_B_JONES, FROG_AND_TOAD, ELEPHANT_AND_PIGGIE]
CHAPTER_BOOK_EXAMPLES = [ROALD_DAHL, DIARY_OF_A_WIMPY_KID, PERCY_JACKSON]
BEDTIME_EXAMPLES = [GOODNIGHT_MOON, GUESS_HOW_MUCH]

ALL_EXAMPLES = PICTURE_BOOK_EXAMPLES + EARLY_READER_EXAMPLES + CHAPTER_BOOK_EXAMPLES + BEDTIME_EXAMPLES
