import os, json, re, requests, traceback
from flask import Flask, render_template, request, jsonify
from xml.etree import ElementTree as ET
from datetime import datetime

app = Flask(__name__)
API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')

# ── RSS FEEDS ──────────────────────────────────────────────────────────
FEEDS = {
    'mideast-uae': [
        {'name':'Al Jazeera',    'url':'https://www.aljazeera.com/xml/rss/all.xml'},
        {'name':'BBC ME',        'url':'https://feeds.bbci.co.uk/news/world/middle_east/rss.xml'},
        {'name':'BBC World',     'url':'https://feeds.bbci.co.uk/news/world/rss.xml'},
    ],
    'uae': [
        {'name':'Gulf News',     'url':'https://gulfnews.com/rss'},
        {'name':'The National',  'url':'https://www.thenationalnews.com/rss'},
        {'name':'BBC ME',        'url':'https://feeds.bbci.co.uk/news/world/middle_east/rss.xml'},
    ],
    'subcontinent': [
        {'name':'NDTV',          'url':'https://feeds.feedburner.com/ndtvnews-top-stories'},
        {'name':'Times of India','url':'https://timesofindia.indiatimes.com/rssfeedstopstories.cms'},
        {'name':'BBC World',     'url':'https://feeds.bbci.co.uk/news/world/rss.xml'},
    ],
    'world': [
        {'name':'BBC World',     'url':'https://feeds.bbci.co.uk/news/world/rss.xml'},
        {'name':'Guardian',      'url':'https://www.theguardian.com/world/rss'},
        {'name':'NYT World',     'url':'https://rss.nytimes.com/services/xml/rss/nyt/World.xml'},
    ],
    'tech': [
        {'name':'TechCrunch',    'url':'https://techcrunch.com/feed/'},
        {'name':'Wired',         'url':'https://www.wired.com/feed/rss'},
        {'name':'BBC Tech',      'url':'https://feeds.bbci.co.uk/news/technology/rss.xml'},
    ],
    'sports': [
        {'name':'BBC Sport',     'url':'https://feeds.bbci.co.uk/sport/rss.xml'},
        {'name':'ESPN',          'url':'https://www.espn.com/espn/rss/news'},
        {'name':'ESPNcricinfo',  'url':'https://www.espncricinfo.com/rss/content/story/feeds/0.xml'},
    ],
    'business': [
        {'name':'Bloomberg',     'url':'https://feeds.bloomberg.com/markets/news.rss'},
        {'name':'FT',            'url':'https://www.ft.com/rss/home/uk'},
        {'name':'BBC Business',  'url':'https://feeds.bbci.co.uk/news/business/rss.xml'},
    ],
    'life': [
        {'name':'BBC Life',      'url':'https://feeds.bbci.co.uk/news/entertainment_and_arts/rss.xml'},
        {'name':'CNN Travel',    'url':'http://rss.cnn.com/rss/edition_travel.rss'},
        {'name':'Guardian Life', 'url':'https://www.theguardian.com/lifeandstyle/rss'},
    ],
    'markets': [
        {'name':'Bloomberg',     'url':'https://feeds.bloomberg.com/markets/news.rss'},
        {'name':'CNBC',          'url':'https://www.cnbc.com/id/100727362/device/rss/rss.html'},
        {'name':'BBC Business',  'url':'https://feeds.bbci.co.uk/news/business/rss.xml'},
    ],
    'entertainment': [
        {'name':'Variety',       'url':'https://variety.com/feed/'},
        {'name':'BBC Ent',       'url':'https://feeds.bbci.co.uk/news/entertainment_and_arts/rss.xml'},
        {'name':'Guardian Film', 'url':'https://www.theguardian.com/film/rss'},
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

RSS_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'application/rss+xml, application/xml, text/xml, */*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Cache-Control': 'no-cache',
}

def fetch_rss(feed):
    try:
        r = requests.get(feed['url'], headers=RSS_HEADERS, timeout=10)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        items = []
        for item in root.iter('item'):
            title = item.findtext('title', '').strip()
            desc  = re.sub(r'<[^>]+>', '', item.findtext('description', '')).strip()[:300]
            if len(title) > 10:
                items.append({'title': title, 'description': desc, 'source': feed['name']})
            if len(items) >= 6:
                break
        print(f"RSS OK [{feed['name']}]: {len(items)} items")
        return items
    except Exception as e:
        print(f"RSS FAIL [{feed['name']}]: {e}")
        return []

def synthesise(section_id, items, source_names):
    if not API_KEY:
        raise ValueError('ANTHROPIC_API_KEY environment variable not set on server')

    today = datetime.now().strftime('%A, %d %B %Y')
    label = SECTION_LABELS.get(section_id, section_id)
    headlines = '\n'.join(
        f"[{i+1}] ({it['source']}) {it['title']}: {it['description']}"
        for i, it in enumerate(items[:15])
    )

    prompt = f"""You are the editor of The Gulf Epoch, a premium AI-synthesised personal newspaper for a UAE-based reader. Today is {today}.

You have gathered these real headlines from {', '.join(source_names)} for the section: "{label}".

HEADLINES:
{headlines}

Write exactly 5 original news articles based on these REAL headlines. Each article must:
1. Be based ONLY on actual stories in the headlines — no invented facts
2. Synthesise multiple related headlines into one cohesive story where possible
3. Be written in authoritative, elegant newspaper English
4. Prioritise stories relevant to a UAE-based reader
5. Be accurate — only state facts from the source headlines

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
        timeout=90,
    )

    if not response.ok:
        err = response.json().get('error', {})
        raise ValueError(f"Anthropic API error {response.status_code}: {err.get('message', response.text[:200])}")

    data = response.json()
    text = ''.join(b['text'] for b in data.get('content', []) if b.get('type') == 'text')
    match = re.search(r'\[[\s\S]*\]', text)
    if not match:
        raise ValueError(f'No JSON array in Claude response. Got: {text[:300]}')
    articles = json.loads(match.group(0))
    return articles[:5] if isinstance(articles, list) else []


# ── ROUTES ────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/refresh', methods=['POST'])
def api_refresh():
    try:
        data = request.get_json()
        section_id = data.get('section', '')

        if section_id not in FEEDS:
            return jsonify({'error': f'Unknown section: {section_id}'}), 400

        print(f"\n=== Refreshing section: {section_id} ===")

        # Fetch RSS
        all_items = []
        for feed in FEEDS[section_id]:
            all_items.extend(fetch_rss(feed))

        print(f"Total RSS items: {len(all_items)}")

        if not all_items:
            # Return error but don't crash — let client show warning
            return jsonify({'error': f'No RSS items fetched for {section_id} — feeds may be temporarily unavailable'}), 200

        # Synthesise
        source_names = [f['name'] for f in FEEDS[section_id]]
        articles = synthesise(section_id, all_items, source_names)
        print(f"Articles synthesised: {len(articles)}")

        return jsonify({'section': section_id, 'articles': articles})

    except Exception as e:
        tb = traceback.format_exc()
        print(f"ERROR in api_refresh: {e}\n{tb}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/health')
def health():
    return jsonify({
        'status': 'ok',
        'api_key_set': bool(API_KEY),
        'api_key_prefix': API_KEY[:12] + '...' if API_KEY else 'NOT SET'
    })


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
