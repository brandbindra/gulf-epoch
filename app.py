import os, json, requests
from flask import Flask, render_template, request, jsonify
from xml.etree import ElementTree as ET

app = Flask(__name__)

API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')

# ── RSS FEEDS ──────────────────────────────────────────────────────────
FEEDS = {
    'mideast-uae': [
        {'name': 'Al Jazeera',   'url': 'https://www.aljazeera.com/xml/rss/all.xml'},
        {'name': 'BBC ME',       'url': 'https://feeds.bbci.co.uk/news/world/middle_east/rss.xml'},
        {'name': 'Reuters',      'url': 'https://feeds.reuters.com/reuters/worldNews'},
    ],
    'uae': [
        {'name': 'Khaleej Times','url': 'https://www.khaleejtimes.com/rss'},
        {'name': 'Gulf News',    'url': 'https://gulfnews.com/rss'},
        {'name': 'The National', 'url': 'https://www.thenationalnews.com/rss'},
    ],
    'subcontinent': [
        {'name': 'NDTV',         'url': 'https://feeds.feedburner.com/ndtvnews-top-stories'},
        {'name': 'Times of India','url': 'https://timesofindia.indiatimes.com/rssfeedstopstories.cms'},
        {'name': 'India Today',  'url': 'https://www.indiatoday.in/rss/1206514'},
    ],
    'world': [
        {'name': 'NYT',          'url': 'https://rss.nytimes.com/services/xml/rss/nyt/World.xml'},
        {'name': 'Reuters',      'url': 'https://feeds.reuters.com/reuters/topNews'},
        {'name': 'Guardian',     'url': 'https://www.theguardian.com/world/rss'},
    ],
    'tech': [
        {'name': 'TechCrunch',   'url': 'https://techcrunch.com/feed/'},
        {'name': 'Wired',        'url': 'https://www.wired.com/feed/rss'},
        {'name': 'MIT Tech',     'url': 'https://www.technologyreview.com/feed/'},
    ],
    'sports': [
        {'name': 'ESPNcricinfo', 'url': 'https://www.espncricinfo.com/rss/content/story/feeds/0.xml'},
        {'name': 'BBC Sport',    'url': 'https://feeds.bbci.co.uk/sport/rss.xml'},
        {'name': 'ESPN',         'url': 'https://www.espn.com/espn/rss/news'},
    ],
    'business': [
        {'name': 'Bloomberg',    'url': 'https://feeds.bloomberg.com/markets/news.rss'},
        {'name': 'FT',           'url': 'https://www.ft.com/rss/home/uk'},
        {'name': 'WSJ',          'url': 'https://feeds.a.dj.com/rss/RSSWorldNews.xml'},
    ],
    'life': [
        {'name': 'Time Out Dubai','url': 'https://www.timeoutdubai.com/rss'},
        {'name': 'BBC Life',     'url': 'https://feeds.bbci.co.uk/news/entertainment_and_arts/rss.xml'},
        {'name': 'CNN Travel',   'url': 'http://rss.cnn.com/rss/edition_travel.rss'},
    ],
    'markets': [
        {'name': 'Bloomberg',    'url': 'https://feeds.bloomberg.com/markets/news.rss'},
        {'name': 'CNBC',         'url': 'https://www.cnbc.com/id/100727362/device/rss/rss.html'},
        {'name': 'FT Markets',   'url': 'https://www.ft.com/rss/home/uk'},
    ],
    'entertainment': [
        {'name': 'Variety',      'url': 'https://variety.com/feed/'},
        {'name': 'Pinkvilla',    'url': 'https://www.pinkvilla.com/rss'},
        {'name': 'NDTV Ent',     'url': 'https://feeds.feedburner.com/ndtvnews-top-stories'},
    ],
}

SECTION_LABELS = {
    'mideast-uae':   'Gulf Slate — Middle East & UAE',
    'uae':           'Gulf Slate — UAE',
    'subcontinent':  'Subcontinent Desk',
    'world':         'Global Dispatch',
    'tech':          'Innovation Ledger',
    'sports':        'The Arena',
    'business':      'Commerce & Enterprise',
    'life':          'Culture & Society',
    'markets':       'Bourse & Yield',
    'entertainment': 'The Ritz & Review',
}

def fetch_rss(feed):
    """Fetch and parse RSS feed, return list of items."""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 GulfEpoch/1.0'}
        r = requests.get(feed['url'], headers=headers, timeout=8)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        items = []
        for item in root.iter('item'):
            title = item.findtext('title', '').strip()
            desc  = item.findtext('description', '').strip()
            # Strip HTML tags from description
            import re
            desc = re.sub(r'<[^>]+>', '', desc)[:300]
            if len(title) > 10:
                items.append({
                    'title': title,
                    'description': desc,
                    'source': feed['name'],
                })
            if len(items) >= 6:
                break
        return items
    except Exception as e:
        print(f"RSS error [{feed['name']}]: {e}")
        return []

def synthesise(section_id, items, source_names):
    """Call Claude API to synthesise articles from RSS items."""
    from datetime import datetime
    today = datetime.now().strftime('%A, %d %B %Y')
    label = SECTION_LABELS.get(section_id, section_id)

    headlines = '\n'.join(
        f"[{i+1}] ({it['source']}) {it['title']}: {it['description']}"
        for i, it in enumerate(items[:15])
    )

    prompt = f"""You are the editor of The Gulf Epoch, a premium AI-synthesised personal newspaper for a UAE-based reader with strong interest in the Middle East, India and global affairs. Today is {today}.

You have gathered these real headlines from {', '.join(source_names)} for the section: "{label}".

HEADLINES:
{headlines}

Write exactly 5 original news articles based on these REAL headlines. Each article must:
1. Be based ONLY on actual stories in the headlines above — no invented facts
2. Synthesise multiple related headlines into one cohesive original story where possible
3. Be written in authoritative, elegant newspaper English
4. Prioritise stories most relevant to a UAE-based reader
5. Be accurate — only state facts supported by the source headlines

Return ONLY a valid JSON array with exactly 5 objects. Each must have:
- "tag": 2-3 word category (string)
- "headline": sharp newspaper headline (string)
- "standfirst": one sentence summary (string)
- "body": exactly 5 paragraphs separated by \\n\\n (string)
- "sources": array of source names used (string[])

Start with [ and end with ]. No markdown, no explanation, just JSON."""

    response = requests.post(
        'https://api.anthropic.com/v1/messages',
        headers={
            'x-api-key': API_KEY,
            'anthropic-version': '2023-06-01',
            'content-type': 'application/json',
        },
        json={
            'model': 'claude-sonnet-4-20250514',
            'max_tokens': 4000,
            'messages': [{'role': 'user', 'content': prompt}],
        },
        timeout=60,
    )
    response.raise_for_status()
    data = response.json()
    text = ''.join(b['text'] for b in data.get('content', []) if b.get('type') == 'text')

    # Extract JSON array
    import re
    match = re.search(r'\[[\s\S]*\]', text)
    if not match:
        raise ValueError('No JSON array in Claude response')
    articles = json.loads(match.group(0))
    return articles[:5] if isinstance(articles, list) else []


# ── ROUTES ────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/refresh', methods=['POST'])
def api_refresh():
    """Fetch RSS + synthesise one section. Called once per section."""
    data = request.get_json()
    section_id = data.get('section')

    if section_id not in FEEDS:
        return jsonify({'error': f'Unknown section: {section_id}'}), 400

    # 1. Fetch RSS
    all_items = []
    for feed in FEEDS[section_id]:
        all_items.extend(fetch_rss(feed))

    if not all_items:
        return jsonify({'error': f'No RSS items fetched for {section_id}'}), 200

    # 2. Synthesise with Claude
    source_names = [f['name'] for f in FEEDS[section_id]]
    articles = synthesise(section_id, all_items, source_names)

    return jsonify({'section': section_id, 'articles': articles})


@app.route('/api/health')
def health():
    return jsonify({'status': 'ok', 'api_key_set': bool(API_KEY)})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
