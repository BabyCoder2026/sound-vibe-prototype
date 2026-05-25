from flask import Flask, request, render_template_string
import math
import json
import os
import requests

app = Flask(__name__)

# Load dataset (static for now)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(BASE_DIR, "data", "recordings.json")

with open(DATA_PATH) as f:
    DATA = json.load(f)

FEATURES = ["energy", "tempo", "loudness", "danceability", "acousticness", "valence"]

def distance(a, b):
    return math.sqrt(sum((a[f] - b[f]) ** 2 for f in FEATURES))

def explain_difference(base, other):
    explanations = []

    for f in FEATURES:
        diff = other[f] - base[f]
        if abs(diff) < 0.05:
            continue

        if f == "energy":
            phrase = "more energetic and driven" if diff > 0 else "more subdued and restrained"
        elif f == "tempo":
            phrase = "slightly faster in feel" if diff > 0 else "slightly slower and more relaxed"
        elif f == "loudness":
            phrase = "louder and more present" if diff > 0 else "quieter and more intimate"
        elif f == "danceability":
            phrase = "more rhythmically engaging" if diff > 0 else "less rhythm-focused"
        elif f == "acousticness":
            phrase = "more stripped-down and acoustic" if diff > 0 else "more polished and produced"
        elif f == "valence":
            phrase = "emotionally brighter" if diff > 0 else "more emotionally reflective"
        else:
            continue

        explanations.append(phrase)

    return explanations[:3]

def search_musicbrainz(query):
    url = "https://musicbrainz.org/ws/2/recording/"
    headers = {
        "User-Agent": "SoundVibePrototype/1.0 (test@example.com)"
    }

    q = (query or "").strip()
    parts = q.split()
    artist_guess = ""
    title_guess = q

    if len(parts) >= 3:
        artist_guess = " ".join(parts[-2:])
        title_guess = " ".join(parts[:-2])

    if artist_guess and title_guess:
        mb_query = f'recording:"{title_guess}" AND artist:"{artist_guess}"'
    else:
        mb_query = f'recording:"{q}"'

    params = {"query": mb_query, "fmt": "json", "limit": 10}

    r = requests.get(url, headers=headers, params=params, timeout=15)
    r.raise_for_status()

    data = r.json()
    results = []

    for rec in data.get("recordings", []):
        title = rec.get("title", "")

        # SAFELY get artist name (prevents 500 errors)
        artist_credit = rec.get("artist-credit") or []
        if artist_credit and isinstance(artist_credit, list):
            artist_name = artist_credit[0].get("name", "Unknown") if isinstance(artist_credit[0], dict) else "Unknown"
        else:
            artist_name = "Unknown"

        mbid = rec.get("id", "")

        results.append({
            "title": title,
            "artist": artist_name,
            "mbid": mbid
        })

    # Filter out obvious cover entries unless user typed "cover"
    if "cover" not in q.lower():
        results = [x for x in results if "cover" not in (x["title"] or "").lower()]

    return results[:5]

HTML = """
<!doctype html>
<html>
<head>
  <title>Sound Vibe Prototype</title>
  <style>
    body { font-family: Arial, sans-serif; padding: 30px; }
    input { padding: 8px; width: 280px; }
    button { padding: 8px 12px; cursor: pointer; }
    ul { line-height: 1.6; }
    li { margin-bottom: 10px; }
    small { color: #333; }
  </style>
</head>
<body>

<h2>Sound Similarity Prototype</h2>

<form method="get">
  <input name="q" placeholder="Enter song or artist" size="40" value="{{ q|default('') }}">
  <button type="submit">Analyze</button>
</form>

{% if base %}
<hr>
<h3>Base Recording</h3>
<b>{{ base["title"] }}</b> — {{ base["artist"] }}

<h4>Sound Profile</h4>
<ul>
{% for f in features %}
  <li>{{ f }}: {{ "%.2f"|format(base[f]) }}</li>
{% endfor %}
</ul>

<h3>Similar Recordings</h3>
<ol>
{% for r in recs %}
  <li>
    <b>{{ r["title"] }}</b> — {{ r["artist"] }}
    <br>
    {% if r["explanation"] %}
      <small>This version feels {{ r["explanation"] | join(", ") }}.</small>
    {% endif %}
  </li>
{% endfor %}
</ol>
{% endif %}

</body>
</html>
"""

@app.route("/")
def index():
    q = request.args.get("q", "").lower()
    if not q:
        return render_template_string(HTML, q="")

    matches = [
        d for d in DATA.values()
        if q in d["title"].lower() or q in d["artist"].lower()
    ]
    if not matches:
        return render_template_string(HTML, q=request.args.get("q", ""))

    base = matches[0]

    recs = []
    for d in DATA.values():
        if d == base:
            continue
        rec = d.copy()
        rec["dist"] = distance(base, d)
        rec["explanation"] = explain_difference(base, d)
        recs.append(rec)

    recs = sorted(recs, key=lambda x: x["dist"])[:10]
    return render_template_string(HTML, q=request.args.get("q", ""), base=base, recs=recs, features=FEATURES)

# ✅ Temporary test endpoint to prove MusicBrainz works
@app.route("/mbtest")
def mbtest():
    return {"results": search_musicbrainz("Landslide Fleetwood Mac")}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    app.run(host="0.0.0.0", port=port)
