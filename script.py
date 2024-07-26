import praw
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import json
from random import randrange
from tqdm import tqdm

from notion.client import NotionClient
from notion.block import *
from time import sleep
from decouple import config

import sys


TOKEN_V2 = config("TOKEN_V2")


HEADERS = {
    "Authorization": config("BEARER_SECRET"),
    "Content-Type": "application/json",
    "Notion-Version": "2021-05-13",
}


def get_saved():
    reddit = praw.Reddit(
        client_id=config("CLIENT_ID"),
        client_secret=config("CLIENT_SECRET"),
        password=config("PASSWORD"),
        user_agent=config("AGENT"),
        username=config("USERNAME"),
    )

    return list(reddit.user.me().saved(limit=None))[::-1]


def get_notion():
    client = NotionClient(token_v2=TOKEN_V2)

    database = client.get_collection_view(
        "https://www.notion.so/a315520f38524b3d93fc1e8ea2851f65?v=b950d56597204439b6c9da210eda2e58"
    )

    return database


# Formats posts (submissions)
def format_posts(submission):
    out = {
        "post_id": submission.id,
        "type": "Submission",
        "link": "https://www.reddit.com" + str(submission.permalink),
        "title": submission.title,
        "subreddit": submission.subreddit.display_name,
        "text": submission.selftext,
        "is_video": submission.is_video,
        "has_gallery": False,
        "has_img": False,
        "img": False,
        "author": False,
        "flair": submission.link_flair_text,
        "created": datetime.utcfromtimestamp(float(submission.created_utc)).strftime(
            "%Y/%m/%d"
        ),
        "score": submission.score,
        "total_awards_received": submission.total_awards_received,
        "num_comments": submission.num_comments,
        "upvote_ratio": submission.upvote_ratio,
        "shortlink": submission.shortlink,
    }
    if submission.author is not None:
        out["author"] = submission.author.name

    for extension in [".jpg", ".jpeg", ".png", ".gif"]:
        if extension in submission.url:
            out["has_img"] = True
            out["img"] = submission.url
            break
    else:
        if "/gallery/" in submission.url:
            out["has_gallery"] = True

            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.95 Safari/537.36"
            }
            r = requests.get(out["link"], headers=headers)
            soup = BeautifulSoup(r.content, "html.parser")
            x = soup.find(
                "a", class_="_3BxRNDoASi9FbGX01ewiLg iUP9nbvcaxfwKrQTgt0sw"
            ).get("href")
            out["img"] = x

    return out


# Formats comments
def format_comments(comment):
    out = {
        "post_id": comment.id,
        "type": "Comment",
        "link": "https://www.reddit.com" + str(comment.permalink),
        "body": comment.body,
        "author": False,
        "subreddit": comment.subreddit.display_name,
        "created": datetime.utcfromtimestamp(float(comment.created_utc)).strftime(
            "%Y/%m/%d"
        ),
        "score": comment.score,
    }
    if comment.author is not None:
        out["author"] = comment.author.name
    return out


# Formats reddit posts in list into json with relevant info
def formater(post_list):
    out = []
    for i in post_list:
        if type(i) == praw.models.reddit.submission.Submission:
            out.append(format_posts(i))
        else:
            out.append(format_comments(i))
    return out


# Returns posts not saved in local json file, and all post that are currently saved
def to_be_added(saved):
    with open("saved_posts_data.json", "r") as f:
        try:
            current_data = json.load(f)
        except:
            current_data = []

    temp = []
    for post in saved:
        if post.id not in [i["post_id"] for i in current_data]:
            temp.append(post)
            # print(post.id)

    return formater(temp), current_data


# Adds saved posts on reddit that haven't been saved locally yet to the json.
def update_json(to_be_added, current_data):
    from collections import deque

    d = deque(current_data)

    for i in to_be_added:
        d.appendleft(i)

    with open("saved_posts_data.json", "w") as f:
        json.dump(list(d), f)


# Creates select tags for notion page
def patch_select(page_id, category, name, color):
    url = "https://api.notion.com/v1/pages/" + page_id
    if color == "random":
        colors = [
            "gray",
            "brown",
            "orange",
            "yellow",
            "green",
            "blue",
            "purple",
            "pink",
            "red",
        ]
        color = colors[randrange(len(colors)) - 1]

    data = {
        "object": "page",
        "properties": {
            category: {"type": "select", "select": {"name": name, "color": color}},
        },
    }
    r = requests.patch(url, headers=HEADERS, json=data)
    if "Select option color doesn't match existing" in r.text:
        data["properties"][category]["select"].pop("color")
        r = requests.patch(url, headers=HEADERS, json=data)
    return


# Adds newly saved posts to the database
def update_database(to_add, database):
    for post in tqdm(to_add):
        new_row = database.collection.add_row()
        page_id = new_row.id

        if post["type"] == "Submission":
            new_row.post_id = post["post_id"]
            patch_select(page_id, "type", "Submission", "default")
            new_row.Name = post["title"]
            patch_select(page_id, "subreddit", post["subreddit"], "random")
            new_row.text = post["text"]
            new_row.is_video = post["is_video"]
            new_row.has_gallery = post["has_gallery"]
            new_row.has_img = post["has_img"]
            if post["img"]:
                new_row.img = post["img"]
                new_row.img_link = post["img"]
            new_row.author = post["author"]
            patch_select(page_id, "flair", post["flair"], "default")
            new_row.created = post["created"]
            new_row.score = post["score"]
            new_row.total_awards_received = post["total_awards_received"]
            new_row.num_comments = post["num_comments"]
            new_row.upvote_ratio = str(post["upvote_ratio"])
            new_row.link = post["shortlink"]

            newchild = new_row.children.add_new(TextBlock, title=post["text"])

        else:
            new_row.post_id = post["post_id"]
            new_row.type = post["type"]
            new_row.Name = post["body"][:20]
            new_row.subreddit = post["subreddit"]
            new_row.is_video = False
            new_row.has_gallery = False
            new_row.has_img = False
            new_row.author = post["author"]
            new_row.flair = None
            new_row.created = post["created"]
            new_row.score = post["score"]
            new_row.link = post["link"]

            newchild = new_row.children.add_new(TextBlock, title=post["body"])


# list of comment/submission object directly from reddit api
saved = get_saved()

# Json data for posts not yet in the database, post that are already saved
to_add, cur = to_be_added(saved)

update_json(to_add, cur)
update_database(to_add, get_notion())

sys.exit()
