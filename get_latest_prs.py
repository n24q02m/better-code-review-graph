import urllib.request
import json

def get_pulls():
    url = "https://api.github.com/repos/n24q02m/better-code-review-graph/pulls?state=all&sort=created&direction=desc&per_page=10"
    try:
        with urllib.request.urlopen(url) as response:
            return json.loads(response.read())
    except Exception as e:
        print(f"Error: {e}")
        return []

pulls = get_pulls()
for pr in pulls:
    print(f"#{pr['number']} {pr['title']} ({pr['state']})")
    print(f"  Branch: {pr['head']['ref']}")
    print(f"  URL: {pr['html_url']}")
    print(f"  Updated: {pr['updated_at']}")
    print("-" * 20)
