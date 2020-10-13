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
DEFAULT_REGEX = r"\d{1,3}00"


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
    SERIES_CONFIGS = config['series']
    print("=== Series found ===")
    for series_config in SERIES_CONFIGS:
        if 'regex' not in series_config:
            series['regex'] = DEFAULT_REGEX
        # print(f"{series_config=}") # Python 3.8 needed :(
        keyvals = ', '.join([f"{k}='{v}'" for k, v in series_config.items()])
        print(f"series_config={keyvals}")
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


def get_goal_function(series_config):
    return {
        "highest": max,
        "lowest": min,
    }[series_config.get('goal', 'highest')]


def get_goal_number_from_text(series_config, text):
    goal_function = get_goal_function(series_config)
    numbers = [int(a) for a in re.findall(series_config['regex'], text)]
    if 'min' in series_config:
        numbers = filter(lambda x: series_config['min'] <= x, numbers)
    if 'max' in series_config:
        numbers = filter(lambda x: x <= series_config['max'], numbers)
    # May return None, needs to be handled
    if numbers:
        return goal_function(numbers)
    return None


def get_score_list(submission, series_config):
    score_list = {}
    for comment in submission.comments.list():
        if comment.author.name not in ignore_users:
            number = get_goal_number_from_text(series_config, comment.body)
            if number:
                score_list[comment.author.name] = number
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
        body += f"[Score history of top 5 participants]({url})\n\n"
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


def merge_scores(scores_dict, submission, series_index: int, series_config):
    sub_scores = get_score_list(submission, series_config)
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


def check_submissions_for_series(series_config):
    print(str(datetime.now()) + ": Running GeoStackr.")

    reddit = get_reddit_instance()
    redditor = reddit.redditor(series_config['author'])
    relevant_submissions = []
    for submission in redditor.submissions.new():
        if format_title(series_config['title']) in format_title(submission.title):
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
        merge_scores(scores_dict, submission, series_index, series_config)


def handle_each_series():
    for series_config in SERIES_CONFIGS:
        check_submissions_for_series(series_config)


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
