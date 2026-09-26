"""Publisher photos for Agent News. Standard library; Pillow optimizes when installed."""
import base64
import concurrent.futures
import hashlib
import html
from html.parser import HTMLParser
import io
import ipaddress
import json
from pathlib import Path
import re
import socket
import time
import unicodedata
import urllib.parse as urls
import urllib.request as http

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/129.0 Safari/537.36"
MAX_BYTES = 6 * 1024 * 1024


def public_url(url):
    parsed = urls.urlsplit(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Invalid public URL")
    for entry in socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == 'https' else 80)):
        if not ipaddress.ip_address(entry[4][0]).is_global:
            raise ValueError("Non-public address")
    return url


class PublicRedirect(http.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        public_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(url, data=None):
    public_url(url)
    headers = {"User-Agent": USER_AGENT}
    if data is not None:
        headers['Content-Type'] = 'application/x-www-form-urlencoded;charset=UTF-8'
    opener = http.build_opener(PublicRedirect())
    with opener.open(http.Request(url, data=data, headers=headers), timeout=7) as response:
        body = response.read(MAX_BYTES + 1)
        if len(body) > MAX_BYTES:
            raise ValueError("Response too large")
        return body, response.geturl(), response.headers.get_content_type()


class Metadata(HTMLParser):
    def __init__(self, document):
        super().__init__(convert_charrefs=True)
        self.meta = {}
        self.signature = self.timestamp = ''
        self.feed(document)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'meta':
            key = (attrs.get('property') or attrs.get('name') or '').lower()
            self.meta.setdefault(key, attrs.get('content') or '')
        if attrs.get('data-n-a-sg'):
            self.signature = attrs['data-n-a-sg']
            self.timestamp = attrs.get('data-n-a-ts', '')


def publisher_url(link):
    if urls.urlsplit(link).hostname != 'news.google.com':
        return link
    token = urls.urlsplit(link).path.rsplit('/', 1)[-1]
    # Older RSS redirects contain the destination URL directly.
    decoded = base64.urlsafe_b64decode(token + '=' * (-len(token) % 4))
    legacy = re.search(rb'https?://[^\x00-\x20\x7f-\xff]+', decoded)
    if legacy:
        return legacy.group().decode('utf-8')
    body, final_url, _ = fetch(link)
    if urls.urlsplit(final_url).hostname != 'news.google.com':
        return final_url
    metadata = Metadata(body.decode('utf-8', 'replace'))
    if not metadata.signature or not metadata.timestamp:
        raise ValueError("Publisher redirect unavailable")
    # Google RSS redirect protocol; reference: SSujitX/google-news-url-decoder.
    context = [["X", "X", ["X", "X"], None, None, 1, 1, "US:en", None, 1,
                None, None, None, None, None, 0, 1], "X", "X", 1, [1, 1, 1], 1, 1, None, 0, 0, None, 0]
    request = ["garturlreq", context, token, int(metadata.timestamp), metadata.signature]
    payload = urls.urlencode({'f.req': json.dumps([[["Fbv4je", json.dumps(request), None, "generic"]]])}).encode()
    response, _, _ = fetch('https://news.google.com/_/DotsSplashUi/data/batchexecute', payload)
    for line in response.decode('utf-8').splitlines():
        if not line.startswith('['):
            continue
        for row in json.loads(line):
            if isinstance(row, list) and len(row) > 2 and row[1] == 'Fbv4je' and row[2]:
                result = json.loads(row[2])
                if result[0] == 'garturlres':
                    return result[1]
    raise ValueError("Publisher redirect missing")


def title_matches(expected, actual):
    def tokens(text):
        text = ''.join(c for c in unicodedata.normalize('NFD', text.lower()) if unicodedata.category(c) != 'Mn')
        return set(re.findall(r'\w{3,}', html.unescape(text)))
    left, right = tokens(expected), tokens(actual)
    return len(left & right) / max(1, len(left)) >= 0.75


def image_metadata(document, page_url, title):
    meta = Metadata(document).meta
    if not title_matches(title, meta.get('og:title') or meta.get('twitter:title', '')):
        return '', ''
    image = meta.get('og:image:secure_url') or meta.get('og:image') or meta.get('twitter:image', '')
    if not image or re.search(r'(?:logo|favicon|placeholder|default[-_]image)', image, re.I):
        return '', ''
    image = urls.urljoin(page_url, image)
    if urls.urlsplit(image).scheme not in ('https', 'http'):
        return '', ''
    return image, meta.get('og:description') or meta.get('description', '')


def save_image(url, output_dir):
    body, _, content_type = fetch(url)
    if not content_type.startswith('image/'):
        raise ValueError('Not an image')
    suffix = ''
    if body.startswith(b'\xff\xd8\xff'): suffix = '.jpg'
    elif body.startswith(b'\x89PNG\r\n\x1a\n'): suffix = '.png'
    elif body.startswith((b'GIF87a', b'GIF89a')): suffix = '.gif'
    elif body.startswith(b'RIFF') and body[8:12] == b'WEBP': suffix = '.webp'
    if not suffix:
        raise ValueError('Unsupported image')
    try:
        from PIL import Image, ImageOps
    except ImportError:
        pass
    else:
        with Image.open(io.BytesIO(body)) as original:
            if original.width < 240 or original.height < 120:
                raise ValueError('Thumbnail too small')
            picture = ImageOps.exif_transpose(original).convert('RGB')
            picture.thumbnail((800, 500))
            stream = io.BytesIO()
            picture.save(stream, format='JPEG', quality=82, optimize=True)
            body, suffix = stream.getvalue(), '.jpg'
    filename = hashlib.sha256(url.encode()).hexdigest()[:24] + suffix
    (output_dir / 'images' / filename).write_bytes(body)
    return 'images/' + filename


def enrich_images(articles, output_dir):
    output_dir = Path(output_dir)
    (output_dir / 'images').mkdir(parents=True, exist_ok=True)
    cache_path = output_dir / 'image_cache.json'
    try:
        cache = json.loads(cache_path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        cache = {}
    def enrich(article):
        cached = cache.get(article.link, {})
        image = cached.get('image', '')
        if cached.get('time', 0) > time.time() - 7 * 86400 and re.fullmatch(r'images/[a-f0-9]{24}\.(jpg|png|gif|webp)', image) and (output_dir / image).exists():
            return article, cached, ''
        page_url = publisher_url(article.link)
        body, page_url, content_type = fetch(page_url)
        if content_type not in ('text/html', 'application/xhtml+xml'):
            raise ValueError('Not an article page')
        image_url, description = image_metadata(body.decode('utf-8', 'replace'), page_url, article.title)
        image_url = image_url or article.image_url
        if not image_url:
            raise ValueError('No matching article photo')
        path = save_image(image_url, output_dir)
        return article, {'image': path, 'page': page_url, 'original': image_url,
                         'description': description, 'time': time.time()}, ''
    failures = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        jobs = {pool.submit(enrich, article): article for article in articles if article.link and article.source != 'Demo local'}
        for future in concurrent.futures.as_completed(jobs):
            article = jobs[future]
            try:
                article, entry, _ = future.result()
                cache[article.link] = entry
                article.image_url = entry['image']
                article.link = entry['page']
                if entry.get('description'):
                    article.description = entry['description']
            except Exception as exc:
                article.image_url = ''
                failures.append(f'{article.source}: {type(exc).__name__}: {exc}')
    cache = dict(sorted(cache.items(), key=lambda item: item[1].get('time', 0), reverse=True)[:400])
    cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding='utf-8')
    return failures
