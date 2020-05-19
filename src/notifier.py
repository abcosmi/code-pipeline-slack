# -*- coding: utf-8 -*-

import json
import boto3
import time

from build_info import BuildInfo, CodeBuildInfo
from slack_helper import post_build_msg, find_message_for_build, send_codepipeline_result
from message_builder import MessageBuilder


codepipeline_client = boto3.client('codepipeline')
codebuild_client = boto3.client('codebuild')

def findRevisionInfo(info):
    r = codepipeline_client.get_pipeline_execution(
        pipelineName=info.pipeline,
        pipelineExecutionId=info.executionId
    )['pipelineExecution']

    revs = r.get('artifactRevisions', [])
    if len(revs) > 0:
        return revs[0]
    return None


def pipelineFromBuild(codeBuildInfo):
    r = codepipeline_client.get_pipeline_state(name=codeBuildInfo.pipeline)
    for s in r['stageStates']:
        for a in s['actionStates']:
            executionId = a.get('latestExecution', {}).get(
                'externalExecutionId')
            if executionId and codeBuildInfo.buildId.endswith(executionId):
                pe = s['latestExecution']['pipelineExecutionId']
                return (s['stageName'], pe, a)

    return (None, None, None)


def processCodePipeline(event):
    buildInfo = BuildInfo.fromEvent(event)
    existing_msg = find_message_for_build(buildInfo)
    builder = MessageBuilder(buildInfo, existing_msg)
    send_reply = builder.updatePipelineEvent(event)

    if builder.needsRevisionInfo():
        revision = findRevisionInfo(buildInfo)
        builder.attachRevisionInfo(revision)

    post_build_msg(builder)

    if send_reply:
        send_codepipeline_result(builder)


def processCodeBuild(event):
    event_id = event['detail']['build-id'].split('/')[1]
    build_status = codebuild_client.batch_get_builds(ids=[event_id])

    pid = event_id.split(':')[1] or None
    if not pid:
        return
    pipeline_name =  event_id.split(':')[0]
    cbi = CodeBuildInfo(build_status['builds'][0]['initiator'][13:], event_id)
    (stage, pid, actionStates) = pipelineFromBuild(cbi)
    buildInfo = BuildInfo(pid,pipeline_name)

    existing_msg = find_message_for_build(buildInfo)
    builder = MessageBuilder(buildInfo, existing_msg)

    
    phases = build_status['builds'][0]['phases']
    builder.updateBuildStageInfo(stage, phases, actionStates)

    logs = build_status['builds'][0].get('logs', {})
    try:
        if logs['streamName']:
            builder.attachLogs(
                logs)
    except KeyError:
        pass

    post_build_msg(builder)


def process(event):
    if event['source'] == "aws.codepipeline":
        processCodePipeline(event)
    if event['source'] == "aws.codebuild":
        processCodeBuild(event)


def run(event, context):
    # print(json.dumps(event, indent=2, default=str))
    process(event)


if __name__ == "__main__":
    with open('full_test.json') as f:
        events = json.load(f)
        for e in events:
            run(e, {})
            time.sleep(1)
