"""
ShortsLab Backend - Bot Bypass Fixed Version
YouTube bot detection fix: android client + Piped/Invidious/Cobalt fallback
"""
from flask import Flask, request, jsonify, Response, stream_with_context
from flask_cors import CORS
import yt_dlp
import requests
import re
import os
import time
import random

app = Flask(__name__)
CORS(app, origins="*", supports_credentials=True)

PIPED_SERVERS = [
    'https://pipedapi.kavin.rocks',
    'https://pipedapi.syncpundit.io',
    'https://api.piped.privacydev.net',
    'https://pipedapi.adminforge.de',
    'https://pipedapi.mha.fi'
]

INVIDIOUS_SERVERS = [
    'https://inv.nadeko.net',
    'https://yewtu.be',
    'https://invidious.nerdvpn.de'
]

COBALT_SERVERS = [
    'https://co.wuk.sh/api/json',
    'https://api.cobalt.tools/api/json'
]

def extract_id(url):
    m = re.search(r'(?:youtube\.com\/(?:[^\/]+\/.+\/|(?:v|e(?:mbed)?)\/|.*[?&]v=)|youtu\.be\/)([^"&?\/\s]{11})', url)
    return m.group(1) if m else None

def try_piped_backend(video_id):
    """Backend se Piped try karo - browser se nahi"""
    for base in PIPED_SERVERS:
        try:
            print(f"Trying Piped backend: {base}")
            r = requests.get(f"{base}/streams/{video_id}", timeout=8)
            if r.status_code == 200:
                data = r.json()
                if data.get('videoStreams'):
                    best = None
                    mp4s = [v for v in data['videoStreams'] if 'mp4' in v.get('mimeType','')]
                    if mp4s:
                        best = sorted(mp4s, key=lambda x: x.get('width',0), reverse=True)[0]
                    else:
                        best = data['videoStreams'][0]
                    
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
            print(f"Piped {base} fail: {e}")
            continue
    return None

def try_invidious_backend(video_id):
    for base in INVIDIOUS_SERVERS:
        try:
            print(f"Trying Invidious: {base}")
            r = requests.get(f"{base}/api/v1/videos/{video_id}", timeout=8)
            if r.status_code == 200:
                data = r.json()
                if data.get('formatStreams'):
                    best = data['formatStreams'][0]
                    return {
                        'id': video_id,
                        'title': data.get('title', 'YouTube Video'),
                        'thumbnail': data.get('videoThumbnails', [{}])[0].get('url', f'https://img.youtube.com/vi/{video_id}/hqdefault.jpg'),
                        'duration': data.get('lengthSeconds', 0),
                        'direct_url': best.get('url'),
                        'subtitles': [],
                        'source': f'invidious:{base}'
                    }
        except Exception as e:
            print(f"Invidious {base} fail: {e}")
            continue
    return None

def try_cobalt_backend(youtube_url):
    for ep in COBALT_SERVERS:
        try:
            print(f"Trying Cobalt: {ep}")
            r = requests.post(ep, json={"url": youtube_url, "vQuality": "720", "isAudioOnly": False}, timeout=10, headers={'Accept':'application/json','Content-Type':'application/json'})
            if r.status_code == 200:
                data = r.json()
                url = data.get('url') or (data.get('picker', [{}])[0].get('url'))
                if url:
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
            print(f"Cobalt {ep} fail: {e}")
            continue
    return None

def try_ytdlp_with_bypass(url):
    """yt-dlp with bot bypass techniques"""
    
    # Technique 1: Android client (most effective against bot check)
    ydl_opts_android = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'format': 'best[ext=mp4]/best',
        'noplaylist': True,
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'web'],
                'player_skip': ['webpage', 'configs'],
            }
        },
        'http_headers': {
            'User-Agent': 'com.google.android.youtube/17.31.35 (Linux; U; Android 6.0.1; en_US; SM-G532G Build/MMB29Q) gzip',
        }
    }
    
    # Technique 2: iOS client
    ydl_opts_ios = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'format': 'best[ext=mp4]/best',
        'noplaylist': True,
        'extractor_args': {
            'youtube': {
                'player_client': ['ios', 'web'],
            }
        },
    }
    
    # Technique 3: Web client with visitor data
    ydl_opts_web = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'format': 'best[ext=mp4]/best',
        'noplaylist': True,
        'extractor_args': {
            'youtube': {
                'player_client': ['web', 'android'],
            }
        },
    }
    
    # Technique 4: TV embedded (often bypasses)
    ydl_opts_tv = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'format': 'best[ext=mp4]/best',
        'noplaylist': True,
        'extractor_args': {
            'youtube': {
                'player_client': ['tv_embedded', 'web'],
            }
        },
    }

    configs = [
        ('android', ydl_opts_android),
        ('ios', ydl_opts_ios),
        ('tv_embedded', ydl_opts_tv),
        ('web', ydl_opts_web),
    ]
    
    for name, opts in configs:
        try:
            print(f"Trying yt-dlp with {name} client...")
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
                formats = info.get('formats', [])
                mp4s = [f for f in formats if f.get('ext') == 'mp4' and f.get('vcodec') != 'none']
                mp4s = sorted(mp4s, key=lambda x: x.get('height') or 0, reverse=True)
                best = None
                for f in mp4s:
                    if f.get('height') and f.get('height') >= 720 and f.get('acodec') != 'none':
                        best = f
                        break
                if not best and mp4s:
                    best = mp4s[0]
                
                if best and best.get('url'):
                    print(f"yt-dlp {name} SUCCESS")
                    subs = []
                    all_caps = {**(info.get('subtitles') or {}), **(info.get('automatic_captions') or {})}
                    for lang, caps in all_caps.items():
                        if caps:
                            vtt = next((c for c in caps if 'vtt' in c.get('ext','')), caps[0] if caps else None)
                            if vtt:
                                subs.append({'code': lang, 'url': vtt['url']})
                    
                    return {
                        'id': extract_id(url),
                        'title': info.get('title'),
                        'thumbnail': info.get('thumbnail') or f'https://img.youtube.com/vi/{extract_id(url)}/hqdefault.jpg',
                        'duration': info.get('duration'),
                        'direct_url': best.get('url'),
                        'subtitles': subs[:5],
                        'source': f'ytdlp:{name}'
                    }
        except Exception as e:
            err = str(e)
            print(f"yt-dlp {name} failed: {err[:200]}")
            # If bot detection, continue to next client
            if 'bot' in err.lower() or 'sign in' in err.lower():
                print(f"Bot detection with {name}, trying next...")
                time.sleep(1)
                continue
            continue
    
    return None

@app.route('/')
def home():
    return jsonify({
        'service': 'ShortsLab Backend - Bot Bypass',
        'version': 'v4.1-fixed',
        'status': 'running',
        'fixes': ['android client bypass', 'piped fallback', 'invidious fallback', 'cobalt fallback'],
        'endpoints': ['/api/health', '/api/extract', '/api/proxy', '/api/auto-clip']
    })

@app.route('/api/health')
def health():
    return jsonify({'status':'ok', 'service':'ShortsLab Backend v4.1 bot-bypass'})

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
        return jsonify({'error':'invalid youtube url'}), 400

    print(f"\n=== Extract request for {vid} : {url} ===")
    
    # Try 1: yt-dlp with bot bypass (android, ios, tv)
    result = try_ytdlp_with_bypass(url)
    if result and result.get('direct_url'):
        print(f"SUCCESS via {result.get('source')}")
        return jsonify(result)
    
    print("yt-dlp all clients failed, trying Piped backend...")
    
    # Try 2: Piped backend (often works when yt-dlp blocked)
    result = try_piped_backend(vid)
    if result and result.get('direct_url'):
        print(f"SUCCESS via {result.get('source')}")
        return jsonify(result)
    
    print("Piped failed, trying Invidious...")
    
    # Try 3: Invidious
    result = try_invidious_backend(vid)
    if result and result.get('direct_url'):
        print(f"SUCCESS via {result.get('source')}")
        return jsonify(result)
    
    print("Invidious failed, trying Cobalt...")
    
    # Try 4: Cobalt
    result = try_cobalt_backend(url)
    if result and result.get('direct_url'):
        print(f"SUCCESS via {result.get('source')}")
        return jsonify(result)
    
    print("All methods failed!")
    
    # All failed - return with error but with thumbnail so frontend can show tab-record
    return jsonify({
        'id': vid,
        'title': 'YouTube Video',
        'thumbnail': f'https://img.youtube.com/vi/{vid}/hqdefault.jpg',
        'duration': 0,
        'direct_url': None,
        'error': 'All extraction methods failed - YouTube bot detection. Use Tab-Record mode or Upload.',
        'fallback': True,
        'suggestion': 'YouTube has blocked datacenter IPs. Please use Tab-Record mode (100% works) or upload video file.'
    })

@app.route('/api/proxy')
def proxy():
    url = request.args.get('url')
    if not url:
        return jsonify({'error':'url required'}), 400
    try:
        # Randomize user agent to avoid blocking
        agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'com.google.android.youtube/17.31.35 (Linux; U; Android 6.0.1; en_US; SM-G532G Build/MMB29Q) gzip',
            'Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15'
        ]
        r = requests.get(url, stream=True, timeout=20, headers={
            'User-Agent': random.choice(agents),
            'Referer': 'https://www.youtube.com/'
        })
        def generate():
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    yield chunk
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Content-Type': r.headers.get('Content-Type', 'video/mp4'),
        }
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
        clips.append({'start': 0, 'end': min(30, duration), 'label': 'Full — Auto', 'score': 9.2, 'reason': 'Auto clipped'})
    else:
        clips.append({'start': 0, 'end': min(30, duration*0.15), 'label': 'Hook — Auto', 'score': 9.4, 'reason': 'Opening hook'})
        clips.append({'start': duration*0.42-15, 'end': duration*0.42+15, 'label': 'Viral Peak — Auto', 'score': 8.9, 'reason': 'Mid peak'})
        clips.append({'start': max(0, duration-30), 'end': duration, 'label': 'CTA — Auto', 'score': 8.5, 'reason': 'End CTA'})
    return jsonify({'clips': clips})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8001))
    print(f"Starting bot-bypass backend on 0.0.0.0:{port}")
    app.run(host='0.0.0.0', port=port, threaded=True)
