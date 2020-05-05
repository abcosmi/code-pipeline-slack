import slack
import os
import json
import logging
from datetime import datetime
logger = logging.getLogger()
logger.setLevel(logging.INFO)

sc_bot = slack.WebClient(os.getenv("SLACK_BOT_TOKEN"))
SLACK_CHANNEL = os.getenv("SLACK_CHANNEL")
SLACK_PR_CHANNEL = os.getenv("SLACK_PR_CHANNEL")
SLACK_BOT_NAME = os.getenv("SLACK_BOT_NAME", "BuildBot")
SLACK_BOT_ICON = os.getenv("SLACK_BOT_ICON", ":robot_face:")

CHANNEL_CACHE = {}


def find_channel(name):
    if name in CHANNEL_CACHE:
        return CHANNEL_CACHE[name]

    r = sc_bot.conversations_list(exclude_archived=1, types='private_channel,public_channel')

    if 'error' in r:
        logger.error("error: {}".format(r['error']))
    else:
        for ch in r['channels']:
            if ch['name'] == name:
                CHANNEL_CACHE[name] = ch['id']
                return ch['id']

    return None


def find_msg(ch, window_ms=1800, limit=200):
    now_ms = datetime.now().timestamp()
    oldest_ms = now_ms - window_ms 

    return sc_bot.conversations_history(channel=ch, limit=limit, inclusive="true", oldest=str(oldest_ms), latest=str(now_ms))

USER_CACHE = {}

def find_my_messages(ch_name, user_name=SLACK_BOT_NAME):
    ch_id = find_channel(ch_name)
    msg = find_msg(ch_id)
    if 'error' in msg:
        logger.error("error: {}".format(msg['error']))
    else:
        cached_user = USER_CACHE.get(user_name, "not_found")
        if cached_user == "not_found":
            for m in msg['messages']:
                user = sc_bot.users_info(user=m.get('user'))
                if user['ok']:
                    if user['user']['name'] == user_name:
                        USER_CACHE[user_name] = m.get('user')
                        yield m
        else:
            for m in msg['messages']:
                if cached_user == m.get('user'):
                    yield m


MSG_CACHE = {}


def find_message_for_build(buildInfo):
    cached = MSG_CACHE.get(buildInfo.executionId)
    
    if cached:
        return cached
    
    for m in find_my_messages(SLACK_CHANNEL):
        for block in msg_blocks(m):
            if block['block_id'] == "9-footer":
                if block['elements'][0]['text'] == buildInfo.executionId:
                    MSG_CACHE[buildInfo.executionId] = m
                    return m
    return None


def msg_blocks(m):
    return m.get('blocks', [])


def find_user_per_message(pr_id, ch_id):
    msgs = find_msg(ch_id, window_ms=1728000, limit=1000)
    for m in msgs['messages']:
        if m['text'].find(pr_id) != -1:
            return m['user']
    return None

def send_codepipeline_result(msgBuilder):
    if msgBuilder.messageId:
        ch_id = find_channel(SLACK_PR_CHANNEL)
        pr_id = msgBuilder.retrievePRId()
        user = find_user_per_message(pr_id, ch_id)
        msgBuilder.getUser(user)
        r = send_msg(ch_id, msgBuilder,reply=True)
        return r


def post_build_msg(msgBuilder):
    if msgBuilder.messageId:
        ch_id = find_channel(SLACK_CHANNEL)
        msg = msgBuilder.message()
        r = update_msg(ch_id, msgBuilder.messageId, msg)
        # logger.info(json.dumps(r, indent=2))
        if r['ok']:
            r['message']['ts'] = r['ts']
            MSG_CACHE[msgBuilder.buildInfo.executionId] = r['message']
        return r
    
    r = send_msg(SLACK_CHANNEL, msgBuilder)
    if r['ok']:
        # TODO: are we caching this ID?
        #MSG_CACHE[msgBuilder.buildInfo.executionId] = r['ts']
        CHANNEL_CACHE[SLACK_CHANNEL] = r['channel']

    return r


def send_msg(ch, msg_builder, reply=False):
    if reply:
       r = sc_bot.chat_postMessage(
            channel=ch,
            icon_emoji=SLACK_BOT_ICON,
            username=SLACK_BOT_NAME,
            text=msg_builder.result()[0]['text']['text'],
            thread_ts=msg_builder.messageId,
            blocks=msg_builder.result()
        ) 
    else:
        r = sc_bot.chat_postMessage(
            channel=ch,
            icon_emoji=SLACK_BOT_ICON,
            username=SLACK_BOT_NAME,
            blocks=msg_builder.message()
        )

    return r


def update_msg(ch, ts, blocks):

    r = sc_bot.chat_update(
        channel=ch,
        ts=ts,
        icon_emoji=SLACK_BOT_ICON,
        username=SLACK_BOT_NAME,
        blocks=blocks
    )

    return r
