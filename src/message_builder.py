# -*- coding: utf-8 -*-

import json
import logging
from datetime import datetime
logger = logging.getLogger()
logger.setLevel(logging.INFO)


block_order = ['0-title', '1-status', '2-revision_title', '3-revision',
               '4-build_name', '5-build', '6-build_context_title', '7-build_context', '8-timestamp', '9-footer', '10-divider', '11-actions']


class MessageBuilder(object):
    def __init__(self, buildInfo, message):
        self.buildInfo = buildInfo
        self.blocks = []
        self.messageId = None

        if message:
            logger.info(json.dumps(message, indent=2))
            self.blocks = message['blocks']
            self.messageId = message['ts']
        else:
            if buildInfo.pipeline == "airflow-dags-codepipeline-prod":
                self.findOrCreateBlock(
                    "section", "0-title", "*:airflow: Dags Airflow*")
            else:
                self.findOrCreateBlock(
                    "section", "0-title", ":picpay: *" + buildInfo.pipeline + "*")

    def sortBlocks(self):
      self.blocks.sort(key = lambda i: int(i['block_id'].split('-')[0]))

    def createElement(self, text, element_type="mrkdwn", value=""):
      if element_type == "button":
        element = {
          "type": element_type,
          "text": self.createElement(text=text, element_type="plain_text"),
          "url": value
        }
      else:
        element = {
          "type": element_type,
          "text": text
        }

      return element

    def findOrCreateBlock(self, block_type, block_id, value=""):
        for a in self.blocks:
            if a['block_id'] == block_id:
                return a
        if block_type == "section":
            block = {
                "type": block_type,
                "block_id": block_id,
                "text": {
                    "text": value,
                    "type": "mrkdwn"
                }
            }
        elif block_type == "divider":
            block = {
                "type": block_type,
                "block_id": block_id,
            }
        else:  # context and actions
            block = {
                "type": block_type,
                "block_id": block_id,
                "elements": [] if value == "" else [value]
            }

        self.blocks.append(block)
        return block

    def hasField(self, name):
        return len([f for f in self.blocks if f['block_id'].split('-')[1] == name]) > 0

    def needsRevisionInfo(self):
        return not self.hasField('revision')

    def attachRevisionInfo(self, rev):
        if self.needsRevisionInfo() and rev:
            revisionSummary = rev['revisionSummary'].replace('\n', ' ')
            git_user = revisionSummary.split(" ")[5].split('/')[0]
            branch = revisionSummary.split(" ")[5].split('/')[1]
            pr_id = revisionSummary.split('#')[1].split(' ')[0]
            pr_name = revisionSummary.split(branch)[1]

            self.findOrCreateBlock(
                "section", "2-revision_title", "*Revision*")
            self.findOrCreateBlock(
                "section", "3-revision", ">*Merge PR #{}:* {}\n>:github: *@{} | :branch:{}*\n".format(pr_id, pr_name, git_user, branch))

            if rev['revisionUrl']:
                self.findOrCreateAction("Link PR", rev['revisionUrl'])


    def updateBuildStageInfo(self, name, phases, info):
      url = info.get('latestExecution', {}).get('externalExecutionUrl')
      if url:
          self.findOrCreateAction('CodePipeline Logs', url)

      self.findOrCreateBlock("section", "4-build_title", "*Build*")
      si = self.findOrCreateBlock("section", "5-build", "")

      def pi(p):
            p_status = p.get('phase-status', 'IN_PROGRESS')
            return BUILD_PHASES[p_status]

      def fmt_p(p):
          msg = "&gt;{} {}".format(pi(p), p['phase-type'].capitalize())
          d = p.get('duration-in-seconds')
          if d:
              return msg + " - Time: {} seconds\n".format(d)
          else:
              msg = msg + "\n"
          return msg

      def show_p(p):
        return p['phase-type'] != 'COMPLETED' 
        
      def pc(p):
          ctx = p.get('phase-context', [])
          if len(ctx) > 0:
              if ctx[0] != ': ':
                  return ctx[0]
          return None

      context = [pc(p) for p in phases if pc(p)]

      if len(context) > 0:
          self.findOrCreateBlock("section", "6-build_context_title", "*Build Context*")
          self.findOrCreateBlock("section", "7-build_context", ">" + "".join(context))

      pp = [fmt_p(p) for p in phases if show_p(p)]
      
      if len(pp) >= (len(si['text']['text'].split('\n')) - 1):
        si['text']['text'] = "".join(pp)


    def attachTime(self, started_at, ended_at):
        time = self.findOrCreateBlock("context", "8-timestamp")

        if started_at != 'no_update' and started_at != " ":
            started_at = datetime.strptime(
                started_at, "%Y-%m-%dT%H:%M:%SZ").strftime("%d/%m/%Y %H:%M:%S UTC")
            time['elements'].append(self.createElement(text=">:clock2: Started: {}".format(started_at)))

        if ended_at != 'no_update' and ended_at != " ":
            ended_at = datetime.strptime(
                ended_at, "%Y-%m-%dT%H:%M:%SZ").strftime("%d/%m/%Y %H:%M:%S UTC")
            time['elements'][0]['text'] = time['elements'][0]['text'] + "\n>:clock10: Ended:  {}".format(ended_at)

        

    def attachLogs(self, logs):
        self.findOrCreateAction(name='CloudWatch Logs', link=logs['deep-link'])

    def findOrCreateAction(self, name, link):
        for a in self.blocks:
            if a['block_id'] == '11-actions':
              for el in a['elements']:
                if el['text']['text'] == name:
                  return a
        
        a = self.createElement(text=name, value=link, element_type="button")
        
        try:
          for block in self.blocks:
            if block['block_id'] == "11-actions":
              block['elements'].append(a)
              return block
        except KeyError:
           pass
        
        self.findOrCreateBlock("actions", "11-actions", a)
        
        return a

    def pipelineStatus(self):
        return self.blocks[1]['text']['text'].split(" ")[1].upper()

    def updatePipelineEvent(self, event):
        if event['detail-type'] == "CodePipeline Pipeline Execution State Change":
            status = self.findOrCreateBlock("section", "1-status", ">" + STATE_ICONS[event['detail']
                                                        ['state']] + " " + event['detail']['state'].capitalize())
            status['text']['text'] = ">" + STATE_ICONS[event['detail']
                                                        ['state']] + " " + event['detail']['state'].capitalize()
            if event['detail']['state'] == 'STARTED':
                self.attachTime(event['time'], 'no_update')
            elif (event['detail']['state'] == 'SUCCEEDED') or (event['detail']['state'] == 'FAILED') or (event['detail']['state'] == 'CANCELED'):
                self.attachTime('no_update', event['time'])

    def color(self):
        return STATE_COLORS.get(self.pipelineStatus(), '#eee')

    def message(self):
      self.findOrCreateBlock("context", "9-footer", self.createElement(text=self.buildInfo.executionId))
      self.findOrCreateBlock("divider", "10-divider")
      self.sortBlocks()
      return self.blocks


# https://docs.aws.amazon.com/codepipeline/latest/userguide/detect-state-changes-cloudwatch-events.html
STATE_ICONS = {
    'STARTED': ":loading:",
    'SUCCEEDED': ":done:",
    'RESUMED': "",
    'FAILED': ":x:",
    'CANCELED': ":no_entry:",
    'SUPERSEDED': ""
}

STATE_COLORS = {
    'STARTED': "#9E9E9E",
    'SUCCEEDED': "good",
    'RESUMED': "",
    'FAILED': "danger",
    'CANCELED': "",
    'SUPERSEDED': ""
}

# https://docs.aws.amazon.com/codebuild/latest/APIReference/API_BuildPhase.html
BUILD_PHASES = {
    'SUCCEEDED': ":done:",
    'FAILED': ":x:",
    'FAULT': "",
    'TIMED_OUT': ":stop_watch:",
    'IN_PROGRESS': ":loading:",
    'STOPPED': ""
}
