"""
ShortsLab Backend v4.3 - Format Not Available Fix
Changed format from best[ext=mp4]/best to best to fix "Requested format is not available"
"""
from flask import Flask, request, jsonify, Response, stream_with_context
from flask_cors import CORS
import yt_dlp
import requests
import re
import os
import time

app = Flask(__name__)
CORS(app, origins="*", supports_credentials=True)

PIPED_SERVERS = [
    'https://pipedapi.kavin.rocks',
    'https://pipedapi.syncpundit.io',
    'https://api.piped.privacydev.net',
    'https://pipedapi.adminforge.de',
    'https://pipedapi.mha.fi',
]

COBALT_SERVERS = [
    'https://co.wuk.sh/api/json',
    'https://api.cobalt.tools/api/json'
]

def extract_id(url):
    m = re.search(r'(?:youtube\.com\/(?:[^\/]+\/.+\/|(?:v|e(?:mbed)?)\/|.*[?&]v=)|youtu\.be\/)([^"&?\/\s]{11})', url)
    return m.group(1) if m else None

def try_piped_first(video_id):
    for base in PIPED_SERVERS:
        try:
            print(f"[PIPED] Trying {base}")
            r = requests.get(f"{base}/streams/{video_id}", timeout=10)
            if r.status_code == 200:
                data = r.json()
                if data.get('videoStreams'):
                    # Accept ANY format with url, not just mp4
                    all_streams = [v for v in data['videoStreams'] if v.get('url')]
                    if all_streams:
                        best = sorted(all_streams, key=lambda x: x.get('width',0) or 0, reverse=True)[0]
                        print(f"[PIPED] SUCCESS {base} -> {best.get('width')}p")
                        return {
                            'id': video_id,
                            'title': data.get('title', 'YouTube Video'),
                            'thumbnail': data.get('thumbnailUrl', f'https://img.youtube.com/vi/{video_id}/hqdefault.jpg'),
                            'duration': data.get('duration', 0),
                            'direct_url': best.get('url'),
                            'subtitles': data.get('subtitles', [])[:3],
                            'source': f'piped:{base}'
                        }
        except Exception as e:
            print(f"[PIPED] {base} fail: {str(e)[:100]}")
            continue
    return None

def try_cobalt(youtube_url):
    for ep in COBALT_SERVERS:
        try:
            print(f"[COBALT] Trying {ep}")
            r = requests.post(ep, json={"url": youtube_url, "vQuality": "720"}, timeout=12, headers={'Accept':'application/json','Content-Type':'application/json'})
            if r.status_code == 200:
                data = r.json()
                url = data.get('url') or (data.get('picker', [{}])[0].get('url') if data.get('picker') else None)
                if url:
                    print(f"[COBALT] SUCCESS")
                    return {
                        'id': extract_id(youtube_url),
                        'title': 'YouTube Video',
                        'thumbnail': f'https://img.youtube.com/vi/{extract_id(youtube_url)}/hqdefault.jpg',
                        'duration': 0,
                        'direct_url': url,
                        'subtitles': [],
                        'source': f'cobalt:{ep}'
                    }
        except Exception as e:
            print(f"[COBALT] fail: {e}")
            continue
    return None

def try_ytdlp_fixed_format(url):
    """
    FIXED: Use 'best' format instead of 'best[ext=mp4]/best' to avoid "format not available"
    """
    
    # Check cookies
    cookie_file = None
    for p in ['/tmp/cookies.txt', './cookies.txt', 'cookies.txt']:
        if os.path.exists(p):
            cookie_file = p
            break
    if os.environ.get('YT_COOKIES') and not cookie_file:
        try:
            with open('/tmp/cookies.txt', 'w') as f:
                f.write(os.environ.get('YT_COOKIES'))
            cookie_file = '/tmp/cookies.txt'
        except:
            pass

    # FIXED FORMATS - use 'best' to avoid format not available error
    base_opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'noplaylist': True,
        # FIX: Use flexible format that always exists
        'format': 'best',
        'extractor_args': {'youtube': {'player_client': ['android']}},
    }
    
    configs = [
        ('android_best', {**base_opts, 'format': 'best', 'extractor_args': {'youtube': {'player_client': ['android']}}}),
        ('android_720', {**base_opts, 'format': 'best[height<=720]/best', 'extractor_args': {'youtube': {'player_client': ['android']}}}),
        ('web_best', {**base_opts, 'format': 'best', 'extractor_args': {'youtube': {'player_client': ['web']}}}),
        ('any_best', {**base_opts, 'format': 'b', 'extractor_args': {'youtube': {'player_client': ['android', 'web']}}}),
    ]
    
    if cookie_file:
        for cfg in configs:
            cfg[1]['cookiefile'] = cookie_file

    for name, opts in configs:
        try:
            print(f"[YT-DLP] Trying {name} with format={opts['format']}")
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                # FIXED: Accept ANY format with url, not just mp4
                formats = info.get('formats', [])
                # Filter only formats with url and video
                valid_formats = [f for f in formats if f.get('url') and f.get('vcodec') != 'none']
                if not valid_formats:
                    valid_formats = [f for f in formats if f.get('url')]
                
                if not valid_formats:
                    print(f"[YT-DLP] {name} - no valid formats found")
                    # Try to use requested_formats or direct url
                    if info.get('url'):
                        print(f"[YT-DLP] {name} using info.url directly")
                        return {
                            'id': extract_id(url),
                            'title': info.get('title'),
                            'thumbnail': info.get('thumbnail') or f'https://img.youtube.com/vi/{extract_id(url)}/hqdefault.jpg',
                            'duration': info.get('duration'),
                            'direct_url': info.get('url'),
                            'subtitles': [],
                            'source': f'ytdlp:{name}:info.url'
                        }
                    continue
                
                # Sort by height
                valid_formats = sorted(valid_formats, key=lambda x: (x.get('height') or 0, x.get('width') or 0), reverse=True)
                
                # Prefer 720p or lower for faster proxy
                best = None
                for f in valid_formats:
                    h = f.get('height') or 0
                    if 360 <= h <= 720:
                        best = f
                        break
                if not best:
                    best = valid_formats[0]
                
                if best and best.get('url'):
                    print(f"[YT-DLP] {name} SUCCESS -> {best.get('height')}p {best.get('ext')}")
                    return {
                        'id': extract_id(url),
                        'title': info.get('title'),
                        'thumbnail': info.get('thumbnail') or f'https://img.youtube.com/vi/{extract_id(url)}/hqdefault.jpg',
                        'duration': info.get('duration'),
                        'direct_url': best.get('url'),
                        'subtitles': [],
                        'source': f"ytdlp:{name}:{best.get('height')}p"
                    }
        except Exception as e:
            err = str(e)[:400]
            print(f"[YT-DLP] {name} failed: {err}")
            if 'format' in err.lower() and 'not available' in err.lower():
                print(f"[YT-DLP] Format not available, trying next format...")
                continue
            if 'bot' in err.lower() or 'sign in' in err.lower():
                time.sleep(0.5)
                continue
            continue
    
    return None

@app.route('/')
def home():
    return jsonify({'service': 'ShortsLab v4.3 Format Fixed', 'status': 'running'})

@app.route('/api/health')
def health():
    return jsonify({'status':'ok', 'version':'v4.3-format-fixed'})

@app.route('/api/extract', methods=['POST', 'OPTIONS'])
def extract():
    if request.method == 'OPTIONS':
        return '', 200
    data = request.get_json() or {}
    url = data.get('url') or request.args.get('url')
    if not url:
        return jsonify({'error':'url required'}), 400
    vid = extract_id(url)
    if not vid:
        return jsonify({'error':'invalid url'}), 400

    print(f"\n=== EXTRACT {vid} ===")
    
    # Piped first (most reliable)
    print("Step 1: Piped...")
    result = try_piped_first(vid)
    if result and result.get('direct_url'):
        return jsonify(result)
    
    print("Step 2: Cobalt...")
    result = try_cobalt(url)
    if result and result.get('direct_url'):
        return jsonify(result)
    
    print("Step 3: yt-dlp with fixed format...")
    result = try_ytdlp_fixed_format(url)
    if result and result.get('direct_url'):
        return jsonify(result)
    
    print("All failed")
    return jsonify({
        'id': vid,
        'title': 'YouTube Video',
        'thumbnail': f'https://img.youtube.com/vi/{vid}/hqdefault.jpg',
        'duration': 0,
        'direct_url': None,
        'error': 'All methods failed. YouTube may have blocked. Use Tab-Record or Upload.',
        'fallback': True,
    })

@app.route('/api/proxy')
def proxy():
    url = request.args.get('url')
    if not url:
        return jsonify({'error':'url required'}), 400
    try:
        r = requests.get(url, stream=True, timeout=20, headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://www.youtube.com/'})
        def generate():
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    yield chunk
        headers = {'Access-Control-Allow-Origin': '*', 'Content-Type': r.headers.get('Content-Type', 'video/mp4')}
        if 'Content-Length' in r.headers:
            headers['Content-Length'] = r.headers['Content-Length']
        return Response(stream_with_context(generate()), headers=headers)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/auto-clip', methods=['POST'])
def auto_clip():
    data = request.get_json() or {}
    duration = float(data.get('duration', 300))
    clips = []
    if duration <= 40:
        clips.append({'start': 0, 'end': min(30, duration), 'label': 'Full — Auto', 'score': 9.2, 'reason': 'Auto'})
    else:
        clips.append({'start': 0, 'end': min(30, duration*0.15), 'label': 'Hook — Auto', 'score': 9.4, 'reason': 'Opening'})
        clips.append({'start': duration*0.42-15, 'end': duration*0.42+15, 'label': 'Viral Peak — Auto', 'score': 8.9, 'reason': 'Mid'})
        clips.append({'start': max(0, duration-30), 'end': duration, 'label': 'CTA — Auto', 'score': 8.5, 'reason': 'End'})
    return jsonify({'clips': clips})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8001))
    app.run(host='0.0.0.0', port=port, threaded=True)
