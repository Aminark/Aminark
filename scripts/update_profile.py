"""Refresh public, merged contributions to repositories owned by others."""

from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

USER = "Aminark"
QUERY = f"is:public is:pr is:merged author:{USER} -user:{USER}"
START = "<!-- contributions:start -->"
END = "<!-- contributions:end -->"
LABELS = {
    "ant-design/ant-design": "Ant Design",
    "alibaba/hooks": "ahooks",
    "baomidou/mybatis-plus": "MyBatis-Plus",
    "codecentric/spring-boot-admin": "Spring Boot Admin",
    "youzan/vant": "Vant",
    "apache/commons-lang": "Apache Commons Lang",
}


def request_page(page):
    params = urlencode({"q": QUERY, "per_page": 100, "page": page,
                        "sort": "created", "order": "asc"})
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "Aminark-profile"}
    if os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]
    request = Request("https://api.github.com/search/issues?" + params, headers=headers)
    for attempt in range(3):
        try:
            with urlopen(request, timeout=30) as response:
                data = json.load(response)
            if data.get("incomplete_results"):
                raise RuntimeError("GitHub returned incomplete search results")
            return data
        except (HTTPError, URLError, RuntimeError):
            if attempt == 2:
                raise
            time.sleep(10 * (attempt + 1))


def fetch_contributions(fetch=request_page):
    first = fetch(1)
    total = first["total_count"]
    if first.get("incomplete_results") or total > 1000:
        raise RuntimeError("Search is incomplete; keeping the existing profile")
    items = list(first["items"])
    for page in range(2, (total + 99) // 100 + 1):
        result = fetch(page)
        if result.get("incomplete_results") or result["total_count"] != total:
            raise RuntimeError("Search changed during pagination; try again later")
        items.extend(result["items"])
    if len(items) != total or len({item["id"] for item in items}) != total:
        raise RuntimeError("Search is missing or repeating results")
    counts = Counter()
    for item in items:
        repo = item["repository_url"].removeprefix("https://api.github.com/repos/")
        if (not re.fullmatch(r"[\w.-]+/[\w.-]+", repo)
                or repo.split("/")[0].lower() == USER.lower()
                or item["user"]["login"].lower() != USER.lower()
                or not item.get("pull_request", {}).get("merged_at")):
            raise RuntimeError("Unexpected contribution in search results")
        counts[repo] += 1
    return counts


def render_section(counts, day):
    search_url = "https://github.com/search?" + urlencode({"q": QUERY, "type": "pullrequests"})
    links = [f"[{LABELS.get(repo, repo)}](https://github.com/{repo})"
             for repo in sorted(counts, key=lambda repo: (-counts[repo], repo))]
    return (f"{START}\n"
            f"[**{sum(counts.values())} merged PRs**]({search_url})"
            f" · **{len(counts)} projects**\n\n"
            + " · ".join(links) + "\n"
            + f"<!-- refreshed: {day} -->\n{END}")


def update_readme(path, counts, day):
    original = path.read_text()
    if original.count(START) != 1 or original.count(END) != 1:
        raise RuntimeError("README contribution markers are missing or duplicated")
    start, end = original.index(START), original.index(END)
    if end < start:
        raise RuntimeError("README contribution markers are reversed")
    updated = original[:start] + render_section(counts, day) + original[end + len(END):]
    if updated != original:
        path.write_text(updated)


if __name__ == "__main__":
    counts = fetch_contributions()
    update_readme(Path(__file__).resolve().parents[1] / "README.md", counts,
                  datetime.now(timezone.utc).date().isoformat())
    print(f"{sum(counts.values())} merged PRs across {len(counts)} projects")
