import sys
import re
import time
from datetime import datetime

import praw
import yaml


# Change these if you want to run it for a different series
CONFIG = "config.yaml"
FIG_PATH = "last_fig.png"
TOP_COUNT = 20
TOP_PLOT_COUNT = 5
SLEEP_INTERVAL_SECONDS = 600


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

try:
    REDDIT_API = config['reddit_api']
except KeyError:
    print(f"reddit_api not defined in {CONFIG}!")
    sys.exit(1)

try:
    IMGUR_API = config['imgur_api']
except KeyError:
    print(f"imgur_api not defined in {CONFIG}, won't post graphs!")
    IMGUR_API = None


class UserScores:
    def __init__(self, author):
        self.scores = {}
        self.author = author

    def add(self, round_index: int, score: int):
        self.scores[round_index] = score

    def sum(self):
        return sum(self.scores.values())

    def len(self):
        return len(self.scores)

    def avg(self):
        return self.sum()//self.len()

    def last(self):
        return self.scores[max(self.scores)]

    def __repr__(self):
        return str(self.scores)

    def _xy(self):
        xy = {"x": [], "y": []}
        prev_y = 0
        for i in range(1, max(self.scores)+1):
            xy['x'].append(i)
            if i in self.scores:
                prev_y = prev_y + self.scores[i]
            xy['y'].append(prev_y)
        return xy

    def x(self):
        """For using in pyplot"""
        return self._xy()['x']

    def y(self):
        """For using in pyplot"""
        return self._xy()['y']


def get_reddit_instance():
    # Get reddit instance
    return praw.Reddit(
        client_id=REDDIT_API['client_id'],
        client_secret=REDDIT_API['client_secret'],
        username=REDDIT_API['username'],
        password=REDDIT_API['password'],
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

    return f"\n---\n\n^(I'm a {bot}! | Author: {author} | {source})"


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


def get_formatted_body(top10, url=None):
    body = "Stacked Scores:\n\n"
    if url:
        body += f"## NEW! [Score history of top 5 participants]({url})\n\n"
    body += "| # | Username | Times Played | Average | **Sum** |\n"
    body += "|:-|:-|-:|-:|-:|\n"
    for index, (user, scores) in enumerate(top10, 1):
        body += f"| {index} | /u/{user} | {scores.len()} | {scores.avg()} | {scores.sum()} |\n"
    body += get_info_line()
    return body


def get_formatted_csv(top):
    indent = " " * 4
    text = f"{indent}Username, Times Played, Average, Sum\n"
    for index, (user, scores) in enumerate(top, 1):
        text += f"{indent}{user}, {scores.len()}, {scores.avg()}, {scores.sum()}\n"
    return text


def merge_scores(scores_dict, submission, series_index: int):
    sub_scores = get_score_list(submission)
    for user, score in sub_scores.items():
        if user not in scores_dict:
            scores_dict[user] = UserScores(user)
        scores_dict.get(user).add(series_index, score)


def save_plot(scores_dict, series_index: int):
    from matplotlib import pyplot as plt
    from labellines import labelLines
    # Doesn't make much sense to plot anything if there is only 1 post
    if series_index <= 2:
        return None
    plt.rcParams.update({'font.size': 8})
    plt.title(f"Score History for Current Top {TOP_PLOT_COUNT} Participants")
    plt.ylabel("Stacked scores")
    plt.xlabel("Post number")
    plt.xticks(list(range(1, series_index)))
    plt.margins(x=.15)
    for user, scores in scores_dict[:TOP_PLOT_COUNT]:
        prev_line = plt.plot(scores.x(), scores.y(), ".-", label=user, linewidth=1.5)
        x_offset = 0.01 * series_index
        plt.text(scores.x()[-1]+x_offset, scores.y()[-1],
                 scores.sum(), color=prev_line[0].get_color(),
                 verticalalignment="center")
    # for line in plt.gca().get_lines():
    #     print(line, line.get_data())
    filter_lines_below_2x_values = [l for l in plt.gca().get_lines() if len(l.get_data()[0]) >= 2]
    labelLines(filter_lines_below_2x_values, zorder=2.5)
    # plt.legend(loc="upper left")
    plt.savefig(FIG_PATH, dpi=300)
    plt.close()


def upload_to_imgur():
    from imgurpython import ImgurClient
    client = ImgurClient(IMGUR_API['client_id'], IMGUR_API['client_secret'])
    url = client.upload_from_path(FIG_PATH)['link']
    print(f"Uploaded image to {url}")
    return url


def format_title(title):
    return title.lower().replace(" ", "")


def check_submissions_for_series(user, series):
    print(str(datetime.now()) + ": Running GeoStackr.")

    reddit = get_reddit_instance()
    redditor = reddit.redditor(user)
    relevant_submissions = []
    for submission in redditor.submissions.new():
        if series in format_title(submission.title):
            relevant_submissions.append(submission)
    relevant_submissions.sort(key=lambda s: s.created_utc)
    scores_dict = {}
    for series_index, submission in enumerate(relevant_submissions, 1):
        print(f"\n{submission.title}: ")
        # Check if should post
        if scores_dict:
            if still_needs_post(submission) or DEBUG_MODE:
                top = get_top(scores_dict)
                url = None
                if IMGUR_API:
                    save_plot(top, series_index)
                    url = upload_to_imgur()
                csv = get_formatted_csv(top)
                print(csv)
                subject = f'Statistics for "{submission.title}"'
                body = get_formatted_body(top[:TOP_COUNT], url=url)
                print(body)
                # sys.exit()
                if not DEBUG_MODE:
                    redditor.message(subject, csv)
                    submission.reply(body)

        # Get scores
        merge_scores(scores_dict, submission, series_index)


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
            sleep_message = "Sleeping for " + str(SLEEP_INTERVAL_SECONDS / 60) + " minutes"
            print(sleep_message)
            print("=" * len(sleep_message))
            time.sleep(SLEEP_INTERVAL_SECONDS)
