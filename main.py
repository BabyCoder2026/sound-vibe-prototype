from flask import Flask, request, render_template_string
import math
import json
import os

app = Flask(__name__)

# Load dataset
with open("data/recordings.json") as f:
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

        if diff > 0:
            direction = "higher"
        else:
            direction = "lower"

        explanations.append(f"{f} is {direction} by {abs(diff):.2f}")

    return explanations[:3]  # limit to top 3 differences

HTML = """
<!doctype html>
<html>
<head>
  <title>Sound Vibe Prototype</title>
  <style>
    body { font-family: Arial, sans-serif; padding: 30px; }
    input { padding: 8px; width: 250px; }
    button { padding: 8px 12px; cursor: pointer; }
    ul { line-height: 1.6; }
  </style>
</head>
<body>

<h2>Sound Similarity Prototype</h2>

<form method="get">
  <input name="q" placeholder="Enter song or artist" size="40">
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
  <small>
    {% for e in r["explanation"] %}
      • {{ e }}<br>
    {% endfor %}
  </small>
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
        return render_template_string(HTML)

    matches = [
        d for d in DATA.values()
        if q in d["title"].lower() or q in d["artist"].lower()
    ]

    if not matches:
        return render_template_string(HTML)

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

    return render_template_string(
        HTML,
        base=base,
        recs=recs,
        features=FEATURES
    )
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    app.run(host="0.0.0.0", port=port)
