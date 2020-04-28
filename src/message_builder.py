# -*- coding: utf-8 -*-

import json
import logging
from datetime import datetime
logger = logging.getLogger()
logger.setLevel(logging.INFO)

from collections import OrderedDict

class MessageBuilder(object):
  def __init__(self, buildInfo, message):
    self.buildInfo = buildInfo
    self.actions = []
    self.messageId = None

    if message:
      logger.info(json.dumps(message, indent=2))
      att = message['attachments'][0]
      self.fields = att['fields']
      self.actions = att.get('actions', [])
      self.messageId = message['ts']
      logger.info("Actions {}".format(self.actions))
    else:
      if buildInfo.pipeline == "airflow-dags-codepipeline-prod":
        self.fields = [
          { "title" : ":airflow: Dags Airflow",
            "value" : "UNKNOWN",
            "short" : False
          }
        ]
      else:
        self.fields = [
          { "title" : ":picpay: " + buildInfo.pipeline,
            "value" : "UNKNOWN",
            "short" : False
          }
        ]
    
  def hasField(self, name):
    return len([f for f in self.fields if f['title'] == name]) > 0

  def needsRevisionInfo(self):
    return not self.hasField('Revision')

  def attachRevisionInfo(self, rev):
    if self.needsRevisionInfo() and rev:
      revisionSummary = rev['revisionSummary'].replace('\n', ' ')
      git_user = revisionSummary.split(" ")[5].split('/')[0]
      branch = revisionSummary.split(" ")[5].split('/')[1]
      pr_id = revisionSummary.split('#')[1].split(' ')[0]
      pr_name = revisionSummary.split(branch)[1]
      
      if len(self.fields) < 1:
        self.fields.append({
          "title": "Revision",
          "value": ">*Merge PR #{}:* {}\n>:github: *@{} | :branch:{}*\n".format(pr_id, pr_name, git_user, branch),
          "short": False
        })
      else:
        tmp = self.fields
        self.fields = []
        self.fields.append(tmp[0])
        self.fields.append({
          "title": "",
          "value": "---",
          "short": False
        })
        self.fields.append({
          "title": "Revision",
          "value": ">*Merge PR #{}:* {}\n>:github: *@{} | :branch:{}*\n".format(pr_id, pr_name, git_user, branch),
          "short": False
        })
        self.fields.append({
          "title": "",
          "value": "---",
          "short": False
        })
        for el in tmp[1:]:
          self.fields.append(el)

      if rev['revisionUrl']:
        self.findOrCreateAction("Link PR", rev['revisionUrl'])

  def findOrCreateTime(self, title, short=False):
    for a in self.fields:
      if a['title'] == title:
        return a
    sep = { "title": "", "value": "---", "short": short }
    p = { "title": title, "value": ">Started: \n>Ended: ", "short": short }
    self.fields.append(sep)
    self.fields.append(p)
    return p

  def attachTime(self, started_at, ended_at):
    time = self.findOrCreateTime("Codepipeline Timestamp")
    s = " ".join(time['value'].split('\n')[0].split(' ')[1:])
    e = " ".join(time['value'].split('\n')[1].split(' ')[1:])

    if started_at != 'no_update':
      started_at = datetime.strptime(started_at, "%Y-%m-%dT%H:%M:%SZ").strftime("%d/%m/%Y %H:%M:%S UTC")
      time['value'] = ">Started: {}\n>Ended: {}".format(started_at, e)
    
    if ended_at != 'no_update':
      ended_at = datetime.strptime(ended_at, "%Y-%m-%dT%H:%M:%SZ").strftime("%d/%m/%Y %H:%M:%S UTC")
      time['value'] = ">Started: {}\n>Ended: {}".format(s, ended_at)
    
    print(time['value'])
   

  def attachLogs(self, logs):
    self.findOrCreateAction('CloudWatch Logs', logs['deep-link'])

  def findOrCreateAction(self, name, link):
    for a in self.actions:
      if a['text'] == name:
        return a
    
    a = { "type": "button", "text": name, "url": link }
    self.actions.append(a)
    return a

  def pipelineStatus(self):
    return self.fields[0]['value'].split(" ")[1].upper()

  def findOrCreatePart(self, title, short=True):
    for a in self.fields:
      if a['title'] == title:
        return a
    
    p = { "title": title, "value": "", "short": short }
    if len(self.fields) > 3:
      time = self.fields[-2:]
      del self.fields[-2:]
      self.fields.append(p)
      for t in time:
        self.fields.append(t)
    else:
      self.fields.append(p)
    return p
  
  def updateBuildStageInfo(self, name, phases, info):
    url = info.get('latestExecution', {}).get('externalExecutionUrl')
    if url:
      self.findOrCreateAction('CodePipeline Logs', url)

    si = self.findOrCreatePart(name, short=False)
    def pi(p):
      p_status = p.get('phase-status', 'IN_PROGRESS')
      return BUILD_PHASES[p_status]
    def fmt_p(p):
      msg = ">{} {}".format(pi(p), p['phase-type'].capitalize())
      d = p.get('duration-in-seconds')    
      if d:
        return msg + " - Time: {} seconds\n".format(d)
      else:
        msg = msg + "\n"
      return msg

    def show_p(p):
      d = p.get('duration-in-seconds') 
      # if d != None:
      return p['phase-type'] != 'COMPLETED' 
      # else:
      #   return None

    def pc(p):
      ctx = p.get('phase-context', [])
      if len(ctx) > 0:
        if ctx[0] != ': ':
          return ctx[0]
      return None
    
    context = [pc(p) for p in phases if pc(p)]
    
    if len(context) > 0:
      self.findOrCreatePart("Build Context", short=False)['value'] = " ".join(context)
    
    pp = [fmt_p(p) for p in phases if show_p(p)]
    si['value'] = "".join(pp) 
    print("si= "+si['value'])
    

  def updatePipelineEvent(self, event):
    if event['detail-type'] == "CodePipeline Pipeline Execution State Change":
      self.fields[0]['value'] = ">" + STATE_ICONS[event['detail']['state']] + " " + event['detail']['state'].capitalize() 
      if event['detail']['state'] == 'STARTED':
        self.attachTime(event['time'], 'no_update')
      elif (event['detail']['state'] == 'SUCCEEDED') or (event['detail']['state'] == 'FAILED') or (event['detail']['state'] == 'CANCELED'):
        self.attachTime('no_update', event['time'])


  def color(self):
    return STATE_COLORS.get(self.pipelineStatus(), '#eee')

  def message(self):
    return [
      {
        "fields": self.fields,
        "color":  self.color(),
        "footer": self.buildInfo.executionId,
        "actions": self.actions
      }
    ]

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
