# Reddit-GeoStackr-Bot

A bot which posts stacked (added) scores to [/r/geoguessr](https://reddit.com/r/geoguessr) for series as specified in the `config.yaml`.

See [this post](https://www.reddit.com/r/geoguessr/comments/j6wzvj/3_october_streak_stacker_2/g87hqfh?utm_source=share&utm_medium=web2x&context=3) for an example.


# Running it

## Copy the `config.yaml.example` and rename it to `config.yaml`:

* Add the reddit api keys, username and password of the bot account.
* Add the series name and author in the series dict
* Set debug to `True` if you want to make a single test-run to see what it would do

## Install the requirements using pip:

`pip3 install requirements.txt`

## Run it in a `tmux` or `screen` session on your server:

`python3 geostackr.py`

If `debug` is set to `False` then it will run in a while True loop every 10 minutes.
