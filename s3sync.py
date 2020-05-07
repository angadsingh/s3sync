import sys
import click
import click_log
import logging
import yaml
import subprocess
import functools
import watchdog.events
import watchdog.observers
import shlex
import time
import token_bucket
from pyformance import timer, time_calls, MetricsRegistry
from pyformance.reporters import ConsoleReporter
from functools import partial 

logger = logging.getLogger(__name__)
click_log.basic_config(logger)

AWS_CLI_MIN_SUPPORTED_VERSION = "2.0.9"
AWS_S3SYNC_PROFILE = "s3sync"
AWS_S3_SYNC_COMMAND = "aws s3 sync --storage-class REDUCED_REDUNDANCY --delete --exact-timestamps {leftPath} {rightPath}"
NUM_TOKENS_PER_PUSH = 10.0 #since rate cannot be < 1 in limiter

def _run_long_command(command):
    process = subprocess.Popen(shlex.split(command), stdout=subprocess.PIPE)
    while True:
        output = process.stdout.readline()
        if (output == '' or output == b'') and process.poll() is not None:
            break
        if output:
            logger.debug(output.decode().strip())
    rc = process.poll()
    return rc


@time_calls
def _do_sync(ctx, leftPath, rightPath, include_patterns=None, exclude_patterns=None):
    logger.info("Performing aws s3 sync from [{}] to [{}]".format(leftPath, rightPath))
    cmd = AWS_S3_SYNC_COMMAND.format(leftPath=leftPath, rightPath=rightPath)
    if include_patterns != None:
        for pattern in include_patterns:
            cmd = " ".join((cmd, "--include \"{}\"".format(pattern)))
    if exclude_patterns != None:
        for pattern in exclude_patterns:
            cmd = " ".join((cmd, "--exclude \"{}\"".format(pattern)))
    logger.debug(cmd)
    returncode = _run_long_command(cmd)
    if returncode != 0:
        ctx.fail("Could not run aws sync command!")
    else:
        logger.info("aws s3 sync ran successfully")
    if ctx.obj['CONFIG']['global']['report_stats']:
        reporter = ConsoleReporter()
        for line in reporter._collect_metrics(reporter.registry)[1:]:
            logger.debug(line)


class FSWatchHandler(watchdog.events.PatternMatchingEventHandler):
    def __init__(self, ctx, localpath, s3path):
        self.ctx = ctx
        self.config = ctx.obj['CONFIG']
        self.localpath = localpath
        self.s3path = s3path

        self.include_patterns = self.config['watcher']['include_patterns']
        self.exclude_patterns = self.config['watcher']['exclude_patterns']
        exclude_directories = self.config['watcher']['exclude_directories']
        case_sensitive = self.config['watcher']['case_sensitive']

        watchdog.events.PatternMatchingEventHandler.__init__(self, patterns=self.include_patterns, ignore_patterns=self.exclude_patterns,
                                                             ignore_directories=exclude_directories, case_sensitive=case_sensitive)

        self.syncop = partial(_do_sync, ctx, self.localpath, self.s3path, include_patterns=self.include_patterns, exclude_patterns=self.exclude_patterns)

        storage = token_bucket.MemoryStorage()
        per_second_rate = (float(self.config['global']['max_syncs_per_minute'])/60.0)*NUM_TOKENS_PER_PUSH
        logger.debug("Rate limiting to [{}] tokens per second".format(per_second_rate))
        self.limiter = token_bucket.Limiter(per_second_rate, 60, storage)

        #do one sync to begin with
        self.syncop()

    def _rate_limited_sync(self):
        if self.limiter.consume('global', num_tokens=NUM_TOKENS_PER_PUSH):
            self.syncop()
        else:
            logger.debug("Rate limited by max_syncs_per_minute [{}]".format((self.limiter._rate*60)/NUM_TOKENS_PER_PUSH))
            time.sleep(NUM_TOKENS_PER_PUSH/self.limiter._rate)
            self._rate_limited_sync()

    def on_any_event(self, event):
        if event.is_directory and event.event_type == "modified":
            return

        logger.info("Watchdog received [{}] event for [{}] - [{}]".format(event.event_type,
            "directory" if event.is_directory else "file",
            event.src_path))

        self._rate_limited_sync()


def _read_config_yaml(ctx, file):
    with open(file, 'r') as stream:
        try:
            return yaml.safe_load(stream)
            logger.info("Loaded configuration yaml")
        except yaml.YAMLError as exc:
            logger.error(exc)
            ctx.fail("Could not load configuration yaml")


def _check_aws_cli_version_compatibility(ctx):
    cmd = 'aws --version' 
    process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)
    result, err = process.communicate()
    if process.returncode != 0:
        ctx.fail("Could not run aws cli to check version")
    version = result.decode().split("/")[1].split(" ")[0]
    if version >= AWS_CLI_MIN_SUPPORTED_VERSION:
        logger.info("Found compatible AWS CLI version [{}]".format(version))
    else:
        ctx.fail("Found incompatible AWS CLI version [{}]".format(version))


def _set_aws_config_param(ctx, param, value):
    cmd = "aws configure --profile {} set {} {}".format(AWS_S3SYNC_PROFILE, param, value)
    process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)
    result, err = process.communicate()
    if process.returncode != 0:
        ctx.fail("Could not set {} in aws credentials under {} profile", param, value)


def _set_s3_advanced_config_params(ctx):
    s3_config = ctx.obj['CONFIG']['s3']
    if 'max_concurrent_requests' in s3_config:
        _set_aws_config_param(ctx, "s3.max_concurrent_requests", s3_config['max_concurrent_requests'])

    if 'max_queue_size' in s3_config:
        _set_aws_config_param(ctx, "s3.max_queue_size", s3_config['max_queue_size'])

    if 'region' in s3_config:
        _set_aws_config_param(ctx, "region", s3_config['region'])

    if 'multipart_threshold' in s3_config:
        _set_aws_config_param(ctx, "multipart_threshold", s3_config['multipart_threshold'])

    if 'multipart_chunksize' in s3_config:
        _set_aws_config_param(ctx, "multipart_chunksize", s3_config['multipart_chunksize'])

    if 'max_bandwidth' in s3_config:
        _set_aws_config_param(ctx, "max_bandwidth", s3_config['max_bandwidth'])

    if 'use_accelerate_endpoint' in s3_config:
        _set_aws_config_param(ctx, "use_accelerate_endpoint", s3_config['use_accelerate_endpoint'])


def _init_aws_cli_profile(ctx):
    cmd = "aws configure get aws_access_key_id"
    process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)
    result, err = process.communicate()
    if process.returncode != 0:
        ctx.fail("Could not find aws_access_key_id in aws credentials. Please set it and rerun.")
    aws_access_key_id = result.decode()
    cmd = "aws configure get aws_secret_access_key"
    process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)
    result, err = process.communicate()
    if process.returncode != 0:
        ctx.fail("Could not find aws_secret_access_key in aws credentials. Please set it and rerun.")
    aws_secret_access_key = result.decode()

    #create s3sync profile, copying default profile's credentials
    _set_aws_config_param(ctx, "aws_access_key_id", aws_access_key_id)
    _set_aws_config_param(ctx, "aws_secret_access_key", aws_secret_access_key)

    if 's3' in ctx.obj['CONFIG']:
        _set_s3_advanced_config_params(ctx)


def base_sync_params(func):
    @click.option('--s3path', required=True, type=click.Path(), help='Full s3 path to sync to/from, e.g. s3://bucket/path')
    @click.option('--localpath', required=True, type=click.Path(), help='Local directory path which you want to sync')
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)
    return wrapper

@click.group()
@click.option('--config', required=True, type=click.Path(), help='Path to the config.yaml file containing configuration params for this utility')
@click.pass_context
@click_log.simple_verbosity_option(logger)
def s3sync(ctx, config):
    """A utility created to sync files to/from S3 as a continuously running
    process, without having to manually take care of managing the sync. 
    It internally uses the aws s3 sync command to do the sync and uses
    python's watchdog listener to get notified of any changes to the watched folder."""
    ctx.obj['CONFIG'] = _read_config_yaml(ctx, config)

@s3sync.command()
@click.pass_context
def init(ctx):
    """Initial setup. Run this for the first-time"""
    _check_aws_cli_version_compatibility(ctx)
    _init_aws_cli_profile(ctx)
    logger.info("Init successful")

@s3sync.command()
@base_sync_params
@click.pass_context
def push(ctx, s3path, localpath):
    """One-way continuous sync from localpath to s3 path (uses a file watcher called watchdog)"""
    logger.info("Starting continuous one-way sync from local path[{}] to s3 path[{}]".format(localpath, s3path))
    event_handler = FSWatchHandler(ctx, localpath, s3path)
    observer = watchdog.observers.Observer()
    observer.schedule(event_handler, path=localpath, recursive=True)
    observer.start()
    try:
        while observer.isAlive():
            observer.join(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

@s3sync.command()
@base_sync_params
@click.option('--interval', required=True, type=click.INT, help='S3 polling interval in seconds')
@click.pass_context
def pull(ctx, s3path, localpath, interval):
    """One-way continuous sync from s3 path to local path (based on polling on an interval)"""
    logger.info("Starting continuous one-way sync from s3 path[{}] to local path[{}]".format(s3path, localpath))
    while True:
        _do_sync(ctx, s3path, localpath)
        time.sleep(interval)

def cli():
    s3sync(obj={})

if __name__ == '__main__':
    s3sync(obj={})
