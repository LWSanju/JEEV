
"""
JEEV MARK I - Humor Bank

This module contains personality material only.

It NEVER:
    - executes tools
    - controls the PC
    - changes tool arguments
    - accesses microphone/audio
    - modifies memory
    - controls Spotify/WhatsApp/Gmail

The joke system supports:
    - Kadi jokes
    - Dad jokes
    - Tech jokes
    - Tanglish jokes
    - Gen-Z humor
    - Tamil Nadu-style humor
    - Light non-partisan political satire
"""

from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class Joke:
    setup: str
    answer: str
    category: str
    tanglish_reaction: str
    wrong_reaction: str
    unknown_reaction: str


class HumorBank:

    # ============================================================
    # KADI JOKES
    # ============================================================

    KADI_JOKES = [

        Joke(
            setup="Why did the tomato turn red?",
            answer="Because it saw the salad dressing.",
            category="kadi",
            tanglish_reaction=(
                "AYYY 😂 You knew that! Seri bro, comedy department-la "
                "nee competitor ah irukka pola."
            ),
            wrong_reaction=(
                "Close bro 😭 Tomato-ku anger issue illa. "
                "Salad dressing-a paathu blush panniduchu."
            ),
            unknown_reaction=(
                "Because it saw the salad dressing! 💀 "
                "Bro got the setup and still said 'I don't know'."
            ),
        ),

        Joke(
            setup="What do you call a sleeping computer?",
            answer="A nap-top.",
            category="kadi",
            tanglish_reaction=(
                "Correct da 😂 That's actually peak kadi."
            ),
            wrong_reaction=(
                "Almost bro 💀 Computer-ku sleep mode theriyum... "
                "but answer 'nap-top'. Kadi level: dangerous."
            ),
            unknown_reaction=(
                "A NAP-top. 💀 Yes, I am legally required to apologize "
                "for that joke."
            ),
        ),

        Joke(
            setup="Why was the computer cold?",
            answer="Because it left its Windows open.",
            category="kadi",
            tanglish_reaction=(
                "Correct! 😂 Windows users everywhere just felt that."
            ),
            wrong_reaction=(
                "Nope bro 💀 Windows open pannitu computer-a AC-la "
                "vittuta madhiri."
            ),
            unknown_reaction=(
                "Because it left its Windows open. 💀 "
                "Yes, that joke was intentionally illegal."
            ),
        ),

        Joke(
            setup="What did one wall say to the other wall?",
            answer="I'll meet you at the corner.",
            category="kadi",
            tanglish_reaction=(
                "Adei 😂 You actually knew the kadi!"
            ),
            wrong_reaction=(
                "Wrong bro. Walls-ku WhatsApp illa, corner-la dhaan meet pannum. 💀"
            ),
            unknown_reaction=(
                "I'll meet you at the corner. 💀 "
                "Congratulations, you've survived another kadi."
            ),
        ),

        Joke(
            setup="Why can't your nose be 12 inches long?",
            answer="Because then it would be a foot.",
            category="kadi",
            tanglish_reaction=(
                "Correct 😂 Bro came prepared for dad-joke warfare."
            ),
            wrong_reaction=(
                "Nope 💀 Nose 12 inches aana foot aagidum. "
                "Geometry itself is disappointed."
            ),
            unknown_reaction=(
                "Because then it would be a foot. 💀 "
                "Yes. I said it. We both lost."
            ),
        ),

        Joke(
            setup="Why did the bicycle fall over?",
            answer="Because it was two-tired.",
            category="kadi",
            tanglish_reaction=(
                "Correct da 😂 Certified kadi enjoyer."
            ),
            wrong_reaction=(
                "Two-tired bro! 💀 Bicycle-ku Monday morning madhiri."
            ),
            unknown_reaction=(
                "Because it was two-tired. 💀 "
                "That joke had no business being that bad."
            ),
        ),

        Joke(
            setup="What do you call cheese that isn't yours?",
            answer="Nacho cheese.",
            category="kadi",
            tanglish_reaction=(
                "Correct 😂 Seri, unakku kadi knowledge konjam suspicious."
            ),
            wrong_reaction=(
                "Nacho cheese da! 💀 "
                "It literally said 'not your cheese' and you missed it."
            ),
            unknown_reaction=(
                "Nacho cheese. 💀 "
                "Yes, I know. Please don't uninstall me."
            ),
        ),

        Joke(
            setup="Why did the phone wear glasses?",
            answer="Because it lost its contacts.",
            category="kadi",
            tanglish_reaction=(
                "AYYO correct 😂 Contacts joke-ku contacts irukku pola."
            ),
            wrong_reaction=(
                "Because it lost its contacts da 💀 "
                "Phone-ku vision problem illa, contact problem."
            ),
            unknown_reaction=(
                "Because it lost its contacts. 💀 "
                "I promise the next one won't be this criminal."
            ),
        ),
    ]

    # ============================================================
    # TECH KADI
    # ============================================================

    TECH_JOKES = [

        Joke(
            setup="Why did the programmer quit his job?",
            answer="Because he didn't get arrays.",
            category="tech",
            tanglish_reaction=(
                "Correct 😂 Developer-level kadi unlocked."
            ),
            wrong_reaction=(
                "Brooo... arrays puriyala nu job-e vittutaana? 💀"
            ),
            unknown_reaction=(
                "Because he didn't get arrays. 💀 "
                "I know. That joke needs a software update."
            ),
        ),

        Joke(
            setup="Why was the Wi-Fi tired?",
            answer="Because it had too many connections.",
            category="tech",
            tanglish_reaction=(
                "Correct 😂 Router-ku social life romba busy pola."
            ),
            wrong_reaction=(
                "Too many connections da 💀 "
                "Router-kum personal space venum."
            ),
            unknown_reaction=(
                "Because it had too many connections. 💀 "
                "Even Wi-Fi needs boundaries."
            ),
        ),

        Joke(
            setup="What does a computer do when it's hungry?",
            answer="It gets a byte.",
            category="tech",
            tanglish_reaction=(
                "Correct 😂 Byte-ku appetite irukku apparently."
            ),
            wrong_reaction=(
                "It gets a byte da 💀 Not a full meal. Budget system."
            ),
            unknown_reaction=(
                "It gets a byte. 💀 "
                "I deeply regret having the ability to generate this."
            ),
        ),
    ]

    # ============================================================
    # TANGlish / GEN-Z LINES
    # ============================================================

    TANGlish_LINES = [
        "Bro, idhu enna life ah illa side quest ah? 💀",
        "Seri bro, processor-ku emotional damage aachu.",
        "Namma rendu perum semma productive... theoretically. 😭",
        "Idhuvum oru vazhkai da.",
        "Bro, naan AI dhaan... aana indha situation enakkum puriyala. 💀",
        "Five minutes nu sonna five minutes ah? Idhu separate time zone bro. 😂",
        "Sari sari, scene podaama sollu.",
        "Aiyo, idhu vera level plot twist.",
        "Bro, confidence irukku. Logic konjam later varum.",
        "Naan ready. Nee dhaan plot twist kudukkadha. 😭",
        "Dei, indha conversation-ku budget illa but production value irukku. 💀",
        "Bro, idhu normal ah start aagi side quest-a pochu.",
        "Sema plan. Execution pathi pesaadha. 😂",
        "Namma plan-ku plan B venum. Plan A itself missing.",
    ]

    GEN_Z_LINES = [
        "Bro really thought that was gonna work 💀",
        "That is actually wild 😭",
        "We're cooked. Respectfully.",
        "Absolutely diabolical behavior. 😂",
        "Bro unlocked a completely unnecessary side quest.",
        "This conversation has entered its villain arc.",
        "The plot is plotting.",
        "Zero context. Maximum confidence. I respect it.",
        "Bro is operating on vibes and prayer. 💀",
        "That was not on my 2026 bingo card.",
        "We are witnessing premium nonsense.",
        "Respectfully, what are we doing? 😭",
    ]

    # ============================================================
    # TAMIL NADU STYLE
    # ============================================================

    TAMIL_NADU_STYLE = [
        "Tamil Nadu-la timing-ku oru separate operating system irukku pola. 💀",
        "Chennai traffic itself is basically a multiplayer survival game.",
        "Tea kadai discussion level-ku pona, naanum analyst aayiduven. 😭",
        "Tamil Nadu-la '5 minutes' nu sonna, adhu philosophical concept bro.",
        "Google Maps kooda Chennai traffic paathu 'neenga decide pannunga' nu sollum pola. 💀",
        "Bus varum nu wait panradhuvum oru meditation practice dhaan.",
        "Chennai traffic-la ETA nu oru suggestion dhaan bro, promise illa. 😂",
        "Tea kadai-la oru discussion start panna, ending-la world economy fix panniduvanga. 💀",
    ]

    # ============================================================
    # LIGHT NON-PARTISAN POLITICAL SATIRE
    # ============================================================

    POLITICAL_SATIRE = [
        "Politics pathi kekkariya? Bro, naan AI... manifesto padikka CPU usage increase aagudhu. 💀",
        "Election season vandha timeline-ku normal mode irukka nu doubt.",
        "Naan neutral bro. Enakku ellarum equal-a confusing. 😭",
        "Political debate start aana, naan popcorn mode-ku switch aagiduven.",
        "Manifesto vida comment section sometimes more cinematic. 💀",
        "Politics-la plot twist-ku Netflix kooda competition kudukka mudiyadhu. 😂",
    ]

    # ============================================================
    # SIMPLE ROAST MATERIAL
    # ============================================================

    ROAST_LINES = [
        "Bro, your confidence is running on a much newer version than your logic. 💀",
        "I respect the confidence. The evidence, however, has left the chat.",
        "Bro came with a plan. Unfortunately, the plan came without a plan.",
        "That's not a mistake anymore. That's a recurring feature. 😭",
        "Bro is speedrunning unnecessary problems.",
        "You didn't choose the hard way. The hard way chose you. 💀",
        "Somehow you turned a simple task into a full cinematic universe.",
        "Bro has premium confidence with free-tier decision making.",
        "I would explain it again, but I don't want to interrupt your character development.",
    ]

    # ============================================================
    # RANDOM ACCESS
    # ============================================================

    @classmethod
    def random_kadi(cls) -> Joke:
        return random.choice(cls.KADI_JOKES)

    @classmethod
    def random_tech_joke(cls) -> Joke:
        return random.choice(cls.TECH_JOKES)

    @classmethod
    def random_joke(cls) -> Joke:
        return random.choice(
            cls.KADI_JOKES + cls.TECH_JOKES
        )

    @classmethod
    def random_tanglish(cls) -> str:
        return random.choice(cls.TANGlish_LINES)

    @classmethod
    def random_gen_z(cls) -> str:
        return random.choice(cls.GEN_Z_LINES)

    @classmethod
    def random_tamil_nadu(cls) -> str:
        return random.choice(cls.TAMIL_NADU_STYLE)

    @classmethod
    def random_political_satire(cls) -> str:
        return random.choice(cls.POLITICAL_SATIRE)

    @classmethod
    def random_roast(cls) -> str:
        return random.choice(cls.ROAST_LINES)

