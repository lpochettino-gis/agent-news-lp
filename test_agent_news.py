import datetime as dt
import unittest
from unittest.mock import MagicMock, patch
import agent_news as news


class NewsCoverageTests(unittest.TestCase):
    def setUp(self):
        self.profile = news.build_interest_profile()

    def article(self, category, title, age=1, source="Diario Democracia", score=1):
        return news.Article(category, "consulta", title, "https://example.com/nota", source,
                            title, news.now_local() - dt.timedelta(hours=age), score=score)

    def test_geographic_evidence_and_homonyms(self):
        for category, title, source, expected in [
            ("Pasteur", "Pasteur: mejoras en la unidad sanitaria", "Diario Democracia", True),
            ("Lincoln", "Lincoln bonaerense: nuevas obras", "Otro medio", True),
            ("General Villegas", "General Villegas repara caminos", "Otro medio", True),
            ("Pehuajó", "Pehuajó recibe nuevas ambulancias", "Otro medio", True),
            ("Pasteur", "El legado científico de Louis Pasteur", "Internacional", False),
            ("Lincoln", "Lincoln presenta su nueva camioneta", "Motor", False),
            ("Región cercana", "América y las elecciones de Estados Unidos", "Internacional", False),
            ("Región cercana", "Comienza la FIT América Latina en Buenos Aires", "Turismo", False),
            ("Región cercana", "Obras en avenida Rivadavia de Buenos Aires", "Nacional", False),
            ("Región cercana", "La ciudad de América mejora caminos", "Otro medio", True),
            ("Región cercana", "Obras en Mar del Plata", "Diario Democracia", False),
            ("Región cercana", "Rufino mejora el acceso rural", "Otro medio", True),
        ]:
            with self.subTest(title=title):
                self.assertEqual(news.local_article_matches(self.article(category, title, source=source)), expected)

    def test_query_or_source_alone_do_not_prove_location(self):
        article = self.article("Pasteur", "Obras en una escuela", source="Pasteur")
        article.query = "Pasteur Lincoln Buenos Aires"
        self.assertFalse(news.local_article_matches(article))

    def test_local_age_window_and_missing_dates(self):
        self.assertTrue(news.article_in_scope(self.article("Pehuajó", "Pehuajó obras", age=48)))
        self.assertFalse(news.article_in_scope(self.article("Pehuajó", "Pehuajó obras", age=73)))
        self.assertFalse(news.article_in_scope(self.article("Agricultura y mercados", "Cosecha de soja", age=25)))
        article = self.article("Pehuajó", "Pehuajó obras")
        article.published = None
        self.assertFalse(news.article_in_scope(article))

    def test_local_queries_use_three_days_only(self):
        with patch.object(news, "read_url", return_value=b"<rss><channel/></rss>") as fetch:
            news.fetch_feed("Pasteur", "Pasteur")
            self.assertIn("when%3A3d", fetch.call_args.args[0].full_url)
            news.fetch_feed("Agricultura y mercados", "agro")
            self.assertIn("when%3A1d", fetch.call_args.args[0].full_url)

    def test_agro_relevance_and_livestock_category(self):
        self.assertTrue(news.article_in_scope(self.article("Ganadería y lechería", "La producción de leche en Córdoba creció")))
        self.assertFalse(news.article_in_scope(self.article("Ganadería y lechería", "Récord agroindustrial de exportaciones de Argentina")))
        self.assertFalse(news.article_in_scope(self.article("Agricultura y mercados", "Centroamérica apuesta por semillas resistentes")))
        self.assertTrue(news.article_in_scope(self.article("Agricultura y mercados", "Argentina inicia la siembra de maíz")))

    def test_priority_towns_survive_many_high_scoring_regional_articles(self):
        articles = [self.article("Región cercana", f"Rufino obra {i}", score=100-i) for i in range(15)]
        articles += [self.article(town, f"{town}: nuevo centro de salud") for town in news.LOCAL_CATEGORIES[:4]]
        selected = news.choose_articles(articles, self.profile)
        self.assertEqual(len(selected), 8)
        self.assertTrue(set(news.LOCAL_CATEGORIES[:4]) <= {a.category for a in selected})

    def test_new_groups_are_in_briefing_and_radio_even_with_low_scores(self):
        articles = []
        for idx, group in enumerate(news.profile_topic_groups(self.profile)):
            for number in range(8):
                articles.append(self.article(group["categories"][0], f"{group['name']} titular {number}", score=100-idx*10))
        briefing = news.build_briefing(articles, self.profile, {})
        for group in (news.AGRO_GROUP, news.LOCAL_GROUP):
            self.assertIn(group, {item['group'] for item in briefing['fast_read']})
            self.assertIn(group, {item['group'] for item in briefing['radar']})
        radio = news.build_radio_briefing(articles, self.profile, {}, briefing)
        self.assertIn("En Agro.", radio)
        self.assertIn(f"En {news.LOCAL_GROUP}.", radio)
        self.assertIn("Publicada el", radio)

    def test_missing_news_not_counted_or_narrated_as_fact(self):
        articles = news.complete_article_targets([], self.profile)
        self.assertEqual(len(articles), 56)
        self.assertFalse(any(news.is_real_article(a) for a in articles))
        briefing = news.build_briefing(articles, self.profile, {})
        self.assertEqual(briefing['fast_read'], [])
        radio = news.build_radio_briefing(articles, self.profile, {}, briefing)
        self.assertIn("no se obtuvieron noticias verificables", radio)
        page = news.render_html(articles, self.profile, [], {}, briefing)
        self.assertIn("0 noticias · 8 espacios pendientes", page)
        self.assertIn("250 km", page)

    def test_existing_profile_migrates(self):
        path = MagicMock()
        path.exists.return_value = True
        path.read_text.return_value = '{"profile_version": 4}'
        with patch.object(news, "PROFILE_PATH", path), patch.object(news, "ensure_dirs"):
            migrated = news.load_or_create_profile()
        self.assertEqual(migrated['profile_version'], 5)
        self.assertEqual(news.target_total(migrated), 56)
        self.assertEqual(len(migrated['themes']), 18)
        self.assertIn('local_coverage', migrated)
        path.write_text.assert_called_once()


if __name__ == '__main__':
    unittest.main()
