import urllib.request
import json

def get_pulls():
    url = "https://api.github.com/repos/n24q02m/better-code-review-graph/pulls?state=all&sort=created&direction=desc&per_page=50"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read())
    except Exception as e:
        print(f"Error: {e}")
        return []

pulls = get_pulls()
for pr in pulls:
    if "cleanup" in pr['title'].lower():
        print(f"#{pr['number']} {pr['title']} ({pr['state']}) - Updated: {pr['updated_at']}")
        print(f"  Head: {pr['head']['label']}")
        print(f"  URL: {pr['html_url']}")
        print("-" * 20)
