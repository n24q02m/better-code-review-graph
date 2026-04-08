import urllib.request
import json

def fetch(url):
    try:
        with urllib.request.urlopen(url) as response:
            return json.loads(response.read())
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return None

prs = fetch("https://api.github.com/repos/n24q02m/better-code-review-graph/pulls?state=all&per_page=100")
if prs:
    for pr in prs:
        if "file_path" in pr['title'] or "file_path" in pr['head']['ref']:
            print(f"PR #{pr['number']} ({pr['state']}): {pr['title']}")
            print(f"  Branch: {pr['head']['ref']}")
            print(f"  Comments: {pr['comments_url']}")
            print(f"  Review Comments: {pr['review_comments_url']}")
            print("-" * 20)
