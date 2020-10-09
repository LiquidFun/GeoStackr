import praw
import re
import os, sys
from datetime import datetime
import math
import time

# Change these if you want to run it for a different series 
USER = "olsnes"
SERIES = "octoberstreakstacker"

DRY_RUN = False

def get_reddit_instance():
    # Read reddit client_id and client_secret from file (to avoid accidentally publishing it)
    inputFile = open(os.path.join(os.path.dirname(__file__), "RedditAPIAccess.txt"))
    lines = []
    for line in inputFile:
        lines.append(line)
    client_id = lines[0]
    client_secret = lines[1]
    username = lines[2]
    password = lines[3]

    # Get reddit instance
    reddit = praw.Reddit(client_id=client_id.rstrip(), 
                         client_secret=client_secret.rstrip(), 
                         user_agent='linux:geostackr:0.1 (by /u/LiquidProgrammer',
                         username=username.rstrip(),
                         password=password.rstrip())
    return reddit


# Get the username of the bot which is currently logged in
def get_bot_username():
    inputFile = open(os.path.join(os.path.dirname(__file__), "RedditAPIAccess.txt"))
    lines = []
    for line in inputFile:
        lines.append(line)
    return lines[2].strip()


ignore_users = {get_bot_username(), "GeoGuessrTrackingBot"}


def get_info_line():
    return """

---

^(I'm a bot! | Author:) ^[LiquidProgrammer](https://www.reddit.com/message/compose/?to=LiquidProgrammer) ^(|) ^([Source code](https://github.com/LiquidFun/GeoStackr))
"""


def get_score_list(submission):
    score_list = {}
    for comment in submission.comments.list():
        numbers = re.findall(r'\d{2,5}', comment.body)
        if numbers:
            if comment.author.name not in ignore_users:
                highest = max([int(a) for a in numbers])
                score_list[comment.author.name] = highest
    return score_list


def get_highest_streak(submission):
    score_list = {}
    for comment in submission.comments.list():
        numbers = re.findall(r'\d{1,5}', comment.body)
        if numbers:
            if comment.author.name not in ignore_users:
                intified = [int(a) for a in numbers]
                m = max(intified)
                highest_streak = max(set(intified) - {m} - {m/100})
                score_list[comment.author.name] = highest_streak
    return score_list


class UserScores:
    def __init__(self, author):
        self.scores = []
        self.author = author

    def add(self, score: int):
        self.scores.append(score)

    def sum(self):
        return sum(self.scores)

    def len(self):
        return len(self.scores)

    def avg(self):
        return self.sum()//self.len()

    def __repr__(self):
        return str(self.scores)


def still_needs_post(submission):
    for comment in submission.comments:
        if comment.author.name == get_bot_username():
            if "Stacked Scores" in comment.body:
                return False
    return True


def get_top(scores_dict):
    score_list = list(scores_dict.items())
    score_list.sort(key=lambda v: -v[1].sum())
    return score_list


def get_formatted_body(top10):
    body = ""
    body += "Stacked Scores:\n\n"
    body += "| # | Username | Times Played | Average | **Sum** |\n"
    body += "|:-|:-|-:|-:|-:|\n"
    for index, (user, scores) in enumerate(top10):
        body += f"| {index+1} | /u/{user} | {scores.len()} | {scores.avg()} | {scores.sum()} |\n"
    body += get_info_line()
    return body


def get_formatted_csv(top):
    text = ""
    text += "    Username, Times Played, Average, Sum\n"
    for index, (user, scores) in enumerate(top):
        text += f"    {user}, {scores.len()}, {scores.avg()}, {scores.sum()}\n"
    return text


def merge_scores(scores_dict, submission):
    sub_scores = get_score_list(submission)
    for user, score in sub_scores.items():
        if user not in scores_dict:
            scores_dict[user] = UserScores(user)
        scores_dict.get(user).add(score)


def check_submissions(user, series):
    print(str(datetime.now()) + ": Running GeoStackr.")

    reddit = get_reddit_instance()
    redditor = reddit.redditor(user)
    relevant_submissions = []
    for submission in redditor.submissions.new():
        if series in submission.title.lower().replace(" ", ""):
            relevant_submissions.append(submission)
    relevant_submissions.sort(key=lambda s: s.created_utc)
    scores_dict = {}
    for s in relevant_submissions:
        print()
        print(s.title, ":")
        # Check if should post
        if scores_dict:
            if still_needs_post(s) or DRY_RUN:
                top = get_top(scores_dict)
                csv = get_formatted_csv(top)
                print(csv)
                subject = f'Statistics for "{s.title}"'
                body = get_formatted_body(top[:10])
                print(body)
                if not DRY_RUN:
                    redditor.message(subject, csv)
                    s.reply(body)

        # Get scores
        merge_scores(scores_dict, s)


if __name__ == "__main__":
    if DRY_RUN:
        check_submissions(USER, SERIES)
    else:
        while True:
            try:
                check_submissions(USER, SERIES)
            except Exception as e:
                print("Found error, skipping this loop. ")
                print(str(e))
            time_to_sleep = 600
            sleep_message = "Sleeping for " + str(time_to_sleep / 60) + " minutes"
            print(sleep_message)
            print("=" * len(sleep_message))
            time.sleep(time_to_sleep)
