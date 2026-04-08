import urllib.request
import json
import sys

def get_pulls():
    url = "https://api.github.com/repos/n24q02m/better-code-review-graph/pulls?state=all&sort=updated&direction=desc"
    try:
        with urllib.request.urlopen(url) as response:
            return json.loads(response.read())
    except Exception as e:
        print(f"Error: {e}")
        return []

pulls = get_pulls()
for pr in pulls[:20]:
    print(f"#{pr['number']} {pr['title']} ({pr['state']}) - {pr['head']['ref']}")
