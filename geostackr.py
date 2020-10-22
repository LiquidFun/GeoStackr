#!/bin/python3

import sys
import re
import time
from typing import Dict, List, Optional, Callable, Any, Tuple
from datetime import datetime

import praw
import yaml


# Change these if you want to run it for a different series
CONFIG = "config.yaml"
FIG_PATH = "last_fig.png"
SLEEP_INTERVAL_SECONDS = 300


# Load config
try:
    config = yaml.load(open(CONFIG), Loader=yaml.FullLoader)
except IOError:
    print(f"Could not load {CONFIG}. Make sure to rename it from {CONFIG}.example to {CONFIG}!")
    sys.exit(1)

# Check if all keys required to be in config are there
for required_in_config in ["defaults", "reddit_api", "series", "debug"]:
    if required_in_config not in config:
        print(f"'{required_in_config}' not defined in {CONFIG}")
        sys.exit(1)

# In debug mode nothing committing will be done (i.e. no posts on reddit). Only prints to stdout
DEBUG_MODE = config['debug']
DEFAULTS = config['defaults']
REDDIT_API = config['reddit_api']
SERIES_CONFIGS = config['series']

print("=== Series found ===")
for current_series_config in SERIES_CONFIGS:
    if 'regex' not in current_series_config:
        current_series_config['regex'] = DEFAULTS['regex']
    # print(f"{series_config=}") # Python 3.8 needed :(
    keyvals = ', '.join([f"{k}='{v}'" for k, v in current_series_config.items()])
    print(f"series_config={{{keyvals}}}")
print()

try:
    IMGUR_API = config['imgur_api']
except KeyError:
    print(f"imgur_api not defined in {CONFIG}, won't post graphs!")
    IMGUR_API = None


class UserScores:
    def __init__(self, author: str):
        self.scores = {}
        self.author = author

    def __getitem__(self, item: int) -> int:
        return self.scores.get(item, 0)

    def add(self, round_index: int, score: int):
        self.scores[round_index] = score

    def sum(self) -> int:
        return sum(self.scores.values())

    def len(self) -> int:
        return len(self.scores)

    def avg(self) -> int:
        return self.sum()//self.len()

    def last(self) -> int:
        return self.scores[max(self.scores)]

    def __repr__(self) -> str:
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
    # Get an authenticated reddit instance from praw by using the config
    return praw.Reddit(
        client_id=REDDIT_API['client_id'],
        client_secret=REDDIT_API['client_secret'],
        username=REDDIT_API['username'],
        password=REDDIT_API['password'],
        user_agent='linux:geostackr:0.1 (by /u/LiquidProgrammer)',
    )


def get_bot_username() -> str:
    """Get the username of the bot which is currently logged in
    """
    return config['reddit_api']['username']


ignore_users = {get_bot_username(), "GeoGuessrTrackingBot"}


def get_info_line() -> str:
    return """
---

^(I'm a [bot][1]! | Author: [LiquidProgrammer][2] | [Source code][3])

[1]: https://xkcd.com/1646/
[2]: https://www.reddit.com/message/compose/?to=LiquidProgrammer
[3]: https://github.com/LiquidFun/GeoStackr
"""


def get_goal_function(series_config: Dict[str, Any]) -> Callable[[int, int], int]:
    return {
        "highest": max,
        "lowest": min,
    }[series_config.get('goal', 'highest')]


def get_goal_number_from_text(series_config, text) -> Optional[int]:
    goal_function = get_goal_function(series_config)
    # Use regex in series config
    numbers = [int(a) for a in re.findall(series_config['regex'], text)]
    # Min and max may not both be defined, so handle separately
    if 'min' in series_config:
        numbers = filter(lambda x: series_config['min'] <= x, numbers)
    if 'max' in series_config:
        numbers = filter(lambda x: x <= series_config['max'], numbers)
    # May return None, needs to be handled
    if numbers:
        return goal_function(numbers)
    return None


def get_score_list(submission, series_config: Dict[str, UserScores]) -> Dict[str, int]:
    score_list: Dict[str, int] = {}
    for comment in submission.comments.list():
        if comment.author:
            if comment.author.name not in ignore_users:
                number = get_goal_number_from_text(series_config, comment.body)
                if number:
                    score_list[comment.author.name] = number
    return score_list


def get_already_posted_comment(submission):
    for comment in submission.comments:
        if comment.author:
            if comment.author.name == get_bot_username():
                if "Stacked Scores" in comment.body:
                    return comment
    return None


def get_top(scores_dict: Dict[str, UserScores]) -> List[Tuple[str, UserScores]]:
    """Returns a the scores dict as a sorted list of tuples"""
    score_list: List[Tuple[str, UserScores]] = list(scores_dict.items())
    # TODO: sort depending on config goal option
    score_list.sort(key=lambda v: -v[1].sum())
    return score_list


def add_ordinal_suffix(i: int) -> str:
    return str(i) + {1: 'st', 2: 'nd', 3: 'rd'}.get(i if i%100 < 20 else i%10, 'th')


def get_formatted_table(top):
    table = "| # | Username | Times Played | Average | **Sum** |\n"
    table += "|:-|:-|-:|-:|-:|\n"
    last_score_and_index = (None, None)
    for index, (user, scores) in enumerate(top, 1):
        # Remember score and index if multiple people have the same score, so that each of
        # them have the same position
        if last_score_and_index[0] != scores.sum():
            last_score_and_index = (scores.sum(), index)
        index_fmt = add_ordinal_suffix(last_score_and_index[1])
        table += f"| {index_fmt} | /u/{user} | {scores.len()} | {scores.avg()} | {scores.sum()} |\n"
    return table


def get_iso_date():
    return datetime.utcnow().replace(microsecond=0).isoformat().replace("T", " ")


def get_formatted_body(top, urls=[]):
    body = ""
    for url in urls:
        body += url + "\n\n"
        # body += f"[Score history of top {DEFAULTS['top_plot_count']} participants]({url})\n\n"
    body += "Stacked Scores (including current post):\n\n"
    body += get_formatted_table(top)
    body += f"\nUpdated: {get_iso_date()} UTC\n"
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


def save_line_plot(scores_list: List[Tuple[str, UserScores]], series_index: int) -> str:
    from matplotlib import pyplot as plt
    from labellines import labelLines
    # Doesn't make much sense to plot anything if there is only 1 post
    if series_index <= 2:
        return ""
    title = f"Score History for Current Top {DEFAULTS['top_plot_count']} Participants"
    plt.rcParams.update({'font.size': 6})
    plt.title(title)
    plt.ylabel("Stacked scores")
    plt.xlabel("Post number")
    plt.xticks(list(range(1, series_index+1)))
    plt.margins(x=.15)
    for user, scores in scores_list[:DEFAULTS['top_plot_count']]:
        prev_line = plt.plot(scores.x(), scores.y(), ".-", label=user, linewidth=1.5)
        x_offset = 0.01 * series_index
        plt.text(scores.x()[-1]+x_offset, scores.y()[-1],
                 scores.sum(), color=prev_line[0].get_color(),
                 verticalalignment="center")
    # for line in plt.gca().get_lines():
    #     print(line, line.get_data())
    filter_lines_below_2x_values = [l for l in plt.gca().get_lines() if len(l.get_data()[0]) >= 2]
    # print(filter_lines_below_2x_values)
    plt.legend(loc="upper left")
    try:
        labelLines(filter_lines_below_2x_values, zorder=2.5)
    except:
        return ""
    plt.savefig(FIG_PATH, dpi=300)
    plt.close()
    return title


def save_bar_plot(scores_list: List[Tuple[str, UserScores]], series_index: int) -> str:
    from matplotlib import pyplot as plt
    scores_list = list(reversed(scores_list[:DEFAULTS['top_count']]))
    title = f"Bar Plot for Current Top {len(scores_list)} Participants' Scores"
    plt.rcParams.update({'font.size': 6})
    plt.title(title)
    plt.gcf().subplots_adjust(bottom=0.25)
    plt.ylabel("Stacked scores")
    plt.xlabel("Username")
    plt.xticks(list(range(len(scores_list))), [label for label, _ in scores_list], rotation=45)
    prev = [0] * len(scores_list)
    bars = []
    for i in range(1, series_index+1):
        bar_scores = [user_scores[i] for _, user_scores in scores_list]
        bars.append(plt.bar(range(20), bar_scores, bottom=prev, width=0.55))
        prev = [a + b for a, b in zip(prev, bar_scores)]
    plt.legend((b[0] for b in bars), (f"Round #{r}" for r in range(1, len(bars)+1)), loc="upper left")
    plt.savefig(FIG_PATH, dpi=300)
    plt.close()
    return title


def upload_to_imgur() -> str:
    """Uploads the locally saved figure to imgur"""
    from imgurpython import ImgurClient
    client = ImgurClient(IMGUR_API['client_id'], IMGUR_API['client_secret'])
    url = client.upload_from_path(FIG_PATH)['link']
    print(f"Uploaded image to {url}")
    return url


def format_title(title: str):
    """Formats title by making it lowercase and removing all spaces"""
    return title.lower().replace(" ", "").strip()


def if_graph_needs_update(body: str, top: List[Tuple[str, UserScores]]) -> bool:
    """Returns True if at least a single score needs an update"""
    pattern = re.compile(r"\d+ \|$", re.MULTILINE)
    matches = re.findall(pattern, body)[:DEFAULTS['top_count']]
    return any([s[1].sum() != int(c.replace("|", "")) for s, c in zip(top, matches)])


def save_plots_and_get_urls(top_list: List[Tuple[str, UserScores]], series_index) -> List[str]:
    """Goes over every plot function, creates the url and uploads it to imgur"""
    formatted_urls: List[str] = []
    if IMGUR_API:
        for plot_function in [save_line_plot, save_bar_plot]:
            formatted_urls.append(f"[{plot_function(top_list, series_index)}]({upload_to_imgur()})")
    return formatted_urls


def check_submissions_for_series(series_config):
    print(str(datetime.now()) + ": Running GeoStackr.")

    reddit = get_reddit_instance()
    redditor = reddit.redditor(series_config['author'])
    relevant_submissions = []
    for submission in redditor.submissions.new():
        if format_title(series_config['title']) in format_title(submission.title):
            relevant_submissions.append(submission)
    relevant_submissions.sort(key=lambda s: s.created_utc)
    scores_dict: Dict[str, UserScores] = {}
    for series_index, submission in enumerate(relevant_submissions, 1):
        print(f"\n{submission.title}: ")
        # Get scores
        merge_scores(scores_dict, submission, series_index, series_config)

        # Check if should post
        if scores_dict:
            top: List[Tuple[str, UserScores]] = get_top(scores_dict)
            comment = get_already_posted_comment(submission)

            # Post new if not already there
            if comment is None:
                print("\n\n\n=== POSTING NEW COMMENT ===")
                csv = get_formatted_csv(top)
                print(csv)
                subject = f'Statistics for "{submission.title}"'
                urls = save_plots_and_get_urls(top, series_index)
                body = get_formatted_body(top[:DEFAULTS['top_count']], urls=urls)
                print(body)
                if not DEBUG_MODE:
                    redditor.message(subject, csv)
                    submission.reply(body)

            # If comment exists then edit it instead
            else:
                print("\n\n\n=== EDITING COMMENT ===")
                if if_graph_needs_update(comment.body, top):
                    print("=== Updating graph ===")
                    urls = save_plots_and_get_urls(top, series_index)
                else:
                    urls = re.findall(r'\[.*]\(https://i\.imgur\.com/.*\.png\)', comment.body)
                body = get_formatted_body(top[:DEFAULTS['top_count']], urls=urls)
                print(body)
                if not DEBUG_MODE:
                    comment.edit(body)


def handle_each_series():
    for series_config in SERIES_CONFIGS:
        check_submissions_for_series(series_config)


def message_author_about_error(exception):
    import traceback
    subject = f"{get_iso_date()} Error with GeoStackr Bot"
    body = traceback.format_exc()
    user = config['username_to_message_in_case_of_errors']
    print(f"Sending message to author: {user}")
    print(subject)
    print(body, "\n")
    get_reddit_instance().redditor(user).message(subject, body)


if __name__ == "__main__":
    if DEBUG_MODE:
        print("Script running in DEBUG_MODE. No changes to reddit will be commited.")
        handle_each_series()
    else:
        print("Script running without DEBUG_MODE. Changes will be applied to reddit.")
        while True:
            try:
                handle_each_series()
            except Exception as e:
                print("Found error, skipping this loop. ")
                message_author_about_error(e)
            sleep_message = "Sleeping for " + str(SLEEP_INTERVAL_SECONDS / 60) + " minutes"
            print(sleep_message)
            print("=" * len(sleep_message))
            time.sleep(SLEEP_INTERVAL_SECONDS)
