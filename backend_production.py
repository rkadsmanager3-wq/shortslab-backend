"""
ShortsLab Backend v4.4 - FINAL FIX for "Requested format is not available"
For video 1WEAJ-DFkHE which has only 360p format available
"""
from flask import Flask, request, jsonify, Response, stream_with_context
from flask_cors import CORS
import yt_dlp
import requests
import re
import os

app = Flask(__name__)
CORS(app, origins="*", supports_credentials=True)

def extract_id(url):
    m = re.search(r'(?:youtube\.com\/(?:[^\/]+\/.+\/|(?:v|e(?:mbed)?)\/|.*[?&]v=)|youtu\.be\/)([^"&?\/\s]{11})', url)
    return m.group(1) if m else None

def try_ytdlp_any_format(url):
    """
    Try to get ANY format, not just best[ext=mp4]
    For videos like 1WEAJ-DFkHE which only have 360p
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

    # Try multiple format strategies, from most permissive to specific
    format_strategies = [
        'best',  # Most permissive - should always work
        'b',     # Alias for best
        'bestvideo+bestaudio/best',
        'bv*+ba/b',
        '18',    # 360p mp4 - exists for almost all videos
        '22',    # 720p mp4
        '18/22/best',  # Fallback chain
    ]
    
    clients = ['android', 'ios', 'web', 'tv_embedded', 'android_testsuite']
    
    for client in clients:
        for fmt in format_strategies:
            try:
                print(f"[YT-DLP] Trying client={client}, format={fmt} for {extract_id(url)}")
                opts = {
                    'quiet': True,
                    'no_warnings': True,
                    'skip_download': True,
                    'noplaylist': True,
                    'format': fmt,
                    'extractor_args': {'youtube': {'player_client': [client]}},
                }
                if cookie_file:
                    opts['cookiefile'] = cookie_file
                
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    
                    # Get direct url from info
                    direct_url = None
                    if info.get('url'):
                        direct_url = info.get('url')
                    elif info.get('formats'):
                        # Find any format with url
                        valid = [f for f in info['formats'] if f.get('url')]
                        if valid:
                            # Sort by preference: mp4, then height
                            valid = sorted(valid, key=lambda x: (1 if x.get('ext')=='mp4' else 0, x.get('height') or 0), reverse=True)
                            direct_url = valid[0].get('url')
                            print(f"[YT-DLP] Found format: {valid[0].get('format_id')} {valid[0].get('ext')} {valid[0].get('height')}p")
                    
                    if direct_url:
                        print(f"[YT-DLP] SUCCESS client={client} format={fmt}")
                        return {
                            'id': extract_id(url),
                            'title': info.get('title'),
                            'thumbnail': info.get('thumbnail') or f'https://img.youtube.com/vi/{extract_id(url)}/hqdefault.jpg',
                            'duration': info.get('duration'),
                            'direct_url': direct_url,
                            'subtitles': [],
                            'source': f'ytdlp:{client}:{fmt}'
                        }
            except Exception as e:
                err = str(e)[:300]
                print(f"[YT-DLP] client={client} format={fmt} failed: {err}")
                if 'not available' in err.lower():
                    continue  # Try next format
                if 'bot' in err.lower():
                    continue
                continue
    
    return None

def try_piped_any(video_id):
    """Try Piped with any format"""
    servers = [
        'https://pipedapi.kavin.rocks',
        'https://pipedapi.syncpundit.io',
        'https://api.piped.privacydev.net',
    ]
    for base in servers:
        try:
            print(f"[PIPED] Trying {base}")
            r = requests.get(f"{base}/streams/{video_id}", timeout=10)
            if r.status_code == 200:
                data = r.json()
                streams = data.get('videoStreams', []) + data.get('audioStreams', [])
                # Also check adaptive formats
                all_urls = []
                if data.get('videoStreams'):
                    all_urls.extend(data['videoStreams'])
                if data.get('audioStreams'):
                    # For fallback, we need video, but if only audio, still return for proxy test
                    pass
                if data.get('audioStreams') and not data.get('videoStreams'):
                    # Try hls
                    if data.get('hls'):
                        return {
                            'id': video_id,
                            'title': data.get('title'),
                            'thumbnail': data.get('thumbnailUrl'),
                            'duration': data.get('duration'),
                            'direct_url': data.get('hls'),
                            'subtitles': [],
                            'source': f'piped:{base}:hls'
                        }
                
                valid = [s for s in data.get('videoStreams', []) if s.get('url')]
                if valid:
                    best = sorted(valid, key=lambda x: x.get('width',0), reverse=True)[0]
                    return {
                        'id': video_id,
                        'title': data.get('title'),
                        'thumbnail': data.get('thumbnailUrl'),
                        'duration': data.get('duration'),
                        'direct_url': best.get('url'),
                        'subtitles': [],
                        'source': f'piped:{base}'
                    }
        except Exception as e:
            print(f"[PIPED] {base} fail: {e}")
            continue
    return None

@app.route('/')
def home():
    return jsonify({'service': 'ShortsLab v4.4 Format Fix', 'status': 'running'})

@app.route('/api/health')
def health():
    return jsonify({'status':'ok', 'version':'v4.4-format-any'})

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
    
    # Try yt-dlp with ANY format first (most reliable now)
    result = try_ytdlp_any_format(url)
    if result and result.get('direct_url'):
        return jsonify(result)
    
    # Then Piped
    print("Trying Piped fallback...")
    result = try_piped_any(vid)
    if result and result.get('direct_url'):
        return jsonify(result)
    
    return jsonify({
        'id': vid,
        'title': 'YouTube Video',
        'thumbnail': f'https://img.youtube.com/vi/{vid}/hqdefault.jpg',
        'duration': 0,
        'direct_url': None,
        'error': 'Format not available - YouTube has restricted this video. Use Tab-Record or Upload.',
        'fallback': True,
        'solutions': [
            'This video may be a YouTube Movie with only 360p or special restrictions',
            'Use Tab-Record Mode: Click Tab Record button, select current tab, play video - 100% works',
            'Or download via y2mate.is and upload file',
            'Or try different video (normal videos work better)'
        ]
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
