# coding=utf-8
"""
CLI Application Implementation
==============================

"""
import argparse
import collections
import logging
import re
import sys
import time

import boto3
import coloredlogs

from . import __version__

LOGGER = logging.getLogger(__name__)

LOGGING_FORMAT = '%(asctime)s %(name)s %(message)s'
LOGGING_FIELD_STYLES = {
    'hostname': {'color': 'magenta'},
    'programname': {'color': 'cyan'},
    'name': {'color': 'blue'},
    'levelname': {'color': 'white', 'bold': True},
    'asctime': {'color': 'white'}}


Image = collections.namedtuple('Image', ['registry', 'name', 'tag'])

IMAGE_PATTERN = re.compile(
    r'^(?P<repository>[\w.\-_]+(?:(?::\d+|)(?=/[a-z0-9._-]+/[a-z0-9._-]+))|)'
    r'(?:/|)(?P<name>[a-z0-9.\-_]+(?:/[a-z0-9.\-_]+|))'
    r'(?::(?P<tag>[\w.\-_]{1,127})|)$')


class ECSPipeline:
    """Controller class for performing Pipeline based deployments in ECS."""

    def __init__(self, args):
        """Create a new instance of the ECSPipeline class

        :param argparse.namespace args: The parsed CLI args

        """
        self.args = args
        self.client = boto3.client('ecs')
        try:
            self.image = self.parse_image(args.image)
        except ValueError:
            exit_application(
                'Malformed image specified: {}'.format(args.image), 1)
        self.redeploying = False
        try:
            self.service_arn = self._get_service_arn()
        except self.client.exceptions.ClusterNotFoundException:
            exit_application('Cluster not found: {}'.format(args.cluster), 1)
        self.desired_qty, self.current = self._describe_service()
        self.task_definition = self._get_task_definition()

    def deploy(self):
        """Deploy the task definition to the configured cluster."""
        LOGGER.info('%s %s in %s to %s',
                    'Redeploying' if self.redeploying else 'Updating',
                    self.args.service, self.args.cluster,
                    self.task_definition.split('/')[-1])
        result = self.client.update_service(
            cluster=self.args.cluster, service=self.service_arn,
            taskDefinition=self.task_definition,
            forceNewDeployment=self.args.redeploy)
        if result['service']['taskDefinition'] == self.task_definition:
            LOGGER.info('%s %s in %s to %s',
                        'Redeployed' if self.redeploying else 'Updated',
                        self.args.service, self.args.cluster,
                        self.task_definition.split('/')[-1])
            if self.args.wait:
                self._wait_on_tasks()
            LOGGER.info('%s complete',
                        'Redeployment' if self.redeploying else 'Deployment')

    @staticmethod
    def image_to_str(image):
        """Build the image string value from the namedtuple.

        :param Image image: The image tuple to return the string from
        :rtype: str

        """
        if image.registry:
            return '{}/{}:{}'.format(image.registry, image.name, image.tag)
        return '{}:{}'.format(image.name, image.tag)

    @staticmethod
    def parse_image(image):
        """Parse an image returning the info as a namedtuple

        :rtype: Image
        :raises: ValueError

        """
        try:
            result = IMAGE_PATTERN.match(image)
        except TypeError:
            result = None
        if not result:
            raise ValueError('Failed to parse image')
        img = result.groupdict()
        return Image(img['repository'] or None, img['name'],
                     img['tag'] or 'latest')

    def _describe_service(self):
        """Return the current task definition the service and configured
        quantity of tasks for the service.

        :rtype: (qty, dict)

        """
        LOGGER.info('Getting the current task definition for %s in %s',
                    self.args.service, self.args.cluster)
        response = self.client.describe_services(
            cluster=self.args.cluster, services=[self.service_arn])
        return (response['services'][0]['desiredCount'],
                self._describe_task_definition(
                    response['services'][0]['taskDefinition']))

    def _describe_task_definition(self, arn):
        """Return the task definition from ECS.

        :rtype: dict

        """
        response = self.client.describe_task_definition(taskDefinition=arn)
        return response['taskDefinition']

    def _get_service_arn(self):
        """Return the ARN of the service to perform the deployment on.

        :rtype: str

        """
        for arn in self._services():
            parts = arn.split('/')
            if parts[-1] == self.args.service:
                return arn
        exit_application(
            'Service {} not found in {}'.format(
                self.args.service, self.args.cluster), 1)

    def _get_task_definition(self):
        """Return the task definition ARN to use, creating a new task
        definition if required.

        """
        if self.image in self._get_containers(self.current):
            if self.args.redeploy:
                self.redeploying = True
                return self.current['taskDefinitionArn']
            elif self.args.force:
                self.redeploying = True
                return self._save_task_definition(self.current)
            exit_application(
                '{} is already deployed to {} as "{}"'.format(
                    self.args.image, self.args.cluster,
                    self.current['taskDefinitionArn'].split('/')[-1]), 2)
        return self._save_task_definition(
            self._modify_task_definition(self.current))

    def _get_containers(self, task_definition):
        """Return the containers from a task definition.

        :param dict task_definition: The task definition data structure
        :rtype: list

        """
        containers = [
            self.parse_image(cd['image'])
                for cd in task_definition['containerDefinitions']]
        for container in sorted(containers):
            LOGGER.debug('Found %s in the task definition', container)
        return sorted(containers)

    def _get_task_definitions_from_family(self, family):
        """Return a list of task definitions for the family sorted in
        descending numerical order.

        :param str family: The task definition family
        :rtype: list

        """
        LOGGER.info('Getting all of the task definitions for %s in %s',
                    self.args.service, self.args.cluster)
        definitions = []
        paginator = self.client.get_paginator('list_task_definitions')
        for page in paginator.paginate(familyPrefix=family, sort='DESC'):
            definitions += page['taskDefinitionArns']

        for definition in sorted(definitions):
            LOGGER.debug('Task definition %s found', definition)

        return definitions

    def _list_running_tasks(self):
        """Return all tasks and their task definitions as a list of tuples.

        :rtype: [(str, str), ...]

        """
        LOGGER.info('Getting running tasks for %s in %s',
                    self.args.service, self.args.cluster)
        task_arns = []
        paginator = self.client.get_paginator('list_tasks')
        for page in paginator.paginate(cluster=self.args.cluster,
                                       serviceName=self.args.service,
                                       desiredStatus='RUNNING'):
            task_arns += page['taskArns']

        for task_arn in sorted(task_arns):
            LOGGER.debug('Task found: %s', task_arn)

        # Build the result set of tasks that are running
        tasks = []
        while task_arns:
            response = self.client.describe_tasks(
                cluster=self.args.cluster,
                tasks=task_arns[:100])
            for task in response['tasks']:
                LOGGER.debug('Task %s running %s',
                             task['taskArn'], task['taskDefinitionArn'])
                tasks.append((task['taskArn'], task['taskDefinitionArn']))
                task_arns.remove(task['taskArn'])
        return tasks

    def _modify_task_definition(self, definition):
        """Modify the task definition that was passed in, replacing the image
        appropriately with the image that is going to be tagged.

        :param dict definition: The definition to modify
        :rtype: dict

        """
        LOGGER.info('Modifying the task definition "%s" to use %s',
                    definition['taskDefinitionArn'], self.args.image)
        for offset, image in enumerate(self._get_containers(definition)):
            if self.image.registry == image.registry and \
                    self.image.name == image.name:
                definition['containerDefinitions'][offset]['image'] = \
                    self.image_to_str(self.image)
                log_config = definition['containerDefinitions'][offset].get(
                    'logConfiguration', {})
                options = log_config.get('options', {})
                if 'tag' in options:
                    log_config['options']['tag'] = \
                        options['tag'].replace(image.tag, self.image.tag)
                return definition
        raise ValueError(
            'Did not find the image {!r} in the task definition'.format(
                self.args.image))

    def _save_task_definition(self, definition):
        """Save the task definition, returning the new ARN.

        :param dict definition: The new definition to save
        :rtype: str

        """
        for key in {'compatibilities', 'requiresAttributes',
                    'requiresCompatibilities', 'revision', 'status',
                    'taskDefinitionArn'}:
            if key in definition:
                del definition[key]
        LOGGER.debug('Saving the new task definition for %s',
                     definition['family'])
        result = self.client.register_task_definition(**definition)
        return result['taskDefinition']['taskDefinitionArn']

    def _services(self):
        """Return the list of services configured in the cluster.

        :rtype: list

        """
        LOGGER.info('Getting services in the %s cluster', self.args.cluster)
        arns = []
        paginator = self.client.get_paginator('list_services')
        for page in paginator.paginate(cluster=self.args.cluster):
            arns += page['serviceArns']
        for arn in sorted(arns):
            LOGGER.debug('Returning %r', arn)
        return sorted(arns)

    def _wait_on_tasks(self):
        """Wait for all tasks to be in the running state for the task
        definition.

        """
        LOGGER.info('Waiting for %i tasks to enter running state for "%s"',
                    self.desired_qty, self.task_definition.split('/')[-1])
        while True:
            tasks = self._list_running_tasks()
            counts = collections.Counter()
            for _task, task_def in tasks:
                counts[task_def] += 1
            LOGGER.debug('Current running tasks by definition: %s',
                         ', '.join(
                             ['{}: {}'.format(k.split('/')[-1], counts[k])
                              for k in sorted(
                                 counts.keys(),
                                 key=lambda x: int(x.split(':')[-1]))]))
            if counts.get(self.task_definition, 0) == self.desired_qty:
                if not self.args.only_new or (len(tasks) == self.desired_qty):
                    break
            time.sleep(self.args.delay)

    def _running_task_count(self, tasks):
        """Return the quantity of tasks that are running for the task
        definition.

        :param list tasks: The list of task tuples
        :rtype: int

        """
        return len([t for t in tasks if t[1] == self.task_definition])


def parse_cli_args():
    """Construct the CLI argument parser and return the parsed the arguments.

    :rtype: argparse.namespace

    """
    parser = argparse.ArgumentParser(
        prog='ecs-pipeline-deploy',
        description='Opinionated ECS deployment made easy',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        conflict_handler='resolve')

    parser.add_argument('cluster', nargs='?', type=str, metavar='CLUSTER',
                        help='The ECS cluster name to deploy in')
    parser.add_argument('service', nargs='?', type=str, metavar='SERVICE',
                        help='The ECS Service name to deploy')
    parser.add_argument('image', nargs='?', type=str, metavar='IMAGE',
                        help='The Docker image (with tag) to deploy for '
                             'finding the task definition')

    parser.add_argument('-f', '--force', action='store_true',
                        help='Create a new task definition for the image even '
                             'if one already exists for the tagged version')
    parser.add_argument('-r', '--redeploy', action='store_true',
                        help='Force a redeployment if the tagged images match')
    parser.add_argument('-w', '--wait', action='store_true',
                        help='Wait for running tasks to be replaced')
    parser.add_argument('-o', '--only-new', action='store_true',
                        help='If waiting, wait for only newly deployed tasks '
                             'to be running')
    parser.add_argument('-d', '--delay', type=int, default=5,
                        help='Seconds to delay before checking tasks while '
                             'waiting on a deployment to finish')
    parser.add_argument('-v', '--verbose', action='store_true')
    parser.add_argument('-V', '--version', action='version',
                        version='%(prog)s {}'.format(__version__))
    return parser.parse_args()


def configure_logging(args):
    """Setup logging"""
    level = logging.DEBUG if args.verbose else logging.INFO
    coloredlogs.install(level=level, fmt=LOGGING_FORMAT,
                        field_styles=LOGGING_FIELD_STYLES)
    silence_noisy_loggers()


def exit_application(message=None, code=0):
    """Exit the application displaying the message to info or error based upon
    the exit code

    :param str message: The exit message
    :param int code: The exit code (default: 0)

    """
    log_method = LOGGER.error if code else LOGGER.info
    log_method(message.strip())
    sys.exit(code)


def main():
    """Application Entrypoint"""
    args = parse_cli_args()
    configure_logging(args)
    LOGGER.info('ecs-pipeline-deploy v%s starting', __version__)
    ECSPipeline(args).deploy()


def silence_noisy_loggers():
    """Some things are noisier than others. Some libraries mothers are noisier
    than other libraries mothers.

    """
    for logger in ['boto3', 'botocore',
                   'urllib3.connectionpool',
                   'botocore.vendored.requests.packages.urllib3']:
        logging.getLogger(logger).setLevel(logging.WARNING)
