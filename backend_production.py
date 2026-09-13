"""
ShortsLab Backend - Production Ready for Hostinger VPS
Hostinger pe deploy karne ke liye ye file use karo
"""
from flask import Flask, request, jsonify, Response, stream_with_context
from flask_cors import CORS
import yt_dlp
import requests
import re
import os

app = Flask(__name__)
# CORS - Hostinger domain ko allow karo
CORS(app, origins="*", supports_credentials=True)

def extract_id(url):
    m = re.search(r'(?:youtube\.com\/(?:[^\/]+\/.+\/|(?:v|e(?:mbed)?)\/|.*[?&]v=)|youtu\.be\/)([^"&?\/\s]{11})', url)
    return m.group(1) if m else None

@app.route('/')
def home():
    return jsonify({
        'service': 'ShortsLab Backend',
        'version': 'v4-production',
        'status': 'running',
        'endpoints': ['/api/health', '/api/extract', '/api/proxy', '/api/auto-clip']
    })

@app.route('/api/health')
def health():
    return jsonify({'status':'ok', 'service':'ShortsLab Backend v4'})

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

    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
            'format': 'best[ext=mp4]/best',
            'noplaylist': True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            formats = info.get('formats', [])
            mp4_formats = [f for f in formats if f.get('ext') == 'mp4' and f.get('vcodec') != 'none']
            mp4_formats = sorted(mp4_formats, key=lambda x: x.get('height') or 0, reverse=True)
            
            best = None
            for f in mp4_formats:
                if f.get('height') and f.get('height') >= 720 and f.get('acodec') != 'none':
                    best = f
                    break
            if not best and mp4_formats:
                best = mp4_formats[0]

            # Subtitles
            subs = []
            auto_caps = info.get('automatic_captions') or {}
            manual_caps = info.get('subtitles') or {}
            all_caps = {**manual_caps, **auto_caps}
            for lang, caps in all_caps.items():
                if caps:
                    vtt = next((c for c in caps if 'vtt' in c.get('ext','')), caps[0] if caps else None)
                    if vtt:
                        subs.append({'code': lang, 'url': vtt['url']})

            return jsonify({
                'id': vid,
                'title': info.get('title'),
                'thumbnail': info.get('thumbnail') or f'https://img.youtube.com/vi/{vid}/hqdefault.jpg',
                'duration': info.get('duration'),
                'direct_url': best.get('url') if best else None,
                'subtitles': subs[:5],
            })
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({
            'id': vid,
            'title': 'YouTube Video',
            'thumbnail': f'https://img.youtube.com/vi/{vid}/hqdefault.jpg',
            'duration': 0,
            'direct_url': None,
            'error': str(e),
            'fallback': True
        })

@app.route('/api/proxy')
def proxy():
    url = request.args.get('url')
    if not url:
        return jsonify({'error':'url required'}), 400
    try:
        r = requests.get(url, stream=True, timeout=20, headers={
            'User-Agent': 'Mozilla/5.0',
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
    print(f"Starting on 0.0.0.0:{port}")
    app.run(host='0.0.0.0', port=port, threaded=True)
