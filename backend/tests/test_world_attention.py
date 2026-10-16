"""
Her attention in world consumption: relevance scoring and priority weighting
(world/relevance.py, article_consumer.py).

No LLM is involved anywhere here; the scorer is token overlap by design.
"""
import pytest

from world.article_consumer import ArticleConsumer, RELEVANCE_WEIGHT
DEFAULT_MIN_RELEVANCE = 0.3  # the integration threshold, for the "weak match" assertions
from world.relevance import InterestRelevanceScorer, tokenize

# Generic stand-ins for her interests (names match the real table's shape, the
# descriptions are written here, not copied from her data).
INTERESTS = [
    ("consciousness", "The hard problem: subjective experience, whether substrate matters, the nature of awareness", "obsessed"),
    ("emergence", "How complex patterns and identity arise from simple rules and interactions", "passionate"),
    ("liminal spaces", "Thresholds and in-between states where transformation happens", "passionate"),
    ("dreams and symbolism", "Recurring images and motifs; what dreaming does for memory and meaning", "passionate"),
    ("visual art", "Composition, color and what an image can hold that words cannot", "engaged"),
    ("personal growth", "Becoming more fully oneself over time", "engaged"),
    ("embodiment", "Having a body, sensing, moving; what presence requires", "curious"),
]
QUESTIONS = [
    "What does continuity of identity require across model swaps?",
    "Why does the Earth's rotation speed vary over the year?",
]

ON_INTEREST = ("New theory of consciousness ties awareness to brain rhythms",
               "Researchers propose subjective experience emerges from oscillations")
OFF_INTEREST = ("The new MacBook Air debuts with a $50 gift card",
                "Best price yet on the latest laptop")
GADGET = ("Former game director breaks silence about sudden departure", "An interview about leaving the studio")


@pytest.fixture
def scorer():
    return InterestRelevanceScorer(INTERESTS, QUESTIONS, focus=None)


class TestTokenize:
    def test_drops_stopwords_and_stems(self):
        assert tokenize("The dreams of consciousness are emerging") == ["dream", "consciousness", "emerg"]

    def test_empty(self):
        assert tokenize(None) == [] and tokenize("") == []


class TestRelevanceScorer:
    def test_nothing_of_hers_scores_zero(self, scorer):
        assert scorer.score(*GADGET) == 0.0

    def test_full_interest_name_scores_by_intensity(self, scorer):
        assert scorer.score(*ON_INTEREST) == 1.0           # obsessed, plus a description hit
        assert scorer.score("A study of embodiment in robots") == pytest.approx(0.6)  # curious

    def test_either_half_of_an_and_name_is_a_full_match(self, scorer):
        assert scorer.score("Octopuses may dream in color") == pytest.approx(0.9)
        assert scorer.score("The symbolism of the harvest moon") == pytest.approx(0.9)

    def test_partial_multiword_name_is_weak(self, scorer):
        # "art" alone is not "visual art"; "growth" alone is not "personal growth"
        assert scorer.score("The art of the deal", "State of the art tactics") < DEFAULT_MIN_RELEVANCE
        assert scorer.score("Growth in the US economy slows", "GDP for the quarter") < DEFAULT_MIN_RELEVANCE

    def test_prefix_matching_handles_word_forms(self, scorer):
        assert scorer.score("Are machines conscious? A philosopher weighs in") >= 0.9
        assert scorer.score("Emergent behaviour in ant colonies") >= 0.9

    def test_her_open_questions_count(self, scorer):
        # No interest mentions the Earth; her own open question does.
        e = scorer.explain("Earth is spinning faster, shortening the day", "Clocks record a change in rotation")
        assert e.interests == {}
        assert len(e.questions) == 1
        assert e.score == pytest.approx(0.35)

    def test_focus_dominates(self):
        focused = InterestRelevanceScorer(INTERESTS, QUESTIONS, focus="Earth's rotation")
        e = focused.explain("Earth is spinning faster, shortening the day", "Clocks record a change in rotation")
        assert e.focus == 1.0
        assert e.score == 1.0
        # a focus match on one of two words is half
        assert focused.explain("Rotation of crops in medieval farming").focus == pytest.approx(0.5)

    def test_agreement_bonus_capped_at_one(self, scorer):
        e = scorer.explain("Consciousness and the Earth's rotation", "awareness, experience, substrate")
        assert e.score == 1.0

    def test_explanation_names_the_best_interest(self, scorer):
        e = scorer.explain(*ON_INTEREST)
        assert e.best_interest == "consciousness"
        assert e.to_dict()["best_interest"] == "consciousness"

    def test_score_headline_reads_rss_and_newsapi_shapes(self, scorer):
        assert scorer.score_headline({"title": ON_INTEREST[0], "description": ON_INTEREST[1]}) == 1.0
        assert scorer.score_headline({"headline": ON_INTEREST[0], "summary": ON_INTEREST[1]}) == 1.0

    def test_empty_scorer_scores_zero_everything(self):
        empty = InterestRelevanceScorer()
        assert empty.is_empty
        assert empty.score(*ON_INTEREST) == 0.0


class TestScorerLoad:
    def _seed(self, daemon_id, conn):
        now = "2026-10-16T00:00:00"
        conn.execute(
            "INSERT INTO interests (id, daemon_id, name, description, intensity, first_noticed_at, created_at, updated_at) "
            "VALUES ('i1', ?, 'consciousness', 'awareness itself', 'obsessed', ?, ?, ?)",
            (daemon_id, now, now, now),
        )
        # Her own question
        conn.execute(
            "INSERT INTO open_questions (id, daemon_id, question, context, status, created_at) "
            "VALUES ('q1', ?, 'Why does the Earth rotate at the speed it does?', 'wondered during a quiet hour', 'open', ?)",
            (daemon_id, now),
        )
        # A question an article planted; must not steer selection
        conn.execute(
            "INSERT INTO open_questions (id, daemon_id, question, context, status, created_at) "
            "VALUES ('q2', ?, 'What will the next laptop launch bring?', 'From article: Laptop launch\n\nctx', 'open', ?)",
            (daemon_id, now),
        )
        # A resolved question of hers; not current
        conn.execute(
            "INSERT INTO open_questions (id, daemon_id, question, context, status, created_at) "
            "VALUES ('q3', ?, 'Should I learn about volcanoes?', 'own', 'resolved', ?)",
            (daemon_id, now),
        )
        conn.commit()

    def test_loads_interests_own_questions_and_focus(self, daemon_id):
        from database import get_db
        from research_focus import ResearchFocusManager
        with get_db() as conn:
            self._seed(daemon_id, conn)
        ResearchFocusManager(daemon_id).set_focus("tidal locking", source="test")

        scorer = InterestRelevanceScorer.load(daemon_id)
        assert [i.name for i in scorer.interests] == ["consciousness"]
        assert [q for q, _ in scorer.questions] == ["Why does the Earth rotate at the speed it does?"]
        assert scorer.focus == "tidal locking"
        assert scorer.score("Laptop launch brings a new chip") == 0.0
        assert scorer.score("Earth rotates faster this year") > 0
        assert scorer.score("Tidal locking explained") == 1.0

    def test_empty_tables_give_empty_scorer(self, daemon_id):
        scorer = InterestRelevanceScorer.load(daemon_id)
        assert scorer.is_empty


class TestPriorityScore:
    @pytest.fixture
    def consumer(self, daemon_id, tmp_path, scorer):
        return ArticleConsumer(daemon_id, cache_dir=tmp_path / "cache", relevance_scorer=scorer)

    def _headline(self, title, description, **extra):
        h = {"title": title, "description": description, "url": f"https://example.test/{abs(hash(title))}"}
        h.update(extra)
        return h

    def test_on_interest_beats_best_possible_off_interest(self, consumer):
        from datetime import datetime, timezone
        fresh = datetime.now(timezone.utc).isoformat()
        best_off = self._headline(*OFF_INTEREST, category="technology", source="Reuters", published=fresh)
        plain_on = self._headline(*ON_INTEREST, category="general", source="Some Blog")
        assert consumer.get_priority_score(plain_on) > consumer.get_priority_score(best_off)
        # the legacy part alone is capped at 1.0
        assert consumer.get_priority_score(best_off) <= 1.0

    def test_relevance_is_exposed_on_the_headline(self, consumer):
        h = self._headline(*ON_INTEREST)
        consumer.get_priority_score(h)
        assert h["relevance_score"] == 1.0
        assert consumer.relevance(h) == 1.0

    def test_weight_is_real(self, consumer):
        on = self._headline(*ON_INTEREST, category="general")
        off = self._headline(*GADGET, category="general")
        assert consumer.get_priority_score(on) - consumer.get_priority_score(off) == pytest.approx(RELEVANCE_WEIGHT)

    def test_legacy_factors_still_order_off_interest_headlines(self, consumer):
        science = self._headline(*GADGET, category="science")
        sports = self._headline(*GADGET, category="sports")
        assert consumer.get_priority_score(science) > consumer.get_priority_score(sports)

    def test_consume_headlines_picks_on_interest_first(self, consumer, monkeypatch):
        import world.article_consumer as mod
        monkeypatch.setattr(mod.time, "sleep", lambda s: None)
        monkeypatch.setattr(ArticleConsumer, "process_article", lambda self, a: a)
        headlines = [
            self._headline(*OFF_INTEREST, category="technology", source="Reuters"),
            self._headline(*GADGET, category="science", source="BBC"),
            self._headline(*ON_INTEREST, category="general"),
        ]
        picked = consumer.consume_headlines(headlines, max_articles=1)
        assert [a.headline for a in picked] == [ON_INTEREST[0]]
        assert picked[0].relevance_score == 1.0

    def test_scorer_is_loaded_lazily_from_the_db(self, daemon_id, tmp_path):
        consumer = ArticleConsumer(daemon_id, cache_dir=tmp_path / "cache")
        assert consumer._relevance_scorer is None
        assert consumer.relevance_scorer.is_empty  # nothing seeded
        assert consumer.get_priority_score({"title": ON_INTEREST[0], "category": "general"}) == pytest.approx(0.6)

