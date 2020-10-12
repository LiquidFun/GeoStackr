import sys
import re
import time
from datetime import datetime

import praw
import yaml
from matplotlib import pyplot as plt

# Change these if you want to run it for a different series 
CONFIG = "config.yaml"
TOP_COUNT = 20


# Load config
try:
    config = yaml.load(open(CONFIG), Loader=yaml.FullLoader)
except IOError:
    print(f"Could not load {CONFIG}. Make sure to rename it from {CONFIG}.example to {CONFIG}!")
    sys.exit(1)

# In debug mode nothing commiting will be done (i.e. no posts on reddit). Only prints to stdout
try:
    DEBUG_MODE = config['debug']
except KeyError:
    print(f"Setting 'debug' to 'True' since it is not defined in {CONFIG}")
    DEBUG_MODE = True

# Each series to be tracked
try:
    SERIES = config['series']
    print("=== Series found ===")
    for series in SERIES:
        print(f"Series title: {series['title']}, author: {series['author']}")
    print()
except KeyError:
    print(f"No series defined in {CONFIG}!")
    sys.exit(1)


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


def get_reddit_instance():
    reddit_api = config['reddit_api']

    # Get reddit instance
    return praw.Reddit(
        client_id=reddit_api['client_id'],
        client_secret=reddit_api['client_secret'],
        username=reddit_api['username'],
        password=reddit_api['password'],
        user_agent='linux:geostackr:0.1 (by /u/LiquidProgrammer)',
    )


# Get the username of the bot which is currently logged in
def get_bot_username():
    return config['reddit_api']['username']


ignore_users = {get_bot_username(), "GeoGuessrTrackingBot"}


def get_info_line():
    bot = "[bot](https://xkcd.com/1646/)"
    author = "[LiquidProgrammer](https://www.reddit.com/message/compose/?to=LiquidProgrammer)"
    source = "[Source code](https://github.com/LiquidFun/GeoStackr)"

    return f"\n\n---\n\n ^(I'm a {bot}! | Author: {author} | {source})"


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
    indent = " " * 4
    text = f"{indent}Username, Times Played, Average, Sum\n"
    for index, (user, scores) in enumerate(top):
        text += f"{indent}{user}, {scores.len()}, {scores.avg()}, {scores.sum()}\n"
    return text


def merge_scores(scores_dict, submission):
    sub_scores = get_score_list(submission)
    for user, score in sub_scores.items():
        if user not in scores_dict:
            scores_dict[user] = UserScores(user)
        scores_dict.get(user).add(score)


def check_submissions_for_series(user, series):
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
            if still_needs_post(s) or DEBUG_MODE:
                top = get_top(scores_dict)
                csv = get_formatted_csv(top)
                print(csv)
                subject = f'Statistics for "{s.title}"'
                body = get_formatted_body(top[:TOP_COUNT])
                print(body)
                if not DEBUG_MODE:
                    redditor.message(subject, csv)
                    s.reply(body)

        # Get scores
        merge_scores(scores_dict, s)


def handle_each_series():
    for series in SERIES:
        check_submissions_for_series(series['author'], series['title'])


if __name__ == "__main__":
    if DEBUG_MODE:
        handle_each_series()
    else:
        while True:
            try:
                handle_each_series()
            except Exception as e:
                print("Found error, skipping this loop. ")
                print(str(e))
            time_to_sleep = 600
            sleep_message = "Sleeping for " + str(time_to_sleep / 60) + " minutes"
            print(sleep_message)
            print("=" * len(sleep_message))
            time.sleep(time_to_sleep)
