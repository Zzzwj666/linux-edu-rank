#!/usr/bin/env python3
import json
import os
import shutil
from argparse import ArgumentParser
from datetime import datetime
from functools import reduce

import git
import requests
from tqdm import tqdm

parser = ArgumentParser()
parser.add_argument("--branch", type=str, default="master")
parser.add_argument("--path", type=str, default="/tmp/linux")
parser.add_argument("--repo", type=str, default="Linux Mainline")

args = parser.parse_args()
branch = args.branch
path = args.path
repo_name = args.repo

repo = git.Repo(path)


print("Getting university list...")
university_json = requests.get(
    "https://github.com/Hipo/university-domains-list/raw/master/world_universities_and_domains.json"
).text
university_list: list = json.loads(university_json)


print("Getting commits list...")
commits = list(repo.iter_commits(branch))

meta = {
    "update": datetime.now().isoformat(),
    "repo": repo_name,
    "branch": branch,
    "commit": repo.commit("master").hexsha,
}

# exec command and turn pipe to iterator
result = {}
result_detail = {}
result_authors = {}
print("Total commits: ", len(commits))
for commit in tqdm(commits):
    email = commit.author.email
    if not email:
        continue
    # get email domain
    domain = email.split("@")[-1]
    if not ".edu" in domain:
        continue

    result[domain] = result.get(domain, 0) + 1
    if result_detail.get(domain) is None:
        result_detail[domain] = []
    result_detail[domain].append(repo.git.show(commit.hexsha))
    if result_authors.get(domain) is None:
        result_authors[domain] = {}
    if result_authors.get(domain).get(email) is None:
        result_authors[domain][email] = [commit.author.name, 0]
    result_authors[domain][email][1] = result_authors[domain][email][1] + 1


def get_university(domain):
    for university in university_list:
        if domain in university["domains"]:
            return university

    for university in university_list:
        for raw_domain in university["domains"]:
            if domain.endswith(raw_domain) or raw_domain.endswith(domain):
                return university
    return None


# sort and save result to file
result = map(
    lambda x: {
        "domain": x[0],
        "count": x[1],
        "university": get_university(x[0]),
    },
    result.items(),
)

result_tmp = {}
# merge same university and set domain to list
for item in result:
    if item["university"] is None:
        authors = list(
            map(
                lambda x: {"email": x[0], "name": x[1][0], "count": x[1][1]},
                result_authors.get(item["domain"], {}).items(),
            )
        )
        authors.sort(key=lambda x: x["count"], reverse=True),
        result_tmp[item["domain"]] = {
            "name": f"Unknown ({item['domain']})",
            "domains": [item["domain"]],
            "university": None,
            "count": item["count"],
            "authors": authors,
        }
        continue
    name = item["university"]["name"]
    if result_tmp.get(name) is None:
        result_tmp[name] = {
            "name": name,
            "domains": [],
            "university": item["university"],
            "count": 0,
            "authors": [],
        }
    if item["domain"] not in result_tmp[name]["domains"]:
        result_tmp[name]["domains"].append(item["domain"])
        result_tmp[name]["authors"].extend(
            list(
                map(
                    lambda x: {"email": x[0], "name": x[1][0], "count": x[1][1]},
                    result_authors.get(item["domain"], {}).items(),
                )
            )
        )
    result_tmp[name]["authors"].sort(key=lambda x: x["count"], reverse=True)
    result_tmp[name]["count"] += item["count"]

result = list(result_tmp.values())
result.sort(key=lambda x: x["count"], reverse=True)
result = list(map(lambda x: x[1] | {"id": x[0] + 1}, enumerate(result)))

result = reduce(
    lambda s, i: s
    + [
        i
        | {
            "rank": (
                i["id"]
                if len(s) == 0 or i["count"] != s[-1]["count"]
                else s[-1]["rank"]
            )
        }
    ],
    result,
    [],
)

with open("result.json", "w") as f:
    f.write(json.dumps({"meta": meta, "data": result}, indent=2))
print("Result saved to result.json")

print("Save patches to detail dir...")

shutil.rmtree("detail", ignore_errors=True)
os.mkdir("detail")


def generate_html(id, title, patches):
    PAGE_SIZE = 10
    total = len(patches)
    page_num = total // PAGE_SIZE + 1

    def get_href(page):
        return f"{id}.html" if page == 1 else f"{id}_{page}.html"

    def get_pagination(page):
        str = ""
        if page > 1:
            str += "<a href='{}'>&lt;&lt;Prev</a>".format(get_href(page - 1))

        for i in range(1, page_num + 1):
            if i == page:
                str += f"<span>[{i}]</span>"
            else:
                str += "<a href='{}'>{}</a>".format(get_href(i), i)

        if page < page_num:
            str += "<a href='{}'>Next&gt;&gt;</a>".format(get_href(page + 1))
        return str

    template = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
    .pagination {{
        border-top: 1px solid #ddd;
        border-bottom: 1px solid #ddd;
        overflow-wrap: break-word;
    }}
    .pagination a, .pagination span {{
        margin: 0 4px;
    }}

    </style>
</head>
<body>
    <h1>{title}</h1>
    <div class="pagination">
        {pagination}
    </div>
    <hr>
    {content}
    <div class="pagination">
        {pagination}
    <div>
</body>
"""
    for i in range(1, page_num + 1):
        with open(f"detail/{get_href(i)}", "w") as f:
            f.write(
                template.format(
                    title=title,
                    pagination=get_pagination(i),
                    content="<hr>".join(
                        map(
                            lambda x: "<pre>{}</pre>".format(
                                x.replace("&", "&amp;")
                                .replace("<", "&lt;")
                                .replace(">", "&gt;")
                            ),
                            patches[(i - 1) * PAGE_SIZE : i * PAGE_SIZE],
                        )
                    ),
                )
                .encode("utf-8", "replace")
                .decode("utf-8")
            )


for item in result:
    domains = item["domains"]

    patches = []
    for d in domains:
        patches.extend(result_detail[d])
    generate_html(item["id"], "Patches contributed by " + item["name"], patches)

print("Done!")
