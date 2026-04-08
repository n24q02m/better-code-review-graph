import urllib.request
import json

def get_pulls():
    url = "https://api.github.com/repos/n24q02m/better-code-review-graph/pulls?state=open"
    try:
        with urllib.request.urlopen(url) as response:
            return json.loads(response.read())
    except Exception as e:
        print(f"Error: {e}")
        return []

pulls = get_pulls()
for pr in pulls:
    if "cleanup-unused-file-path-arg-parser" in pr['head']['ref']:
        print(f"FOUND OPEN PR: #{pr['number']} {pr['title']} - {pr['html_url']}")
