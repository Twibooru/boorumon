# boorumon

Monitor Philomena image boorus and push new images uploaded to them to a Redis queue.

## Setup

Install redis with `sudo apt install redis-server`

Then install the necessary python packages with `python install -r requirements.txt`

## Usage

Start redis with `redis-server`

To begin monitoring for any new images run `python boorumon.py`

