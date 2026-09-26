import unittest
from unittest.mock import patch
import agent_news as news
from news_images import image_metadata, title_matches, public_url


class VisualNewsTests(unittest.TestCase):
    def test_matching_article_photo_and_relative_url(self):
        document = '<meta content="Pehuajó inaugura una sala de salud" property="og:title"><meta property="og:image" content="/fotos/sala.jpg"><meta property="og:description" content="El hospital amplía su atención.">'
        image, description = image_metadata(document, 'https://example.com/noticia', 'Pehuajó inaugura una sala de salud')
        self.assertEqual(image, 'https://example.com/fotos/sala.jpg')
        self.assertIn('hospital', description)

    def test_unrelated_page_logo_and_unsafe_image_are_rejected(self):
        for title, image in [('Inicio del diario', '/foto.jpg'), ('Pehuajó inaugura una sala', '/logo.jpg'), ('Pehuajó inaugura una sala', 'javascript:alert(1)')]:
            document = f'<meta property="og:title" content="{title}"><meta property="og:image" content="{image}">'
            self.assertEqual(image_metadata(document, 'https://example.com/nota', 'Pehuajó inaugura una sala'), ('', ''))

    def test_private_and_non_http_urls_are_rejected(self):
        for url in ('file:///C:/secret', 'javascript:alert(1)', 'https://user:pass@example.com'):
            with self.assertRaises(ValueError): public_url(url)
        with patch('news_images.socket.getaddrinfo', return_value=[(None, None, None, None, ('127.0.0.1', 80))]):
            with self.assertRaises(ValueError): public_url('http://localhost/secret')

    def test_photos_render_without_audio_or_briefing(self):
        article = news.Article('Argentina', '', 'Obras y salud', 'https://example.com/nota', 'Medio local', 'Nueva sala.', news.now_local(), image_url='images/' + 'a'*24 + '.jpg')
        page = news.render_html([article], news.build_interest_profile(), [])
        for forbidden in ('<audio', 'speechSynthesis', 'Agent News Radio', 'Briefing ejecutivo', 'Lectura rapida', 'radio-script-data'):
            self.assertNotIn(forbidden, page)
        self.assertIn('<figure class="news-photo">', page)
        self.assertIn('height: 220px', page)
        self.assertIn('Imagen de Medio local', page)
        article.image_url = ''
        self.assertNotIn('<figure class="news-photo">', news.render_html([article], news.build_interest_profile(), []))

    def test_default_run_never_generates_audio(self):
        with patch.object(news, 'ensure_dirs'), patch.object(news, 'load_or_create_profile', return_value=news.build_interest_profile()), patch.object(news, 'write_report', return_value='preview.html'), patch.object(news, 'log'), patch.object(news, 'write_radio_outputs') as audio, patch.object(news, 'build_briefing') as briefing, patch.object(news, 'enrich_images') as images:
            self.assertEqual(news.run(news.parse_args(['--offline-demo', '--no-open'])), 0)
            audio.assert_not_called()
            briefing.assert_not_called()
            images.assert_not_called()


if __name__ == '__main__':
    unittest.main()
