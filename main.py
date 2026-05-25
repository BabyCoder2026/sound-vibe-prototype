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

def pick_best_local_match(selected_title, selected_artist):
    """
    We don't have live audio features yet, so we map the selected MusicBrainz recording
    to the closest local dataset entry by title/artist text match.
    """
    st = (selected_title or "").lower()
    sa = (selected_artist or "").lower()

    best = None
    best_score = -1

    for d in DATA.values():
        dt = d["title"].lower()
        da = d["artist"].lower()

        score = 0
        # Title match weight
        if st and st in dt:
            score += 3
        if dt and dt in st:
            score += 2

        # Artist match weight
        if sa and sa in da:
            score += 3
        if da and da in sa:
            score += 2

        # Small bonus for shared words
        for w in set(st.split()):
            if len(w) >= 4 and w in dt:
                score += 1
        for w in set(sa.split()):
            if len(w) >= 4 and w in da:
                score += 1

        if score > best_score:
            best_score = score
            best = d

    return best

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
    headers = {"User-Agent": "SoundVibePrototype/1.0 (your-real-email@example.com)"}

    q = (query or "").strip()
    parts = q.split()

    artist_guess = ""
    title_guess = q

    if len(parts) >= 3:
        artist_guess = " ".join(parts[-2:])
        title_guess = " ".join(parts[:-2])

    # Strict query first (best when it works)
    if artist_guess and title_guess:
        strict_query = f'recording:"{title_guess}" AND artist:"{artist_guess}"'
    else:
        strict_query = q

    def run_query(qstring):
        params = {"query": qstring, "fmt": "json", "limit": 15}
        r = requests.get(url, headers=headers, params=params, timeout=15)
        if r.status_code != 200:
            return []
        data = r.json()
        return data.get("recordings", []) or []

    try:
        recordings = run_query(strict_query)

        # Fallback: if strict returns nothing, try broader search
        if not recordings:
            recordings = run_query(q)

    except Exception:
        return []

    results = []
    for rec in recordings:
        title = rec.get("title", "")

        artist_credit = rec.get("artist-credit") or []
        if artist_credit and isinstance(artist_credit, list) and isinstance(artist_credit[0], dict):
            artist_name = artist_credit[0].get("name", "Unknown")
        else:
            artist_name = "Unknown"

        # Artist filter: contains-match (not exact), only if we guessed an artist
        if artist_guess and artist_guess.lower() not in artist_name.lower():
            continue

        # Remove obvious cover indicators unless the user typed "cover"
        t = title.lower()
        if "cover" not in q.lower():
            if "cover" in t:
                continue
            if "(" in t and "fleetwood mac" in t:
                continue

        results.append({
            "title": title,
            "artist": artist_name,
            "mbid": rec.get("id", "")
        })

    return results[:5]

HTML = """
<!doctype html>
<html>
<head>
  <title>Sound Vibe Prototype</title>
  <style>
    body { font-family: Arial, sans-serif; padding: 30px; }
    input { padding: 8px; width: 320px; }
    button { padding: 8px 12px; cursor: pointer; }
    ul { line-height: 1.6; }
    li { margin-bottom: 10px; }
    small { color: #333; }
    .panel { border: 1px solid #ddd; padding: 14px; margin-top: 16px; border-radius: 6px; }
    .muted { color:#666; }
    .mb-item { margin: 8px 0; }
    .mb-title { font-weight: 700; }
  </style>
</head>
<body>

<h2>Sound Similarity Prototype</h2>

<form method="get" action="/">
  <input name="q" placeholder="Enter song or artist" value="{{ q|default('') }}">
  <button type="submit">Search</button>
</form>

{% if q %}
  <div class="panel">
    <h3>Which version did you mean?</h3>
    <p class="muted">Pick one result below to analyze. (This always appears, even if the results look similar.)</p>

    {% if mb_results and mb_results|length > 0 %}
      <form method="get" action="/">
        <input type="hidden" name="q" value="{{ q }}">
        {% for r in mb_results %}
          <div class="mb-item">
            <label>
              <input type="radio" name="mbid" value="{{ r.mbid }}" {% if selected_mbid == r.mbid %}checked{% endif %}>
              <span class="mb-title">{{ r.title }}</span> — {{ r.artist }}
{% if r.release_title %}
  <small class="muted"> — {{ r.release_title }}{% if r.release_date %} ({{ r.release_date }}){% endif %}</small>
{% endif %}
<br>
<small class="muted">(MBID: {{ r.mbid }})</small>
            </label>
          </div>
        {% endfor %}
        <button type="submit">Analyze Selected Version</button>
      </form>
    {% else %}
      <p>No MusicBrainz results found for that query.</p>
    {% endif %}
  </div>
{% endif %}

{% if base %}
  <hr>
  <h3>Base Recording (Local Dataset Match)</h3>
  <b>{{ base["title"] }}</b> — {{ base["artist"] }}

  {% if selected_title and selected_artist %}
    <p class="muted">Selected from MusicBrainz: <b>{{ selected_title }}</b> — {{ selected_artist }}</p>
  {% endif %}

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
      <b>{{ r["title"] }}</b> — {{ r["artist"] }}<br>
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
    q_raw = request.args.get("q", "")
    q = (q_raw or "").strip()
    selected_mbid = request.args.get("mbid", "")

    # Always fetch MusicBrainz results when q exists
    mb_results = search_musicbrainz(q) if q else []

    # If user searched but hasn't chosen a version yet:
    if q and not selected_mbid:
        return render_template_string(
            HTML,
            q=q_raw,
            mb_results=mb_results,
            selected_mbid="",
            base=None
        )

    # If user picked a MusicBrainz version, find its title/artist
    selected_title = ""
    selected_artist = ""
    if selected_mbid and mb_results:
        for r in mb_results:
            if r.get("mbid") == selected_mbid:
                selected_title = r.get("title", "")
                selected_artist = r.get("artist", "")
                break

    # Map selected MusicBrainz recording -> best local dataset entry
    base = pick_best_local_match(selected_title, selected_artist) if selected_mbid else None
    if not base:
        # fallback: if something went weird, just show picker again
        return render_template_string(
            HTML,
            q=q_raw,
            mb_results=mb_results,
            selected_mbid=selected_mbid,
            base=None
        )

    # Compute recommendations as before
    recs = []
    for d in DATA.values():
        if d == base:
            continue
        rec = d.copy()
        rec["dist"] = distance(base, d)
        rec["explanation"] = explain_difference(base, d)
        recs.append(rec)

    recs = sorted(recs, key=lambda x: x["dist"])[:10]

    return render_template_string(
        HTML,
        q=q_raw,
        mb_results=mb_results,
        selected_mbid=selected_mbid,
        selected_title=selected_title,
        selected_artist=selected_artist,
        base=base,
        recs=recs,
        features=FEATURES
    )
    
# ✅ Temporary test endpoint to prove MusicBrainz works
@app.route("/mbtest")
def mbtest():
    q = "Landslide Fleetwood Mac"
    return {"query_sent": q, "results": search_musicbrainz(q)}

@app.route("/mbdebug")
def mbdebug():
    q = "Landslide Fleetwood Mac"
    url = "https://musicbrainz.org/ws/2/recording/"
    headers = {"User-Agent": "SoundVibePrototype/1.0 (your-real-email@example.com)"}

    parts = q.split()
    artist_guess = " ".join(parts[-2:]) if len(parts) >= 3 else ""
    title_guess = " ".join(parts[:-2]) if len(parts) >= 3 else q
    strict_query = f'recording:"{title_guess}" AND artist:"{artist_guess}"' if artist_guess else q

    def call_mb(query_string):
        params = {"query": query_string, "fmt": "json", "limit": 10}

        try:
            r = requests.get(url, headers=headers, params=params, timeout=15)
        except Exception as e:
            return {
                "query": query_string,
                "status": None,
                "error": f"request_failed: {str(e)}"
            }

        # Always return status + a small response preview (helps diagnose HTML blocks)
        preview = (r.text or "")[:300]
        content_type = r.headers.get("Content-Type", "")

        data = {}
        try:
            data = r.json()
        except Exception:
            # If it wasn't valid JSON, keep data empty
            data = {}

        recs = data.get("recordings", []) if isinstance(data, dict) else []
        mini = []
        for rec in (recs[:5] if isinstance(recs, list) else []):
            ac = rec.get("artist-credit") or []
            artist = ac[0].get("name", "Unknown") if ac and isinstance(ac[0], dict) else "Unknown"
            mini.append({"title": rec.get("title", ""), "artist": artist})

        return {
            "query": query_string,
            "status": r.status_code,
            "content_type": content_type,
            "recordings_count": len(recs) if isinstance(recs, list) else 0,
            "preview_first_5": mini,
            "response_text_preview": preview
        }

    strict = call_mb(strict_query)
    fallback = call_mb(q)

    return {
        "query_sent": q,
        "artist_guess": artist_guess,
        "title_guess": title_guess,
        "strict_query": strict_query,
        "strict": strict,
        "fallback": fallback
    }

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    app.run(host="0.0.0.0", port=port)
